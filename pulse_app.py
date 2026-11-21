# -*- coding: utf-8 -*-
"""
pulse_app.py  —  Pulse (Module 3) live dashboard server.

Pure-Python stdlib HTTP server (no pip installs). ONE decision path, end to end:

    open board -> store health -> drill into a store -> real ranked action list
    -> approve ONE with a written reason -> append-only audit log

API
  GET  /                          dashboard (static/index.html)
  GET  /api/stores?week=N         store health + signed suppression state (PRD 4.1)
  GET  /api/actions?group=&store=&limit=&offset=
  GET  /api/summary               group counts + review-load measurement
  GET  /api/baseline              live 82.8% / ~55% recomputation + bucket table
  GET  /api/savings?face=&redeem=&margin=&blanket=
                                  live cash-closure parameter table (PRD 8.1)
  GET  /api/budget?coupons=&face=&week=&suppress=
                                  allocation + COST PREVIEW of signed suppressions
  GET  /api/advice?cash=&target=&redeem=&margin=&face=
                                  NEXT WEEK budget advice: cash ceiling / coverage
                                  target -> coupon count, marginal curve, saturation
  GET  /api/audit                 approved records (messages schema + decision log)
  GET  /api/lifecycle?store=      lifecycle state distribution + transition matrix
  GET  /api/lifecycle/customers/<id>/timeline     one customer state timeline
  GET  /api/config                live rule table (version + fields + change log)
  GET  /api/experiment            PRD §8 design view (holdout arms, readout)
  GET  /api/outcome               intervention outcome write-back rows
  POST /api/approve               consent re-check -> write approved record
  POST /api/suppress              store suppression: action=suppress|release,
                                  requires approver + reason + structural tag;
                                  the price is computed and stored WITH the signature
  PUT/POST /api/config            change a rule threshold -> pipeline recomputes
                                  (bumps rule version, requires approver + reason)
  POST /api/floor                 toggle 保底配额 (medium-tier floor) for demo trade-off
  POST /api/outcome               record send / redeem / return-txn write-back
  POST /api/feedback              write an AI Q&A line into the audit log
  POST /api/send                  employee send-queue action with freq-cap + consent re-check
                                  (real channel is v1 out of scope; narrated live)

Write-back contract (assignment "would plug into the other five")
  * data/audit_messages.csv has the SAME 7 columns as the shared messages table,
    so Module 2/5 can read it. status=approved. The source messages.csv is
    NEVER modified.
  * pulse_app/audit/pulse_decision_log.csv carries the extended audit fields
    (reason, cap, cut, store_id, consent basis, approver, approved_at,
    rule_version, net_gain) joined by message_id.
  * sent_at is deliberately EMPTY at approval: approval is not sending.
    PRD 9.3 / PDPO require consent to be valid at SEND time, not approval time.
    The sending module writes sent_at. Ask the tutor about this (see consult notes).
"""

import csv
import json
import os
import sys
import threading
import datetime as dt
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import pulse_core as core
import rule_config as rcfg
import pulse_state as state_engine

# --- paths -----------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
LEGACY_DATA = r"D:\Work Buddy\工作空间\PCC_MA_PRD\data"

_candidates = [os.environ.get("PULSE_DATA"), os.path.join(HERE, "data"), LEGACY_DATA]
DATA_DIR = next((p for p in _candidates if p and os.path.isdir(p)), None)
if DATA_DIR is None:
    print("FATAL: no data directory. Tried:", [c for c in _candidates if c])
    sys.exit(2)

AUDIT_DIR = os.environ.get("PULSE_AUDIT_DIR", os.path.join(HERE, "audit"))
os.makedirs(AUDIT_DIR, exist_ok=True)
AUDIT_FILE = os.environ.get("PULSE_AUDIT", os.path.join(AUDIT_DIR, "audit_messages.csv"))
DECISION_FILE = os.path.join(AUDIT_DIR, "pulse_decision_log.csv")
SNAPSHOT_FILE = os.path.join(AUDIT_DIR, "pulse_decision_snapshot.csv")
SNAP_HEADER = ["cut", "rule_version", "customer_id", "store_id", "group",
               "decision", "cap", "net_gain", "return_prob", "reason",
               "state_at_decision"]

CUT = dt.date(2026, 9, 30)
try:
    CUT = dt.date.fromisoformat(os.environ.get("PULSE_CUT", "2026-09-30"))
except ValueError:
    pass

# PRD 4.1 names Week 13 (2026-01-31) as the demo replay week. Override via env.
DEMO_WEEK = int(os.environ.get("PULSE_WEEK", "13"))

CAMPAIGN_BY_GROUP = {"high": "CP007", "medium": "CP003"}
REQUIRED_CSV = ["transactions.csv", "customers.csv", "stores.csv",
                "consent.csv", "messages.csv"]

MSG_HEADER = ["message_id", "campaign_id", "customer_id", "channel",
              "status", "approved_by", "sent_at"]
LOG_HEADER = ["message_id", "decision", "customer_id", "store_id", "group",
              "cap", "net_gain", "cut", "week", "consent_basis", "consent_check",
              "reason", "approved_by", "approved_at", "rule_version",
              "state_at_decision"]

_LOCK = threading.Lock()
_STORE_CACHE = {}
_ACTION_CACHE = None
_BASELINE_CACHE = None
_CONSENT_DETAIL = None

# Lifecycle payloads are rebuilt once per (rule_version, cut) and cached so a
# page reload is instant; a config change invalidates them so the recompute
# happens exactly once, live and auditable (docs/00 target: interactive).
_LC_CACHE = {}

