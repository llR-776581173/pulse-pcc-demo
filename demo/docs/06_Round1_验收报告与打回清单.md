# 06 · Round 1 独立质量验收报告与打回清单

> 验收角色：工 W（独立质量验收，**不改动任何核心代码文件**）
> 执行时刻：**2026-11-20 15:37:43**（稳定快照）｜ 基准规格：`00 ~ 05`，其中 `00` 为需求基准（已锁定）
> 验收装置：`demo/acceptance_check.py`（只读、可复跑）｜ 结构化留痕：`demo/acceptance_last.json`
> 过程留痕：`demo/acceptance_R1.txt`（15:33:38 并行编辑窗口快照）、`demo/acceptance_R1_stable.txt`（15:37:43 采用）

---

## 0. 结论

**代码验收 26 PASS / 14 FAIL → NOT GREEN，不进入最终交付物料产出阶段。**

- 回归基线守住：`selftest.py` **18/18 PASS（exit 0）**、`demo_probe.py` **5/5 PASS（exit 0）**；
  `00` 与 `selftest.py` 的 sha256 与锁定指纹一致，**一字未改**。
- 工 D 本轮修复成效显著，**6 项偏差已关闭**（详见 §2），其中「状态机按天演进」是上一轮
  被我判定为底层架构重大偏差的项目，现已修复。
- 仍有 **14 项未达标**：3 项 BLOCKER、7 项 P1 需求/数据契约缺口、3 项同一根因的页面项、
  1 项环境项（服务未重启）。
- **2 条底层架构层面的重大偏差需用户评估**（§4）：状态机数据层未持久化、三窗口/预警提前天数未实现。
  按文档规则 1，`00` 不迁就代码缺陷 → **建议代码向规格对齐，不改需求基准**。

> ⚠️ 执行期间并行开发仍在进行：`rule_config.py`(15:33:05)、`pulse_app.py`(15:33:21)、
> `pulse_state.py`(15:33~15:37) 陆续被修改，15:33 复跑一度撞上编辑中间态
> （`NameError: _demo_events_for`）。本轮结论以 **15:37:43 代码可运行状态**为准；
> 工 D 宣告本轮收工后需再复跑一次确认。

---

## 1. 五个维度逐项结果（26 PASS / 14 FAIL）

| 维度 | PASS | FAIL | 概要 |
|---|---|---|---|
| **BASELINE 回归基线** | 4 | 1 | 18/18、5/5、`00` 锁定、`selftest.py` 未改全绿；缺 `selftest_lifecycle.py` |
| **PAGE 页面校验** | 1 | 4 | 旧答辩材料原样保留 ✅；**独立干净商用演示页完全缺失** |
| **LOGIC 业务逻辑** | 12 | 7 | 六状态/矩阵/回流边/禁止跳级/按天演进/前视/价值分离/六出口/重算全绿；数据层与元数据契约缺口 |
| **CASE 演示案例** | 4 | 0 | **全绿**：不注入、A/B/C 三组可走通、改阈值状态真变、cut 内回流 |
| **D05 集成审查清单** | 4 | 2 | P0-2 / P1-3 / P1-4 / P1-5 已关闭；P0-1 / P2-6 未关闭 |
| **ENV 环境（不计入）** | 0 | 1 | 8000 服务仍是 11/19 旧进程，新 API 404 |

**关键实测数据（当前磁盘代码，进程内只读加载）**

```
状态分布(2026-09-30, n=5716):
  NEW_UNPURCHASED 0 | FIRST_PURCHASE 733 | ACTIVE 3284
  AT_RISK 1320 | DEEP_DORMANT 295 | CHURNED 84
转移矩阵: ACTIVE->AT_RISK 26742 | AT_RISK->DEEP_DORMANT 687 | 召回回流 22
改阈值验证: C01441 default=DEEP_DORMANT -> FLAG_MAX_SILENCE=120 => CHURNED
案例: A/C05326 ACTIVE, B/C01441 DEEP_DORMANT, C/C00437 ACTIVE（均非注入）
```

---

## 2. 本轮已关闭的偏差（确认工 D 修复有效）

