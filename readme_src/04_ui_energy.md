---

# PART C: USER INTERFACES

## 18. Industrial Engineer Dashboard

### 18.1 Design goals

| Goal | How |
|---|---|
| Understandable without programming knowledge | Plain words ("Sensor disconnected", not "MIS-001"), with rule IDs shown as small secondary text |
| Minimal cognitive load | Five tabs; five parameter tiles; one status colour per tile |
| No decoration | No animated gauges, no 3-D charts, no auto-rotating carousels |
| Honest about freshness | Every value shows its timestamp; a stale-data banner when sync is late |
| Safe by construction | No edit or delete controls for historical data |
| Works on a rugged tablet in sunlight | High contrast, large touch targets (≥ 44 px), dark and light themes |
| Accessible | Colour is never the only signal: every status also has a text label and an icon |

### 18.2 Layout

<p align="center"><img src="diagrams/17_dashboard_mockup.png" alt="Dashboard mockup" width="100%"/></p>

<sub>Figure 18.1: Dashboard layout reference (Python-generated mock-up; values illustrative).</sub>

### 18.3 Tabs and content

| Tab | Shows | Actions allowed |
|---|---|---|
| **LIVE** | pH · Turbidity · TDS · EC · Temperature · timestamp · node ID · verification status (with plain-language reason) | None (read-only) |
| **NODES** | Online/offline · last communication · sensor health per sensor · firmware version · power state · deployment state | None |
| **POWER** | Solar · Wind · Battery · current power source · charging · backup · low-power flag | None |
| **ALERTS** | Active and recent alerts with severity, time and plain explanation | **Acknowledge** (with optional note) |
| **HISTORY** | Raw readings table · verification status · events · power history · node history · CSV export | Filter, export (read-only) |

### 18.4 Alert catalogue (dashboard)

| Alert type | Plain-language text | Source | Default severity | Suggested engineer action |
|---|---|---|---|---|
| `SENSOR_DISCONNECTED` | "The {sensor} sensor is not responding." | MIS-001 × N consecutive | ALARM | Check connector and cable; run the debugger sensor check |
| `ABNORMAL_READING` | "{param} is outside the configured attention band." | ABN-001 | WARNING | Follow the site procedure; consider a manual sample or screening |
| `SUDDEN_CHANGE` | "{param} changed faster than expected." | ROC-001 | WARNING | Check the probe is immersed and has no air bubble; compare with a manual reading |
| `NODE_OFFLINE` | "No data from node for {duration}." | Heartbeat timeout | ALARM | Check power and link; use the debugger |
| `COMMUNICATION_FAILURE` | "Messages were lost between node and gateway." | COM-001 / link counters | WARNING | Check the cable; look for noise sources |
| `POWER_FAILURE` | "No renewable input and battery supplying all loads." | Power monitor | WARNING | Inspect panel, turbine and controllers |
| `BATTERY_LOW` | "Battery low: system entering low-power mode." | SoC < LOW_ENTER | WARNING | Check charging; plan a visit |
| `BATTERY_CRITICAL` | "Battery critical: non-essential loads switched off." | SoC < CRITICAL | CRITICAL | Urgent site visit |
| `VERIFICATION_FAILURE` | "Recent readings failed data checks ({count} in {window})." | Verification failure rate | WARNING | Open History to see which rules fired |
| `MAINTENANCE_REQUIRED` | "{task} is due." | Maintenance schedule | INFO | Perform the task and log it |

### 18.5 Alert lifecycle

<p align="center"><img src="diagrams/23_alert_lifecycle.png" alt="Alert lifecycle" width="100%"/></p>

<sub>Figure 18.2: Alert lifecycle and escalation. Every transition is an immutable event.</sub>

### 18.6 Technology

| Concern | Choice | Reason |
|---|---|---|
| Framework | React 18 + TypeScript + Vite | Mature, typed, fast build |
| Styling | Plain CSS modules with a small design-token file | No heavy UI kit; predictable rendering on low-end tablets |
| Data | Firebase JS SDK (Firestore `onSnapshot`) | Live updates, offline cache |
| Charts (History only) | One lightweight line chart per parameter | Charts only where they help: history, not live |
| Testing | Vitest + React Testing Library; Playwright for e2e | |
| Hosting | Firebase Hosting (optional) | |

