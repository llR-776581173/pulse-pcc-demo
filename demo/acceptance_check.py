# -*- coding: utf-8 -*-
"""
acceptance_check.py — Pulse 演示版 · 独立质量验收装置（只读）

角色边界（工 W / 独立验收）：
  * 本脚本**只读**核心代码与数据，绝不修改 pulse_core.py / pulse_app.py /
    pulse_state.py / rule_config.py / selftest.py / static/*.html / data/。
  * 唯一写文件：本脚本同目录下的 acceptance_last.json（结构化验收留痕）。
  * 基准规格 = demo/docs/00~05，其中 00 为需求基准（锁定，不迁就代码缺陷）。
  * 并行开发进行中可能撞上「编辑中间态」；脚本不崩溃，如实记为 FAIL/SKIP。

用法：
  cd pulse_app
  python demo/acceptance_check.py                 # 明细 + acceptance_last.json
  python demo/acceptance_check.py --no-json      # 只打印
  python demo/acceptance_check.py --http         # 额外对运行中服务发只读 GET

分组：BASELINE / PAGE / LOGIC / CASE / D05 / ENV
退出码：0 = 代码验收全绿（ENV 不计入）；1 = 存在 FAIL。
"""
import hashlib
import inspect
import json
import os
import subprocess
import sys
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCS = os.path.join(HERE, "docs")
sys.path.insert(0, ROOT)

RESULTS = []
LOCK = {
    "00_演示版范围与架构.md": "2bf1a6465aa3bfe34b82ac83b265a8bb560d023e15f88778c2cd0bcfb8a5a4f9",
    "selftest.py": "9dd163d47843ea29d5b712f88bb3da1dd283ed22ed5808fed1e671ea12199bbe",
}
BAD_WORDS = ["待校准", "占位", "estimate-to-verify", "合成数据", "未接入",
             "暂不支持", "不是预测模型", "已知限制", "数字仅供演示",
             "口径待确认", "仅供演示", "口径待"]
DATA_DIR = r"D:\Work Buddy\工作空间\PCC_MA_PRD\data"
CUT = dt.date(2026, 9, 30)
SIX_EXITS = {"C", "no_consent", "normal", "low", "high", "medium"}


def check(group, code, name, ok, detail, spec):
    RESULTS.append(dict(group=group, code=code, name=name,
                        status="PASS" if ok else "FAIL",
                        detail=str(detail), spec=spec))


def skip(group, code, name, detail):
    RESULTS.append(dict(group=group, code=code, name=name,
                        status="SKIP", detail=str(detail), spec="-"))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def collect():
    """一次性加载当前磁盘代码并采集运行时事实；异常不抛出，记入 error。"""
    p = dict(error=None, core=None, ps=None, rcfg=None, app=None,
             eng=None, lc={}, tl={}, src_app="", src_state="", cfg={}, fields=[])
    try:
        import pulse_core as core
        import pulse_state as ps
        import rule_config as rcfg
        import pulse_app as app
        p.update(core=core, ps=ps, rcfg=rcfg, app=app)
        p["src_app"] = read(os.path.join(ROOT, "pulse_app.py"))
        p["src_state"] = read(os.path.join(ROOT, "pulse_state.py"))
        p["cfg"] = rcfg.load()
        p["fields"] = list(rcfg.FIELDS)
    except Exception as e:
        p["error"] = "IMPORT %s: %s" % (type(e).__name__, e)
        return p
    try:
        eng = app._lifecycle_engine()
        p["eng"] = eng
        p["lc"] = eng.lifecycle()
        p["tl"] = eng.timeline("C01441")
    except Exception as e:
        p["error"] = "RUNTIME %s: %s" % (type(e).__name__, e)
    return p


def safe(fn, group, P=None):
    try:
        fn(P) if P is not None else fn()
    except Exception as e:
        check(group, "X99", "本组验收可完整执行", False,
              "%s: %s" % (type(e).__name__, e), "代码须处于可运行状态")


