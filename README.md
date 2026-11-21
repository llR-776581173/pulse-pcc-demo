# Pulse 决策工作台 · PCC Habit Atlas（R4 验收通过版）

> **这是可交互的正式成品，不是静态页、不是截图。**
> 本仓库包含完整的 Python 后端服务、R4 重构后的前端页面、17MB 合成数据集、持久化状态机快照与审计记录，以及全部验收文档。
> 启动后在本机 `8100` 端口运行，四个视图、筛选联动、阈值/预算重算、客户「沉寂→预警→回流」时间轴都能亲手点击。

---

## 一、30 秒启动（验收必读）

### 环境要求
- **Python 3.9+**（仅使用标准库，**不需要 pip install 任何依赖**）
- 浏览器：Chrome / Edge 任意现代浏览器
- 无需数据库、无需 Node、无需网络

### Windows（最简单）
双击仓库根目录的 **`run.bat`**，或在 CMD / PowerShell 中执行：

```bat
cd /d <本仓库目录>
run.bat
```

### macOS / Linux
```bash
cd <本仓库目录>
bash run.sh
```

### 通用手动命令（等价）
```bash
# Windows CMD
set PYTHONUTF8=1
python pulse_app.py 8100

# macOS / Linux
PYTHONUTF8=1 python3 pulse_app.py 8100
```

### 打开页面
服务启动后，在浏览器打开：

```
http://127.0.0.1:8100/
```

> Windows 请务必带上 `PYTHONUTF8=1`（`run.bat` / `run.sh` 已自动设置），否则 CSV 中文可能乱码。
> 端口由命令行参数决定：`python pulse_app.py 8100` 即 8100；不传参数默认 8000。
> 数据自动从仓库内的 `data/` 目录读取（优先级：`PULSE_DATA` 环境变量 → 仓库 `data/` → 旧本机绝对路径），**克隆下来无需配置路径**。
> 按 `Ctrl+C` 停止服务。

---

## 二、在线活系统（无需本地启动，可直接点）

已把同一套完整后端整包部署，可直接交互验收：

```
https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR
```

> 这是跑在云端的 Python 活系统（含全部 API 与重算能力），**不是静态快照**。
> 本地 8100 与云端是两个独立实例，互不共享状态；在云端改阈值会写入云端自己的规则版本文件，不会污染本地仓库。

---

## 三、进页面后能点什么（四个视图）

左侧导航可折叠，菜单高亮为 PCC 暖棕：

| 视图 | 主要内容 |
|---|---|
| **营销总览** | 6 状态分布环形图与清单、状态转移热力矩阵、预警提前量卡（mean 5.2 天）、六决策出口漏斗、预算覆盖率 42.8% |
| **客户案例演示** | A / B / C 三组预置案例，本页筛选联动；点任一客户展开完整生命周期时间轴，含「沉寂 → 预警 → 回流」弧线（A 组首位 `C02186` 有 26 次回流弧线） |
| **营销审批记录** | 规则版本变更留痕、审批汇总表，页载即自动填充 |
| **规则阈值配置** | 13 个可调参数，填写审批人与理由后「应用并重算」，触发全链路重算并递增规则版本 |

关键交互：改阈值 / 预算后点「应用并重算」→ 状态机、KPI、案例池、决策出口全部重算；首屏 KPI 无需手动触发，加载即填充。

---

## 四、验收脚本（拿到仓库可自行复跑）

> 全部在 `PYTHONUTF8=1` 下执行；`--http` 模式需先启动服务。

```bash
# 1) 原始决策逻辑基线
PYTHONUTF8=1 python selftest.py
# 期望：18/18 checks passed

# 2) 生命周期状态机
PYTHONUTF8=1 python selftest_lifecycle.py
# 期望：21/21

# 3) 演示案例探针
PYTHONUTF8=1 python demo/demo_probe.py
# 期望：5/5

# 4) 全量验收（另开一个终端先启动 python pulse_app.py 8100）
PYTHONUTF8=1 python demo/acceptance_check.py --http --base=http://127.0.0.1:8100
# 期望：40/40 ALL GREEN
```

验收留痕见 `demo/acceptance_R4_final.txt`、`demo/acceptance_last.json` 与 `demo/docs/12_Round4_前端重构验收报告.md`。

---

## 五、目录结构

