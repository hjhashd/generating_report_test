# Prompt Studio 临时会话保存修复文档

## 问题背景

当用户从"我的提示词"或"公共提示词"进入 Prompt Studio 时，如果该提示词没有关联的会话记录，系统会创建一个**临时会话**来显示提示词内容。但保存后，会话仍然显示在"临时对话"区域，而不是"已保存的提示词"区域。

---

## 数据关系说明

### 核心表结构

| 表名 | 字段 | 说明 |
|------|------|------|
| `ai_prompts` | `id` | 提示词卡片ID |
| `ai_prompts` | `user_id` | 提示词创建者ID |
| `ai_chat_sessions` | `id` | 会话ID |
| `ai_chat_sessions` | `origin_prompt_id` | 关联的提示词ID（保存时设置） |
| `ai_chat_sessions` | `ref_prompt_id` | 引用的提示词ID（从哪个提示词开始对话） |

### 关系图

```
ai_prompts (提示词卡片)
    ↑
    | origin_prompt_id
    |
ai_chat_sessions (会话记录)
```

---

## 场景分析

### 场景1：正常保存（有会话记录）

**流程：**
1. 用户从"我的提示词"点击卡片
2. 系统调用 `getSessionByPromptId` 查找关联会话
3. 找到会话 → 直接加载该会话
4. 用户修改后保存
5. `sessionId` 有值 → `finalize_session: true`
6. 后端更新 `origin_prompt_id`
7. 会话显示在"已保存的提示词"区域 ✅

### 场景2：临时会话保存（无会话记录）- 问题场景

**原有流程（有问题）：**
1. 用户从"我的提示词"点击卡片
2. 系统调用 `getSessionByPromptId` 查找关联会话
3. 未找到会话 → 创建临时会话（`tempSession`）
4. `currentSessionId` 为 `null`
5. 用户保存时 `props.sessionId` 为 `null`
6. `finalize_session: false` → 后端不创建会话
7. 会话仍然显示在"临时对话"区域 ❌

**修复后流程：**
1. 用户从"我的提示词"点击卡片
2. 系统调用 `getSessionByPromptId` 查找关联会话
3. 未找到会话 → 创建临时会话（`tempSession`）
4. `currentSessionId` 为 `null`，但 `promptId` 有值
5. 用户保存时检测到 `!sessionId && promptId`
6. **先调用 `createChatSession` 创建新会话**
7. 使用新会话ID保存，`finalize_session: true`
8. 后端设置 `origin_prompt_id`
9. 会话显示在"已保存的提示词"区域 ✅

### 场景3：删除记录保留卡片

**流程：**
1. 用户删除会话记录但保留提示词卡片
2. 下次点击该提示词卡片
3. `getSessionByPromptId` 返回未找到
4. 创建临时会话显示提示词内容
5. 保存时创建新会话并绑定

### 场景4：删除卡片保留记录

**流程：**
1. 用户删除提示词卡片但保留会话记录
2. 会话的 `origin_prompt_id` 指向不存在的提示词
3. 该会话显示在"对话记录"区域（普通会话）
4. 用户可以重新保存为新的提示词

---

## 代码修改

### 文件：`src/components/editor/SavePromptModal.vue`

#### 1. 添加导入

```typescript
import { createChatSession } from '@/api/lyf-ai'
```

#### 2. 修改 handleSave 函数

```typescript
const handleSave = async () => {
  // ... 前置验证代码 ...

  isSaving.value = true
  try {
    // 如果没有会话ID但有提示词ID（临时会话场景），需要先创建会话
    let sessionId = props.sessionId
    if (!sessionId && props.promptId) {
      const newSession = await createChatSession(form.value.title.trim())
      sessionId = newSession.session_id
      console.log(`[SavePromptModal] Created new session ${sessionId} for temp prompt ${props.promptId}`)
    }

    // 构建保存请求
    const saveData: any = {
      title: form.value.title.trim(),
      source_type: 'prompt',
      visibility: form.value.visibility,
      tag_ids: form.value.tagIds || [],
      description: form.value.description || '',
      user_input_example: form.value.userInputExample || '',
      finalize_session: !!sessionId,  // 有会话ID时收敛会话
      content: props.promptContent
    }

    if (sessionId) {
      saveData.session_id = sessionId
    }
    
    // ... 后续保存逻辑 ...
    
    // 触发保存成功事件，传递新创建的sessionId
    emit('saved', {
      ...result,
      session_id: sessionId,
      formData: form.value
    })
  }
}
```

---

## 关键逻辑说明

### 1. 临时会话判断条件

```typescript
if (!sessionId && props.promptId)
```

- `!sessionId`：当前没有活跃的会话
- `props.promptId`：有关联的提示词ID（说明是从提示词卡片进入的临时会话）

### 2. finalize_session 的作用

| 值 | 后端行为 |
|---|---------|
| `true` | 调用 `finalize_session` 方法，设置 `origin_prompt_id`，会话显示在"已保存的提示词" |
| `false` | 不调用 `finalize_session`，会话保持普通状态 |

### 3. 左侧边栏过滤逻辑

```typescript
// StudioSidebar.vue
const savedPromptSessions = computed(() => 
  sessions.value.filter(s => s.origin_prompt_id)  // 有 origin_prompt_id 的会话
)
const normalSessions = computed(() => 
  sessions.value.filter(s => !s.origin_prompt_id)  // 没有 origin_prompt_id 的会话
)
```

---

## 测试用例

### 测试1：从"我的提示词"进入，无会话记录

**步骤：**
1. 创建一个新提示词
2. 删除关联的会话记录（保留提示词卡片）
3. 从"我的提示词"点击该提示词卡片
4. 修改内容后保存

**预期结果：**
- 保存成功
- 左侧边栏显示在"已保存的提示词"区域
- 不再显示"临时对话"

### 测试2：从"我的提示词"进入，有会话记录

**步骤：**
1. 从"我的提示词"点击一个已有会话记录的提示词
2. 修改内容后保存

**预期结果：**
- 保存成功
- 左侧边栏仍然显示在"已保存的提示词"区域

### 测试3：新建对话保存

**步骤：**
1. 点击"新建对话"
2. 编写提示词内容
3. 保存

**预期结果：**
- 保存成功
- 提示词保存到提示词库
- 无会话关联（因为是从空白开始）

---

## 相关文件

| 文件路径 | 说明 |
|----------|------|
| `src/components/editor/SavePromptModal.vue` | 保存弹窗组件 |
| `src/views/PromptStudio.vue` | 主页面，处理保存成功回调 |
| `src/components/editor/StudioSidebar.vue` | 左侧边栏，会话列表过滤 |
| `src/stores/chat.ts` | 会话状态管理 |
| `src/api/lyf-ai.ts` | 会话相关API |
| `generate_report_test/routers/prompt_save_api.py` | 后端保存API |
| `generate_report_test/routers/prompt_service.py` | 后端保存服务 |

---

## 修改记录

| 日期 | 修改内容 |
|------|----------|
| 2026-03-10 | 修复临时会话保存后不显示在"已保存的提示词"区域的问题 |
