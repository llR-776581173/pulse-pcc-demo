# -*- coding: utf-8 -*-
"""
selftest.py  —  reproducibility checks for the Pulse scoring core.

Run:  python selftest.py

Prints the numbers the PRD claims, recomputed from data/, so a reviewer can
see whether the implementation actually reproduces them. Nothing here writes
to the source data directory.

Checks
  1. dataset scale + required tables
  2. PRD 4.1 validation: 25 stores / 41 complete weeks / 1,025 store-weeks,
     de-trend effect, -40% injection, fixed & P10 flag rates
  3. PRD 1 / 8 baselines: 82.8% at 2026-04-30, ~55% at 2026-07-31, and the
     number at the app's own cut (they are DIFFERENT cuts -- never mix them)
  4. decision layer: ranking, net-gain rule, consent gate, review load,
     live cash-closure table
"""

import os
import sys
import datetime as dt
import statistics as st
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pulse_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("PULSE_DATA") or os.path.join(HERE, "data")
if not os.path.isdir(DATA):
    DATA = r"D:\Work Buddy\工作空间\PCC_MA_PRD\data"
CUT = dt.date(2026, 9, 30)


def line(t):
    print("\n" + "=" * 72 + "\n" + t + "\n" + "=" * 72)


def ok(cond, msg):
    print(("  [PASS] " if cond else "  [FAIL] ") + msg)
    return bool(cond)


results = []

# ---------------------------------------------------------------- 1. scale
line("1  DATASET SCALE / ASSUMPTIONS AUDIT")
txn = core.load_transactions(DATA)
stores = core.load_stores(DATA)
members = core.load_members(DATA)
msg = core.load_messages(DATA)
end = max(r["d"].date() for r in txn)
print("  data dir        :", DATA)
print("  transactions    :", len(txn), "from", txn[0]["d"], "to", txn[-1]["d"])
print("  customers       :", len(members), "| stores:", len(stores),
      "| messages:", len(msg))
print("  seed / generator: 20261026 (see data generator header comments).")
print("  SYNTHETIC. Every figure below describes this dataset, not real customers.")
results.append(ok(len(txn) == 118365 and len(stores) == 25 and len(members) == 6000,
                  "6,000 customers / 118,365 txn / 25 stores"))

# ------------------------------------------------------- 2. PRD 4.1 validation
line("2  PRD 4.1 STORE-DRIFT VALIDATION (recomputed)")
s = core.store_drift_report(DATA, end, week=None)
print("  complete weeks  :", len(core._complete_weeks(end)),
      "| store-week obs :", s["total_store_weeks"])
print("  latest week     :", s["week"], s["week_date"], "| alerts:", s["n_alert"],
      "| fixed-rule firings:", s["n_firing_fixed"])
print("  flagged weeks   :", len([w for w in s["weeks_available"] if w.get("n_alert")]),
      "(PRD 4.1 suggests replaying one; Week 13 = 2026-01-31)")

# rebuild raw / specific series to measure rates and the injection test
byc = core._pre_cut_history(txn, end)
modal, baseline = {}, {}
for cid, lst in byc.items():
    modal[cid] = Counter(r["store"] for r in lst).most_common(1)[0][0]
    g = core._gaps([r["d"].date() for r in lst])
    if len(g) >= 3:
        baseline[cid] = st.median(g)
regulars = {c for c, b in baseline.items() if b <= core.BASELINE_REGULAR_CAP}
act = defaultdict(set)
for cid, lst in byc.items():
    if cid in regulars:
        for r in lst:
            act[(modal[cid], core._week_of(r["d"].date()))].add(cid)
complete = core._complete_weeks(end)
names = sorted(x["store_id"] for x in stores)
ser = {s_: {w: len(act.get((s_, w), set())) for w in complete} for s_ in names}


