# 全量事件分类与画像标签

本批最终结果包含 **5,968,620 条事件观察、18 个类别**。公开图表、分类汇总与画像标签采用同一全量范围，保留每条事件的类别、阶段及来源。事件数量不代表独立有效证照数，也不代表企业数量。

分类由 `bank_data.event_taxonomy` 在原聚合数据库之后执行。企业许可、人员资格、设备检验、产品备案、申请和检查分别归类；行政处罚、经营异常等其他类别保留各自语义。来源主题用于区分类别，结构化引用字段用于阶段校验；无法确定的记录保留待复核状态。分类规则尚未经过独立人工语义准确率评测。

| 新类别 | 范围与边界 |
| --- | --- |
| 企业经营许可 | 食品经营、药品经营、经营备案等；不解释为目前有效 |
| 企业行业资质 | 建筑业资质、机构专业能力认定等 |
| 人员执业资格 | 建造师、施工人员考核等，仅表示人员与来源单位有关联 |
| 产品注册备案 | 药品批准、化妆品注册备案等 |
| 设备检验登记 | 特种设备检验、设备使用登记等 |
| 申请办理 | 资质申请、许可受理及办理事项；不表示获批或拟获批 |
| 监督检查 | 日常、行政、执法检查等；出现证号或检查机关不足以证明许可获批 |
| 行业考核与年检 | 信誉考核、年检、标准化考评等 |
| 项目审批与验收 | 施工许可、工程验收等，不归为企业自身经营许可 |
| 待分类复核 | 来源主题含混、非获证语境或同一事件不同来源分类冲突 |
| 行政处罚 | 来源中观察到的处罚事项，保留阶段及证据 |
| 经营异常 | 经营异常相关记录，保留来源状态 |
| 环保监管 | 环境与环保监管相关事项 |
| 科技认定 | 科技与创新认定相关记录 |
| 经营状态 | 来源中观察到的经营状态事项 |
| 采购中标 | 采购、中标相关公开记录 |
| 政策支持 | 补贴与政策支持相关记录 |
| 税务信用 | 税务信用相关公开记录 |

规则有顺序：申请和检查优先识别；人员、设备、产品及项目单独处理；普通“行政许可公示”不强行解释成企业经营许可。培训、通知和指南不作为获证依据。来源级细分仍有边界：混合业务表、含混标题和尚未验证的表头需要继续复核。

## 阶段与数量口径

- 保存 `original_type`、`original_status`、`classification_reason`、`stage_reason` 及来源指针。
- `unknown` 不因本次细分提升为 `confirmed`；申请和未分类记录统一保留阶段未知，旧阶段可查询。
- 原 `confirmed` 记录需要相应结构化依据：证件／批准／备案引用或发证等日期；检查类需要结论／结果字段。有效期不能当证件编号，检查实施机关不能当检查结果。
- `confirmed` 表示保留了相应记录的阶段依据，不证明证照当前有效；所有记录的 `current_validity` 均为 `not_verified`。
- 事件观察数按原 `event_id` 计数。关联画像数按类别及所选阶段去重，不同类别／阶段之间可能重叠，且包含临时身份。独立有效证照数和权威登记企业数均不报告。
- 非 `qualification` 类别及阶段保持原值；不是本次修正已完成其准确性评测的意思。

## 全量结果与画像接入

2026-11-10 已完成全批 5,968,620 条事件的分类与对账，事件 ID、来源链接数量保留，四份 Parquet 回读计数通过。公开的 `showcase/assets/event-classification.json` 仅保存全量类别、阶段及关联画像数量，不单列历史子集。

画像标签由全部事件按 `entity_id, event_type, status` 汇总。18 类均保留；“待分类复核”不作为相似度特征。拟议、阶段未明等状态保留，并不自动成为已获批或当前有效的企业能力。人员、设备、产品等标签只表示来源中的关联。

公开网络展示100家真实匿名企业，使用这些企业在全部18类中的观察；这与全量画像的存储范围不同。私有分类输出如下：

| 输出 | 用途 |
| --- | --- |
| `classification.duckdb` | 独立查询修正后的分类及关联关系 |
| `classified_events.parquet` | 每个原事件的细分类别、修正阶段及依据 |
| `classified_event_sources.parquet` | 每个原来源的来源级分类与原指针；最终事件分类以 `classified_events` 为准 |
| `classified_profile_tags.parquet` | 由修正事件重新聚合的画像标签，供下游使用 |
| `scope_rules.parquet` | 各来源逻辑表所用规则 |
| `audit.json` | 私有输入位置、代码哈希、数量及只读核对 |
| `public_summary.json` | 全部事件的18类分类与阶段汇总，经过字段白名单限制 |

下游统一消费 `classified_profile_tags`，按 `entity_id` 关联画像及原始证据。历史中间产物仅用于内部审计，不作为当前公开统计口径。

## 执行与接入

```bash
python -m pip install -e '.[taxonomy]'
python -m bank_data.event_taxonomy \
  --database /private/completed-run/07_entities/results.duckdb \
  --output /private/completed-run/10_classification_v1
```

输出目录必须是新的，避免覆盖已有版本。完整主任务仍在运行时，可将修正作为一次性下游阶段排队：

```bash
python scripts/refine_completed_run.py \
  --work-dir /private/full-run \
  --output /private/full-run/10_classification_v1 --wait
```

脚本仅在主任务完成且两项总覆盖对账通过后执行；主任务失败则明确退出。状态单独写入 `classification_job.json`，不修改主任务状态或重启模型。

```sql
-- 在独立 classification.duckdb 中查询。
SELECT event_type, status, count(*) AS observations
FROM classified_events GROUP BY event_type, status;

SELECT entity_id, event_type, status, observed_events
FROM classified_profile_tags;

-- 原始证据在原 results.duckdb 的 events / event_sources，按 event_id 回查。
```
