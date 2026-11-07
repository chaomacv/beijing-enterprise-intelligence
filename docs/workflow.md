# 文件卡片优先的处理流程

v0.2 增加 `bank-data workflow`，执行：流式文件画像 → 本地模型筛选 → 保留文件入库 → 分块抽取 → 企业关联与导出。原有 `prepare`、`run` 和合成 `demo` 命令仍保留。

## 为什么拆开

文件筛选只需要文件名、表头、统计及首/中/尾和随机样本。先把所有原始记录写入事实库，会增加不相关文件的存储和后续准备成本。新的扫描阶段完整读取可识别文件以计数，但只持有固定数量的完整样本；精确中段样本通过第二次流式读取获取。

每个记录编号由读取器版本、相对文件路径、内容哈希、工作表和原始位置生成。文件卡片的样本编号与随后入库的编号一致。读取行为变化时提升版本，避免旧的空结果继续命中缓存。

当前 CSV、XLS、JSON 和 XML/RDF 使用 reader-v2；XLSX 使用 reader-v3-xlsx-dimensions。Excel 声明范围修正只使相应文件缓存失效，其他格式保持编号稳定。范围过大不会生成上万列虚假字段，范围过小也不能截断实际存在的记录。

## 运行与阶段输出

```bash
bank-data workflow --input /private/raw --work-dir /private/results --through scan --workers 4
bank-data workflow --input /private/raw --work-dir /private/results \
  --backend local --model YOUR_LOCAL_MODEL_ID \
  --tokenizer-dir /private/models/Qwen3-8B
```

输入和工作目录必须分开。默认处理输入目录发现的全部文件，不默认截取前几百行。不支持的格式进入复核，不将它们记作空表。

| 文件 | 含义 |
| --- | --- |
| `file_profiles.json` | 每份源文件的格式、哈希、记录数、文件卡片或复核原因 |
| `scan_cards.jsonl` | 提供给文件筛选模型的工作表级卡片 |
| `file_decisions.json` | 每个输入文件的 KEEP / DROP / REVIEW / EMPTY 与工作表决策 |
| `screen-cache/`、`profile-cache/` | 输入及配置未变化时的阶段缓存 |
| `facts/state.sqlite` | 仅保留文件的完整可解析记录及处理状态 |
| `facts/record_results.json` | 入库记录的 EXTRACTED / NO_EVENT / REVIEW / FILE_EXCLUDED 状态 |
| `facts/events.json`、`facts/profiles.json` | 证据支持的事件及企业画像 |
| `facts/source_index.json` | 原文件、工作表、记录位置和来源元数据 |
| `facts/review_queue.json` | 校验失败及模型主动复核的记录，含来源或错误说明 |
| `facts/progress.json` | 抽取阶段已分配状态的记录数；final_exports_ready 表示本轮最终导出是否就绪 |
| `workflow_summary.json` | 当前阶段、输入范围、复核与覆盖统计 |

任一工作表被保留时，整份文件进入准备阶段。文件内其余工作表仍按各自决策处理。排除文件保留文件级决策与记录总量，不把未入库的行伪装成已逐条抽取的结果。

`extraction_complete` 表示所选文件中已成功入库的记录完成状态分配；`completed_with_review`、`unresolved_files` 和 `review_records` 说明未解决范围。这些字段都不表示语义准确率或银行业务结论。

`file_record_counts` 按 KEEP / DROP / REVIEW 分别汇总已知记录数量；无法解析的文件没有可靠行数，不能把它们算成零条业务内容。中断后读取阶段摘要与 `facts/progress.json` 判断进度；旧的导出文件不代表本轮已经完成。重复执行同一命令续跑，同一工作目录不要同时启动多个写入进程。

## 真实文件暴露的问题

- CSV 名称可能承载 Excel 内容：按签名字节识别后交给对应读取器。
- 平台 RDF 使用带 `rdf:about` 的自定义资源节点：按资源节点读取，不再只认固定标签。
- 非空 XML 不符合已支持结构：进入复核，避免输出零行后误报成功。
- 旧 Word 与旧 Excel 都使用 OLE 容器：明确的 `.doc` 进入文档格式复核。
- UTF-16 CSV 与无后缀的文本文件：在有明确编码或分隔证据时识别，无法确定时复核。
- XLSX 声明范围可能覆盖大量空样式或小于真实数据范围：重置声明范围后按实际坐标读取，保留物理行号，并为表头内缺失的尾列补空值。

压缩包、扫描 PDF、复杂文档与超长单条记录仍需对应读取或分段扩展；它们在文件清单中可追查。当前首先验证表格主流程，不承诺所有文档格式均可自动理解。
