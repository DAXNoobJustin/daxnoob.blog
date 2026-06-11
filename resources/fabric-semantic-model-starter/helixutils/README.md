# HelixUtils

HelixUtils is a Python library that provides specialized utilities for Microsoft Fabric Spark environments, specifically designed for HelixData workflows. It includes tools for data reading, quality checking, incident alerting, secret management, Delta operations, and tabular model processing.

## Features

### 📊 Data Reading & Processing

-   **Multi-format Data Reading**: Read from Delta, Parquet, CSV, SQL endpoints, and Kusto clusters
-   **Schema Mismatch Handling**: Read parquet files whose schema evolves over time
-   **Linked Service Integration**: Connect to configured SQL / Kusto sources
-   **DataFrame Extensions**: Spark DataFrame helpers via monkey patching — `to_view`, `to_staged_view`, `write_delta`, `write_parquet`, `select_except`, `check`

### 🔍 Data Quality & Validation

-   **PyDeequ-based Checks**: Uniqueness, completeness, and other PyDeequ constraints via `CheckConfig`
-   **Row-count Drift**: Flag tables whose row count moves outside a ratio band vs. the previous version
-   **Consecutive-date Gaps**: Detect missing dates per dimension within a backfill window
-   **Write-time Enforcement**: `write_delta(checks=...)` runs the checks and can raise an incident on failure

> 📖 Background: [Sometimes it's good to fail: raising errors with data-quality tests](https://daxnoob.blog/sometimes-its-good-to-fail-raising-errors-with-data-quality-tests/) — the `checks.error` (fail the load) vs `.warn` philosophy.

### 🔔 Monitoring & Incident Management

-   **Incident Webhook**: `create_incident(...)` posts to a configurable webhook (ticketing API, PagerDuty, Teams, etc.) — prod-gated

### 🔐 Security & Vault Management

-   **Azure Key Vault Integration**: Secure secret retrieval via NotebookUtils credentials
-   **Token Management**: AAD token acquisition for Azure services
-   **Environment-aware Configuration**: Variable libraries resolve per environment (dev / test / prod)

### 🏗️ Tabular & Delta Management

-   **Tabular Processing**: `write_delta(tabular=True)` preps a table for DirectLake — derives `DIM_CalendarKey`, reduces facts to surviving dimension members (left-semi join), and auto-partitions large facts by `DIM_CalendarKey` (with per-table overrides). Reusable key-replacement helpers extend it for your own star schema
-   **Delta Table Management**: Vacuum with retention, plus version-aware rollback

## Documentation

### Main Modules

-   **`helix_read`**: Data reading utilities for Delta, Parquet, SQL, and Kusto sources
-   **`helix_check` / `CheckConfig`**: PyDeequ-based data-quality checks (uniqueness, completeness, row-count drift)
-   **`helix_monitoring`**: Incident webhook + alerting (prod-gated)
-   **`helix_vault`**: Azure Key Vault integration and secure secret management
-   **`helix_tabular`**: Tabular processing for DirectLake — calendar-key derivation, dimension reduction (left-semi), partitioning, + reusable key-replacement helpers
-   **`helix_delta`**: Delta Lake operations and table management

### Common Patterns

```python
# Pattern 1: Data pipeline with quality checks
from helixutils import CheckConfig, helix_read, helix_vault

df = helix_read.sql_endpoint("source_db", "SELECT * FROM daily_data")

checks = CheckConfig("Daily validation")
checks.error.isComplete("id").hasConsecutiveDates(group_by="DIM_Product", day_count=60)
df.check(checks)

# Pattern 2: Secure configuration retrieval
connection_string = helix_vault.get_helix_secret("db-connection")
api_token = helix_vault.get_token("https://management.azure.com/.default")
```

## Requirements

-   Python 3.10+ (< 3.13)
-   Microsoft Fabric Spark environment
-   PySpark 3.5+
-   Access to Azure Key Vault (for secret management)
-   Configured linked services (for data source connectivity)

## Contributing

A utility library for Fabric Spark data-engineering workflows in this repo.

### Development Setup

```bash
# Clone and install in development mode (with dev dependencies)
git clone <repository-url>
cd helixutils
pip install -e ".[dev]"
```

## License

MIT License - Copyright (c) Microsoft Corporation