def series(mod=None):
    raw = defaultdict(dict)
    for s_ in names:
        v = dict(ser[s_])
        if mod and mod[0] == s_:
            for w in mod[1]:
                v[w] = round(v[w] * 0.6)
        for i in range(core.MIN_WEEKS, len(complete)):
            w = complete[i]
            a = sum(v[complete[i - k]] for k in range(0, 4)) / 4.0
            b = sum(v[complete[i - k]] for k in range(4, 12)) / 8.0
            if b > 0:
                raw[s_][w] = a / b - 1.0
    weeks = sorted(set().union(*[set(x) for x in raw.values()]))
    chain = {w: st.median([raw[s_][w] for s_ in names if w in raw[s_]]) for w in weeks}
    spec = {s_: {w: raw[s_][w] - chain[w] for w in raw[s_]} for s_ in raw}
    return raw, spec, weeks


raw, spec, weeks = series()
obs = sum(len(v) for v in spec.values())
fixed = sum(1 for s_, v in spec.items() for x in v.values() if x < core.ALERT_FIXED)
p10 = 0
for s_, v in spec.items():
    vals = sorted(v.values())
    q = vals[max(0, int(0.10 * len(vals)) - 1)]
    p10 += sum(1 for x in v.values() if x < q)
print("  store-week obs  :", obs, "(PRD claims 1,025)")
print("  FIXED rate      : %.1f%% (%d)  | PRD claims 4.9%%" % (100 * fixed / obs, fixed))
print("  P10 rate        : %.1f%% (%d)  | PRD claims 9.8%%" % (100 * p10 / obs, p10))
results.append(ok(obs == 1025, "1,025 store-week observations"))
print("  NOTE: flag rates do NOT exactly reproduce the PRD's 4.9% / 9.8% --")
print("        either align the implementation or correct the PRD figures.")

# common-mode injection: a chain-wide dip, no de-trend => everything false-alarms
w0 = complete[-1]
fake = {s_: dict(ser[s_]) for s_ in names}
for s_ in names:
    for k in range(0, 4):
        fake[s_][complete[len(complete) - 1 - k]] = round(fake[s_][complete[len(complete) - 1 - k]] * 0.8)
no_detrend = sum(1 for s_ in names
                 if (sum(fake[s_][complete[len(complete) - 1 - k]] for k in range(0, 4)) / 4.0) /
                    max(1, (sum(fake[s_][complete[len(complete) - 5 - k]] for k in range(0, 8)) / 8.0)) - 1.0
                    < core.ALERT_FIXED)
print("  chain-wide -20%% dip WITHOUT de-trend: %d/%d stores false-alarm" % (no_detrend, len(names)),
      "(PRD claims 24/25)")

# single-store -40% injection
inj_store = names[0]
inj_weeks = complete[-4:]
_, spec_i, weeks_i = series((inj_store, inj_weeks))
wi = weeks_i[-1]
print("  -40%% 4-week injection into %s -> specific_drift = %.3f (PRD: -0.445)"
      % (inj_store, spec_i[inj_store][wi]))
results.append(ok(spec_i[inj_store][wi] < -0.30, "injection fires the alert unambiguously"))

# ------------------------------------------------------------- 3. baselines
line("3  PRD 1 / 8 BASELINES — DIFFERENT CUTS, NEVER ONE TABLE")
for c in ("2026-04-30", "2026-07-31", "2026-09-30"):
    b = core.baseline_report(DATA, dt.date.fromisoformat(c))
    print("  cut %s : flag pool %5.1f%% (n=%4d) | silent >=30d %5.1f%% (n=%4d) | "
          ">=4-gap silent %5.1f%% | excluded contacted %d"
          % (c, b["flag_return"] or 0, b["flag_n"], b["silent_return"] or 0,
             b["silent_n"], b["silent4_return"] or 0, b["contacted_excluded"]))
b4 = core.baseline_report(DATA, dt.date(2026, 4, 30))
results.append(ok(b4["flag_return"] == 82.8, "82.8% reproduces at 2026-04-30 (excluding contacted)"))
print("  NOTE: the app's own cut is 2026-09-30 -> its live number is 78.5%, not 82.8%.")
print("        The baseline card shows the cut, n and exclusion rule. Do not mix cuts.")

