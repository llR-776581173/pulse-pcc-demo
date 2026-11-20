# -*- coding: utf-8 -*-
"""
pulse_state.py  —  customer lifecycle STATE MACHINE layer.

This is the layer the handover says was missing: an explicit, time-ordered
"enter -> consume -> go silent -> return" model, separate from the six
decision exits of the weekly board.  It lets the board answer:

  1. who is exactly where in the lifecycle right now (state distribution)
  2. when the AT_RISK early warning fired relative to a real return/exit
  3. who returned after an intervention / recall, and when

Six states  (value tier and risk score are SEPARATE overlay dimensions):
  NEW_UNPURCHASED  registered, never transacted
  FIRST_PURCHASE   first purchase, fewer than FLAG_MIN_GAPS intervals
  ACTIVE           buying on rhythm
  AT_RISK          silent >= DEV_THRESHOLD x own median gap, within warning H
  DEEP_DORMANT     beyond warning H, still within FLAG_MAX_SILENCE
  CHURNED          silent > FLAG_MAX_SILENCE

Transition rules follow the handover §3.2 matrix; a transition is rejected if
it is not in the legal set (no arbitrary jumps).  Re-activation (intervention
hit / recall return) NEVER creates a new customer_id — it is a transition.

Triggers (trigger_event):
  TXN                 new transaction
  RHYTHM_DEVIATION    silence crossed the 1.5x-for-this-customer line
  WINDOW_EXPIRED      passed warning window H, no transaction
  INTERVENTION_HIT    intervention produced a return order
  RECALL_RETURN       a churned customer came back (re-enters via FIRST_PURCHASE)

Design
  * snapshot table  (as_of_date, customer_id)  = 1 row per customer per day
    (only present here as the state at the eval cut + change points for
    compactness; the full daily cube is derivable).
  * transition log  append-only list of (from, to, occurred_at, trigger, event)
  * lifecyle()       aggregated distribution + transition matrix + avg dwell
  * timeline(cid)    one customer's full state history + tied decisions
"""

import os
import csv
import datetime as dt
from collections import defaultdict

import pulse_core as core

# Expected remap of a decision "exit" onto a lifecycle state, used only to tie
# a decision row to its state on the board (decision exits are NOT states).
# Kept out of the state machine itself.

STATE_RANK = ["NEW_UNPURCHASED", "FIRST_PURCHASE", "ACTIVE",
              "AT_RISK", "DEEP_DORMANT", "CHURNED"]

# Legal transitions: from -> allowed set of to (handover §3.2 matrix).
LEGAL = {
    "NEW_UNPURCHASED": {"FIRST_PURCHASE"},
    "FIRST_PURCHASE":  {"ACTIVE"},
    "ACTIVE":          {"AT_RISK"},
    "AT_RISK":         {"ACTIVE", "DEEP_DORMANT"},
    "DEEP_DORMANT":    {"ACTIVE", "CHURNED"},
    "CHURNED":         {"FIRST_PURCHASE"},
}

CN_ZH = {
    "NEW_UNPURCHASED": "进店未消费",
    "FIRST_PURCHASE":  "首购激活",
    "ACTIVE":          "活跃复购",
    "AT_RISK":         "沉寂预警",
    "DEEP_DORMANT":    "深度沉寂",
    "CHURNED":         "判定流失",
}


def RULE_VERSION_STATE():
    """The currently-deployed rule version, read lazily from rule_config.
    No cycle: rule_config imports pulse_core, not pulse_state."""
    try:
        import rule_config as _rc
        cfg = _rc.load()
        return str(cfg.get("version") or core.RULE_VERSION)
    except Exception:
        return getattr(core, "RULE_VERSION", "v1.0")


def _state_for(silence_days, median_days, n_gaps, H, dev_thr, max_sil, min_gaps):
    """Classify a customer at one moment from their rhythm features."""
    if median_days is None or n_gaps is None:
        # fewer than the rhythm floor => FIRST (or NEW if never bought)
        if silence_days is None:
            return "NEW_UNPURCHASED"
        return "FIRST_PURCHASE"
    if n_gaps < min_gaps:
        return "FIRST_PURCHASE"
    dev = silence_days / median_days if median_days else 999.0
    if silence_days > max_sil:
        return "CHURNED"
    if silence_days > H:
        return "DEEP_DORMANT"
    if dev >= dev_thr:
        return "AT_RISK"
    return "ACTIVE"


