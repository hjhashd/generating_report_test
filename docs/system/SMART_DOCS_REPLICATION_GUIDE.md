# 智能文档体系复刻指南 (Smart Docs Replication Guide)

本文档旨在帮助开发者将本项目中使用的“自动分类、Skill 同步”的智能文档管理体系，快速迁移并复用到其他项目中。

> **核心理念**: 让 AI 成为文档的“图书管理员”，通过明确的规则和 Skill 绑定，实现文档的自动化维护和精准检索。

## 1. 体系核心三要素 (The Trinity)

要复刻这套体系，必须在目标项目中建立以下三个核心组件：

1.  **物理层 (Physical Layer)**: 结构化的 `docs/` 目录。
    *   **规则**: 严禁散乱文件，所有文档必须归类到子目录。
    *   **作用**: 保持文件系统整洁，隐含分类语义。

2.  **逻辑层 (Logical Layer)**: `docs/system/DOCUMENTATION_MANAGEMENT_RULE.md`。
    *   **规则**: 定义了“如何分类”、“语言规范”以及“AI 操作准则”。
    *   **作用**: 作为 AI 的“宪法”，指导 AI 的每一次文档操作。

3.  **智能层 (Intelligence Layer)**: `.trae/skills/doc-manager`。
    *   **规则**: 一个专门的 Skill，强制 AI 在处理文档任务时读取上述规则。
    *   **作用**: 将死板的规则转化为 AI 的可执行能力。

## 2. 迁移步骤 (Migration Steps)

请按照以下步骤在您的新项目中部署此体系：

### 第一步：初始化目录结构
在项目根目录下执行：

```bash
mkdir -p docs/system
mkdir -p .trae/skills/doc-manager
```

### 第二步：植入核心规则
复制本项目的 `docs/system/DOCUMENTATION_MANAGEMENT_RULE.md` 到新项目的相同位置。
*   **因地制宜 (Adaptability)**:
    *   如果您的项目是纯英文项目，请修改规则中的“语言规范”，要求所有文档使用英文。
    *   如果您的项目是 Monorepo，可能需要定义更深层级的目录结构（如 `docs/packages/frontend/`）。

### 第三步：激活智能 Skill
在 `.trae/skills/doc-manager/` 下创建 `SKILL.md`，内容如下（可直接复用）：

```markdown
---
name: "doc-manager"
description: "Manages project documentation structure and rules. Invoke when user wants to create docs, organize files, or asks about documentation standards."
---

# Documentation Manager

This skill enforces the system-level documentation rules defined in `docs/system/DOCUMENTATION_MANAGEMENT_RULE.md`.

## Core Responsibilities
1. **Classification**: Ensure all markdown files in `docs/` are categorized.
2. **Syncing**: Maintain 1:1 mapping between `docs/<category>/` and `.trae/skills/<skill>/`.
3. **Evolution**: Update existing docs instead of creating duplicates.

## Reference
[DOCUMENTATION_MANAGEMENT_RULE.md](file:///path/to/your/project/docs/system/DOCUMENTATION_MANAGEMENT_RULE.md)
```

### 第四步：整理现有资产
如果新项目中已经有一堆散乱的文档：
1.  **不要手动整理**。
2.  告诉 AI：“我已经配置好了 `doc-manager`，请帮我把 `docs/` 下的旧文档按规则整理好。”
3.  AI 会自动创建分类目录、移动文件，并为你生成对应的 Skills。

## 3. 体系的自我进化 (Self-Evolution)

这套体系不是一成不变的。随着项目架构的演进，文档管理规则也需要升级。

**给 AI 的指令**:
当您（AI）发现现有的文档结构或管理规则不再适应当前的项目规模（例如：子目录过多、分类维度混乱）时，请主动执行以下操作：

1.  **提出优化方案**: 比如引入二级目录，或者拆分过大的 Skill。
2.  **更新规则文档**: 直接修改 `docs/system/DOCUMENTATION_MANAGEMENT_RULE.md`，记录新的共识。
3.  **更新本指南**: **非常重要！** 修改本文件 (`SMART_DOCS_REPLICATION_GUIDE.md`)，将新的最佳实践记录下来，确保这套“火种”永远保持最先进的状态。

## 4. 常见场景适配 (Adaptability Scenarios)

*   **微服务架构**: 建议在 `docs/` 下按服务名一级分类（`docs/service-a/`），Skill 命名为 `service-a-guide`。
*   **开源项目**: 建议增加 `docs/community/` 分类，存放贡献指南、Code of Conduct 等。
*   **科研项目**: 建议增加 `docs/papers/` 或 `docs/experiments/` 分类。

---
*版本: 1.0.0*
*最后更新: 2026-01-31*
