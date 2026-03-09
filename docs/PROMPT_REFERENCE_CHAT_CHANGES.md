# 🔗 提示词引用与对话优化方案 (Prompt Reference Chat)

> **文档状态**: ✅ 已验证 / 🚀 已发布
> **最后更新**: 2026-02-17

## 📖 背景与目标

当用户在 **广场/公共目录** 中点击"引用"他人的提示词卡片进入工作室时，我们需要确保以下体验：

1.  **🛡️ 零侵入 (Read-Only)**: 不修改被引用的原始提示词卡片。
2.  **🧬 引用溯源**: 新建对话会话，并记录引用源 ID (`ref_prompt_id`)。
3.  **🧠 上下文感知**: 对话时，AI 模型必须"看见"被引用卡片的完整详情（标题/描述/内容），以便基于此进行优化。
4.  **💾 状态持久化**: 刷新页面、加载历史或自动生成标题时，引用状态不应丢失。
5.  **🔄 引用保存**: 引用别人的提示词保存时，创建新提示词而非更新原提示词，并记录溯源关系。

---

## 🏗️ 设计思路

### 1. 会话层记录引用关系 (`ref_prompt_id`)

我们在 `ai_chat_sessions` 表中使用 `ref_prompt_id` 字段来追踪引用来源：

*   **进入时**: 引用卡片进入工作室后，首条消息触发创建会话时写入 `ref_prompt_id`。
*   **保存时**: 保存操作仍然走原流程，保存后通过 `origin_prompt_id` 绑定到用户**新创建**的提示词，不影响原引用卡片。

**收益**:
*   ✅ 被引用卡片数据绝对安全（只读）。
*   ✅ 新会话可追溯引用来源（用于统计热度、审计、推荐算法等）。

### 2. 模型上下文注入 (System Context Injection)

模型"没有记忆"的根本原因是之前的调用仅传递了对话历史。解决方案是在后端构造 LLM `messages` 时动态注入：

*   **检测**: 若会话存在 `ref_prompt_id`。
*   **注入**: 读取 `ai_prompts` 中该提示词的 `title`, `description`, `content`。
*   **指令**: 将其作为 System Prompt 的一部分，明确告知模型"这是参考内容，请基于此优化，不要直接执行它"。

### 3. 结构化输出模式 (Prompt Engineer Mode)

引用会话的核心场景是 **"基于某条提示词进行优化/改写/增强"**。
因此，在引用模式下，System 指令切换为 **Prompt Engineer 专家模式**，强制模型按固定结构输出：

```markdown
### 🛠️ 优化思路
(分析原提示词的优缺点...)

### ✨ 优化后的 Prompt
```markdown
(这里是优化后的完整代码)
```

### 💡 进一步建议
(关于如何更好使用该提示词的建议...)
```

### 4. 状态恢复与 UI 复原

前端引用卡片属于临时 UI 消息 (`type: 'prompt-ref'`)，历史加载通常会覆盖它。

**解决方案**:
*   **API**: 会话列表接口返回 `ref_prompt_id`。
*   **前端**: 加载历史后，若发现 `ref_prompt_id` 存在，自动请求该提示词详情，并将"引用卡片"**动态插入**到消息列表顶部。
*   **URL 清理**: 创建会话后，自动从 URL 移除 `promptId` 参数，防止刷新页面时重复触发"草稿模式"逻辑。

### 5. 引用保存与溯源 (2026-02-17 新增)

当用户引用别人的提示词并点击保存时：

*   **权限判断**: 后端检查 `prompt_id` 是否属于当前用户。
*   **创建新提示词**: 若不属于当前用户，则创建新提示词，并在 `origin_prompt_id` 字段记录原始提示词 ID。
*   **标题验证**: 前端验证新标题不能与原提示词标题相同，避免混淆。
*   **成功提示**: 根据 `is_forked` 字段显示"已引用并创建新提示词"而非"更新成功"。

---

## 💻 具体实现改动

### 🟢 后端 (Backend)

| 模块 | 文件路径 | 改动说明 |
| :--- | :--- | :--- |
| **API** | `generate_report_test/routers/prompt_chat_api_v2.py` | 流式对话接口支持接收并写入 `ref_prompt_id`。 |
| **会话管理** | `generate_report_test/utils/lyf/prompt_chat_async.py` | `list_sessions` 返回字段增加 `ref_prompt_id`。 |
| **LLM 上下文** | `generate_report_test/utils/lyf/prompt_chat_async.py` | `_get_ref_prompt_context()`: 读取引用详情。<br>`chat_stream()`: 注入上下文并切换 System Prompt。 |
| **保存服务** | `generate_report_test/routers/prompt_service.py` | `create_or_update_prompt()`: 引用别人的提示词时创建新提示词，记录 `origin_prompt_id`，返回 `is_forked` 标识。 |
| **保存 API** | `generate_report_test/routers/prompt_save_api.py` | 响应增加 `is_forked` 字段，`is_update` 逻辑修正。 |
| **日志配置** | `generate_report_test/utils/log_config.py` | 降低 `utils.lyf.prompt_chat_async` 日志级别为 WARNING，减少 SQL 和 `list_sessions` 噪音。 |

### 🔵 前端 (Frontend)

| 模块 | 文件路径 | 改动说明 |
| :--- | :--- | :--- |
| **对话组件** | `StudioDialogue.vue` | 首条消息携带 `ref_prompt_id`；<br>加载历史后自动复原引用卡片 UI；<br>URL 参数清理逻辑。 |
| **类型定义** | `src/api/lyf-ai.ts` | `ChatSessionItem` 增加 `ref_prompt_id` 字段定义。 |
| **工作室主页** | `PromptStudio.vue` | 新增 `isReferencingOthersPrompt` 计算属性；<br>修复 `promptContent` 同步：`prompt-ref` 类型消息从 `promptData.content` 获取内容；<br>传递 `originalPromptTitle` 给保存弹窗；<br>成功提示根据 `is_forked` 显示不同文案。 |
| **保存弹窗** | `SavePromptModal.vue` | 新增 `originalPromptTitle` prop；<br>验证标题不能与原提示词相同；<br>成功提示区分"保存"/"更新"/"引用创建"。 |
| **配置面板** | `StudioConfig.vue` | 成功提示逻辑同步更新。 |

---

## ✨ 实现效果

### 引用模式 (Reference Mode)
1.  **首条消息**: 创建的新会话自动关联 `ref_prompt_id`。
2.  **模型表现**: 始终知晓被引用内容，输出专业的优化建议。
3.  **持久化**: 刷新页面或切换会话后，顶部蓝色的"引用卡片"会自动恢复显示，不会消失。
4.  **保存行为**: 引用别人的提示词保存时，创建新提示词并记录溯源关系，标题不能与原标题相同。
5.  **成功提示**: 显示"已引用并创建新提示词"，明确告知用户操作结果。

### 普通模式 (Normal Mode)
*   保持原有行为不变（通用助手对话）。

---

## ✅ 验证方式

已执行以下验证：
*   **前端构建**: `vue-tsc --noEmit` (类型检查通过), `npm run build` (构建成功)。
*   **后端编译**: `python -m compileall -q generate_report_test` (语法检查通过)。
*   **功能测试**: 引用别人的提示词 → 修改标题 → 保存 → 验证新提示词创建成功，`origin_prompt_id` 正确记录。
