"""
Rule definitions for the Helix notebook linter.

Each rule is a class with its own detection logic. No YAML pretending to be configurable.
"""

import ast
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Optional

from .analyzer import AnalysisContext, Violation


def _class_name_to_id(name: str) -> str:
    """
    Convert CamelCase class name to kebab-case id.

    NoSparkReadParquet -> no-spark-read-parquet
    """
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
    return s.lower()


@dataclass
class Rule(ABC):
    """Base class for all linting rules."""

    message: str
    replacement: Optional[str] = None
    suggestion: Optional[str] = None
    auto_fix: Optional[str] = None

    @property
    def id(self) -> str:
        """Auto-generate rule id from class name."""
        return _class_name_to_id(self.__class__.__name__)

    @abstractmethod
    def check(self, node: ast.AST, context: "RuleContext") -> Optional[Violation]:
        """Check if this node violates the rule. Return Violation or None."""
        pass

    def create_violation(self, node: ast.AST, source_lines: list[str], **kwargs) -> Violation:
        """Helper to create a violation with this rule's metadata."""
        snippet = source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
        return Violation(
            rule_id=self.id,
            line=node.lineno,
            column=node.col_offset,
            code_snippet=snippet,
            message=kwargs.get("message", self.message),
            replacement=kwargs.get("replacement", self.replacement),
            suggestion=kwargs.get("suggestion", self.suggestion),
            auto_fix=kwargs.get("auto_fix", self.auto_fix),
            fix_data=kwargs.get("fix_data"),
        )


@dataclass
class RuleContext:
    """Context passed to rules during checking."""

    source_lines: list[str]
    analysis_context: AnalysisContext
    # Track what's been reported to avoid duplicates
    reported: set = field(default_factory=set)

    def is_tracked_object(self, name: str) -> bool:
        """Check if name is a tracked object (spark, etc) or alias."""
        return self.analysis_context.is_tracked(name)

    def get_base_object(self, name: str) -> Optional[str]:
        """Get the base object for an alias."""
        return self.analysis_context.get_base_object(name)


@dataclass
class HelixutilsNoWildcardImport(Rule):
    """Wildcard imports from helixutils are not allowed."""

    message: str = "Wildcard imports are not allowed for helixutils."
    suggestion: str = "from helixutils import connection, helix_read"

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for wildcard imports from helixutils."""
        if not isinstance(node, ast.ImportFrom):
            return None
        if node.module != "helixutils":
            return None
        for alias in node.names:
            if alias.name == "*":
                return self.create_violation(node, context.source_lines)
        return None


@dataclass
class HelixutilsPrivateAccess(Rule):
    """Direct access to private helixutils modules (e.g. _var, _internal) is not allowed."""

    message: str = "Direct access to private helixutils modules is not allowed. Use exported APIs."
    suggestion: str = "Import from helixutils directly: from helixutils import ..."

    # Known private modules in helixutils
    _PRIVATE_MODULES: ClassVar[set[str]] = {"_var", "_internal", "_config", "_utils"}

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for direct access to private helixutils modules."""
        # Check for: from helixutils._var import ...
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("helixutils._"):
                return self.create_violation(node, context.source_lines)
            return None

        # Check for: helixutils._var.something or _var.something (if _var was imported)
        if isinstance(node, ast.Attribute):
            # helixutils._var.attr pattern
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "helixutils"
                and node.value.attr.startswith("_")
            ):
                return self.create_violation(node, context.source_lines)
            # Direct _var.attr where _var is a known helixutils private module
            if isinstance(node.value, ast.Name) and node.value.id in self._PRIVATE_MODULES:
                return self.create_violation(node, context.source_lines)
        return None


# =============================================================================
# SPARK READ RULES
# =============================================================================