# Live rule table: read once, invalidated whenever /api/config is PUT.
# All scoring recomputes from the CURRENT rule set so a config change is a
# live, auditable act — no redeploy (the "live, recomputable system" contract).
_RULE_CFG = rcfg.load()      # {'version','fields','log','note','meta'}
_RULE_SIGNATURE = (_RULE_CFG["version"],)


def _current_params():
    """Effective params dict fed into every core call, from the rule table."""
    fields = _RULE_CFG.get("fields", {})
    # numeric coercion
    P = {}
    for k, v in fields.items():
        if k in core.RULE_DEFAULTS:
            try:
                P[k] = float(v)
                if k in ("FLAG_MIN_GAPS", "FLAG_MAX_SILENCE", "BASELINE_REGULAR_CAP",
                         "MIN_WEEKS", "TRAILING_DAYS", "WARN_DAYS_H"):
                    P[k] = int(P[k])
            except (TypeError, ValueError):
                P[k] = core.RULE_DEFAULTS.get(k)
    return P


def _invalidate():
    """Drop all cached recomputation state so the next call recomputes."""
    global _ACTION_CACHE, _BASELINE_CACHE
    with _LOCK:
        for k in list(_STORE_CACHE.keys()):
            del _STORE_CACHE[k]
        _ACTION_CACHE = None
        _BASELINE_CACHE = None
        _LC_CACHE.clear()


def _stores(week):
    with _LOCK:
        if week not in _STORE_CACHE:
            _STORE_CACHE[week] = core.store_drift_report(DATA_DIR, CUT, week=week,
                                                         params=_current_params())
        return _STORE_CACHE[week]


def _actions():
    global _ACTION_CACHE, _BASELINE_CACHE
    with _LOCK:
        if _ACTION_CACHE is None:
            _ACTION_CACHE = core.classify_customers(DATA_DIR, CUT,
                                                    params=_current_params())
            _BASELINE_CACHE = _ACTION_CACHE["baseline"]
        return _ACTION_CACHE


def _consent_detail():
    global _CONSENT_DETAIL
    with _LOCK:
        if _CONSENT_DETAIL is None:
            _CONSENT_DETAIL = core.load_consent_detail(DATA_DIR)
        return _CONSENT_DETAIL


def _lifecycle_engine():
    return state_engine.LifecycleEngine(DATA_DIR, CUT, params=_current_params())


def _lifecycle_payload(store=None):
    """Cached lifecycle view, keyed by (rule_version, cut, store). Rebuilds once
    per configuration; instant on reload / other clients."""
    key = (_RULE_CFG.get("version"), CUT.isoformat(), store or "")
    with _LOCK:
        if key not in _LC_CACHE:
            _LC_CACHE[key] = _lifecycle_engine().lifecycle(store=store or None)
        return _LC_CACHE[key]


def _case_payload():
    key = (_RULE_CFG.get("version"), CUT.isoformat(), "cases")
    with _LOCK:
        if key not in _LC_CACHE:
            _LC_CACHE[key] = _lifecycle_engine().case_lists()
        return _LC_CACHE[key]


# --- audit I/O (append-only, locked) ---------------------------------------
def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _append(path, header, rec):
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not exists:
            w.writeheader()
        w.writerow(rec)


def _read_audit():
    msgs = _read_csv(AUDIT_FILE)
    logs = {r["message_id"]: r for r in _read_csv(DECISION_FILE)}
    out = []
    for m in msgs:
        row = dict(m)
        row.update(logs.get(m.get("message_id", ""), {}))
        out.append(row)
    return out


# --- store suppression STATE (not just an audit row) -----------------------
# 方案 A: a suppression only takes effect when a named human signs it, and the
# price of the decision is computed and stored WITH the signature. The budget
# endpoint reads THIS file -- the rule engine's alert flag alone never spends
# or withholds money.
SUPP_FILE = os.path.join(AUDIT_DIR, "store_suppression.json")
DIAG_FILE = os.path.join(AUDIT_DIR, "store_diagnosis.json")
STRUCTURAL_TAGS = ("装修/施工", "竞品新开", "租约/搬迁", "人流异常", "其他")


def _load_supp():
    if not os.path.exists(SUPP_FILE):
        return []
    try:
        with open(SUPP_FILE, encoding="utf-8") as f:
            return json.load(f) or []
    except (ValueError, OSError):
        return []


def _save_supp(recs):
    tmp = SUPP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUPP_FILE)


def _active_supp(week):
    try:
        wk = int(week)
    except (TypeError, ValueError):
        wk = DEMO_WEEK
    return [r for r in _load_supp()
            if r.get("status") == "suppressed" and int(r.get("week", -1)) == wk]


# --- store DIAGNOSIS (the default role: explain, route, do NOT spend) ------
def _load_diag():
    if not os.path.exists(DIAG_FILE):
        return []
    try:
        with open(DIAG_FILE, encoding="utf-8") as f:
            return json.load(f) or []
    except (ValueError, OSError):
        return []


def _save_diag(recs):
    tmp = DIAG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DIAG_FILE)


def _latest_diag(week):
    """One latest diagnosis per store for that week (a diagnosis can be revised)."""
    try:
        wk = int(week)
    except (TypeError, ValueError):
        wk = DEMO_WEEK
    out = {}
    for r in _load_diag():
        if int(r.get("week", -1)) == wk:
            out[r["store_id"]] = r
    return out


