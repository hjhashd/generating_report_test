# 公共资料库 (User ID 0) 集成方案

本文档详细说明如何将 `/root/zzp/langextract-main/generate_report_test/inferrence/0` 目录下的内容作为所有用户可见的公共资料库，并集成到现有的文件管理系统中。

## 1. 现状分析

*   **文件存储**：
    *   私有文件存储在 `/inferrence/{user_id}/{folder_name}/{file_name}`。
    *   公共文件将存储在 `/inferrence/0/{folder_name}/{file_name}`。
*   **后端查询**：
    *   目前 `queryAll.py` 仅查询 `user_id = current_user_id` 的文件夹。
    *   返回的数据字段不包含 `user_id`，导致前端无法区分文件来源。
*   **前端展示**：
    *   `fileSelectPanel.vue` 假设所有文件都属于当前登录用户。
    *   文件路径硬编码为 `/python-api/files/${currentUserId}/...`。

---

## 2. 后端改造方案

### 2.1 修改 SQL 查询逻辑 (`queryAll.py`)

我们需要修改 `get_all_files_with_folders` 函数，使其：
1.  **扩大查询范围**：同时查询当前用户 (`user_id`) 和公共用户 (`0`) 的文件夹。
2.  **返回所有者信息**：在结果中增加 `userId` 字段，供前端区分路径。

**目标文件**：`generate_report_test/utils/lyf/queryAll.py`

**修改建议**：

```python
# 原逻辑
sql = """
    SELECT
        s.id           AS folderId,
        s.folder_name  AS folderName,
        f.id           AS fileId,
        f.file_name    AS fileName,
        f.hotClick,
        f.create_time
    FROM file_structure s ...
"""

# 新逻辑 (修改点：增加 s.user_id 字段，修改 WHERE 条件)
sql = """
    SELECT
        s.id           AS folderId,
        s.folder_name  AS folderName,
        s.user_id      AS userId,       -- [新增] 返回文件夹所属用户ID
        f.id           AS fileId,
        f.file_name    AS fileName,
        f.hotClick,
        f.create_time
    FROM file_structure s
    LEFT JOIN file_item f ON s.id = f.folder_id
"""

# 修改 WHERE 子句
if user_id is not None:
    # 同时查询当前用户和公共用户(0)
    sql += " WHERE (s.user_id = :user_id OR s.user_id = 0) "
    params['user_id'] = user_id
```

同时，记得在 Python 处理结果列表 (`result.append`) 时，将新增的 `userId` 字段加入字典：

```python
result.append({
    "folderId": r[0],
    "folderName": r[1],
    "userId": r[2],      # [新增]
    "fileId": r[3],      # 索引顺延
    "fileName": r[4],
    "hotClick": r[5],
    "createTime": formatted_time
})
```

---

## 3. 前端改造方案

### 3.1 动态生成文件路径 (`fileSelectPanel.vue`)

前端在处理 `queryAllPython` 返回的数据时，需要根据 `item.userId` 来决定拼接哪种路径。

**目标文件**：`ljt/report_system/src/views/dataGo/home/components/fileSelectPanel.vue`

**修改建议 (在 `fetchTreeData` 方法中)**：

```javascript
// 原逻辑
path: `/python-api/files/${this.currentUserId}/${item.folderName}/${item.fileName}`

// 新逻辑
// 如果 item.userId 是 0，说明是公共文件，路径用 0
// 否则使用当前用户的 ID (或者直接使用 item.userId，这样更稳健)
const fileOwnerId = item.userId === 0 ? 0 : this.currentUserId;
const filePath = `/python-api/files/${fileOwnerId}/${item.folderName}/${item.fileName}`;

const fileObj = {
  // ...
  path: filePath,
  isPublic: item.userId === 0, // [可选] 标记为公共文件，用于 UI 展示
  // ...
}
```

### 3.2 UI 区分展示 (可选)

为了让用户知道哪些是公共文件（通常是只读的），可以在界面上做区分。

*   **文件夹名称**：在 `folderMap` 处理时，如果是公共文件夹，名字后加 `(公共)`。
    ```javascript
    const displayName = item.userId === 0 ? `${item.folderName} (公共)` : item.folderName;
    ```
*   **图标区分**：在渲染文件树时，根据 `isPublic` 属性显示不同颜色的文件夹图标。

---

## 4. 实施步骤总结

1.  **后端**：修改 `queryAll.py`，确保 SQL 查询包含 `OR s.user_id = 0`，并返回 `s.user_id` 字段。
2.  **验证**：重启后端服务，使用 Postman 或浏览器调用 `/query_all/` 接口，确认返回数据中包含 `userId: 0` 的记录。
3.  **前端**：修改 `fileSelectPanel.vue`，利用返回的 `userId` 修正文件路径拼接逻辑。
4.  **测试**：
    *   登录普通用户账号。
    *   确认能看到公共文件夹（如 `inferrence/0/xxx`）。
    *   点击预览，确认请求 URL 为 `/files/0/...` 且能正常加载。
