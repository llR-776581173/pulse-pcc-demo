# 20 · Round11 AI 月报接入大模型与体验优化验收报告

> 日期：2026-11-22 · 范围：**仅** `static/demo_workspace.html`（前端页面 / CSS / 前端 JS）
> 红线遵守：后端状态机、决策计算、数据口径、接口地址、持久化数据、`00_演示版范围与架构.md`
> 需求基准、`selftest.py` 与其余验收基线 **零改动**；五原色卡不新增、不删减；
> API Key 仅存使用者本机浏览器 `localStorage`，不写入代码、不提交仓库、不上传工作台服务端。

## 一、需求

| # | 需求 | 落地 |
|---|---|---|
| 一-1 | 「AI 生成月报」升级接入真实大模型，与右下角 AI 助手**共用同一套 API 配置**（接口地址 / API Key / 模型名称），填一次两边同时生效 | ✅ |
| 一-2 | 二者**共用同一份页面真实数据快照**作为事实依据，遵守**相同的防幻觉规则**，禁止编造数据与结论 | ✅ |
| 一-3 | 未配置 Key、调用失败或网络异常时，**自动降级为现有模板生成**，保证功能始终可用、不影响演示 | ✅ |
| 一-4 | API Key **仅存 localStorage**，绝对不写入代码 / 不提交仓库 / 不上传服务端 | ✅ |
| 二-1 | AI 生成月报弹窗整体放大：放宽宽高、放大正文字号与「复制全文」按钮，风格统一 | ✅ |
| 二-2 | 审批记录、客户列表等表格**表头背景适度加深**，提升长表可读性 | ✅ |
| 二-3 | 「暂无审批发券记录」等**空状态提示文字适度放大** | ✅ |

> 补充：R10 只升级了右下角问答助手，本轮把 R10 报告中「生成月报仍为原有前端能力」这一项补齐；
> R7 的「AI 推荐卡」仍为原有前端能力，本轮未改动其功能逻辑。

## 二、改动清单（唯一文件）

### 1. 需求一 · AI 月报接入大模型（仅前端，与问答助手共用一切）

**共用机制（重构 R10 的 AI 区块，问答侧行为零回退）**：

- `AI_GUARD` — 抽出的**同一套防幻觉护栏常量**（只依据工作台真实数据、禁止编造/估算/外推、
  数据中没有的信息明确回答「工作台当前没有这项数据」、引用数值必须与数据一致、不输出 JSON/原始表）；
  `aiSystem()`（问答）与新增 `aiReportSystem()`（月报）**字面拼接同一份 `AI_GUARD`**。
- `aiFacts()` = `'\n\n【工作台真实数据】\n' + aiSnapshot()` — 两者共用**同一份真实数据快照**，
  `aiSnapshot()` 零改动（六状态分布、预警提前量、预算覆盖率、案例池、转移矩阵等全部来自已加载接口缓存）。
- `aiRequest(messages, maxTokens)` — 抽出**单次大模型请求封装**，问答与月报共用同一份
  `aiCfg()` 配置（本机 `localStorage['pulse.ai.cfg']`）、同一套 `Bearer {key}` / OpenAI 兼容
  `/chat/completions` / `temperature 0.2` / `AbortController` 30s 超时处理。
  `aiLLM(q)` 改为调用 `aiRequest(msgs, 600)`（原问答行为完全不变）；
  `aiMonthlyLLM()` 调用 `aiRequest([月报 system + user], 1200)`。
- 因此**在助手「设置」里填一次配置，问答与月报同时生效**；配置提示、保存提示、帮助页 FAQ 已同步说明。

**月报主入口 `aiMonthly()`（原固定模板抽为 `aiMonthlyTemplate()`，模板正文与数字口径零改动）**：

```
AI_REPORT = aiMonthlyTemplate();        // 先备好降级内容
openModal(..., 'report-modal');         // 立即展示弹窗（模板可见、可复制）
if(!aiEnabled()) return;                // 未配置 Key → 直接用模板，不发任何请求
setMode('大模型 · 正在生成…');
try { AI_REPORT = await aiMonthlyLLM();  // 成功 → 替换正文
      setMode('大模型 · 实时数据'); }
catch { /* 保持模板 */
      setMode('内置模板 · 模型未响应'); }
```

- `AI_REPORT_SEQ` 请求序号防止连续点击时旧响应覆盖新弹窗；`closeModal()` / 重新打开均安全。
- `aiCopy()`（含 `navigator.clipboard` 与 `execCommand` 兜底）零改动，复制内容始终取 `AI_REPORT`，
  模板态与模型态都可用。