```
├── pulse_app.py            # HTTP 服务与全部 API（main: python pulse_app.py 8100）
├── pulse_core.py           # 决策引擎 / 六出口分类
├── pulse_state.py          # 六状态生命周期状态机、案例池、时间轴
├── rule_config.py          # 13 个规则参数、版本与变更日志
├── selftest.py             # 18/18 原始回归基线（锁定，勿改）
├── selftest_lifecycle.py   # 21/21 状态机回归
├── run.bat / run.sh        # 一键启动 8100
├── static/
│   ├── demo_workspace.html # ★ R4 正式成品页（四视图、暖棕奶杏、PCC logo）
│   ├── img/pcc_logo.svg    # 官方 logo
│   └── ...                 # 历史版本页面（保留作材料）
├── data/                   # 8 个合成数据 CSV（17MB）
├── audit/                  # 状态快照、64,887 行转移日志、决策日志、审批记录
├── demo/
│   ├── acceptance_check.py / demo_probe.py
│   ├── acceptance_R*.txt / acceptance_last.json
│   └── docs/               # 00 基准 + 01~12 全部文档、话术、操作脚本、验收报告
└── docs/ORIGINAL_README.md # 项目原始说明（完整保留）
```

---

## 六、口径与合规须知（对外展示前请确认）

1. **数据为合成数据集**，用于演示，不代表 Pacific Coffee 真实经营结果；对外表述请勿写成真实业绩。
2. 页面左上角为 **Pacific Coffee 官方 logo**，公开仓库 / 公开展示涉及商标使用授权，请先取得许可。
3. 正式上线前需业务校准的 4 个核心口径（消费间隔分层、流失判定时长、预警提前天数、活跃分母口径）在演示版使用临时默认值，登记见 `demo/docs/02_口径占位登记表.md`；发送通道未接入（OPT-03 作为合规现状记录）。
4. 侧栏底部标注「内部营销工作台」，如要公开请自行评估是否调整。

---

## 七、技术说明

- 纯 Python 标准库 `http.server.ThreadingHTTPServer`，绑定 `127.0.0.1`，无第三方依赖。
- 前端为单文件 `static/demo_workspace.html`，`const API=''` 全部走相对路径，因此本地 8100 与云端部署共用同一份前端。
- 状态机为 append-only 转移日志，`CHURNED` 不直接复活；六状态与价值分层分离；`decision_log` / `state_transition` 分表。
- `00_演示版范围与架构.md` 为需求基准，`selftest.py` 18/18 为回归基线，二者在 R2/R3/R4 全程零改动。

---

## 八、R5 修复（在线卡死 + 配色）

- 首屏不再等待案例池：`/api/lifecycle/cases?limit=8` 把 828KB 响应降为 4.2KB，案例改为后台预取 + 加载态提示，**首屏 160ms 就绪**，慢后端下也不会「一直不动」。
- 配色统一为**低饱和奶棕**：去掉原五色系里的蓝色 DOWNPOUR 与多色语义色，六状态 / 六出口 / pills 全部改为同一棕系明度阶梯；侧栏仍为低饱和奶棕渐变。
- `/api/lifecycle/cases` 的 `limit` 为可选参数，**不传仍返回全量**（A 3058 / B 1607 / C 188），不影响任何验收 CASE。
- 复验：真实浏览器 24/24、selftest 18/18、lifecycle 21/21、probe 5/5、acceptance 40/40 ALL GREEN。详见 `demo/docs/13_Round5_在线卡死与配色修复说明.md`。

---

## R6 · 五原色卡 + 四视图业务优化（当前版本）

本轮**只改前端** `static/demo_workspace.html`（CSS / 文案 / 前端交互），后端状态机、计算逻辑、
持久化数据、`demo/docs/00` 基准、`selftest.py` 基线、全部 ID / JS 函数名 / 接口地址均未改动。

- **配色**：严格五原色卡 `#E7CFB8` 浅奶杏 / `#BD8D63` 榻榻米棕 / `#8A5A3C` 深木棕 /
  `#3A2E2D` 深炭棕 / `#43718E` 灰蓝（≤5% 小面积点缀）；85% 暖棕 + 10% 深棕 + 5% 蓝；
  左上角官方红色 logo 原样保留。
- **营销总览**：5 张 KPI 卡（含「平均预警提前 5.2 天」灰蓝核心价值卡）、预算结论条
  「当前预算可覆盖 42.8% 高危客户，对应 308 人」、筛选栏标注「仅作用于当前视图」。
- **流失预警客户池**：菜单更名，A/B/C 改中文（已回流验证客户 / 高危预警客户 / 健康活跃客户），
  新增 3 个前端筛选，时间轴三色区分正常消费 / 触发预警 / 回流成功，首屏 8 位完整回流弧线。
- **营销审批记录**：顶部 4 张汇总小卡 + 表格下方效果闭环总结。
- **规则阈值配置**：13 个参数问号 tooltip + 重算完成后真实前后数值对比弹框。