class SparkReadRule(Rule):
    """Base for spark.read.* rules - detects method chains on spark."""

    chain: list[str] = field(default_factory=list)  # e.g., ["read", "parquet"]
    format_arg: Optional[str] = None  # For read.format("delta").load()

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for spark.read.* method chains."""
        if not isinstance(node, ast.Call):
            return None

        # Build the method chain from this call
        chain = self._extract_chain(node)
        if not chain:
            return None

        base_obj, methods = chain[0], chain[1:]

        # Must start with tracked object (spark or alias)
        if not context.is_tracked_object(base_obj):
            return None

        # Check if chain matches
        if not self._chain_matches(methods, node):
            return None

        return self.create_violation(node, context.source_lines)

    def _extract_chain(self, node: ast.Call) -> list[str]:
        """Extract method chain like ['spark', 'read', 'parquet'] from a Call node."""
        chain = []
        current = node.func

        while isinstance(current, ast.Attribute):
            chain.append(current.attr)
            current = current.value
            if isinstance(current, ast.Call):
                current = current.func

        if isinstance(current, ast.Name):
            chain.append(current.id)

        chain.reverse()
        return chain

    def _chain_matches(self, methods: list[str], node: ast.Call) -> bool:
        """Check if the method chain matches our target pattern."""
        # Check direct chain match (e.g., read.parquet)
        if self.chain and methods == self.chain:
            return True
        # Check format pattern match (e.g., read.format("parquet").load())
        if self.format_arg and methods == ["read", "format", "load"]:
            return self._has_format_arg(node, self.format_arg)
        return False

    def _has_format_arg(self, node: ast.Call, expected_format: str) -> bool:
        """Check if a .format() call in the chain has the expected argument."""
        # Walk up to find the format() call
        current = node.func
        while isinstance(current, ast.Attribute):
            if isinstance(current.value, ast.Call):
                call = current.value
                if (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == "format"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                ):
                    val = call.args[0].value if isinstance(call.args[0], ast.Constant) else call.args[0].s
                    return val == expected_format
            current = current.value
        return False


@dataclass
class NoSparkReadParquet(SparkReadRule):
    """Detect spark.read.parquet() usage."""

    message: str = "Use helix_read.parquet() instead of spark.read.parquet()"
    replacement: str = "helix_read.parquet(path)"
    chain: list = field(default_factory=lambda: ["read", "parquet"])
    format_arg: str = "parquet"  # Also catches read.format('parquet').load()


@dataclass
class NoSparkReadDelta(SparkReadRule):
    """Detect spark.read.delta() usage."""

    message: str = "Use helix_read.delta() instead of spark.read.delta()"
    replacement: str = "helix_read.delta(path)"
    chain: list = field(default_factory=lambda: ["read", "delta"])
    format_arg: str = "delta"  # Also catches read.format('delta').load()


@dataclass
class NoSparkReadCsv(SparkReadRule):
    """Detect spark.read.csv() usage."""

    message: str = "Use helix_read.csv() instead of spark.read.csv()"
    replacement: str = "helix_read.csv(path, **options)"
    chain: list = field(default_factory=lambda: ["read", "csv"])
    format_arg: str = "csv"  # Also catches read.format('csv').load()


@dataclass
class NoSparkReadTable(SparkReadRule):
    """Detect spark.read.table() usage."""

    message: str = "spark.read.table() is redundant. Use spark.table() directly."
    replacement: str = "spark.table(tablename)"
    chain: list = field(default_factory=lambda: ["read", "table"])


# =============================================================================
# SPARK WRITE RULES
# =============================================================================


@dataclass
class NoWriteFormatDelta(SparkReadRule):
    """Detect df.write.format('delta')...save()"""

    message: str = "Use DataFrame.write_delta() instead of .write.format('delta')...save()"
    replacement: str = "df.write_delta(path, mode='overwrite', mergeSchema=True)"
    format_arg: str = "delta"

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for df.write.format('delta')...save() pattern."""
        if not isinstance(node, ast.Call):
            return None

        chain = self._extract_chain(node)
        if len(chain) < 2:
            return None

        methods = chain[1:]  # Skip the base object (any DataFrame)

        # Check for write.format.*.save pattern
        if "write" in methods and "format" in methods and "save" in methods and self._has_format_arg(node, "delta"):
            return self.create_violation(node, context.source_lines)
        return None


