# 提示词与会话关联功能实现说明

## 一、需求描述

用户希望实现以下功能：

### 1. 点击提示词卡片时激活对应的聊天记录

当用户在"我的提示词"或"提示词广场"点击自己的提示词卡片时：
- 如果该提示词已经保存过（有关联的会话记录），应该直接跳转到对应的会话
- 在编辑器中显示该会话的完整聊天记录（欢迎语 + 提示词内容）
- **不显示"引用"横幅与其它相关的样式和文字**（引用横幅只应该出现在引用他人提示词时）

### 2. 左侧对话列表区分已保存的提示词

左侧对话列表需要：
- 有一个专门的区域显示"已保存为提示词"的记录
- 与普通的未保存对话记录区分开来
- 视觉上明显不同（绿色主题）

---

## 二、数据结构说明

### 数据库表关系

```
ai_prompts (提示词表)
    ↑
    | origin_prompt_id
    |
ai_chat_sessions (会话表)
```

- 当用户保存提示词时，会话表的 `origin_prompt_id` 字段会被设置为提示词的 ID
- 通过 `origin_prompt_id` 可以找到提示词关联的会话

### 关键字段

| 表名 | 字段 | 说明 |
|------|------|------|
| ai_chat_sessions | origin_prompt_id | 关联的提示词ID，NULL表示普通会话 |
| ai_prompts | user_id | 提示词创建者ID |

---

## 三、实现方案

### 1. 后端修改

#### 1.1 会话列表返回 origin_prompt_id

**文件**: `/root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py`

**修改内容**: 在 `list_sessions` 方法中添加 `origin_prompt_id` 字段的查询

```python
# 第108-123行
async def list_sessions(self, user_id: int, limit: int = 50, status: Optional[str] = "active") -> List[Dict[str, Any]]:
    # ... 省略其他代码 ...
    has_origin_prompt_id = await self._column_exists("ai_chat_sessions", "origin_prompt_id")
    
    select_cols = ["id AS session_id", "title"]
    # ... 其他字段 ...
    if has_origin_prompt_id:
        select_cols.append("origin_prompt_id")
```

#### 1.2 新增API：根据提示词ID获取关联会话

**文件**: `/root/zzp/langextract-main/generate_report_test/routers/prompt_user_api.py`

**新增接口**: `GET /{prompt_id}/session`

```python
@router.get("/{prompt_id}/session")
async def get_prompt_session(
    prompt_id: int,
    current_user: CurrentUser = Depends(require_user),
):
    """
    获取提示词关联的会话
    用于：点击提示词卡片时，找到对应的会话并跳转
    """
    # 查询 ai_chat_sessions 表中 origin_prompt_id = prompt_id 的记录
    # 返回 session_id 等信息
```

---

### 2. 前端修改

#### 2.1 类型定义更新

**文件**: `/root/zzp/langextract-main/ljt/note-prompt/src/api/lyf-ai.ts`

```typescript
export interface ChatSessionItem {
  session_id: number
  title: string
  create_time?: string
  update_time?: string
  status?: string
  origin_prompt_id?: number  // 新增字段
}
```

#### 2.2 新增API调用函数

**文件**: `/root/zzp/langextract-main/ljt/note-prompt/src/api/promptSave.ts`

```typescript
export function getPromptSession(prompt_id: number): Promise<{
  code: number
  message: string
  data?: {
    session_id: number
    title: string
    status: number
    create_time?: string
    update_time?: string
  }
}>
```

#### 2.3 提示词卡片点击逻辑

**文件**: `/root/zzp/langextract-main/ljt/note-prompt/src/components/layout/PromptList.vue`

**修改函数**: `handleCardClick`

```typescript
const handleCardClick = async (prompt: PromptItem) => {
  // 批量操作模式下点击卡片切换选择状态
  if (isDeleteMode.value || isShareMode.value) {
    togglePromptSelection(prompt.id)
    return
  }

  // 如果是当前用户的提示词，尝试获取关联的会话
  if (isOwnPrompt(prompt)) {
    try {
      const res = await getPromptSession(prompt.id)
      if (res.code === 0 && res.data?.session_id) {
        // 有关联的会话，跳转到该会话
        router.push({
          path: '/studio',
          query: {
            session_id: res.data.session_id
          }
        })
        return
      }
    } catch (error) {
      console.error('Failed to get prompt session:', error)
    }
  }

  // 没有关联的会话或者是他人的提示词，按原有逻辑跳转
  router.push({
    path: '/studio',
    query: {
      promptId: prompt.id
    }
  })
}
```

#### 2.4 左侧会话列表分区域显示

**文件**: `/root/zzp/langextract-main/ljt/note-prompt/src/components/editor/StudioSidebar.vue`

**新增计算属性**:
```typescript
// 分离已保存提示词的会话和普通会话
const savedPromptSessions = computed(() => 
  sessions.value.filter(s => s.origin_prompt_id)
)
const normalSessions = computed(() => 
  sessions.value.filter(s => !s.origin_prompt_id)
)
```

