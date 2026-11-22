# 18 · Round9 客户状态大盘六状态生命周期排序验收报告

> 日期：2026-11-22 · 范围：**仅** `static/demo_workspace.html`（前端展示层）
> 红线遵守：后端计算、状态机、数据口径、接口地址、持久化数据、`00` 需求基准、`selftest.py`
> 与其余验收基线 **零改动**；五原色卡不新增、不删减；全部原有 ID / JS 函数名 / CASE 数据保留。

## 一、需求

「客户状态大盘」六状态环形图按**完整客户生命周期顺序**统一排列，从健康到流失递进：

| # | 状态 | 状态机 key | 色块 |
|---|---|---|---|
| 1 | 进店未消费 | `NEW_UNPURCHASED` | `#E7CFB8` 浅奶杏 |
| 2 | 首购激活 | `FIRST_PURCHASE` | `#BD8D63` 榻榻米棕 |
| 3 | 活跃复购 | `ACTIVE` | `#8A5A3C` 深木棕 |
| 4 | 沉寂预警 | `AT_RISK` | `#43718E` 灰蓝 |
| 5 | 深度沉寂 | `DEEP_DORMANT` | `#38536B` 深灰蓝 |
| 6 | 判定流失 | `CHURNED` | `#2C4356` 更深灰蓝 |

要求：环形图**色块顺序**、右侧**列表顺序**、底部**图例顺序**全部对应统一，阅读路径符合从健康到流失的业务直觉。

## 二、改动清单（唯一文件，2 处）

### 1. `STATE_ORDER` 常量（一处驱动三处渲染）
```js
// 改前：['ACTIVE','AT_RISK','DEEP_DORMANT','FIRST_PURCHASE','CHURNED','NEW_UNPURCHASED']
// 改后：
const STATE_ORDER=['NEW_UNPURCHASED','FIRST_PURCHASE','ACTIVE','AT_RISK','DEEP_DORMANT','CHURNED'];
```
该常量同时被 `loadLifecycle()` 中三处使用，改一处即三处自动统一，无需改任何渲染函数：
- 环形图 `conic-gradient` 色块序列（`segs` 累加顺序）
- 右侧列表 `#distlist`（`.srow` 渲染顺序）
- 底部图例 `#distlegend`（`span` 渲染顺序）

### 2. 「客户分组」下拉选项显示顺序
`overview` 视图 `select[data-f="group"]` 的 option 顺序同步为生命周期顺序（原顺序把「进店未消费 / 首购激活」放在末尾）。
**value 集合完全不变**：`all,new,first,active,risk,deep,churn`，因此 `GROUP_KW` 关键词匹配与 `applyViewFilters()` 筛选联动逻辑零影响。

### 3. 明确不改的部分
- **`STATE_COLOR` 配色零改动**：沿用 R7 H1 既定色阶。顺序调整后自然形成「浅奶杏 → 榻榻米棕 → 深木棕（健康递进）→ 灰蓝 → 深灰蓝 → 更深灰蓝（风险递进）」的视觉路径，未新增任何颜色（hex 扫描仍为 13 色：五原色 + 近白中性 + 灰蓝明度阶梯）。
- **`MATRIX_S` 零改动**：状态转移矩阵表头原本就是生命周期顺序，本轮作为「全站状态顺序统一」的佐证纳入验证。
- KPI 5 卡、AI 问答 / 月报、时间轴、筛选逻辑、后端 `/api/lifecycle` 返回字段与数值均不动。

## 三、验证结果

### 真实浏览器（Edge headless，隔离 8101 服务，同源内联断言页）
| 视口 | 实测 innerWidth | 断言 | 结果 |
|---|---|---|---|
| 桌面 | 1410 | 26 | **26/26 PASS** |
| 平板 | 738 | 26 | **26/26 PASS** |
| 手机 | 492 | 26 | **26/26 PASS** |
| **合计** | — | **78** | **78/78 PASS，0 FAIL** |

关键证据（三视口一致）：
- 右侧列表 / 底部图例 / 矩阵表头文案顺序均 = `进店未消费 / 首购激活 / 活跃复购 / 沉寂预警 / 深度沉寂 / 判定流失`
- 环形图 6 段色块 = `#E7CFB8 / #BD8D63 / #8A5A3C / #43718E / #38536B / #2C4356`
- 环形图色块、列表圆点、图例圆点 **三处颜色序列完全一致**
- **数值不错位**：列表各行人数 `284 / 733 / 3284 / 1320 / 295 / 84` 与后端 `distribution` 按生命周期 key 逐一对应；六状态合计 `6000` = 在册会员
- 下拉文案顺序 = 生命周期顺序，value 集合不变；筛选「判定流失」仍只剩 1 行，恢复「全部状态」后 6 行全显
- 不回退：五原色变量、7 项导航、KPI 5 卡、`tl-scroll`、帮助页 4 个 `hlp-scroll`、12 个 `scroll-x`、`topbar` 装饰裁剪、抽屉元素、整页无横向溢出、flash 无加载失败

### 全套回归（主仓库 + 8100 活系统）
- `selftest.py` **18/18** · `selftest_lifecycle.py` **21/21** · `demo/demo_probe.py` **5/5**
- `demo/acceptance_check.py --http` **40 PASS / 0 FAIL / 0 SKIP → ALL GREEN**（E01 运行中服务已加载当前磁盘代码 PASS）
- 静态检查：`node --check` 通过、违禁字样 0、hex 仅 13 色无新增
- 基线：`/api/config` 仍为 `v1.0 / log=0`；`00_演示版范围与架构.md` 与 `selftest.py` 指纹与 R8 完全一致、零改动；`git diff` 仅 `static/demo_workspace.html` 与 `demo/acceptance_last.json`（验收留痕时间戳）
- 8100 服务返回的页面 md5 与仓库文件 md5 一致，确认活系统加载改动后代码

## 四、交付与启动

```bash
set PYTHONUTF8=1          # Windows cmd；Git Bash / macOS / Linux 用 export PYTHONUTF8=1
python pulse_app.py 8100  # 或双击 run.bat / 执行 bash run.sh
```

浏览器打开 **`http://127.0.0.1:8100/`**；在线活系统（无需本地启动）：
**`https://pcc-pulse-demo.app.workbuddy.host/?sharecode=KKXKERMBOR`**

源码仓库：`https://github.com/llR-776581173/pulse-pcc-demo`。离线兜底：`pulse-github.zip` / `pulse-github.bundle`。

## 五、已知边界（如实记录）

- 本轮为**纯展示层排序调整**，不改变任何统计口径、状态定义、阈值或计算结果；各状态人数与占比完全沿用后端 `/api/lifecycle` 实时返回。
- 环形图 `conic-gradient` 起点仍为顶部（12 点方向）顺时针，未改起点角度；仅调整各扇区排列顺序。
- 状态转移矩阵、AI 月报、AI 问答中的状态枚举顺序本就与生命周期一致或按业务语义组织，本轮未强行改动。
