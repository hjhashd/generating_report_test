---
name: "database-schema"
description: "Provides precise access to the project's database schema, table definitions, and migration scripts. Invoke when user asks about database tables, fields, or migration."
---

# Database Schema Knowledge Base

This skill provides access to the SQL definitions and migration scripts stored in `docs/database/`.

## Core Resources

1.  **Current Schema**: [generating_reports_test.sql](file:///root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test.sql) - The existing database state.
2.  **Target Schema (V2)**: [generating_reports_test_v2.sql](file:///root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test_v2.sql) - The designed final state with all new modules.
3.  **Migration Script**: [generating_reports_test_migration_v2.sql](file:///root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test_migration_v2.sql) - Incremental updates to transition from Current to Target without data loss.

## Documentation
- [README.md](file:///root/zzp/langextract-main/generate_report_test/docs/database/README.md): Detailed explanation of the files.

## Usage Guide
- When analyzing table structure, refer to the **Target Schema (V2)** for the latest design.
- When planning updates, check the **Migration Script** to see how changes are applied.
- Always check table comments in SQL files for field semantics.