**模板结构**:
```html
<!-- 已保存的提示词区域 -->
<div v-if="savedPromptSessions.length > 0" class="saved-prompts-section">
  <div class="section-subtitle">
    <BookmarkCheck :size="14" class="subtitle-icon" />
    <span>已保存的提示词</span>
  </div>
  <!-- 会话列表 -->
</div>

<!-- 普通对话记录区域 -->
<div class="normal-sessions-section">
  <div class="section-subtitle">
    <MessageSquare :size="14" class="subtitle-icon" />
    <span>对话记录</span>
  </div>
  <!-- 会话列表 -->
</div>
```

#### 2.5 引用横幅显示逻辑

**文件**: `/root/zzp/langextract-main/ljt/note-prompt/src/views/PromptStudio.vue`

```typescript
// 是否为引用他人提示词（自己的提示词不显示引用横幅）
// 通过 session_id 进入时（已保存的提示词会话），不显示引用横幅
const showRefBanner = computed(() => {
  // 如果是通过 session_id 进入，不显示引用横幅
  if (route.query.session_id) return false
  // 只有通过 promptId 进入时才判断
  if (!route.query.promptId) return false
  if (!referencedPrompt.value) return true
  const currentUserId = userStore.userInfo?.id
  return String(currentUserId) !== String(referencedPrompt.value.author?.id)
})
```

---

## 四、CSS样式

**文件**: `/root/zzp/langextract-main/ljt/note-prompt/src/assets/base.css`

新增 emerald 颜色变量：
```css
/* Emerald Colors - For saved prompts */
--emerald-50: #ecfdf5;
--emerald-100: #d1fae5;
--emerald-200: #a7f3d0;
--emerald-300: #6ee7b7;
--emerald-400: #34d399;
--emerald-500: #10b981;
--emerald-600: #059669;
--emerald-700: #047857;
--emerald-800: #065f46;
--emerald-900: #064e3b;
```

---

## 五、可能的问题排查

### 5.1 点击提示词卡片后没有跳转到会话

**检查点**:
1. 后端 API `GET /{prompt_id}/session` 是否正常返回数据
2. 检查数据库中 `ai_chat_sessions.origin_prompt_id` 是否正确设置
3. 检查前端 `getPromptSession` 函数是否正确调用

**调试方法**:
```javascript
// 在 PromptList.vue 的 handleCardClick 中添加日志
console.log('isOwnPrompt:', isOwnPrompt(prompt))
const res = await getPromptSession(prompt.id)
console.log('getPromptSession response:', res)
```

### 5.2 左侧列表没有显示"已保存的提示词"区域

**检查点**:
1. 后端 `list_sessions` 是否返回了 `origin_prompt_id` 字段
2. 前端 `ChatSessionItem` 类型是否包含 `origin_prompt_id`
3. `savedPromptSessions` 计算属性是否正确过滤

**调试方法**:
```javascript
// 在 StudioSidebar.vue 中添加日志
console.log('sessions:', sessions.value)
console.log('savedPromptSessions:', savedPromptSessions.value)
```

### 5.3 引用横幅仍然显示

**检查点**:
1. 检查 URL 参数是 `session_id` 还是 `promptId`
2. 检查 `showRefBanner` 计算属性的返回值

**调试方法**:
```javascript
// 在 PromptStudio.vue 中添加日志
console.log('route.query:', route.query)
console.log('showRefBanner:', showRefBanner.value)
```

---

## 六、文件清单

| 文件路径 | 修改类型 | 说明 |
|----------|----------|------|
| `generate_report_test/utils/lyf/prompt_chat_async.py` | 修改 | list_sessions 添加 origin_prompt_id |
| `generate_report_test/routers/prompt_user_api.py` | 新增 | get_prompt_session API |
| `ljt/note-prompt/src/api/lyf-ai.ts` | 修改 | ChatSessionItem 类型添加字段 |
| `ljt/note-prompt/src/api/promptSave.ts` | 新增 | getPromptSession 函数 |
| `ljt/note-prompt/src/components/layout/PromptList.vue` | 修改 | handleCardClick 逻辑 |
| `ljt/note-prompt/src/components/editor/StudioSidebar.vue` | 修改 | 分区域显示会话列表 |
| `ljt/note-prompt/src/views/PromptStudio.vue` | 修改 | showRefBanner 逻辑 |
| `ljt/note-prompt/src/assets/base.css` | 修改 | 添加 emerald 颜色变量 |

---

## 七、预期效果

1. **点击自己的提示词卡片**：
   - 调用 `getPromptSession` API 获取关联的会话
   - 如果有会话，跳转到 `/studio?session_id=xxx`
   - 如果没有会话，跳转到 `/studio?promptId=xxx`

2. **通过 session_id 进入编辑器**：
   - 不显示引用横幅
   - 显示该会话的完整聊天记录

3. **左侧对话列表**：
   - 顶部显示"已保存的提示词"区域（绿色主题）
   - 下方显示"对话记录"区域
   - 两个区域视觉上明显区分