# =============================================================================
# LEGACY CONTEXT RULES
# =============================================================================


@dataclass
class NoSqlContext(Rule):
    """Detect deprecated sqlContext usage."""

    message: str = "sqlContext is deprecated. Use spark instead."
    replacement: str = "spark"

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for sqlContext usage."""
        if isinstance(node, ast.Name) and node.id == "sqlContext":
            return self.create_violation(node, context.source_lines)
        return None


# =============================================================================
# METHOD CALL RULES
# =============================================================================


@dataclass
class NoCreateOrReplaceTempView(Rule):
    """Detect createOrReplaceTempView() usage."""

    message: str = "Use .to_view() instead of createOrReplaceTempView()"
    replacement: str = "df.to_view('viewname')"

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for createOrReplaceTempView usage."""
        if not isinstance(node, ast.Call):
            return None
        if isinstance(node.func, ast.Attribute) and node.func.attr == "createOrReplaceTempView":
            return self.create_violation(node, context.source_lines)
        return None


# =============================================================================
# STAGING RULES
# =============================================================================


@dataclass
class NoTempDefaultUsage(Rule):
    """Detect writes to temp_default storage."""

    message: str = "Use to_staged_view() instead of writing to temp_default"
    replacement: str = "df.to_staged_view('viewName')"

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for temp_default connection usage."""
        if not isinstance(node, ast.Subscript):
            return None
        # Check for connection["temp_default"] or similar
        slice_val = None
        if isinstance(node.slice, ast.Constant):
            slice_val = node.slice.value

        if slice_val == "temp_default":
            return self.create_violation(node, context.source_lines)
        return None


# =============================================================================
# PATH RULES (from Validate_Notebook.yml)
# =============================================================================


@dataclass
class NoWildcardPaths(Rule):
    """Detect /*/ wildcard paths in reads for HelixData connections."""

    message: str = "Do not use /*/ wildcard paths - breaks dependency crawler."
    suggestion: str = "Specify explicit paths or use date ranges"

    # Connections where wildcard paths are problematic
    _HELIX_CONNECTIONS: ClassVar[set[str]] = {
        "core_default",
        "tabular_default",
        "staging_default",
        "source_lakehouse",
    }

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for wildcard paths in HelixData connection strings."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "/*/" in node.value:
            # Check if this line also references a HelixData connection
            line = context.source_lines[node.lineno - 1] if node.lineno <= len(context.source_lines) else ""
            for conn in self._HELIX_CONNECTIONS:
                if conn in line:
                    return self.create_violation(node, context.source_lines)
        return None


@dataclass
class NoNonDefaultHelixConnections(Rule):
    """HelixData connections should use standard suffixes (_prod, _default)."""

    message: str = "HelixData connections should use standard names."
    suggestion: str = "Use core_default, tabular_default, or staging_default"

    # Valid connection names
    _VALID_CONNECTIONS: ClassVar[set[str]] = {
        "core_default",
        "restricted_core_default",
        "tabular_default",
        "restricted_tabular_default",
        "staging_default",
        "source_lakehouse",
        "temp_default",
    }

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check for non-standard HelixData connection names."""
        # Check for connection["core_xyz"] style access
        if not isinstance(node, ast.Subscript):
            return None

        slice_val = None
        if isinstance(node.slice, ast.Constant):
            slice_val = node.slice.value

        if not isinstance(slice_val, str):
            return None

        # Check if it's a HelixData connection but not the standard name
        prefixes = ("core", "restricted", "tabular", "staging", "source", "temp")
        if any(slice_val.startswith(p) for p in prefixes) and slice_val not in self._VALID_CONNECTIONS:
            return self.create_violation(node, context.source_lines)
        return None


# =============================================================================
# DIM TABLE VALIDATION RULES
# =============================================================================


@dataclass
class DimTableChecksRequired(Rule):
    """
    DIM table writes must have CheckConfig with isUnique and isComplete constraints.

    Validates that write_delta calls to /DIM_*/ paths have:
    1. A checks= parameter
    2. The CheckConfig has isUnique called with a DIM_ column
    3. The CheckConfig has isComplete called with a DIM_ column
    """

    message: str = "DIM table write_delta requires CheckConfig with isUnique and isComplete on DIM_ columns"
    suggestion: str = "checks = CheckConfig(); checks.error.isUnique('DIM_Id').isComplete('DIM_Id')"

    def check(self, node: ast.AST, context: RuleContext) -> Optional[Violation]:
        """Check that DIM table writes have proper CheckConfig constraints."""
        if not isinstance(node, ast.Call):
            return None

        # Check if this is a write_delta call
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "write_delta"):
            return None

        # Check if writing to a DIM_ table (look for /DIM_ in path arguments)
        if not self._is_dim_table_write(node):
            return None

        # Check for checks= keyword argument
        checks_var = None
        for keyword in node.keywords:
            if keyword.arg == "checks":
                if isinstance(keyword.value, ast.Name):
                    checks_var = keyword.value.id
                break

        if checks_var is None:
            return self.create_violation(
                node,
                context.source_lines,
                message="DIM table write_delta is missing checks= parameter",
            )

        # Validate the CheckConfig variable has required constraints
        check_config_info = context.analysis_context.check_configs.get(checks_var)
        if check_config_info is None:
            return self.create_violation(
                node,
                context.source_lines,
                message=f"CheckConfig '{checks_var}' not found or not properly configured",
            )

        has_unique, has_complete = check_config_info
        missing = []
        if not has_unique:
            missing.append("isUnique('DIM_...')")
        if not has_complete:
            missing.append("isComplete('DIM_...')")

        if missing:
            return self.create_violation(
                node,
                context.source_lines,
                message=f"CheckConfig '{checks_var}' is missing: {', '.join(missing)}",
            )

        return None

    def _is_dim_table_write(self, node: ast.Call) -> bool:
        """Check if this write_delta is targeting a DIM_ table."""
        # Check positional args and target_path keyword for /DIM_ pattern
        for arg in node.args:
            if self._contains_dim_path(arg):
                return True

        for keyword in node.keywords:
            if keyword.arg in ("target_path", None) and self._contains_dim_path(keyword.value):
                return True

        return False

    def _contains_dim_path(self, node: ast.AST) -> bool:
        """Check if an AST node contains a /DIM_ path string."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return "/DIM_" in node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self._contains_dim_path(node.left) or self._contains_dim_path(node.right)
        if isinstance(node, ast.JoinedStr):  # f-string
            for value in node.values:
                if self._contains_dim_path(value):
                    return True
        if isinstance(node, ast.FormattedValue):
            return self._contains_dim_path(node.value)
        return False


# =============================================================================
# RULE REGISTRY
# =============================================================================

# All rules - instantiate once
ALL_RULES: list[Rule] = [
    # Import rules
    HelixutilsNoWildcardImport(),
    HelixutilsPrivateAccess(),
    # Spark read rules
    NoSparkReadParquet(),
    NoSparkReadDelta(),
    NoSparkReadCsv(),
    NoSparkReadTable(),
    # Spark write rules
    NoWriteFormatDelta(),
    # Legacy context
    NoSqlContext(),
    # Method calls
    NoCreateOrReplaceTempView(),
    # Staging
    NoTempDefaultUsage(),
    # Path rules
    NoWildcardPaths(),
    NoNonDefaultHelixConnections(),
    # DIM table validation
    DimTableChecksRequired(),
]

# Tracked objects for alias detection
TRACKED_OBJECTS = {"spark", "sqlContext"}
