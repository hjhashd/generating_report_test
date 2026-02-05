# Word 图片资源目录重构计划 (全生命周期管理版)

本文档旨在规划后端 Word 文档转 HTML 及编辑器上传过程中，图片资源的存储路径重构方案。
核心目标是将图片资源从“扁平化堆积”转变为“结构化隔离”，并实现随报告生命周期自动清理。

## 1. 核心目标

1.  **结构化存储**：解决 `editor_image` 目录下文件扁平堆积、难以管理的问题。
2.  **生命周期绑定**：
    *   删除“草稿”时 -> 自动删除对应的草稿图片目录。
    *   删除“合并报告”时 -> 自动删除对应的合并报告图片目录。
3.  **目录隔离**：在 `editor_image` 下建立 `report` (草稿) 和 `report_merge` (合并报告) 双目录结构，避免混淆。

## 2. 目录结构设计 (Unified Directory Structure)

我们将 `editor_image` 目录划分为两个核心区域：

```text
editor_image_root/ (图片根目录)
├── report/                         <-- [NEW] 草稿阶段图片区 (对应 firstDraft.vue)
│   └── {user_id}/
│       └── {report_type}/
│           └── {report_name}/      <-- 对应一个具体的草稿报告
│               ├── 20231027_uuid1.png
│               └── 20231027_uuid2.jpg
│
└── report_merge/                   <-- [NEW] 合并报告图片区 (对应 reportLists.vue)
    └── {user_id}/
        └── {report_type}/
            └── {report_name}/      <-- 对应一个已合并的报告
                ├── image1.png
                └── image2.jpg
```

### 2.1 为什么需要区分 `report` 和 `report_merge`？
*   **物理隔离**：草稿是动态编辑的，合并报告是归档的。两者可能同名（如“2023年度总结”），如果不隔离，删除草稿可能误删合并报告的图片。
*   **逻辑复用**：`report_merge` 目录的逻辑可以完全复用现有的合并报告处理逻辑（只需改变根路径）。

## 3. 业务流程与改动点

### 3.1 场景一：编辑器上传图片 (草稿阶段)

**现状**：
图片直接存入 `editor_image/{user_id}/`，文件名扁平堆积。

**重构计划**：
1.  **前端 (`HtmlEditor.vue`)**：
    *   上传接口 `upload_editor_image` 增加参数：`source_type="report"`, `report_type`, `report_name`。
2.  **后端 (`editor_api.py`)**：
    *   接收新参数，将存储路径改为：`editor_image/report/{user_id}/{report_type}/{report_name}/`。
    *   返回 URL 需包含完整相对路径，例如 `report/1001/资产报告/xx项目/image.png`。

### 3.2 场景二：删除草稿 (Draft Deletion)

**现状**：
只删除 `report/{user_id}/{type}/{name}` 下的 DOCX/HTML 文件，**不删除** `editor_image` 下的图片。

**重构计划**：
1.  **后端 (`delete_report_api.py` / `delete_report.py`)**：
    *   在删除文档目录的同时，显式计算对应的图片目录：`editor_image/report/{user_id}/{report_type}/{report_name}/`。
    *   执行 `shutil.rmtree` 彻底清除该目录下的所有图片。
    *   **一键清理**：用户在前端草稿箱点击删除时，相关图片瞬间消失，不再残留。

### 3.3 场景三：生成合并报告 (Merge Generation)

**现状**：
DOCX/HTML 生成在 `report_merge` 目录，图片目前混在其中或扁平存放。

**重构计划**：
1.  **后端 (`report_merge_api.py`)**：
    *   DOCX/HTML 保持在 `report_merge` 目录不动。
    *   图片提取/生成路径改为：`editor_image/report_merge/{user_id}/{report_type}/{report_name}/`。
    *   HTML 中的图片引用路径同步更新。

### 3.4 场景四：删除合并报告 (Merged Report Deletion)

**现状**：
只删除 DOCX/HTML 文件。