| 编号 | 偏差 | 关闭证据 |
|---|---|---|
| `05 P0-2` | 预置案例注入合成事件 | `C01` PASS：`_demo_events_for` 已移除、`_pick_demo` 硬编码切片已移除；`C04` PASS 案例来自 ≤cut 真实交易 |
| `05 P1-3` | `rule_config` 标签含 `estimate-to-verify` | `D03`/`L10` PASS：13 个标签全部中性（「兑换率」「毛利率」） |
| `05 P1-4` | 缺 provisional / calibrated 元数据 | `D04`/`L09` PASS：`load()` 返回 `meta`，每字段 `source=provisional, calibrated=false` |
| `05 P1-5` | `/api/send` 写 `sent_at` | `D05` PASS：不再写时间戳；`L19` PASS 审批记录 `sent_at` 留空 |
| **新增（上轮重大偏差）** | 转移日志为空、状态机不按天演进 | `L04` PASS：ACTIVE→AT_RISK **26,742** 条、AT_RISK→DEEP_DORMANT **687** 条、召回回流 **22** 条 |
| **新增** | `or st == "ACTIVE"` 硬编码绕过合法性检查（跳级） | `L03` PASS：绕过已移除，`sm.legal` 生效 |

> 这 6 项直接支撑了「谁正在流失」「谁回流了」两个问题的回答能力，是本次改造的核心进展。

---

## 3. 打回工 D 的问题清单（按规格对齐，非改需求）

### BLOCKER · 阻塞全绿与演示

**BK-01 · 干净商用演示页（P0-1）｜ 规格：`00 §3 / 00 §5 / 01 勾检 / 05 P0-1`｜ 对应 FAIL：`P01 P02 P04 P05 D01`**
- 现状证据：`static/` 今日无新增 HTML（3 个文件 mtime 均 11-19）；`pulse_app.py` 根路由
  `_send_file("index.html")` 指向旧答辩页；该页含「未接入」「不是预测模型」等禁字样；
  `GET /` 页面无状态机 UI。
- 明确问题：演示入口仍是作业/答辩材料，违反「页面对标商用系统、不添加任何待校准提示文字」；
  阈值面板、六出口漏斗联动、状态分布视图均无处承载。
- 修改建议：
  1. 新建**独立演示外壳**（如 `demo/static/index.html` 或 `static/demo.html`），商用级 UI，
     不含 `01` 禁字样清单中任何字样；
  2. 根路由 `/` 指向该外壳；`static/index.html`、`decision_workspace.html`、
     `Pulse_动手试_版.html` 按 `00 §5` **原样保留**，不作演示入口；
  3. 面板接 `PUT /api/config`（改阈值/预算 → loading → 全量重算 → 显示 `rule_version`），
     至少覆盖 `00 §4` 的：六出口漏斗、状态分布与转移矩阵、单客时间轴、预置案例一键切换。
- 复验方式：`P01 P02 P04 P05 D01` 全 PASS；`01` 演示前勾检可逐条打勾。

**BK-02 · 新增断言独立文件 `selftest_lifecycle.py`｜ 规格：`04 §1 / 04 §4 / 05 P2-6`｜ FAIL：`B05 D06`**
- 现状证据：文件不存在；`04 §4` 质量门槛第 2 项未满足。
- 修改建议：新建独立文件，放交接包 §3.5 的 10 条断言（防前视、状态守恒、转移连续性、
  回流不新建 ID、基线不混用、金额口径、consent 时序、幂等、覆盖率单调与饱和等）；
  CI 两个文件分开跑，**`18/18` 分母保持 18**。
- 复验方式：`B05 D06` PASS；`python selftest.py` 与 `python selftest_lifecycle.py` 均 exit 0。

**BK-03 · 服务未重启（环境项）｜ FAIL：`E01`**
- 现状证据：8000 端口进程 PID 14584，`CreationDate 11/19 20:14:54`，
  CommandLine `pulse_app.py 8000`；`GET /api/lifecycle`、`/api/config` 均 **404**，
  `GET /` 返回 34,959 字节（与当前 `static/index.html` 41,469 字节不符）。
