# 用户专属路径改造与隔离计划

## 1. 目标
将系统所有涉及文件读写的操作（创建、查询、编辑、合并、删除）全部从“基于路径的硬编码”迁移为“基于用户ID的强隔离路径”。确保：
1.  **数据隐私**：用户 A 只能访问/操作自己的文件。
2.  **数据安全**：物理文件路径包含 `user_id`，防止同名文件覆盖。
3.  **唯一性**：严格校验同一用户下的文件名唯一性。

## 2. 路径规范
| 资源类型 | 旧路径 (Deprecated) | 新路径 (User Isolated) | 说明 |
| :--- | :--- | :--- | :--- |
| **原始报告** | `report/{Type}/{Name}/` | `report/{user_id}/{Type}/{Name}/` | 用于存放拆分后的章节 Docx |
| **合并报告** | `report_merge/{Type}/{Name}.docx` | `report_merge/{user_id}/{Type}/{Name}.docx` | 用于存放最终合并文件 |
| **推理图片** | `inferrence/{TaskID}/` | `inferrence/{user_id}/{TaskID}/` | 存放 PDF 提取的图片 |
| **编辑器图** | `editor_image/` | `editor_image/{user_id}/` | 存放富文本编辑器上传的图片 |

## 3. 核心架构设计与思维 (New)

### 3.1 COW (Copy-On-Write) 变体策略
在浏览和编辑报告时，采用了类似 COW 的策略来平衡“用户隔离”与“公共模板复用”：
*   **读取 (Read)**: 优先查找用户专属目录 `report/{user_id}/...`。如果未找到，则回退查找公共目录（作为模板或默认文件）。
*   **写入 (Write)**: 所有的保存、修改操作，**强制**写入用户专属目录。绝不修改公共目录下的文件。
*   **优势**: 既实现了用户对文件的个性化修改，又保留了系统预置模板的能力，且互不干扰。

### 3.2 资源隔离与生命周期管理
针对图片等静态资源，实施严格的隔离与清理策略：
*   **隔离**: 图片上传路径动态注入 `user_id`，前端获取的 URL 包含用户标识，避免不同用户上传同名文件导致的冲突。
*   **生命周期**:
    *   **实时清理**: 引入 `/delete_editor_image/` 接口，配合前端保存动作，实时删除被移除的图片。
    *   **兜底清理**: 提供 `/clean_images/` 接口，扫描数据库引用，清理无主（Orphaned）文件。

### 3.3 统一路径管理 (Single Source of Truth)
废弃散落在各个 API 文件中的路径拼接逻辑，统一收敛至 `server_config.py`：
*   新增 `get_user_report_dir(uid)`
*   新增 `get_user_merge_dir(uid)`
*   新增 `get_user_editor_image_dir(uid)`
*   **优势**: 当未来存储结构发生变化（如迁移至对象存储 S3/OSS）时，只需修改配置中心一处代码。

### 3.4 全链路上下文注入
*   **Request Scope**: 利用 FastAPI 的依赖注入 (`Depends(require_user)`)，在请求进入的第一时间解析 JWT Token。
*   **Service Layer**: 将解析出的 `user_id` 作为必选参数传递给底层服务函数（如 `process_report_merge`, `create_catalogue`），确保业务逻辑层始终知晓“当前是谁在操作”。

## 4. 改造执行清单

### ✅ 第一阶段：基础设施 (已完成)
- [x] **配置中心 (`server_config.py`)**: 增加 `get_user_report_dir(uid)` 等工具函数，统一管理路径生成逻辑。
- [x] **鉴权中间件**: 核心接口已接入 JWT Token 校验。

### ✅ 第二阶段：核心链路打通 (已完成)
此阶段重点保证“创建 -> 查看 -> 编辑”这一主流程的畅通。

#### 1. 创建报告 (`/Create_Catalogue/`)
- [x] **逻辑修改**: 物理文件夹创建路径已加入 `user_id`。
- [x] **查重逻辑**: 数据库已增加 `user_id` 字段查重。
- [ ] **物理查重 (新增)**: 在创建文件夹前，增加 `os.path.exists` 检查，防止“幽灵文件”干扰。

#### 2. 浏览报告 (`/Browse_Report/`)
- [x] **逻辑修改**: 优先查找 `report/{user_id}/...`，找不到则找公共目录。
- [x] **问题排查**: 修复了路径拼接问题，确保能正确读取用户目录下的文件。

#### 3. 编辑报告 (`/Editor/` & `/Save_Content/`)
- [x] **逻辑修改**:
    - `get_content`: 优先从用户目录读取 Docx 并转换为 HTML。
    - `save_content`: 将 HTML 转回 Docx 时，保存到用户目录。
    - `upload_image`: 图片上传至 `editor_image/{user_id}/`，接口返回相对路径（如 `123/img.png`），前端直接拼接 URL。

