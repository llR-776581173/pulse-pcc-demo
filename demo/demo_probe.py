# -*- coding: utf-8 -*-
"""
demo_probe.py — 演示版可行性验证（只读，可复跑，不写任何源数据文件）

验证四件事，供《演示版归档》引用：
  1. 合成数据里能零改动筛出「沉寂后回流」与「截止日仍沉寂」的预置案例
  2. 改阈值后六个决策出口计数确实变化（证明 params 穿透与全量重算有效）
  3. 全量重算耗时基线（交互可行性）
  4. 现有 selftest.py 18/18 回归基线未受任何影响

运行:  python demo/demo_probe.py
"""
import os
import sys
import csv
import re
import time
import datetime as dt
import statistics as st
import subprocess
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
import pulse_core as core  # noqa: E402

DATA = os.environ.get("PULSE_DATA") or os.path.join(APP, "data")
if not os.path.isdir(DATA):
    DATA = r"D:\Work Buddy\工作空间\PCC_MA_PRD\data"
CUT = dt.date(2026, 9, 30)
LEGACY = not os.path.isdir(os.path.join(APP, "data"))


def read(name):
    with open(os.path.join(DATA, name), encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def line(t):
    print("\n" + "=" * 72 + "\n" + t + "\n" + "=" * 72)


line("0  ENVIRONMENT")
print("  data dir :", DATA, "(legacy fallback)" if LEGACY else "(local)")
print("  cut      :", CUT, "| rule version:", core.RULE_VERSION)
print("  source   : SYNTHETIC — none of the numbers below describe real customers.")

# ---------------------------------------------------------------- 1. cases
line("1  PRESET DEMO CASES — selected from existing synthetic data, ZERO data edits")
trs = read("transactions.csv")
byc = defaultdict(list)
for r in trs:
    byc[r["customer_id"]].append(
        (dt.date.fromisoformat(r["timestamp"][:10]), r["store_id"], float(r["amount"])))
for cid in byc:
    byc[cid].sort()

optin = defaultdict(set)
for r in read("consent.csv"):
    if r["status"] == "opt_in":
        optin[r["customer_id"]].add(r["channel"])

ac = core.classify_customers(DATA, CUT)
grp = {r["customer_id"]: r["group"] for r in ac["rows"]}

return_cases, silent_cases, healthy_cases = [], [], []
for cid, seq in byc.items():
    dates = [x[0] for x in seq]
    if len(dates) < 5:
        continue
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    med = st.median(gaps)
    if med <= 0:
        continue
    home = Counter(x[1] for x in seq).most_common(1)[0][0]
    tail = (CUT - dates[-1]).days
    # a long silence (>=1.5x own median, <=180d) followed by >=1 more purchase
    comebacks = [g for g in gaps[:-1]
                 if med < g <= 180 and g >= 1.5 * med]
    cb_gap = max(comebacks) if comebacks else 0
    rec = dict(cid=cid, home=home, n=len(dates), med=round(med, 1),
               first=str(dates[0]), last=str(dates[-1]),
               max_gap=max(gaps), tail=tail, group=grp.get(cid, "?"),
               channels=sorted(optin.get(cid, ())),
               cb_gap=cb_gap, comebacks=len(comebacks))
    # the whole silence -> return arc must be INSIDE the observable window
    if comebacks and 0 <= tail < 1.5 * med and rec["channels"]:
        return_cases.append(rec)
    elif 0 < tail <= core.FLAG_MAX_SILENCE and tail >= 1.5 * med and rec["channels"]:
        silent_cases.append(rec)
    elif tail <= med and rec["group"] in ("high", "medium", "low", "normal"):
        healthy_cases.append(rec)

print("  natural 'silence -> return' cases : %d" % len(return_cases))
print("  natural 'still silent at cut'     : %d" % len(silent_cases))
print("  natural 'on rhythm' cases        : %d" % len(healthy_cases))


def show(tag, cases, k=3):
    print("\n  [%s] top %d preset candidates" % (tag, min(k, len(cases))))
    for r in cases[:k]:
        print("    %s | %s | txn=%-3d med=%-5s | %s -> %s | cb_gap=%-3d tail=%-3d | group=%-10s ch=%s"
              % (r["cid"], r["home"], r["n"], r["med"], r["first"], r["last"],
                 r["cb_gap"], r["tail"], r["group"], ",".join(r["channels"][:2])))


show("A 回全链路: 进店->消费->沉寂->预警->回流 (arc inside cut)",
     sorted(return_cases, key=lambda r: (-r["cb_gap"], -r["n"])), 3)
show("B 流失预警: 沉寂中、可干预",
     sorted(silent_cases, key=lambda r: -r["tail"]), 3)
show("C 健康常客: 节奏正常对照组",
     sorted(healthy_cases, key=lambda r: r["n"]), 2)

# ------------------------------------------------------- 2. recompute works
line("2  PARAMETER OVERRIDE — six decision exits actually recompute")
p = {"DEV_THRESHOLD": 1.8, "FLAG_MAX_SILENCE": 120,
     "WARN_DAYS_H": 45, "FACE_BUDGET": 40.0}
t = time.time()
ac2 = core.classify_customers(DATA, CUT, params=p)
t_cls = time.time() - t
c1 = Counter(r["group"] for r in ac["rows"])
c2 = Counter(r["group"] for r in ac2["rows"])
print("  default :", dict(c1))
print("  changed :", dict(c2))
print("  exited  :", {k: c2[k] - c1[k] for k in c1 if c2[k] != c1[k]})
print("  exits unchanged in DEFINITION; only counts move. rows=%d" % len(ac2["rows"]))

# ------------------------------------------------------------- 3. timing
line("3  FULL RECOMPUTE TIMING (single-thread, stdlib)")
t = time.time(); core.classify_customers(DATA, CUT); t1 = time.time() - t
t = time.time(); core.store_drift_report(DATA, CUT, week=None); t2 = time.time() - t
t = time.time(); core.baseline_report(DATA, CUT); t3 = time.time() - t
t = time.time(); core.budget_advice(ac["rows"], cash_cap=3003, target=90.0); t4 = time.time() - t
print("  classify_customers : %.2fs" % t1)
print("  store_drift_report : %.2fs" % t2)
print("  baseline_report    : %.2fs" % t3)
print("  budget_advice      : %.2fs" % t4)
print("  TOTAL (today)      : %.2fs  -> interactive with a loading state" % (t1 + t2 + t3 + t4))
print("  PLAN: cache threshold-invariant base layer (txn sequence / home store /")
print("        median gap / interval cohort); re-run only state + decision layers.")
print("        Target < 2.0s after caching.")

# ------------------------------------------------------------ 4. regression
line("4  REGRESSION BASELINE — selftest.py must stay 18/18")
r = subprocess.run([sys.executable, "selftest.py"], cwd=APP,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
m = re.search(r"(\d+)/(\d+) checks passed", r.stdout or "")
print("  selftest exit code :", r.returncode)
print("  result             :", m.group(0) if m else "<not found>")
print("  NOTE: this probe never imports/modifies selftest.py and never writes data/.")

line("PROBE RESULT")
checks = [
    ("preset cases exist without data edits", len(return_cases) > 0 and len(silent_cases) > 0),
    ("parameter override changes exit counts", c1 != c2),
    ("six exit definitions preserved", set(c1) == set(c2) == {"C", "no_consent", "normal", "low", "high", "medium"}),
    ("recompute is interactive (<6s)", (t1 + t2 + t3 + t4) < 6.0),
    ("selftest 18/18 untouched", r.returncode == 0 and bool(m) and m.group(1) == m.group(2) == "18"),
]
for name, ok in checks:
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
print("\n  %d/%d probe checks passed" % (sum(1 for _, o in checks if o), len(checks)))
sys.exit(0 if all(o for _, o in checks) else 1)
