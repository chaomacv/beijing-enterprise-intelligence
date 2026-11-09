# Project Page

Project Page 源码位于 `showcase/`，部署地址为 https://chaomacv.github.io/beijing-enterprise-intelligence/ 。README 开头提供入口与预览图。

页面以“分散的数据，有据可查的企业情报”为主线，展示文件筛选、结构分块和企业归并的方法选择。视觉参考 Observable 的可探索文档、留白与数据图形；参考 RailMind 和 experience-guided-code-agent 的项目介绍结构。页面代码和图形独立实现，不复制参考站点的代码或资源。

2026-11-09 视觉改版采用白色文档底色、黑色主文字与操作按钮、居中的双行标题、细线分隔及彩色数据图形。首页的点阵、完整记录分组和来源网络是三个可点击的实验入口，分别打开既有抽样、分块和匹配面板。正文、状态、表格和辅助说明同步调整字号与对比度；移动端保留全部导航入口并将预览改成紧凑列表。

## 页面内容与数据

- `index.html` / `style.css`：中文项目介绍、方法、交互实验、证据追溯、九步流程、工程案例和复现入口。
- `model.js` / `app.js`：无第三方前端依赖的浏览器交互。抽样和分块实验是原理示意，不报告 token 节省或语义召回率。
- `run.js` / `assets/run-summary.json`：全量运行的汇总快照。九步导航说明各步输入、方法、中间产物及对应版本源码；每步支持鼠标和方向键切换。快照只含汇总数字，不连接私有处理服务。
- `assets/demo.json`：由仓库现有 Python 规则基线生成，包含 3 份合成文件、5 条记录、2 个暂定企业主体和 3 条事件。
- `assets/project-preview.svg`：README 的独立绘制预览图，图形是方法示意。
- `assets/notebook-*.svg`：三份独立绘制的静态合成图形，不依赖远程图片、字体或可视化库。

交互实验和企业证据案例均为合成示例；实际规模与工程对照在对应区域单独标明。没有把真实业务明细、下载会话、服务器路径、凭据或模型推理日志放入页面。页面不调用模型服务，也不接受业务文件上传。当前全量运行尚未完成，画像、事件等最终数量为空；完成总对账前不会展示最终结果。

三条工程笔记解释实际方法选择：完整内容精确复用仍保留每条来源；可重建的 HTML 文字视图仍绑定原字段；预算拆组后批量提交改善过长请求的串行回退。八条真实记录的耗时对照是单次工程实验，八条最终均进入复核，不能据此报告语义准确率或全量提速比例。向量召回的增益和独立标注评测仍待验证。

重新生成示例并验证：

```bash
python -m pip install -e .
python scripts/build_showcase_demo.py
node --check showcase/app.js
node --check showcase/run.js
node --test scripts/test_showcase.cjs
```

本地预览：

```bash
python -m http.server 8787 --bind 127.0.0.1 --directory showcase
```

浏览器打开 http://127.0.0.1:8787/ 。GitHub Pages 的项目子路径由相对资源链接支持，不需要构建器。

## 发布与更新

仓库的 Settings → Pages → Build and deployment → Source 选择 GitHub Actions，然后运行 `Deploy project page` 工作流。之后修改页面或处理逻辑并推送 main 会重新生成合成示例、运行页面检查并发布。工作流仅上传 `showcase` 目录。

更新汇总快照时，需要核对[处理源码版本中的流程说明](https://github.com/chaomacv/beijing-enterprise-intelligence/blob/57748c4c4086432c4b129a0fee059018a1d6a4c1/docs/full_corpus.md)、私有运行验收和汇总字段口径。只有实际完成运行且总对账通过后，才设置完成状态、`final_audit_passed` 和 `final_counts`；独立语义准确率另作评测。禁止加入真实记录、模型输入或回复。当前合成案例中的“来源覆盖未知”“身份暂定”“拟议状态”应继续保留。