### ✅ 第三阶段：外围功能适配 (已完成)
- [x] **合并报告 (`/Merge_Report/`)**: 
    - 数据库查询：只筛选当前用户的源文件。
    - 物理路径：合并结果存放在 `report_merge/{user_id}/` 下。
- [x] **删除报告 (`/Delete_Report/`)**: 物理删除时已支持定位到用户目录。
- [x] **图片路径修正**: 修复了编辑器图片上传未存入用户目录的问题，现在严格隔离。

## 5. 唯一性保证策略
为了确保“一个用户目录下的同一个报告类型，文件命名唯一”：
1.  **数据库层**: `report_name` 表加唯一索引 `(user_id, type_id, report_name)`。
2.  **应用层**: 在 `create_catalogue.py` 中，在 `os.makedirs` 之前进行物理路径检查。

## 6. 常见问题与解决方案 (Troubleshooting)

### 6.1 源文件缺失 (`[Warn] 源文件未找到`)

**现象**:
在导入模板或生成报告（`Import_modul` / `Create_Catalogue`）时，日志出现大量 `[Warn] 源文件未找到: ...`，导致系统降级创建空文件，内容丢失。

**原因**:
1.  **物理路径迁移**: 多用户改造后，文件从 `report/...` 迁移到了 `report/{user_id}/...`。
2.  **数据滞后**: 数据库 `report_catalogue.file_name` 字段中存储的是绝对路径，且可能是旧的路径（未包含 `user_id`）或公共路径。
3.  **查找逻辑僵化**: 代码直接使用数据库中的路径查找，未适配新的路径隔离规则。

**解决方案 (Implemented)**:
在 `utils/zzp/create_catalogue.py` 的 `get_source_file_path` 函数中实现了**路径智能纠错**：
1.  **数据库路径优先**: 如果数据库记录的路径存在，直接使用。
2.  **智能推断**: 如果路径不存在，提取文件名，按以下优先级重新查找：
    *   **Tier 1 (用户私有)**: `report/{user_id}/{Type}/{Name}/{file_name}`
    *   **Tier 2 (公共/模板)**: `report/None/{Type}/{Name}/{file_name}` (兜底)
3.  **权限隔离**: SQL 查询时增加 `user_id` 过滤，优先匹配当前用户的私有模板资源。

**关键代码引用**:
*   `utils/zzp/create_catalogue.py`: `get_source_file_path`

## 7. 文件查看稳健性增强计划 (Robust File Viewing)

**背景**:
当前 `Browse_Report` 接口通过检测文件是否存在来推断用户是想看“草稿文件夹”还是“合并后的Docx文件”。这导致了歧义，尤其是在同名的文件夹和文件同时存在时（例如：`report/3/Demo` 文件夹 和 `report_merge/3/Demo.docx` 文件）。

**问题**:
*   后端依靠猜测（heuristic）决定返回哪个路径。
*   前端 `Get_Content` 接口可能使用错误的 `source_type`（例如拿着 Draft 的类型去请求 Merge 的文件，或反之）。

**实施计划**:

### 7.1 消除歧义 (Explicit Context)
前后端交互必须明确当前的操作上下文，不再依赖猜测。

*   **Frontend (`firstDraft.vue`)**: 
    *   在路由跳转时，明确传递 `viewMode` 参数：
        *   点击“草稿箱”列表项 -> `viewMode=draft`
        *   点击“报告列表”列表项 -> `viewMode=merge`

*   **Frontend (`viewReportFirstDraft.vue`)**:
    *   接收 `viewMode` 参数。
    *   调用 `browseReport` 时，将 `viewMode` 作为参数传递（映射为 `source_type`）。
    *   调用 `getContent` 时，依据 `viewMode` 决定 `source_type`（不再仅依赖 `currentChose` 的默认值）。

*   **Backend (`browse_report_api.py`)**:
    *   更新 `BrowseReport` 模型，增加可选字段 `source_type: str` (枚举值: `draft`, `merge`)。
    *   逻辑分支：
        *   `IF source_type == 'merge'`: **只**在 `MERGE_DIR` (用户/公共) 中查找 `.docx` 文件。
        *   `IF source_type == 'draft'`: **只**在 `REPORT_DIR` (用户/公共) 中查找文件夹。
        *   `ELSE` (兼容旧代码): 保持现有的“优先查找 Docx”或“优先查找文件夹”的启发式逻辑。

### 7.2 稳健性收益
1.  **确定性**: 无论同名文件是否存在，系统都将准确返回用户请求的视图。
2.  **解耦**: 后端无需维护复杂的优先级逻辑，只需响应明确的指令。
3.  **可维护性**: 前端逻辑更加清晰，状态管理（Draft vs Merge）更加直观。
