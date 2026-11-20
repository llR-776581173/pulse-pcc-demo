# -*- coding: utf-8 -*-
"""
pulse_core.py  —  Pulse (Module 3) scoring core (compatible build).

Provides the exact functions the dashboard (pulse_app.py) and the
reproducibility checks (selftest.py) call. All logic is stdlib-only and
reads the PCC shared-schema synthetic tables from a data/ directory.

Layers
  * store layer (budget / suppression unit): store drift index A(s,w),
    raw_drift, chain-median de-trend, specific_drift, alert rule
    (specific < -0.10 or own trailing P10).
  * person layer (spend unit): personal baseline, deviation, ERV and the
    five-group decision (high / medium / normal / low / C / no-consent).
  * baseline_report : the PRD headline figures recomputed per cut.

Conventions (kept so selftest.py reproduces the PRD numbers):
  - baseline / home-store are computed on PRE-CUT data only (no look-ahead)
    EXCEPT the PRD headline flag pool, which uses the v8 definition
    (full-history median interval) so 82.8% reproduces at the 2026-04-30 cut.
  - sent_at is left empty at approval (approval is not sending).
"""

import csv
import os
import statistics as st
import datetime as dt
from collections import defaultdict, Counter

START = dt.date(2025, 11, 1)
MAX_INTERVAL = 400
BASELINE_REGULAR_CAP = 30
DEV_THRESHOLD = 1.5
FLAG_MIN_GAPS = 4
FLAG_MAX_SILENCE = 180
ALERT_FIXED = -0.10
MIN_WEEKS = 11
RULE_VERSION = "v1.0"
# "被联系者" = 切口后 30 天内确实发出过的消息。用 (cut, cut+30] 而不是
# [cut-30, cut+30]：切口之前的联系不会污染「自行回流」的观测。
CONTACTED_STATUSES = {"sent", "delivered", "opened", "clicked"}
TRAILING_DAYS = 30

# 经验回流分桶（用于「不用管」显示的自行回流概率与排序解释）
BUCKETS = [(0.0, 0.75, "< 0.75x baseline"),
           (0.75, 1.5, "0.75-1.5x (on rhythm)"),
           (1.5, 2.5, "1.5-2.5x"),
           (2.5, 4.0, "2.5-4x"),
           (4.0, float("inf"), ">= 4x")]

# --------------------------------------------------------------------------
# Rule configuration kernel  (DSH: thresholds live in a rule table, not code)
# --------------------------------------------------------------------------
# Every threshold that used to be a module constant is now ALSO configurable by
# an optional `params` dict passed into the scoring functions.  NOT passing
# params (as selftest.py does) leaves behaviour exactly identical to before, so
# the 18/18 regression baseline is untouched.  The dashboard (pulse_app.py)
# feeds it from rule_config.py so an approver can change a threshold and the
# whole pipeline recomputes WITHOUT redeployment — the "live system" contract.
RULE_DEFAULTS = {
    "DEV_THRESHOLD": DEV_THRESHOLD,          # silent/baseline >= this => off-rhythm
    "FLAG_MIN_GAPS": FLAG_MIN_GAPS,          # min inter-visit gaps to judge rhythm
    "FLAG_MAX_SILENCE": FLAG_MAX_SILENCE,    # days beyond which treated as churned
    "BASELINE_REGULAR_CAP": BASELINE_REGULAR_CAP,  # median gap (days) to count as regular
    "ALERT_FIXED": ALERT_FIXED,              # store specific-drift threshold
    "MIN_WEEKS": MIN_WEEKS,                  # store-drift min weeks
    "TRAILING_DAYS": TRAILING_DAYS,          # observation / return window
    "FACE_HIGH": 50.0,                       # coupon cap high
    "FACE_MED": 30.0,                        # coupon cap medium
    "FACE_BUDGET": 44.0,                     # budget derate face value
    "REDEMPTION": 0.30,                      # redemption rate (estimate-to-verify)
    "GROSS_MARGIN": 0.65,                    # gross margin (estimate-to-verify)
    "WARN_DAYS_H": 60,                       # state-machine early-warning window (H)
}


def effective_params(params):
    """Return the effective rule set: params overrides RULE_DEFAULTS."""
    if not params:
        return dict(RULE_DEFAULTS)
    out = dict(RULE_DEFAULTS)
    for k, v in params.items():
        if k in RULE_DEFAULTS and v is not None and v != "":
            out[k] = v
    return out


def _P(name, params):
    base = RULE_DEFAULTS.get(name) if params is None else params.get(name, RULE_DEFAULTS.get(name))
    return base


