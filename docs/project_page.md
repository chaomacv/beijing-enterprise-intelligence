# Project Page

Project Page 源码位于 `showcase/`，部署地址为 https://chaomacv.github.io/beijing-enterprise-intelligence/ 。README 开头提供入口与预览图。

页面以“分散的数据，有据可查的企业情报”为主线，展示文件筛选、结构分块和企业归并的方法选择。视觉参考 Observable 的可探索文档、留白与数据图形；参考 RailMind 和 experience-guided-code-agent 的项目介绍结构。页面代码和图形独立实现，不复制参考站点的代码或资源。

## 页面内容与数据

- `index.html` / `style.css`：中文项目介绍、方法、交互实验、证据追溯、版本进展和复现入口。
- `model.js` / `app.js`：无第三方前端依赖的浏览器交互。抽样和分块实验是原理示意，不报告 token 节省或语义召回率。
- `assets/demo.json`：由仓库现有 Python 规则基线生成，包含 3 份合成文件、5 条记录、2 个暂定企业主体和 3 条事件。
- `assets/project-preview.svg`：README 的独立绘制预览图，图形是方法示意。

所有企业与事实均为虚构。没有把真实业务数据、下载会话、服务器路径、凭据或模型推理日志放入页面。页面不调用模型服务，也不接受业务文件上传。Qwen 方案、已实现功能和待验证能力分别说明；向量召回及复杂文件处理仍属于后续扩展。

重新生成示例并验证：

```bash
python -m pip install -e .
python scripts/build_showcase_demo.py
node --check showcase/app.js
node --test scripts/test_showcase.cjs
```

本地预览：

```bash
python -m http.server 8787 --bind 127.0.0.1 --directory showcase
```

浏览器打开 http://127.0.0.1:8787/ 。GitHub Pages 的项目子路径由相对资源链接支持，不需要构建器。

## 发布与更新

仓库的 Settings → Pages → Build and deployment → Source 选择 GitHub Actions，然后运行 `Deploy project page` 工作流。之后修改页面或处理逻辑并推送 main 会重新生成合成示例、运行页面检查并发布。工作流仅上传 `showcase` 目录。

如未来增加真实效果数据，需要同时公开可核验的来源、运行配置和评测范围；不能将原理演示统计写成全量实验结果。当前页面中“来源覆盖未知”“身份暂定”“拟议状态”均是数据含义，应在更新时保留相应事实边界。
