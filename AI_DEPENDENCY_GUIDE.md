# AI 依赖查找与检查规范指南

本文档旨在指导 AI 助手在处理本项目时，如何正确地查找、检查和安装 Python 依赖。

## 1. 故障诊断流程

当遇到 `ModuleNotFoundError` 或 `ImportError` 时，请遵循以下步骤：

### 1.1 确认缺失的包名
- 从错误日志中提取缺失的模块名称。
- 注意：模块名（如 `bs4`）可能与安装包名（如 `beautifulsoup4`）不同。

### 1.2 确认当前使用的环境
- 查看启动脚本（如 `restart_service.sh`）以确定激活的 Conda 环境名称或虚拟环境路径。
- 在本项目中，主要环境通常是 Conda 环境 `LangExtract`。
- 环境变量路径参考：`/opt/conda_envs/anaconda3/envs/LangExtract/`

### 1.3 验证环境中的依赖状态
- 使用以下命令检查包是否已安装：
  ```bash
  /opt/conda_envs/anaconda3/envs/LangExtract/bin/pip list | grep <包名>
  ```
- **关键点**：如果 `pip list` 显示已安装但运行报错，可能是因为：
    1. 包安装在用户本地目录（如 `~/.local/lib/...`）而非环境目录。
    2. 包的依赖项缺失（例如 `htmldocx` 依赖 `beautifulsoup4`）。
    3. 环境权限问题导致无法读取。

## 2. 依赖安装规范

### 2.1 使用正确的 Pip 路径
- 始终使用对应环境下的 `pip` 完整路径进行安装，避免误装到系统环境或其他用户目录。
- 示例：`sudo /opt/conda_envs/anaconda3/envs/LangExtract/bin/pip install <包名>`

### 2.2 权限处理
- 本服务器环境的部分 Conda 目录由 `root` 所有。
- 如果普通用户（如 `cqj`）安装失败并提示 `Permission denied`，请使用 `sudo` 执行安装命令。
- 安装时建议加上 `PYTHONNOUSERSITE=1` 环境变量，以确保包被安装到环境目录而不是用户的 `.local` 目录：
  ```bash
  sudo PYTHONNOUSERSITE=1 /opt/conda_envs/anaconda3/envs/LangExtract/bin/pip install <包名>
  ```

### 2.3 递归检查依赖
- 安装完主包后，应运行简单的测试脚本验证导入是否成功：
  ```bash
  /opt/conda_envs/anaconda3/envs/LangExtract/bin/python -c "import <模块名>; print('Success')"
  ```
- 如果报错提示其他模块缺失，请重复安装流程。

### 2.4 常见依赖陷阱
- **jwt**: 代码中 `import jwt`，但安装包应为 `PyJWT`。如果误装了 `jwt` 包（这是一个旧的、不相关的包），可能会导致冲突或功能缺失。
  - 正确安装：`pip install PyJWT`
  - 错误安装：`pip install jwt`

## 3. 维护建议

- **更新 requirements.txt**：在成功安装新依赖后，应检查并更新项目根目录下的 `requirements.txt`。
- **记录环境变化**：如果对 Conda 环境进行了重大修改，请在相关日志或文档中说明。