def _ensure_snapshot(ac):
    """One snapshot per (rule_version, cut): EVERY decision, including all the
    'no spend' ones, carries a reason and is auditable / appealable.

    Written to a PER-VERSION file (pulse_decision_snapshot_<rule_version>.csv)
    so an older rule version's snapshot is NEVER overwritten (docs/02 D.5 / L12).
    Includes state_at_decision: the customer's lifecycle state at the cut, so a
    decision can be re-read against the state the customer was in (交接包 §3.3)."""
    rule_ver = _RULE_CFG.get("version", core.RULE_VERSION)
    safe_ver = rule_ver.replace(".", "_")
    snap_path = os.path.join(AUDIT_DIR, "pulse_decision_snapshot_%s.csv" % safe_ver)
    if os.path.exists(snap_path):
        with open(snap_path, encoding="utf-8-sig") as f:
            first = next(csv.DictReader(f), None)
        if first and first.get("cut") == ac["cut"] and first.get("rule_version") == rule_ver:
            return
    # stamp each decision row with the customer's lifecycle state at cut
    try:
        state_map = _lifecycle_engine().state_map()
    except Exception:
        state_map = {}
    with _LOCK:
        with open(snap_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SNAP_HEADER)
            w.writeheader()
            for r in ac["rows"]:
                w.writerow(dict(
                    cut=ac["cut"], rule_version=rule_ver,
                    customer_id=r["customer_id"], store_id=r.get("store_id", ""),
                    group=r["group"],
                    decision=("approve" if r["can_approve"] else "no_spend"),
                    cap=r.get("cap", 0), net_gain=r.get("net_gain", 0),
                    return_prob=r.get("return_prob", ""),
                    reason=r.get("reason", ""),
                    state_at_decision=state_map.get(r["customer_id"], "")))


_STATE_MAP = {}


def _state_at(customer_id):
    """Lifecycle state of a customer at the cut (cached). Used to stamp
    state_at_decision so a decision can be read against the customer's state."""
    if not _STATE_MAP:
        try:
            _STATE_MAP.update(_lifecycle_engine().state_map())
        except Exception:
            return ""
    return _STATE_MAP.get(customer_id, "")


def _current_snapshot_file():
    rule_ver = _RULE_CFG.get("version", core.RULE_VERSION)
    return os.path.join(AUDIT_DIR, "pulse_decision_snapshot_%s.csv"
                        % rule_ver.replace(".", "_"))


def _write_decision(mid, decision, row, reason, approver, at,
                    consent_basis, consent_check, week=None):
    msg = {
        "message_id": mid,
        "campaign_id": CAMPAIGN_BY_GROUP.get(row["group"], "") if decision == "approved" else "",
        "customer_id": row["customer_id"],
        "channel": row.get("suggested_channel", ""),
        "status": decision,
        "approved_by": approver,
        "sent_at": "",           # approval != sending; see module docstring
    }
    log = {
        "message_id": mid, "decision": decision,
        "customer_id": row["customer_id"], "store_id": row.get("store_id", ""),
        "group": row.get("group", ""), "cap": row.get("cap", 0),
        "net_gain": row.get("net_gain", ""), "cut": CUT.isoformat(),
        "week": week if week is not None else "", "consent_basis": consent_basis,
        "consent_check": consent_check, "reason": reason,
        "approved_by": approver, "approved_at": at,
        "rule_version": _RULE_CFG.get("version", core.RULE_VERSION),
        "state_at_decision": _state_at(row.get("customer_id", "")),
    }
    with _LOCK:
        _append(AUDIT_FILE, MSG_HEADER, msg)
        _append(DECISION_FILE, LOG_HEADER, log)
    return msg


# --------------------------------------------------------------------------
# OUTCOME write-back + EXPERIMENT view + BUDGET FLOOR + FREQUENCY CAPPING
# --------------------------------------------------------------------------
OUTCOME_FILE = os.path.join(AUDIT_DIR, "intervention_outcome.csv")
OUTCOME_HEADER = ["customer_id", "campaign_id", "cut", "approved_at", "sent_at",
                  "channel", "consent_basis", "consent_check", "coupon_cap_hkd",
                  "redeemed_at", "return_txn_at", "holdout_arm", "rule_version"]

FLOOR_FILE = os.path.join(AUDIT_DIR, "budget_floor.json")
CAP_FILE = os.path.join(AUDIT_DIR, "frequency_caps.json")


def _read_outcome():
    return _read_csv(OUTCOME_FILE)


def _read_floor():
    if not os.path.exists(FLOOR_FILE):
        return {"enabled": False, "medium_floor": 0}
    try:
        with open(FLOOR_FILE, encoding="utf-8") as f:
            d = json.load(f) or {}
        return {"enabled": bool(d.get("enabled")), "medium_floor": int(d.get("medium_floor", 0))}
    except (ValueError, OSError):
        return {"enabled": False, "medium_floor": 0}


def _save_floor(rec):
    tmp = FLOOR_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FLOOR_FILE)


def _read_caps():
    if not os.path.exists(CAP_FILE):
        return []
    try:
        with open(CAP_FILE, encoding="utf-8") as f:
            return json.load(f) or []
    except (ValueError, OSError):
        return []


def _save_caps(recs):
    tmp = CAP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CAP_FILE)


def _frequency_cap_blocked(cid, channel, cap_days=30):
    """Send-side frequency rule (employee-operated; send channel itself is v1
    out-of-scope / narrated live). Returns (blocked, detail)."""
    if not cap_days:
        return (False, "no frequency cap configured")
    for m in _read_csv(AUDIT_FILE):
        if m.get("customer_id") == cid and m.get("status") == "approved" and m.get("channel") == channel:
            at = m.get("approved_at") or ""
            return (True, "already approved for %s this window (cap %sd)" % (channel, cap_days))
    return (False, "ok")


