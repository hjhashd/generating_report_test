# Prompt Studio 保存功能修复文档

## 问题背景

当用户在 Prompt Studio 中选择"当前编辑器"保存提示词时，存在以下问题：

1. **空会话问题**：用户直接进入专业模式编写提示词并保存，会话中没有聊天记录
2. **无关联消息**：保存的提示词没有关联的聊天记录，用户从对话列表打开会话时看到空对话
3. **数据不完整**：提示词保存成功，但缺少可追溯的聊天记录

## 解决方案

**方案 A：保存"当前编辑器"时自动创建用户消息**

当用户选择"当前编辑器"并保存时，系统自动创建一条用户消息，内容为保存的提示词。

## 修改内容

### 1. 后端修改

#### 文件：`routers/prompt_service.py`

**修改方法：`finalize_session`**

- 新增 `source_type` 参数
- 当 `source_type='prompt'` 且没有 `message_id` 时，自动创建用户消息
- 获取当前会话的最大 `round_index`，新消息使用 `round_index + 1`
- 创建消息后，使用新消息的 ID 作为 `message_id`

```python
async def finalize_session(
    self,
    session_id: int,
    user_id: int,
    prompt_id: int,
    final_content: str,
    message_id: Optional[int] = None,
    source_type: Optional[str] = None  # 新增参数
):
    """收敛会话：将会话标记为已保存状态，并标记其他消息为已删除

    当 source_type='prompt'（当前编辑器）且没有 message_id 时，
    会创建一条新的用户消息来保存编辑器内容。
    """
    # 如果是"当前编辑器"模式且没有message_id，先创建一条用户消息
    if source_type == "prompt" and not message_id:
        # 获取当前会话的最大round_index
        result = await self.session.execute(...)
        next_round = (row["max_round"] if row else 0) + 1

        # 创建用户消息，内容为保存的提示词
        result = await self.session.execute(...)
        message_id = result.lastrowid
        logger.info(f"[PromptSave] Created user message {message_id}...")

    # 更新会话状态...
    # 标记其他消息为已删除...
```

#### 文件：`routers/prompt_save_api.py`

**修改 API 调用：**

- 调用 `finalize_session` 时传递 `source_type` 参数

```python
if request.finalize_session:
    message_id = request.message_id if request.source_type == "reply" else None
    await service.finalize_session(
        request.session_id, user_id, prompt_id, content, message_id, request.source_type
    )
```

### 2. 前端修改

前端无需修改，`SavePromptModal.vue` 已经正确传递 `source_type` 字段。

```typescript
const saveData: any = {
  session_id: props.sessionId,
  title: form.value.title.trim(),
  source_type: form.value.sourceType,  // 已正确传递
  // ...
}
```

## 场景处理

### 场景 1：对话区域完全无记录（空会话）

**用户行为：**
- 直接进入专业模式
- 编写提示词内容
- 点击保存，选择"当前编辑器"

**处理逻辑：**
1. `max_round = 0`（会话中没有消息）
2. 创建新消息，`round_index = 1`
3. 消息内容为保存的提示词
4. 会话收敛，保留这条新消息

**结果：**
- 会话中有一条用户消息
- 用户从对话列表打开，能看到这条消息

### 场景 2：对话区域有记录，但选择"当前编辑器"

**用户行为：**
- 在对话区域与 AI 交流
- 选择某条 AI 回复进入专家模式
- 在编辑器中修改内容
- 点击保存，选择"当前编辑器"（而非原来的 AI 回复）

**处理逻辑：**
1. `max_round = N`（会话中有 N 条消息）
2. 创建新消息，`round_index = N + 1`
3. 消息内容为编辑器中的修改后内容
4. 会话收敛，保留这条新消息，其他消息标记为删除

**结果：**
- 会话中只有一条用户消息（保存的最终版本）
- 之前的对话记录被软删除

### 场景 3：选择 AI 回复保存（原有逻辑）

**用户行为：**
- 在对话区域与 AI 交流
- 选择某条 AI 回复
- 点击保存，选择该 AI 回复

**处理逻辑：**
1. `source_type = 'reply'`，`message_id` 为选中的 AI 消息 ID
2. 不会创建新消息
3. 会话收敛，保留选中的 AI 消息，其他消息标记为删除

**结果：**
- 会话中只有选中的 AI 回复
- 之前的对话记录被软删除

## 数据表结构

### ai_chat_messages 表

```sql
CREATE TABLE `ai_chat_messages` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `session_id` bigint NOT NULL COMMENT '关联会话ID',
  `role` varchar(20) NOT NULL COMMENT '角色: user/assistant/system',
  `content` text NOT NULL COMMENT '消息内容',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP,
  `round_index` int DEFAULT 1,
  `is_deleted` tinyint DEFAULT 0 COMMENT '软删除标记: 0-未删除, 1-已删除',
  `deleted_at` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  INDEX `idx_msg_session`(`session_id`),
  INDEX `idx_round`(`session_id`, `round_index`)
) ENGINE=InnoDB COMMENT='AI对话消息详情表';
```

## API 请求示例

### 保存"当前编辑器"内容

```json
{
  "session_id": 123,
  "title": "周报润色助手",
  "source_type": "prompt",
  "content": "你是一位专业的文案编辑...",
  "visibility": "private",
  "tag_ids": [1, 2],
  "finalize_session": true
}
```

### 保存 AI 回复

```json
{
  "session_id": 123,
  "title": "周报润色助手",
  "source_type": "reply",
  "message_id": 456,
  "visibility": "private",
  "tag_ids": [1, 2],
  "finalize_session": true
}
```

## 注意事项

1. **标题必填**：前端已验证标题不能为空，创建的消息会关联到会话标题
2. **round_index 递增**：新消息的 `round_index` 始终为当前最大值 + 1，确保消息顺序正确
3. **软删除机制**：收敛会话时，其他消息标记为 `is_deleted=1`，不会物理删除
4. **source_type 传递**：前端必须正确传递 `source_type` 字段，否则后端无法判断保存来源

## 测试建议

1. **空会话保存**：新创建会话，直接进入专业模式，编写内容保存
2. **有对话记录保存**：先进行对话，再进入专业模式修改保存
3. **切换保存来源**：对话后选择"当前编辑器"而非 AI 回复保存
4. **不收敛会话**：测试 `finalize_session=false` 时是否正常
5. **多次保存**：同一会话多次保存，验证消息创建逻辑

## 相关文件

- `routers/prompt_service.py` - 后端服务逻辑
- `routers/prompt_save_api.py` - API 接口
- `routers/prompt_models.py` - 数据模型
- `src/components/editor/SavePromptModal.vue` - 前端保存弹窗
- `src/api/promptSave.ts` - 前端 API 封装