### 18.7 Folder structure

```text
smart-water-dashboard/
├── README.md
├── LICENSE
├── .env.example
├── package.json
├── vite.config.ts
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/        # StatusBadge, ParamTile, StaleBanner, AckButton, DataTable
│   ├── pages/             # LivePage, NodesPage, PowerPage, AlertsPage, HistoryPage, LoginPage
│   ├── services/          # firebase.ts, readings.ts, alerts.ts, power.ts, auth.ts
│   ├── dashboard/         # live layout, tile grid
│   ├── alerts/            # alert list, plain-language map
│   ├── history/           # filters, CSV export
│   ├── power/             # power panel
│   └── styles/tokens.css
└── tests/
    ├── unit/
    └── e2e/
```

### 18.8 Key component: parameter tile

```tsx
// smart-water-dashboard/src/components/ParamTile.tsx
import { StatusBadge } from "./StatusBadge";
import type { VerificationStatus } from "../services/types";

interface Props {
  label: string;             // "pH"
  value: number | null;      // raw value, never modified
  unit: string;              // "NTU"
  status: VerificationStatus;
  reason?: string;           // plain-language reason
  ts: string;                // ISO timestamp of the reading
  annotated?: boolean;       // true if an audit annotation exists
}

export function ParamTile({ label, value, unit, status, reason, ts, annotated }: Props) {
  const display = value === null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return (
    <section className={`tile tile--${status.toLowerCase()}`} aria-label={`${label} reading`}>
      <header className="tile__label">{label}</header>
      <div className="tile__value">
        {display} <span className="tile__unit">{unit}</span>
      </div>
      <StatusBadge status={status} />
      {reason && <p className="tile__reason">{reason}</p>}
      <footer className="tile__ts">
        {new Date(ts).toLocaleString()} {annotated && <span className="tile__annot">annotated</span>}
      </footer>
    </section>
  );
}
```

### 18.9 Plain-language mapping

```ts
// smart-water-dashboard/src/alerts/plainLanguage.ts
export const RULE_TEXT: Record<string, string> = {
  "FMT-001": "Message could not be read",
  "FMT-002": "Message incomplete",
  "FMT-005": "Sensor sent a non-numeric value",
  "DUP-001": "Duplicate message ignored",
  "NID-001": "Unknown device",
  "NID-002": "Unregistered sensor",
  "TS-001":  "Time stamp unreadable",
  "TS-002":  "Device clock ahead of gateway",
  "TS-003":  "Very old message",
  "TS-004":  "Time went backwards",
  "COM-001": "Some messages were lost",
  "MIS-001": "Sensor not responding",
  "RNG-001": "Value outside what the sensor can measure: likely sensor fault",
  "ROC-001": "Changed faster than expected",
  "HLT-001": "Sensor value not changing: possibly stuck",
  "CON-001": "TDS and EC sensors disagree",
  "ABN-001": "Outside configured attention band",
};
```

---

## 19. Industrial Debugger

### 19.1 Purpose

The dashboard answers *"what is the water doing, and do I need to act?"*
The debugger answers *"what exactly is wrong with this installation, and how do I prove it's fixed?"*

It is a **separate application** (web UI plus CLI) for service engineers. It talks to the edge's local API over the LAN or the gateway's service Wi-Fi access point, so it **works on site with no internet**.

### 19.2 Layout

<p align="center"><img src="diagrams/18_debugger_mockup.png" alt="Debugger mockup" width="100%"/></p>

<sub>Figure 19.1: Debugger layout reference (Python-generated mock-up). Monospace, high-density, service-tool aesthetic.</sub>

### 19.3 Panels

