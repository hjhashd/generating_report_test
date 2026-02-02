# Ops Guide Skill

**Description:** Manages operational tasks including deployment, user permissions, and log monitoring.

**Reference Documents:**
- [LOG_MANAGEMENT.md](../../../docs/ops/LOG_MANAGEMENT.md): Details about log file locations and monitoring commands.

**Context:**
- Always check the current user before running deployment scripts (prefer `cqj`).
- Use separate log files for different environments to avoid confusion.
- Production logs: `logs/prod_report.log`
- Test logs: `test_report.log`
