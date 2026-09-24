#!/usr/bin/env python3
"""
Generate every figure used in README.md.

    python scripts/generate_diagrams.py          # writes into diagrams/

All diagrams are produced with matplotlib only (no external services), so the
documentation can be rebuilt reproducibly in CI. Charts that depend on data use
the deterministic simulator in reference/edge/simulator.py and are clearly
stamped "SIMULATED - NOT FIELD DATA".
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle, Polygon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))
from edge.verification_engine import VerificationEngine, Status  # noqa: E402
from edge.simulator import water_stream, power_profile  # noqa: E402

OUT = ROOT / "diagrams"
OUT.mkdir(exist_ok=True)

# ----------------------------------------------------------------- palette
C = {
    "bg": "#0f1720", "panel": "#16212c", "ink": "#e6edf3", "mute": "#8b98a5",
    "grid": "#2a3845", "blue": "#2f81f7", "cyan": "#39c5cf", "green": "#3fb950",
    "amber": "#d29922", "orange": "#f0883e", "red": "#f85149", "purple": "#a371f7",
    "steel": "#56687a", "yellow": "#e3b341",
}
plt.rcParams.update({
    "figure.facecolor": "white", "axes.facecolor": "white", "font.family": "DejaVu Sans",
    "font.size": 10, "axes.edgecolor": "#444", "axes.titleweight": "bold",
    "axes.titlesize": 13, "savefig.dpi": 150, "savefig.bbox": "tight",
})

SIM_STAMP = "SIMULATED - NOT FIELD DATA"


def stamp(fig, text=SIM_STAMP):
    fig.text(0.995, 0.005, text, ha="right", va="bottom", fontsize=7.5,
             color="#b00020", alpha=0.85, family="monospace")


def save(fig, name):
    path = OUT / name
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.relative_to(ROOT)}")


# ------------------------------------------------------------ diagram kit
def canvas(w, h, title=None, dark=False):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w * 10)
    ax.set_ylim(0, h * 10 + (9 if title else 0))
    ax.axis("off")
    if dark:
        fig.patch.set_facecolor(C["bg"])
        ax.set_facecolor(C["bg"])
    if title:
        ax.text(w * 5, h * 10 + 6, title, ha="center", va="top", fontsize=15,
                fontweight="bold", color=C["ink"] if dark else "#111")
    return fig, ax


def box(ax, x, y, w, h, text, fc="#e8f0fe", ec="#2f81f7", fs=9.5, bold=False,
        tc="#111", r=1.2, lw=1.6, style="round"):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"{style},pad=0.2,rounding_size={r}"
                       if style == "round" else style, fc=fc, ec=ec, lw=lw)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", color=tc, wrap=True)
    return (x, y, w, h)


def diamond(ax, cx, cy, w, h, text, fc="#fff4e5", ec="#d29922", fs=9):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, fc=fc, ec=ec, lw=1.6))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs)


def arrow(ax, x1, y1, x2, y2, color="#333", lw=1.6, text=None, style="-|>",
          ls="-", fs=8, rad=0.0, tc=None):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14,
                        color=color, lw=lw, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(a)
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, text, fontsize=fs, ha="center",
                va="center", color=tc or color,
                bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9))


def zone(ax, x, y, w, h, label, ec="#8b98a5", fc="none", tc="#555"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=2",
                                fc=fc, ec=ec, lw=1.2, ls="--"))
    ax.text(x + 1.2, y + h - 1.2, label, fontsize=8.5, color=tc, va="top",
            fontweight="bold")


# ================================================================ FIGURES
def fig_system_architecture():
    fig, ax = canvas(16, 10, "Smart Water Monitoring & Purification System - System Architecture")
    zone(ax, 2, 6, 44, 82, "FIELD SITE (outdoor enclosure)", ec="#3fb950", fc="#f3fbf4")
    zone(ax, 50, 6, 44, 82, "EDGE (Raspberry Pi gateway)", ec="#2f81f7", fc="#f2f7ff")
    zone(ax, 98, 6, 60, 82, "CLOUD + USERS", ec="#a371f7", fc="#f7f3ff")

    box(ax, 6, 74, 36, 8, "WATER SOURCE\n(well / tank / stream / mine run-off)", "#d8f1ff", "#39c5cf", bold=True)
    sensors = ["pH", "Turbidity", "TDS", "EC", "Temperature"]
    for i, s in enumerate(sensors):
        box(ax, 5 + i * 7.6, 60, 6.6, 7, s, "#fff", "#39c5cf", fs=8)
    ax.text(24, 69.5, "VERIFIED SENSORS", ha="center", fontsize=8.5, fontweight="bold", color="#1b7f86")
    box(ax, 8, 42, 32, 11, "ESP32 FIELD NODE\nacquisition | calibration\nmodes | health | alerts", "#e9f7ec", "#3fb950", bold=True)
    box(ax, 5, 28, 14, 7, "Buzzer +\nLED status", "#fff", "#f0883e", fs=8)
    box(ax, 29, 28, 14, 7, "Cellular modem\n(e.g. SIM800L)", "#fff", "#a371f7", fs=8)
    box(ax, 5, 10, 38, 11, "HYBRID POWER\nSolar + Wind -> charge controllers -> Battery\npower monitor | load priority", "#fff8e1", "#d29922", fs=8.5)
    for i in range(5):
        arrow(ax, 8.3 + i * 7.6, 60, 20 + i * 2, 53.3, "#39c5cf", lw=1.1)
    arrow(ax, 24, 74, 24, 67.3, "#39c5cf")
    arrow(ax, 16, 42, 12, 35.2, "#f0883e", lw=1.2)
    arrow(ax, 32, 42, 36, 35.2, "#a371f7", lw=1.2)
    arrow(ax, 24, 21.2, 24, 41.8, "#d29922", lw=2, text="DC bus")

    box(ax, 54, 70, 36, 9, "RECEIVER\nUART / RS-485 / Wi-Fi (configurable)", "#fff", "#2f81f7", fs=8.5)
    box(ax, 54, 56, 36, 9, "VERIFICATION ENGINE\nFMT | RNG | ROC | HLT | CON | TS | NID", "#e8f0fe", "#2f81f7", bold=True, fs=8.5)
    box(ax, 54, 42, 17, 9, "RAW STORE\n(append-only\nSQLite)", "#fff", "#2f81f7", fs=8)
    box(ax, 73, 42, 17, 9, "RESULTS +\nEVENTS +\nAUDIT", "#fff", "#2f81f7", fs=8)
    box(ax, 54, 28, 36, 9, "SYNC ENGINE\noutbox queue | idempotent upsert | backoff", "#e8f0fe", "#2f81f7", fs=8.5)
    box(ax, 54, 12, 36, 9, "LOCAL ALERTS + HEALTH MONITOR\n(works with no internet)", "#fff", "#f0883e", fs=8.5)
    arrow(ax, 40.2, 48, 53.8, 74, "#3fb950", text="raw JSON", rad=-0.15)
    arrow(ax, 72, 70, 72, 65.2, "#2f81f7")
    arrow(ax, 62, 56, 62, 51.2, "#2f81f7")
    arrow(ax, 82, 56, 82, 51.2, "#2f81f7")
    arrow(ax, 72, 42, 72, 37.2, "#2f81f7")
    arrow(ax, 72, 28, 72, 21.2, "#f0883e", ls="--")

    box(ax, 102, 62, 52, 16, "FIREBASE\nAuthentication | Firestore\nSecurity Rules (append-only) | Cloud Functions", "#f1e9ff", "#a371f7", bold=True)
    box(ax, 102, 38, 24, 14, "ENGINEER\nDASHBOARD\n(simple UI)", "#fff", "#a371f7", bold=True, fs=9)
    box(ax, 130, 38, 24, 14, "INDUSTRIAL\nDEBUGGER\n(service tool)", "#fff", "#a371f7", bold=True, fs=9)
    box(ax, 102, 14, 52, 12, "ON-SITE ENGINEER  |  SUPERVISOR  |  ADMIN\nrole-based access, audit trail", "#fff", "#555", fs=9)
    arrow(ax, 90.2, 32, 101.8, 68, "#a371f7", text="HTTPS / TLS\nwhen online", rad=0.1)
    arrow(ax, 36, 31.5, 101.8, 64, "#a371f7", ls=":", rad=-0.25)
    ax.text(47, 36, "cellular fallback (optional)", fontsize=7.5, color="#a371f7")
    arrow(ax, 114, 62, 114, 52.2, "#a371f7")
    arrow(ax, 142, 62, 142, 52.2, "#a371f7")
    arrow(ax, 114, 38, 114, 26.2, "#555")
    arrow(ax, 142, 38, 142, 26.2, "#555")
    save(fig, "01_system_architecture.png")


def fig_power_architecture():
    fig, ax = canvas(15, 9, "Hybrid Renewable Power Architecture (all ratings TBD / CONFIGURABLE)")
    box(ax, 5, 64, 24, 12, "SOLAR PANEL\n(PV array)", "#fff8e1", "#e3b341", bold=True)
    box(ax, 5, 36, 24, 12, "WIND TURBINE\n(small, AC/DC)", "#e6f7fa", "#39c5cf", bold=True)
    box(ax, 38, 64, 26, 12, "SOLAR CHARGE\nCONTROLLER\n(PWM / MPPT)", "#fff", "#e3b341")
    box(ax, 38, 36, 26, 12, "RECTIFIER +\nWIND CHARGE CTRL\n+ dump load / brake", "#fff", "#39c5cf")
    box(ax, 72, 48, 24, 16, "BATTERY\nSTORAGE\n(chemistry TBD)", "#e9f7ec", "#3fb950", bold=True, fs=10)
    box(ax, 104, 48, 22, 16, "PROTECTION\nfuse | TVS | reverse\npolarity | LVD", "#fdecea", "#f85149", fs=8.5)
    box(ax, 38, 10, 26, 12, "POWER MONITOR\nV/I sensors per source\n(e.g. INA-series, TBD)", "#f2f7ff", "#2f81f7", fs=8.5)
    loads = [("P1  ESP32 + sensors", 72), ("P1  Local alert (buzzer/LED)", 62),
             ("P2  Raspberry Pi edge", 52), ("P3  Cellular modem", 42), ("P4  Purification aux.", 32)]
    for name, y in loads:
        box(ax, 134, y - 4, 22, 7, name, "#fff", "#56687a", fs=7.5)
        arrow(ax, 126.2, 56, 133.8, y - 0.5, "#56687a", lw=1)
    ax.text(145, 80, "LOAD PRIORITY BUS", ha="center", fontsize=8.5, fontweight="bold")
    arrow(ax, 29.2, 70, 37.8, 70, "#e3b341", lw=2)
    arrow(ax, 29.2, 42, 37.8, 42, "#39c5cf", lw=2)
    arrow(ax, 64.2, 70, 71.8, 60, "#e3b341", lw=2)
    arrow(ax, 64.2, 42, 71.8, 52, "#39c5cf", lw=2)
    arrow(ax, 96.2, 56, 103.8, 56, "#3fb950", lw=2.4)
    arrow(ax, 51, 22.2, 51, 35.8, "#2f81f7", ls="--", text="measure")
    arrow(ax, 64.2, 16, 84, 47.8, "#2f81f7", ls="--", rad=0.2, text="SoC estimate")
    ax.text(80, 3, "Solar and wind each feed the shared battery through their OWN controller. "
            "Neither source is assumed to be available.", ha="center", fontsize=9, style="italic")
    save(fig, "02_power_architecture.png")


def fig_data_pipeline():
    fig, ax = canvas(17, 5.2, "Raw Data Pipeline - raw value is preserved end-to-end")
    steps = [("SENSE", "ADC / 1-Wire\nread", "#39c5cf"), ("PACK", "raw JSON +\nrecord_id + seq", "#3fb950"),
             ("SEND", "UART / RS-485\nCRC framed", "#3fb950"), ("RECEIVE", "rx timestamp\nschema check", "#2f81f7"),
             ("STORE RAW", "append-only\nraw_readings", "#2f81f7"), ("VERIFY", "rule engine\n-> result row", "#2f81f7"),
             ("QUEUE", "outbox\n(pending)", "#2f81f7"), ("SYNC", "idempotent\nupsert", "#a371f7"),
             ("DISPLAY", "dashboard /\ndebugger", "#a371f7")]
    w = 16.5
    for i, (t, s, c) in enumerate(steps):
        x = 3 + i * (w + 2.2)
        box(ax, x, 16, w, 22, f"{t}\n\n{s}", "#fff", c, fs=8.5)
        ax.text(x + w / 2, 12, f"{i+1}", ha="center", fontsize=9, color=c, fontweight="bold")
        if i < len(steps) - 1:
            arrow(ax, x + w + 0.2, 27, x + w + 2.0, 27, c)
    ax.text(85, 5, "Raw row is written BEFORE verification -> a failed/rejected verification never loses the original reading.",
            ha="center", fontsize=9, style="italic", color="#b00020")
    save(fig, "03_data_pipeline.png")


def fig_verification_flowchart():
    fig, ax = canvas(12, 16, "Verification Engine - Decision Flow")
    cx = 60
    box(ax, cx - 14, 148, 28, 6, "Raw message received", "#e8f0fe", "#2f81f7", bold=True)
    checks = [
        ("Valid JSON object\n& required fields?", "FMT-001/002", "INVALID"),
        ("Duplicate\nrecord_id?", "DUP-001", "INVALID", True),
        ("Node & sensor IDs\nregistered?", "NID-001/002", "INVALID"),
        ("Timestamp valid,\nnot future, monotonic?", "TS-001..004", "INVALID"),
        ("Sequence\ncontinuous?", "COM-001", "COMMUNICATION_ERROR"),
        ("Each value present\n& numeric?", "MIS-001 / FMT-005", "SUSPECTED_SENSOR_ERROR"),
        ("Within sensor\noperating range?", "RNG-001", "SUSPECTED_SENSOR_ERROR"),
        ("Rate of change\nwithin limit?", "ROC-001", "ABNORMAL"),
        ("Not stuck /\nconsistent TDS-EC?", "HLT-001 / CON-001", "SUSPECTED_SENSOR_ERROR"),
        ("Inside project\nattention band?", "ABN-001 (if configured)", "ABNORMAL"),
    ]
    y = 136
    arrow(ax, cx, 148, cx, y + 6.3)
    for i, c in enumerate(checks):
        inverted = len(c) == 4
        diamond(ax, cx, y, 34, 11, c[0], fs=8)
        col = C["red"] if c[2] == "INVALID" else (C["amber"] if c[2] == "ABNORMAL" else
                                                   C["purple"] if "COMM" in c[2] else C["orange"])
        box(ax, cx + 24, y - 3, 30, 6, f"{c[2]}\n{c[1]}", "#fff", col, fs=7)
        arrow(ax, cx + 17, y, cx + 23.8, y, col, text="yes" if inverted else "no", fs=7)
        if i < len(checks) - 1:
            arrow(ax, cx, y - 5.5, cx, y - 7.2, text="no" if inverted else "yes", fs=7)
        y -= 12.7
    box(ax, cx - 16, 3, 32, 7, "Aggregate hits -> highest severity\nVALID => VERIFICATION_PASSED", "#e9f7ec", "#3fb950", fs=8, bold=True)
    arrow(ax, cx, y + 12.7 - 5.5, cx, 10.2, text="yes", fs=7)
    box(ax, 2, 50, 22, 28, "Hard-fail rules stop\nearly (INVALID).\n\nSoft rules continue\nso ALL issues are\nreported together.\n\nRaw value is never\noverwritten.", "#fafafa", "#999", fs=7.5)
    save(fig, "04_verification_flowchart.png")


def fig_mode_state_machine():
    fig, ax = canvas(14, 9, "Operating Mode State Machine")
    def node(cx, cy, r, text, col):
        ax.add_patch(Circle((cx, cy), r, fc="white", ec=col, lw=2.5))
        ax.text(cx, cy, text, ha="center", va="center", fontsize=9.5, fontweight="bold", color=col)
    node(30, 55, 13, "MODE 1\nNORMAL\n(~5 min,\nconfigurable)", C["green"])
    node(110, 55, 13, "MODE 2\nLOW-POWER\n/ BURST", C["amber"])
    node(70, 18, 13, "MODE 3\nEMERGENCY\n(high rate)", C["red"])
    node(70, 80, 7, "BOOT /\nSELF-TEST", C["blue"])
    arrow(ax, 64, 76, 40, 64, C["blue"], text="diagnostics OK")
    arrow(ax, 43, 58, 97, 58, C["amber"], text="SoC < LOW_ENTER or\nrenewable < threshold for T", fs=7.5)
    arrow(ax, 97, 51, 43, 51, C["green"], text="SoC > LOW_EXIT (hysteresis)\nand renewable restored", fs=7.5)
    arrow(ax, 36, 43, 60, 27, C["red"], rad=-0.1)
    arrow(ax, 64, 30, 42, 45, C["green"], rad=-0.1)
    arrow(ax, 104, 43, 80, 27, C["red"], rad=0.1)
    arrow(ax, 76, 30, 98, 45, C["amber"], rad=0.1)
    ax.text(22, 30, "configured critical\ncondition", fontsize=7.5, color=C["red"], ha="center")
    ax.text(55, 42, "cleared +\nhold time", fontsize=7.5, color=C["green"], ha="center")
    ax.text(118, 30, "critical condition\n(overrides low-power*)", fontsize=7.5, color=C["red"], ha="center")
    ax.text(85, 42, "cleared,\nSoC still low", fontsize=7.5, color=C["amber"], ha="center")
    ax.text(70, 2, "* Emergency may be rate-capped when SoC < CRITICAL to protect P1 loads (configurable)",
            ha="center", fontsize=8, style="italic")
    box(ax, 116, 72, 22, 14, "LOW-POWER CYCLE\nSLEEP -> WAKE ->\nCOLLECT -> PROCESS\n-> STORE -> BURST\n-> SLEEP", "#fff8e1", C["amber"], fs=7.5)
    save(fig, "05_mode_state_machine.png")


def fig_deployment_workflow():
    fig, ax = canvas(16, 7, "Verified Sensor Deployment Workflow (12 gates)")
    steps = ["Install\nsensor", "Verify\nconnection", "Calibrate /\nverify", "Baseline\nreading",
             "Verify\ncomms", "Antenna /\nnetwork", "Verify\ntimestamp", "Pi\nreception",
             "Data\nstorage", "Firebase\nsync", "System\ndiagnostic", "READY FOR\nDEPLOYMENT"]
    for i, s in enumerate(steps):
        row, col = divmod(i, 6)
        x = 6 + col * 25 if row == 0 else 6 + (5 - col) * 25
        y = 40 if row == 0 else 12
        final = i == 11
        box(ax, x, y, 19, 13, f"{i+1}\n{s}", "#e9f7ec" if final else "#fff",
            C["green"] if final else C["blue"], fs=8.5, bold=final)
        if i < 11:
            if i == 5:
                arrow(ax, x + 9.5, y - 0.2, x + 9.5, 25.3, C["blue"])
            elif row == 0:
                arrow(ax, x + 19.2, y + 6.5, x + 24.8, y + 6.5, C["blue"])
            else:
                arrow(ax, x - 0.2, y + 6.5, x - 5.8, y + 6.5, C["blue"])
    ax.text(80, 62, "Each gate: PASS -> next  |  FAIL -> fix & repeat gate (logged as deployment event)",
            ha="center", fontsize=9, style="italic")
    ax.text(80, 4, "Only after all 12 gates PASS does the node state change to  DEPLOYED / VERIFIED",
            ha="center", fontsize=10, fontweight="bold", color=C["green"])
    save(fig, "06_deployment_workflow.png")


def fig_offline_sync_sequence():
    fig, ax = canvas(14, 10, "Offline-First Synchronisation - Sequence")
    lanes = [("ESP32", 15), ("Pi Receiver", 45), ("Local DB\n(SQLite)", 75), ("Sync Engine", 105), ("Firebase", 130)]
    for name, x in lanes:
        box(ax, x - 9, 88, 18, 7, name, "#f2f7ff", C["blue"], fs=8.5, bold=True)
        ax.plot([x, x], [4, 88], color="#aaa", ls="--", lw=1)
    msgs = [(15, 45, 82, "raw frame #n", C["green"]), (45, 75, 77, "INSERT raw + result", C["blue"]),
            (75, 75, 72, "outbox(state=PENDING)", C["blue"]), (105, 130, 66, "upsert (network DOWN)", C["red"]),
            (130, 105, 62, "timeout / error", C["red"]), (105, 105, 57, "backoff 2^k s (+jitter)", C["amber"]),
            (15, 45, 52, "raw frames #n+1..#n+k", C["green"]), (45, 75, 48, "INSERT (queue grows)", C["blue"]),
            (105, 130, 40, "network UP: batch upsert\ndoc id = record_id", C["green"]),
            (130, 105, 34, "200 OK / already exists", C["green"]),
            (105, 75, 29, "mark SYNCED (ack)", C["blue"]),
            (105, 130, 22, "retry of same batch", C["amber"]),
            (130, 105, 17, "no-op (idempotent)", C["mute"])]
    for x1, x2, y, t, c in msgs:
        if x1 == x2:
            ax.annotate("", xy=(x1 + 0.3, y - 2.5), xytext=(x1 + 0.3, y + 0.5),
                        arrowprops=dict(arrowstyle="-|>", color=c, connectionstyle="arc3,rad=-1.6"))
            ax.text(x1 + 4, y - 1, t, fontsize=7.5, color=c)
        else:
            arrow(ax, x1, y, x2, y, c, text=t, fs=7.5)
    ax.add_patch(Rectangle((2, 44), 136, 26, fc=C["red"], alpha=0.05))
    ax.text(3, 68, "OUTAGE WINDOW", fontsize=8, color=C["red"], fontweight="bold")
    ax.text(70, 7, "Duplicates are impossible by construction: the Firestore document ID IS the record_id.",
            ha="center", fontsize=8.5, style="italic")
    save(fig, "07_offline_sync_sequence.png")


def fig_repo_map():
    fig, ax = canvas(14, 8, "Repository Map (8 repositories)")
    box(ax, 52, 60, 36, 12, "smart-water-main\narchitecture | docs | links", "#fff", "#111", bold=True)
    repos = [("smart-water-esp32", "firmware (C++/PlatformIO)", C["green"]),
             ("smart-water-raspberry-pi", "edge services (Python)", C["blue"]),
             ("smart-water-firebase", "rules | indexes | functions", C["purple"]),
             ("smart-water-dashboard", "engineer UI (web)", C["purple"]),
             ("smart-water-debugger", "service tool (web)", C["orange"]),
             ("smart-water-power", "power mgmt + models", C["amber"]),
             ("smart-water-testing", "HIL | integration | e2e", C["red"])]
    xs = np.linspace(4, 118, len(repos))
    for (n, d, c), x in zip(repos, xs):
        box(ax, x, 22, 17, 14, f"{n.replace('smart-water-', 'sw-')}\n\n{d}", "#fff", c, fs=7.5, bold=False)
        arrow(ax, 70, 59.8, x + 8.5, 36.2, c, lw=1.1)
    ax.text(70, 12, "Shared contract: schema/raw-reading.v1.json (owned by smart-water-main, vendored by version tag)",
            ha="center", fontsize=9, style="italic")
    save(fig, "08_repository_map.png")


def _stream_results():
    msgs = water_stream()
    eng = VerificationEngine()
    res = []
    for m in msgs:
        ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        res.append(eng.verify(m, ts + timedelta(seconds=3)))
    return msgs, res


def fig_sensor_timeseries():
    msgs, res = _stream_results()
    t = [datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) for m in msgs]
    params = [("ph", "pH", C["blue"]), ("turbidity_ntu", "Turbidity (NTU)", C["orange"]),
              ("tds_ppm", "TDS (ppm)", C["green"]), ("ec_us_cm", "EC (uS/cm)", C["purple"]),
              ("temperature_c", "Temperature (C)", C["red"])]
    fig, axes = plt.subplots(5, 1, figsize=(14, 12), sharex=True)
    for ax, (k, lbl, col) in zip(axes, params):
        v = [m["raw"].get(k) for m in msgs]
        vv = np.array([np.nan if x is None else x for x in v], dtype=float)
        ax.plot(t, vv, color=col, lw=1.2)
        for ti, r, x in zip(t, res, vv):
            hit = [h for h in r.rules_triggered if h.parameter in (k, None)]
            if hit:
                mark_y = x if not np.isnan(x) else np.nanmin(vv)
                colr = C["red"] if r.status in (Status.INVALID, Status.SUSPECTED_SENSOR_ERROR) else C["amber"]
                ax.scatter([ti], [mark_y], s=40, color=colr, zorder=5, edgecolor="k", lw=0.5)
                if hit[0].parameter == k:
                    ax.annotate(hit[0].rule_id, (ti, mark_y), textcoords="offset points",
                                xytext=(4, 6), fontsize=7.5)
        ax.set_ylabel(lbl)
        ax.grid(alpha=0.3)
    axes[0].set_title("24 h raw sensor stream with verification flags (red = sensor error / invalid, amber = abnormal)")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    stamp(fig)
    save(fig, "09_sensor_timeseries_flags.png")


def fig_verification_distribution():
    _, res = _stream_results()
    cnt = Counter(r.status.value for r in res)
    rule_cnt = Counter(h.rule_id for r in res for h in r.rules_triggered)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.2))
    order = ["VALID", "ABNORMAL", "SUSPECTED_SENSOR_ERROR", "COMMUNICATION_ERROR", "INVALID"]
    cols = [C["green"], C["amber"], C["orange"], C["purple"], C["red"]]
    vals = [cnt.get(o, 0) for o in order]
    bars = a1.barh(order, vals, color=cols)
    a1.bar_label(bars, padding=3)
    a1.set_title("Record status (288 samples / 24 h)")
    a1.invert_yaxis()
    a1.set_xscale("symlog")
    a1.set_xlabel("records (symlog)")
    rk = sorted(rule_cnt.items(), key=lambda x: -x[1])
    b2 = a2.bar([k for k, _ in rk], [v for _, v in rk], color=C["blue"])
    a2.bar_label(b2)
    a2.set_title("Rule hits by rule ID")
    a2.set_ylabel("hits")
    for a in (a1, a2):
        a.grid(alpha=0.3, axis="x" if a is a1 else "y")
    stamp(fig)
    save(fig, "10_verification_distribution.png")


def _simulate_power():
    p = power_profile()
    t = np.array(p["t"])
    solar = np.array(p["solar"]) * 1.0
    wind = np.array(p["wind"]) * 0.45
    load_nominal = np.array(p["load"])
    soc = np.zeros_like(t)
    mode = []
    source = []
    s = 0.55
    cur_mode = "NORMAL"
    dt = (t[1] - t[0])
    cap = 3.2     # normalised capacity (units of peak-solar-hours); ILLUSTRATIVE
    for i in range(len(t)):
        if cur_mode == "NORMAL" and s < 0.30:
            cur_mode = "LOW_POWER"
        elif cur_mode == "LOW_POWER" and s > 0.45:
            cur_mode = "NORMAL"
        load = load_nominal[i] * (0.35 if cur_mode == "LOW_POWER" else 1.0)
        gen = solar[i] + wind[i]
        s = float(np.clip(s + (gen - load) * dt / cap, 0, 1))
        soc[i] = s
        mode.append(cur_mode)
        if gen >= load:
            src = "SOLAR+WIND" if solar[i] > 0.02 and wind[i] > 0.02 else ("SOLAR" if solar[i] > wind[i] else "WIND")
        else:
            src = "BATTERY" if gen < 0.02 else "RENEWABLE+BATTERY"
        source.append(src)
    return t, solar, wind, load_nominal, soc, mode, source


def fig_hybrid_power():
    t, solar, wind, load, soc, mode, _ = _simulate_power()
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 2]})
    a1.fill_between(t, 0, solar, color=C["yellow"], alpha=0.6, label="Solar (normalised)")
    a1.fill_between(t, solar, solar + wind, color=C["cyan"], alpha=0.6, label="Wind (normalised)")
    a1.plot(t, load, color="k", lw=1, label="Nominal load")
    for d, lbl in enumerate(["Day 1: sunny, low wind", "Day 2: cloudy, windy",
                             "Day 3: rain, intermittent wind", "Day 4: storm, gusts"]):
        a1.axvline(d * 24, color="#999", lw=0.8, ls="--")
        a1.text(d * 24 + 1, 1.25, lbl, fontsize=8.5)
    a1.set_ylim(0, 1.35)
    a1.set_ylabel("power (normalised)")
    a1.legend(loc="center right", fontsize=8)
    a1.set_title("Hybrid generation vs load over a 4-day weather sequence")
    a1.grid(alpha=0.3)
    a2.plot(t, soc * 100, color=C["green"], lw=1.8, label="Battery SoC estimate")
    a2.axhline(30, color=C["amber"], ls="--", lw=1, label="LOW_ENTER (example 30%)")
    a2.axhline(45, color=C["green"], ls=":", lw=1, label="LOW_EXIT (example 45%)")
    a2.axhline(15, color=C["red"], ls="--", lw=1, label="CRITICAL (example 15%)")
    lp = np.array([m == "LOW_POWER" for m in mode])
    a2.fill_between(t, 0, 100, where=lp, color=C["amber"], alpha=0.12, label="LOW-POWER mode active")
    a2.set_ylim(0, 100)
    a2.set_ylabel("SoC %")
    a2.set_xlabel("hours")
    a2.legend(loc="lower left", fontsize=7.5, ncol=3)
    a2.grid(alpha=0.3)
    stamp(fig, SIM_STAMP + " | thresholds are examples, configure per battery")
    save(fig, "11_hybrid_power_4day.png")


def fig_power_source_timeline():
    t, *_, source = _simulate_power()
    cats = ["SOLAR", "WIND", "SOLAR+WIND", "RENEWABLE+BATTERY", "BATTERY"]
    cols = [C["yellow"], C["cyan"], C["green"], C["amber"], C["red"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 4.2), gridspec_kw={"width_ratios": [3, 1]})
    idx = [cats.index(s) for s in source]
    for i in range(len(t) - 1):
        a1.axvspan(t[i], t[i + 1], color=cols[idx[i]], lw=0)
    a1.set_yticks([])
    a1.set_xlabel("hours")
    a1.set_title("Active power source over time")
    for d in range(1, 4):
        a1.axvline(d * 24, color="k", lw=0.8, ls="--")
    c = Counter(source)
    a2.pie([c.get(k, 0) for k in cats], labels=None, colors=cols, autopct=lambda p: f"{p:.0f}%" if p > 2 else "",
           startangle=90, wedgeprops=dict(width=0.45))
    a2.legend(cats, fontsize=7, loc="center left", bbox_to_anchor=(1, 0.5))
    a2.set_title("Share of time")
    stamp(fig)
    save(fig, "12_power_source_timeline.png")


def fig_weather_matrix():
    rows = ["Sunny", "Cloudy", "Continuous rain", "High humidity", "Low solar",
            "Variable wind", "High wind", "Storm"]
    colsl = ["Solar\ncontribution", "Wind\ncontribution", "Battery\nreliance", "Likely\nmode", "Hardware\nrisk"]
    # qualitative levels 0..3 (none/low/med/high); design expectations, not measurements
    data = np.array([
        [3, 1, 1, 0, 1], [1, 2, 2, 0, 0], [0, 1, 3, 1, 2], [2, 1, 1, 0, 2],
        [0, 1, 3, 1, 0], [1, 2, 2, 0, 1], [1, 3, 1, 0, 2], [0, 1, 3, 2, 3]])
    mode_lbl = {0: "NORMAL", 1: "LOW-PWR", 2: "LOW-PWR\n/EMERG."}
    lvl = {0: "none", 1: "low", 2: "med", 3: "high"}
    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.imshow(data, cmap="YlOrRd", vmin=0, vmax=3.5, aspect="auto")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            txt = mode_lbl[data[i, j]] if j == 3 else lvl[data[i, j]]
            ax.text(j, i, txt, ha="center", va="center", fontsize=8.5)
    ax.set_xticks(range(len(colsl)), colsl)
    ax.set_yticks(range(len(rows)), rows)
    ax.set_title("Weather scenario design matrix (qualitative expectations - actual values come from V/I sensors)")
    stamp(fig, "QUALITATIVE DESIGN EXPECTATION - NOT MEASURED")
    save(fig, "13_weather_scenario_matrix.png")


def fig_mode_energy():
    # Relative duty-cycle model. Units deliberately normalised.
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5))
    modes = ["NORMAL\n(5 min)", "LOW-POWER\n(30 min burst)", "EMERGENCY\n(30 s)"]
    # components: sensing, processing, radio, idle/sleep (relative energy/hour)
    sensing = np.array([12, 2, 120])
    proc = np.array([6, 1, 60])
    radio = np.array([20, 4, 90])
    idle = np.array([30, 3, 30])
    b = np.zeros(3)
    for arr, lbl, c in [(idle, "idle / sleep", C["steel"]), (sensing, "sensing", C["cyan"]),
                        (proc, "processing", C["blue"]), (radio, "radio / uplink", C["purple"])]:
        a1.bar(modes, arr, bottom=b, label=lbl, color=c)
        b += arr
    for i, v in enumerate(b):
        a1.text(i, v + 3, f"{v/b[0]*100:.0f}%\nof NORMAL", ha="center", fontsize=8.5)
    a1.set_ylabel("relative energy per hour (arbitrary units)")
    a1.set_title("Relative energy per mode (model - measure on your hardware)")
    a1.legend(fontsize=8)
    a1.set_ylim(0, b.max() * 1.25)
    # Timeline of a low-power burst cycle
    tt = np.linspace(0, 60, 1200)
    cur = np.full_like(tt, 0.05)
    for start in (0, 30):
        cur[(tt >= start) & (tt < start + 0.6)] = 0.6
        cur[(tt >= start + 0.6) & (tt < start + 0.9)] = 0.9
        cur[(tt >= start + 0.9) & (tt < start + 1.5)] = 1.0
    a2.plot(tt, cur, color=C["amber"], lw=1.4)
    a2.fill_between(tt, 0, cur, color=C["amber"], alpha=0.25)
    for s, lbl in [(0.1, "wake+sense"), (0.65, "process"), (1.0, "burst TX")]:
        a2.annotate(lbl, (s, 1.02), fontsize=7.5, rotation=60)
    a2.text(12, 0.12, "deep sleep", fontsize=9)
    a2.set_ylim(0, 1.3)
    a2.set_xlabel("minutes")
    a2.set_ylabel("relative current")
    a2.set_title("LOW-POWER burst cycle (SLEEP -> WAKE -> COLLECT -> STORE -> BURST)")
    for a in (a1, a2):
        a.grid(alpha=0.3)
    stamp(fig, "ILLUSTRATIVE MODEL - NOT MEASURED")
    save(fig, "14_mode_energy_model.png")


def fig_sync_backlog():
    hours = np.arange(0, 48, 5 / 60)
    online = ~(((hours > 6) & (hours < 19)) | ((hours > 30) & (hours < 33)))
    queue = np.zeros_like(hours)
    q = 0
    drain_rate = 60  # records per 5-min tick when online (batch)
    for i, on in enumerate(online):
        q += 1
        if on:
            q = max(0, q - drain_rate)
        queue[i] = q
    fig, ax = plt.subplots(figsize=(14, 4.5))
    ax.plot(hours, queue, color=C["blue"], lw=1.6, label="Outbox queue depth (records)")
    ax.fill_between(hours, 0, queue.max() * 1.1, where=~online, color=C["red"], alpha=0.08, label="Connectivity down")
    ax.set_xlabel("hours")
    ax.set_ylabel("pending records")
    ax.set_title("Offline queue build-up and drain (no data lost, no duplicates)")
    ax.legend()
    ax.grid(alpha=0.3)
    stamp(fig)
    save(fig, "15_sync_queue_backlog.png")


def fig_load_priority():
    fig, ax = plt.subplots(figsize=(12, 4.8))
    loads = ["P1 ESP32 + sensors", "P1 Local alert", "P2 Raspberry Pi", "P3 Cellular modem", "P4 Purification aux."]
    states = ["NORMAL\n(SoC high)", "LOW-POWER\n(SoC < LOW_ENTER)", "CRITICAL\n(SoC < CRITICAL)", "SHUTDOWN\n(LVD)"]
    grid = np.array([[3, 3, 2, 0], [3, 3, 3, 0], [3, 2, 1, 0], [3, 1, 1, 0], [3, 0, 0, 0]])
    lbl = {3: "ON", 2: "DUTY-CYCLED", 1: "BURST ONLY", 0: "OFF"}
    ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=3, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, lbl[grid[i, j]], ha="center", va="center", fontsize=9, fontweight="bold")
    ax.set_xticks(range(4), states)
    ax.set_yticks(range(5), loads)
    ax.set_title("Configurable load-priority shedding table (default profile)")
    save(fig, "16_load_priority_matrix.png")


def _ui_frame(title, w=16, h=10):
    fig, ax = canvas(w, h, dark=True)
    ax.add_patch(Rectangle((0, h * 10 - 7), w * 10, 7, fc="#0b1117"))
    ax.text(3, h * 10 - 3.5, title, color=C["ink"], fontsize=12, fontweight="bold", va="center")
    return fig, ax


def _tile(ax, x, y, w, h, label, value, unit, state="VALID", col=None):
    col = col or {"VALID": C["green"], "ABNORMAL": C["amber"], "ERROR": C["red"]}[state]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1", fc=C["panel"], ec=col, lw=1.5))
    ax.text(x + 1.5, y + h - 2.2, label, color=C["mute"], fontsize=8.5)
    ax.text(x + 1.5, y + h / 2 - 1.2, value, color=C["ink"], fontsize=17, fontweight="bold", va="center")
    ax.text(x + w - 1.5, y + h / 2 - 1.2, unit, color=C["mute"], fontsize=8.5, ha="right", va="center")
    ax.text(x + 1.5, y + 1.3, "* " + state, color=col, fontsize=7.5, fontweight="bold")


def fig_dashboard_mockup():
    fig, ax = _ui_frame("SMART WATER | Engineer Dashboard      Node SWN-0001  ONLINE  | last msg 00:02:14 ago | mode NORMAL")
    tabs = ["LIVE", "NODES", "POWER", "ALERTS (2)", "HISTORY"]
    for i, t in enumerate(tabs):
        ax.add_patch(Rectangle((3 + i * 20, 84), 18, 5, fc=C["blue"] if i == 0 else C["panel"], ec=C["grid"]))
        ax.text(12 + i * 20, 86.5, t, color=C["ink"], ha="center", va="center", fontsize=8.5, fontweight="bold")
    tiles = [("pH", "7.21", "pH", "VALID"), ("Turbidity", "4.8", "NTU", "VALID"), ("TDS", "212", "ppm", "VALID"),
             ("EC", "426", "uS/cm", "VALID"), ("Temperature", "26.4", "C", "ABNORMAL")]
    for i, (l, v, u, s) in enumerate(tiles):
        _tile(ax, 3 + i * 31, 60, 28, 20, l, v, u, s)
    ax.text(3, 55, "Verification: VERIFICATION_PASSED (6 / 7 rules OK, ROC-001 temperature watch)   |   ts 2026-09-23 10:42:05 IST",
            color=C["mute"], fontsize=8.5)
    ax.add_patch(Rectangle((3, 8), 74, 43, fc=C["panel"], ec=C["grid"]))
    ax.text(5, 48, "POWER", color=C["ink"], fontsize=10, fontweight="bold")
    rows = [("Solar", "ACTIVE", C["green"]), ("Wind", "UNAVAILABLE", C["mute"]), ("Battery", "CHARGING | SoC est. 72%", C["green"]),
            ("Source", "SOLAR", C["yellow"]), ("Backup", "READY", C["green"]), ("Low power", "NO", C["green"])]
    for i, (k, v, c) in enumerate(rows):
        ax.text(6, 42 - i * 5.5, k, color=C["mute"], fontsize=9)
        ax.text(30, 42 - i * 5.5, v, color=c, fontsize=9, fontweight="bold")
    ax.add_patch(Rectangle((81, 8), 76, 43, fc=C["panel"], ec=C["grid"]))
    ax.text(83, 48, "ACTIVE ALERTS", color=C["ink"], fontsize=10, fontweight="bold")
    alerts = [("WARN", "Sudden change - temperature (ROC-001)", "10:40", C["amber"]),
              ("INFO", "Maintenance due: pH probe re-calibration", "09:00", C["blue"])]
    for i, (s, m, t, c) in enumerate(alerts):
        y = 40 - i * 10
        ax.add_patch(Rectangle((83, y - 3), 72, 8, fc="#0b1117", ec=c))
        ax.text(85, y + 1, s, color=c, fontsize=8.5, fontweight="bold", va="center")
        ax.text(95, y + 1, m, color=C["ink"], fontsize=8.5, va="center")
        ax.text(140, y + 1, t, color=C["mute"], fontsize=8.5, va="center")
        ax.add_patch(Rectangle((146, y - 1.5), 8, 5, fc=C["blue"]))
        ax.text(150, y + 1, "ACK", color="white", fontsize=7.5, ha="center", va="center")
    ax.text(83, 12, "Raw history is read-only. Corrections are filed as audit events (admin only).",
            color=C["mute"], fontsize=7.5, style="italic")
    stamp(fig, "UI MOCKUP - LAYOUT REFERENCE")
    save(fig, "17_dashboard_mockup.png")


def fig_debugger_mockup():
    fig, ax = _ui_frame("SW-DEBUG  service tool  |  target: SWN-0001 via edge GW-01  |  role: SERVICE_ENGINEER", 16, 11)
    panels = [
        ("SENSORS", [("PH-01", "CONNECTED", "7.21", "VALID"), ("TU-01", "CONNECTED", "4.8", "VALID"),
                     ("TD-01", "CONNECTED", "212", "VALID"), ("EC-01", "CONNECTED", "426", "VALID"),
                     ("TP-01", "NO RESPONSE", "--", "MIS-001")]),
        ("NODE (ESP32)", [("status", "RUNNING", "", ""), ("firmware", "0.4.2+a1b2c3", "", ""),
                          ("heartbeat", "4 s ago", "", ""), ("uptime", "3d 04:11", "", ""), ("reset", "POWERON", "", "")]),
        ("EDGE (Raspberry Pi)", [("cpu", "18 %  52 C", "", ""), ("disk", "23 % used", "", ""),
                                 ("sqlite", "OK  wal", "", ""), ("sw-receiver", "active", "", ""), ("sw-sync", "active", "", "")]),
        ("COMMUNICATION", [("cellular", "REG HOME  CSQ 17", "", ""), ("firebase", "REACHABLE", "", ""),
                           ("last sync", "00:01:10 ago", "", ""), ("queued", "0 records", "", ""), ("seq gaps 24h", "1 (COM-001)", "", "")]),
        ("POWER", [("solar", "18.1 V  0.62 A", "", ""), ("wind", "0.0 V  0.00 A", "", ""),
                   ("battery", "12.9 V  +0.41 A", "", ""), ("load", "3.4 W", "", ""), ("backup", "READY", "", "")]),
        ("VERIFICATION (24 h)", [("passed", "271", "", ""), ("failed", "17", "", ""),
                                 ("top rule", "MIS-001 (4)", "", ""), ("anomaly", "HLT-001 temp", "", ""), ("engine", "v0.1.0", "", "")]),
    ]
    for i, (title, rows) in enumerate(panels):
        col, row = i % 3, i // 3
        x, y = 3 + col * 52, 52 - row * 42
        ax.add_patch(Rectangle((x, y), 49, 38, fc=C["panel"], ec=C["grid"]))
        ax.text(x + 2, y + 35, title, color=C["cyan"], fontsize=9.5, fontweight="bold", family="monospace")
        for j, r in enumerate(rows):
            yy = y + 29 - j * 6
            bad = any(s in (r[1] + r[3]) for s in ("NO RESPONSE", "MIS", "COM-001", "HLT"))
            ax.text(x + 2, yy, r[0], color=C["mute"], fontsize=8.5, family="monospace")
            ax.text(x + 17, yy, r[1], color=C["red"] if bad else C["green"], fontsize=8.5, family="monospace")
            if r[2]:
                ax.text(x + 36, yy, r[2], color=C["ink"], fontsize=8.5, family="monospace")
            if r[3]:
                ax.text(x + 43, yy, r[3], color=C["red"] if bad else C["mute"], fontsize=7.5, family="monospace")
    ax.add_patch(Rectangle((3, 1), 154, 6, fc="#000"))
    ax.text(5, 4, "> diag run --full   [OK] 23  [WARN] 1  [FAIL] 1  | export: diag_SWN-0001_20260923T1042.json",
            color=C["green"], fontsize=8.5, family="monospace", va="center")
    stamp(fig, "UI MOCKUP - LAYOUT REFERENCE")
    save(fig, "18_debugger_mockup.png")


def fig_roadmap():
    phases = ["Repository architecture", "ESP32 sensor acquisition", "ESP32 -> Pi comms", "Pi raw storage",
              "Verification engine", "Offline queue", "Firebase sync", "Dashboard", "Industrial debugger",
              "Solar subsystem", "Wind subsystem", "Hybrid energy mgmt", "Battery backup", "Operating modes",
              "Full integration", "Testing", "Documentation"]
    start = [0, 1, 3, 4, 5, 7, 8, 9, 11, 3, 5, 7, 8, 10, 13, 2, 0]
    dur = [1, 2, 1, 1, 2, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 14, 17]
    groups = ["arch", "fw", "fw", "edge", "edge", "edge", "cloud", "ui", "ui", "pwr", "pwr", "pwr", "pwr", "fw", "int", "qa", "doc"]
    gc = {"arch": C["steel"], "fw": C["green"], "edge": C["blue"], "cloud": C["purple"], "ui": C["orange"],
          "pwr": C["amber"], "int": C["red"], "qa": C["cyan"], "doc": "#777"}
    fig, ax = plt.subplots(figsize=(14, 7.5))
    for i, (p, s, d, g) in enumerate(zip(phases, start, dur, groups)):
        ax.barh(i, d, left=s, color=gc[g], alpha=0.9 if g not in ("qa", "doc") else 0.35, edgecolor="k", lw=0.4)
        ax.text(s + 0.1, i, f"P{i+1}", va="center", fontsize=7.5, color="white" if g not in ("qa", "doc") else "k")
    ax.set_yticks(range(len(phases)), [f"Phase {i+1}: {p}" for i, p in enumerate(phases)])
    ax.invert_yaxis()
    ax.set_xlabel("sprint (2-week units, indicative)")
    ax.set_title("17-phase development plan (testing & documentation run continuously)")
    ax.grid(axis="x", alpha=0.3)
    save(fig, "19_phase_roadmap.png")


def fig_risk_matrix():
    risks = [("Sensor drift / fouling", 4, 3), ("Cellular coverage gaps", 4, 2), ("Battery degradation", 3, 3),
             ("Enclosure water ingress", 2, 4), ("Lightning / surge", 2, 4), ("Theft / vandalism", 3, 4),
             ("SD card corruption", 3, 3), ("Clock drift", 3, 2), ("Firebase quota/cost", 2, 2),
             ("Credential leak", 1, 4), ("Wind over-speed", 2, 3), ("Operator misreads UI", 2, 2)]
    fig, ax = plt.subplots(figsize=(10, 8))
    zz = np.add.outer(np.arange(1, 6), np.arange(1, 6))
    ax.imshow(zz, origin="lower", cmap="RdYlGn_r", extent=(0.5, 5.5, 0.5, 5.5), alpha=0.55)
    rnd = np.random.default_rng(3)
    for n, l, i in risks:
        jx, jy = rnd.uniform(-0.3, 0.3, 2)
        ax.scatter(i + jx, l + jy, s=60, color="k")
        ax.annotate(n, (i + jx, l + jy), xytext=(5, 4), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Impact (1 = minor ... 5 = severe)")
    ax.set_ylabel("Likelihood (1 = rare ... 5 = frequent)")
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_title("Field risk register (qualitative, pre-deployment)")
    save(fig, "20_risk_matrix.png")


def fig_test_matrix():
    suites = {"Sensor": 6, "Communication": 5, "Raspberry Pi": 5, "Power": 9, "Modes": 3, "Security": 4,
              "Verification rules": 17, "Integration / E2E": 8, "Environmental": 4}
    fig, ax = plt.subplots(figsize=(12, 4.8))
    names = list(suites)
    vals = list(suites.values())
    bars = ax.bar(names, vals, color=[C["cyan"], C["purple"], C["blue"], C["amber"], C["green"], C["red"], C["steel"], C["orange"], "#777"])
    ax.bar_label(bars)
    ax.set_ylabel("documented test cases")
    ax.set_title("Test plan coverage by suite (see Section 26)")
    ax.grid(axis="y", alpha=0.3)
    plt.setp(ax.get_xticklabels(), rotation=15)
    save(fig, "21_test_plan_coverage.png")


def fig_enclosure():
    fig, ax = canvas(14, 11, "Field Enclosure Concept (layout reference - no IP rating claimed)")
    ax.add_patch(Rectangle((8, 20), 22, 60, fc="#bbb", ec="#555"))
    ax.text(19, 50, "MAST /\nPOLE", ha="center", fontsize=9, rotation=90)
    ax.add_patch(Polygon([(20, 88), (50, 96), (52, 90), (22, 82)], fc="#2b4a7a", ec="k"))
    ax.text(36, 92, "PV panel (tilt TBD)", color="white", fontsize=7.5, ha="center", rotation=12)
    ax.plot([19, 19], [80, 97], color="k", lw=2)
    for ang in (0, 120, 240):
        a = np.deg2rad(ang)
        ax.plot([19, 19 + 7 * np.cos(a)], [97, 97 + 7 * np.sin(a)], color="#39c5cf", lw=3)
    ax.text(28, 99, "small wind turbine\n(furling/brake)", fontsize=7.5)
    ax.add_patch(FancyBboxPatch((40, 30), 60, 44, boxstyle="round,pad=0.5,rounding_size=2", fc="#eef2f5", ec="#333", lw=2))
    ax.text(70, 76, "MAIN ENCLOSURE (sealed, gasketed lid, UV-stable)", ha="center", fontsize=8.5, fontweight="bold")
    comps = [(43, 58, 16, 12, "ESP32\nnode PCB"), (62, 58, 16, 12, "Raspberry Pi\n+ SSD"), (81, 58, 16, 12, "Modem\n+ SIM"),
             (43, 42, 16, 12, "Charge\nctrl x2"), (62, 42, 16, 12, "Power\nmonitor +\nfuses"), (81, 42, 16, 12, "Terminal\nblocks\n+ TVS"),
             (43, 32, 54, 7, "Separate battery compartment / vented box (chemistry-dependent)")]
    for x, y, w, h, t in comps:
        box(ax, x, y, w, h, t, "#fff", "#56687a", fs=7.5, r=0.6)
    for i, x in enumerate([48, 56, 64, 72, 80]):
        ax.add_patch(Rectangle((x, 26), 3, 4, fc="#444"))
    ax.text(70, 23, "cable glands / waterproof connectors on BOTTOM face only (drip loops)", ha="center", fontsize=8)
    ax.add_patch(Rectangle((104, 60), 3, 18, fc="#333"))
    ax.text(109, 70, "antenna (external,\nsurge arrestor)", fontsize=7.5)
    ax.add_patch(Rectangle((100, 50), 8, 5, fc="#9fd"))
    ax.text(109, 52, "breather vent\n(condensation)", fontsize=7.5)
    ax.add_patch(Rectangle((40, 3), 90, 12, fc="#cde8f7", ec="#39c5cf"))
    ax.text(110, 9, "WATER BODY / TANK", ha="center", fontsize=9, color="#1b7f86")
    for x in (49.5, 57.5, 65.5, 73.5, 81.5):
        ax.plot([x, x], [26, 10], color="#555", lw=1.2)
        ax.add_patch(Rectangle((x - 1.5, 6), 3, 5, fc="#39c5cf", ec="k"))
    ax.text(112, 18, "sensors in perforated\nguard pipe / flow cell\n(serviceable, anti-fouling)", fontsize=7.5)
    ax.text(23, 6, "Earthing rod\n& bonding", fontsize=7.5)
    ax.plot([19, 19], [20, 5], color="#555", lw=3)
    ax.add_patch(Circle((19, 4), 1.5, fc="#7a5"))
    save(fig, "22_enclosure_concept.png")


def fig_alert_escalation():
    fig, ax = canvas(15, 6, "Alert lifecycle & escalation")
    states = [("RAISED", C["red"]), ("LOCAL ALERT\nbuzzer/LED", C["orange"]), ("NOTIFIED\n(cloud)", C["purple"]),
              ("ACKNOWLEDGED", C["amber"]), ("RESOLVED", C["green"]), ("CLOSED\n(audited)", C["steel"])]
    for i, (s, c) in enumerate(states):
        x = 4 + i * 24.5
        box(ax, x, 26, 20, 14, s, "#fff", c, fs=8.5, bold=True)
        if i < len(states) - 1:
            arrow(ax, x + 20.2, 33, x + 24.3, 33, c)
    arrow(ax, 88, 26, 40, 26, C["red"], rad=0.35, text="not ACKed within T_escalate -> re-notify / escalate", fs=7.5)
    ax.text(75, 48, "Every transition writes an immutable alert_event (who, when, previous state, new state)",
            ha="center", fontsize=9, style="italic")
    save(fig, "23_alert_lifecycle.png")


def fig_data_model():
    fig, ax = canvas(16, 9, "Data model - edge SQLite and Firestore collections")
    tables = [
        (3, 44, "raw_readings  (APPEND-ONLY)", ["record_id PK", "node_id", "sensor_ids (json)", "device_ts", "received_ts",
                                                 "seq, boot_id", "ph, turbidity_ntu", "tds_ppm, ec_us_cm", "temperature_c",
                                                 "mode, power_json, comm_json", "raw_sha256", "prev_hash (chain)"], C["blue"]),
        (43, 50, "verification_results", ["result_id PK", "record_id FK", "status", "verification",
                                          "rules_json", "engine_version", "verified_ts"], C["blue"]),
        (43, 8, "events / alerts", ["event_id PK", "node_id", "type, severity", "state", "ack_by, ack_ts", "payload_json"], C["orange"]),
        (83, 50, "audit_log  (APPEND-ONLY)", ["audit_id PK", "actor_uid, role", "action", "target_ref", "previous_value",
                                              "new_value", "reason", "ts", "prev_hash"], C["red"]),
        (83, 8, "power_samples", ["sample_id PK", "node_id, ts", "solar_v/i/p", "wind_v/i/p", "battery_v/i, soc_est",
                                  "load_p, source", "charge_state"], C["amber"]),
        (123, 44, "sync_outbox", ["outbox_id PK", "table, ref_id", "state PENDING/SENT/ACKED", "attempts",
                                   "next_attempt_ts", "last_error"], C["purple"]),
    ]
    for x, y, title, cols, c in tables:
        h = 5 + len(cols) * 3.4
        ax.add_patch(Rectangle((x, y), 34, h, fc="white", ec=c, lw=1.8))
        ax.add_patch(Rectangle((x, y + h - 5), 34, 5, fc=c))
        ax.text(x + 17, y + h - 2.5, title, color="white", ha="center", va="center", fontsize=8, fontweight="bold")
        for i, col in enumerate(cols):
            ax.text(x + 1.5, y + h - 8 - i * 3.4, col, fontsize=7.5, family="monospace")
    arrow(ax, 37.2, 70, 42.8, 66, C["blue"], text="1:1")
    arrow(ax, 37.2, 55, 42.8, 25, C["orange"], text="1:n", rad=0.2)
    arrow(ax, 77.2, 68, 122.8, 66, C["purple"], ls="--", rad=-0.2, text="enqueued")
    ax.text(80, 3, "Firestore mirrors: nodes/{nodeId}, readings/{recordId}, alerts/{alertId}, power/{sampleId}, audit/{auditId}",
            ha="center", fontsize=8.5, style="italic")
    save(fig, "24_data_model.png")


def fig_hash_chain():
    fig, ax = canvas(15, 4.5, "Tamper-evidence: per-node hash chain over raw records")
    for i in range(5):
        x = 4 + i * 29
        box(ax, x, 12, 24, 22, f"record n{'+' + str(i) if i else ''}\n\nraw_sha256 = H(raw)\nprev_hash = H(n-1)\nchain = H(prev || raw)",
            "#fff", C["blue"], fs=7.5)
        if i < 4:
            arrow(ax, x + 24.2, 23, x + 28.8, 23, C["blue"])
    ax.text(75, 5, "Editing any past record breaks every subsequent chain value -> detectable by the debugger's 'verify chain' command.",
            ha="center", fontsize=8.5, style="italic")
    save(fig, "25_hash_chain.png")


def fig_scaling():
    fig, ax = plt.subplots(figsize=(12, 5))
    nodes = np.array([1, 5, 10, 25, 50, 100, 250])
    interval = {"5 min (NORMAL)": 288, "1 min": 1440, "30 s (EMERGENCY)": 2880}
    for (lbl, per_day), c in zip(interval.items(), [C["green"], C["amber"], C["red"]]):
        ax.plot(nodes, nodes * per_day, marker="o", color=c, label=lbl)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("number of field nodes")
    ax.set_ylabel("reading documents / day")
    ax.set_title("Cloud write volume vs fleet size (arithmetic, per sampling interval)")
    ax.grid(which="both", alpha=0.3)
    ax.legend()
    save(fig, "26_scaling_write_volume.png")


def main():
    print("Generating diagrams ->", OUT)
    for f in [fig_system_architecture, fig_power_architecture, fig_data_pipeline, fig_verification_flowchart,
              fig_mode_state_machine, fig_deployment_workflow, fig_offline_sync_sequence, fig_repo_map,
              fig_sensor_timeseries, fig_verification_distribution, fig_hybrid_power, fig_power_source_timeline,
              fig_weather_matrix, fig_mode_energy, fig_sync_backlog, fig_load_priority, fig_dashboard_mockup,
              fig_debugger_mockup, fig_roadmap, fig_risk_matrix, fig_test_matrix, fig_enclosure,
              fig_alert_escalation, fig_data_model, fig_hash_chain, fig_scaling]:
        f()
    print("done.")


if __name__ == "__main__":
    main()