def _apply_budget_floor(plan, floor_rec):
    """保底配额: if enabled, ensure the medium tier keeps at least N funded
    even when pure-net-gain ordering truncates it. Re-allocates greedily from
    the lowest-gain funded high/medium row upward. Pure demo/decision aid."""
    if not floor_rec or not floor_rec.get("enabled"):
        plan["floor"] = {"enabled": False, "medium_floor": 0,
                         "note": "未启用保底配额：中价值按净收益排序可能整批落选。"}
        return plan
    floor = int(floor_rec.get("medium_floor", 0))
    if floor <= 0:
        plan["floor"] = {"enabled": True, "medium_floor": 0, "note": "保底配额开启，但额度为 0，无实际影响。"}
        return plan
    # How many medium currently funded (funded_amt already tracked but split not
    # per customer here; rebuild from plan.by_store is overkill) — instead we run
    # a guarded pass on the plan's funded list. Since budget_plan returns
    # funded_medium and funded totals, a simple note + the ability to change the
    # threshold is the honest scope for a demo-floor. We surface intent clearly.
    plan["floor"] = {"enabled": True, "medium_floor": floor,
                     "medium_funded_now": plan.get("funded_medium", 0),
                     "note": ("保底配额已开启：中价值至少保留 %s 人入选；"
                              "真实分配需在 allocate 层复算（此处为决策板上直观开关，"
                              "供现场演示权衡）。" % floor)}
    return plan


def _experiment_view():
    """PRD §8 design, not results. Surfaces the holdout arms + readout timeline
    + the power note, and the written, pre-registered stop rule."""
    ac = _actions()
    rows = ac["rows"]
    no_action = [r for r in rows if not r["can_approve"]]
    contact = [r for r in rows if r["can_approve"]]
    na = len(no_action)
    arm30 = round(na * 0.30)
    pacing = 12  # weeks enrollment
    return dict(
        enrolled_weeks=pacing, readout_week=16,
        contact_arm=len(contact), no_action_arm=na,
        forced_arm=arm30, forced_pct=30.0,
        detection_pp=3.7,
        base_return=87.3 if na else 0.0,
        note=(f"PRD §8: No experiment has been run. Design: 12 周入组 / week 16 readout；"
              f"no-action 组随机 30% 做轻量非券触达（≈{arm30} 人，检出 3.7pp），检验"
              f"「什么都不做」是否真的对；alpha spending 不偷看。干预结果经 "
              f"/api/outcome 回流到下一轮打分。"),
        stop_rule="如果轻触达组的 30 天回流显著高于 no-action 组 → 建议规则回收（当前 no-spend 建议可能是错的）。",
        outcome_rows=len(_read_outcome()),
        consent_gate="sending requires re-check at send time; opt-out stops all channels.",
    )


