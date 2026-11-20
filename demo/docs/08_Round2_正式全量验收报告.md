# 08 · Round 2 正式全量验收报告（ALL GREEN）

> 验收角色：工 W（**独立质量验收，不改动任何核心代码文件**）
> 执行时刻：**2026-11-20 18:27:58**（稳定快照，复跑一致）
> 基准规格：`demo/docs/00 ~ 05`，其中 `00` 为需求基准（**锁定**，sha256 `2bf1a646…`）
> 验收装置：`demo/acceptance_check.py --http`（本轮仅把 HTTP 目标由 8000 适配到 8100，
> 并支持 `--base=` / `PULSE_BASE`；规格断言一条未改）｜结构化留痕：`demo/acceptance_last.json`
> 交付信息：`http://127.0.0.1:8100/` · `static/demo_workspace.html` · 启动目录 `pulse_app`
> 运行环境：按用户提醒全程启用 **UTF-8 模式**（Windows cmd `set PYTHONUTF8=1`；
> Git Bash 等价 `export PYTHONUTF8=1` / 命令前缀 `PYTHONUTF8=1`），中文解码自检 `utf8_mode=1` OK。

---

## 0. 结论

**正式全量验收：40 PASS / 0 FAIL / 0 SKIP → ALL GREEN，环境项 E01 亦 PASS。**

- 三组测试独立实跑全绿：`selftest.py` **18/18**、`demo/demo_probe.py` **5/5**、
  `selftest_lifecycle.py` **21/21**，退出码均为 0。
- `06` 打回清单 **BK-01 / BK-02 / BK-03 与 P1-01 ~ P1-06 全部关闭**；
  Round 1 同步用户的 **两条底层架构重大偏差 A1（数据层未持久化）/ A2（预警提前天数不可算）已关闭**。
- `00` 与 `selftest.py` 的 sha256 与锁定指纹完全一致；六个决策出口集合不变；
  `selftest.py` 18 项不增不减，`18/18` 分母未被扩写。
- **→ 满足用户设定的「全部验收通过后直接产出最终交付物料」闸门**，本轮同步产出
  `09_交付方演示话术.md` + `10_完整操作脚本.md`，全部取自本轮成品实测，无需事后重写。
- 另记录 **4 条验收断言之外的演示体验优化项**（§4）：均不属 `00~05` 规格不达标、
  **不推翻 ALL GREEN**，已如实同步用户并写入最终物料的勾检与零代码兜底。

> 与 Round 1 的差异：R1 为 26 PASS / 14 FAIL（NOT GREEN）；本轮代码、页面、服务、
> 持久化数据层全部到位，验收装置从 39 项扩到 40 项（ENV 由 FAIL 转 PASS）后全绿。

---

## 1. 五个维度逐项结果（40 / 40）

| 维度 | PASS | FAIL | 概要 |
|---|---|---|---|
| **BASELINE 回归基线** | 5 | 0 | 18/18、5/5、`00` 锁定、`selftest.py` 未改、`selftest_lifecycle.py` 已建 |
| **PAGE 页面校验** | 5 | 0 | 独立干净商用页 `static/demo_workspace.html` 落地；禁字样 NONE；旧答辩材料原样保留；根路由切换；面板接 `/api/config` |
| **LOGIC 业务逻辑** | 19 | 0 | 六状态/矩阵/两条回流边/禁止跳级/按天演进/三窗口/持久化/版本贯穿/元数据/六出口/重算/前视/价值分离/NEW/审批全绿 |
| **CASE 演示案例** | 4 | 0 | 不注入、A/B/C 可走通、改阈值状态真变、cut 内回流 |
| **D05 集成审查清单** | 6 | 0 | P0-1 / P0-2 / P1-3 / P1-4 / P1-5 / P2-6 全部关闭 |
| **ENV 环境** | 1 | 0 | 8100 服务加载当前磁盘代码，`GET /api/lifecycle` → 200 |

### 成品实测数据（8100 HTTP 只读联调 + 磁盘代码 + `audit/` 实质抽查）