# --------------------------------------------------------- 4. decision layer
line("4  DECISION LAYER / REVIEW LOAD / CASH CLOSURE")
ac = core.classify_customers(DATA, CUT)
rows = ac["rows"]
rev = core.review_load(rows)
net = [r["net_gain"] for r in rows]
print("  scored          :", len(rows), "| E50 HK$", ac["E50"], "| E75 HK$", ac["E75"])
print("  groups          :", dict(Counter(r["group"] for r in rows)))
print("  approvable      :", rev["approvable"], "| no-spend:", rev["no_spend"])
print("  review load     :", rev["minutes"], "min /", rev["hours"], "h (batch-approval rule)")
print("                    if EVERY approvable row needed a human written reason:",
      rev["full_minutes"], "min /", rev["full_hours"], "h -- the honest bottleneck")
print("                    PRD narrative: 30-40 written-reason rows ~ 1 hour")
results.append(ok(all(net[i] >= net[i + 1] for i in range(len(net) - 1)),
                  "action list is actually sorted by expected net gain"))
results.append(ok(all(r["can_approve"] == (r["group"] in ("high", "medium") and r["net_gain"] > 0)
                     for r in rows), "rule decides amount; no-negative-gain approvals"))
print("  net_gain        :", ac["net_gain_note"])

sv = core.savings_calc(rows)
print("  cash closure    : %d no-spend x avg self-return %.1f%% -> %d avoided coupons"
      % (sv["no_spend_count"], sv["avg_self_return"], sv["avoided_coupons"]))
print("                    face %.0f x redeem %.2f x margin %.2f = HK$%.2f/coupon -> HK$%d/week"
      % (sv["face"], sv["redemption"], sv["margin"], sv["cost_per_coupon"], sv["weekly_saving"]))
sv2 = core.savings_calc(rows, face=20.0)
print("                    if face is changed to HK$20 -> HK$%d/week (live parameter)" % sv2["weekly_saving"])
print("                    PRD 4 scope (%d coupons, %d wasted): face HK$%d / cash HK$%d"
      % (sv["prd_coupons"], sv["prd_wasted"], sv["prd_face_saving"], sv["prd_cash_saving"]))
results.append(ok(sv2["weekly_saving"] != sv["weekly_saving"], "cash table is live, not hardcoded"))

sample = next((r for r in rows if r["can_approve"]), None)
if sample:
    good, basis, why = core.check_consent(DATA, sample["customer_id"],
                                          sample["suggested_channel"], dt.datetime(2026, 11, 19))
    print("  consent gate    : sample %s / %s -> %s (%s)"
          % (sample["customer_id"], sample["suggested_channel"], good, why))
    bad, _, why2 = core.check_consent(DATA, sample["customer_id"], "sms", dt.datetime(2026, 11, 19))
    results.append(ok(good and not bad, "consent gate accepts valid channel, blocks invalid one"))

line("5  STORE GATE — SUPPRESSION IS A SIGNED DECISION WITH A PRICE")
base = core.budget_plan(rows, total_coupons=350, face=44.0)
p7 = core.budget_plan(rows, total_coupons=350, face=44.0, suppressed_stores=["PCC007"])
p45 = core.budget_plan(rows, total_coupons=350, face=44.0,
                       suppressed_stores=["PCC019", "PCC010", "PCC020", "PCC004",
                                          "PCC024", "PCC011", "PCC018"])
print("  no suppression : funded %d / HK$%d | expected net gain HK$%d"
      % (base["funded_n"], base["funded_amt"], base["gain"]))
for tag, p in (("PCC007 (W13, 1 store)", p7), ("W45 alerts (7 stores)", p45)):
    print("  %-22s: funded %d / HK$%d | gain HK$%d (%+.2f%%) | swapped %d | deferred %d / HK$%d"
          % (tag, p["funded_n"], p["funded_amt"], p["gain"], p["gain_delta_pct"],
             p["swapped_n"], p["deferred_n"], p["deferred_amt"]))
results.append(ok(base["gain_delta"] == 0 and base["deferred_n"] == 0,
                  "no signed suppression -> no price, no deferred list"))
results.append(ok(p7["funded_amt"] == base["funded_amt"],
                  "suppression does NOT save money: spend stays HK$15,400"))
results.append(ok(p7["gain_delta"] < 0 and p7["swapped_n"] > 0,
                  "suppression moves coupons to lower-value customers (price is negative)"))
results.append(ok(p45["gain_delta"] < p7["gain_delta"],
                  "the more stores are suppressed, the bigger the loss (W45 > W13)"))
