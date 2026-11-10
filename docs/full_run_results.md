# 本批全量最终结果

完成时间：2026-11-10 05:56（北京时间）。状态：`COMPLETED_WITH_REVIEW`。
实际运行源码为 `57748c4c4086432c4b129a0fee059018a1d6a4c1`，模型为本地 Qwen3-8B 原始 BF16。
这里记录固定输入批次的结果；当前仓库后续改进不冒充该批次重新运行。

| 口径 | 数量 |
| --- | ---: |
| 网站目录数据集 | 4,710 |
| 已接收原始附件 | 5,200 |
| 展开及转换后的逻辑文件 | 11,701 |
| 逻辑表／文本作用域 | 13,281 |
| 已知逻辑记录 | 43,653,625 |
| 显式排除 | 27,792,348 |
| 保留并逐条给出去向 | 15,861,277 |
| EXTRACTED | 6,300,941 |
| NO_EVENT | 3,381,302 |
| REVIEW | 6,179,034 |
| 主体画像（包含临时身份） | 5,202,714 |
| 其中临时身份 | 4,364,721 |
| 主体提及 | 8,800,229 |
| 事件观察 | 5,968,620 |
| 事件来源链接 | 6,331,400 |

## 从输入到输出

| 步骤 | 输入与方法 | 私有运行目录产物 |
| --- | --- | --- |
| 01 固定输入 | 下载附件、目录及历史状态；核对哈希并保留容器来源 | `01_inputs/input_ledger.json`、`snapshot_integrity.json`、`archive_members.json` |
| 02 解析抽样 | 内容识别、展开、正文／OCR／XML／地理库解析；首中尾及固定种子样本 | `02_profiles/文件总表.csv`、`all_profiles_native.json`、`file_cards_native.jsonl` |
| 03 文件筛选 | 本地模型只接收卡片，保留、排除或复核 | `03_screen/筛选总表.csv`、`scopes/`、`prompt.md` |
| 04 字段方案 | 模型选主体、事件、条件和阶段，形成声明式映射 | `04_plans/字段方案总表.csv`、`scopes/`、`config.json` |
| 05 完整读取 | 每条保留记录完整原值、语境、位置及稳定编号 | `05_records/<file_id>/rows.jsonl`、`contexts.json`、`chunks.jsonl` |
| 06 抽取核验 | 14,420,658 条执行字段方案；1,440,619 条复杂来源分组为 388,349 个内容代表，推理后逐来源核验回填 | `06_validation/内容去重总表.csv`、`content_indices/`、`<file_id>/record_results.jsonl`；根目录模型请求／回复 |
| 07 主体关联 | 信用代码校验、名称与非空地址保守关联；近名仅产生候选 | `07_entities/results.duckdb`、`entity_mentions.parquet`、`name_ambiguities.parquet`、`name_neighbors.parquet` |
| 08 导出 | 主体画像、事件观察、来源链接及逐条记录台账 | `08_results/profiles.*`、`events.*`、`event_sources.*`、`record_ledger.parquet`、`file_index.json` |
| 09 复核验收 | 原附件及已知逻辑记录对账、导出回读、结构／OCR／语义分流 | `audit.json`、`09_review/file_review.json`、`record_review.parquet`、`表头及结构复核清单.csv` |
| 10 分类修正 | 5,032,506 条原许可宽类事件细分为十类，保留原事件与来源；阶段证据不足则回退 | `10_classification_v1/classification.duckdb`、`classified_events.parquet`、`classified_profile_tags.parquet`、`audit.json` |
| 最终报告 | 汇总所有验收与修正结果 | `交付汇总/完整处理结果.md`、`全量汇总.json`、`事件类别与阶段.csv`、`交付文件清单.json` |

画像／事件 → `event_sources` → `record_ledger` → `06_validation` 逐条结果与模型来源 → `05_records` 完整原值与语境 → 原始附件及网站来源。
修正后的分类标签使用 `classified_profile_tags.parquet`，原始 `profiles.tags` 保留作基线。

## 公开图表口径

- [最终汇总 JSON](../showcase/assets/final-results.json)：白名单字段导出，无原始业务单元格或企业标识。
- [三种旭日图接口](../showcase/assets/event-hierarchy.json)：原始附件按格式→官网所属部门→数据集；逻辑文件按类型→生成方式→匿名文件编号；业务记录按官网主题→互斥事件类别→真实阶段或处理去向。
- 业务记录旭日图包含排除和待复核项，多事件类别记录单列，每条记录只计一次，不能把 5,968,620 条事件观察当作 43,653,625 条输入记录的分母。
- [真实全量网络](../showcase/assets/real-network.json)：所有 5,202,714 个画像聚合为 1,753 个精确标签组合，包括 1,665,951 个没有事件标签的画像。没有抽样，也不生成虚构企业。
- 网络节点是标签组合，节点数量不等于企业数量。相似度为排除“待分类复核”后的二值 Jaccard；每组取 6 个满足阈值的近邻，边为双向召回结果的并集。无有效相似维度的组合保持孤立。
- 二维和三维使用同一份全量统计，分别运行 2D／3D 力模拟；三维可以旋转、平移、缩放和拖动节点。颜色使用 D3 Category10，额外类别循环配色。
- 画像个体与实验区继续明确标注合成素材，用于说明交互与证据结构，不能当作真实个体结果。

## 验收与边界

附件与已知逻辑记录覆盖对账、事件／来源守恒及导出回读通过；原始快照和模型哈希全部一致。
22 项源站下载失败未进入本批快照，65 个逻辑文件无法可靠读取，715 个已处理作用域仍有结构复核标记。
6,179,034 条记录保留复核。NO_EVENT 不等于企业没有风险；confirmed 描述来源阶段，不代表人工核验。
主体画像含临时身份；信用代码只验证校验位，未核验登记机关。证照当前有效性及独立语义准确率尚未核验，不生成授信分或授信决定。

完整明细、原始文件、模型权重及请求回复保存在私有服务器，不随公开仓库发布。
