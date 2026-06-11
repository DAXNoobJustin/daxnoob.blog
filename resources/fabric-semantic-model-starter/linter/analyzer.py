"""AST-based analyzer for detecting code patterns with alias tracking."""

import ast
import re
import warnings
from dataclasses import dataclass, field
from typing import ClassVar, Optional

# Pattern for inline ignore comments: # helix-lint: ignore rule1, rule2
IGNORE_PATTERN = re.compile(r"#\s*helix-lint:\s*ignore\s+(.+)$", re.IGNORECASE)


def parse_ignore_comment(line: str) -> set[str]:
    """Parse a line for helix-lint ignore comments. Returns set of rule IDs to ignore."""
    match = IGNORE_PATTERN.search(line)
    if match:
        rules_str = match.group(1)
        return {r.strip() for r in rules_str.split(",")}
    return set()


@dataclass
class Violation:
    """Represents a single linting violation."""

    rule_id: str
    line: int
    column: int
    code_snippet: str
    message: str
    replacement: Optional[str] = None
    suggestion: Optional[str] = None
    auto_fix: Optional[str] = None
    fix_data: Optional[dict] = None


@dataclass
class AnalysisContext:
    """Tracks aliases and state during AST traversal."""

    aliases: dict = field(default_factory=dict)
    tracked_objects: set = field(default_factory=lambda: {"spark"})
    # Track CheckConfig variables: name -> (has_isUnique_dim, has_isComplete_dim)
    check_configs: dict = field(default_factory=dict)

    def is_tracked(self, name: str) -> bool:
        """Check if name is a tracked object or alias."""
        return name in self.tracked_objects or name in self.aliases

    def get_base_object(self, name: str) -> Optional[str]:
        """Get the base object name for an alias, or the name if it's tracked."""
        if name in self.tracked_objects:
            return name
        return self.aliases.get(name)

    def add_alias(self, alias: str, target: str):
        """Add an alias for a tracked object."""
        base = self.get_base_object(target)
        if base:
            self.aliases[alias] = base


