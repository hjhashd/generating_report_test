# 用户导入与模板同步重构计划 (user_import_refactor_plan.md)

## 1. 目标
对文件导入、状态轮询和模板结构查询接口进行多用户改造，确保：
1.  **文件导入 (`/Import_Doc/`)**：上传的文件和生成的报告归属于当前登录用户。
2.  **状态轮询 (`/check_import_status/`)**：用户只能查询自己发起的任务进度。
3.  **模板同步 (`/Import_modul/`)**：用户只能获取自己拥有的报告结构作为模板（或公共模板）。

## 2. 现状与问题
| 接口 | 文件位置 | 问题描述 |
| :--- | :--- | :--- |
| `/Import_Doc/` | `routers/import_doc_to_db_api.py` | 1. 接收 `agentUserId` 但未使用。<br>2. 任务状态存储 (`task_status_store`) 未绑定用户。<br>3. 底层 `process_document` 无法将报告归属到特定用户。 |
| `/check_import_status/` | `routers/import_doc_to_db_api.py` | 1. 无需登录即可访问。<br>2. 只要猜到 `task_id` 就能查看进度，存在越权风险。 |
| `/Import_modul/` | `routers/import_modul_api.py` | 1. `get_report_json_structure` 仅按 `type_name` 和 `report_name` 查询。<br>2. 无法区分同名报告属于哪个用户。<br>3. 用户可访问任意他人的报告结构。 |

## 3. 重构方案

### 3.1 基础设施调整
1.  **任务存储升级**: `task_status_store` 的 value 中增加 `owner_user_id` 字段，用于后续权限校验。
2.  **底层函数签名变更**:
    *   `process_document(..., user_id)`
    *   `split_and_import_to_db(..., user_id)`
    *   `get_report_json_structure(..., user_id)`

### 3.2 接口改造细节

#### A. `/Import_Doc/`
*   **认证**: 添加 `current_user: CurrentUser = Depends(require_user)`。
*   **逻辑**:
    1.  从 `current_user.id` 获取 `user_id`。
    2.  初始化 `task_status_store[task_id]` 时记录 `owner_user_id: user_id`。
    3.  调用 `process_document` 时传入 `user_id`。
    4.  `agentUserId` 参数保留用于兼容，但仅记录日志。

#### B. `/check_import_status/{task_id}`
*   **认证**: 添加 `current_user: CurrentUser = Depends(require_user)`。
*   **逻辑**:
    1.  获取 `task_info = task_status_store.get(task_id)`。
    2.  如果任务存在，检查 `task_info['owner_user_id'] == current_user.id`。
    3.  如果不匹配，返回 403 Forbidden 或 404 Not Found。

#### C. `/Import_modul/`
*   **认证**: 添加 `current_user: CurrentUser = Depends(require_user)`。
*   **逻辑**:
    1.  调用 `get_report_json_structure` 时传入 `user_id`。
    2.  底层 SQL 查询 `report_name` 表时，增加 `WHERE owner_user_id = :user_id` 条件。

#### D. 底层数据库操作 (`utils/zzp/import_doc_to_db.py` & `import_modul.py`)
*   **`split_and_import_to_db`**:
    *   插入 `report_name` 表时，写入 `owner_user_id`。
    *   检查报告是否存在时，增加 `owner_user_id` 条件。
*   **`get_report_json_structure`**:
    *   查询 `report_name` 表时，增加 `owner_user_id` 条件。

## 4. 实施步骤

- [ ] **Step 1**: 修改 `utils/zzp/import_doc_to_db.py`，使 `process_document` 和 `split_and_import_to_db` 支持 `user_id` 参数，并在 SQL 中处理 `owner_user_id`。
- [ ] **Step 2**: 修改 `utils/zzp/import_modul.py`，使 `get_report_json_structure` 支持 `user_id` 参数并增加 SQL 过滤。
- [ ] **Step 3**: 修改 `routers/import_doc_to_db_api.py`，引入 `require_user`，在 `/Import_Doc/` 和 `/check_import_status/` 中实现用户校验与隔离。
- [ ] **Step 4**: 修改 `routers/import_modul_api.py`，引入 `require_user`，在 `/Import_modul/` 中传递 `user_id`。
