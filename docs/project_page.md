# Project Page

地址：https://chaomacv.github.io/beijing-enterprise-intelligence/?view=compact#explorations

页面沿用深色首屏向白色过渡、直角笔记本卡片和左上角页签。桌面中央显示三张完整卡片，两侧有限露出相邻卡片；八张首尾循环，卡片可移入扩大阅读器并保留交互状态。键盘、触摸、悬停、后台及减少动态效果的处理保持不变。

## 当前八张卡片

1. 文件概览：全批逻辑文件的格式和解析状态。
2. 事件分类：全批许可相关十类细分与全部18类事件，可切换事件阶段、关联画像数和对数刻度。
3. 内容去重：1,440,619 条复杂来源记录对应 388,349 个内容代表，所有原始位置保留。
4. 方法说明：读取、发现价值、效率、可信度、业务应用五个问题，含输入输出和概念代码。
5. 画像网络：真实全量标签组合的二维／三维力导向图，D3 Category10 配色。
6. 企业画像：全批真实数量；下方个体证据教程继续明确使用合成素材。
7. 执行进度：真实观测快照，末点为本批完成汇总，非企业业务时间分布。
8. 层级探索：三种真实计量口径的 Zoomable Sunburst。

## 旭日图

`event-sunburst.js` 使用本地固定版本 D3 7.9.0，参考 [D3 Zoomable Sunburst](https://observablehq.com/@d3/zoomable-sunburst) 的分区布局和750ms坐标插值。每次只显示两层，点击分支进入下级，点击中心或面包屑返回。扇区可键盘激活，悬停提示完整名称、数量、占父级比例和路径；筛选只强调分支，不改变分母。减少动态效果时直接切换。

| 模式 | 总数 | 层级 |
| --- | ---: | --- |
| 原始附件 | 5,200 | 实际格式 → 官网所属部门 → 数据集 |
| 逻辑文件 | 11,701 | 文件类型 → 生成方式 → 匿名具体文件编号 |
| 业务记录 | 43,653,625 | 官网业务主题 → 互斥事件类别 → 真实阶段或处理去向 |

附件部门全部匹配官网目录。逻辑文件末层一对一计数，不公开文件名或私有路径。业务记录每条只计一次，多事件类别单列，包含排除、未提取事件和待复核去向。末层阶段不冒充未经核实的业务子类。等面积环带使同一聚焦范围内同层扇区面积与数量成正比；内层和子层不能重复相加。

服务器生成：`scripts/build_exploration_hierarchies.py --run-dir PRIVATE_RUN --snapshot-dir PRIVATE_SNAPSHOT --output-dir PUBLIC_EXPORT`。输出 `assets/event-hierarchy.json` 和 `sunburst-attachments.json`、`sunburst-logical.json`、`sunburst-records.json`，清单含每份数据哈希。`scripts/build_event_hierarchy.py` 只验证现有发布数据，不再生成历史子集。

## 全量真实网络

`assets/real-network.json` 从 `classified_profile_tags` 与全量主体表统计，5,202,714 个画像精确分为1,753个完整标签组合。1,665,951个没有事件标签的画像也进入计数。保留临时身份数量，未抽样、未虚构企业；组合节点不是单家企业，公开数据不包含企业标识。

默认采用标签概览：按固定类别顺序的前两项可比较观察标签，将所有完整组合精确归入127个概览分组，全部5,202,714个画像计数继续保留。概览边为成员完整标签集合之间、按画像数量加权的平均Jaccard，每组取2个近邻后取并集（默认阈值0.35）。分组前缀不是标签重要性排序，成员的其他标签继续保留。

二维／三维选择保持可见；完整组合、视图、范围、类别、阈值、常驻标签及图例收进“更多选项”。默认白底、Category10圆点和细灰线，不常驻显示节点文字；悬停查看标签，选择节点查看分组说明。完整组合仍可切换到1,753个节点。

`network-model.js` 计算分组、排除复核维度的二值Jaccard和每组2近邻的并集。18类及许可相关十类可以切换，切换范围后重新按选定标签集合精确聚合，总画像数不变；类别筛选显示当前覆盖数与完整分母。阈值和6近邻规则仅定义展示边，不推断业务联系或信用。

`network-worker.js` 在Worker内计算真实2D或3D力模拟，页面线程保持可操作。`enterprise-network.js` 用SVG显示灰色连线、白边圆点及 Category10 配色，支持节点拖动、平移、滚轮／按钮缩放和复位。三维拖动空白旋转，Shift拖动平移，键盘方向键旋转；三维标签按投影位置跟随，坐标轴提供方向参照。额外类别循环使用相同调色板。二维与三维读取同一完整数据。

## 最终汇总与复现

`scripts/sync_final_public.py` 从最终报告和分类修正汇总白名单更新 `run-summary.json`、`gallery-data.json` 和 `final-results.json`。历史 `subset` 字段为兼容接口继续保留，`partial_only=false` 明确当前为全批。`scripts/build_gallery_data.py` 的旧阶段生成器仅用于历史快照，不用于本次最终发布。

实际输出、复核数量与使用边界见[本批最终结果](full_run_results.md)。公开JSON不包含原始单元格、企业身份、服务器连接信息或模型回复。页面不连接私有模型或数据服务。

## 验证与第三方代码

Node测试核对父子数量、模式哈希、记录分母、完整网络组合计数、类别边际数、Jaccard、3D投影及页面契约。GitHub Actions在1440、2048、390及320宽度运行Chromium，验证模式切换、真实下钻、中心返回、网络筛选、二维拖动、三维旋转和阅读器恢复，并保留截图。

D3 7.9.0为ISC许可；d3-force-3d 3.0.6及其binarytree／octree依赖为MIT许可。固定版本代码及许可保存在 `showcase/vendor/`，浏览器不加载远程脚本。参考图形设计来自[D3力导向图](https://observablehq.com/@d3/force-directed-graph/2)，三维模拟接口来自[d3-force-3d](https://github.com/vasturiano/d3-force-3d)。
