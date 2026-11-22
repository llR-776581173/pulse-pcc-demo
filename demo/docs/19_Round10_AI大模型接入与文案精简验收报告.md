# 19 · Round10 AI 大模型接入与页面文字精简验收报告

> 日期：2026-11-22 · 范围：**仅** `static/demo_workspace.html`（前端页面 / CSS / 前端 JS）
> 红线遵守：后端状态机、决策计算、数据口径、接口地址、持久化数据、`00_演示版范围与架构.md`
> 需求基准、`selftest.py` 与其余验收基线 **零改动**；五原色卡不新增、不删减；
> 全部原有 ID / JS 函数名 / CASE 数据保留（`#rver`、`#ovwindow` 保留为 hidden 锚点）。

## 一、需求

| # | 需求 | 落地 |
|---|---|---|
| 一 | AI 助手从前端预设规则升级为 LLM 驱动的真实问答；回答必须基于系统真实数据、避免数据幻觉；保留快捷问题并支持自由输入；仅新增前端调用逻辑 | ✅ |
| 二 | 删除全部冗余说明文字（编号副标题 / 右上角小字 / 底部注释 / 规则版本标识 / 筛选提示 / 主标题副标题） | ✅ |
| 三 | 客户状态大盘右侧状态条改为两列纵向（左：进店未消费→首购激活→活跃复购；右：沉寂预警→深度沉寂→判定流失） | ✅ |
| 四 | UI 细节持续打磨（卡片间距、文字层级、圆角阴影、交互反馈），不改动功能与数据逻辑 | ✅ |

## 二、改动清单（唯一文件）

### 1. 需求二 · 页面文字精简

| 类别 | 删除/处理方式 | 数量 |
|---|---|---|
| 模块编号副标题 `汇总图表 / 01` 等 | 删除 `.eyebrow` DOM（静态 21 处）+ 配置页 JS 拼接的「最近调整」 | 22 |
| 模块右上角小字标注 | 删除 `<span class="hint">`（20 处）；`#tlsub` 保留为功能性数据锚点（运行时显示当前客户 ID，非说明文字） | 20 |
| 模块底部注释小字 | 矩阵底部口径说明、审批页口径说明、门店排行口径、面额对比补充说明、月报按钮旁说明、复盘趋势图底部说明、画像推荐卡「前端固定规则生成」说明 | 7 |
| 右上角「规则版本 v1.0」 | 删除 `.chip` 视觉；`<b id="rver" hidden>` 保留（JS 写入与验收信号依赖） | 1 |
| 筛选栏提示「筛选仅作用于当前视图…」 | 删除 `.scope`（overview 保留 hidden `#ovwindow`，其余 4 页 + profile/help 引导共 6 处） | 6 |
| 主标题旁小字副标题 | 删除 `#viewdesc` DOM；`switchView()` 加空值保护；`VIEW_META.desc` 7 项清空 | 1 + 7 |
| 帮助页 AI FAQ | 更新为「可接入大模型 / 回答一律以工作台真实数据为唯一依据 / 不填时用内置数据问答」 | 1 |

删除后全页 `.eyebrow = 0`、`.scope = 0`、`.hint` 仅剩 `#tlsub` 一个数据锚点、`class="note" = 0`；
剩余 6 处 `.muted` 均为数据展示或空状态功能文案（如「共 N 位 · 显示前 8」「该客户无关键事件记录」），非说明性标注。

### 2. 需求一 · AI 大模型接入（仅前端调用逻辑）

**面板 HTML**：新增「设置」按钮、`#ai-mode` 模式徽标（内置数据问答 / 大模型 · 实时数据）、
`#ai-cfg` 配置区（接口地址 / API Key / 模型名称）、保存与「恢复内置」；保留 `#ai-fab`、`#ai-panel`、
`#ai-msgs`、`#ai-chips` 快捷问题、`#ai-q` 自由输入。

**JS 调用链**（替换原预置规则块，函数名与调用点保持兼容）：

