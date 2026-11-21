# Round 5 · 在线卡死与配色偏差修复说明

> 需求来源：用户验收在线活系统时反馈「页面卡死 / 此页面没有响应、一直不动」，且「配色不是约定的太平洋咖啡低饱和奶棕方案」。
> 修复范围：`static/demo_workspace.html`（前端）、`pulse_app.py`（仅一个可选切片参数）。
> 状态机 / 持久化 / `00` 需求基准 / `selftest.py` 18 基线 / 全部验收 CASE **零改动**。

---

## 一、卡死根因（实测定位）

云端托管出口带宽约 9–17 KB/s，且每个请求有 1.4–5s 固定延迟。实测：

| 接口 | 体积 | 耗时 |
|---|---|---|
| `/api/lifecycle/cases` | 828,864 B | **50–92 s** |
| `/api/actions?limit=500` | 258,911 B | 14.9 s |
| `/api/budget?coupons=350&face=44` | 7,473 B | 11.7 s |
| `/api/lifecycle` | 2,201 B | 5.0 s |
| `/` 首页 | 46,232 B | 4.5 s |

前端存在两处放大问题：

1. `boot()` 的 `Promise.all` 中，`loadLifecycle()` 末尾用 **`await loadCases()`** 拉取 828KB 全量案例池，把整个首屏阻塞 50–90 秒 —— 这是「一直不动」的直接原因。
2. `loadActions()` 并发请求 `/api/actions?limit=500`（258KB / 15s），但返回值 `a` **从未被使用**，漏斗实际只用 `/api/summary`（537 B）。

`MutationObserver` 虽用 `childList` 观察（class 变化不触发），但缺少去抖，在真实浏览器里存在回调堆积风险；原 DOM 模拟测试用桩对象替换了 `MutationObserver`，从未覆盖真实行为。

## 二、修复内容

### 前端 `static/demo_workspace.html`（21 处）

- **首屏解耦**：`boot()` 只等待总览必需的小接口；`loadLifecycle()` 去掉 `await loadCases()`。案例池改由 `scheduleCases()` 后台预取，切到「客户案例演示」视图时也会触发。首屏就绪实测 **160ms**。
- **数据瘦身**：案例请求改为 `/api/lifecycle/cases?limit=8`，**828,864 B → 4,234 B（196 倍）**，页面仍只渲染 8 行；总数改从 `/api/lifecycle` 的 `demo_pool_counts` 取，仍显示「共 3058 位」。
- **去掉无用大请求**：`loadActions()` 只用 `/api/summary` 渲染漏斗；`/api/actions` 接口地址保留，改为 `limit=1` 的非阻塞后台调用（258,911 B → 871 B）。
- **加载态与容错**：案例池、时间轴均有「正在加载…」提示与失败重试按钮；`loadBudget()` 加错误兜底，不再产生未捕获的 Promise rejection。
- **重算后刷新**：`applyConfig()` 成功后强制 `loadCases(true)`，保证改阈值后案例状态真实变化（验收 C03）。
- **MutationObserver 加固**：`requestAnimationFrame` 去抖 + 显式 `attributes:false / characterData:false`，杜绝回调堆积。

### 后端 `pulse_app.py`（仅接口层，默认行为不变）

`/api/lifecycle/cases` 新增**可选** `limit` 查询参数，只做返回切片：

- 不传 `limit` → 仍返回全量 A 3058 / B 1607 / C 188（所有既有消费者与验收 CASE 不变）。
- 传 `limit=8` → 每组前 8 条，排序规则不变（首位仍为 `C02186`）。
- 不修改 `case_lists()`、状态机、缓存键、持久化数据或任何计算逻辑。

## 三、配色修复（统一低饱和奶棕）

R3/R4 文档记载的「五色系」含一个蓝色 DOWNPOUR `#43718E`（用于 KPI 数值 / 数据强调），并保留活跃绿、预警琥珀、深度砖红、紫等多色语义色。用户验收判定不符合「低饱和奶棕方案」，本次全部收敛：

- 根变量：`--mole:#41352F` / `--brush:#8A6247` / `--tan:#B98F6B` / `--bluff:#E7D2BA` / `--rain:#7C5C45`（原蓝色改为低饱和深棕）；底色 `--bg:#F8F3EC`、侧栏 `linear-gradient(#F1E5D6 → #E9DBC7)` 保持低饱和奶棕。
- 六状态色、六出口色、六类状态 pill 全部改为**同一棕系的明度阶梯**，去掉蓝 / 绿 / 红 / 紫 / 琥珀的色相跳跃；圆环、热力矩阵、漏斗、刻度轴随变量统一。
- 花卉点缀、主按钮 hover、flash 提示底色同步换棕系。
- 真实浏览器 `getComputedStyle` 复验：侧栏渐变 `rgb(241,229,214)`、KPI 数值 `rgb(124,92,69)`、菜单高亮 `rgb(138,98,71)`，整页无 `#43718E` 残留。

## 四、验证结果

| 项目 | 结果 |
|---|---|
| 真实浏览器（Edge headless，同源 iframe 实际操作） | **24/24 PASS**：首屏 160ms、四视图切换与高亮、折叠导航、A/B/C 组切换、案例懒加载 8 行、时间轴弧线、审批表、配色计算值 |
| `selftest.py` | **18/18** |
| `selftest_lifecycle.py` | **21/21** |
| `demo/demo_probe.py` | **5/5** |
| `demo/acceptance_check.py --http` | **40 PASS / 0 FAIL → ALL GREEN** |
| 默认全量 cases（不传 limit） | A 3058 / B 1607 / C 188，与修复前一致 |
| 前端 JS | `node --check` PASS；`py_compile pulse_app.py` PASS |

> 真实浏览器验证页为一次性临时文件，验证后已删除，不进入仓库。

## 五、两个验收入口

- 在线活系统（重新部署后）：`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`
- 本地：`run.bat` / `bash run.sh` / `python pulse_app.py 8100` → `http://127.0.0.1:8100/`

两处使用同一份修复后的前端与后端文件。