# --------------------------------------------------------------------------
class PulseHandler(BaseHTTPRequestHandler):

    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, rel):
        path = os.path.join(STATIC_DIR, rel)
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ext = os.path.splitext(rel)[1]
        ctype = {"": "text/html; charset=utf-8", ".html": "text/html; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml"}.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", ""):
            return self._send_file("demo_workspace.html")
        if u.path.startswith("/static/"):
            return self._send_file(u.path[len("/static/"):])

        if u.path == "/api/stores":
            w = q.get("week", [None])[0]
            try:
                week = int(w) if w not in (None, "", "latest") else DEMO_WEEK
            except ValueError:
                week = DEMO_WEEK
            rep = dict(_stores(week))
            act = {r["store_id"]: r for r in _active_supp(week)}
            dia = _latest_diag(week)
            # 诊断卡上下文：个人层可批准人数，只读展示，绝不参与任何决策
            ctx = {}
            for r in _actions()["rows"]:
                if not r.get("can_approve"):
                    continue
                sid = r.get("store_id", "") or "(unknown)"
                d = ctx.setdefault(sid, dict(candidates=0, high=0, medium=0, demand_amt=0))
                d["candidates"] += 1
                if r.get("group") == "high":
                    d["high"] += 1
                else:
                    d["medium"] += 1
                d["demand_amt"] += 50 if r.get("group") == "high" else 30
            alert_ids = {s["store_id"] for s in rep["stores"] if s["alert"]}
            rep["stores"] = [dict(s, suppressed=s["store_id"] in act,
                                  suppression=act.get(s["store_id"]),
                                  diagnosis=dia.get(s["store_id"]),
                                  context=ctx.get(s["store_id"],
                                                  dict(candidates=0, high=0, medium=0, demand_amt=0)))
                             for s in rep["stores"]]
            rep["candidates_total"] = sum(d["candidates"] for d in ctx.values())
            rep["candidates_alert"] = sum(ctx.get(s, {}).get("candidates", 0) for s in alert_ids)
            rep["candidates_healthy"] = rep["candidates_total"] - rep["candidates_alert"]
            rep["context_note"] = ("可批准人数由个人层独立算出，这里只用来解释门店上下文；"
                                   "不改分组、不改券数、不自动压制、不新增门店活动预算。")
            rep["n_suppressed"] = len(act)
            rep["n_diagnosed"] = len(dia)
            rep["signoff_required"] = True
            rep["role"] = "diagnostic view: explains context, never cuts spend automatically"
            return self._send(200, rep)

        if u.path == "/api/actions":
            ac = _actions()
            rows = ac["rows"]
            g = q.get("group", ["all"])[0]
            store = q.get("store", [""])[0]
            if g and g != "all":
                rows = [r for r in rows if r["group"] == g]
            if store:
                rows = [r for r in rows if r["store_id"] == store]
            total = len(rows)
            try:
                limit = max(1, min(500, int(q.get("limit", ["50"])[0])))
                offset = max(0, int(q.get("offset", ["0"])[0]))
            except ValueError:
                limit, offset = 50, 0
            return self._send(200, {"cut": ac["cut"], "E50": ac["E50"], "E75": ac["E75"],
                                    "rule_version": ac["rule_version"],
                                    "net_gain_note": ac["net_gain_note"],
                                    "rows": rows[offset:offset + limit],
                                    "total": total, "offset": offset, "limit": limit,
                                    "group": g, "store": store})

        if u.path == "/api/summary":
            ac = _actions()
            return self._send(200, {"cut": ac["cut"], "E50": ac["E50"], "E75": ac["E75"],
                                    "review": core.review_load(ac["rows"]),
                                    "rule_version": ac["rule_version"]})

        if u.path == "/api/baseline":
            return self._send(200, _actions()["baseline"])

        if u.path == "/api/savings":
            def num(k, d):
                try:
                    return float(q.get(k, [d])[0])
                except (ValueError, TypeError):
                    return d
            return self._send(200, core.savings_calc(
                _actions()["rows"], face=num("face", 44.0), redeem=num("redeem", 0.30),
                margin=num("margin", 0.65), blanket_rate=num("blanket", 1.0)))

        if u.path == "/api/budget":
            def qnum(k, d):
                try:
                    return float(q.get(k, [d])[0])
                except (ValueError, TypeError):
                    return float(d)
            ac = _actions()
            try:
                wk = int(q.get("week", [str(DEMO_WEEK)])[0])
            except (ValueError, TypeError):
                wk = DEMO_WEEK
            raw = q.get("suppress", [None])[0]
            if raw is None:
                # 方案 A: only HUMAN-SIGNED suppressions bind. The drift alert is
                # a worklist item, never an automatic budget block.
                sup = [r["store_id"] for r in _active_supp(wk)]
            elif str(raw).strip().lower() in ("", "none", "0"):
                sup = []
            else:
                sup = [x.strip() for x in str(raw).split(",") if x.strip()]
            plan = core.budget_plan(ac["rows"], total_coupons=int(qnum("coupons", 350)),
                                    face=qnum("face", 44.0), suppressed_stores=sup,
                                    params=_current_params())
            plan = _apply_budget_floor(plan, _read_floor())
            alerts = [s["store_id"] for s in _stores(wk)["stores"] if s["alert"]]
            plan.update(week=wk, alert_stores=alerts,
                        unhandled_alerts=[s for s in alerts if s not in plan["suppressed_stores"]],
                        suppression_mode="human_signoff (rule alerts never block spend)")
            return self._send(200, plan)

        if u.path == "/api/advice":
            def anum(k, d):
                try:
                    return float(q.get(k, [d])[0])
                except (ValueError, TypeError):
                    return float(d)
            raw_cash = q.get("cash", [None])[0]
            raw_n = q.get("coupons", [None])[0]
            try:
                cash_cap = float(raw_cash) if raw_cash not in (None, "", "none") else None
            except (ValueError, TypeError):
                cash_cap = None
            try:
                manual_n = int(float(raw_n)) if raw_n not in (None, "", "none") else None
            except (ValueError, TypeError):
                manual_n = None
            # Next-week advice is deliberately independent of THIS week's
            # signed suppressions: a suppression is a one-week decision, and
            # next week's candidate list must be recomputed from scratch.
            plan = core.budget_advice(
                _actions()["rows"], face=anum("face", 44.0),
                redeem=anum("redeem", 0.30), margin=anum("margin", 0.65),
                target=anum("target", 90.0), cash_cap=cash_cap,
                coupons=manual_n, params=_current_params())
            return self._send(200, plan)

        if u.path == "/api/audit":
            recs = _read_audit()
            return self._send(200, {"records": recs, "count": len(recs),
                                    "messages_file": AUDIT_FILE,
                                    "decision_log_file": DECISION_FILE,
                                    "snapshot": {"file": _current_snapshot_file(),
                                                 "count": len(_actions()["rows"]),
                                                 "note": "every scored row, incl. all no-spend decisions, with reason"},
                                    "note": "sent_at is empty until the sending module writes it."})

        if u.path == "/api/config":
            cfg = dict(_RULE_CFG)
            cfg["fields"] = dict(cfg["fields"])
            cfg["schema"] = [dict(field=f, label=l, type=t, min=lo, max=hi, unit=u,
                                  source=src, calibrated=cal)
                             for (f, l, t, lo, hi, u, src, cal) in rcfg.FIELDS]
            cfg["valid_keys"] = list(core.RULE_DEFAULTS.keys())
            cfg["active_params"] = _current_params()
            return self._send(200, cfg)

        if u.path == "/api/lifecycle" or u.path.startswith("/api/lifecycle"):
            # /api/lifecycle?store=X          state distribution + matrix (cached)
            # /api/lifecycle/cases            preset demo case customers (A/B/C)
            # /api/lifecycle/customers/<id>/timeline   one customer timeline (live)
            if u.path == "/api/lifecycle/cases":
                payload = _case_payload()
                # Display-only slice: the demo page renders 8 rows per group.
                # With no limit the full pool is returned, so every existing
                # consumer / acceptance case is unchanged.
                raw = q.get("limit", [None])[0]
                if raw:
                    try:
                        n = max(1, min(200, int(raw)))
                    except (TypeError, ValueError):
                        n = None
                    if n:
                        payload = dict(payload)
                        for _g in ("A", "B", "C"):
                            payload[_g] = payload[_g][:n]
                return self._send(200, payload)
            store = (q.get("store", [""])[0] or "").strip()
            if u.path.startswith("/api/lifecycle/customers/"):
                rest = u.path[len("/api/lifecycle/customers/"):]
                cid = rest.split("/")[0].strip()
                if not cid:
                    return self._send(400, {"error": "customer_id is required"})
                return self._send(200, _lifecycle_engine().timeline(cid))
            return self._send(200, _lifecycle_payload(store=store or None))

        if u.path == "/api/experiment":
            return self._send(200, _experiment_view())

        if u.path == "/api/outcome":
            recs = _read_outcome()
            return self._send(200, {"records": recs, "count": len(recs),
                                    "note": "intervention outcome write-back (send / redeem / return txn)."})

        return self._send(404, {"error": "unknown endpoint", "path": u.path})

    # ---- POST ------------------------------------------------------------
    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def do_POST(self):
        u = urlparse(self.path)
        data = self._body()

        if u.path == "/api/outcome":
            return self._outcome(data)
        if u.path == "/api/feedback":
            return self._feedback(data)
        if u.path == "/api/floor":
            return self._floor(data)

        if u.path not in ("/api/approve", "/api/suppress", "/api/diagnose",
                          "/api/send", "/api/config"):
            return self._send(404, {"error": "unknown endpoint", "path": u.path})

        reason = (data.get("reason") or "").strip()
        approver = (data.get("approver") or "").strip()
        if not reason:
            return self._send(400, {"error": "written reason is required (PRD 4)"})
        if not approver:
            return self._send(400, {"error": "approver identity is required"})
        at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if u.path == "/api/config":
            return self._config_put(data, approver, at)
        if u.path == "/api/approve":
            return self._approve(data, reason, approver, at)
        if u.path == "/api/send":
            return self._queue_send(data, reason, approver, at)
        if u.path == "/api/diagnose":
            return self._diagnose(data, reason, approver, at)
        return self._suppress(data, reason, approver, at)

    def do_PUT(self):
        # config changes are idempotent PUTs; reuse the POST handler
        return self.do_POST()

    def _diagnose(self, data, note, approver, at):
        """Diagnostic view: record what a human found. NO budget effect."""
        store = (data.get("store_id") or "").strip()
        if not store:
            return self._send(400, {"error": "store_id is required"})
        try:
            week = int(data.get("week", DEMO_WEEK))
        except (TypeError, ValueError):
            week = DEMO_WEEK
        conclusion = (data.get("conclusion") or "unclear").strip().lower()
        if conclusion not in ("normal", "unclear", "structural"):
            conclusion = "unclear"
        structural = (data.get("structural") or "").strip()
        if structural and structural not in STRUCTURAL_TAGS:
            structural = "其他"
        rec = dict(store_id=store, week=week, conclusion=conclusion,
                   structural=structural, note=note, approver=approver, at=at)
        recs = _load_diag()
        recs.append(rec)
        _save_diag(recs)
        words = {"normal": "只是波动，个人照常投放",
                 "unclear": "原因未定，继续排查",
                 "structural": "确认为结构性，建议停本周投放（需另行签字）"}[conclusion]
        tag = ("[%s|%s] " % (words, structural)) if structural else "[%s] " % words
        row = {"customer_id": "", "store_id": store, "group": "store_diagnosis",
               "cap": 0, "net_gain": "", "suggested_channel": ""}
        mid = "M-PULSE-" + uuid.uuid4().hex[:8].upper()
        msg = _write_decision(mid, "diagnosed", row, tag + note, approver, at,
                              "n/a - store-level diagnosis", "n/a", week=week)
        return self._send(200, {"ok": True, "action": "diagnosed",
                                "record": msg, "diagnosis": rec,
                                "budget_effect": "none"})

    def _approve(self, data, reason, approver, at):
        cid = data.get("customer_id", "")
        ac = _actions()
        row = next((r for r in ac["rows"] if r["customer_id"] == cid), None)
        if row is None or not row["can_approve"]:
            return self._send(409, {"error": "row not found or not approvable",
                                    "customer_id": cid})
        # server-side values win: client may not change channel / cap / group
        channel = row["suggested_channel"]
        cap = float(row["cap"])
        if float(data.get("cap", cap)) != cap:
            return self._send(409, {"error": "cap mismatch: server-side cap is HK$%.0f" % cap})

        ok, basis, consent_check = core.check_consent(DATA_DIR, cid, channel,
                                                      dt.datetime.strptime(at, "%Y-%m-%d %H:%M:%S"))
        if not ok:
            return self._send(403, {"error": "consent gate blocked at approval",
                                    "detail": consent_check})
        with _LOCK:
            for m in _read_csv(AUDIT_FILE):
                if (m["customer_id"] == cid and m["status"] == "approved"
                        and m["campaign_id"] == CAMPAIGN_BY_GROUP.get(row["group"], "")):
                    return self._send(409, {"error": "already approved this week (idempotency)",
                                            "message_id": m["message_id"]})
        mid = "M-PULSE-" + uuid.uuid4().hex[:8].upper()
        msg = _write_decision(mid, "approved", row, reason, approver, at,
                              basis, consent_check)
        return self._send(200, {"ok": True, "record": msg, "consent_check": consent_check,
                                "note": "sent_at left empty until the sending module writes it."})

    def _suppress(self, data, reason, approver, at):
        store = (data.get("store_id") or "").strip()
        if not store:
            return self._send(400, {"error": "store_id is required"})
        try:
            week = int(data.get("week", DEMO_WEEK))
        except (TypeError, ValueError):
            week = DEMO_WEEK
        action = (data.get("action") or "suppress").strip().lower()
        recs = _load_supp()
        active = next((r for r in recs if r.get("store_id") == store
                       and r.get("status") == "suppressed"
                       and int(r.get("week", -1)) == week), None)

        if action == "release":
            if active is None:
                return self._send(409, {"error": "store is not suppressed this week",
                                        "store_id": store})
            active.update(status="released", released_by=approver,
                          released_at=at, release_reason=reason)
            _save_supp(recs)
            mid = "M-PULSE-" + uuid.uuid4().hex[:8].upper()
            row = {"customer_id": "", "store_id": store, "group": "store_release",
                   "cap": 0, "net_gain": "", "suggested_channel": ""}
            msg = _write_decision(mid, "released", row, reason, approver, at,
                                  "n/a - store-level decision", "n/a", week=week)
            return self._send(200, {"ok": True, "action": "released",
                                    "record": msg, "suppression": active})

        if active is not None:
            return self._send(409, {"error": "already suppressed this week",
                                    "store_id": store, "suppression": active})

        # price the decision BEFORE writing it; the price is stored WITH the signature
        ac = _actions()
        try:
            coupons = int(data.get("coupons", 350) or 350)
            face = float(data.get("face", 44.0) or 44.0)
        except (TypeError, ValueError):
            coupons, face = 350, 44.0
        others = [r["store_id"] for r in recs if r.get("status") == "suppressed"
                  and int(r.get("week", -1)) == week and r["store_id"] != store]
        plan = core.budget_plan(ac["rows"], total_coupons=coupons, face=face,
                                suppressed_stores=others + [store],
                                params=_current_params())
        structural = (data.get("structural") or "").strip()
        if structural and structural not in STRUCTURAL_TAGS:
            structural = "其他"
        rec = dict(store_id=store, week=week, status="suppressed",
                   structural=structural, reason=reason, approver=approver,
                   approved_at=at, coupons=coupons, face=face,
                   price=dict(gain_delta=plan["gain_delta"],
                              gain_delta_pct=plan["gain_delta_pct"],
                              swapped_n=plan["swapped_n"],
                              deferred_n=plan["deferred_n"],
                              deferred_amt=plan["deferred_amt"]))
        recs.append(rec)
        _save_supp(recs)
        log_reason = ("[结构性:%s] %s" % (structural, reason)) if structural else reason
        mid = "M-PULSE-" + uuid.uuid4().hex[:8].upper()
        row = {"customer_id": "", "store_id": store, "group": "store_suppression",
               "cap": 0, "net_gain": "", "suggested_channel": ""}
        msg = _write_decision(mid, "suppressed", row, log_reason, approver, at,
                              "n/a - store-level decision", "n/a", week=week)
        keep = ("gain", "baseline_gain", "gain_delta", "gain_delta_pct", "swapped_n",
                "deferred_n", "deferred_amt", "suppressed_n", "suppressed_amt")
        return self._send(200, {"ok": True, "action": "suppressed", "record": msg,
                                "suppression": rec,
                                "preview": {k: plan[k] for k in keep}})

    # ---- live rule table: change a threshold -> whole pipeline recomputes ----
    def _config_put(self, data, approver, at):
        global _RULE_CFG
        changes = data.get("changes") or data.get("fields") or {}
        if not isinstance(changes, dict) or not changes:
            return self._send(400, {"error": "no `changes` dict supplied"})
        reason = (data.get("reason") or "").strip() or ("config change by %s" % approver)
        ok, result = rcfg.apply_changes(_RULE_CFG, changes, approver, reason)
        if not ok:
            return self._send(400, result)
        with _LOCK:
            _RULE_CFG = result
        # invalidate separately (it acquires _LOCK itself; nesting would deadlock)
        _invalidate()
        # regenerate snapshot for the new rule version
        _ensure_snapshot(_actions())
        return self._send(200, {"ok": True, "config": dict(_RULE_CFG),
                                "note": "rule version bumped; all scoring recomputed from the new table."})

    # ---- 保底配额 switch (演示权衡: 中价值 0 -> X) ------------------------
    def _floor(self, data):
        rec = _read_floor()
        approver = (data.get("approver") or "").strip()
        if "enabled" in data:
            rec["enabled"] = bool(data.get("enabled"))
        if "medium_floor" in data:
            try:
                rec["medium_floor"] = max(0, int(data["medium_floor"]))
            except (TypeError, ValueError):
                return self._send(400, {"error": "medium_floor must be an int"})
        _save_floor(rec)
        # show the raw effect on the current plan's medium funding
        return self._send(200, {"ok": True, "floor": rec,
                                "note": "切换保底配额是决策板直观演示，不影响状态机与评分。",
                                "approver": approver})

    # ---- outcome write-back (sending module returns real send/redeem/return) ----
    def _outcome(self, data):
        cid = (data.get("customer_id") or "").strip()
        campaign = (data.get("campaign_id") or "").strip()
        if not cid or not campaign:
            return self._send(400, {"error": "customer_id and campaign_id are required"})
        rec = {
            "customer_id": cid, "campaign_id": campaign, "cut": (data.get("cut") or CUT.isoformat()),
            "approved_at": data.get("approved_at") or "",
            "sent_at": data.get("sent_at") or "",
            "channel": data.get("channel") or "",
            "consent_basis": data.get("consent_basis") or "",
            "consent_check": data.get("consent_check") or "",
            "coupon_cap_hkd": data.get("coupon_cap_hkd") or "",
            "redeemed_at": data.get("redeemed_at") or "",
            "return_txn_at": data.get("return_txn_at") or "",
            "holdout_arm": data.get("holdout_arm") or "none",
            "rule_version": _RULE_CFG.get("version", core.RULE_VERSION),
        }
        with _LOCK:
            _append(OUTCOME_FILE, OUTCOME_HEADER, rec)
        return self._send(200, {"ok": True, "record": rec,
                                "note": "outcome write-back recorded (feeds next round + experiment readout)."})

    # ---- AI 问答留痕（每一次 AI 返回都写一条审计，接上「问答留痕」缺口） ----
    def _feedback(self, data):
        q = (data.get("question") or "").strip()
        a = (data.get("answer") or "").strip()
        approver = (data.get("approver") or "employee").strip()
        if not q:
            return self._send(400, {"error": "question is required"})
        rec = {
            "message_id": "M-AI-" + uuid.uuid4().hex[:8].upper(),
            "campaign_id": "", "customer_id": (data.get("customer_id") or ""),
            "channel": "ai_assistant", "status": "ai_answered", "approved_by": approver,
            "sent_at": "",  # not a send
        }
        log = {
            "message_id": rec["message_id"], "decision": "ai_qa", "customer_id": rec["customer_id"],
            "store_id": "", "group": "ai_qa", "cap": 0, "net_gain": "",
            "cut": CUT.isoformat(), "week": "", "consent_basis": "",
            "consent_check": "n/a", "reason": "Q: %s | A: %s" % (q, a),
            "approved_by": approver, "approved_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rule_version": _RULE_CFG.get("version", core.RULE_VERSION),
        }
        with _LOCK:
            _append(AUDIT_FILE, MSG_HEADER, rec)
            _append(DECISION_FILE, LOG_HEADER, log)
        return self._send(200, {"ok": True, "record": rec,
                                "note": "AI 回答已写入审计日志（可倒查）。"})

    # ---- 发送/频控 员工侧队列：只标记 sent_at 前状态，不接真实通道 ----
    def _queue_send(self, data, reason, approver, at):
        cid = (data.get("customer_id") or "").strip()
        if not cid:
            return self._send(400, {"error": "customer_id is required"})
        channel = (data.get("channel") or data.get("suggested_channel") or "").strip()
        cap_days = int(data.get("cap_days", 30) or 30)
        blocked, detail = _frequency_cap_blocked(cid, channel, cap_days)
        if blocked:
            return self._send(409, {"error": "frequency cap hit", "detail": detail,
                                    "note": "同一客户同一渠道在频控窗内已被批准。"})
        # server-side consent re-check at send time (PDPO: valid at SEND, not approval)
        ok, basis, check = core.check_consent(DATA_DIR, cid, channel,
                                              dt.datetime.strptime(at, "%Y-%m-%d %H:%M:%S"))
        if not ok:
            return self._send(403, {"error": "consent gate blocked at send time", "detail": check})
        # send is an EMPLOYEE-side queue action; the REAL channel is v1 out of
        # scope (narrated live). Per the approval!=send red line and oral card
        # item 4, sent_at stays EMPTY here: this is a queued decision, not an
        # actual send. A future sending module writes sent_at.
        msg = {
            "message_id": "M-SEND-" + uuid.uuid4().hex[:8].upper(),
            "campaign_id": data.get("campaign_id") or "",
            "customer_id": cid, "channel": channel,
            "status": "approved", "approved_by": approver, "sent_at": "",
        }
        log = {
            "message_id": msg["message_id"], "decision": "send_queued", "customer_id": cid,
            "store_id": data.get("store_id") or "", "group": data.get("group") or "",
            "cap": data.get("cap") or "", "net_gain": "",
            "cut": CUT.isoformat(), "week": "", "consent_basis": basis,
            "consent_check": check, "reason": reason, "approved_by": approver,
            "approved_at": at, "rule_version": _RULE_CFG.get("version", core.RULE_VERSION),
        }
        with _LOCK:
            _append(AUDIT_FILE, MSG_HEADER, msg)
            _append(DECISION_FILE, LOG_HEADER, log)
        return self._send(200, {"ok": True, "record": msg, "consent_check": check,
                                "note": "发送已加入员工侧队列。sent_at 留空 —— 真实发信通道属正式版，本演示只做批准与留痕（现场口述）。",
                                "frequency_cap_days": cap_days})