- `aiCfg() / aiCfgSave() / aiEnabled() / aiSyncMode() / aiToggleCfg() / aiSaveCfg() / aiClearCfg()`
  — 配置存本机 `localStorage['pulse.ai.cfg']`，**不写后端、不落仓库**。
- `aiSnapshot()` — 把 `LC_DATA` / `BUDGET_DATA` 中已加载的真实值汇总为唯一事实来源：
  评估截止、在册会员、六状态分布与占比、沉寂合计、平均预警提前量、观察窗/结果窗、
  案例池三组人数、预算覆盖率与投放/需求/未覆盖人数、额度与挽回消费代理、规则版本、状态转移矩阵。
- `aiSystem()` — 系统提示词强制四条护栏：只依据工作台真实数据、禁止编造/估算/外推、
  数据中没有的信息明确回答「工作台当前没有这项数据」、引用数值必须与数据完全一致（≤6 句、中文）。
- `aiLLM(q)` — OpenAI 兼容 `POST {base}` `/chat/completions`，`Bearer {key}`、
  `model` 可配，`temperature 0.2`、`max_tokens 600`，`AbortController` 30s 超时；
  携带最近 6 条上下文 + `system` + 本轮问题。
- `aiAsk(q)` — 有配置走大模型；**无配置 / 模型不可用自动降级**到 `aiAnswer(q)`（原预置规则完整保留），
  并在回答尾部提示「模型服务本次没有响应，已切换为内置数据问答」。
- `aiGreet()` 保留 6 个预设快捷问题，`aiSend()` 支持自由输入回车/点击发送；
  `aiRender()` 统一转义与换行渲染。

> API Key 由使用者后续在助手「设置」中填写即可启用，无需改代码。未填 Key 时系统仍可正常问答（内置数据问答）。

### 3. 需求三 · 状态条两列纵向（仅 CSS）

```css
.state-grid{grid-auto-flow:column;grid-template-rows:repeat(3,minmax(0,1fr))}
```

原 `grid-template-columns:repeat(2,...)` 与 6 项 DOM 顺序（R9 生命周期顺序）均不变，
仅把填充方向由「行优先」改为「列优先」：前 3 项落左列、后 3 项落右列，自上而下递进。
色值、数据、`STATE_ORDER`、环形图/图例顺序、筛选联动全部零改动。

### 4. 需求四 · UI 质感打磨（仅 CSS，置于 R8 `@media` 之前）

卡片/KPI 圆角 16px、两级分层阴影、`.grid` 间距 14px、`h3`/KPI 字重与字距微调、
`.btn / select / .nav-item / .ai-chips / .srow / .ai-gear` 统一 `.18s` 过渡、
`:hover` 阴影与 `:focus-visible` 描边、图例行距；AI 面板新增模式徽标/设置按钮/配置区/思考态/降级提示样式。
全部沿用五原色变量与近白中性色，**未新增任何彩色**；R8 全部 `@media` 仍在样式表末尾，覆盖关系不变。

## 三、验证结果

### 真实浏览器（Edge headless，隔离 8101 服务，同源内联断言页）

| 视口 | 断言 | 结果 |
|---|---|---|
| 桌面 1440×900 | 56 | **56/56 PASS** |
| 平板 768×1024 | 58 | **58/58 PASS** |
| 手机 390×844 | 58 | **58/58 PASS** |
| **合计** | **172** | **172/172 PASS，0 FAIL** |

关键证据（三视口一致）：

- 文案：`.eyebrow=0`、`.scope=0`、`.card > h3 .hint` 仅 `#tlsub`、`#rver`/`#ovwindow` computed `display:none`、
  `#viewdesc` DOM 不存在、可见区域无「汇总图表 / 筛选仅作用于 / 演示级 / 口径说明：」等残留；七视图切换无空引用异常。
