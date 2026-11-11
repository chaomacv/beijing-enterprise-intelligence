# Beijing Enterprise Intelligence

<p><strong>简体中文</strong> &nbsp; | &nbsp; <a href="README.en.md">English</a></p>

[![Project Page](https://img.shields.io/badge/Project-Page-191919?style=flat-square)](https://chaomacv.github.io/beijing-enterprise-intelligence/)
[![Interactive Methods](https://img.shields.io/badge/Interactive-Methods-4269d0?style=flat-square)](https://chaomacv.github.io/beijing-enterprise-intelligence/#lab)

[![Beijing Enterprise Intelligence：从分散的数据到有据可查的企业情报](showcase/assets/project-preview.svg)](https://chaomacv.github.io/beijing-enterprise-intelligence/)

**[探索 Project Page ↗](https://chaomacv.github.io/beijing-enterprise-intelligence/?view=compact#explorations)** · 九张数据笔记本、真实来源目录与采集安全说明、三模式缩放旭日图、100家真实企业样本的二维／三维网络，以及九步处理与来源追溯。[最终结果与文件索引](docs/full_run_results.md) · [页面设计与复现](docs/project_page.md)

本批于 **2026-11-10 05:56（北京时间）**完成自动处理、分类修正与最终验收，状态为 `COMPLETED_WITH_REVIEW`。

| 本批口径 | 数量 |
| --- | ---: |
| 已接收原始附件 | 5,200 |
| 逻辑文件 | 11,701 |
| 已知逻辑记录 | 43,653,625 |
| 保留并逐条给出去向 | 15,861,277 |
| 主体画像（包含临时身份） | 5,202,714 |
| 事件观察 | 5,968,620 |
| 待复核记录 | 6,179,034 |

## 从4,365万条记录到38.8万个推理代表

```text
43,653,625 条已知逻辑记录
├─ 27,792,348 条：显式排除，保留排除台账
└─ 15,861,277 条：保留处理
   ├─ 14,420,658 条：字段方案通道，程序逐条执行
   └─  1,440,619 条：复杂语义来源
      ├─   388,349 个：不同内容代表，交给模型推理
      └─ 1,052,270 条：重复来源，核对后复用代表结果
```

推理后按来源回填到 **1,440,619 条**复杂记录，再与字段方案通道合并成 **15,861,277 条处理台账**。加上 **27,792,348 条显式排除**，本批 **43,653,625 条已知记录全部有去向**。388,349是语义通道的代表数，不是最终仅保留的记录数；复用不会删除原始来源。

处理台账进一步分为 EXTRACTED **6,300,941**、NO_EVENT **3,381,302**、REVIEW **6,179,034**。这些状态互斥、合计为15,861,277；画像、事件、来源链接分别计量，不能相加当作记录总数。

[交互数据去向与实际时间进度](https://chaomacv.github.io/beijing-enterprise-intelligence/?view=compact#explorations) · [九步输入、方法、数量与中间文件](docs/data_lineage.md) · [可对账数据接口](showcase/assets/data-lineage.json)

企业网络从已处理结果中分层选取 **100家具有校验位有效信用代码的企业画像**，每个圆点就是一家企业，以匿名编号展示。相似网络根据共同标签种类及可对应事件数决定目标距离；标签网络将标签固定在外围，企业与自身观察标签相连。保留二维拖动、缩放及三维旋转。

这是按类别与标签丰富度选取的展示样本，非总体随机样本。代码尚未做登记机关核验，事件数量是来源观察，包含拟议或阶段未明记录。全量5,202,714个主体画像的汇总、复核结果与完整标签组合统计继续保留；原始身份映射及模型回复只在私有服务器。

把北京公共数据平台下载的异构文件，转换为有来源证据的企业记录、业务事件与标签画像。语义理解使用私有环境中的 Qwen；读取、分块、校验和聚合使用 Python。

这是从 [beijing-open-data-enterprise-risk](https://github.com/chaomacv/beijing-open-data-enterprise-risk) 的业务问题出发建立的新后处理工程。原仓库和原始数据不做删除或覆盖。本项目重新实现处理模块，不复制旧脚本中的云 API 凭据或非企业筛选提示词。

## 当前版本能做什么

1. 接收独立下载器的工作目录，或服务器上的原始文件目录；按内容哈希盘点并保存处理状态。
2. 识别 CSV、Excel、JSON/JSONL、RDF/XML。识别“扩展名是 CSV、实际是 Excel”的文件，读取全部工作表。
3. 流式扫描全目录，生成首/中/尾与固定种子随机样本的文件卡片；筛选前不建立原始记录事实库。
4. 生成按完整记录划分的准备块；使用本地模型时，再以实际 tokenizer 和聊天模板检查输入/输出预算。
5. 用本地模型筛选并生成字段方案，结构化表由程序逐行执行，复杂内容分组后抽取。小样本入口使用 SQLite，全量入口使用流式 JSONL 和 DuckDB；原文引用、主体索引及记录覆盖分别验证，不可靠内容进入复核。
6. 使用信用代码校验、名称和地址做保守实体关联；名称相似只生成复核候选，不直接合并。
7. 导出事实事件、标签、画像、匹配依据、复核队列和来源索引。保留 proposed/confirmed/removed/revoked/unknown 状态，不生成授信评分。

当前版本 **v0.3.0**。本批已用本地 Qwen3-8B 原始 BF16 完成全量流程，采用流式 JSONL、字段方案执行、精确内容复用及 DuckDB 聚合。[全量流程](docs/full_corpus.md) · [最终结果](docs/full_run_results.md) · [独立评测边界](docs/validation.md)

全部 **5,968,620 条事件观察、18 个类别**按主体、类别及阶段汇总为画像标签，以 `classified_profile_tags.parquet` 为准。类别包含许可、人员、设备、产品、检查，以及行政处罚、经营异常、采购中标、科技认定等。拟议和阶段未明状态原样标注；待分类复核保留在画像中，不参与相似度计算。页面网络展示其中100家真实匿名企业的样本，范围覆盖全部18类。

全量处理入口如下，依赖、模型服务及系统读取工具见[部署与全量流程](docs/full_corpus.md)。同一工作目录支持兼容检查后的续跑；本批已完成目录无需再次运行。

```bash
python -m bank_data.bulk_run \
  --input /private/raw --work-dir /private/full_run \
  --model YOUR_LOCAL_MODEL_ID --tokenizer-dir /private/models/Qwen3-8B \
  --endpoints http://127.0.0.1:18080/v1 --workers 6
```

## 安装

Python >=3.10。在服务器项目目录执行：

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -e .
```

文件准备和规则 Demo 不需要 GPU、浏览器、平台登录或云 API。

## 小样本 workflow 入口

先生成文件卡片，再由本地模型筛选；只有保留文件的记录进入事实库。阶段结果与缓存支持重复运行。

```bash
python -m pip install -e '.[llm]'
bank-data workflow --input /private/raw --work-dir /private/results --through scan --workers 4
bank-data workflow --input /private/raw --work-dir /private/results \
  --backend local --endpoint http://127.0.0.1:8000/v1 \
  --model YOUR_LOCAL_MODEL_ID --tokenizer-dir /private/models/Qwen3-8B
```

[完整流程与状态说明](docs/workflow.md) · [本地模型服务与部署](docs/local_inference.md)

[为什么这样选工具和方法](docs/method_decisions.md) 将真实失败、当前修正和后续实验的触发条件放在一起。

## 先运行离线闭环

```bash
.venv/bin/bank-data demo --work-dir ../demo_process_work
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m unittest discover -s tests -v
```

Demo 输入由代码生成并明确标注为合成示例，所有企业名称和业务事实都是虚构的测试素材。`demo` 使用显式的规则基线，不能冒充 LLM 结果或银行实际业务数据。

## 准备真实文件

```bash
.venv/bin/bank-data prepare \
  --input /opt/data/private/mc/Bank/beijing_download_work \
  --work-dir /opt/data/private/mc/Bank/process_work
```

也可以把 `--input` 指向 `/opt/data/private/mc/Bank/data/raw/full-catalog` 等专门的数据目录。下载器的浏览器目录、运行依赖、目录导出和控制文件不参与业务抽取。下载或复制尚未结束的 `.part/.crdownload` 文件被排除。

`prepare` 输出：

- `inventory.json`：每个文件的内容哈希、格式与状态。
- `state.sqlite`：原始位置、原值、工作表和缓存。
- `file_cards.jsonl`：模型筛选所需的文件摘要。
- `prepared_chunks.jsonl`：按记录划分的准备块。
- `prepare_summary.json`：准备结果及解析失败统计。

解析失败会隔离整个文件，不把“读到一半”记作成功。原始文件保持只读。工作目录必须在输入目录之外。

## 使用本地 Qwen

先按 [部署说明](docs/local_inference.md) 在独立推理环境安装 CUDA 版 PyTorch 和 `.[serve]`，模型权重放在仓库外。服务绑定本机 `127.0.0.1:8000`，不自动升级系统驱动。

```bash
python -m bank_data.serve --model-dir /private/models/Qwen3-8B \
  --model-id qwen3-8b-checkpoint-v1 --device cuda:0 --port 8000
```

在另一个终端运行：

```bash
bank-data workflow \
  --input /opt/data/private/mc/Bank/data/raw/full-catalog \
  --work-dir /opt/data/private/mc/Bank/process_work \
  --backend local \
  --endpoint http://127.0.0.1:8000/v1 \
  --model qwen3-8b-checkpoint-v1 \
  --tokenizer-dir /path/to/local/Qwen3-8B
```

tokenizer 和权重只从本地读取，不下载远程代码。客户端只允许 loopback/RFC1918 地址，禁用代理及重定向，没有云 API 回退。内置服务通过 JSON Schema 约束输出并关闭思考模式；格式约束不保证语义正确。

明确选择规则对照：

```bash
.venv/bin/bank-data run --input /path/to/data --work-dir /path/to/private_work --backend rules
```

## 最终输出与核验

下面的 JSON／SQLite 文件说明对应小样本 workflow。全量入口的 JSONL、Parquet、DuckDB 和分类修正文件见[最终结果与文件索引](docs/full_run_results.md)。

`record_results.json` 给每条已解析记录一个处理结果；`FILE_EXCLUDED`、`REVIEW` 和 `NO_EVENT` 含义不同。`run_summary.json` 的状态覆盖检查只说明台账完整，不代表语义召回率为 100%。

`source_index.json` 将结果关联回原文件、工作表和逻辑记录序号。事件证据必须来自指定单元格，或受校验的 `__filename__` 原始标题；事件通过主体下标关联本行已校验的名称引用。文件、模型配置、本体和提示词变化会影响缓存键；更换权重时使用新的服务模型名。来源清单变化会重新准备文件，校验失败则隔离旧记录。

`entities.json`、`entity_mentions.json`、`match_decisions.json` 保留实体来源和匹配理由。不同且可信的信用代码不会自动合并；同名无地址的记录保留独立主体和候选。信用代码校验只证明形式/校验位正确，不等于权威工商身份核验。

## 当前边界

- 文件抽样不能保证发现罕见事件；排除文件仍需独立抽查与标注评估。
- 多行表头采用可检查的启发式。Excel 读取单元格缓存值，复杂子表、公式缓存和脚注语义需要抽查；全量入口支持文档正文、必要 OCR、压缩包、XML 与地理库属性；本批 65 个无法可靠读取的逻辑文件仍单列复核。
- 文件扫描使用固定数量的行样本；全量结果采用分区 JSONL 与 DuckDB 磁盘聚合，规模扩大仍需重新验证资源与质量。
- 复杂请求先按实际 token 预算拆组，长正文可重叠分段并合并；仍不可靠的单条内容保留复核。
- 没有可靠事件编号时保守保留不同源事件，不把语义相似直接当成重复。尚未实现跨事件阶段的自动关联。
- 已提供100家真实企业样本的相似图和外围标签图；向量召回、概率身份匹配、人工复核工作台和实体撤销合并仍属后续工作。
- 没有训练/验证集，因此不报告准确率、性能提升或银行收益。

## 数据与代码分离

原始数据、处理结果、模型权重、浏览器资料与凭据均不提交 Git。建议服务器布局：

```text
Bank/
  beijing-enterprise-intelligence/   # 仅源码、配置、文档、测试
  beijing_download_work/            # 原下载工作目录
  data/raw/                        # 原始文件
  models/                          # 本地权重
  process_work/                    # 私有处理结果
```

详细契约见 [docs/data_contract.md](docs/data_contract.md)。