- 明确问题：这是**旧进程未加载当前磁盘代码**，不是代码缺陷；但阻塞 HTTP 层联调与现场演示。
- 修改建议：工 D 本轮修复收工后**重启服务**（`python pulse_app.py 8000`），
  确认 `GET /api/lifecycle` 200、`GET /api/config` 含 `meta`。
- 复验方式：`python demo/acceptance_check.py --http` → `E01` PASS。

### P1 · 数据契约与需求缺口

| 编号 | 问题 | 规格依据 | FAIL | 现状证据 | 修改建议 | 复验 |
|---|---|---|---|---|---|---|
| **P1-01** | 三窗口与「预警提前了几天」不可算 | `00 §4 / 04 #2 #3 / 02 A 第 3 项` | `L05` | `lifecycle()` 返回键无 window / warn / lead / 提前 任何指标 | 在转移边记录 `AT_RISK` 触发日 `T`，定义观察窗 `W` 与结果窗 `[T, T+H]`，输出 `warn_lead_days = 实际回流日 − T`；断言只读 ≤cut、无前视；`H=WARN_DAYS_H` 参与 `AT_RISK→DEEP_DORMANT` 边 | `L05` PASS + `03` 脚本第 3 步可演示 |
| **P1-02** | 状态机**数据层未持久化** | 交接包 §3.1 / `00 §4` | `L06 L07` | `audit/` 无 `customer_state_snapshot*` / `customer_state_transition*`；仅内存列表；`pulse_state.py` docstring 自承 "full daily cube is derivable" | 落两张表：快照表每客户每天一行、按 `as_of_date` 分区、含 `rule_version`；转移表 append-only，含 `from_state/to_state/trigger_event/occurred_at/rule_version`；重算生成新版本**不覆盖旧版本** | `L06 L07` PASS |
| **P1-03** | `rule_version` 未贯穿状态层 | `01 原则 / 02 D.5 / 04 #9 #10` | `L08` | `lifecycle()` 无该字段、`timeline()` 无、transition 记录无 | 三者 + 导出统一带 `rule_version`；界面只显示版本号（属系统状态，非口径提示） | `L08` PASS |
| **P1-04** | 旧 `rule_version` 快照被覆盖 | `02 D.5 / 04 #10` | `L12` | `_ensure_snapshot` 用 `open(SNAPSHOT_FILE, "w")`，版本变化即整体重写 | 改为按 `(cut, rule_version)` 分文件或追加写；旧版本快照、转移日志、决策日志一律保留 | `L12` PASS |
| **P1-05** | `decision_log` 缺 `state_at_decision` | 交接包 §3.3 / `00 §4` | `L11` | `SNAP_HEADER` / `LOG_HEADER` 均无该字段 | 两表加 `state_at_decision`，写入时取该客户在 cut 的状态机状态；与两类日志分表原则一致 | `L11` PASS |
| **P1-06** | `NEW_UNPURCHASED` 恒为 0，六状态分布不完整 | `00 §4 / 02 A 第 4 项` | `L18` | 分布 `NEW_UNPURCHASED=0`；`byc` 只含 ≤cut 有交易客户，`customers.csv` 注册未消费会员未入状态机 | 把注册但未交易会员纳入状态机（`customers.csv` 全集）；或书面确认活跃分母口径后按 `02` A 第 4 项登记，并在状态分布视图中如实呈现 | `L18` PASS |

> `P1-02` 与 `P1-01` 同时属于 §4 的底层架构重大偏差，需用户先评估再排期。

---

## 4. ⚠️ 底层架构层面的重大偏差（同步用户，请评估后续方案）

### A1 · 「客户生命周期状态机数据层」尚未成为数据层

- **差距**：本次改造的核心目标是在决策板**底下补一层带时间轴的持久化状态机数据层**。
  当前实现已能按天计算状态与转移（`L04` 有 26,742 条真实 `ACTIVE→AT_RISK` 转移，质量很好），
  但**结果只存在于内存返回值里**：`audit/` 无快照表、无 append-only 转移表、
  无 `as_of_date` 分区、`rule_version` 未贯穿。交接包 §3.1 的数据契约（`customer_state_snapshot`
  每客户每天恰好一行、`customer_state_transition` append-only）**未落地**。