```
页面 GET /                      200 | 17,594 B | 与磁盘 demo_workspace.html 逐字一致 | 禁字样 NONE
                              标题「Pulse · 客户生命周期决策工作台」；9 个 UI 区块齐全
服务进程                       PID 22892，CreationDate 11/20 17:21:25，
                              命令行 pulse_app.py 8100（晚于核心代码最后修改 17:16 → 新代码）

状态分布 (cut=2026-09-30, n=6000)
  NEW_UNPURCHASED 284 (4.7%) | FIRST_PURCHASE 733 (12.2%) | ACTIVE 3284 (54.7%)
  AT_RISK 1320 (22.0%) | DEEP_DORMANT 295 (4.9%) | CHURNED 84 (1.4%)

三窗口 window = {T: 2026-09-30, W: 30, H: 60}
warn_lead_days = {count: 4205, mean: 5.2, min: 0, max: 117}
demo_pool_counts = {A: 3058, B: 1607, C: 188}

转移矩阵（全局）
  ACTIVE->AT_RISK 26,742 | AT_RISK->DEEP_DORMANT 687 | AT_RISK->ACTIVE 26,055
  DEEP_DORMANT->ACTIVE 687 | CHURNED->FIRST_PURCHASE 22

六出口漏斗 (/api/summary, total 5716)
  high 417 | medium 505 | low 768 | normal 3281 | C 733 | no_consent 12
  approvable 922 | no_spend 4794 | blocked 12 | E50 862 | E75 1326
预算卡 (/api/budget?coupons=350&face=44)
  coverage 42.8% | funded 308 / demand 922 / unserved 614 | HK$15,400 | face 44
审计 (/api/audit) 5 条记录，sent_at 非空 0 条 → 批准 ≠ 发送成立

持久化数据层
  customer_state_snapshot_v1_0.csv    6,000 行，as_of_date 全为 2026-09-30，
                                      6,000 个唯一客户，带 rule_version=v1.0
  customer_state_transition_v1_0.csv 64,887 行 append-only，
                                      含 from/to/trigger_event/occurred_at/rule_version
  pulse_decision_snapshot_v1_0.csv   5,716 行，含 state_at_decision
```

### 重算推演（进程内 `build_rows()`，不写文件、不污染演示现场）

| 配置 | NEW | AT_RISK | DEEP | CHURNED | lead_n | lead_mean | window.H |
|---|---|---|---|---|---|---|---|
| 默认 | 284 | 1,320 | 295 | 84 | 4,205 | **5.2** | 60 |
| `WARN_DAYS_H=45` | 284 | **1,174** | **485** | 84 | 4,210 | 5.2 | 45 |
| `WARN_DAYS_H=90` | 284 | **1,456** | **155** | 84 | 4,204 | 5.2 | 90 |
| `DEV_THRESHOLD=1.8` | 284 | 1,016 | 295 | 84 | 3,997 | **5.7** | 60 |
| `FLAG_MAX_SILENCE=120` | 284 | 1,320 | 216 | **163** | 4,183 | **4.9** | 60 |

> **口径修正（重要，已同步写进 `03` 与最终操作脚本）**：`WARN_DAYS_H` 决定
> `AT_RISK → DEEP_DORMANT` 的时点，因此改 H 会**迁移 AT_RISK / DEEP_DORMANT 人数**，
> 但**不改变 `warn_lead_days` 均值**（预警触发日由 `DEV_THRESHOLD × 个人基线` 决定）。
> 要演示「预警提前了几天」变化，应改 `DEV_THRESHOLD`（5.2 → 5.7 天）。
> `03` 原脚本第 3 步「改 H 观察预警提前天数变化」据此修正。

---

## 2. `06` 打回清单逐项关闭证据

| 编号 | R1 问题 | 关闭证据 |
|---|---|---|
| **BK-01** | 干净商用演示页缺失 | `static/demo_workspace.html` 17:07 新建（17,594 B）；`GET /` 与之逐字一致；9 个 UI 区块齐全；禁字样扫描 NONE；根路由不再指向 `index.html`；旧答辩材料（含「未接入」「不是预测模型」）按 `00 §5` 原样保留 → `P01 P02 P03 P04 P05 D01` PASS |
| **BK-02** | `selftest_lifecycle.py` 缺失 | 17:16 新建（238 行），实跑 **21/21 PASS exit 0**；覆盖防前视/状态守恒/转移连续性/回流不新建 ID/金额口径/consent 时序/覆盖率/基线不混用/重算/案例真实/版本贯穿/三窗口/六状态/持久化/state_at_decision/旧版本保留 → `B05 D06` PASS，`18/18` 分母不变 |
| **BK-03** | 服务未重启 | 8100 进程 17:21:25 启动的 `pulse_app.py 8100`；`/api/config`、`/api/lifecycle`、`/api/lifecycle/cases`、timeline 等全部 200；验收装置 E01 → 200 |
| **P1-01** | 三窗口 / 预警提前天数不可算 | `lifecycle()` 返回 `window={T,W,H}` 与 `warn_lead_days={count,mean,min,max}`；`timeline()` 返回 `window` 与单客 `warn_lead_days`；selftest_lifecycle #14 断言 → `L05` PASS |
| **P1-02** | 状态机数据层未持久化 | `audit/` 两张表实质落地（6,000 行快照 / 64,887 行 append-only 转移表）→ `L06` PASS |
| **P1-03** | `rule_version` 未贯穿状态层 | `lifecycle` / `timeline` / 每条转移记录 / 两张表均带 `v1.0` → `L08` PASS |
| **P1-04** | 旧版本快照被覆盖 | 按版本分文件 `*_v1_0.csv`；`_persist()` 快照仅在文件不存在时写；`_ensure_snapshot` 不再整体重写 → `L12` PASS |
| **P1-05** | `decision_log` 缺 `state_at_decision` | `pulse_decision_snapshot_v1_0.csv` 含 `state_at_decision`（5,716 行）→ `L11` PASS（详见 §4 OPT-03） |
| **P1-06** | `NEW_UNPURCHASED` 恒为 0 | 注册未消费会员纳入 `build_rows()`，分布 **284**、total 6,000 → `L18` PASS |

