# 文档拆分与生成机制及最佳实践方案

## 1. 现有机制深度解析

目前的文档生成过程（特别是基于“章节超市”或模板的组装流程）并非传统意义上的“物理拆分”，而是一个**“逻辑重组 + 动态生成”**的过程。

### 1.1 核心流程
1.  **前端重组 (Frontend)**：
    *   用户在 `NewReportModal` 中从不同来源（模板、上传文件、历史报告）拖拽章节。
    *   **关键动作**：无论来源章节原本叫什么（例如“3.5 结论”），一旦被拖入新的位置（例如第一章的第一个子节点），前端会根据当前的视觉顺序，重新分配 `sortOrder`（排序索引），即强制标记为 `1`。
    *   **数据构造**：前端将重组后的树形结构（包含新的 `sortOrder` 和原始 `title`）打包成 JSON 发送给后端。

2.  **后端生成 (Backend)**：
    *   **递归遍历**：后端接收 JSON，从根节点开始递归遍历。
    *   **前缀生成**：根据父节点的编号和当前节点的 `sortOrder` 动态计算新的章节号（Prefix）。
        *   算法：`ParentPrefix` + `.` + `SortOrder` (例如 `1` + `.` + `1` = `1.1`)
    *   **文件命名**：将 `Prefix` 与 `Title` 拼接，生成最终文件名。
        *   逻辑：`{Prefix} {Title}.docx` (例如 `1.1` + `项目背景` = `1.1 项目背景.docx`)
    *   **物理落盘**：如果是导入节点，复制源文件；如果是新节点，创建空文件。

### 1.2 存在的风险点
虽然前端已经做了“重排”，但如果直接使用现有逻辑，生成的并不是“完美顺序”的文件，主要存在以下缺陷：

1.  **“幽灵编号”残留 (Double Numbering)**
    *   **现象**：如果你从超市拖入一个原本叫 `3.5 风险分析` 的章节，把它放在新报告的 `1.1` 位置。
    *   **结果**：后端生成的文名为 `1.1 3.5 风险分析.docx`。
    *   **原因**：原始标题中携带了旧的编号，直接拼接导致混乱。

2.  **系统排序错乱 (Sorting Issue)**
    *   **现象**：当同级章节超过 9 个时（如 `1.1` 到 `1.12`）。
    *   **结果**：Windows/Linux 文件管理器默认排序可能变成 `1.1`, `1.10`, `1.11`, `1.12`, `1.2`...
    *   **评价**：这不符合人类阅读习惯，破坏了“完美顺序”。

3.  **文件名过长风险**
    *   层级过深（如 `1.1.1.1.1`）加上冗长的标题，可能触碰操作系统的路径长度限制（通常 255 字符），导致生成失败。

---

## 2. 最佳实践方案：构建“稳健的完美序列”

为了确保无论用户如何拖拽、来源如何混杂，最终生成的都是**干净、有序、计算机与人眼排序一致**的文件结构，建议实施以下 **"Clean-Order-Safe" (COS)** 策略。

### 2.1 方案核心逻辑 (伪代码)

```python
def process_node_best_practice(node, parent_prefix, sort_order):
    # 1. 生成智能前缀 (支持零填充，解决排序问题)
    # 使用 01, 02... 代替 1, 2...
    current_prefix = generate_padded_prefix(parent_prefix, sort_order) 
    
    # 2. 标题清洗 (解决幽灵编号问题)
    # 核心：无论原标题是什么，先用正则把开头的数字编号扒掉
    raw_title = node.get("title")
    clean_title = regex_replace(raw_title, pattern=r"^[\d\.\s]+", replacement="")
    
    # 3. 组装最终文件名
    final_name = f"{current_prefix} {clean_title}.docx"
    
    # 4. 安全截断 (防止路径溢出)
    safe_name = truncate_filename(final_name, max_length=100)
    
    return safe_name
```

### 2.2 具体实施步骤

#### 步骤一：后端增加“标题清洗” (必须)
这是解决乱码编号的最关键一步。在拼接新编号前，强制清洗旧编号。

*   **Regex 规则**：`^(\d+(\.\d+)*\s*)+`
*   **效果**：
    *   `3.5 风险分析` -> `风险分析`
    *   `1.1.1  详细设计` -> `详细设计`
    *   `绪论` -> `绪论` (保持不变)

#### 步骤二：引入“零填充”排序 (建议)
为了保证文件系统排序完美（1.01, 1.02 ... 1.10），建议对章节号进行格式化。

*   **规则**：每一级编号都保证至少两位数（或根据总数动态调整）。
*   **对比**：
    *   旧：`1.1`, `1.2`, `1.10` (排序混乱)
    *   新：`01.01`, `01.02`, `01.10` (排序完美)