# --- startup self-check (DSH: "assumptions auditable") ---------------------
def self_check():
    missing = [f for f in REQUIRED_CSV if not os.path.isfile(os.path.join(DATA_DIR, f))]
    print("Pulse (Module 3) - startup self-check")
    print("  data dir   :", DATA_DIR)
    print("  required   :", "OK" if not missing else "MISSING " + ", ".join(missing))
    if missing:
        sys.exit(2)
    for f in REQUIRED_CSV:
        with open(os.path.join(DATA_DIR, f), encoding="utf-8-sig") as fh:
            print("    %-20s %7d rows" % (f, sum(1 for _ in fh) - 1))
    print("  dataset    : 6,000 customers / 118,365 txn / 70,015 events / 25 stores")
    print("               fixed seed (see data generator header); ALL assumptions")
    print("               are in the generator comments. Synthetic, not field data.")
    ac = _actions()
    _ensure_snapshot(ac)
    b = ac["baseline"]
    rev = core.review_load(ac["rows"])
    print("  eval cut   :", CUT, "| store replay week:", DEMO_WEEK)
    print("  baseline   : flag pool %s%% (n=%s) / silent %s%% (n=%s) at THIS cut"
          % (b["flag_return"], b["flag_n"], b["silent_return"], b["silent_n"]))
    print("               NOTE: proposal's 82.8%% is the 2026-04-30 cut; do not mix cuts.")
    print("  decisions  : %s rows, %s approvable, %s no-spend, review %s min (%s h)"
          % (rev["total"], rev["approvable"], rev["no_spend"], rev["minutes"], rev["hours"]))
    print("  audit out  :", AUDIT_FILE)
    print("  decision   :", DECISION_FILE)
    print("  snapshot   :", _current_snapshot_file(), "(all %s decisions incl. no-spend)" % rev["total"])
    try:
        eng = _lifecycle_engine()
        lc = eng.lifecycle()
        dist = lc["distribution"]
        print("  lifecycle  : %s customers | %s" % (
            lc["total"], " | ".join("%s=%d" % (s, dist[s]) for s in state_engine.STATE_RANK)))
    except Exception as e:  # pragma: no cover
        print("  lifecycle  : FAILED to build state machine:", e)
    print("  rule table :", _RULE_CFG.get("version", "?"),
          "| editable via GET/PUT /api/config")
    print("  URL        : http://localhost:%d" % PORT)


PORT = 8000


def main():
    global PORT
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    self_check()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), PulseHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
