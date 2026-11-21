# 17 · Round8 帮助页高度控制与基础响应式适配验收报告

> 日期：2026-11-22 · 范围：**仅** `static/demo_workspace.html`（CSS / 前端布局 / 前端交互）
> 红线遵守：后端逻辑、状态机、持久化数据、接口地址、`00` 需求基准、`selftest.py` 与其余基线
> **零改动**；全部原有 ID、JS 函数名、CASE 数据保留；页面违禁字样为零；五原色卡不新增、不删减。

## 一、需求与工作量评估

| # | 用户诉求 | 工作量评估 | 结论 |
|---|---|---|---|
| 1 | 「数据口径与帮助」四板块统一最大高度、内部独立滚动，避免页面过长 | 小：新增一个 `.hlp-scroll` 滚动层，四个板块各包一层内容区 | 本轮完成 |
| 2 | 基础响应式适配（平板 + 手机）：窄屏侧边栏收起 + 顶部汉堡展开、卡片单列、宽表/图表横向滚动 | 小到中：在已有响应式基础上补抽屉双态、栅格断点与 `.scroll-x` 容器，无需改渲染逻辑 | 本轮一起完成 |

评估结论：**两条都不大，且共用同一套 CSS 断点，无新增接口、无后端改动、无渲染函数改写**，因此本轮一次性做掉，未按「暂缓响应式」拆分交付。

## 二、改动清单（唯一文件 `static/demo_workspace.html`）

### 需求 1 · 帮助页四板块独立滚动
- 新增 `.hlp-scroll`：`max-height` + `overflow-y:auto` + `overscroll-behavior:contain`，细滚动条沿用榻榻米棕 / 浅奶杏（不引入新色）；参考已上线的 `.tl-scroll` 做法。
- `renderHelp()` 四个板块的**内容区**各包一层 `.hlp-scroll`，标题（`h3`）留在滚动层外，滚动时标题不动。
- 三档统一上限：桌面 **340px** / 平板 **290px** / 手机 **240px**；四板块同屏一致，实测 `scrollHeight > clientHeight` 的板块 4/4 可独立滚动。
- 效果：桌面 `helpbodyH=880`；平板 1176；手机 1372，均受控；帮助页与配置页切换时整页高度差 203px（未撑高整页）。

### 需求 2 · 基础响应式（平板 + 手机）
- **抽屉侧边栏**：≤1000px 时侧栏 `translateX(-100%)` 收起、主内容 `margin-left:0` 全宽；顶部新增汉堡按钮 `.mtoggle`；新增 `.nav-backdrop` 遮罩。
- `toggleNav()` 改为双态（函数名与调用点不变）：宽屏保留原有 `nav-collapsed` 折叠；窄屏切 `nav-drawer-open` 抽屉。点任意菜单项（`switchView()`）或点遮罩自动收起抽屉。
- **栅格单列**：≤700px 时 `.g4/.g3/.g2/.g5/.g21/.mini/.mini.four` 统一 `1fr`；≤1000px 时 KPI 栅格降为 2 列。实测手机 KPI `cols=1 (1fr)`、平板 `repeat(2, ...)`。
- **宽表 / 图表横向滚动**：12 个动态容器加 `.scroll-x`（审批表、矩阵、漏斗、预算、复盘、画像、案例列表等），手机下 `table.tbl{min-width:480px}`，容器可横滑且不撑破页面；`#configform` **刻意不加** `scroll-x`，护住 13 个参数问号气泡的绝对定位。
- **顶部装饰层裁剪**：`.topbar{overflow:hidden}` 裁掉右上角装饰花 SVG 越界的 11px，修复三视口共有的横向溢出。

### 本轮 QA 发现并修复的 3 个真实问题
1. **CSS 层叠顺序**：R6 组件样式里的 `.g5{repeat(5,...)}` / `.mini.four{repeat(4,...)}` 写在 R8 响应式 media 之后，同特异性下把窄屏降列规则覆盖掉了 → 将 R8 全部 `@media` 块整体移到样式表**末尾**，确保响应式规则最终生效。
2. **帮助页堆叠过高**：手机四板块单列堆叠后 `helpbodyH=1532` → 收紧手机上限至 240px，实测降到 **1372**。
3. **11px 横向溢出**：定位到 `.floral-top` 装饰 SVG（`right:-26px`），三视口均让 `documentElement.scrollWidth` 多 11px → `topbar` 裁剪后三视口 `scrollWidth <= innerWidth`。

> 说明：`展开后侧栏归位` 在首轮 QA 报 `-238`，经诊断是 `--virtual-time-budget` 下 CSS transition 不随虚拟时间推进，读到的是过渡起始值；禁用过渡后目标态为 `matrix(1,0,0,1,0,0)`。属**验证方法**问题，产品 CSS 与真实浏览器行为正确，验证脚本已改为读目标态。

## 三、验证结果

### 真实浏览器（Edge headless，隔离 8101 服务，同源内联断言页）
| 视口 | 实测 innerWidth | 断言 | 结果 |
|---|---|---|---|
| 桌面 | 1410 | 30 | **30/30 PASS** |
| 平板 | 738 | 34 | **34/34 PASS** |
| 手机 | 492 | 37 | **37/37 PASS** |
| **合计** | — | **101** | **101/101 PASS，0 FAIL** |

覆盖：五原色变量不回退、7 项导航、关键容器齐全、KPI 5 卡、`tl-scroll` 保留、四板块统一上限与独立滚动、标题在滚动层外、帮助页高度受控、`scroll-x` 容器 12 个、审批表横滚、栅格单列/降列、汉堡显示/隐藏、抽屉展开归位、遮罩显隐、点菜单/点遮罩收起、整页无横向溢出、flash 无加载失败、R6/R7 功能不回退。

### 全套回归（主仓库 + 8100 活系统）
- `selftest.py` **18/18**
- `selftest_lifecycle.py` **21/21**
- `demo/demo_probe.py` **5/5**
- `demo/acceptance_check.py --http` **40 PASS / 0 FAIL / 0 SKIP → ALL GREEN**（E01 运行中服务已加载当前磁盘代码）
- 基线：`/api/config` 仍为 `v1.0 / log=0`；`00_演示版范围与架构.md` 与 `selftest.py` 指纹锁定、零改动；`git diff` 仅 `static/demo_workspace.html` 与 `demo/acceptance_last.json`（验收留痕时间戳）。
- 写入型重算验证全部在隔离目录完成，主仓库审计留痕未被污染。

## 四、交付与启动

```bash
set PYTHONUTF8=1          # Windows cmd；Git Bash / macOS / Linux 用 export PYTHONUTF8=1
python pulse_app.py 8100  # 或双击 run.bat / 执行 bash run.sh
```

浏览器打开 **`http://127.0.0.1:8100/`**；在线活系统（无需本地启动）：
**`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`**

源码仓库：`https://github.com/llR-776581173/pulse-pcc-demo`（本轮同步后为最新 commit）。
离线兜底：`pulse-github.zip` / `pulse-github.bundle`（本轮同步）。

## 五、已知边界（如实记录）

- 响应式定位为「基础适配」：覆盖 1410 / 738 / 492 三档常见宽度，未做触控手势侧滑、未做超小屏（<360px）专项断点。
- AI 助手仍为 R7 的前端预置规则 + 实时数据计算，未接入外部大模型；后端接入方案待后续评审。
- 所有数字仍来自合成演示数据集与后端接口实时返回，正式接入门店真实数据后口径不变。