- **影响**：无法回答「改阈值前后同一客户状态如何演进」「旧配置下谁被判流失」，
  也无法支撑 `02 D.5` 的校准追溯与 `04 #9/#10` 的快照导出/版本可追溯。
- **性质**：不是「改几行」，是要补一层持久化模型与写入路径，涉及 `00 §4` 的交付范围。
- **建议**：**维持 `00` 需求基准不变，代码向规格对齐**（符合文档规则 1）。请确认是否按此排期，
  或是否需要我先出一份数据契约落地方案供工 D 参照（我不改核心代码）。

### A2 · 三个核心问题里的「预警提前了几天」目前答不了

- **差距**：`00 §4` 明确包含三窗口 `T / [T−W,T] / [T,T+H]` 与预警提前天数；
  `04 #2/#3` 要求「能算出一个具体天数且断言无数据泄漏」。当前 `lifecycle()` / `timeline()`
  无任何 window/lead 指标，`WARN_DAYS_H=60` 虽已接进 params，但没有被用于度量「提前」。
- **影响**：`03` 演示脚本第 3 步（把 `WARN_DAYS_H` 60→45 观察预警提前天数变化）
  **当前无法演示**；`01` 口述卡第 8 条也缺少可指给交付方看的数字。
- **性质**：涉及 `T` 的定义、`W`/`H` 的口径与时间戳建模，属需求级缺口，不是 UI 补丁。
- **建议**：同样按「代码向规格对齐」处理；`H` 的**业务真实值**仍属 `02` A 类第 3 项
  （交付方认可后再收集），演示版继续用占位默认值 60，但**度量能力必须先建起来**。

> 说明：上一轮我判断为重大偏差的「状态机不按天演进 / 转移日志为空」**已由工 D 修复并关闭**，
> 本节的 A1/A2 是本轮验收后**剩余**的两条，范围已明显收窄。

---

## 5. 回归基线与规格锁定声明

- `selftest.py` 18/18 PASS、`demo_probe.py` 5/5 PASS，`00` sha256 `2bf1a646…`、
  `selftest.py` sha256 `9dd163d4…` 与 Round 1 锁定指纹一致 → **基线未被触碰**。
- `00` 按文档规则 1 **仅当用户主动变更需求时才修改**；本轮 14 项 FAIL 全部判定为
  **「代码未向规格对齐」**，因此打回工 D 修代码，**不改 `00` 的任何一条**。
- 六个决策出口 `C / no_consent / normal / low / high / medium` 实测集合不变（`L15` PASS）；
  架构四原则中的「并行不替换」「状态不掺价值」「两类日志分表、状态与价值分离」均保持
  （`L14` PASS，`05 A` 吻合项）。

---

## 6. 下一轮复验方式（工 D 收工后）

```bash
cd D:/DSH/DSH工作区域/pulse_app
python demo/acceptance_check.py --http        # 全量复验，自动写 acceptance_last.json
python selftest.py                            # 18/18
python demo/demo_probe.py                     # 5/5
python selftest_lifecycle.py                  # 新增断言（BK-02 交付后）
```

全部 PASS 后，我按用户要求**直接产出与成品系统匹配的最终交付物料**
（面向交付方的全套演示话术 + 完整操作脚本），素材台账见 `07_最终交付物料素材台账.md`，
届时无需再事后重新整理编写。

---

## 7. 归档变更

| 文件 | 变更 |
|---|---|
| `demo/acceptance_check.py` | **本轮新建**：只读、可复跑、抗编辑中间态的独立验收装置 |
| `demo/acceptance_last.json` | 结构化验收留痕（脚本自动生成） |
| `demo/acceptance_R1.txt` / `acceptance_R1_stable.txt` | 两轮过程留痕 |
| `docs/01 ~ 05` | 按文档规则 2 增量更新，关闭已修复项 |
| `docs/07_最终交付物料素材台账.md` | **本轮新建**：素材台账骨架，待全绿后成文 |
| `docs/00` | **未改动**（需求基准锁定） |