- API Key 全程只经 `localStorage` 读写，模型请求由浏览器直连**使用者自行填写**的地址；
  工作台后端接口、仓库代码、服务端均无 Key 落地路径。

### 2. 需求二-1 · 月报弹窗放大（仅 CSS）

`openModal(html, cls)` 新增可选样式类参数（不影响重算对比弹框等既有调用），月报传 `report-modal`：

```css
.modal.report-modal{width:760px;max-width:94vw;max-height:88vh;overflow:auto;padding:26px 28px}
.report-modal .recalc-hd{font-size:18px}
.report-modal .recalc-sub{font-size:12.5px}
.report-modal .ai-report{height:420px;font-size:14px;line-height:1.85;padding:14px 16px}
.report-modal .recalc-foot{display:flex;...}
.report-modal .btn-copy{padding:10px 22px;font-size:14px;border-radius:9px}
```

- 弹窗宽度 520→760px，正文区高度 260→420px、字号 12→14px、行高 1.7→1.85；
  「复制全文」按钮 7px/14px→10px/22px、字号 12.5→14px。
- 新增 `.report-mode` 模式徽标（内置模板 / 大模型 · 正在生成… / 大模型 · 实时数据 /
  内置模板 · 模型未响应），风格与助手 `#ai-mode` 一致，沿用五原色与近白中性色。
- 窄屏 `@media(max-width:700px)` 收敛：`width:94vw`、正文 `height:50vh` / `13px`、按钮 `9px 16px` / `13px`，
  **置于样式表末尾**（R8 全部 `@media` 之后），保证不横向溢出。

### 3. 需求二-2 · 表格表头背景加深（仅 CSS）

```css
.tbl th{background:rgba(189,141,99,.26) → rgba(189,141,99,.46)}   /* 榻榻米棕同一原色，不新增颜色 */
```

`.tbl` 是审批记录、客户列表明细、画像推荐记录等标准数据表；表头底色由 26% 提高到 46%，
与 `#F1E7DA` 数据行分隔更明显，缓解长表格视觉串行。`.matrix th`（状态转移矩阵列标签）保持透明设计不变。

### 4. 需求二-3 · 空状态字号放大（仅 CSS）

```css
.loadbox,.emptybox{font-size:12.5px → 14px}
```

「暂无审批发券记录」「暂无审批记录 · 经理批准后将在此留痕」等空状态与加载态文案统一提升，
`line-height:1.7`、暖棕底色与虚线/实线边框全部不变。

### 5. 一致性文案（无禁词、无开发感标注）

助手配置提示改为「配置仅存本机浏览器 · 问答助手与 AI 月报共用 · 密钥只发往所填模型地址」；
`aiSaveCfg()` 保存提示改为「问答与月报」；帮助页 FAQ 更新为「AI 助手与 AI 月报可信吗？」
并说明共用配置、相同护栏、三种降级；R7 区块注释中过时的「不调用外部大模型接口」同步更正。

## 三、验证结果

### 真实浏览器（Edge headless，隔离 8101 服务，同源内联断言页）

> 断言页只拦截 `chat/completions` 的 POST，其余接口全部走真实 8101 服务，避免污染页面数据；
> 用模拟模型服务验证「接入真实大模型」链路，并覆盖三种降级路径。

| 视口 | 断言 | 结果 |
|---|---|---|
| 桌面 1440×900 | 77 | **77/77 PASS** |
| 平板 768×1024 | 79 | **79/79 PASS** |
| 手机 390×844 | 79 | **79/79 PASS** |
| **合计** | **235** | **235/235 PASS，0 FAIL** |

关键证据（三视口一致）：

- **共用护栏/快照**：`aiSystem()` 与 `aiReportSystem()` 都包含同一份 `AI_GUARD` 与同一份
  `aiSnapshot()` 输出；快照含六状态名称与真实总数；月报 system 要求按一~五分章节。
- **未配置 Key**：`aiMonthly()` 不发起任何模型请求、模式为「内置模板」、正文为模板且含真实
  `total`、`AI_REPORT` 与正文一致（可复制）。
- **已配置（填一次两边生效）**：月报 POST 的 `url` = 配置 base、`Authorization` = `Bearer {key}`、
  `model` = 配置 model、`max_tokens` ≥ 1000，system 含护栏与真实快照、user 指令要求分章节；
  正文替换为模型返回、模式变「大模型 · 实时数据」、`AI_REPORT` 同步。
  随后问答助手 `aiSend()` 复用**同一 base / Key / model**，system 同样含护栏+快照，回答为模型返回。