| Panel | Fields | Source |
|---|---|---|
| **Sensor diagnostics** | Connected/disconnected · last reading · reading validity · response status · raw mV · calibration version/date · noise (σ over last N) | Latest frames + `raw_electrical` |
| **Node diagnostics** | ESP32 status · firmware version · last heartbeat · communication status · uptime · reset reason · free heap · boot_id · ring-buffer depth | Heartbeat frames |
| **Raspberry Pi** | CPU %, CPU temperature · storage used/free · local database status (integrity check, WAL size) · processing service status (systemd) | `sw-health` |
| **Communication** | Cellular status (registration, CSQ) · Firebase status · last successful sync · queued records · CRC error rate · seq gaps | `sw-sync`, receiver counters |
| **Power** | Solar V/I/W · wind V/I/W · battery V/I/state · load W · backup state · active source · last source switch | Power samples |
| **Data verification** | Passed/failed counts (1 h / 24 h) · rule triggered (histogram) · sensor anomalies · engine version · config hash | `verification_results` |
| **Maintenance** | Calibration due dates · last maintenance · open tasks · chain verification status | `maintenance`, chain check |

### 19.4 CLI

```text
$ swdebug --gateway 192.168.4.1 --token $SW_DEBUG_API_TOKEN

swdebug> status
  node SWN-0001  RUNNING  fw 0.4.2+a1b2c3  mode NORMAL  hb 4s  link LINK_OK
  edge GW-01     cpu 18%  52C  disk 23%  db OK  receiver active  sync active
  cloud          REACHABLE  last sync 70s  queued 0

swdebug> sensors
  ID     STATE        LAST     mV      VALID   CAL           NOISE(σ)
  PH-01  CONNECTED    7.21     1412    VALID   2026-09-01#3  0.004
  TU-01  CONNECTED    4.80     3021    VALID   2026-09-01#1  0.12
  TD-01  CONNECTED    212      611     VALID   2026-09-01#2  1.1
  EC-01  CONNECTED    426      702     VALID   2026-09-01#2  2.3
  TP-01  NO RESPONSE  --       --      MIS-001 n/a           --

swdebug> rules --since 24h
  MIS-001  4   ████
  ROC-001  3   ███
  HLT-001  3   ███
  CON-001  1   █
  RNG-001  1   █
  COM-001  1   █

swdebug> verify-chain SWN-0001
  checked 12,447 records ... OK (head 9c1e…44af)

swdebug> diag run --full
  [OK]   sensor.ph.response        [OK]   edge.disk.free
  [OK]   sensor.tu.response        [OK]   edge.db.integrity
  ...
  [FAIL] sensor.tp.response        -> check 1-Wire cable / pull-up (TSG-S03)
  [WARN] comm.seq_gaps_24h = 1     -> see TSG-C02
  summary: OK 23  WARN 1  FAIL 1
  report: diag_SWN-0001_20260923T1042.json
```

### 19.5 Diagnostic check catalogue

| Check ID | Checks | PASS criterion (configurable) | Troubleshooting ref |
|---|---|---|---|
| `sensor.<x>.response` | Value non-null in the last N frames | ≥ 1 non-null in last 3 | TSG-S01…S05 |
| `sensor.<x>.noise` | σ of the last N readings | < `noise_max.<x>` | TSG-S06 |
| `sensor.<x>.cal_age` | Days since calibration | < `cal_interval_days.<x>` | §43 |
| `node.heartbeat` | Age of the last heartbeat | < `heartbeat_timeout_s` | TSG-N01 |
| `node.fw_match` | Firmware equals the expected release | equal | TSG-N03 |
| `node.reset_reason` | Last reset not brownout/watchdog | not in {BROWNOUT, WDT} | TSG-P04 |
| `edge.disk.free` | Free space | > 20% | TSG-E02 |
| `edge.db.integrity` | `PRAGMA integrity_check` | `ok` | TSG-E03 |
| `edge.services` | systemd units active | all active | TSG-E01 |
| `edge.cpu_temp` | CPU temperature | < `cpu_temp_warn_c` | TSG-E04 |
| `comm.link` | CRC error rate | < 1% | TSG-C01 |
| `comm.seq_gaps_24h` | COM-001 count | 0 | TSG-C02 |
| `comm.cloud` | Last sync age | < `stale_after_s` | TSG-C03 |
| `comm.modem` | Registered, CSQ | registered & CSQ ≥ `csq_min` | TSG-C04 |
| `power.battery` | SoC estimate | > LOW_ENTER | TSG-P01 |
| `power.solar` | Daylight output | > 0 during the configured daylight window | TSG-P02 |
| `power.wind` | Output when the anemometer (optional) reports wind | consistent | TSG-P03 |
| `data.verify_rate` | Failed/total over 24 h | < `verify_fail_max` | TSG-D01 |
| `data.chain` | Hash chain intact | OK | TSG-D02 |