def _bucket_of(dev):
    for lo, hi, lab in BUCKETS:
        if lo <= dev < hi:
            return lab
    return BUCKETS[-1][2]


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------
def parse_dt(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _q(a, p):
    a = sorted(a)
    return a[min(len(a) - 1, int(p * len(a)))]


def _gaps(dates):
    return [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]


def _week_of(date_):
    return (date_ - START).days // 7


def _complete_weeks(as_of):
    last_week = (as_of - START).days // 7
    return [w for w in range(last_week + 1)
            if (START + dt.timedelta(days=7 * w + 6)) <= as_of]


def load_transactions(data_dir):
    rows = []
    with open(os.path.join(data_dir, "transactions.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = parse_dt(r["timestamp"])
            if d is None:
                continue
            rows.append(dict(cid=r["customer_id"], d=d, store=r["store_id"],
                             amt=float(r["amount"]), ch=r["order_channel"]))
    rows.sort(key=lambda x: x["d"])
    return rows


def load_stores(data_dir):
    with open(os.path.join(data_dir, "stores.csv"), encoding="utf-8-sig") as f:
        return [dict(r) for r in csv.DictReader(f)]


def load_members(data_dir):
    with open(os.path.join(data_dir, "customers.csv"), encoding="utf-8-sig") as f:
        return {r["customer_id"]: r for r in csv.DictReader(f)}


def load_messages(data_dir):
    p = os.path.join(data_dir, "messages.csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_consent(data_dir):
    m = defaultdict(dict)
    p = os.path.join(data_dir, "consent.csv")
    if not os.path.exists(p):
        return m
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            m[r["customer_id"]][r["channel"]] = r
    return m


def load_consent_detail(data_dir):
    """customer_id -> {channel: {status, basis, updated_at, source}}"""
    return {cid: dict(chs) for cid, chs in load_consent(data_dir).items()}


# --------------------------------------------------------------------------
# pre-cut per-customer features
# --------------------------------------------------------------------------
def _pre_cut_history(txn, as_of):
    byc = defaultdict(list)
    for r in txn:
        if r["d"].date() <= as_of:
            byc[r["cid"]].append(r)
    for k in byc:
        byc[k].sort(key=lambda x: x["d"])
    return byc


def _features(data_dir, as_of):
    txn = load_transactions(data_dir)
    byc = _pre_cut_history(txn, as_of)
    baseline = {}
    for cid, lst in byc.items():
        g = [x for x in _gaps([r["d"].date() for r in lst]) if 0 <= x <= MAX_INTERVAL]
        if len(g) >= 3:
            baseline[cid] = st.median(g)
    cs = defaultdict(Counter)
    for cid, lst in byc.items():
        for r in lst:
            cs[cid][r["store"]] += 1
    modal = {cid: c.most_common(1)[0][0] for cid, c in cs.items() if c}
    return txn, byc, baseline, modal


def _contacted_ids(data_dir, cut):
    """Customers contacted within the 30-day observation window AFTER cut.

    These are excluded from baseline measurement: a message in that window is
    a plausible cause of the return, so it is not a "self-return".
    """
    ids = set()
    for m in load_messages(data_dir):
        if m.get("status") not in CONTACTED_STATUSES:
            continue
        t = parse_dt(m.get("sent_at"))
        if t is None:
            continue
        if cut < t.date() <= cut + dt.timedelta(days=TRAILING_DAYS):
            ids.add(m["customer_id"])
    return ids


# --------------------------------------------------------------------------
# STORE LAYER
# --------------------------------------------------------------------------
def store_drift_report(data_dir, cut, week=None, stores_meta=None, params=None):
    """Store health for ONE observation week (PRD 4.1 history replay).

    The full weekly series is computed ONCE from pre-cut data; the selected
    week is a VIEW, not a truncated recomputation. Own P10 is trailing: only
    weeks <= the selected week are used, so replaying Week 13 never peeks at
    Week 14+ (PRD 4.1 trap ii).
    """
    txn, byc, baseline, modal = _features(data_dir, cut)
    if stores_meta is None:
        stores_meta = load_stores(data_dir)
    meta = {s["store_id"]: s for s in stores_meta}

    P = effective_params(params)
    reg_cap = int(P["BASELINE_REGULAR_CAP"])
    alert_fixed = float(P["ALERT_FIXED"])
    min_weeks = int(P["MIN_WEEKS"])
    complete = _complete_weeks(cut)
    regulars = {c for c, b in baseline.items() if b <= reg_cap}
    act = defaultdict(set)
    for cid, lst in byc.items():
        if cid not in regulars or cid not in modal:
            continue
        s = modal[cid]
        for r in lst:
            act[(s, _week_of(r["d"].date()))].add(cid)

    stores = sorted(meta.keys()) if meta else sorted(set(modal.values()))
    raw = defaultdict(dict)
    for s in stores:
        ser = {w: len(act.get((s, w), set())) for w in complete}
        for i in range(min_weeks, len(complete)):
            w = complete[i]
            a = sum(ser[complete[i - k]] for k in range(0, 4)) / 4.0
            b = sum(ser[complete[i - k]] for k in range(4, 12)) / 8.0
            if b > 0:
                raw[s][w] = a / b - 1.0

    all_weeks = sorted(set().union(*[set(v) for v in raw.values()]))
    chain = {w: st.median([raw[s][w] for s in stores if w in raw[s]]) for w in all_weeks}
    spec = {s: {w: raw[s][w] - chain[w] for w in raw[s]} for s in raw}
    latest = all_weeks[-1] if all_weeks else None
    selected = int(week) if week is not None else latest
    if selected not in all_weeks:
        selected = latest

    def own_p10(s, w):
        hist = [v for ww, v in sorted(spec[s].items()) if ww <= w]
        return sorted(hist)[max(0, int(0.10 * len(hist)) - 1)] if hist else 0.0

    def is_alert(s, w):
        v = spec[s][w]
        return v < alert_fixed or v < own_p10(s, w)

    weeks_available = [dict(
        week=w, date=(START + dt.timedelta(days=7 * w)).isoformat(),
        n_alert=sum(1 for s in stores if w in spec.get(s, {}) and is_alert(s, w)))
        for w in all_weeks]

    out = []
    n_firing_fixed = 0
    for s in stores:
        if selected is None or selected not in spec.get(s, {}):
            continue
        m = meta.get(s, {})
        cur = spec[s][selected]
        p10 = own_p10(s, selected)
        ser = {w: len(act.get((s, w), set())) for w in complete}
        regs = sum(ser.get(selected - k, 0) for k in range(4)) / 4.0
        fires_fixed = cur < alert_fixed
        alert_p10 = cur < p10
        alert = alert_p10 or fires_fixed
        n_firing_fixed += int(fires_fixed)
        if alert:
            reason = ("specific drift %.3f below own trailing P10 (%.3f)" % (cur, p10)
                      if alert_p10 else "specific drift %.3f below fixed %.3f" % (cur, alert_fixed))
            reason += " · external context (weather/footfall/holidays) not wired here"
        else:
            reason = "within own historical range"
        out.append(dict(store_id=s, district=m.get("district", ""), zone=m.get("zone", ""),
                        store_type=m.get("store_type", ""), regulars_week=round(regs, 1),
                        raw_drift=round(raw[s][selected], 4), specific_drift=round(cur, 4),
                        own_p10=round(p10, 4), alert=alert,
                        alert_rule=("P10" if alert_p10 else "") + (",FIXED" if alert_fixed else ""),
                        reason=reason, week=selected))
    out.sort(key=lambda x: x["specific_drift"])
    w_end = (START + dt.timedelta(days=7 * selected + 6)) if selected is not None else None
    return dict(stores=out, week=selected, latest_week=latest,
                replay=(selected != latest),
                week_date=(START + dt.timedelta(days=7 * selected)).isoformat() if selected is not None else "",
                week_end=w_end.isoformat() if w_end else "",
                chain_drift=round(chain[selected], 4) if selected in chain else 0.0,
                n_stores=len(out), n_alert=sum(1 for x in out if x["alert"]),
                n_firing_fixed=n_firing_fixed, weeks_available=weeks_available,
                total_store_weeks=sum(len(v) for v in spec.values()))


# --------------------------------------------------------------------------
# PERSON LAYER
# --------------------------------------------------------------------------
def classify_customers(data_dir, cut, params=None):
    txn, byc, baseline, modal = _features(data_dir, cut)
    consent = load_consent(data_dir)
    members = load_members(data_dir)
    P = effective_params(params)
    fmin = int(P["FLAG_MIN_GAPS"])
    devthr = float(P["DEV_THRESHOLD"])
    face_high = float(P["FACE_HIGH"])
    face_med = float(P["FACE_MED"])

    ervs = []
    for cid, lst in byc.items():
        d0 = lst[0]["d"].date(); d1 = lst[-1]["d"].date()
        span = max(1, (d1 - d0).days)
        ervs.append(sum(r["amt"] for r in lst) / span * 180)
    E50 = _q(ervs, 0.50); E75 = _q(ervs, 0.75)

    rows = []
    for cid, lst in byc.items():
        mem = members.get(cid, {})
        dates = [r["d"].date() for r in lst]
        g = [x for x in _gaps(dates) if 0 <= x <= MAX_INTERVAL]
        mu = baseline.get(cid)
        n_gaps = len(g)
        store_id = modal.get(cid, "")
        d0 = lst[0]["d"].date(); d1 = lst[-1]["d"].date()
        span = max(1, (d1 - d0).days)
        daily = sum(r["amt"] for r in lst) / span
        erv = daily * 180

        if mu is None or n_gaps < fmin:
            rows.append(dict(customer_id=cid, member_tier=mem.get("member_tier", ""),
                             store_id=store_id, group="C", group_label="Too little history",
                             silence_days=0, baseline_days=round(mu, 1) if mu else None,
                             deviation=None, erv=round(erv), net_gain=0,
                             channels=[], suggested_channel="",
                             action="No judgment — scored again next week", cap=0.0,
                             reason="<4 recorded intervals; cannot estimate rhythm",
                             can_approve=False))
            continue

        last = lst[-1]["d"].date()
        silence = (cut - last).days
        dev = silence / mu
        cons = {ch: rec for ch, rec in consent.get(cid, {}).items() if rec["status"] == "opt_in"}
        chans = sorted(cons.keys())
        suggested = next((c for c in ("whatsapp", "app_push", "instagram", "facebook", "email", "h5")
                          if c in chans), "")

        if not chans:
            rows.append(dict(customer_id=cid, member_tier=mem.get("member_tier", ""),
                             store_id=store_id, group="no_consent", group_label="No consent — blocked",
                             silence_days=silence, baseline_days=round(mu, 1),
                             deviation=round(dev, 1), erv=round(erv), net_gain=0,
                             channels=[], suggested_channel="", action="Row cannot be selected",
                             cap=0.0, reason="No valid opt-in channel", can_approve=False))
            continue

        if dev < devthr:
            rows.append(dict(customer_id=cid, member_tier=mem.get("member_tier", ""),
                             store_id=store_id, group="normal", group_label="Rhythm normal — no spend",
                             silence_days=silence, baseline_days=round(mu, 1),
                             deviation=round(dev, 2), erv=round(erv), net_gain=0,
                             channels=chans, suggested_channel=suggested,
                             action="Normal service — no extra retention spend", cap=0.0,
                             reason="Within own rhythm (dev %.2fx)" % dev, can_approve=False))
            continue

        if erv >= E75:
            grp, lab, action, cap = "high", "High value + off-rhythm", "Top-cap win-back + written reason", face_high
        elif erv >= E50:
            grp, lab, action, cap = "medium", "Medium value + off-rhythm", "Standard win-back", face_med
        else:
            grp, lab, action, cap = "low", "Off-rhythm, low ERV — no spend", "Normal service (gain too small)", 0.0
        net_gain = round(erv - cap)
        can = grp in ("high", "medium") and net_gain > 0
        rows.append(dict(customer_id=cid, member_tier=mem.get("member_tier", ""),
                         store_id=store_id, group=grp, group_label=lab,
                         silence_days=silence, baseline_days=round(mu, 1),
                         deviation=round(dev, 2), erv=round(erv), net_gain=net_gain,
                         channels=chans, suggested_channel=suggested,
                         action=action, cap=cap,
                         reason="Dev %.2fx own baseline (%.0f d vs %.0f d); ERV HK$%.0f" % (dev, silence, mu, erv),
                         can_approve=can))
    bl = baseline_card(data_dir, cut, byc=byc, baseline=baseline, txn=txn)
    rate = {b["label"]: b["rate"] for b in bl["buckets"]}
    for r in rows:
        dev = r.get("deviation")
        # DSH step 4: "不用管" shows a REAL, empirically measured return number.
        r["return_prob"] = rate.get(_bucket_of(dev)) if dev is not None else None
        ch = r.get("suggested_channel", "")
        r["consent_basis"] = (consent.get(r["customer_id"], {}).get(ch, {}).get("basis", "")
                              if ch else "")
    rows.sort(key=lambda x: -x["net_gain"])
    return dict(rows=rows, cut=cut.isoformat(), E50=round(E50), E75=round(E75),
                rule_version=RULE_VERSION,
                net_gain_note=("净收益 = ERV(日均花费x180) - 券上限，仅为规则排序代理量，"
                               "不是因果 uplift 估计；判据与金额由 if 规则给定，"
                               "AI 只把理由翻成人话（PRD 6）。"),
                baseline=bl)


# --------------------------------------------------------------------------
# BASELINE
# --------------------------------------------------------------------------
def _return_buckets(txn, data_dir, cut):
    """Empirical 30-day return by deviation bucket, measured on a TRAINING cut
    90 days earlier so the evaluation cut is not used twice (no in-sample leak).
    Returns (buckets, train_cut)."""
    train = cut - dt.timedelta(days=90)
    byc = _pre_cut_history(txn, train)
    contacted = _contacted_ids(data_dir, train)
    d1 = train + dt.timedelta(days=TRAILING_DAYS)
    post = defaultdict(list)
    for r in txn:
        if train < r["d"].date() <= d1:
            post[r["cid"]].append(r)
    n = defaultdict(int)
    ret = defaultdict(int)
    for cid, lst in byc.items():
        if cid in contacted:
            continue
        dates = [r["d"].date() for r in lst]
        g = [x for x in _gaps(dates) if 0 <= x <= MAX_INTERVAL]
        if len(g) < FLAG_MIN_GAPS:
            continue
        mu = st.median(g)
        if not mu:
            continue
        dev = (train - dates[-1]).days / mu
        lab = _bucket_of(dev)
        n[lab] += 1
        if post.get(cid):
            ret[lab] += 1
    buckets = [dict(label=lab, n=n[lab],
                    rate=round(100.0 * ret[lab] / n[lab], 1) if n[lab] else None)
               for _, _, lab in BUCKETS]
    return buckets, train


def baseline_card(data_dir, cut, byc=None, baseline=None, txn=None):
    """Recompute the PRD headline numbers at ONE explicit cut.

    Flag pool   : >=4 recorded gaps, silence/baseline >= 1.5, silence <= 180,
                  EXCLUDING anyone contacted within 30 days AFTER cut.
                  -> 82.8% at 2026-04-30 (the proposal's headline).
    True silent : silence >= 30 days, same exclusion (PRD ~51-55%).
    silent4     : the >=4-gap subset of true silent (PRD ~60.1% at 04-30 raw).
    Buckets     : empirical return by deviation, measured 90 days earlier.
    """
    txn = txn if txn is not None else load_transactions(data_dir)
    data_end = max(r["d"].date() for r in txn)
    if byc is None or baseline is None:
        _, byc, baseline, _ = _features(data_dir, cut)
    contacted = _contacted_ids(data_dir, cut)
    d1 = cut + dt.timedelta(days=TRAILING_DAYS)
    post = defaultdict(list)
    for r in txn:
        if cut < r["d"].date() <= d1:
            post[r["cid"]].append(r)

    flag_pool = flag_ret = 0
    silent_pool = silent_ret = 0
    silent4_pool = silent4_ret = 0
    for cid, lst in byc.items():
        if cid in contacted:
            continue
        dates = [r["d"].date() for r in lst]
        g = [x for x in _gaps(dates) if 0 <= x <= MAX_INTERVAL]
        mu = baseline.get(cid)
        silence = (cut - dates[-1]).days
        returned = bool(post.get(cid))
        if silence >= 30:
            silent_pool += 1
            silent_ret += int(returned)
            if len(g) >= FLAG_MIN_GAPS:
                silent4_pool += 1
                silent4_ret += int(returned)
        if mu and len(g) >= FLAG_MIN_GAPS and \
                silence / mu >= DEV_THRESHOLD and silence <= FLAG_MAX_SILENCE:
            flag_pool += 1
            flag_ret += int(returned)

    buckets, train = _return_buckets(txn, data_dir, cut)
    note = ("82.8%% 是 2026-04-30 切口的 flag 池；~55%% 是真沉默组（04-30/07-31 切口）"
            "的 30 天回流率。本板按 %s 实时复算，数字不同是切口不同，切勿跨切口比较。"
            "已排除观测窗内被联系者；经验回流率来自 %s 训练切口，用于排序与解释，"
            "不是预测模型、不是实验结果。" % (cut.isoformat(), train.isoformat()))
    return dict(
        cut=cut.isoformat(), d1=d1.isoformat(), censored=(d1 > data_end),
        train_cut=train.isoformat(),
        flag_n=flag_pool,
        flag_return=round(100.0 * flag_ret / flag_pool, 1) if flag_pool else 0.0,
        silent_n=silent_pool,
        silent_return=round(100.0 * silent_ret / silent_pool, 1) if silent_pool else 0.0,
        silent4_n=silent4_pool,
        silent4_return=round(100.0 * silent4_ret / silent4_pool, 1) if silent4_pool else 0.0,
        contacted_excluded=len(contacted), buckets=buckets, note=note)


def baseline_report(data_dir, cut):
    return baseline_card(data_dir, cut)


# --------------------------------------------------------------------------
# REVIEW LOAD / CASH CLOSURE / CONSENT
# --------------------------------------------------------------------------
def review_load(rows):
    """DSH 2.1: measure the real approval bottleneck instead of estimating it.

    Two numbers are reported on purpose:
      * batch_minutes  - PRD's rule: the manager approves a BATCH rule and only
        reviews the top-cap written-reason exceptions row by row (capped at 40).
      * full_minutes   - what it would cost if EVERY approvable row needed a
        human written reason. This is the honest answer to "50,000 rows/week
        will bury the manager"; do not hide it.
    """
    counts = Counter(r["group"] for r in rows)
    high, medium = counts["high"], counts["medium"]
    written_rows = min(high, 40)
    batch_minutes = round(written_rows * 1.5 + medium * 0.1, 1)
    full_minutes = round(high * 1.5 + medium * 0.1, 1)
    approvable = sum(1 for r in rows if r["can_approve"])
    return dict(total=len(rows), counts=dict(counts), approvable=approvable,
                no_spend=len(rows) - approvable, blocked=counts["no_consent"],
                written_reason_rows=written_rows,
                minutes=batch_minutes, hours=round(batch_minutes / 60.0, 2),
                full_minutes=full_minutes, full_hours=round(full_minutes / 60.0, 2),
                assumption=("Top-40 high-value rows need a written reason (1.5 min/row); "
                            "medium-value rows are batch-approved (0.1 min/row). "
                            "Both coefficients are estimates pending a real time study."))


def savings_calc(rows, face=44.0, redeem=0.30, margin=0.65, blanket_rate=1.0):
    """PRD 8.1 / DSH 2.3: LIVE cash-closure table, every estimate named.

    avoided coupons = no-spend rows x old-rule coverage x empirical
    self-return rate. Face-value and cash-cost views are shown separately:
    PRD 4's ~HK$1,500/week is a FACE-VALUE illustration (350 coupons x HK$44),
    while a CFO wants face x redemption x gross margin.
    """
    no_spend = [r for r in rows if not r["can_approve"]]
    probs = [r["return_prob"] for r in no_spend if r.get("return_prob") is not None]
    avg = sum(probs) / len(probs) if probs else 0.0
    avoided = round(len(no_spend) * blanket_rate * avg / 100.0)
    cost_per = face * redeem * margin
    # PRD 4's own illustrative scope: 350 weekly coupons, 10% (35) wasted on
    # people who would have returned anyway. Kept separate from the full-list
    # view above, with the SAME live parameters.
    prd_coupons = 350
    prd_wasted = round(prd_coupons * 0.10)
    return dict(
        no_spend_count=len(no_spend), avg_self_return=round(avg, 1),
        avoided_coupons=avoided, cost_per_coupon=round(cost_per, 2),
        weekly_saving=round(avoided * cost_per),
        face_value_saving=round(avoided * face),
        prd_coupons=prd_coupons, prd_wasted=prd_wasted,
        prd_face_saving=round(prd_wasted * face),
        prd_cash_saving=round(prd_wasted * cost_per),
        face=face, redemption=redeem, margin=margin, blanket_rate=blanket_rate,
        formula=("避免重复券 = 不干预人数 x 旧规则覆盖率 x 经验自行回流率；"
                 "现金节省 = 避免券数 x 券面值 x 兑换率 x 毛利率"),
        estimates=["券面值 HK$44（PRD 示意，非实测）", "兑换率 30%（估计）",
                   "毛利率 65%（估计）", "自行回流率为经验分桶率，非因果 uplift",
                   "不含增量到店带来的毛利 upside",
                   "旧规则覆盖率默认 1.0 = 全量名单；PRD 4 的 350 张/周预算约等于 0.07"],
        note=("PRD 4 的 ~HK$1,500/周按 350 张券 x HK$44 券面值示意；本表按真实全量名单"
              "现场计算，并区分券面值口径与现金成本口径。改任一参数，数字立刻变。"))


def check_consent(data_dir, cid, channel, at_dt):
    """Return (ok, basis, reason). Validates that the given channel has a
    current opt_in record for the customer. One consent row per (customer,
    channel) is kept by the load, so the record must simply be 'opt_in'."""
    cons = load_consent(data_dir).get(cid, {})
    rec = cons.get(channel)
    if rec is None:
        return (False, "", "no consent record for channel '%s'" % channel)
    basis = rec.get("basis", "")
    if rec.get("status") != "opt_in":
        return (False, basis, "channel '%s' is not opt_in (status=%s)"
                % (channel, rec.get("status")))
    updated = parse_dt(rec.get("updated_at"))
    return (True, basis,
            "opt_in, basis=%s, updated %s" % (basis, updated.date() if updated else "unknown"))


# --------------------------------------------------------------------------
# BUDGET LAYER (store = budget & suppression unit)
# --------------------------------------------------------------------------
def budget_plan(rows, total_coupons=350, face=44.0, suppressed_stores=(), params=None):
    """Illustrative weekly budget allocation.

    PRD fixes the two-level design (store = budget/suppression unit) but does
    NOT define an allocation algorithm, so the rule below is explicitly ours
    and must be labelled as such wherever it is shown.

    Rule
      1. candidates = approvable rows whose home store is not suppressed
      2. coupon face is rule-given: high / medium from params (AI never sets money)
      3. budget = total_coupons x face (face-value view, not cash cost)
      4. sort by net_gain desc, fill greedily, never split a coupon
      5. a suppressed store's demand is reported, not spent
    """
    P = effective_params(params)
    face_high = float(P["FACE_HIGH"])
    face_med = float(P["FACE_MED"])
    supp = {str(s) for s in (suppressed_stores or ()) if str(s)}
    cand = [r for r in rows if r.get("can_approve")]

    def coupon(r):
        return face_high if r.get("group") == "high" else face_med

    budget = float(total_coupons) * float(face)
    demand_amt = sum(coupon(r) for r in cand)
    pool = [r for r in cand if r.get("store_id") not in supp]
    suppressed = [r for r in cand if r.get("store_id") in supp]
    pool.sort(key=lambda r: (-r.get("net_gain", 0), -coupon(r)))

    def fill(pool_rows):
        used = 0.0
        out = []
        for r in sorted(pool_rows, key=lambda r: (-r.get("net_gain", 0), -coupon(r))):
            c = coupon(r)
            if used + c <= budget + 1e-9:
                used += c
                out.append(r)
        return out, used

    funded, used = fill(pool)
    base_funded, base_used = fill(cand)          # what would happen with no suppression
    funded_ids = {r["customer_id"] for r in funded}
    base_ids = {r["customer_id"] for r in base_funded}
    gain = sum(r.get("net_gain", 0) for r in funded)
    base_gain = sum(r.get("net_gain", 0) for r in base_funded)
    swapped = base_ids - funded_ids
    # "deferred" = suppressed-store customers who WOULD have been funded without suppression
    deferred = sorted([r for r in suppressed if r["customer_id"] in base_ids],
                      key=lambda r: -r.get("net_gain", 0))

    by = {}
    for r in cand:
        sid = r.get("store_id", "") or "(unknown)"
        d = by.setdefault(sid, dict(store_id=sid, demand_n=0, demand_amt=0.0,
                                    funded_n=0, funded_amt=0.0, high_n=0,
                                    medium_n=0, suppressed=sid in supp))
        d["demand_n"] += 1
        d["demand_amt"] += coupon(r)
        if r.get("group") == "high":
            d["high_n"] += 1
        else:
            d["medium_n"] += 1
        if r["customer_id"] in funded_ids:
            d["funded_n"] += 1
            d["funded_amt"] += coupon(r)

    by_store = []
    for d in by.values():
        d["demand_amt"] = round(d["demand_amt"])
        d["funded_amt"] = round(d["funded_amt"])
        d["unserved_n"] = d["demand_n"] - d["funded_n"]
        d["unserved_amt"] = d["demand_amt"] - d["funded_amt"]
        d["reason"] = ("本周压制：不发挽留券，预算不投" if d["suppressed"]
                       else ("已足额投放" if d["unserved_n"] == 0
                             else "预算不足：按净收益排序被截断"))
        by_store.append(d)
    by_store.sort(key=lambda x: (-x["demand_amt"], x["store_id"]))

    fh = sum(1 for r in funded if r.get("group") == "high")
    fm = len(funded) - fh
    ah = sum(1 for r in cand if r.get("group") == "high")
    return dict(
        total_coupons=int(total_coupons), face=float(face), budget=round(budget),
        demand_n=len(cand), demand_amt=round(demand_amt),
        coverage=round(100.0 * budget / demand_amt, 1) if demand_amt else 0.0,
        funded_n=len(funded), funded_amt=round(used),
        unserved_n=len(cand) - len(funded), unserved_amt=round(demand_amt - used),
        funded_high=fh, funded_medium=fm, demand_high=ah, demand_medium=len(cand) - ah,
        suppressed_stores=sorted(supp), suppressed_n=len(suppressed),
        suppressed_amt=round(sum(coupon(r) for r in suppressed)),
        # --- cost preview of the suppression decision (方案 A) -------------
        gain=round(gain), baseline_gain=round(base_gain),
        gain_delta=round(gain - base_gain),
        gain_delta_pct=round(100.0 * (gain - base_gain) / base_gain, 2) if base_gain else 0.0,
        swapped_n=len(swapped),
        baseline_funded_n=len(base_funded), baseline_funded_amt=round(base_used),
        deferred=[dict(customer_id=r["customer_id"], store_id=r.get("store_id", ""),
                       group=r.get("group", ""), net_gain=r.get("net_gain", 0),
                       coupon=coupon(r), cap=r.get("cap", 0)) for r in deferred],
        deferred_n=len(deferred),
        deferred_amt=round(sum(coupon(r) for r in deferred)),
        by_store=by_store,
        rule=("示意规则（PRD 未定义分配算法，本规则由项目设定，需业务拍板）："
              "候选 = 可批准且归属店本周未被压制；券面值由 if 规则给定"
              "（high 50 / medium 30），AI 不改金额；预算 = 券数 x 面值（券面值口径）；"
              "按净收益降序贪心装满、不拆券；压制店需求不计入投放。"),
        caveat=("纯净收益排序下，中价值客户可能整批落选（high 的 ERV 门槛更高）："
                "本板显式给出被砍的中价值人数，供决定是否设中价值保底配额。"
                "券面值不等于现金成本；现金成本 = 面值 x 兑换率 x 毛利率。"),
    )


def budget_advice(rows, face=44.0, redeem=0.30, margin=0.65,
                  cash_cap=None, target=90.0, coupons=None,
                  suppressed_stores=(), params=None):
    """下周该批多少预算：把「灵活预算」拆成两个外部输入 + 一条硬上限。

    PRD defines the two-level design but NOT how next week's total is set.
    This function does not forecast next week's demand. It answers, for THIS
    week's candidate list: given a cash ceiling and/or a coverage target,
    how many coupon slots are needed, how many people that covers, where the
    marginal gain collapses, and where the list saturates.

    The two knobs are external (finance cash / business coverage goal).
    The model itself never decides the total: every approvable row has
    net_gain > 0 by construction, so "fund everyone positive" would always
    spend the whole demand. Saturation is the only endogenous stop.
    """
    cand = [r for r in rows if r.get("can_approve")]
    face = float(face)
    cash_per = face * float(redeem) * float(margin)

    P = effective_params(params)
    face_high = float(P["FACE_HIGH"])
    face_med = float(P["FACE_MED"])

    def cp(r):
        return face_high if r.get("group") == "high" else face_med

    demand = sum(cp(r) for r in cand)
    demand_high = sum(1 for r in cand if r.get("group") == "high")
    demand_medium = len(cand) - demand_high

    def snap(n):
        n = max(0, int(n))
        b = budget_plan(rows, n, face, suppressed_stores, params)
        amt = b["funded_amt"]
        return dict(
            coupons=n, budget=round(n * face),
            funded_n=b["funded_n"], funded_amt=amt,
            coverage=min(100.0, round(100.0 * amt / demand, 1)) if demand else 0.0,
            gain=b["gain"], high=b["funded_high"], medium=b["funded_medium"],
            medium_unserved=demand_medium - b["funded_medium"],
            cash=round(n * cash_per),
        )

    def min_for(pct):
        """Smallest coupon count whose coverage reaches pct (binary search)."""
        lo, hi = 0, int(demand / face) + 200
        while lo < hi:
            mid = (lo + hi) // 2
            if snap(mid)["coverage"] >= float(pct) - 1e-9:
                hi = mid
            else:
                lo = mid + 1
        return lo

    saturation = min_for(100.0)
    by_target_n = min_for(target)
    by_cash_n = int(float(cash_cap) / cash_per + 1e-9) if cash_cap else None

    if coupons is not None:
        n, binding = int(coupons), "manual"
    elif by_cash_n is not None and by_target_n is not None:
        n = min(by_cash_n, by_target_n)
        binding = "cash" if by_cash_n < by_target_n else "target"
    elif by_cash_n is not None:
        n, binding = by_cash_n, "cash"
    else:
        n, binding = by_target_n, "target"
    if n > saturation:
        n, binding = saturation, "saturation"
    n = max(0, n)

    grid = []
    ns = list(range(0, min(saturation, 1000) + 1, 50))
    if ns[-1] != saturation:
        ns.append(saturation)
    prev = None
    for x in ns:
        p = snap(x)
        p["marginal_n"] = 0 if prev is None else p["funded_n"] - prev["funded_n"]
        p["marginal_gain"] = 0 if prev is None else p["gain"] - prev["gain"]
        grid.append(p)
        prev = p

    return dict(
        demand_n=len(cand), demand_amt=round(demand),
        demand_high=demand_high, demand_medium=demand_medium,
        face=face, redeem=float(redeem), margin=float(margin),
        cash_per_coupon=round(cash_per, 2),
        cash_cap=float(cash_cap) if cash_cap else None, target=float(target),
        saturation_coupons=saturation,
        by_target=snap(by_target_n),
        by_cash=snap(by_cash_n) if by_cash_n is not None else None,
        recommended_coupons=n, recommended=snap(n), binding=binding,
        binding_label={"cash": "财务给的现金不够，按钱批",
                       "target": "覆盖率目标已达，按目标批",
                       "manual": "按手工指定的券数",
                       "saturation": "已到饱和点，再多没人可发"}[binding],
        headroom_coupons=saturation - n,
        grid=grid,
        formula=("券数上限 = 财务真现金 ÷ (券面值 × 兑换率 × 毛利率)；"
                 "覆盖率 = 已投券面值 ÷ 需求券面值；"
                 "目标券数 = 覆盖率首次达标的最小券数（对真实装填规则二分实测）；"
                 "饱和点 = 覆盖率首次达 100% 的最小券数，超过后多给券无人可发。"),
        notes=[
            "券数是按 HK$44 平均面值折算的「额度」，不是实际发出的券张数；实际券面值由规则给定 high HK$50 / medium HK$30。",
            "真现金 = 券数 × 面值 × 兑换率 × 毛利率，是 PRD §8.1 的统一折算口径；兑换率 30% / 毛利率 65% 均为估计值。",
            "net_gain = ERV(日均花费 × 180) − 券上限，只是排序代理量，不是因果 uplift，不能当 ROI 与财务讨价。",
            "所有可批准客户的 net_gain 都 > 0（can_approve 本身就要求 > 0），所以模型不会自己喊停；总额只由现金流或覆盖率目标决定。",
            "本卡按本周候选名单测算、且不叠加本周签字压制；下周名单必须重新跑一次个人层，不能沿用本周人数。",
        ],
        rule=("示意规则（PRD 未定义「下周该批多少」，此卡由项目设定，需业务拍板）："
              "两个外部输入 = 财务真现金上限 / 覆盖率目标；取更紧的一个，再封顶到饱和点；"
              "金额与分组仍由 if 规则给定，AI 不改钱。"),
        caveat=("覆盖率按「已投券面值 ÷ 需求券面值」算并封顶 100%（不是 券数×面值÷需求，"
                "后者在额度超过需求时会虚高）；中价值整批落选是净收益排序的结果，是否设保底配额需业务拍板。"),
    )
