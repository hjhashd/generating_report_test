# Prompt Studio 保存提示词功能文档

本文档记录 Prompt Studio 中"保存提示词"功能的实现方案与使用说明。

---

## 1. 功能概述

用户可从 Prompt Studio 将对话内容或编辑器中的提示词保存到提示词库，支持：
- 保存编辑器内容或 AI 回复
- 私有保存与公开保存（选择部门）
- 标签关联与创建个人标签
- 会话收敛（保存后只显示最终内容）
- 重复保存时更新已有提示词（而非新建）

---

## 2. 核心文件

### 2.1 后端

| 文件 | 说明 |
|------|------|
| `routers/prompt_save_api.py` | 保存提示词 API |
| `routers/prompt_service.py` | 保存提示词核心业务逻辑 |
| `routers/prompt_models.py` | 请求/响应数据模型 |
| `utils/lyf/prompt_chat_async.py` | 会话与消息管理 |

### 2.2 前端

| 文件 | 说明 |
|------|------|
| `src/components/editor/SavePromptModal.vue` | 保存弹窗 |
| `src/components/editor/StudioSidebar.vue` | 侧边栏（标签目录） |
| `src/views/PromptStudio.vue` | 主页面 |
| `src/api/promptSave.ts` | API 封装 |
| `src/stores/chat.ts` | 会话状态管理 |

---

## 3. 数据库变更

### 3.1 增量迁移 SQL

```sql
-- 给 ai_chat_sessions 表添加 ref_prompt_id 字段
ALTER TABLE `ai_chat_sessions` 
ADD COLUMN `ref_prompt_id` bigint NULL DEFAULT NULL COMMENT '引用的提示词ID(用户从哪个提示词开始对话)' 
AFTER `origin_prompt_id`;

-- 添加索引
ALTER TABLE `ai_chat_sessions` 
ADD INDEX `idx_session_ref_prompt`(`ref_prompt_id`);
```

### 3.2 字段说明

| 字段名 | 说明 |
|--------|------|
| `origin_prompt_id` | 用户保存的提示词ID，绑定会话与提示词的关系。保存提示词时更新 |
| `ref_prompt_id` | 引用的提示词ID，用户从哪个提示词开始对话。创建会话时设置 |
| `final_content` | 用户最终保存的提示词内容 |
| `status` | 会话状态：0-进行中, 1-已保存(最终态), 2-已归档, -1-已删除 |

---

## 4. API 接口

### 4.1 保存提示词

**POST** `/api/ai/prompts/save_from_studio`

```json
{
  "session_id": 123,
  "title": "周报润色助手",
  "source_type": "reply",
  "message_id": 456,
  "visibility": "private",
  "department_id": null,
  "tag_ids": [1, 2],
  "finalize_session": true,
  "prompt_id": null
}
```

**字段说明：**
- `prompt_id`: 可选。如果传递了 `prompt_id`，则更新已有提示词；否则创建新提示词

**响应：**
```json
{
  "code": 0,
  "data": {
    "prompt_id": 999,
    "session_id": 123,
    "session_status": 1,
    "final_content": "提示词内容...",
    "is_update": false
  }
}
```

### 4.2 其他接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/ai/prompts/tags/tree` | GET | 获取标签树 |
| `/api/ai/prompts/tags/personal` | POST | 创建个人标签 |
| `/api/ai/prompts/tags/{id}` | DELETE | 删除个人标签 |
| `/api/ai/prompts/tags/{id}/public` | DELETE | 删除自己创建的公共标签 |
| `/api/ai/prompts/departments/tree` | GET | 获取部门树 |
| `/api/ai/prompts/sessions/{id}/save_info` | GET | 获取会话保存信息 |
| `/api/ai/prompts/{id}` | DELETE | 删除自己保存的提示词 |

---

## 5. 保存逻辑详解

### 5.1 核心流程

1. **前端判断**：检查当前会话是否已关联提示词（通过 `session.origin_prompt_id`）
2. **传递参数**：
   - 如果已有关联提示词，传递 `prompt_id` 进行更新
   - 否则不传 `prompt_id`，创建新提示词
3. **后端处理**：
   - 如果传了 `prompt_id`：更新已有提示词
   - 如果没传 `prompt_id`：创建新提示词，`origin_prompt_id` 设为 NULL
4. **会话收敛**：更新会话的 `origin_prompt_id` 为新创建/更新的提示词ID

### 5.2 代码实现

#### 前端 SavePromptModal.vue

```typescript
// 初始化时从会话获取已关联的提示词ID
form.value.promptId = props.promptId || null

// 保存时传递 prompt_id（如果存在）
if (form.value.promptId) {
  saveData.prompt_id = form.value.promptId
}
```

#### 后端 prompt_service.py

```python
async def create_or_update_prompt(self, user, request, content):
    if request.prompt_id:
        # 更新已有提示词
        await self.session.execute(
            text("UPDATE ai_prompts SET title=:title, content=:content WHERE id=:prompt_id"),
            {"prompt_id": request.prompt_id, "title": request.title, "content": content}
        )
        prompt_id = request.prompt_id
    else:
        # 创建新提示词
        await self.session.execute(
            text("INSERT INTO ai_prompts (uuid, title, content, ...) VALUES (...)"),
            {"title": request.title, "content": content, ...}
        )
        prompt_id = result.scalar()
    
    return prompt_id
```

### 5.3 会话收敛逻辑

当 `finalize_session=true` 时：

1. 更新会话状态为已完成（`status=1`）
2. 设置 `origin_prompt_id` 为保存的提示词ID
3. 设置 `final_content` 为保存的内容
4. 标记其他消息为已删除（`is_deleted=1`）
5. 保留选中的消息

```python
async def finalize_session(self, session_id, user_id, prompt_id, final_content, message_id):
    # 更新会话状态
    await self.session.execute(
        text("""
            UPDATE ai_chat_sessions
            SET status = 1,
                origin_prompt_id = :prompt_id,
                final_content = :final_content
            WHERE id = :session_id
        """),
        {"session_id": session_id, "prompt_id": prompt_id, "final_content": final_content}
    )
    
    # 标记其他消息为已删除
    if message_id:
        await self.session.execute(
            text("""
                UPDATE ai_chat_messages
                SET is_deleted = 1, deleted_at = NOW()
                WHERE session_id = :session_id AND id != :message_id
            """),
            {"session_id": session_id, "message_id": message_id}
        )
```

---

## 6. 标签目录功能

### 6.1 功能说明

侧边栏标签目录支持：
- **"全部"默认目录**：显示所有对话记录
- **已保存的提示词**：显示 `origin_prompt_id` 不为空的会话
- **个人标签列表**：用户创建的标签（type=2）
- **收起/展开**：点击标题可收起标签目录

### 6.2 会话过滤

```typescript
// 分离已保存提示词的会话和普通会话
const savedPromptSessions = computed(() => 
  sessions.value.filter(s => s.origin_prompt_id)
)
const normalSessions = computed(() => 
  sessions.value.filter(s => !s.origin_prompt_id)
)
```

---

## 7. 修改记录

### 2024-xx-xx

1. **修复问题**：重复保存时创建新提示词而非更新
   - 前端添加 `promptId` prop，传递已有提示词ID
   - 后端根据 `prompt_id` 判断是更新还是新建

2. **修复问题**：保存时未绑定 origin_prompt_id
   - 修改 `finalizeSession` 默认值为 `true`
   - 确保保存时调用会话收敛逻辑

3. **新增字段**：`ref_prompt_id`
   - 用于记录用户从哪个提示词开始对话
   - 区分于 `origin_prompt_id`（用户保存的提示词ID）
