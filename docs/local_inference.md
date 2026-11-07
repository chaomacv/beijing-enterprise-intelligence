# 本地 Qwen 推理

业务文件、提示词输入和模型输出仅在私有机器内处理。下载公开模型权重与运行业务推理解耦。推理服务只绑定 loopback，不会自动切换到云 API。

## 独立环境

使用 Python 3.10+ 创建与数据准备环境分开的虚拟环境。项目提供 Transformers + JSON Schema 约束的服务入口；不要求更新系统 GPU 驱动。

```bash
python3.10 -m venv ../qwen_runtime
../qwen_runtime/bin/python -m pip install --upgrade pip
```

根据机器驱动选择 PyTorch 构建。本项目在 RTX 4090、驱动 525.105.17、Python 3.10.22 上已验证以下 CUDA 11.8 组合：

```bash
../qwen_runtime/bin/python -m pip install 'torch==2.6.0+cu118' \
  --index-url https://download.pytorch.org/whl/cu118 \
  --extra-index-url https://pypi.org/simple
../qwen_runtime/bin/python -m pip install -e '.[serve]'
../qwen_runtime/bin/python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)'
```

依赖的具体解析版本应保存为运行报告；只有 `torch.cuda.is_available()` 通过后才启动模型。CUDA 构建选择参考 [PyTorch 官方版本安装说明](https://pytorch.org/get-started/previous-versions/)和 [NVIDIA CUDA 11.8 驱动兼容性说明](https://docs.nvidia.com/cuda/archive/11.8.0/cuda-toolkit-release-notes/index.html)。

本轮实际版本：PyTorch 2.6.0+cu118、Transformers 4.51.3、Accelerate 1.6.0、LM Format Enforcer 0.11.3。BF16 单卡加载 Qwen3-8B 后观测显存约 16.2 GiB（含运行时占用，非峰值基准）；服务就绪后仍需执行抽取回归。

## 权重与运行

模型案例为 [Qwen/Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B)。通过官方 Hugging Face 或 Qwen 的 ModelScope 仓库准备权重，放在 Git 仓库之外，并保存下载版本及 SHA-256 清单。正式推理只从本地目录加载，`trust_remote_code=False`。

```bash
../qwen_runtime/bin/python -m bank_data.serve \
  --model-dir /private/models/Qwen3-8B \
  --model-id qwen3-8b-local-checkpoint-v1 \
  --device cuda:0 --context 8192 --port 8000
```

修改权重后更换 `--model-id`，避免复用旧推理缓存。可选的 `BANK_LLM_API_KEY` 从环境读取，客户端与服务端保持一致；不要写入源码或公共运行日志。

服务提供 `/healthz`、`/v1/models` 和 `/v1/chat/completions`。最后一个接口要求 JSON Schema，固定 `enable_thinking=false`。生成过程使用 [LM Format Enforcer](https://github.com/noamgat/lm-format-enforcer)约束格式，再做 Schema 和原文证据检查；格式正确不代表事实正确。

抽取请求的 Schema 按当前批次绑定记录 ID、条数和可引用字段名，减少模型复制编号或字段名时出错。引用值和主体角色仍需单独核验；模型可能通过结构约束后仍因原文引用不符而进入复核。

服务复用 tokenizer 的约束解码词表数据，每次请求创建独立的 Schema 解析状态；不复用业务输出状态。`--cpu-threads` 默认 4，可按实际机器调整。本地模型默认预留每条记录约 512 个输出 token，2,048 输出预算先按最多 4 条组成初始批次；这只是保守估计，仍检查实际输入预算并在截断或证据失败时递归拆分。

## 接入完整处理流程

```bash
../qwen_runtime/bin/python -m bank_data workflow \
  --input /private/raw/download_snapshot \
  --work-dir /private/results/workflow \
  --backend local --endpoint http://127.0.0.1:8000/v1 \
  --model qwen3-8b-local-checkpoint-v1 \
  --tokenizer-dir /private/models/Qwen3-8B --workers 4
```

`--through scan` 只准备文件卡片，无需模型服务；`screen` 完成文件筛选后停止；`prepare` 只让保留文件进入原始记录库；默认 `run` 继续抽取、关联企业并导出。

重复执行会复用按文件哈希、读取版本、模型和提示词生成的缓存。`--retry-review` 重新处理文件/筛选复核项；原文证据校验失败的推理结果不会写入有效缓存。服务不可用时停止并保留进度，避免把全量输入错误地标成模型复核结果。

## 验证边界

```bash
../qwen_runtime/bin/python scripts/verify_local_model.py \
  --work-dir /private/results/synthetic_regression \
  --endpoint http://127.0.0.1:8000/v1 --model qwen3-8b-local-checkpoint-v1 \
  --tokenizer-dir /private/models/Qwen3-8B
```

该命令只生成虚构输入并检查筛选、合格检查不产生处罚、拟认定状态及逐条结果；不通过时退出码为 1，报告保存在工作目录。重复运行会复用有效推理缓存。它是合成回归检查，不提供真实数据准确率。

版本兼容、合成闭环和真实文件运行分别记录。样本运行通过不代表全量处理完成；记录覆盖不代表语义召回率。未支持格式、空表、读取失败、文件排除和待复核项各有状态，原文件始终保留。