**验收**：真实浏览器 38/38 PASS；`selftest.py 18/18`、`selftest_lifecycle.py 21/21`、
`demo_probe.py 5/5`、`acceptance_check.py --http 40/40 ALL GREEN`。
详见 `demo/docs/14_Round6_前端优化验收报告.md`。

### 启动（不变）

```bash
set PYTHONUTF8=1          # Windows cmd；Git Bash / macOS / Linux 用 export PYTHONUTF8=1
python pulse_app.py 8100  # 或 Windows 双击 run.bat；macOS/Linux 执行 bash run.sh
```

浏览器打开 `http://127.0.0.1:8100/`。

在线活系统（无需本地启动）：`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`

---

## 时间轴浏览体验优化（当前版本增量）

单客户状态时间轴**不做分页**，但控制了长度、优化了浏览体验，仍只改 `static/demo_workspace.html`：

- **固定高度 + 内部独立滚动**：`.tl-scroll` 上限 360px（小屏 280px），`overflow-y:auto`，
  时间轴再长也不撑高整页；实测展开全部后整页高度 `1315 → 1315`。
- **默认只展示关键节点**：触发预警 / 回流成功 / 状态变更；普通日常消费默认收起并提示「已收起 N 条」。
- **「仅看关键事件」开关 + 「展开全部交易」按钮**：两者联动，一键过滤 / 一键看全，切换客户自动重置默认态。
- 不新增接口、不新增分页、不改后端与持久化数据；`showTimeline(cid)` 缓存一次数据后本地重渲染。

验收：真实浏览器 **54/54 PASS**；全套回归 `18/18 · 21/21 · 5/5 · 40/40 ALL GREEN`。
详见 `demo/docs/15_时间轴浏览体验优化验收报告.md`。

## R7 · 商用化打磨（当前版本）

- **导航扩为 7 大模块**：营销总览 / 流失预警客户池 / 干预效果复盘 / 营销审批记录 / 规则阈值配置 / 单客户全景画像 / 数据口径与帮助
- **干预效果复盘**：投入产出比、分门店排行、面额券对比、审批月度趋势、AI 生成月报（可复制）
- **单客户全景画像**：AI 推荐（价值/风险/券种/回流概率）、预警原因、发券记录、回流追踪
- **AI 智能问答助手**：右下角悬浮，基于当前接口数据作答（演示级前端预置，预留企业内部大模型接入能力）
- **图表色系统一**：健康类棕系阶梯、风险类灰蓝深浅；客户列表新增沉寂天数与价值等级列；审批页口径纠偏为「累计验证回流客户」
- 验证：Edge headless 65/65 PASS；全套回归 18/18 · 21/21 · 5/5 · 40/40 ALL GREEN；后端与基线零改动

## R8 · 帮助页高度控制 + 基础响应式（当前版本）

工作量评估：两条需求都不大、共用同一套 CSS 断点，**本轮一起做掉**（未暂缓响应式）。仅改 `static/demo_workspace.html`：

- **帮助页四板块**：新增 `.hlp-scroll` 统一最大高度 + 内部独立滚动，标题固定在滚动层外；桌面 340px / 平板 290px / 手机 240px，实测 4/4 板块可独立滚动，帮助页不再撑出长页面。
- **窄屏抽屉**：≤1000px 侧栏 `translateX(-100%)` 收起、主内容全宽、顶部新增汉堡；抽屉可展开，点菜单 / 点遮罩自动收起；宽屏折叠语义保留。
- **单列与横滚**：≤700px 栅格统一单列；12 个宽表 / 图表容器加 `.scroll-x` 横向滚动；`#configform` 刻意不加，护住参数问号气泡；`.topbar` 裁剪装饰花越界的 11px，三视口无横向溢出。
- **本轮 QA 顺带修好**：R6 后置 `.g5/.mini.four` 覆盖响应式降列（已把 R8 media 块移到样式表末尾）、手机帮助页堆叠过高、装饰 SVG 横向溢出。

验收：真实浏览器 Edge headless 三视口 **101/101 PASS**（桌面 30 / 平板 34 / 手机 37）；全套回归 `18/18 · 21/21 · 5/5 · 40/40 ALL GREEN`；`00` 与 `selftest.py` 锁定零改动、主仓库 `v1.0 / log=0`。详见 `demo/docs/17_Round8_帮助页高度与响应式适配验收报告.md`。

### 启动（不变）

```bash
set PYTHONUTF8=1          # Windows cmd；Git Bash / macOS / Linux 用 export PYTHONUTF8=1
python pulse_app.py 8100  # 或 Windows 双击 run.bat；macOS/Linux 执行 bash run.sh
```

浏览器打开 `http://127.0.0.1:8100/`。
在线活系统（无需本地启动）：`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`