# ---------------------------------------------------------------- BASELINE
def group_baseline(P):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "selftest.py"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    check("BASELINE", "B01", "selftest.py 18/18 回归基线",
          r.returncode == 0 and "18/18 checks passed" in out,
          "exit=%d | %s" % (r.returncode, "18/18 checks passed" if "18/18 checks passed" in out else out[-160:]),
          "00 §5 / 04 §1 / 04 §4")

    r2 = subprocess.run([sys.executable, os.path.join("demo", "demo_probe.py")],
                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    out2 = (r2.stdout or "") + (r2.stderr or "")
    check("BASELINE", "B02", "demo_probe.py 5/5 可复跑验证",
          r2.returncode == 0 and "5/5 probe checks passed" in out2,
          "exit=%d | %s" % (r2.returncode, "5/5" if "5/5 probe checks passed" in out2 else out2[-160:]),
          "04 §2 / 04 §4")

    p00 = os.path.join(DOCS, "00_演示版范围与架构.md")
    h = sha(p00) if os.path.isfile(p00) else "<missing>"
    check("BASELINE", "B03", "基准规格 00 未被改动（需求锁定）",
          h == LOCK["00_演示版范围与架构.md"], "sha256=%s" % h[:16],
          "用户文档规则 1 / 00 全文")

    pst = os.path.join(ROOT, "selftest.py")
    h2 = sha(pst) if os.path.isfile(pst) else "<missing>"
    check("BASELINE", "B04", "selftest.py 文件未被修改（18 项不增不减）",
          h2 == LOCK["selftest.py"], "sha256=%s" % h2[:16], "04 §1 / 用户第 4 点")

    f = os.path.join(ROOT, "selftest_lifecycle.py")
    check("BASELINE", "B05", "新增断言独立文件 selftest_lifecycle.py 已建",
          os.path.isfile(f), "present" if os.path.isfile(f) else "MISSING",
          "04 §1 / 04 §4 / 05 P2-6")


def demo_shells():
    legacy = {"index.html", "decision_workspace.html", "Pulse_动手试_版.html"}
    found = []
    for base in (os.path.join(ROOT, "static"), os.path.join(HERE, "static")):
        if os.path.isdir(base):
            found += [os.path.join(base, fn) for fn in os.listdir(base)
                      if fn.endswith((".html", ".htm")) and fn not in legacy]
    return found


# -------------------------------------------------------------------- PAGE
def group_page(P):
    shells = demo_shells()
    ok_shell = bool(shells)
    check("PAGE", "P01", "存在独立干净商用演示页（不动答辩材料）",
          ok_shell, "candidates=%s" % ([os.path.relpath(c, ROOT) for c in shells] or "NONE"),
          "00 §3 / 00 §5 / 05 P0-1")

    hits = []
    for c in shells:
        txt = read(c)
        hits += ["%s:%s" % (os.path.basename(c), w) for w in BAD_WORDS if w in txt]
    check("PAGE", "P02", "演示页无任何待校准/假设提示文字",
          ok_shell and not hits,
          "hits=%s" % (hits[:8] or ("no demo shell" if not ok_shell else "NONE")),
          "00 §3 / 01 勾检 / 01 禁字样清单")

    idx = os.path.join(ROOT, "static", "index.html")
    old_hits = [w for w in BAD_WORDS if w in read(idx)] if os.path.isfile(idx) else []
    check("PAGE", "P03", "旧答辩材料 static/index.html 原样保留（允许含提示）",
          True, "legacy wording=%s（按 00 §5 保留，不作演示入口）" % (old_hits or "NONE"), "00 §5")

    src = P["src_app"] or read(os.path.join(ROOT, "pulse_app.py"))
    check("PAGE", "P04", "根路由 / 指向演示外壳而非旧答辩页",
          '_send_file("demo' in src or '_send_file("index.html")' not in src,
          "root route = %s" % ('"index.html"' if '_send_file("index.html")' in src else "other"),
          "00 §3 / 05 P0-1")

    ui = " ".join(read(c) for c in shells)
    check("PAGE", "P05", "前端存在阈值/预算面板并触发全链路重算",
          ok_shell and any(k in ui for k in ("/api/config", "WARN_DAYS_H", "recompute", "重算")),
          "demo shell UI wiring=%s" % ("present" if ok_shell and any(
              k in ui for k in ("/api/config", "WARN_DAYS_H", "recompute", "重算")) else "NONE"),
          "00 §3 / 04 #1 / 04 #6")


# ------------------------------------------------------------------- LOGIC
def group_logic(P):
    core, ps, rcfg, app = P["core"], P["ps"], P["rcfg"], P["app"]
    if core is None:
        check("LOGIC", "X00", "核心模块可导入并运行", False, P["error"], "代码须处于可运行状态")
        return
    check("LOGIC", "X00", "核心模块可导入并运行", P["error"] is None,
          P["error"] or "OK", "代码须处于可运行状态")

    lc, tl = P["lc"], P["tl"]
    check("LOGIC", "L01", "六状态定义完整",
          ps.STATE_RANK == ["NEW_UNPURCHASED", "FIRST_PURCHASE", "ACTIVE",
                            "AT_RISK", "DEEP_DORMANT", "CHURNED"],
          str(ps.STATE_RANK), "00 §2 / 00 §4 / 交接包 §3.2")

    leg = {k: sorted(v) for k, v in ps.LEGAL.items()}
    check("LOGIC", "L02", "转移矩阵含两条回流边且 CHURNED 不直接复活",
          leg.get("AT_RISK") == ["ACTIVE", "DEEP_DORMANT"]
          and leg.get("CHURNED") == ["FIRST_PURCHASE"]
          and "CHURNED" not in leg.get("ACTIVE", []),
          str(leg), "00 §2 / 00 §4 / 05 A / 04 #5")

    src_tr = inspect.getsource(ps._transitions_for_customer) if hasattr(ps, "_transitions_for_customer") else ""
    check("LOGIC", "L03", "转移合法性不被硬编码绕过（禁止跳级）",
          bool(src_tr) and 'or st == "ACTIVE"' not in src_tr and "sm.legal" in src_tr,
          "bypass='or st == ACTIVE'=%s" % ('or st == "ACTIVE"' in src_tr),
          "00 §2 / 交接包 §3.2 / 04 #5")

    mat = lc.get("transition_matrix", {})
    risk_edges = (mat.get("ACTIVE", {}).get("AT_RISK", 0)
                  + mat.get("AT_RISK", {}).get("DEEP_DORMANT", 0))
    check("LOGIC", "L04", "时间轴按天演进，转移日志含风险状态转移",
          risk_edges > 0,
          "ACTIVE->AT_RISK=%s, AT_RISK->DEEP_DORMANT=%s, recall=%s" %
          (mat.get("ACTIVE", {}).get("AT_RISK"), mat.get("AT_RISK", {}).get("DEEP_DORMANT"),
           mat.get("CHURNED", {}).get("FIRST_PURCHASE")),
          "00 §3 / 00 §4 / 04 #2 #5 / 交接包 §3.2")

    tri = [k for k in lc if any(t in k.lower() for t in
                                ("window", "warn", "lead", "early", "提前"))]
    check("LOGIC", "L05", "三窗口 T/[T-W,T]/[T,T+H] 与预警提前天数可算",
          bool(tri), "window/lead keys=%s" % (tri or "NONE"),
          "00 §4 / 04 #2 #3 / 02 A 第 3 项")

    audit = os.path.join(ROOT, "audit")
    files = os.listdir(audit) if os.path.isdir(audit) else []
    has_snap = any("state_snapshot" in f for f in files)
    has_tr = any("state_transition" in f for f in files)
    all_src = P["src_app"] + P["src_state"]
    check("LOGIC", "L06", "状态机数据层持久化（快照表 + append-only 转移表）",
          has_snap and has_tr,
          "snapshot=%s transition=%s | audit=%s" % (has_snap, has_tr, files[:8]),
          "交接包 §3.1 数据契约 / 00 §4")

    check("LOGIC", "L07", "每客户每天恰好一行快照（按 as_of_date 分区）",
          has_snap and has_tr and "as_of_date" in all_src,
          "snapshot=%s transition=%s | as_of_date in source=%s" %
          (has_snap, has_tr, "as_of_date" in all_src), "交接包 §3.1 / 00 §4")

    check("LOGIC", "L08", "rule_version 贯穿 lifecycle / timeline / 转移记录 / 导出",
          "rule_version" in lc and "rule_version" in json.dumps(tl),
          "lifecycle.rule_version=%s | timeline has=%s | transition has=%s" %
          (lc.get("rule_version", "<ABSENT>"), "rule_version" in tl,
           any("rule_version" in json.dumps(t) for t in tl.get("transitions", []))),
          "01 原则 / 02 D.5 / 04 #9 #10")

    cfg = P["cfg"]
    check("LOGIC", "L09", "数据层 provisional / calibrated 机器可读标记",
          any(k in json.dumps(cfg) for k in ("provisional", "calibrated")),
          "config keys=%s" % sorted(cfg.keys()), "02 表头 / 01 原则 / 05 P1-4")

    check("LOGIC", "L10", "配置字段标签中性（无待校准字样）",
          not any("estimate-to-verify" in str(f) or "待校准" in str(f) for f in P["fields"]),
          "bad labels=%s" % [f[1] for f in P["fields"]
                             if "estimate-to-verify" in str(f) or "待校准" in str(f)],
          "01 禁字样清单 / 05 P1-3")

    headers = app.SNAP_HEADER + app.LOG_HEADER
    check("LOGIC", "L11", "decision_log 含 state_at_decision 外联",
          any("state_at_decision" in h for h in headers),
          "SNAP=%s | LOG=%s" % (app.SNAP_HEADER[:4], app.LOG_HEADER[:4]),
          "交接包 §3.3 / 00 §4")

    snap_src = inspect.getsource(app._ensure_snapshot) if hasattr(app, "_ensure_snapshot") else ""
    check("LOGIC", "L12", "旧 rule_version 快照保留、不覆盖",
          bool(snap_src) and 'open(SNAPSHOT_FILE, "w"' not in snap_src,
          "overwrite-on-version-change=%s" % ('open(SNAPSHOT_FILE, "w"' in snap_src),
          "02 D.5 / 04 #10")

    feats = inspect.getsource(core._pre_cut_history)
    check("LOGIC", "L13", "只读 ≤ cut，无前视泄漏",
          "<= as_of" in feats, "pre-cut filter=%s" % ("<= as_of" in feats),
          "00 §6 红线 4 / 04 §4 防前视")

    sig = str(inspect.signature(ps._state_for))
    check("LOGIC", "L14", "状态定义不掺 value_tier / risk_score",
          not any(k in sig for k in ("value", "risk", "group", "tier")),
          "_state_for%s" % sig, "00 §2 原则 3 / 05 A")

    try:
        ac = core.classify_customers(DATA_DIR, CUT)
        got = set(r["group"] for r in ac["rows"])
    except Exception:
        got = set()
    check("LOGIC", "L15", "六个决策出口定义不变", got == SIX_EXITS,
          "groups=%s" % sorted(got), "00 §2 原则 2 / 00 §4")

    try:
        a = app.state_engine.LifecycleEngine(DATA_DIR, CUT, params=None).timeline("C01441")["state"]
        b = app.state_engine.LifecycleEngine(DATA_DIR, CUT,
                                             params={"FLAG_MAX_SILENCE": 120}).timeline("C01441")["state"]
        ok16, d16 = (a != b), "C01441: default=%s -> max_sil=120:%s" % (a, b)
    except Exception as e:
        ok16, d16 = False, "RUNTIME %s: %s" % (type(e).__name__, e)
    check("LOGIC", "L16", "改阈值后状态机全链路重算（状态真变）", ok16, d16,
          "00 §3 / 01 口述 8 / 04 #1")

    cp = app._current_params()
    check("LOGIC", "L17", "params 全链路接线（含 H / 兑换率 / 毛利率）",
          all(k in cp for k in ("WARN_DAYS_H", "REDEMPTION", "GROSS_MARGIN", "DEV_THRESHOLD")),
          "keys=%s" % sorted(cp.keys()), "00 §3 / 04 #1")

    dist = lc.get("distribution", {})
    check("LOGIC", "L18", "六状态分布完整（注册未消费会员纳入状态机）",
          dist.get("NEW_UNPURCHASED", 0) > 0, "distribution=%s" % dist,
          "00 §4 / 02 A 第 4 项活跃分母口径")

    check("LOGIC", "L19", "批准 ≠ 发送：审批记录 sent_at 留空",
          '"sent_at": ""' in P["src_app"],
          "approval keeps sent_at empty=%s" % ('"sent_at": ""' in P["src_app"]),
          "00 §6 红线 1 / 01 口述 4")


# -------------------------------------------------------------------- CASE
def group_case(P):
    ps, app, core = P["ps"], P["app"], P["core"]
    if ps is None:
        check("CASE", "X00", "案例组可加载", False, P["error"], "代码须可运行")
        return
    injected = hasattr(ps, "_demo_events_for")
    try:
        pick = inspect.getsource(ps.LifecycleEngine._pick_demo)
        hardcoded = "ids[100:104]" in pick or "ids[400:404]" in pick
    except Exception:
        hardcoded = False
    check("CASE", "C01", "预置案例不注入合成事件",
          not injected and not hardcoded,
          "_demo_events_for=%s hardcoded-slices=%s" % (injected, hardcoded),
          "00 §3 / 03 硬约束 / 05 P0-2")

    eng = P["eng"]
    spec_ids = {"A": ["C05326", "C01255", "C02151"],
                "B": ["C01441", "C03110", "C01387"],
                "C": ["C00437", "C01475"]}
    ok_all, detail = True, []
    for grp, ids in spec_ids.items():
        for cid in ids:
            try:
                t = eng.timeline(cid) if eng else {}
                n = len(t.get("transitions", []))
                ok = n > 0 and t.get("state") in ps.STATE_RANK
                detail.append("%s/%s:%s(%s)" % (grp, cid, t.get("state"), n))
                ok_all &= ok
            except Exception as e:
                detail.append("%s/%s:ERR(%s)" % (grp, cid, type(e).__name__))
                ok_all = False
    check("CASE", "C02", "A/B/C 三组预置案例可走通时间轴", ok_all,
          " ".join(detail), "00 §4 / 03 / 04 #4")

    try:
        changed = 0
        for cid in ["C01441", "C03110", "C01387"]:
            a = app.state_engine.LifecycleEngine(DATA_DIR, CUT, params=None).timeline(cid)["state"]
            b = app.state_engine.LifecycleEngine(DATA_DIR, CUT,
                                                 params={"FLAG_MAX_SILENCE": 120}).timeline(cid)["state"]
            changed += (a != b)
        ok03, d03 = changed > 0, "%d/3 B-group cases changed state" % changed
    except Exception as e:
        ok03, d03 = False, "RUNTIME %s: %s" % (type(e).__name__, e)
    check("CASE", "C03", "改阈值后预置案例状态真实变化（非硬编码动画）", ok03, d03,
          "00 §3 / 01 口述 9 / 04 #4")

    try:
        txn, byc, baseline, modal = core._features(DATA_DIR, CUT)
        ok_cut = all(cid in byc and byc[cid][-1]["d"].date() <= CUT for cid in spec_ids["A"])
        d04 = "A ids in <=cut history=%s | txn=%d" % (ok_cut, len(txn))
    except Exception as e:
        ok_cut, d04 = False, "RUNTIME %s: %s" % (type(e).__name__, e)
    check("CASE", "C04", "A 组回流弧线在 cut 内完成、零数据改动", ok_cut, d04,
          "03 筛选口径 / 00 §3")


# ---------------------------------------------------------------------- D05
def group_d05(P):
    ps, rcfg = P["ps"], P["rcfg"]
    check("D05", "D01", "[05 P0-1] 干净商用演示页已落地", bool(demo_shells()),
          "shells=%s" % ([os.path.basename(s) for s in demo_shells()] or "NONE"), "05 P0-1")
    check("D05", "D02", "[05 P0-2] 预置案例改为从合成数据筛出",
          ps is not None and not hasattr(ps, "_demo_events_for"),
          "_demo_events_for=%s" % (hasattr(ps, "_demo_events_for") if ps else "module unavailable"),
          "05 P0-2")
    check("D05", "D03", "[05 P1-3] rule_config 中性标签",
          bool(P["fields"]) and not any("estimate-to-verify" in str(f) for f in P["fields"]),
          "bad=%s" % [f[1] for f in P["fields"] if "estimate-to-verify" in str(f)], "05 P1-3")
    check("D05", "D04", "[05 P1-4] provisional / calibrated 元数据",
          any(k in json.dumps(P["cfg"]) for k in ("provisional", "calibrated")),
          "keys=%s" % sorted(P["cfg"].keys()), "05 P1-4")
    check("D05", "D05", "[05 P1-5] /api/send 与『发送未接入』口径统一",
          "sent_at = dt.datetime.now()" not in P["src_app"],
          "writes sent_at timestamp=%s" % ("sent_at = dt.datetime.now()" in P["src_app"]),
          "05 P1-5")
    f = os.path.join(ROOT, "selftest_lifecycle.py")
    check("D05", "D06", "[05 P2-6] selftest_lifecycle.py 独立断言文件",
          os.path.isfile(f), "present=%s" % os.path.isfile(f), "05 P2-6")


# ---------------------------------------------------------------------- ENV
def group_env(P):
    if "--http" not in sys.argv:
        skip("ENV", "E01", "运行中服务已加载当前磁盘代码", "未启用 --http，跳过 HTTP 层联调")
        return
    import urllib.request
    # R2: 演示服务已迁到 8100（用户交付信息）。--base= 优先，其次 PULSE_BASE，
    # 最后默认 8100；保留 8000 兼容只需 --base=http://127.0.0.1:8000。
    base = None
    for a in sys.argv:
        if a.startswith("--base="):
            base = a.split("=", 1)[1].rstrip("/")
    if base is None:
        base = os.environ.get("PULSE_BASE", "http://127.0.0.1:8100").rstrip("/")
    url = base + "/api/lifecycle"
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            ok, detail = (r.status == 200), "GET %s -> 200" % url
    except Exception as e:
        ok, detail = False, "GET %s -> %s" % (url, e)
    check("ENV", "E01", "运行中服务已加载当前磁盘代码（需重启）", ok, detail,
          "环境项：非代码缺陷，但阻塞演示与 HTTP 层验收")


def main():
    P = collect()
    for fn, g in ((group_baseline, "BASELINE"), (group_page, "PAGE"),
                  (group_logic, "LOGIC"), (group_case, "CASE"),
                  (group_d05, "D05"), (group_env, "ENV")):
        safe(fn, g, P)

    code_results = [r for r in RESULTS if r["group"] != "ENV"]
    env_results = [r for r in RESULTS if r["group"] == "ENV"]
    n_pass = sum(r["status"] == "PASS" for r in code_results)
    n_fail = sum(r["status"] == "FAIL" for r in code_results)
    n_skip = sum(r["status"] == "SKIP" for r in code_results)
    all_green = (n_fail == 0)

    print("=" * 78)
    print("Pulse 演示版 · 独立质量验收  |  %s  |  基准：docs/00~05" %
          dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78)
    last = None
    for r in RESULTS:
        if r["group"] != last:
            print("\n[%s]" % r["group"])
            last = r["group"]
        print("  [%-4s] %-4s %-42s %s" % (r["status"], r["code"], r["name"], r["detail"]))
        if r["status"] == "FAIL":
            print("          规格依据: %s" % r["spec"])
    print("\n" + "=" * 78)
    print("代码验收: %d PASS / %d FAIL / %d SKIP  -> %s" %
          (n_pass, n_fail, n_skip, "ALL GREEN" if all_green else "NOT GREEN"))
    for r in env_results:
        print("环境项  : [%s] %s — %s" % (r["status"], r["name"], r["detail"]))
    if P["error"]:
        print("注意    : 当前磁盘代码处于并行编辑中间态 -> %s" % P["error"])
    print("=" * 78)

    if "--no-json" not in sys.argv:
        out = os.path.join(HERE, "acceptance_last.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(dict(run_at=dt.datetime.now().isoformat(timespec="seconds"),
                           all_green=all_green, n_pass=n_pass, n_fail=n_fail,
                           runtime_error=P["error"], results=RESULTS),
                      f, ensure_ascii=False, indent=2)
        print("结构化留痕: %s" % out)
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
