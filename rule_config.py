# -*- coding: utf-8 -*-
"""
rule_config.py  —  Pulse rule table (the "thresholds live in a table, not code"
layer).  The dashboard recomputes the WHOLE pipeline when any rule changes, so
a threshold edit is a live, auditable, versionable act — not a redeploy.

Contract (PRD v2.2 / handover §3.3)
  * all thresholds that used to live as pulse_core constants are editable here;
  * the active snapshot is persisted to rule_config.json (under audit/);
  * every change requires a human signature (approver + reason) and bumps the
    RULE_VERSION; the prior values are kept in the change log so any decision
    can still be traced to the exact rule version that produced it;
  * reading is lock-free; writing is serialized under the server's lock.

This file is deliberately UI-agnostic: pulse_app.py mounts it as
  GET  /api/config  (current rule set + version + change log)
  PUT  /api/config  (a named approver changes one or more fields)
"""

import json
import os
import datetime as dt

import pulse_core as core

# Default/initial rule version — kept in step with pulse_core's RULE_VERSION.
BASE_RULE_VERSION = core.RULE_VERSION  # "v1.0"

# Human labels + allowed ranges, used by the config editor and PUT validation.
# (min,max) bounds are generous guards, not business-policy statements.
# Every field carries `source` / `calibrated` machine-readable markers so the
# DEMO defaults are unambiguously provisional, never silently treated as a
# settled business conclusion (see docs/02). Labels are deliberately neutral —
# the UI must not show calibration/estimate wording; that lives in the data
# layer metadata + the oral card.
FIELDS = [
    # (field, label, type, min, max, unit, source, calibrated)
    ("DEV_THRESHOLD",     "偏离判定倍率（静默/基线）",   "float", 0.5, 6.0, "×",   "provisional", False),
    ("FLAG_MIN_GAPS",     "判定所需最少消费间隔数",      "int",   2,   12,   "个",  "provisional", False),
    ("FLAG_MAX_SILENCE",  "判定流失的最长静默天数",      "int",   30,  400,  "天",  "provisional", False),
    ("BASELINE_REGULAR_CAP", "常客中位间隔上限",         "int",   7,   120,  "天",  "provisional", False),
    ("WARN_DAYS_H",       "流失预警窗口 H",              "int",   7,   120,  "天",  "provisional", False),
    ("ALERT_FIXED",       "门店漂移固定阈值",            "float", -0.5, -0.01, "",  "provisional", False),
    ("MIN_WEEKS",         "门店漂移所需最少周数",        "int",   6,   20,   "周",  "provisional", False),
    ("TRAILING_DAYS",     "回流观察窗",                  "int",   7,   90,   "天",  "provisional", False),
    ("FACE_HIGH",         "高价值券上限",                "float", 10.0, 100.0, "HK$", "provisional", False),
    ("FACE_MED",          "中价值券上限",                "float", 5.0,  80.0,  "HK$", "provisional", False),
    ("FACE_BUDGET",       "预算折算券面值",              "float", 10.0, 100.0, "HK$", "provisional", False),
    ("REDEMPTION",        "兑换率",                      "float", 0.0, 1.0, "",    "provisional", False),
    ("GROSS_MARGIN",      "毛利率",                      "float", 0.0, 1.0, "",    "provisional", False),
]


def _cfg_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "audit", "rule_config.json")


def _sorted_fields(fields):
    return {k: fields[k] for k in core.RULE_DEFAULTS if k in fields}


def default_meta():
    """Per-field machine-readable markers: {field: {source, calibrated}}.
    DEMO defaults are `source=provisional`, `calibrated=false` — the UI must not
    print this; it lives in the data layer so a provisional value is never
    silently treated as a settled business conclusion (see docs/01, docs/02)."""
    return {f[0]: {"source": f[6], "calibrated": f[7]} for f in FIELDS}


