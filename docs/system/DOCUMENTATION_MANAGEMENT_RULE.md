# 系统级文档管理规范 (System Documentation Rules)

本文档定义了本项目中 AI 与开发者共同维护文档、管理分类以及同步 Skills 的核心规则。

## 1. 核心原则 (Core Principles)

1.  **分类即秩序 (Categorization is Order)**: 所有文档必须归类到 `docs/` 下的子目录中，严禁在 `docs/` 根目录直接存放散乱文件。
2.  **自动归档 (Auto-Archiving)**: AI 在生成新文档时，必须先判断其所属类别。
    *   如果属于现有类别，放入对应子目录。
    *   如果不属于任何现有类别，**必须**创建一个新的子目录（分类）。
3.  **Skills 同步 (Skills Synchronization)**: 文档分类与 `.trae/skills/` 下的 Skill 是一一对应的关系。
    *   `docs/<category>/` 对应 `.trae/skills/<category-skill>/`
    *   当新建分类时，必须同步创建对应的 Skill。
    *   当新增文档时，必须更新对应 Skill 的引用列表。
4.  **复用优于新建 (Reuse over Create)**:
    *   当新功能与旧功能冲突时，**优先更新旧文档**，记录变更点和新逻辑。
    *   **不要**创建 "V2", "New" 等后缀的重复文档，除非是完全重写的重大版本迭代。
    *   如果旧文档已完全废弃，应将其标记为 `[DEPRECATED]` 或直接删除（需用户确认）。
5.  **语言规范 (Language Policy)**:
    *   **`docs/` 下的文档**: 必须使用 **中文 (Chinese)** 编写，方便用户阅读和理解。
    *   **`.trae/skills/` 下的 Skill**: 必须使用 **英文 (English)** 编写，方便 AI 模型理解语义和意图。

## 2. 目录结构 (Directory Structure)

```text
project_root/
├── docs/
│   ├── devops/           # 部署、CI/CD、服务器相关
│   ├── architecture/     # 系统架构、用户体系、核心设计
│   ├── features/         # 具体功能特性的实现细节
│   ├── system/           # 系统级规范（本文档所在）
│   └── <new_category>/   # AI 自动创建的新分类
└── .trae/
    └── skills/
        ├── devops-guide/     # 对应 docs/devops/
        ├── user-system-arch/ # 对应 docs/architecture/
        ├── feature-refactor/ # 对应 docs/features/
        └── <new-skill>/      # 对应 docs/<new_category>/
```

## 3. AI 操作指南 (AI Operation Guide)

当 AI 需要创建新文档时，请遵循以下决策流程：

### 步骤 1: 确定分类
*   分析文档内容。
*   检查现有 `docs/` 子目录。
*   **匹配成功**: 使用该目录。
*   **匹配失败**:
    *   创建一个新的英文目录名（例如 `api-reference`, `testing`）。
    *   执行 `mkdir -p docs/<new_name>`。

### 步骤 2: 编写/更新文档
*   在目标目录下创建或编辑 `.md` 文件。
*   **语言**: 使用中文。
*   **内容**: 确保包含 "背景"、"方案"、"变更点" 等关键信息。

### 步骤 3: 同步 Skill
*   检查 `.trae/skills/` 下是否有对应的 Skill。
*   **如果有**:
    *   编辑 `SKILL.md`。
    *   在 "Reference Documentation" 部分添加新文档的引用链接。
*   **如果没有**:
    *   使用 `skill-creator` 工具（或手动创建目录）创建新 Skill。
    *   `name`: 与 `docs` 子目录名保持语义一致（可加后缀，如 `testing-guide`）。
    *   `description`: 英文描述该分类的用途。
    *   `content`: 列出该分类下的文档索引。

## 4. 维护与清理 (Maintenance)
*   定期检查 `docs/` 目录，发现未分类文件（Orphaned Files）时，主动将其归类。
*   发现 Skill 中的坏链（Dead Links）时，主动修复。