---

## 3. 两条底层架构重大偏差已关闭

### A1 · 「客户生命周期状态机数据层」已成为真正的数据层 ✅

- `pulse_state.LifecycleEngine.lifecycle()` 调用 `_persist()`，按 `rule_version` 落
  `customer_state_snapshot_vX.csv`（每客户一行、`as_of_date` 分区、`rule_version`）与
  `customer_state_transition_vX.csv`（append-only，`from_state/to_state/trigger_event/
  occurred_at/rule_version`）。
- 实质抽查：快照 6,000 行 / 6,000 唯一客户；转移表 64,887 行，含 26,742 条
  `ACTIVE→AT_RISK`、26,055 条 `AT_RISK→ACTIVE`、687 条 `DEEP_DORMANT→ACTIVE`、
  22 条 `CHURNED→FIRST_PURCHASE` —— 与内存聚合结果一致，**不是空壳文件**。
- 旧版本不覆盖、按版本分文件；`pulse_decision_snapshot` 带 `state_at_decision`，
  状态与决策可关联追溯。交接包 §3.1 数据契约达成。

> 保留说明：docstring 明确「快照为评估 cut + 变化点，非全历史每日立方」，
> 当前 `as_of_date` 单一取值 `2026-09-30`。演示版按 `as_of_date` 分区的结构已具备，
> 全历史每日立方属正式版扩展，不属 `00 §4` 演示版验收范围（见 §4 OPT-03 记录）。

### A2 · 「预警提前了几天」已可算 ✅

- 三窗口 `T / [T−W,T] / [T,T+H]` 落地：`window={T:2026-09-30, W:30, H:60}`，
  `H=WARN_DAYS_H` 参与 `AT_RISK → DEEP_DORMANT` 边。
- 度量：`warn_lead_days = 实际回流日 − AT_RISK 触发日`，单客 `timeline()` 返回该值，
  全局汇总 `{count:4205, mean:5.2, min:0, max:117}`；`B/C` 组案例实测
  `C03299` 33 天、`C02979` 7 天、`C00222` 84 天、`C00073` 1 天。
- 只读 ≤ cut、无前视（`L13` PASS）；`H` 的业务真实值仍属 `02` A 类第 3 项，
  演示版继续用占位默认 60，**度量能力已建、结论仍按口述卡第 10 条不宣称效果**。

---

## 4. 演示链路深挖发现的 4 条优化项（非阻塞，已同步用户）

> 以下**不在 `00~05` 的验收断言内**、不属规格不达标、**不推翻 ALL GREEN**。
> 它们是我在 HTTP 联调与「页面实际可点什么」层面做的额外实测；已写入
> `09` / `10` 的演示前勾检与零代码兜底，并建议工 D 下轮迭代。

