# vLLM 服务部署指南

## 1. 部署概述

本文档记录了在 GPU 服务器上部署 vLLM 服务的过程，用于支持 `generate_report_test` 项目的 AI 功能。

## 2. 环境信息

| 项目 | 配置 |
|------|------|
| **GPU** | NVIDIA L20 (46GB 显存) |
| **vLLM 版本** | 0.15.1 |
| **Python 环境** | `/vm-storage/conda_envs/anaconda3/envs/vLLM` |
| **模型** | `casperhansen/deepseek-r1-distill-qwen-32b-awq` |
| **服务端口** | 8005 |

## 3. 关键更改记录

### 3.1 模型配置更改 (.env)

**文件**: `/root/zzp/langextract-main/generate_report_test/.env`

**修改内容**:
```bash
# 修改前
AI_MODEL_NAME=deepseek-32b

# 修改后
AI_MODEL_NAME=casperhansen/deepseek-r1-distill-qwen-32b-awq
```

**原因**: 模型名称必须与 vLLM 加载的模型名称完全匹配，否则会出现 404 错误。

### 3.2 量化格式优化

**修改内容**:
```bash
# 修改前
--quantization awq

# 修改后
--quantization awq_marlin
```

**原因**: `awq_marlin` 是 vLLM 0.15.1 引入的优化量化格式，比标准 `awq` 快 2-3 倍。

### 3.3 显存利用率调整

**修改内容**:
```bash
# 修改前
--gpu-memory-utilization 0.90

# 修改后
--gpu-memory-utilization 0.85
```

**原因**: GPU 0 上有其他服务占用显存（bge-large-zh-v1.5, bge-reranker-base），需要预留足够空间。

### 3.4 移除不兼容参数

**修改内容**:
```bash
# 移除以下参数（vLLM 0.15.1 不支持）
--device cuda
```

**原因**: vLLM 0.15.1 版本已移除 `--device` 参数，默认使用 CUDA。

### 3.5 添加 HuggingFace 镜像

**修改内容**:
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

**原因**: 解决国内网络无法直接访问 HuggingFace 的问题。

## 4. 启动命令

### 4.1 后台启动命令（推荐）

```bash
source /vm-storage/conda_envs/anaconda3/bin/activate vLLM && \
export HF_ENDPOINT=https://hf-mirror.com && \
CUDA_VISIBLE_DEVICES=0 nohup python -m vllm.entrypoints.openai.api_server \
  --model casperhansen/deepseek-r1-distill-qwen-32b-awq \
  --quantization awq_marlin \
  --dtype half \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 32 \
  --max-num-batched-tokens 8192 \
  --kv-cache-dtype auto \
  --port 8005 \
  > /tmp/vllm.log 2>&1 &
```

### 4.2 参数说明

| 参数 | 说明 |
|------|------|
| `CUDA_VISIBLE_DEVICES=0` | 指定使用 GPU 0 |
| `nohup` | 后台运行，不受终端关闭影响 |
| `--model` | 模型名称（HuggingFace 格式）|
| `--quantization awq_marlin` | 使用 AWQ Marlin 量化（更快）|
| `--dtype half` | 使用 FP16 精度 |
| `--max-model-len 8192` | 最大序列长度 |
| `--gpu-memory-utilization 0.85` | GPU 显存利用率（85%）|
| `--max-num-seqs 32` | 最大并发序列数 |
| `--max-num-batched-tokens 8192` | 最大批处理 token 数 |
| `--port 8005` | 服务端口 |

## 5. 服务管理

### 5.1 查看服务状态

```bash
# 检查进程
ps aux | grep vllm

# 检查端口
lsof -i :8005

# 测试 API
curl http://localhost:8005/v1/models
```

### 5.2 查看日志

```bash
tail -f /tmp/vllm.log
```

### 5.3 停止服务

```bash
# 查找并停止 vLLM 进程
pkill -f "vllm.entrypoints.openai.api_server"
```

## 6. 故障排查

### 6.1 模型不存在错误 (404)

**错误信息**:
```
The model `deepseek-32b` does not exist.
```

**解决方案**: 检查 `.env` 文件中的 `AI_MODEL_NAME` 是否与 vLLM 启动时使用的模型名称一致。

### 6.2 显存不足错误

**错误信息**:
```
Free memory on device cuda:0 (39.96/44.52 GiB) on startup is less than 
desired GPU memory utilization (0.9, 40.07 GiB)
```

**解决方案**: 降低 `--gpu-memory-utilization` 参数值（如从 0.90 改为 0.85）。

### 6.3 网络连接错误

**错误信息**:
```
HTTPSConnectionPool(host='huggingface.co', port=443): 
Failed to establish a new connection
```

**解决方案**: 设置 HuggingFace 镜像源：
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 6.4 输出速度慢

**可能原因**:
1. 使用的是 `awq` 而非 `awq_marlin` 量化
2. GPU 显存几乎占满
3. 首次推理需要 CUDA 图编译

**解决方案**:
1. 使用 `awq_marlin` 量化格式
2. 降低 `--gpu-memory-utilization`
3. 等待 CUDA 图编译完成（首次推理后会缓存）

## 7. 性能参考

| 指标 | 优化前 (awq) | 优化后 (awq_marlin) |
|------|-------------|-------------------|
| 生成速度 | ~4 tokens/s | ~15-30 tokens/s |
| 显存占用 | ~41GB | ~38GB |
| 首次加载时间 | ~30s | ~30s |

## 8. 相关文件

- **环境配置**: `/root/zzp/langextract-main/generate_report_test/.env`
- **服务日志**: `/tmp/vllm.log`
- **API 路由**: `/root/zzp/langextract-main/generate_report_test/routers/lyf_router.py`
- **AI 服务调用**: `/root/zzp/langextract-main/generate_report_test/utils/lyf/prompt_chat_async.py`

## 9. 注意事项

1. **不要修改 GPU 1 上的服务** - 那是同事的其他项目
2. **使用后台运行** - 避免终端关闭导致服务停止
3. **定期清理日志** - `/tmp/vllm.log` 可能会变得很大
4. **重启 generate_report_test** - 修改 `.env` 后需要重启服务才能生效

---

**文档创建时间**: 2026-02-25  
**维护人员**: cqj  
**最后更新**: 2026-02-25
