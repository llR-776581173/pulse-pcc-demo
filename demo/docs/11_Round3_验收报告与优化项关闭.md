# 11 · Round 3 验收报告与优化项关闭（内部归档）

> 时间：2026-11-20 19:10–19:5x ｜ 触发：用户定性 **OPT-01 / OPT-02 / OPT-04 为演示合格项，必须修复**，
> 并要求页面按 Pacific Coffee 品牌视觉重绘。
> **修复约束（用户指定，全程遵守）**：严禁改动已验收通过的后端逻辑、状态机、持久化数据、
> `00` 基准、`selftest.py` 18/18 基线；只允许调整**前端页面、案例排序、前端渲染逻辑、CSS 样式**。

---

## 1. 修复范围（逐文件，全部在允许清单内）

| 文件 | 改动 | 性质 |
|---|---|---|
| `static/demo_workspace.html` | ① `renderKpis(lc)` 填充顶部 4 张 KPI 卡（OPT-04）；② `boot()` 并行加载 `loadAudit()`，审批记录页载即显（OPT-04）；③ 预警卡渲染 `warn_lead_days` mean/min/max/count 与 `window{T,W,H}`（OPT-02）；④ 全量 CSS 换 Pacific Coffee 五色系、左上角官方 logo、页头/页脚低透明度花卉点缀（品牌化）。**全部元素 ID、按钮文字、JS 函数名保持不变** | 纯前端 |
| `static/img/pcc_logo.svg` | 新增：Pacific Coffee 官网 logo（`pacificcoffee.com/image/logo.svg`，5,740 B） | 新增资源 |
| `pulse_state.py` `case_lists()` | A 组排序键由 `-median_gap_days` 改为 **（-回流弧线数， -最大预警提前天数， -间隔中位数）**（OPT-01）。弧线数与提前量用**同一状态机** `_transitions_for_customer()` 现算；组员资格（`_demo_pool`）、状态定义、持久化均未动 | 案例排序（用户明确允许项） |

**未触碰（指纹复验一致）**：`00_演示版范围与架构.md`（sha256 `2bf1a6465aa3bfe3…`）、
`selftest.py`（`9dd163d47843ea29…`）、`pulse_core.py`、`rule_config.py`、`audit/` 全部数据表、
六个决策出口、22 个 API 契约。

## 2. 三条优化项的关闭证据

### OPT-01 · A 组首屏案例（19:2x 实测，服务重启后）

首屏 8 位 **8/8 带完整「沉寂→预警→回流」弧线**：

| # | 客户 | 状态 | 转移数 | 回流边 | 最大提前 |
|---|---|---|---|---|---|
| 1 | `C02186` | ACTIVE | 54 | **26** | **35 天** |
| 2 | `C05939` | ACTIVE | 54 | 26 | 20 天 |
| 3 | `C00593` | ACTIVE | 50 | 24 | 20 天 |
| 4 | `C05569` | ACTIVE | 50 | 24 | 18 天 |
| 5 | `C02137` | ACTIVE | 48 | 23 | 24 天 |
| 6 | `C02827` | ACTIVE | 48 | 23 | 22 天 |
| 7 | `C03015` | ACTIVE | 48 | 23 | 18 天 |
| 8 | `C03127` | ACTIVE | 48 | 23 | 16 天 |

R2 的「改点 B 组 `C03299` / C 组 `C00222`」兜底方案**取消**（二者保留作对照样本）；
验收断言 `C02` 所需 A 组 ID（`C05326`/`C01255`/`C02151`）仍在组内，断言不受影响。

### OPT-02 · 预警提前量卡渲染

页面「预警提前量」卡现在显示：**平均预警提前天数 5.2 天**（可测 4,205 人 · 范围 0–117 天）
+ 观察窗 T−30 / 结果窗 T+60（截止 2026-09-30）。属系统指标渲染，非提示文字，禁字样扫描不受影响。

### OPT-04 · KPI 自动填充 + 审批自动加载

顶部 4 张 KPI 卡页载即显（在册会员 6,000 / 活跃复购 3,284 / 沉寂·值得激励 1,615 / 判定流失 84）；
「审批与操作记录」随 `boot()` 自动加载（5 条记录，`sent` 列全「—」），「刷新」按钮保留。

## 3. 品牌化落地

- 五色系：TATAMI TAN `#BD8D63`（点缀/图标）、FLORAL BLUFF `#E7CFB8`（边框/花卉）、
  MOLE `#3A2E2D`（页头/正文）、BRUSHWOOD `#8A5A3C`（标题/主按钮）、DOWNPOUR `#43718E`（数据强调/KPI 数值）。
- 页头左上角官方 logo（白底圆形，天然适配深色页头）；页头右上一枚花卉、页面右下角一枚
  固定低透明度（opacity .07–.14）花卉，`pointer-events:none`，不遮挡任何图表与数据。
- 背景 `#F7F1E9` 暖米色，卡片纯白、数据区干净；状态语义色保持可读（活跃绿/预警琥珀/深度砖红等）。
- 页面禁字样扫描仍 **NONE**（`P02` PASS）。

## 4. 全量复验结果（修复后）

| 项 | 结果 |
|---|---|
| `selftest.py` | **18/18 checks passed**，exit 0 |
| `demo/demo_probe.py` | **5/5 probe checks passed**，exit 0 |
| `selftest_lifecycle.py` | **21/21 checks passed**，exit 0 |
| `demo/acceptance_check.py --http` | **40 PASS / 0 FAIL / 0 SKIP → ALL GREEN**（E01 PASS，8100 已加载当前代码）；留痕 `acceptance_R3.txt` / `acceptance_last.json` |
| `00` / `selftest.py` 指纹 | 与锁定值一致（`B03 B04` PASS） |
| 页面禁字样 | NONE |
| logo 资源 | `GET /static/img/pcc_logo.svg → 200`，合法 SVG |
| 首屏案例 | A 组 8/8 弧线（见 §2） |

## 5. 运维记录

- 为加载 A 组新排序，重启了 8100 服务两次（终止旧 PID → `PYTHONUTF8=1 python pulse_app.py 8100` 后台启动）。
  页面/CSS 改动无需重启（静态文件逐请求读盘）；`/api/lifecycle/cases` 按 `(rule_version, cut)` 缓存，排序改动必须重启。
- `rule_config` 仍为 **v1.0、log 0 条**：本轮**未执行任何写入型重算**，演示现场配置版本未污染。

## 6. 保留项

- **OPT-03** 维持记录不改：前端不渲染 `/api/lifecycle` 的 `note`；`state_at_decision` 已在决策快照表。
- 视觉细节建议演示前人工过目一遍（本轮沙箱内无法截图）；页面结构、JS 与原版同构，风险低。

## 7. 文档增量（本轮）

`03`（首屏案例表 + R3 演示脚本）、`01`（R3 增量 + 勾检更新）、`05`（OPT 关闭状态）、
`07`（控件对照 / 案例表 / R3 逐轮记录）、`09` / `10`（最终物料同步 R3）、`README`（登记 `11`）、本报告。
`00` 未改一字；`06` / `08` 保留历史快照不改。