def load():
    """Return {'version','fields','meta','log','note'}.  Never raises."""
    p = _cfg_path()
    if not os.path.exists(p):
        base = _sorted_fields(core.RULE_DEFAULTS)
        return {"version": BASE_RULE_VERSION, "fields": base,
                "meta": default_meta(),
                "log": [], "note": "default rule set (as deployed in code)"}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("fields", _sorted_fields(core.RULE_DEFAULTS))
        d.setdefault("meta", default_meta())
        d.setdefault("log", [])
        d.setdefault("note", "")
        return d
    except (ValueError, OSError):
        return {"version": BASE_RULE_VERSION, "fields": _sorted_fields(core.RULE_DEFAULTS),
                "meta": default_meta(),
                "log": [], "note": "corrupt config; fell back to defaults"}


def save(cfg):
    p = _cfg_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def apply_changes(cfg, changes, approver, reason):
    """Validate + apply a set of changes, bump version, append to change log.

    Returns (ok, result|error).
    """
    if not (approver or "").strip():
        return (False, {"error": "approver identity is required"})
    if not (reason or "").strip():
        return (False, {"error": "written change reason is required"})

    fields = dict(cfg["fields"])
    applied = {}
    for k, raw in (changes or {}).items():
        meta = next((m for m in FIELDS if m[0] == k), None)
        if meta is None:
            return (False, {"error": "unknown rule field '%s'" % k})
        _f, _, typ, lo, hi, _u, _src, _cal = meta
        try:
            v = float(raw) if typ == "float" else int(raw)
        except (TypeError, ValueError):
            return (False, {"error": "field '%s' needs a %s value" % (k, typ)})
        if not (lo <= v <= hi):
            return (False, {"error": "field '%s' out of range [%s, %s]" % (k, lo, hi)})
        if typ == "int":
            v = int(v)
        fields[k] = v
        applied[k] = v

    if not applied:
        return (False, {"error": "no valid changes supplied"})

    # version bump: v1.0 -> v1.1 -> ... (single monotonically increasing counter)
    try:
        ver_num = int(cfg.get("version", BASE_RULE_VERSION).lstrip("v").split(".")[0]) + 1
        new_version = "v%d.0" % ver_num
    except (ValueError, AttributeError):
        new_version = BASE_RULE_VERSION

    at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "from_version": cfg.get("version", BASE_RULE_VERSION),
        "to_version": new_version,
        "changed": {k: {"from": cfg["fields"].get(k), "to": v}
                    for k, v in applied.items()},
        "approver": approver.strip(),
        "reason": (reason or "").strip(),
        "at": at,
    }
    cfg["fields"] = fields
    cfg["version"] = new_version
    cfg["note"] = "last change by %s at %s: %s" % (approver.strip(), at, (reason or "").strip())
    log = list(cfg.get("log", []))
    log.append(entry)
    cfg["log"] = log
    save(cfg)  # persist the new rule version so it survives a restart (docs/02)
    return (True, cfg)


def mark_calibrated(cfg, fields, source_doc, approver, confirmed_at):
    """Formal-version calibration: set one or more fields to `calibrated=true`
    with an audit trail. Only touches meta; values are set via apply_changes."""
    meta = dict(cfg.get("meta", default_meta()))
    for k in (fields or ()):
        if k not in meta:
            continue
        meta[k] = {"source": "calibrated", "calibrated": True,
                   "doc": source_doc, "confirmed_at": confirmed_at}
    cfg["meta"] = meta
    entry = {
        "from_version": cfg.get("version", BASE_RULE_VERSION),
        "to_version": cfg.get("version", BASE_RULE_VERSION),
        "changed": {k: {"mark": "calibrated", "doc": source_doc,
                        "confirmed_at": confirmed_at} for k in (fields or ())},
        "approver": approver.strip(),
        "reason": "calibration confirmed",
        "at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    cfg["log"] = list(cfg.get("log", [])) + [entry]
    save(cfg)  # persist calibration marker
    return cfg
