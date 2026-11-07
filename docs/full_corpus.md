# 全量流程与中间结果

全量入口是 `python -m bank_data.bulk_run`。小样本 SQLite 工作流继续可用；大量记录采用流式 JSONL 分区与 DuckDB 磁盘聚合。

原始文件保持只读。文件名、表头、首中尾和固定种子随机样本交给本地 Qwen 做相关性判断；没有把每张表的全部内容一次性输入模型。相关的结构化表由模型生成字段、条件和阶段映射，程序逐行复制原值并校验；需要语义理解的段落再按记录输入模型。这样能减少重复推理和模型转抄原值的错误。文件筛选仍可能遗漏相关文件，不能把处理覆盖率当成语义准确率。

## 运行

```bash
python -m pip install -e '.[bulk,llm,serve,native]'
# CUDA PyTorch 单独按服务器驱动安装；libarchive、antiword 和 OCR 图形依赖见部署说明。
CUDA_VISIBLE_DEVICES=0 python -m bank_data.serve_batch \
  --model-dir /private/models/Qwen3-8B --model-id YOUR_CHECKPOINT_ID --port 18080
```

服务仅绑定本机，支持每批最多 4 个独立 schema 请求。多 GPU 各启动一个副本并使用不同端口；单 GPU 也可完成全流程。

客户端按实际 tokenizer 统计每个请求，默认将填充后的整批输入加输出预算限制为 24,576 token，长请求提前拆批；GPU 仍不足时保留递归缩批。字段规划将相近表头和事件类别数量放在相邻批次，减少长短请求混排的填充开销。它们改变调度，不删除请求内容。

```bash
python -m bank_data.bulk_run \
  --input /private/raw --work-dir /private/full_run \
  --model YOUR_CHECKPOINT_ID --tokenizer-dir /private/models/Qwen3-8B \
  --endpoints http://127.0.0.1:18080/v1 --workers 6
```

已有原始扫描可用 `--profiles /private/previous/file_profiles.json` 代替 `--input`。重复运行同一个工作目录即可续跑。推理服务不可用会停止，不会把剩余语料全部伪装成语义复核。实际启动参数、源码副本和 SHA256 在每次运行的 `01_inputs/run_attempts` 与 `code_snapshots` 中保存。

## 可选的 vLLM 服务

服务器案例使用原始 BF16 Qwen3-8B 权重。vLLM 提供同一批量协议、前缀缓存与 CUDA Graph；`--enforce-eager` 可关闭 Graph。每个服务最多同时处理 4 个独立请求，服务绑定 loopback，禁用使用统计与在线模型下载。

