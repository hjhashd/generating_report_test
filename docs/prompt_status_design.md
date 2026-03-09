# Prompt 状态字段设计规范

## 背景

在提示词系统的开发过程中，`status` 和 `is_template` 两个字段的职责曾经被混淆，导致了一系列 bug。本文档旨在明确这两个字段的设计意图和使用规范，避免后续开发中再次犯错。

## 字段定义

### 1. status 字段

**数据库定义**：`status` tinyint NULL DEFAULT 1 COMMENT '状态: 1-启用, 0-禁用'

**实际业务含义**：
- `0` - 已删除（软删除）
- `1` - 私有（用户自己创建，未公开）
- `2` - 公开（已分享到提示词广场）

**使用场景**：
- 控制提示词的生命周期状态
- 区分私有提示词和公开提示词
- 软删除标记

### 2. is_template 字段

**数据库定义**：`is_template` tinyint NULL DEFAULT 0 COMMENT '是否为公共模板: 1-是, 0-否'

**实际业务含义**：
- `0` - 普通提示词（用户创建）
- `1` - 系统预设模板（官方提供的模板）

**使用场景**：
- 标识系统预设的模板
- 用于区分"官方模板"和"用户创建的提示词"
- **不参与分享/公开逻辑**

## 常见错误

### 错误 1：用 is_template 标记公开状态

**错误代码示例**：
```python
# 错误：用 is_template 标记公开
if request.visibility == "plaza":
    department_id = request.department_id
    status = 2
    is_template = 1  # ❌ 错误！不应该设置 is_template
```

**正确做法**：
```python
# 正确：只用 status 和 department_id 控制公开状态
if request.visibility == "plaza":
    department_id = request.department_id
    status = 2  # ✅ 正确：status=2 表示公开
```

### 错误 2：查询时用 is_template 过滤

**错误代码示例**：
```xml
<!-- 错误：用 is_template 过滤私有提示词 -->
<if test="query.filter == 'my'">
    AND t.user_id = #{query.currentUserId}
    AND (t.is_template IS NULL OR t.is_template = 0)  <!-- ❌ 错误！ -->
</if>
```

**正确做法**：
```xml
<!-- 正确：用 status 过滤 -->
<if test="query.filter == 'my'">
    AND t.user_id = #{query.currentUserId}
    AND t.status = 1  <!-- ✅ 正确：status=1 表示私有 -->
</if>
```

### 错误 3：findById 只查询 status=1

**错误代码示例**：
```xml
<!-- 错误：只查询 status=1 的提示词 -->
<select id="findById" resultMap="PromptResultMap">
    SELECT * FROM ai_prompts WHERE id = #{id} AND status = 1  <!-- ❌ 错误！ -->
</select>
```

**正确做法**：
```xml
<!-- 正确：查询所有未删除的提示词 -->
<select id="findById" resultMap="PromptResultMap">
    SELECT * FROM ai_prompts WHERE id = #{id} AND status != 0  <!-- ✅ 正确 -->
</select>
```

## 查询场景对照表

| 场景 | 查询条件 | 说明 |
|------|----------|------|
| 我的私有提示词 | `status = 1` AND `user_id = 当前用户` | 用户自己创建，未公开 |
| 我的公开分享 | `status = 2` AND `user_id = 当前用户` | 用户自己创建，已公开 |
| 提示词广场 | `status = 2` AND `department_id IS NOT NULL` | 所有公开提示词 |
| 全部（我的+部门）| `status != 0` AND (`user_id = 当前用户` OR `department_id = 用户部门`) | 未删除的提示词 |
| 获取详情 | `status != 0` | 查询所有未删除的 |

## 修改记录

### 2024-02-13 修复

#### Java 后端修改

**文件**: `ljt/prompt-system-backend/src/main/resources/mapper/PromptMapper.xml`

1. **findById 查询**
   - 修改前：`status = 1`
   - 修改后：`status != 0`
   - 原因：需要能查询到公开的提示词（status=2）

2. **updateDepartmentId 方法**
   - 修改前：设置 `is_template = 1`
   - 修改后：设置 `status = 2`
   - 原因：is_template 不应用于标记公开状态

3. **clearDepartmentId 方法**
   - 修改前：设置 `is_template = 0`
   - 修改后：设置 `status = 1`
   - 原因：is_template 不应用于标记公开状态

4. **filter='my' 查询**
   - 修改前：`is_template = 0`
   - 修改后：`status = 1`
   - 原因：用 status 区分私有/公开

5. **filter='shared' 查询**
   - 修改前：无 status 检查
   - 修改后：`status = 2`
   - 原因：明确只查询已公开的提示词

#### Python 后端修改

**文件**: `generate_report_test/routers/prompt_service.py`

1. **create_or_update_prompt 方法**
   - 修改前：公开时设置 `is_template = 1`
   - 修改后：删除 `is_template = 1` 的设置
   - 原因：is_template 不应用于标记公开状态

#### 前端修改

**文件**: `ljt/note-prompt/src/views/ProfileCenter.vue`

1. **公开标签显示**
   - 修改前：`v-if="item.is_template"`
   - 修改后：`v-if="item.status === 2"`
   - 原因：用 status 判断是否为公开提示词

## 最佳实践

### 1. 新增提示词时

```python
# 私有提示词
department_id = None
status = 1
is_template = 0

# 公开提示词
department_id = request.department_id
status = 2
is_template = 0  # 保持为 0，除非真的是系统模板
```

### 2. 分享/取消分享时

```python
# 分享（变为公开）
UPDATE ai_prompts 
SET department_id = #{departmentId}, 
    status = 2,  # ✅ 设置 status=2
    update_time = NOW()
WHERE id = #{id}

# 取消分享（变为私有）
UPDATE ai_prompts 
SET department_id = NULL, 
    status = 1,  # ✅ 设置 status=1
    update_time = NOW()
WHERE id = #{id}
```

### 3. 查询时

```xml
<!-- 查询私有提示词 -->
AND t.user_id = #{userId}
AND t.status = 1

<!-- 查询公开提示词 -->
AND t.status = 2
AND t.department_id IS NOT NULL

<!-- 查询所有未删除的 -->
AND t.status != 0
```

## 注意事项

1. **is_template 字段目前始终为 0**：因为我们没有系统预设模板的功能
2. **如果将来需要系统模板功能**：is_template=1 的提示词应该由管理员创建，且通常 status=2（公开）
3. **department_id 和 status 的关系**：
   - `status=1`（私有）时，`department_id` 必须为 NULL
   - `status=2`（公开）时，`department_id` 必须有值

## 相关文件

- Java Mapper: `ljt/prompt-system-backend/src/main/resources/mapper/PromptMapper.xml`
- Python Service: `generate_report_test/routers/prompt_service.py`
- Python API: `generate_report_test/routers/prompt_user_api.py`
- 前端 Profile: `ljt/note-prompt/src/views/ProfileCenter.vue`
- 前端 API Types: `ljt/note-prompt/src/api/promptSave.ts`
