# 代码迁移与重构实施计划

## 1. 目标
将 `generate_report_test`（测试环境）的代码迁移至 `generate_report`（生产环境），同时消除代码中的硬编码路径，实现一套代码在不同环境下仅需简单配置端口即可运行。

## 2. 准备阶段：备份与环境确认

### 2.1 备份现有生产环境
为了防止意外，首先对现有的 `generate_report` 目录进行完整备份。
- **操作**: 复制 `/root/zzp/langextract-main/generate_report` 到 `/root/zzp/langextract-main/generate_report_copy`。
- **命令**: 
  ```bash
  cp -r /root/zzp/langextract-main/generate_report /root/zzp/langextract-main/generate_report_copy
  ```

## 3. 实施阶段：代码重构 (在 `generate_report_test` 中进行)

本阶段的目标是修改测试环境的代码，使其具备“可移植性”。

### 3.1 引入统一配置文件 (`server_config.py`)
在 `generate_report_test` 根目录下创建一个新的配置文件 `server_config.py`，用于动态获取路径和管理端口。

**`server_config.py` 内容规划**:
```python
import os

# ===========================
# 端口配置
# ===========================
# 默认端口（测试环境：34521，生产环境请修改为：12543）
PORT = 34521

# ===========================
# 路径配置 (自动获取当前路径)
# ===========================
# 获取当前文件所在目录的绝对路径 (即项目根目录)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 定义各业务子目录 (相对于项目根目录)
REPORT_DIR = os.path.join(PROJECT_ROOT, "report")
INFERRENCE_DIR = os.path.join(PROJECT_ROOT, "inferrence")
MERGE_DIR = os.path.join(PROJECT_ROOT, "report_merge")
EDITOR_IMAGE_DIR = os.path.join(PROJECT_ROOT, "editor_image")

# 确保关键目录存在
def ensure_directories():
    for path in [REPORT_DIR, INFERRENCE_DIR, MERGE_DIR, EDITOR_IMAGE_DIR]:
        if not os.path.exists(path):
            os.makedirs(path)
```

### 3.2 替换硬编码路径
将所有文件中写死的 `/root/zzp/langextract-main/generate_report_test` 路径替换为引用 `server_config` 中的变量。

**涉及文件列表**:
1.  **入口文件**: `new_report.py`
    - 修改：导入 `server_config`，使用 `server_config.PORT` 启动应用，使用 `server_config.REPORT_DIR` 等挂载静态目录。
2.  **API 路由**: `routers/editor_api.py`, `routers/browse_report_api.py`, `routers/overwrite_doc_api.py` 等
    - 修改：将 `BASE_DIR = "..."` 替换为 `from server_config import REPORT_DIR as BASE_DIR`。
3.  **工具类**: `utils/zzp/report_merge.py`, `utils/zzp/html_to_docx.py`, `utils/lyf/ai_generate.py` 等
    - 修改：同样引入配置，注意处理 Python 的 import 路径问题（可能需要 `sys.path.append`）。

### 3.3 验证测试环境
在 `generate_report_test` 下启动服务，确保：
- 端口 `34521` 正常启动。
- 能够正常读取和写入文件（验证动态路径是否生效）。

## 4. 迁移阶段：部署到生产环境

### 4.1 清理生产环境
- **操作**: 删除 `generate_report` 目录下的所有**代码文件**（保留可能的历史数据如果需要，或者直接清空，因为我们已经备份了）。
- **注意**: 建议直接删除原目录内容，确保没有旧代码残留。

### 4.2 复制新代码
- **操作**: 将重构后的 `generate_report_test` 目录下的所有内容复制到 `generate_report`。
- **命令**:
  ```bash
  cp -r /root/zzp/langextract-main/generate_report_test/* /root/zzp/langextract-main/generate_report/
  ```

### 4.3 生产环境配置
这是切换环境唯一需要手动修改的地方。
- **操作**: 编辑 `/root/zzp/langextract-main/generate_report/server_config.py`。
- **修改**: 将 `PORT = 34521` 修改为 `PORT = 12543`。

## 5. 验收标准
1.  **代码一致性**: 生产和测试环境的代码文件完全一致（除了 `server_config.py` 中的一行端口配置）。
2.  **路径自适应**: 无论项目放在哪个文件夹，都能自动识别根目录，不再报 `FileNotFound` 或路径错误。
3.  **端口正确**: 生产环境运行在 12543，测试环境运行在 34521。