| 编号 | 级别 | 现状（实测） | 影响 | 建议 / 零代码兜底 |
|---|---|---|---|---|
| **OPT-01** | 建议（演示可用性） | 页面每组只渲染 `list.slice(0,8)`；**A 组「回流案例」首屏 8 位客户 0/8 带回流弧线**，时间轴均为 `NEW→FIRST→ACTIVE` 两条 `TXN`（`C04400`…`C03613`）。A 组随机抽 60 位有 51 位（85%）带完整弧线，说明是**排序**问题：`case_lists()` 按 `median_gap_days` 降序，把交易笔数少、状态机尚在 `FIRST_PURCHASE` 的客户排到前面 | 交付方点「回流案例」看不到「沉寂→预警→回流」，削弱全链路演示 | 建议 A 组排序键改为「有回流边 / `n_transitions` 多 / `warn_lead_days` 有值优先」。**零代码兜底**：演示全链路改点 B 组第 4 位 `C03299`（首屏可见，`DEEP_DORMANT`，`ACTIVE→AT_RISK→ACTIVE`，lead **33 天**）或 C 组第 3 位 `C00222`（lead **84 天**，含 `WINDOW_EXPIRED` → `DEEP_DORMANT→ACTIVE`）；A 组只用于讲候选池规模与状态分布。已写入 `03` / `10` |
| **OPT-02** | 建议（UI 呈现） | 页面有「预警提前量」卡片，但只渲染 `AT_RISK + DEEP_DORMANT` 人数与一句提示；未呈现已算出的 `warn_lead_days`（mean 5.2 天 / count 4,205）与 `window{T,W,H}` | 卡片名实不符；「提前了几天」需靠口述、无屏上数字可指 | 建议把 `lc.warn_lead_days.mean`、`lc.window` 渲染到该卡（**属系统指标，不是待校准提示文字，显示完全合规**）。兜底：口述卡第 8 条 + 实测表给出具体数字 |
| **OPT-03** | 记录（合规确认） | `/api/lifecycle` 的 `note` 含「合成数据」字样；前端 `loadLifecycle()` **不引用**任何 `note/caveat/net_gain_note/context_note` 字段 → 页面禁字样扫描 NONE，符合 `00 §3`。另 `pulse_decision_log.csv`（人做决定的日志）未带 `state_at_decision`，但 `pulse_decision_snapshot_v1_0.csv` 已带 | 若将来有人渲染 `note` 会引入禁字样；日志表关联字段可更完整 | 保持前端不渲染 note；建议后续给 `/api/lifecycle` note 换成不含禁字样的中性表述，或明确「仅内部字段」。`state_at_decision` 已满足「状态与决策关联」，日志表补字段属锦上添花 |
| **OPT-04** | 观察（UI 观感） | 页面顶部 `<div class="row" id="kpis"></div>` 未被任何 JS 填充（`boot()` 只调 `loadConfig/loadLifecycle/loadActions/loadBudget`），首屏顶部留一排空白卡片区；「审批与操作记录」需手动点「刷新」才有内容 | 商用观感小瑕疵 | 建议补 `loadKpis()`（可填 total / AT_RISK 占比 / lead_mean / rule_version），或移除空容器；`boot()` 末尾补一次 `loadAudit()`。不影响任何规格断言 |

> **统一口径**：`00` 维持需求基准不变、代码向规格对齐；以上 4 条按文档规则 1
> **不修改 `00`**。它们不阻塞交付，已在最终物料中给出可执行的现场方案。

---

## 5. 回归基线与规格锁定声明

- `selftest.py` **18/18 PASS**、`demo/demo_probe.py` **5/5 PASS**、
  `selftest_lifecycle.py` **21/21 PASS**、`demo/acceptance_check.py --http` **40/40 ALL GREEN**。
- `00` sha256 `2bf1a6465aa3bfe3…`、`selftest.py` sha256 `9dd163d47843ea29…`
  与 Round 1 锁定指纹一致 → **需求基准与回归基线一字未改**。
- 六个决策出口 `C / no_consent / normal / low / high / medium` 集合不变（`L15` PASS）；
  架构四原则（并行不替换 / 状态不掺价值 / 两类日志分表 / 六出口保留）全部保持。
- `selftest.py` 末尾 5 条 OPEN ITEMS 仍标注 *NOT code bugs*，**未改动**；
  v2.2 规矩「PRD 与代码数字不一致以 selftest 为准，回头改文档」继续有效。

---

## 6. 复验命令（工 D 收工后 / 交付方现场可一键重跑）

```bash
cd D:/DSH/DSH工作区域/pulse_app
set PYTHONUTF8=1                              # Windows cmd；Git Bash 用 export PYTHONUTF8=1
python selftest.py                             # 18/18
python demo/demo_probe.py                      # 5/5
python selftest_lifecycle.py                   # 21/21
python demo/acceptance_check.py --http         # 40/40 ALL GREEN（默认 8100）
python demo/acceptance_check.py --http --base=http://127.0.0.1:8000   # 端口变更时指定
```

---

## 7. 本轮归档变更

| 文件 | 变更 |
|---|---|
| `demo/acceptance_check.py` | 仅 `group_env` 的 HTTP 目标由硬编码 8000 改为可配置（默认 8100，`--base=` / `PULSE_BASE`），**规格断言一条未改** |
| `demo/acceptance_R2.txt` / `acceptance_last.json` | 本轮验收过程留痕与结构化结果 |
| `docs/08_Round2_正式全量验收报告.md` | **本文件（新建）** |
| `docs/01 ~ 05`、`docs/07`、`README.md` | 按文档规则 2 增量更新：记录真实现状、关闭已修复项、登记 4 条优化项与口径修正 |
| `docs/09_交付方演示话术.md` | **新建**：全绿后一次性产出的面向交付方全套话术 |
| `docs/10_完整操作脚本.md` | **新建**：全绿后一次性产出的完整操作脚本（与成品控件/数字逐字对应） |
| `docs/00_演示版范围与架构.md` | **未改动**（需求基准锁定） |
| `docs/06_Round1_验收报告与打回清单.md` | **未改动**（保留 R1 历史快照） |