- **三种降级**：网络异常（`fetch` reject）、空响应（`content:''`）、HTTP 500 三种情况下，
  模式均为「内置模板 · 模型未响应」、正文保持模板（不含模型返回）、`AI_REPORT` 仍可复制；
  恢复内置后月报照常可用。
- **API Key 安全**：配置仅存 `localStorage`，产品脚本中无硬编码 Key，Key 只经运行时 `aiCfg()` 读取。
- **体验优化**：弹窗带 `report-modal` 类、桌面宽 ≥700px（平板/手机按 `94vw` 收敛且不溢出）、
  正文字号 ≥14px（窄屏 13px）、高度 ≥200px、复制按钮字号 ≥13px 且 padding ≥9px、仍绑定 `aiCopy()`；
  构造 `.tbl th` 实测 `rgba(189,141,99,0.46)`（alpha ≥0.4、仍是榻榻米棕、与数据行有区分）；
  构造 `.emptybox` / `.loadbox` 实测字号 ≥14px。
- **零回退 R6~R10**：五原色变量、R10/R11 CSS 块、文案精简（`.eyebrow=0`）、`#rver` 隐藏、
  导航 7 项、KPI 5 卡、状态条两列、六状态顺序与图例、AI 快捷问题 6 个、帮助页 4 个 `hlp-scroll`、
  `scroll-x ≥10`、`topbar` 裁剪、FAQ 已同步月报。
- **三视口**：整页无横向溢出；窄屏汉堡展开抽屉、遮罩点击关闭；flash 无加载失败；可见文案无禁词。

### 全套回归（主仓库 + 8100 活系统）

- `selftest.py` **18/18** · `selftest_lifecycle.py` **21/21** · `demo/demo_probe.py` **5/5**
- `demo/acceptance_check.py --http --base=http://127.0.0.1:8100`
  **40 PASS / 0 FAIL / 0 SKIP → ALL GREEN**（E01 运行中服务已加载当前磁盘代码 PASS）
- 静态检查：`node --check` 通过、违禁字样 0、五原色 hex 全部在位、R11 关键函数/元素齐全、
  旧文案（「固定模板」注释 / 「不调用外部大模型接口」/ 旧 FAQ）残留 0
- 基线：`/api/config` 仍为 `v1.0 / log=0`；`00_演示版范围与架构.md` 与 `selftest.py` 零改动
- 8100 服务返回页面已含 `report-modal` / `aiMonthlyLLM` / `AI_GUARD`，确认活系统加载改动后代码

## 四、交付与启动

```bash
set PYTHONUTF8=1          # Windows cmd；Git Bash / macOS / Linux 用 export PYTHONUTF8=1
python pulse_app.py 8100  # 或双击 run.bat / 执行 bash run.sh
```

浏览器打开 **`http://127.0.0.1:8100/`**；在线活系统（无需本地启动）：
**`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`**

源码仓库：`https://github.com/llR-776581173/pulse-pcc-demo`。离线兜底：`pulse-github.zip` / `pulse-github.bundle`。

大模型启用方式（**填一次，问答助手 + AI 生成月报同时生效**）：打开右下角「AI 助手」→「设置」→
填写接口地址（OpenAI 兼容 `/chat/completions`）、API Key、模型名称 →「保存」。
不填 Key、调用失败或网络异常时，助手自动使用内置数据问答、月报自动使用内置模板，演示不中断。

## 五、已知边界（如实记录）

- 本轮为**纯前端改动**：未新增任何后端接口、未改状态机 / 决策 / 数据口径 / 持久化数据 / 验收基线。
  模型调用由浏览器直连使用者配置的 OpenAI 兼容服务，配置仅存本机浏览器 `localStorage`。
- 若服务地址存在跨域限制，需该服务允许来自工作台域名的 CORS 请求；Key 只发往使用者所填的
  模型地址，不经过 Pulse 后端，也不写入仓库代码。
- 月报与问答的事实来源同为 `aiSnapshot()` 汇总的已加载数据（大盘/预算/预警/案例池/转移矩阵），
  不包含单客户逐笔明细；单客户分析仍走「流失预警客户池」时间轴与画像模块。
- R7 的「AI 推荐卡」仍为原有前端能力，本轮未改动其功能逻辑。
- 模板降级文本沿用 R7 原文（数字口径与页面一致），大模型成功时以模型基于同一快照生成的正文替换；
  「复制全文」在两种模式下均取当前 `AI_REPORT`。