**重构计划**：
1.  **后端 (`delete_merged_report.py`)**：
    *   在删除 DOCX/HTML 后，同步删除 `editor_image/report_merge/{user_id}/{report_type}/{report_name}/` 目录。
    *   此逻辑与“场景二”类似，确保归档报告删除后不留垃圾。

## 4. 实施指南 (Developer Guide)

### Step 1: 后端接口改造 (`routers/editor_api.py`)

修改 `/upload_editor_image/` 接口，支持根据 `source_type` 自动路由到 `report` 或 `report_merge` 子目录。

```python
# 伪代码示意
base_dir = "report" if source_type == "report" else "report_merge"
save_path = os.path.join(EDITOR_IMAGE_ROOT, base_dir, str(user_id), report_type, report_name)
```

### Step 2: 草稿删除逻辑 (`utils/zzp/delete_report.py`)

在 `delete_report_task` 函数中增加图片目录清理逻辑。

```python
# [新增] 删除关联图片
img_dir = os.path.join(
    server_config.EDITOR_IMAGE_ROOT,
    "report",       # 关键：指定 report 子目录
    str(user_id),
    type_name,
    report_name
)
if os.path.exists(img_dir):
    shutil.rmtree(img_dir)
```

### Step 3: 合并报告删除逻辑 (`utils/zzp/delete_merged_report.py`)

同理，在删除合并报告时，清理 `report_merge` 子目录下的图片。

## 5. 迁移策略 (Migration)

对于现有的 `editor_image` 根目录下的扁平图片：
1.  **短期**：保留不动，作为“遗留区”。新逻辑上线后，新图片将全部进入结构化目录。
2.  **长期**：由于旧图片难以自动归类，建议在系统稳定运行一段时间后，通知用户手动清理或编写脚本根据创建时间归档。

## 6. 本次完成情况与验证结果

### 6.1 关键实现 (已完成)

1.  **后台生成 HTML 时补齐上下文**：后台在生成 HTML 时从报告路径中解析 `user_id`、`report_type`、`report_name`，并按结构化目录创建图片输出目录。
2.  **图片目录与 URL 对齐**：图片输出目录采用 `editor_image/report/{user_id}/{report_type}/{report_name}/`，同时 HTML 图片引用使用 `/python-api/editor_images/report/{user_id}/{report_type}/{report_name}/` 作为前缀，确保前后端路径一致。
3.  **兼容无用户路径**：当报告路径中不包含用户目录时，降级为 `editor_image/report/{report_type}/{report_name}/` 的结构，保证历史路径也能生成 HTML。
4.  **转换入口统一**：后台统一通过 `convert_docx_to_html` 传入 `image_output_dir` 与 `image_url_prefix`，保证 HTML 引用与实际落盘目录同步。
5.  **[新增] 合并报告图片物理隔离**：在生成合并报告 HTML 时，主动扫描引用的草稿图片，将其**物理复制**到 `report_merge` 专属目录，并重写 HTML 中的 `src` 属性。这确保了合并报告是完全独立的，即使删除了草稿，合并报告的图片依然存在。
6.  **[新增] 前端上传适配**：前端已完成适配，在上传图片时会根据上下文传递 `source_type="merge"` 或 `source_type="report"`，后端据此将图片存入对应目录。

### 6.2 成果回显
1.  **上传图片成功**：编辑器上传图片已进入结构化目录，路径回显与预期一致。
2.  **合并报告成功**：合并报告输出结果正常生成，图片引用可正确解析与展示，且图片文件实际存在于 `report_merge` 目录下。

### 6.3 验证要点
1.  **目录落盘检查**：在 `editor_image/report` 下可以按用户、报告类型、报告名称逐层找到图片。
2.  **HTML 引用检查**：生成的 HTML 中图片路径与实际目录一致，前端访问无需额外修正。
3.  **合并结果检查**：合并报告的 DOCX/HTML 与图片引用一致，显示正常。即使删除草稿源文件，合并报告图片依然可用。