- 两列：前 3 项同 x 且 y 递增、后 3 项同 x 且 y 递增、右列 x > 左列 x，名称仍是生命周期顺序。
- AI：配置三输入框 / 模式徽标 / 设置按钮齐全；18 个 AI 函数链齐全；
  `aiSnapshot()` 含六状态真实值与预算/预警字段；`aiSystem()` 含「禁止编造 / 工作台真实数据 / 不得猜测」护栏；
  无 Key 默认「内置数据问答」；快捷问题与自由输入均触发真实问答、回答含真实数字；
  设置面板可展开、保存后切换「大模型 · 实时数据」、配置仅存 `localStorage`、「恢复内置」可用。
- 零回退：五原色变量、导航 7 项、KPI 5 卡、`tl-scroll` 360px、帮助页 4 个 `hlp-scroll`、
  `scroll-x >= 10`、`topbar` 装饰裁剪、抽屉元素、R9 环形图/图例/矩阵表头/下拉顺序与色阶、
  筛选「判定流失」只剩 1 行且可恢复 6 行。
- 三视口：整页无横向溢出；窄屏汉堡展开抽屉、遮罩点击关闭抽屉；flash 无加载失败。

### 全套回归（主仓库 + 8100 活系统）

- `selftest.py` **18/18** · `selftest_lifecycle.py` **21/21** · `demo/demo_probe.py` **5/5**
- `demo/acceptance_check.py --http --base=http://127.0.0.1:8100`
  **40 PASS / 0 FAIL / 0 SKIP → ALL GREEN**（E01 运行中服务已加载当前磁盘代码 PASS）
- 静态检查：`node --check` 通过、违禁字样 0、五原色 hex 全部在位、JS 依赖函数（`LC_DATA` /
  `BUDGET_DATA` / `STATE_ORDER` / `ST` / `hkd` / `esc` / `flash` / `CUR`）全部存在
- 基线：`/api/config` 仍为 `v1.0 / log=0`；`00_演示版范围与架构.md` 与 `selftest.py` 零改动
- 8100 服务返回页面已含 `ai-cfg` / `R10 · AI` / `grid-auto-flow:column`，确认活系统加载改动后代码

## 四、交付与启动

```bash
set PYTHONUTF8=1          # Windows cmd；Git Bash / macOS / Linux 用 export PYTHONUTF8=1
python pulse_app.py 8100  # 或双击 run.bat / 执行 bash run.sh
```

浏览器打开 **`http://127.0.0.1:8100/`**；在线活系统（无需本地启动）：
**`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`**

源码仓库：`https://github.com/llR-776581173/pulse-pcc-demo`。离线兜底：`pulse-github.zip` / `pulse-github.bundle`。

AI 大模型启用方式：打开右下角「AI 助手」→「设置」→ 填写接口地址（OpenAI 兼容 `/chat/completions`）、
API Key、模型名称 →「保存」，模式徽标变为「大模型 · 实时数据」即生效；不填则使用内置数据问答。

## 五、已知边界（如实记录）

- 本轮为**纯前端改动**：未新增任何后端接口、未改状态机 / 决策 / 数据口径 / 持久化数据 / 验收基线。
  模型调用由浏览器直连使用者配置的 OpenAI 兼容服务，配置仅存本机浏览器 `localStorage`。
- 用户后续提供 API Key 后无需改代码；若服务地址存在跨域限制，需该服务允许来自工作台域名的 CORS 请求。
- 回答的事实来源限定为 `aiSnapshot()` 汇总的已加载数据（大盘/预算/预警/案例池/转移矩阵），
  不包含单客户逐笔明细；单客户分析仍走「流失预警客户池」时间轴与画像模块。
- R7 的「AI 推荐卡」「生成月报」仍为原有前端能力，本轮按要求只升级右下角问答助手，未改动这两个场景的功能逻辑。
- `#rver` / `#ovwindow` / `#tlsub` 保留为隐藏锚点或功能性数据元素，属 JS 与验收信号依赖，非可见说明文字。
