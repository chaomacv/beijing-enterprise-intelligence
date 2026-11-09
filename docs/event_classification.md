# 许可相关记录的分类修正

旧版 `qualification` 是宽口径候选类，混合了企业许可、人员资格、设备检验、产品备案、申请与检查。它的计数不能作为独立许可证数量或有效企业资质数量。

修正由 `bank_data.event_taxonomy` 在原聚合数据库之后独立执行，不修改原始文件、模型缓存、原事件 ID 或旧交付。新分类依据来源文件／工作表的主题；阶段校验依据结构化引用字段。无法确定的来源保留“待分类复核”，没有把规则细分当作独立人工语义评测。

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

规则有顺序：申请和检查优先识别；人员、设备、产品及项目单独处理；普通“行政许可公示”不强行解释成企业经营许可。培训、通知和指南不作为获证依据。来源级细分仍有边界：混合业务表、含混标题和尚未验证的表头需要继续复核。

## 阶段与数量口径

- 保存 `original_type`、`original_status`、`classification_reason`、`stage_reason` 及来源指针。
- `unknown` 不因本次细分提升为 `confirmed`；申请和未分类记录统一保留阶段未知，旧阶段可查询。
- 原 `confirmed` 记录需要相应结构化依据：证件／批准／备案引用或发证等日期；检查类需要结论／结果字段。有效期不能当证件编号，检查实施机关不能当检查结果。
- `confirmed` 表示保留了相应记录的阶段依据，不证明证照当前有效；所有记录的 `current_validity` 均为 `not_verified`。
- 事件观察数按原 `event_id` 计数。关联画像数按类别及所选阶段去重，不同类别／阶段之间可能重叠，且包含临时身份。独立有效证照数和权威登记企业数均不报告。
- 非 `qualification` 类别及阶段保持原值；不是本次修正已完成其准确性评测的意思。

## 已执行的阶段子集

2026-11-09 对已完成的 1,884 文件子集执行修正：5,031,890 条旧类事件全部归入以上十类，总事件仍为 5,961,231 条。540,317 条旧 `confirmed` 记录因分类或阶段证据不足调整为 `unknown`。四份 Parquet 的回读计数通过，原数据库大小和修改时间保持一致。全部事件 ID、来源链接数量保留。

这仍是阶段子集，不能与未来全量结果相加。公开的 `showcase/assets/event-classification.json` 只含汇总；私有输出包含以下表：

| 输出 | 用途 |
| --- | --- |
| `classification.duckdb` | 独立查询修正后的分类及关联关系 |
| `classified_events.parquet` | 每个原事件的细分类别、修正阶段及依据 |
| `classified_event_sources.parquet` | 每个原来源的来源级分类与原指针；最终事件分类以 `classified_events` 为准 |
| `classified_profile_tags.parquet` | 由修正事件重新聚合的画像标签，供下游使用 |
| `scope_rules.parquet` | 各来源逻辑表所用规则 |
| `audit.json` | 私有输入位置、代码哈希、数量及只读核对 |
| `public_summary.json` | 经过字段白名单限制的公开汇总 |

旧 `08_results/profiles.tags` 保留作基线。使用修正口径时，应消费 `classified_profile_tags`，并按 `entity_id` 关联原画像，不再把旧宽类标签作为“已获企业资质”。

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

SELECT original_status, status, stage_reason, count(*)
FROM classified_events WHERE original_type='qualification'
GROUP BY original_status, status, stage_reason;

-- 原始证据在原 results.duckdb 的 events / event_sources，按 event_id 回查。
```
