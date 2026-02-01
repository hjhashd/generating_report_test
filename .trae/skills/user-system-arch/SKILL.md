---
name: "user-system-arch"
description: "Manages user system architecture, authentication, and multi-user refactoring. Invoke when user asks about user accounts, login, or system architecture."
---

# User System Architecture

This skill captures the architecture and refactoring plans for the multi-user system.

## Reference Documentation

The following documentation files in `docs/architecture/` are the source of truth:

- [user_auth_plan.md](file:///root/zzp/langextract-main/generate_report_test/docs/architecture/user_auth_plan.md): User authentication implementation plan.
- [user_import_refactor_plan.md](file:///root/zzp/langextract-main/generate_report_test/docs/architecture/user_import_refactor_plan.md): Refactoring plan for user data import.
- [user_multi_user_gap_plan.md](file:///root/zzp/langextract-main/generate_report_test/docs/architecture/user_multi_user_gap_plan.md): Gap analysis for multi-user support.
- [user_path_refactor_plan.md](file:///root/zzp/langextract-main/generate_report_test/docs/architecture/user_path_refactor_plan.md): File path isolation and refactoring for multi-user.
- [user_rule.md](file:///root/zzp/langextract-main/generate_report_test/docs/architecture/user_rule.md): Business rules for users.

## Core Concepts

- **Multi-user Isolation**: Each user has isolated paths for resources.
- **Authentication**: Using JWT based auth.