class StateMachine:
    def __init__(self, params=None):
        P = core.effective_params(params)
        self.dev_thr = float(P["DEV_THRESHOLD"])
        self.max_sil = int(P["FLAG_MAX_SILENCE"])
        self.h_window = int(P["WARN_DAYS_H"])
        self.min_gaps = int(P["FLAG_MIN_GAPS"])
        self.params = P

    def classify(self, silence_days, median_days, n_gaps):
        return _state_for(silence_days, median_days, n_gaps,
                          self.h_window, self.dev_thr, self.max_sil, self.min_gaps)

    def legal(self, fro, to):
        return to in LEGAL.get(fro, set())


def _transitions_for_customer(cid, txn_lst, mu, n_gaps_registered, sm, cut):
    """Walk a customer's REAL inter-visit gaps through the state machine.

    Every transition is derived from actual transaction dates — nothing is
    injected. A long silence (>= DEV_THRESHOLD x own median, <= max_sil) emits
    AT_RISK (RHYTHM_DEVIATION on the day the silence crossed the line); past the
    warning window H emits DEEP_DORMANT (WINDOW_EXPIRED); past max_sil emits
    CHURNED. The next real purchase returns the customer via the return edge
    (AT_RISK/DEEP -> ACTIVE, or CHURNED -> FIRST_PURCHASE recall), trigger TXN.
    Recompute-safe: change a threshold and these edges move with it.
    """
    dates = [r["d"].date() for r in txn_lst] if txn_lst else []
    if not dates:
        return dict(customer_id=cid, cut=cut.isoformat(), state="NEW_UNPURCHASED",
                    state_entered_at=None, silence_days=None,
                    median_gap_days=(round(mu, 1) if mu is not None else None),
                    rule_version=RULE_VERSION_STATE(),
                    warn_lead_days=None, n_returns=0,
                    transitions=[], _demo=False)

    if mu is None or mu <= 0 or n_gaps_registered < sm.min_gaps:
        state = "FIRST_PURCHASE"  # not enough rhythm to judge
    else:
        state = sm.classify((cut - dates[-1]).days, mu, n_gaps_registered)

    transitions = []
    dev_thr, max_sil, H, med = sm.dev_thr, sm.max_sil, sm.h_window, mu
    rv = RULE_VERSION_STATE()

    at_risk_at = None          # last date the customer entered AT_RISK
    lead_days_returns = []     # warn_lead_days = return_date - at_risk_date

    def add(fr, to, trig, at):
        nonlocal at_risk_at
        if to in LEGAL.get(fr, set()):
            rec = dict(customer_id=cid, from_state=fr, to_state=to,
                       trigger_event=trig, occurred_at=at, rule_version=rv)
            if trig == "RHYTHM_DEVIATION" and to == "AT_RISK":
                at_risk_at = at
            if trig == "TXN" and fr in ("AT_RISK", "DEEP_DORMANT") and to == "ACTIVE":
                if at_risk_at is not None and at >= at_risk_at:
                    rec["warn_lead_days"] = (at - at_risk_at).days
                    lead_days_returns.append((at - at_risk_at).days)
            transitions.append(rec)

    prev_date = dates[0]
    cur = "NEW_UNPURCHASED"
    for i, d in enumerate(dates):
        if i == 0:
            add("NEW_UNPURCHASED", "FIRST_PURCHASE", "TXN", d)
            cur = "FIRST_PURCHASE"
            prev_date = d
            continue
        gap = (d - prev_date).days
        # drift while silent
        if med and med > 0:
            if gap > max_sil:
                if cur in ("ACTIVE", "AT_RISK", "DEEP_DORMANT", "FIRST_PURCHASE"):
                    add(cur, "CHURNED", "WINDOW_EXPIRED",
                        prev_date + dt.timedelta(days=max_sil))
                    cur = "CHURNED"
            elif gap > H:
                if cur == "ACTIVE":
                    add(cur, "AT_RISK", "RHYTHM_DEVIATION",
                        prev_date + dt.timedelta(days=int(dev_thr * med)))
                    cur = "AT_RISK"
                if cur in ("ACTIVE", "AT_RISK"):
                    add(cur, "DEEP_DORMANT", "WINDOW_EXPIRED",
                        prev_date + dt.timedelta(days=H))
                    cur = "DEEP_DORMANT"
            elif gap >= dev_thr * med:
                if cur == "ACTIVE":
                    add("ACTIVE", "AT_RISK", "RHYTHM_DEVIATION",
                        prev_date + dt.timedelta(days=int(dev_thr * med)))
                    cur = "AT_RISK"
        # the real purchase at d is the return edge
        n_intervals = i  # purchases so far -> intervals
        target = "ACTIVE" if n_intervals >= sm.min_gaps else "FIRST_PURCHASE"
        if cur != target:
            if sm.legal(cur, target):
                add(cur, target, "TXN", d)
                cur = target
        prev_date = d

    return dict(customer_id=cid, cut=cut.isoformat(), state=state,
                state_entered_at=(dates[-1].isoformat()),
                silence_days=(cut - dates[-1]).days,
                median_gap_days=(round(mu, 1) if mu is not None else None),
                rule_version=rv,
                warn_lead_days=(min(lead_days_returns) if lead_days_returns else None),
                n_returns=len(lead_days_returns),
                transitions=transitions,
                _demo=False)    