class PatternAnalyzer(ast.NodeVisitor):
    """AST visitor that checks rules against nodes."""

    # Methods called for side effects - removing assignment but keeping the call
    _SIDE_EFFECT_METHODS: ClassVar[set[str]] = {
        "to_view",
        "to_staged_view",
        "create_incident",
        "write_delta",
        "write_parquet",
        "save",
    }

    def __init__(self, source_lines: list[str], rules: list, context: AnalysisContext):
        """Initialize the analyzer with source code, rules, and context."""
        self.source_lines = source_lines
        self.rules = rules
        self.context = context
        self.violations: list[Violation] = []
        self._reported: set[tuple[int, str]] = set()

        # For unused variable tracking
        self._var_assignments: dict[str, tuple[int, int, ast.AST, bool]] = {}
        self._var_usages: set[str] = set()

        # Import here to avoid circular dependency
        from .rules import RuleContext

        self.rule_context = RuleContext(
            source_lines=source_lines,
            analysis_context=context,
            reported=self._reported,
        )

    def analyze(self) -> list[Violation]:
        """Run analysis and return violations."""
        code = "\n".join(self.source_lines)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=SyntaxWarning)
            try:
                tree = ast.parse(code)
            except SyntaxError:
                return []

        # Pre-scan for CheckConfig tracking
        self._prescan_check_configs(tree)

        self.visit(tree)
        self._check_unused_variables()
        return self.violations

    def _prescan_check_configs(self, tree: ast.AST):
        """Pre-scan AST to track CheckConfig assignments and method calls."""
        # First pass: find all CheckConfig() assignments
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "CheckConfig"
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.context.check_configs[target.id] = (False, False)

        # Second pass: find .isUnique() and .isComplete() calls on CheckConfig vars
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                self._track_check_config_methods(node.value)

    def _track_check_config_methods(self, call_node: ast.Call):
        """Track isUnique/isComplete method calls on CheckConfig variables."""
        # Walk the call chain to find the base variable and methods called
        methods_with_args = []
        current = call_node

        while isinstance(current, ast.Call):
            if isinstance(current.func, ast.Attribute):
                method_name = current.func.attr
                # Get first string argument if present
                arg_value = None
                if current.args and isinstance(current.args[0], ast.Constant):
                    arg_value = current.args[0].value
                methods_with_args.append((method_name, arg_value))
                current = current.func.value
            else:
                break

        # Find the base variable name
        base_var = None
        while current:
            if isinstance(current, ast.Name):
                base_var = current.id
                break
            if isinstance(current, ast.Attribute):
                current = current.value
            elif isinstance(current, ast.Call):
                if isinstance(current.func, ast.Attribute):
                    current = current.func.value
                else:
                    break
            else:
                break

        # Update CheckConfig tracking if this is a known config var
        if base_var in self.context.check_configs:
            has_unique, has_complete = self.context.check_configs[base_var]

            for method_name, arg_value in methods_with_args:
                if method_name == "isUnique" and isinstance(arg_value, str) and arg_value.startswith("DIM_"):
                    has_unique = True
                elif method_name == "isComplete" and isinstance(arg_value, str) and arg_value.startswith("DIM_"):
                    has_complete = True

            self.context.check_configs[base_var] = (has_unique, has_complete)

    def _is_ignored(self, line: int, rule_id: str, end_line: Optional[int] = None) -> bool:
        """Check if a rule is ignored on a given line (or line range) via inline comment."""
        # For multi-line statements, check all lines from start to end
        if end_line is None:
            end_line = line

        for check_line in range(line, end_line + 1):
            if 1 <= check_line <= len(self.source_lines):
                ignored_rules = parse_ignore_comment(self.source_lines[check_line - 1])
                if rule_id in ignored_rules:
                    return True
        return False

    def visit(self, node: ast.AST):
        """Visit node and check all rules."""
        # Check all rules against this node
        for rule in self.rules:
            violation = rule.check(node, self.rule_context)
            if violation:
                key = (violation.line, violation.rule_id)
                if key not in self._reported:
                    # Check for inline ignore comment (including multi-line statements)
                    end_line = getattr(node, "end_lineno", violation.line)
                    if self._is_ignored(violation.line, violation.rule_id, end_line):
                        continue
                    self._reported.add(key)
                    self.violations.append(violation)

        return super().visit(node)

    def visit_Assign(self, node: ast.Assign):
        """Track aliases and variable assignments."""
        # Track alias assignments
        if isinstance(node.value, ast.Name):
            target_name = node.value.id
            if self.context.is_tracked(target_name):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.context.add_alias(target.id, target_name)

        # Check for side-effect methods
        has_side_effect = self._is_side_effect_assignment(node)

        # Track for unused variable detection
        for target in node.targets:
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                is_single_line = (
                    node.lineno == node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else True
                )
                can_auto_fix = is_single_line and not has_side_effect
                self._var_assignments[target.id] = (node.lineno, target.col_offset, node, can_auto_fix)

        self.generic_visit(node)

    def _is_side_effect_assignment(self, node: ast.Assign) -> bool:
        """Check if RHS is a side-effect method call."""
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            return node.value.func.attr in self._SIDE_EFFECT_METHODS
        return False

    def visit_AugAssign(self, node: ast.AugAssign):
        """Track x += 1 as usage."""
        if isinstance(node.target, ast.Name):
            self._var_usages.add(node.target.id)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """Track variable usage."""
        if isinstance(node.ctx, ast.Load):
            self._var_usages.add(node.id)
        self.generic_visit(node)

    def _check_unused_variables(self):
        """Flag unused variables."""
        for var_name, (line, col, _node, can_auto_fix) in self._var_assignments.items():
            if var_name not in self._var_usages:
                key = (line, "unused-variable")
                if key not in self._reported:
                    # Check for inline ignore comment
                    if self._is_ignored(line, "unused-variable"):
                        continue
                    self._reported.add(key)
                    snippet = self.source_lines[line - 1] if line <= len(self.source_lines) else ""
                    self.violations.append(
                        Violation(
                            rule_id="unused-variable",
                            line=line,
                            column=col,
                            code_snippet=snippet,
                            message=f"Variable is assigned but never used: '{var_name}'",
                            suggestion="Remove the unused variable or prefix with _ to indicate intentionally unused",
                            auto_fix="remove_line" if can_auto_fix else None,
                        )
                    )


def analyze_code(code: str, tracked_objects: Optional[set[str]] = None) -> list[Violation]:
    """Analyze code and return violations."""
    from .rules import ALL_RULES, TRACKED_OBJECTS

    if tracked_objects is None:
        tracked_objects = TRACKED_OBJECTS

    source_lines = code.split("\n")
    context = AnalysisContext(tracked_objects=tracked_objects)
    analyzer = PatternAnalyzer(source_lines, ALL_RULES, context)

    return analyzer.analyze()
