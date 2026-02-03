# 数据库结构与迁移 (Database Structure & Migration)

本目录存放项目的数据库表结构定义及迁移脚本，供 AI 检索和开发者参考。

## 文件说明

*   **[generating_reports_test.sql](generating_reports_test.sql)**:
    *   **描述**: 当前线上/现有的数据库表结构快照。
    *   **用途**: 作为基准，了解现有数据模型。

*   **[generating_reports_test_v2.sql](generating_reports_test_v2.sql)**:
    *   **描述**: 经过设计后的全新目标数据库表结构（完整版）。
    *   **用途**: 用于全新部署或参考最终设计形态。包含部门、用户、角色、LLM配置等核心模块。

*   **[generating_reports_test_migration_v2.sql](generating_reports_test_migration_v2.sql)**:
    *   **描述**: 从现有版本平滑升级到 V2 的 **增量迁移脚本**。
    *   **特点**:
        * 使用 `CREATE TABLE IF NOT EXISTS` 和 `information_schema` 检查，**可多次执行且幂等**。
        * 在**保留历史数据**的前提下，逐步补齐字段、索引和新表。
    *   **主要做的几件事**（按模块）：
        * 基础架构：创建 `sys_departments`，为 `users` 增加 `real_name` / `department_id` / `shulingtong_sk` 等字段和索引。
        * 智能报告：升级 `report_name` 状态字段，创建 `report_chapter_content` 存放 Markdown 正文。
        * 提示词系统：创建 `ai_prompts`、目录/目录关联表、标签及标签关联表、交互表、聊天历史表。
        * 日志与图谱：创建 `sys_operation_logs`、`sys_entity_relations` 支持审计和关系图谱。
        * 积分系统：创建 `activity_user_wallet` 和 `activity_point_records`，并通过唯一索引防刷分。
        * 旧表补注释：统一为 `public_prompts`、`roles`、`user_roles`、`llm_config` 等存量表补充字段注释和默认值。
    *   **使用示例**：
        * 线上已有历史数据：在运维窗口执行一次 `generating_reports_test_migration_v2.sql`，即可在不清库的情况下升级到新表结构。
        * 本地开发跟进最新设计：拉取最新代码后，先执行旧版建表脚本（如需），再执行该迁移脚本即可补齐所有新字段、新表。

## 维护指南

当数据库结构发生变更时，请务必同步更新此处的 SQL 文件，并更新本说明文档。