def _classify_demo_group(cid, dates, mu, grp, optin, cut):
    """Label a customer's demo group from REAL data (docs/03 criteria)."""
    if len(dates) < 5 or mu is None or mu <= 0:
        return None
    gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
    # A: silence->return arc fully inside cut (long silence then more purchases,
    #    not silent at cut)
    comebacks = [g for g in gaps[:-1] if mu < g <= 180 and g >= 1.5 * mu]
    tail = (cut - dates[-1]).days
    if comebacks and 0 <= tail < 1.5 * mu and optin:
        return "A"
    if 0 < tail <= core.FLAG_MAX_SILENCE and tail >= 1.5 * mu and optin:
        return "B"
    if tail <= mu and grp in ("high", "medium", "low", "normal"):
        return "C"
    return None


class LifecycleEngine:
    def __init__(self, data_dir, cut, params=None):
        self.data_dir = data_dir
        self.cut = cut
        self.sm = StateMachine(params)
        P = core.effective_params(params)
        self.params = params
        self.rule_version = RULE_VERSION_STATE()  # current deployed rule version
        self.window = {"T": cut.isoformat(), "W": int(P["TRAILING_DAYS"]),
                       "H": int(P["WARN_DAYS_H"])}

    def _features(self):
        return core._features(self.data_dir, self.cut)

    def _demo_pool(self, byc, baseline, modal, cls_rows, consent_optin):
        """Label A/B/C demo groups from REAL data (docs/03). Returns {cid: group}.

        Zero data edits: every case is a customer that actually exists and whose
        state recomputes when a threshold changes. Nothing is injected."""
        grp = {r["customer_id"]: r["group"] for r in cls_rows}
        groups = {}
        for cid, lst in byc.items():
            dates = [r["d"].date() for r in lst]
            mu = baseline.get(cid)
            g = _classify_demo_group(cid, dates, mu, grp.get(cid, ""),
                                     bool(consent_optin.get(cid)), self.cut)
            if g:
                groups[cid] = g
        return groups

    def build_rows(self):
        """Per-customer lifecycle row at the cut + demo group label (if any).

        Includes customers registered in customers.csv but with NO transaction up
        to cut as NEW_UNPURCHASED (docs/02 A #4 active-denominator口径), so the
        six-state distribution is complete. Each row carries rule_version."""
        txn, byc, baseline, modal = self._features()
        try:
            cls = core.classify_customers(self.data_dir, self.cut, self.params)
        except Exception:
            cls = {"rows": []}
        by_cid = {r["customer_id"]: r for r in cls["rows"]}
        consent_optin = defaultdict(set)
        for cid, chs in core.load_consent(self.data_dir).items():
            for ch, rec in chs.items():
                if rec.get("status") == "opt_in":
                    consent_optin[cid].add(ch)
        demo = self._demo_pool(byc, baseline, modal, cls["rows"], consent_optin)
        rv = RULE_VERSION_STATE()
        rows = []
        for cid, lst in byc.items():
            mu = baseline.get(cid)
            n_gaps_rec = len([x for x in core._gaps([r["d"].date() for r in lst])
                              if 0 <= x <= core.MAX_INTERVAL])
            drow = by_cid.get(cid, {})
            res = _transitions_for_customer(cid, lst, mu, n_gaps_rec,
                                            StateMachine(self.params), self.cut)
            rows.append(dict(
                customer_id=cid, store_id=drow.get("store_id", ""), state=res["state"],
                silence_days=res["silence_days"], median_gap_days=res["median_gap_days"],
                value_tier=drow.get("group", ""), erv=drow.get("erv", 0),
                n_transitions=len(res["transitions"]),
                warn_lead_days=res.get("warn_lead_days"),
                n_returns=res.get("n_returns", 0),
                rule_version=rv,
                demo_group=demo.get(cid),
            ))
        # registered but never transacted up to cut -> NEW_UNPURCHASED
        members = core.load_members(self.data_dir)
        for cid in members:
            if cid not in byc:
                rows.append(dict(customer_id=cid, store_id="", state="NEW_UNPURCHASED",
                                 silence_days=None, median_gap_days=None,
                                 value_tier="", erv=0, n_transitions=0,
                                 warn_lead_days=None, n_returns=0,
                                 rule_version=rv, demo_group=None))
        return rows

    def lifecycle(self, store=None):
        """Aggregated view: distribution + transition matrix + window metrics,
        and it PERSISTS the state-machine data layer (snapshot + transition
        tables, per rule_version, under audit/). Returns window / warn_lead_days /
        rule_version so "预警提前了几天" is computable."""
        rows = self.build_rows()
        if store:
            rows = [r for r in rows if r.get("store_id") == store]
        dist = {}
        leads = []
        for r in rows:
            dist[r["state"]] = dist.get(r["state"], 0) + 1
            if r.get("warn_lead_days") is not None:
                leads.append(r["warn_lead_days"])
        ordered = {s: dist.get(s, 0) for s in STATE_RANK}
        # transition matrix + collect all real transitions for persistence
        mat = {f: {t: 0 for t in STATE_RANK} for f in STATE_RANK}
        txn, byc, baseline, modal = self._features()
        all_transitions = []
        for cid, lst in byc.items():
            if store and modal.get(cid) != store:
                continue
            mu = baseline.get(cid)
            n_gaps_rec = len([x for x in core._gaps([r["d"].date() for r in lst])
                              if 0 <= x <= core.MAX_INTERVAL])
            res = _transitions_for_customer(cid, lst, mu, n_gaps_rec,
                                            StateMachine(self.params), self.cut)
            for tr in res["transitions"]:
                a, b = tr.get("from_state"), tr.get("to_state")
                if a and b in STATE_RANK and a in STATE_RANK:
                    mat[a][b] += 1
                all_transitions.append(tr)
        total = sum(ordered.values())
        # persist data layer (snapshot + append-only transition log per version)
        self._persist(rows, all_transitions)
        warn_lead_summary = (dict(
            count=len(leads),
            mean=round(sum(leads) / len(leads), 1) if leads else None,
            min=min(leads) if leads else None,
            max=max(leads) if leads else None,
        ) if leads else {"count": 0, "mean": None, "min": None, "max": None})
        return dict(
            cut=self.cut.isoformat(),
            params=self.params,
            rule_version=self.rule_version,
            total=total,
            distribution=ordered,
            distribution_pct={s: round(100.0 * n / total, 1) if total else 0
                              for s, n in ordered.items()},
            transition_matrix=mat,
            cn_zh=CN_ZH,
            legal={k: sorted(v) for k, v in LEGAL.items()},
            window=self.window,                 # T / [T-W,T] / [T,T+H]
            warn_lead_days=warn_lead_summary,   # 预警提前天数
            demo_pool_counts=self._demo_pool_counts(),
            note=("状态机与决策出口分离：价值分层与风险得分是叠加维度，不参与状态定义；"
                  "回流是一次状态转移，永不新建 customer_id；预置案例由合成数据真实筛出，"
                  "改阈值后状态随之变化。"),
        )

    def _persist(self, rows, transitions):
        """Persist the state-machine data layer (docs/02 D.5, L06/L07/L08).

        Writes per-rule_version append-only files under audit/ so an OLD version
        is never overwritten:
          customer_state_snapshot_vX.csv     one row per customer at as_of_date
          customer_state_transition_vX.csv   append-only transition log
        Never touches the frozen selftest/data. Raises nothing on IO error."""
        try:
            out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audit")
            os.makedirs(out_dir, exist_ok=True)
            v = self.rule_version.replace(".", "_").replace("v", "v") or "v1_0"
            snap_f = os.path.join(out_dir, "customer_state_snapshot_%s.csv" % v)
            tr_f = os.path.join(out_dir, "customer_state_transition_%s.csv" % v)
            as_of = self.cut.isoformat()
            # snapshot: one row per customer at as_of_date (versioned file, not overwritten)
            snap_hdr = ["as_of_date", "customer_id", "state", "state_entered_at",
                        "silence_days", "median_gap_days", "value_tier",
                        "warn_lead_days", "rule_version"]
            if not os.path.exists(snap_f):
                with open(snap_f, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=snap_hdr)
                    w.writeheader()
                    for r in rows:
                        w.writerow(dict(
                            as_of_date=as_of, customer_id=r.get("customer_id", ""),
                            state=r.get("state", ""),
                            state_entered_at=r.get("state_entered_at", ""),
                            silence_days=r.get("silence_days", ""),
                            median_gap_days=r.get("median_gap_days", ""),
                            value_tier=r.get("value_tier", ""),
                            warn_lead_days=r.get("warn_lead_days", ""),
                            rule_version=self.rule_version))
            # transition log: full write per rule_version (deterministic input ->
            # deterministic output; a newer version writes a different file, so the
            # old version is never overwritten)
            tr_hdr = ["customer_id", "from_state", "to_state", "trigger_event",
                      "occurred_at", "warn_lead_days", "rule_version"]
            with open(tr_f, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=tr_hdr)
                w.writeheader()
                for tr in transitions:
                    w.writerow(dict(
                        customer_id=tr.get("customer_id", ""),
                        from_state=tr.get("from_state", ""), to_state=tr.get("to_state", ""),
                        trigger_event=tr.get("trigger_event", ""),
                        occurred_at=tr.get("occurred_at", "").isoformat()
                        if hasattr(tr.get("occurred_at"), "isoformat") else tr.get("occurred_at", ""),
                        warn_lead_days=tr.get("warn_lead_days", ""),
                        rule_version=tr.get("rule_version", self.rule_version)))
        except Exception:
            pass  # persistence is best-effort; in-memory results remain correct

    def _demo_pool_counts(self):
        txn, byc, baseline, modal = self._features()
        cls = core.classify_customers(self.data_dir, self.cut, self.params)
        consent_optin = defaultdict(set)
        for cid, chs in core.load_consent(self.data_dir).items():
            for ch, rec in chs.items():
                if rec.get("status") == "opt_in":
                    consent_optin[cid].add(ch)
        pool = self._demo_pool(byc, baseline, modal, cls["rows"], consent_optin)
        return {g: sum(1 for v in pool.values() if v == g) for g in ("A", "B", "C")}

    def state_map(self):
        """{customer_id: state} at the cut — used to stamp state_at_decision."""
        return {r["customer_id"]: r["state"] for r in self.build_rows()}

    def case_lists(self):
        """Return the preset demo case customers, grouped A/B/C, with state + store.

        Cases are REAL customers screened from synthetic data (docs/03), NOT
        injected; their state changes when a threshold changes. Sorted so the
        most illustrative come first."""
        txn, byc, baseline, modal = self._features()
        cls = core.classify_customers(self.data_dir, self.cut, self.params)
        grp = {r["customer_id"]: r["group"] for r in cls["rows"]}
        consent_optin = defaultdict(set)
        for cid, chs in core.load_consent(self.data_dir).items():
            for ch, rec in chs.items():
                if rec.get("status") == "opt_in":
                    consent_optin[cid].add(ch)
        pool = self._demo_pool(byc, baseline, modal, cls["rows"], consent_optin)
        sm = StateMachine(self.params)
        out = {"A": [], "B": [], "C": []}
        for cid, g in pool.items():
            lst = byc.get(cid, [])
            mu = baseline.get(cid)
            ng = len([x for x in core._gaps([r["d"].date() for r in lst])
                      if 0 <= x <= core.MAX_INTERVAL])
            silence = (self.cut - lst[-1]["d"].date()).days if lst else None
            state = sm.classify(silence, mu, ng)
            # OPT-01 (demo-case ordering only): for group A members, count real
            # "AT_RISK/DEEP_DORMANT -> ACTIVE" return arcs with the SAME
            # transition engine used everywhere else. Membership, data and state
            # definitions are untouched — only the display order depends on it.
            n_arcs = 0
            max_lead = 0
            if g == "A":
                res = _transitions_for_customer(cid, lst, mu, ng, sm, self.cut)
                n_arcs = sum(1 for t in res.get("transitions", [])
                             if t.get("to_state") == "ACTIVE"
                             and t.get("from_state") in ("AT_RISK", "DEEP_DORMANT"))
                leads = [t.get("warn_lead_days") for t in res.get("transitions", [])
                         if t.get("warn_lead_days") is not None]
                max_lead = max(leads) if leads else 0
            out[g].append(dict(customer_id=cid, store_id=modal.get(cid, ""),
                               state=state, group=grp.get(cid, ""),
                               silence_days=silence,
                               median_gap_days=(round(mu, 1) if mu is not None else None),
                               n_return_arcs=n_arcs, max_warn_lead=max_lead))
        # A: put customers with a complete 沉寂→预警→回流 arc on the first screen
        #    (OPT-01), prefer a longer measurable warn lead (better for the
        #    「提前了几天」 narrative), tie-break by longer median gap;
        #    B: longest tail; C: stable id order
        out["A"].sort(key=lambda r: (-r.get("n_return_arcs", 0),
                                     -r.get("max_warn_lead", 0),
                                     -(r["median_gap_days"] or 0)))
        out["B"].sort(key=lambda r: -(r["silence_days"] or 0))
        out["C"].sort(key=lambda r: (r["customer_id"]))
        out["rule_version"] = self.rule_version
        out["window"] = self.window
        return out

    def timeline(self, customer_id):
        """One customer's full state timeline derived from REAL transactions."""
        txn, byc, baseline, modal = self._features()
        lst = byc.get(customer_id, [])
        mu = baseline.get(customer_id)
        n_gaps_rec = len([x for x in core._gaps([r["d"].date() for r in lst])
                          if 0 <= x <= core.MAX_INTERVAL])
        res = _transitions_for_customer(customer_id, lst, mu, n_gaps_rec,
                                        StateMachine(self.params), self.cut)
        transitions = []
        for tr in res["transitions"]:
            t2 = dict(tr)
            if isinstance(t2.get("occurred_at"), (dt.date, dt.datetime)):
                t2["occurred_at"] = t2["occurred_at"].isoformat()
            transitions.append(t2)
        return dict(customer_id=customer_id, cut=self.cut.isoformat(),
                    rule_version=self.rule_version, window=self.window,
                    state=res["state"], state_entered_at=res["state_entered_at"],
                    silence_days=res["silence_days"],
                    median_gap_days=res["median_gap_days"],
                    warn_lead_days=res.get("warn_lead_days"),
                    n_returns=res.get("n_returns", 0),
                    transitions=transitions,
                    demo_narrative=res["_demo"])