### 19.6 Local API (edge, read-mostly)

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/api/v1/status` | service | Summary of node, edge and cloud |
| GET | `/api/v1/sensors` | service | Per-sensor diagnostics |
| GET | `/api/v1/readings?node=&since=&limit=` | service | Raw readings (read-only) |
| GET | `/api/v1/results?node=&since=` | service | Verification results |
| GET | `/api/v1/power?since=` | service | Power samples |
| GET | `/api/v1/outbox` | service | Queue summary |
| POST | `/api/v1/diag/run` | service | Run the diagnostic suite (no data mutation) |
| POST | `/api/v1/chain/verify` | service | Verify the hash chain |
| POST | `/api/v1/calibration/session` | service | Start a calibration session (audited) |
| POST | `/api/v1/maintenance` | engineer+ | Log a maintenance action (audited) |

There are no endpoints to update or delete readings, results or audit entries.

---

# PART D: ENERGY

## 20. Weather-Resilient Energy Management

### 20.1 Principle

> **Weather describes likely conditions; sensors measure actual energy.** The power controller acts only on measured voltage, current and battery state. Weather labels in this section explain *why* measured values might change. They are never inputs to the control law.

### 20.2 Scenario matrix

<p align="center"><img src="diagrams/13_weather_scenario_matrix.png" alt="Weather scenario matrix" width="85%"/></p>

<sub>Figure 20.1: Qualitative design expectations per weather scenario. These are not measurements.</sub>

| Weather condition | Expected solar | Expected wind | Controller response (based on **measurements**) |
|---|---|---|---|
| **Sunny** + low wind | High (daytime) | Low | Solar supplies load and charges battery; battery covers night |
| **Cloudy** + sufficient wind | Reduced | Moderate–high | Wind contributes; solar partial |
| **Continuous rain** + intermittent wind | Low | Variable | Available renewable + battery; watch SoC trend |
| **High humidity** | Unaffected directly | — | Enclosure condensation risk; no power action (monitor internal RH if fitted) |
| **Low solar availability** (e.g. monsoon week) | Low for days | Variable | Battery reliance grows → LOW-POWER as needed |
| **Variable wind** | — | Fluctuating | Wind controller smooths; battery buffers |
| **High wind** | — | High until cut-out | Controller may brake or divert; generation can drop to zero |
| **Storm-related** | Very low | Gusty / braked | Battery + LOW-POWER; lightning protection matters most; check the site after the storm |

### 20.3 Control law (measurement-driven)

```text
every power_interval_s:
    P_solar  = V_solar  × I_solar          (measured)
    P_wind   = V_wind   × I_wind           (measured)
    P_load   = V_load   × I_load           (measured)
    P_batt   = V_batt   × I_batt           (measured, sign: + charging, − discharging)
    SoC_est  = estimator(V_batt, I_batt, T, history)

    source   = classify(P_solar, P_wind, P_load)      # SOLAR | WIND | SOLAR+WIND | RENEWABLE+BATTERY | BATTERY
    state    = CHARGING if P_batt > +ε else DISCHARGING if P_batt < −ε else IDLE

    if SoC_est < CRITICAL: shed(P2, P3, P4) ; mode ← LOW_POWER ; event(BATTERY_CRITICAL)
    elif SoC_est < LOW_ENTER for T_low: shed(P4) ; mode ← LOW_POWER ; event(BATTERY_LOW)
    elif SoC_est > LOW_EXIT and P_solar+P_wind > P_load for T_ok: restore() ; mode ← NORMAL
    emit power_sample, and events on any transition
```

### 20.4 Source classification

```python
# smart-water-power/src/power/classify.py
from enum import Enum

