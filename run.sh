#!/usr/bin/env bash
# Pulse 决策工作台 · 一键启动 8100（macOS / Linux）
set -e
cd "$(dirname "$0")"

export PYTHONUTF8=1
export PULSE_DATA="$PWD/data"
export PULSE_CUT=2026-09-30
export PULSE_WEEK=13

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

echo
echo "  ============================================================"
echo "   Pulse 决策工作台  R4  (interactive live system)"
echo "  ============================================================"
echo "   Data dir : $PULSE_DATA"
echo "   Open     : http://127.0.0.1:8100/"
echo "   Stop     : Ctrl+C"
echo "  ============================================================"
echo

exec "$PY" pulse_app.py 8100