#### 步骤三：文件名与元数据分离
*   **文件系统层**：文件名仅用于“人类可读”和“基本排序”，可以简化。例如 `01_01_项目背景.docx`。
*   **数据库层**：完整保留原始的长标题、特殊符号等。
*   **应用层**：前端展示时优先读取数据库中的 `chapter_title`，而不是去解析文件名。

### 2.3 预期效果对比

| 场景 | 原始方案结果 (有风险) | 最佳实践方案结果 (完美) |
| :--- | :--- | :--- |
| **拖拽旧章节** | `1.1 3.5 风险分析.docx` | `1.1 风险分析.docx` |
| **超过10个章节** | 列表顺序：1.1, 1.10, 1.2 | 列表顺序：1.01, 1.02 ... 1.10 |
| **带特殊符号** | `1.1 项目/方案.docx` (可能报错) | `1.1 项目_方案.docx` (自动转义) |

---

## 3. 分角色实施指南 (Agent Action Plan)

为了实现上述最佳实践，请将以下具体指令分发给对应角色的 Agent 或开发人员。

### 🤖 Backend Agent (Python)

**目标**：确保生成的文件名绝对干净、排序友好，且不包含重复编号。

**任务清单**：
1.  **定位文件**：`/root/zzp/langextract-main/generate_report_test/utils/zzp/create_catalogue.py`
2.  **修改 `process_node_recursive` 函数**：
    *   **引入正则库**：确保文件头部 `import re`。
    *   **实现标题清洗**：
        ```python
        # [Action] 强力清洗标题中的旧编号
        clean_title = re.sub(r'^[\d\.]+\s*', '', title).strip()
        ```
    *   **实现零填充前缀 (Zero-Padding)**：
        修改 `generate_prefix` 函数，使其支持两位数格式化：
        ```python
        def generate_prefix(parent_prefix, sort_order):
            # 格式化为两位数，如 01, 02... 10
            formatted_order = f"{sort_order:02d}" 
            if parent_prefix:
                return f"{parent_prefix}.{formatted_order}"
            return formatted_order
        ```
    *   **文件名组装**：
        使用 `clean_title` 和 `current_prefix` 组合。
        ```python
        raw_node_name = f"{current_prefix} {clean_title}"
        ```

### 🎨 Frontend Agent (Vue/JS)

**目标**：确保前端解析逻辑兼容后端的新命名规则（零填充），并正确展示。

**任务清单**：
1.  **定位文件**：`/root/zzp/langextract-main/ljt/report_system/src/views/dataGo/home/util.js`
2.  **检查 `parseFileListToTree` 函数**：
    *   **验证正则兼容性**：
        当前正则 `const match = fileName.match(/^([\d.]+)/)` 可以匹配 `01.01`，**无需修改**。
    *   **验证排序逻辑**：
        如果前端有自定义排序逻辑，确保其能处理字符串比较（`"01"` vs `"10"`）。目前的字符串字典序比较对于零填充格式是完美的。
3.  **视觉优化 (Optional)**：
    *   如果在界面上不希望看到 `01.01` 这种前导零，可以在渲染层（如 `viewReportFirstDraft.vue`）做一次去零处理：
        ```javascript
        // 显示给用户看的时候，把 01.01 转回 1.1
        displayId = node.id.split('.').map(Number).join('.')
        ```
    *   *注：建议保留前导零，体现专业性和排序的一致性。*

### ✅ 验收标准 (Acceptance Criteria)

1.  **拖拽测试**：从“章节超市”拖入一个名为 `5. 结论` 的章节到新报告的第一章。
    *   **通过**：生成文件名为 `01 结论.docx` (或 `1.1 结论.docx`，取决于是否启用零填充)。
    *   **失败**：生成文件名为 `01 5. 结论.docx`。
2.  **排序测试**：创建 12 个同级章节。
    *   **通过**：文件管理器中顺序为 `01...09, 10, 11, 12`。
    *   **失败**：顺序为 `1, 10, 11, 12, 2...`。

---

## 4. 实施记录 (Implementation Log)

### 2026-02-03 Backend Implementation
- **状态**: ✅ 已完成
- **修改文件**: `/root/zzp/langextract-main/generate_report_test/utils/zzp/create_catalogue.py`
- **主要变更**:
    1.  **强力标题清洗**: 引入 `re` 模块，使用 `re.sub(r'^[\d\.]+\s*', '', title).strip()` 移除标题中的旧编号。
    2.  **零填充前缀**: 更新 `generate_prefix` 函数，使用 `f"{sort_order:02d}"` 格式化编号 (如 `01`, `02`)，确保文件系统排序正确。
    3.  **文件名组装**: 采用 `Prefix + Cleaned Title` 的方式生成文件名，彻底解决“幽灵编号”和排序错乱问题。