class Source(str, Enum):
    SOLAR = "SOLAR"
    WIND = "WIND"
    SOLAR_WIND = "SOLAR+WIND"
    RENEWABLE_BATTERY = "RENEWABLE+BATTERY"
    BATTERY = "BATTERY"

def classify(p_solar: float, p_wind: float, p_load: float, eps: float = 0.2) -> Source:
    """eps (W) = measurement noise floor; TBD / CONFIGURABLE from INA calibration."""
    solar_on, wind_on = p_solar > eps, p_wind > eps
    gen = (p_solar if solar_on else 0.0) + (p_wind if wind_on else 0.0)
    if gen <= eps:
        return Source.BATTERY
    if gen < p_load:
        return Source.RENEWABLE_BATTERY
    if solar_on and wind_on:
        return Source.SOLAR_WIND
    return Source.SOLAR if solar_on else Source.WIND
```

### 20.5 Battery state estimation (honest version)

| Method | Accuracy | Complexity | Notes |
|---|---|---|---|
| Voltage look-up table | Low–medium | Low | Depends on load and temperature; LiFePO₄'s flat curve makes it especially poor |
| Coulomb counting | Medium–high short-term | Medium | Drifts; needs periodic re-sync at full charge |
| BMS-reported SoC | Depends on BMS | Low (integration) | Preferred where a BMS with a data interface exists |
| Combined (coulomb + voltage re-sync at rest) | Medium–high | Medium | Recommended target for Phase 13 |

> The dashboard labels battery state as **"SoC estimate"**, never as a precise percentage guarantee.

---

## 21. Power Monitoring

### 21.1 Recorded measurements

| Measurement | Unit | Sensor | Sample interval |
|---|---|---|---|
| Solar voltage | V | Power monitor #1 | `power_interval_s` (default 60 s NORMAL; at wake in LOW-POWER) |
| Solar current | A | Power monitor #1 | same |
| Solar power | W | computed | same |
| Wind voltage | V | Power monitor #2 (after rectifier) | same |
| Wind current | A | Power monitor #2 | same |
| Wind power | W | computed | same |
| Battery voltage | V | Power monitor #3 | same |
| Battery current (±) | A | Power monitor #3 | same |
| Battery state/status | enum + SoC estimate | estimator | same |
| Load power | W | Power monitor #4 | same |
| Charging/discharging state | enum | derived | same |
| Current power source | enum | classifier | same |
| Timestamp | ISO-8601 | RTC | same |

### 21.2 Power events

| Event | Condition (all thresholds configurable) | Severity | Clears when |
|---|---|---|---|
| `SOLAR_UNAVAILABLE` | P_solar < ε for > `T_solar_absent` **inside** the configured daylight window | INFO | P_solar > ε for `T_restore` |
| `WIND_UNAVAILABLE` | P_wind < ε for > `T_wind_absent` | INFO | P_wind > ε for `T_restore` |
| `BATTERY_LOW` | SoC_est < LOW_ENTER | WARNING | SoC_est > LOW_EXIT |
| `BATTERY_CRITICAL` | SoC_est < CRITICAL | CRITICAL | SoC_est > LOW_ENTER |
| `CHARGING_FAILURE` | P_solar+P_wind > P_load + margin **and** I_batt ≤ 0 for > `T_chg_fail` | ALARM | I_batt > 0 |
| `POWER_SOURCE_SWITCH` | `source` classification changes (debounced by `T_switch_debounce`) | INFO | — |
| `RENEWABLE_RESTORED` | Generation > load after a BATTERY period | INFO | — |
| `OVERSPEED_PROTECTION` | Wind controller status input reports brake/dump (if available) | INFO | Status clears |

### 21.3 Power sample payload

```json
{
  "sample_id": "SWN-0001-P-00017-00012094",
  "node_id": "SWN-0001",
  "ts": "2026-09-23T05:12:00Z",
  "solar":   { "v": 18.1, "i": 0.62, "p": 11.2, "status": "ACTIVE" },
  "wind":    { "v": 0.0,  "i": 0.00, "p": 0.0,  "status": "UNAVAILABLE" },
  "battery": { "v": 12.9, "i": 0.41, "soc_est": 72, "status": "CHARGING" },
  "load_p": 3.4,
  "source": "SOLAR",
  "charge_state": "CHARGING"
}
```

### 21.4 Power configuration (example)

```yaml
# smart-water-power/config/power.example.yaml
battery:
  chemistry: TBD
  nominal_v: TBD
  capacity_ah: TBD            # not specified by this project
  soc_method: combined
  thresholds_pct:
    low_enter: TBD            # e.g. chosen after battery datasheet review
    low_exit:  TBD            # must be > low_enter
    critical:  TBD            # must be < low_enter
