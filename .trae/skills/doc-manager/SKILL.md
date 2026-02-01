---
name: "doc-manager"
description: "Manages project documentation structure and rules. Invoke when user wants to create docs, organize files, or asks about documentation standards."
---

# Documentation Manager

This skill enforces the system-level documentation rules defined in `docs/system/DOCUMENTATION_MANAGEMENT_RULE.md`.

## Core Responsibilities

1.  **Classification**: Ensure all markdown files in `docs/` are categorized into subdirectories.
2.  **Syncing**: Maintain 1:1 mapping between `docs/<category>/` and `.trae/skills/<skill>/`.
3.  **Language**: Enforce Chinese for `docs/*.md` and English for `skills/*.md`.
4.  **Evolution**: Update existing docs instead of creating duplicates.

## Operation Rules

### When Creating New Docs
1.  **Analyze** the content to find a matching `docs/` subdirectory.
2.  **If no match**, create a new subdirectory (e.g., `docs/security/`).
3.  **Write** the document in **Chinese**.
4.  **Update/Create Skill**:
    - If `docs/security/` is new, create `.trae/skills/security-guide/SKILL.md`.
    - If existing, add the new file link to the Skill's reference list.

## System Documentation
- [DOCUMENTATION_MANAGEMENT_RULE.md](file:///root/zzp/langextract-main/generate_report_test/docs/system/DOCUMENTATION_MANAGEMENT_RULE.md): The core rules.
- [SMART_DOCS_REPLICATION_GUIDE.md](file:///root/zzp/langextract-main/generate_report_test/docs/system/SMART_DOCS_REPLICATION_GUIDE.md): Guide for replicating this system in other projects.
