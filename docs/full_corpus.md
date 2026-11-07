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

```bash
python -m bank_data.bulk_run \
  --input /private/raw --work-dir /private/full_run \
  --model YOUR_CHECKPOINT_ID --tokenizer-dir /private/models/Qwen3-8B \
  --endpoints http://127.0.0.1:18080/v1 --workers 6
```

已有原始扫描可用 `--profiles /private/previous/file_profiles.json` 代替 `--input`。重复运行同一个工作目录即可续跑。推理服务不可用会停止，不会把剩余语料全部伪装成语义复核。实际启动参数、源码副本和 SHA256 在每次运行的 `01_inputs/run_attempts` 与 `code_snapshots` 中保存。

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

OCR 记录及其主体、事件会带 `source_quality=OCR_UNVERIFIED`、`source_kind` 和该页最低识别置信度；画像汇总 `observed_source_quality`。`confirmed` 描述来源中的事件阶段，不能理解为识别文字或银行事实已经人工核验。

字段方案是有限的声明式映射，不执行模型生成的 Python 或正则。程序阻止机关代码充当企业代码、明确阶段与映射矛盾，以及检查合格生成处罚。来源引用、事件主体下标、记录 ID 集合分别验证；模型返回顺序不会改变记录归属。这些约束可以减少特定错误，无法替代独立语义评测。

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