- **验证结果**:
    - `generate_prefix` 逻辑验证通过 (`1` -> `01`).
    - `clean_title` 逻辑验证通过 (`3.5 风险分析` -> `风险分析`).

### 2026-02-03 Backend Fix - Source File Missing
- **状态**: ✅ 已完成
- **修改文件**: `/root/zzp/langextract-main/generate_report_test/utils/zzp/create_catalogue.py`
- **问题根因**:
    - 初始实施中仅清洗了生成文件的文件名，但在数据库 `catalogue_name` 字段中仍存储了带有旧编号的“脏标题”。
    - `get_source_file_path` 依赖标题的精确匹配。如果前端传递的标题与数据库存储的标题不一致（例如：前端传递了清洗后的标题而数据库存的是脏标题，反之亦然），会导致查找失败，返回 `None`。
- **主要变更**:
    1.  **数据库一致性**: 修改 `process_node_recursive`，将 `clean_title`（清洗后的标题）存入数据库 `catalogue_name` 字段。这确保了数据库记录与实际文件内容一致，并防止“幽灵编号”在元数据中残留。
    2.  **健壮的查找逻辑**: 升级 `get_source_file_path` 函数，使其同时尝试匹配“原始标题”和“清洗后的标题”。这确保了即使前端传递了“3.5 风险分析”而数据库存储的是“风险分析”（或反之），系统仍能正确通过模糊匹配策略找到源文件路径。
- **验证结果**:
    - 代码审查确认 `get_source_file_path` 现已具备双重匹配能力，能有效解决因标题格式不一致导致的源文件丢失问题。

### 2026-02-03 ID-Based Linking Implementation
- **状态**: ✅ 已完成
- **修改文件**:
    - `utils/zzp/import_catalogueShopping.py`: 在返回给前端的超市列表中，显式暴露 `origin_catalogue_id` 字段。
    - `utils/zzp/create_catalogue.py`: 支持接收并优先使用 `origin_catalogue_id` 进行源文件定位。
- **目的**: 彻底消除因标题重复或变更导致的源文件定位错误，建立稳健的强引用关系。

---

## 5. 已知问题与待解决事项 (Known Issues & Pending Items)

### 5.1 源文件缺失 (Source File Missing) - [已解决]
- **解决方案**: 后端已升级查找逻辑（支持清洗标题匹配）并统一了入库标题格式。

---

## 6. 最佳实践演进：基于ID的强引用 (Evolution to Best Practice: ID-Based Linking)

### 6.1 风险分析：为什么 "标题匹配" 仍不完美？
虽然目前的“标题清洗 + 双重匹配”解决了大部分问题，但它仍依赖于“文本一致性”。
- **风险场景**:
    - **重名章节**: 如果用户有两个报告都包含名为“风险分析”的章节，后端根据标题查找时，可能无法区分到底想要哪一个（目前逻辑是 `LIMIT 1`，可能返回错误的那个）。
    - **标题变更**: 如果源文件标题被修改，但引用关系未更新，链接即刻失效。

### 6.2 推荐方案：ID-Based Source Tracking (Target State)
为了彻底消除歧义，建议前后端交互协议从“基于描述”升级为“基于标识”。

#### 核心协议变更
1.  **Backend (已就绪)**:
    - **发送 (List)**: `Import_catalogue` 接口返回的数据中，每个节点现已包含 `origin_catalogue_id`。
    - **接收 (Create)**: `create_catalogue` 接口支持处理 `origin_catalogue_id`，优先用于文件定位。

2.  **Frontend (待更新 - Action Required)**:
    - **任务**: 在拖拽节点生成 JSON 数据时，**必须**将源节点的 `origin_catalogue_id` 传递给后端。
    - **Payload 示例**:
      ```json
      {
          "title": "风险分析",
          "isimport": 1,
          "origin_catalogue_id": 1024,  // <--- 🚨 请前端务必透传此字段
          "originreportName": "2024Q1报告",
          ...
      }
      ```
    - **注意**: 现在的后端 API 已经返回了这个字段，前端只需要在构建拖拽数据对象时，把这个值从 source 复制到 target 即可。

### 6.3 实施状态 (2026-02-03)
- **Backend**: **✅ 全链路就绪**。
    - 已修改 `import_catalogueShopping.py` 确保 API 返回 ID。
    - 已修改 `create_catalogue.py` 确保 API 消费 ID。
- **Frontend**: **🕒 等待接入**。
    - 请前端开发参考上方 **6.2 核心协议变更** 进行字段透传。
