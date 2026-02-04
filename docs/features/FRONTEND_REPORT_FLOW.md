# 前端 Vue 组件与后端请求流程详解

本文档详细描述了 `NewReportModal.vue`、`UploadFileModal.vue` 和 `viewReportFirstDraft.vue` 三个 Vue 组件向后端发送请求的完整流程，以及后端 `generate_report_test` 目录下的对应处理逻辑。

## 1. 概述

前端项目使用 Axios 封装的 `request` 工具（定义在 `@/api/report.js`）与后端进行通信。后端采用 FastAPI 框架，路由定义在 `generate_report_test/routers/` 目录下。

## 2. NewReportModal.vue (新建报告)

该组件用于创建新的报告项目，主要涉及获取模板结构和提交创建请求。

### 2.1 获取报告模板结构 (`Import_modul`)

*   **前端行为**:
    *   用户选择报告类型或触发相关操作时，调用 `Import_modul` 方法。
    *   **请求 URL**: `/Import_modul/` (POST)
    *   **参数**: `type_name` (报告类型), `report_name` (报告名称) 等。
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/import_modul_api.py`
    *   **函数**: `Import_modul_endpoint`
    *   **逻辑**:
        1.  接收参数并进行日志记录。
        2.  调用 `utils.zzp.import_modul.get_report_json_structure`。
        3.  根据 `type_name` 和 `report_name` 读取对应的 JSON 模板或目录结构。
        4.  返回包含 `modul_list` (目录结构字典) 的响应给前端。

### 2.2 创建报告 (`Create_Report`)

*   **前端行为**:
    *   用户填写完信息并点击“确定”后，调用 `Create_Report` 方法。
    *   **请求 URL**: `/Create_Report/` (POST)
    *   **参数**: 包含完整的报告结构 JSON (`catalogue_json`)。
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/create_catalogue_api.py` (推测对应 `/Create_Catalogue/`)
    *   **注意**: 在当前后端代码中未找到精确匹配 `/Create_Report/` 的路由。根据功能分析，`Create_Catalogue_endpoint` (路由 `/Create_Catalogue/`) 实现了完全一致的功能（接收目录 JSON 并生成报告）。
    *   **逻辑 (基于 Create_Catalogue)**:
        1.  **接收请求**: 解析 `CatalogueRequest`，包含 `task_id` 和 `catalogue_json`。
        2.  **生成文件**: 调用 `generate_merged_report_from_json`，根据 JSON 结构在服务器上创建文件夹和空的 `.docx` 文件。
        3.  **后台任务**: 将耗时的操作（如生成 HTML 预览、清理临时模板）放入 `BackgroundTasks` 异步执行，避免阻塞前端响应。
        4.  **查重校验**: 如果检测到同名报告，返回状态码 `2` 和提示信息。
        5.  **响应**: 返回成功状态，前端收到后关闭弹窗并刷新列表。

---

## 3. UploadFileModal.vue (上传文件)

该组件用于上传 `.docx` 文档并将其导入到系统中，采用“上传+轮询”的异步处理模式。

### 3.1 上传文件 (`importDoc`)

*   **前端行为**:
    *   用户选择文件并确认上传时，调用 `importDoc`。
    *   **请求 URL**: `/Import_Doc/` (POST)
    *   **参数**: `file` (文件对象), `task_id`, `report_name`, `type_name` 等。
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/import_doc_to_db_api.py`
    *   **函数**: `Import_Doc_endpoint`
    *   **逻辑**:
        1.  **校验**: 严格检查文件后缀是否为 `.docx`，并验证是否为有效的 Zip/Word 格式。
        2.  **保存**: 使用分块写入方式将文件保存到 `temp_uploads` 临时目录，防止大文件占用过多内存。
        3.  **初始化任务**: 在内存字典 `task_status_store` 中创建任务记录，状态设为 `pending`。
        4.  **异步处理**: 启动 `background_process_wrapper` 后台任务，然后**立即返回**响应给前端，包含 `task_id`。
        5.  **后台任务逻辑**:
            *   扫描文档结构 (`scan_docx_structure`)。
            *   调用 `process_document` 解析 Word 内容并入库。
            *   更新 `task_status_store` 中的进度和状态。

### 3.2 查询上传状态 (`checkImportStatus`)

*   **前端行为**:
    *   前端收到上传成功的响应后，启动定时器轮询任务状态。
    *   **请求 URL**: `/check_import_status/{task_id}` (GET)
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/import_doc_to_db_api.py`
    *   **函数**: `check_import_status`
    *   **逻辑**:
        1.  根据 `task_id` 从内存字典 `task_status_store` 中查找任务信息。
        2.  **权限校验**: 检查当前用户是否有权查看该任务。
        3.  返回任务的当前状态 (`processing`, `success`, `failed`) 和进度。
    *   **前端反馈**:
        *   若状态为 `processing`，更新进度条。
        *   若状态为 `success`，提示成功并关闭弹窗。
        *   若状态为 `failed` 或 `error`，显示错误信息。

---

## 4. viewReportFirstDraft.vue (查看报告初稿)

该组件用于浏览报告的章节列表，并对具体章节内容进行查看和编辑（富文本编辑器）。

### 4.1 浏览报告列表 (`browseReport`)

*   **前端行为**:
    *   组件加载时，调用 `browseReport` 获取左侧目录树。
    *   **请求 URL**: `/Browse_Report/` (POST)
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/browse_report_api.py`
    *   **函数**: `Browse_Report_endpoint`
    *   **逻辑**:
        1.  查询数据库或遍历文件系统，获取当前报告类型下的所有报告/章节列表。
        2.  返回树形结构数据。

### 4.2 获取章节内容 (`getContent`)

*   **前端行为**:
    *   用户点击左侧目录树的某个章节时，调用 `getContent`。
    *   **请求 URL**: `/Get_Content/` (POST)
    *   **参数**: `file_name` (如 "1.1 项目背景.docx"), `report_name`, `type_name`。
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/editor_api.py`
    *   **函数**: `Get_Content_endpoint`
    *   **逻辑**:
        1.  **定位文件**: 调用 `get_file_path`，根据用户 ID、报告类型和名称，精准定位服务器上的 `.docx` 文件路径。
        2.  **格式转换**:
            *   检查是否存在对应的 `.html` 文件。
            *   如果不存在或需要更新，调用 `convert_docx_to_html` 将 `.docx` 转换为 HTML。
            *   转换过程中会提取文档中的图片，并保存到 `editor_images` 目录。
        3.  **响应**: 返回 HTML 字符串，前端将其加载到富文本编辑器中。

### 4.3 保存章节内容 (`saveContent`)

*   **前端行为**:
    *   用户编辑完成点击保存时，调用 `saveContent`。
    *   **请求 URL**: `/Save_Content/` (POST)
    *   **参数**: `html_content` (编辑后的 HTML), `file_name` 等。
*   **后端处理**:
    *   **文件**: `generate_report_test/routers/editor_api.py`
    *   **函数**: `Save_Content_endpoint`
    *   **逻辑**:
        1.  **定位文件**: 同样使用 `get_file_path` 定位目标路径。
        2.  **保存 HTML**: 将新的 HTML 内容覆盖写入服务器上的 `.html` 文件。
        3.  **反向转换**: 调用 `convert_html_to_docx` 将 HTML 内容转换回 `.docx` 格式，并覆盖原始 Word 文档，确保文件系统中的数据同步更新。
        4.  **响应**: 返回保存成功状态。