CUDA 11.8 安装案例使用独立环境，并按 [核心组件约束](../scripts/vllm-cu118.constraints.txt) 安装。官方安装包 SHA256 为 `54230c11150a8d6314fb9d4856b045b3d5bf80092fa1901f3e1ef3b9afcd6e3f`，由 [官方发布包核对工作流](https://github.com/chaomacv/beijing-enterprise-intelligence/actions/runs/42392558379) 实际计算；镜像下载也须核对相同哈希。安装方法参考 [vLLM 0.8.5 官方 GPU 文档](https://docs.vllm.ai/en/v0.8.5/getting_started/installation/gpu.html)。

```bash
python -m pip install -c scripts/vllm-cu118.constraints.txt \
  'https://github.com/vllm-project/vllm/releases/download/v0.8.5/vllm-0.8.5%2Bcu118-cp38-abi3-manylinux1_x86_64.whl' \
  --extra-index-url https://download.pytorch.org/whl/cu118
CUDA_VISIBLE_DEVICES=0 python -m bank_data.serve_vllm \
  --model-dir /private/models/Qwen3-8B --model-id YOUR_CHECKPOINT_ID --port 18080
```

该版本 XGrammar 对数组长度和数值范围的支持有限。解码时使用其支持的结构约束，每条候选输出随后仍按**完整原始 JSON Schema**校验，再执行原文引用、主体和记录 ID 校验。失败输出仍走重试或复核。完整 Schema 保持原值并保存在请求中；单元测试覆盖超界输出被拒绝、独立约束、截断及日志不输出业务值。

8 个相同的合成请求在原服务、vLLM eager、vLLM Graph 上分别耗时 49.090、17.469、15.209 秒；各自另有预热。三者均通过 8 项业务检查，原服务有 2 个请求需要来源校验重试。输出 token 数不同，这些时间只能描述该组测试，不能外推全量吞吐或真实数据准确率。实际依赖冻结、请求、回复和比较结果保留在私有运行目录。

## 九步产物

| 目录 | 处理 | 可检查的中间结果 |
| --- | --- | --- |
| 01_inputs | 固定输入，展开容器，保留转换来源 | input_ledger.json、archive_members.json、expanded/、ocr_cache/、xml_tables/、geodatabase_tables/ |
| 02_profiles | 流式盘点与抽样 | original_profiles.json、all_profiles.json、all_profiles_native.json、file_cards.jsonl / file_cards_native.jsonl、summary.json |
| 03_screen | 本地模型筛选每个逻辑表 | scopes/ 中的逐表判断及模型原回复、files.json、prompt.md、methods/、summary.json |
| 04_plans | 模型选择主体、事实字段、条件和阶段 | scopes/ 中的映射、输入卡片哈希、校验错误与模型回复；config.json、prompt.md、summary.json |
| 05_records | 按完整记录读取保留内容 | 每个 file_id 的 rows.jsonl、contexts.json、chunks.jsonl，保留 sheet / row / record_id |
| 06_validation | 执行字段方案，复杂行模型抽取，校验来源 | mapped_results.jsonl、pending_llm.jsonl、llm_results/、record_results.jsonl、逐文件和总 summary.json |
| 07_entities | 保守身份关联与候选匹配 | results.duckdb、entities.parquet、entity_mentions.parquet、name_ambiguities.parquet、name_neighbors.parquet |
| 08_results | 导出事实、画像与来源 | profiles / events / event_sources 的 JSONL 和 Parquet；record_ledger.parquet、file_index.json、summary.json |
| 09_review | 集中列出不确定及失败输入 | file_review.json、record_review.jsonl / parquet |

根目录 `run_status.json` 给出阶段状态；`流程与结果.md` 汇总各步数量和追溯方法；`audit.json` 核对原始文件 ID 集合以及已知记录是否都有结果、显式排除或文件失败去向。

人工查看可先打开各阶段的 `文件总表.csv`、`筛选总表.csv`、`字段方案总表.csv`、`分块与处理总表.csv` 和 `校验总表.csv`。这些是文件／表级索引；JSONL 和 Parquet 保存完整记录，避免大型结果受电子表格行数限制。

## 状态的含义

- 文件：PROFILED 已解析；EMPTY 无记录；CONTAINER 压缩容器；CONVERTED 有独立转换结果；COMPONENT 由数据库逻辑表消费的组件；METADATA 配套元数据；REVIEW 无法可靠读取。
- 筛选：KEEP 保留；DROP 明确排除；REVIEW 继续尝试字段规划，仍不确定则保留复核。
- 字段方案：map 直接应用；entity_only 基础主体信息；row_llm 逐行理解；exclude 排除；review 无可靠方案。缺失方案不能当作排除。
- 记录：EXTRACTED 有可追溯事件；NO_EVENT 无该类事件，可以保留基础主体；REVIEW 不进入已确认事实库。
- 事件阶段：confirmed / proposed / removed / revoked / unknown 分开保存。“未提取事件”不等于“企业无风险”。

部分附件只包含数据字典、交通影像或地理数据库配套文件。它们在台账中有完整去向，不应虚构为企业事实。压缩包限制深度、成员数量和展开字节量，拒绝路径穿越；原始文件不会被修改。

## 记录、长文本与证据

结构化单元格保持完整，记录不因字符窗口被截断。文件卡片的样本不等于事实输入。准备块以完整行分组，重复表头、前置说明及工作表语境通过 contexts.json 关联。预算不足时先减少请求中的记录数；长文本使用带重叠的子段并保留字符位置。单条仍不可靠就进入复核，不能将截断输出算成功。

OCR 保留模型版本、原图哈希、页号、文字框、识别置信度及原始文本。OCR 是未经人工核验的识别结果。FileGDB 属性表保留要素 ID，几何以 WKB 单独保存，并记录偏移、字节数及 CRS。通用 XML 展开保留重复节点索引和属性，原 XML 仍可追溯。

PDF 缺少原生文字时，先检查该页渲染图像。只有像素全部为白色才跳过该页，其他内容继续尝试 OCR 或保留复核；原始页码不改变。无扩展名的文本文件通过完整编码校验和有界 CSV 探测识别，支持 UTF-8、UTF-16 与 GB18030；探测窗口落在多字节字符中间时使用增量解码，不丢弃字符。

OCR 记录及其主体、事件会带 `source_quality=OCR_UNVERIFIED`、`source_kind` 和该页最低识别置信度；画像汇总 `observed_source_quality`。`confirmed` 描述来源中的事件阶段，不能理解为识别文字或银行事实已经人工核验。

表头自动识别和列宽异常等 `quality_flags` 也会关联到记录台账、事件来源及事件；事件去重时合并所有来源的标记，画像汇总 `observed_quality_flags`。`header_uncertain` 表示启发式方法未确认表头，不等于判定表头错误。`09_review/表头及结构复核清单.csv` 按逻辑表列出需要检查的结构，避免把这类问题混同于企业风险。覆盖统计针对解析器识别的逻辑记录；原始表头候选保留在上下文中，不能据此宣称全部物理行已经人工核验。

字段方案是有限的声明式映射，不执行模型生成的 Python 或正则。程序阻止机关代码充当企业代码、明确阶段与映射矛盾，以及检查合格生成处罚。来源引用、事件主体下标、记录 ID 集合分别验证；模型返回顺序不会改变记录归属。这些约束可以减少特定错误，无法替代独立语义评测。

`plan` 记录真正执行的方案：exclude / review / row_llm 的字段映射为空，entity_only 不包含事件映射。模型未被采用的定义仍可在 `response` 原回复中检查，避免把无效定义误当作已执行步骤。

## 对完全相同的内容复用推理结果

全量记录准备后，复杂记录按同一文件／逻辑表、完整单元格值及语境做精确哈希分组。模型处理代表记录，所有原始记录仍保留自己的 record_id、sheet、row 和来源。包含“同上”“上述”等相对表述的记录单独处理。数据不做空白归一化、近似文本合并或跨表复用。

本次发现一份百万行附件中有 1,048,465 行内容完全相同。这样的重复内容由一个代表记录进入本地模型，结果回填到各来源时重新核对完整内容哈希、原文引用及记录 ID。已有有效的逐记录检查点继续保留。模型输出格式、来源校验和旧推理缓存签名保持一致。

`06_validation/内容去重总表.csv` 汇总每个文件的原始待抽取记录、不同内容数和重复数；`content_indices/<file_id>/records.jsonl` 保存每条原始任务到代表记录的关系，`groups.jsonl` 保存组内数量及原始行范围。`unique_inference` 是指向原始准备记录及结果目录的执行视图，不另外复制原始数据。模型进度在其 `06_validation/llm_progress.json` 中，根阶段进度同时标明代表记录数量和原始记录数量；回填后每条来源仍有独立结果，并接受最终数量对账。

同一内容的多次出现不构成多份独立证据。原始记录数、不同内容数、模型请求次数、最终事实数分别统计，不能相互替代。

## 身份关联与使用结果

有效信用代码只证明校验位正确，不代表已通过登记机关核验。缺码记录只有在名称和非空地址完全一致且唯一指向一个代码时才挂接；代码冲突阻止自动归并。仅名称相同的记录保留临时身份，名称近似仅生成复核候选。不会对所有条目做全量两两比较，不生成授信分数。

```python
import duckdb
db = duckdb.connect('/private/full_run/07_entities/results.duckdb', read_only=True)
print(db.sql('SELECT status, count(*) FROM record_ledger GROUP BY status').fetchall())
print(db.sql('SELECT event_type, status, count(*) FROM events GROUP BY 1, 2').fetchall())
# 用事件 ID 找原始记录位置和逐字段证据。
print(db.execute('SELECT * FROM event_sources WHERE event_id = ?', ['YOUR_EVENT_ID']).fetchall())
```

全部结果保留在私有运行环境。仓库只包含代码、合成测试和汇总报告。