results.append(ok(p7["deferred_n"] <= p7["suppressed_n"]
                  and all(d["store_id"] == "PCC007" for d in p7["deferred"]),
                  "deferred list only contains that store's customers who would have been funded"))
print("  -> this is why the rule alert must NOT auto-suppress: it would silently")
print("     destroy 0.9%-11.3% of expected gain and save nothing.")

line("6  NEXT-WEEK BUDGET ADVICE — TWO EXTERNAL KNOBS + ONE HARD STOP")
adv = core.budget_advice(rows, cash_cap=3003, target=90.0)
sat = adv["saturation_coupons"]
print("  demand %d / HK$%d | cash HK$%.2f/coupon | saturation %d coupons"
      % (adv["demand_n"], adv["demand_amt"], adv["cash_per_coupon"], sat))
print("  target 90%% -> %d coupons (%.1f%%) | cash HK$3,003 -> %d coupons (%.1f%%)"
      % (adv["by_target"]["coupons"], adv["by_target"]["coverage"],
         adv["by_cash"]["coupons"], adv["by_cash"]["coverage"]))
print("  recommended %d coupons (binding: %s) | %.1f%% | medium %d/%d funded"
      % (adv["recommended_coupons"], adv["binding"], adv["recommended"]["coverage"],
         adv["recommended"]["medium"], adv["demand_medium"]))
results.append(ok(sat > 0 and adv["grid"][-1]["coverage"] == 100.0
                  and core.budget_plan(rows, sat - 1, 44.0)["funded_amt"] < adv["demand_amt"],
                  "saturation is the SMALLEST coupon count covering everyone"))
results.append(ok(core.budget_advice(rows, cash_cap=1e9, target=100.0)["recommended_coupons"] == sat,
                  "unlimited cash still cannot exceed saturation"))
bt = adv["by_target"]["coupons"]
results.append(ok(adv["by_target"]["coverage"] >= 90.0
                  and core.budget_plan(rows, bt - 1, 44.0)["funded_amt"] < adv["demand_amt"] * 0.9,
                  "coverage target: minimal coupon count reaches 90%, one fewer misses"))
results.append(ok(adv["by_cash"]["coupons"] == 350 and adv["by_cash"]["coverage"] == 42.8,
                  "cash ceiling HK$3,003 -> exactly 350 coupons (no float truncation)"))
cs = [p["coverage"] for p in adv["grid"]]
results.append(ok(all(cs[i] <= cs[i + 1] for i in range(len(cs) - 1))
                  and adv["recommended_coupons"] <= sat
                  and all(rows[i]["net_gain"] >= rows[i + 1]["net_gain"]
                          for i in range(len(rows) - 1)),
                  "advice curve is monotone, capped, and never mutates the person layer"))
print("  -> the model cannot set the total: every approvable row has net_gain > 0,")
print("     so only cash, the coverage target, or saturation can stop it.")

line("RESULT")
print("  %d/%d checks passed" % (sum(results), len(results)))
print("  Failures are printed above with the PRD figure they disagree with.")
print()
print("  OPEN ITEMS (bring these to the tutor -- they are NOT code bugs):")
print("   1. PRD 4.1 says fixed-threshold rate 4.9% / own-P10 rate 9.8%;")
print("      this implementation measures %.1f%% / %.1f%% on the same 1,025 store-weeks."
      % (100.0 * fixed / obs, 100.0 * p10 / obs))
print("      -> Is the PRD figure a different de-trend definition, or should the PRD be corrected?")
print("   2. PRD 4.1 says a chain-wide dip false-alarms 24/25 stores without de-trend;")
print("      this build measures %d/25. Same question." % no_detrend)
print("   3. PRD 4.1 says a -40%% injection yields -0.445; this build yields %.3f."
      % spec_i[inj_store][wi])
print("   4. PRD 4 ~HK$1,500/week is a FACE-VALUE illustration on a 350-coupon budget;")
print("      the live table shows both that scope and the full-list scope. Which is expected?")
print("   5. campaign_id CP007 / CP003 in the shared schema do not match the HK$50 / HK$30")
print("      rule caps. Should Module 2 create Pulse-specific campaigns, or should caps change?")
sys.exit(0 if all(results) else 1)
