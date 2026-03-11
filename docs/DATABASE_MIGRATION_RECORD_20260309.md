# 生产环境数据库数据迁移记录

> **执行日期**：2026-03-09  
> **执行人**：Trae AI Assistant  
> **关联问题**：前端首页无数据显示

## 问题概述

### 现象
前端生产环境首页无法显示任何数据（标签树、公开提示词等），但数据库中确实存在数据。

### 根本原因
生产环境连接的数据库 `generating_reports` 与测试环境 `generating_reports_test` 数据不同步，导致生产库中缺少必要的数据。

### 数据库连接配置
| 环境 | 配置文件 | 数据库名 |
|------|---------|---------|
| 生产环境 | `ljt/prompt-system-backend/prod.env` | `generating_reports` |
| 测试环境 | `ljt/prompt-system-backend/.env` | `generating_reports_test` |

---

## 数据对比

### 迁移前数据状态

| 表名 | generating_reports | generating_reports_test |
|------|-------------------|------------------------|
| `ai_prompt_tags` | 0 条 | 38 条 |
| `ai_prompt_tag_relation` | 0 条 | 131 条 |
| `ai_user_interactions` | 0 条 | 6 条 |
| `ai_prompts (status=2 公开)` | 0 条 | 37 条 |
| `ai_prompts (status=1 私有)` | 128 条 | 768 条 |

### 关键发现
1. `ai_prompt_tags` 表为空 → 前端无法显示标签树
2. `ai_prompts` 表中 `status=2`（公开状态）的数据为 0 → 前端广场无内容

---

## 迁移执行

### 1. 迁移标签数据

```sql
-- 迁移 ai_prompt_tags 表
INSERT INTO generating_reports.ai_prompt_tags 
SELECT * FROM generating_reports_test.ai_prompt_tags
ON DUPLICATE KEY UPDATE tag_name = VALUES(tag_name);

-- 迁移 ai_prompt_tag_relation 表
INSERT IGNORE INTO generating_reports.ai_prompt_tag_relation
SELECT * FROM generating_reports_test.ai_prompt_tag_relation;

-- 迁移 ai_user_interactions 表
INSERT IGNORE INTO generating_reports.ai_user_interactions
SELECT * FROM generating_reports_test.ai_user_interactions;
```

### 2. 迁移公开提示词数据

由于两个数据库的 `ai_prompts` 表 ID 范围重叠（都是 1-839），直接 INSERT 会冲突，需要使用 UPDATE 方式：

```sql
-- 将 generating_reports 中与 test 库 status=2 相同 ID 的记录更新为公开
UPDATE generating_reports.ai_prompts t1
INNER JOIN generating_reports_test.ai_prompts t2 ON t1.id = t2.id
SET t1.status = 2, 
    t1.title = t2.title, 
    t1.content = t2.content, 
    t1.description = t2.description,
    t1.user_input_example = t2.user_input_example, 
    t1.variables_json = t2.variables_json,
    t1.model_config_json = t2.model_config_json, 
    t1.department_id = t2.department_id,
    t1.icon_code = t2.icon_code, 
    t1.view_count = t2.view_count, 
    t1.like_count = t2.like_count,
    t1.favorite_count = t2.favorite_count, 
    t1.copy_count = t2.copy_count
WHERE t2.status = 2;
```

---

## 迁移结果

### 迁移后数据状态

| 表名 | 迁移前 | 迁移后 | 状态 |
|------|--------|--------|------|
| `ai_prompt_tags` | 0 | 38 | ✅ |
| `ai_prompt_tag_relation` | 0 | 131 | ✅ |
| `ai_user_interactions` | 0 | 6 | ✅ |
| `ai_prompts (status=2)` | 0 | 37 | ✅ |

### 验证命令

```sql
-- 验证标签数据
SELECT COUNT(*) FROM generating_reports.ai_prompt_tags WHERE type = 1;

-- 验证公开提示词
SELECT status, COUNT(*) FROM generating_reports.ai_prompts GROUP BY status;

-- 验证标签关联
SELECT COUNT(*) FROM generating_reports.ai_prompt_tag_relation;
```

---

## 服务重启

迁移完成后需重启 Java 后端服务：

```bash
cd /root/zzp/langextract-main/ljt/prompt-system-backend
./prod_service.sh restart
```

---

## 注意事项

1. **数据一致性**：此次迁移仅同步了必要的数据，两个数据库的完整数据仍有差异。如需完全同步，建议使用数据库导出/导入工具。

2. **ID 冲突处理**：由于两个数据库的表 ID 范围重叠，迁移时使用了 UPDATE 而非 INSERT，确保已存在的记录被正确更新。

3. **后续维护**：建议在测试环境验证新功能后，及时将相关数据同步到生产数据库，避免再次出现数据不一致问题。

---

## 相关文件

- 生产环境配置：`/root/zzp/langextract-main/ljt/prompt-system-backend/prod.env`
- 测试环境配置：`/root/zzp/langextract-main/ljt/prompt-system-backend/.env`
- 数据库结构：`/root/zzp/langextract-main/generate_report_test/docs/database/generating_reports_test_v2.sql`
- 服务启动脚本：`/root/zzp/langextract-main/ljt/prompt-system-backend/prod_service.sh`