measurement:
  interval_s: 60
  noise_floor_w: TBD          # ε
daylight_window_local: ["06:00", "18:30"]   # site-dependent
events:
  solar_absent_s: 3600
  wind_absent_s: 21600
  charge_fail_s: 1800
  restore_s: 600
  switch_debounce_s: 120
load_priority:                # lower number = more important
  P1: [esp32_sensors, local_alert]
  P2: [raspberry_pi]
  P3: [cellular_modem]
  P4: [purification_aux]
shed_profile:
  low_power: { P4: off, P3: burst, P2: duty_cycle }
  critical:  { P4: off, P3: burst, P2: off_with_graceful_shutdown }
```

---

## 22. Power Failover & Load Priority

### 22.1 Failover behaviour

```text
Renewable ≥ load              → renewable supplies load, surplus charges battery
Renewable < load              → BATTERY supports the deficit         (event: POWER_SOURCE_SWITCH)
Renewable returns             → resume renewable-supported operation (event: RENEWABLE_RESTORED)
SoC < LOW_ENTER               → LOW-POWER mode, shed P4, P3 → burst, P2 → duty-cycle
SoC < CRITICAL                → shed P2 (graceful Pi shutdown), P3 burst-only; P1 protected
Hardware LVD threshold        → everything off (battery protection, independent of firmware)
```

### 22.2 Load-priority matrix

<p align="center"><img src="diagrams/16_load_priority_matrix.png" alt="Load priority matrix" width="85%"/></p>

<sub>Figure 22.1: Default shedding profile (configurable).</sub>

### 22.3 Graceful Raspberry Pi shutdown

Cutting power to a Pi while it writes to its database can corrupt the SD card. Shedding P2 therefore uses a handshake:

```text
ESP32                                   Raspberry Pi
  │ SHUTDOWN_REQUEST (UART, reason)        │
  │───────────────────────────────────────►│ flush WAL, stop services, sync FS
  │                                        │ `systemctl poweroff`
  │◄─────────────── SHUTDOWN_ACK ──────────│
  │ wait for GPIO "PI_HALTED" or t_max     │
  │ open load switch P2                    │
  │ log POWER event (P2_SHED)              │
```

- `t_max` = `TBD / CONFIGURABLE` (measure the actual shutdown time and add margin).
- While the Pi is off, the ESP32 **ring-buffers** frames and replays them after the Pi is restored.
- The Pi is restored only when SoC > LOW_EXIT, which avoids on/off cycling.

### 22.4 Load manager (ESP32, C++)

```cpp
// smart-water-esp32/power/LoadManager.cpp
#include "LoadManager.h"

void LoadManager::apply(PowerLevel level) {
  switch (level) {
    case PowerLevel::NORMAL:
      setLoad(Load::P4_AUX,   cfg_.auxEnabledInNormal);
      setLoad(Load::P3_MODEM, LoadState::ON_DEMAND);
      requestPi(true);
      break;
    case PowerLevel::LOW:
      setLoad(Load::P4_AUX,   LoadState::OFF);
      setLoad(Load::P3_MODEM, LoadState::BURST);
      cfg_.piPolicyLow == PiPolicy::OFF ? requestPi(false) : dutyCyclePi();
      break;
    case PowerLevel::CRITICAL:
      setLoad(Load::P4_AUX,   LoadState::OFF);
      setLoad(Load::P3_MODEM, LoadState::BURST);
      requestPi(false);                 // graceful shutdown handshake
      break;
  }
  // P1 (ESP32 + sensors + local alert) is never shed by firmware.
  events_.log(EventCategory::POWER, "LOAD_PROFILE_APPLIED", toString(level));
}
```
