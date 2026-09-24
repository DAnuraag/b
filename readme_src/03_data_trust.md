---

# PART B: DATA, VERIFICATION AND TRUST

## 10. Raw Data Model: Preserve Everything

### 10.1 Principle

> The system **never** stores only `SAFE / UNSAFE`. It stores the **original reading** and, separately, the **verification result** that refers to it.

### 10.2 Mandatory raw fields

| Field | Type | Required | Source | Example |
|---|---|:-:|---|---|
| `record_id` | string | ✅ | ESP32 | `SWN-0001-00017-00004521` |
| `node_id` | string | ✅ | ESP32 (provisioned) | `SWN-0001` |
| `sensor_ids` | map | ✅ | ESP32 (provisioned) | `{"ph":"PH-01",...}` |
| `timestamp` (device) | ISO-8601 UTC | ✅ | ESP32 RTC | `2026-09-23T05:12:05Z` |
| `received_ts` | ISO-8601 UTC | ✅ | Pi | `2026-09-23T05:12:06.214Z` |
| `raw.ph` | float \| null | ✅ | pH sensor | `7.214` |
| `raw.turbidity_ntu` | float \| null | ✅ | Turbidity sensor | `4.81` |
| `raw.tds_ppm` | float \| null | ✅ | TDS sensor | `212.4` |
| `raw.ec_us_cm` | float \| null | ✅ | EC sensor | `426.1` |
| `raw.temperature_c` | float \| null | ✅ | Temperature sensor | `26.42` |
| `mode` | enum | ✅ | ESP32 | `NORMAL` \| `LOW_POWER` \| `EMERGENCY` |
| `power` | object | ✅ | ESP32 power monitor | battery V, source, W per source |
| `comm` | object | ✅ | ESP32 | link, retries, modem state |
| `verification_status` | enum | ✅ (in result table) | Pi engine | `VALID` … |
| `raw_electrical` | object | recommended | ESP32 | mV values before calibration |
| `cal_version` | map | recommended | ESP32 | calibration record IDs |
| `fw` | string | recommended | ESP32 | `0.4.2+a1b2c3` |
| `raw_sha256` | hex | ✅ | Pi | canonical-JSON SHA-256 |
| `chain_hash` | hex | ✅ | Pi | `H(prev_chain ‖ raw_sha256)` |

**`null` is a first-class value.** A disconnected sensor produces `null`, never `0`, never "the last value", and never an interpolated guess.

### 10.3 Data model overview

<p align="center"><img src="diagrams/24_data_model.png" alt="Data model" width="100%"/></p>

<sub>Figure 10.1: Edge SQLite tables and their Firestore mirrors.</sub>

### 10.4 Edge SQLite schema (DDL)

```sql
-- smart-water-raspberry-pi/database/schema.sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nodes (
    node_id          TEXT PRIMARY KEY,
    location_id      TEXT NOT NULL,
    deployment_state TEXT NOT NULL CHECK (deployment_state IN
                     ('PROVISIONED','COMMISSIONING','READY_FOR_DEPLOYMENT','DEPLOYED_VERIFIED','MAINTENANCE','RETIRED')),
    sensor_ids_json  TEXT NOT NULL,
    fw_version       TEXT,
    registered_ts    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_readings (
    record_id        TEXT PRIMARY KEY,
    node_id          TEXT NOT NULL REFERENCES nodes(node_id),
    boot_id          INTEGER NOT NULL,
    seq              INTEGER NOT NULL,
    sensor_ids_json  TEXT NOT NULL,
    device_ts        TEXT NOT NULL,
    received_ts      TEXT NOT NULL,
    mode             TEXT NOT NULL,
    ph               REAL,
    turbidity_ntu    REAL,
    tds_ppm          REAL,
    ec_us_cm         REAL,
    temperature_c    REAL,
    raw_electrical_json TEXT,
    cal_version_json TEXT,
    power_json       TEXT NOT NULL,
    comm_json        TEXT NOT NULL,
    fw_version       TEXT,
    payload_json     TEXT NOT NULL,        -- full original message, verbatim
    raw_sha256       TEXT NOT NULL,
    prev_chain_hash  TEXT NOT NULL,
    chain_hash       TEXT NOT NULL,
    UNIQUE (node_id, boot_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_raw_node_ts ON raw_readings(node_id, device_ts);

-- Append-only enforcement at the database layer
CREATE TRIGGER IF NOT EXISTS trg_raw_no_update
BEFORE UPDATE ON raw_readings
BEGIN SELECT RAISE(ABORT, 'raw_readings is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trg_raw_no_delete
BEFORE DELETE ON raw_readings
BEGIN SELECT RAISE(ABORT, 'raw_readings is append-only'); END;

CREATE TABLE IF NOT EXISTS verification_results (
    result_id        TEXT PRIMARY KEY,           -- <record_id>#v<engine_version>
    record_id        TEXT NOT NULL,              -- no FK: INVALID frames may lack a raw row
    node_id          TEXT,
    status           TEXT NOT NULL CHECK (status IN
                     ('VALID','INVALID','ABNORMAL','SUSPECTED_SENSOR_ERROR','COMMUNICATION_ERROR')),
    verification     TEXT NOT NULL CHECK (verification IN ('VERIFICATION_PASSED','VERIFICATION_FAILED')),
    rules_json       TEXT NOT NULL,
    raw_snapshot_json TEXT NOT NULL,
    raw_sha256       TEXT NOT NULL,
    engine_version   TEXT NOT NULL,
    config_hash      TEXT NOT NULL,
    verified_ts      TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trg_vr_no_update BEFORE UPDATE ON verification_results
BEGIN SELECT RAISE(ABORT, 'verification_results is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_vr_no_delete BEFORE DELETE ON verification_results
BEGIN SELECT RAISE(ABORT, 'verification_results is append-only'); END;

CREATE TABLE IF NOT EXISTS events (
    event_id     TEXT PRIMARY KEY,
    node_id      TEXT,
    ts           TEXT NOT NULL,
    category     TEXT NOT NULL,     -- SENSOR | COMM | POWER | VERIFICATION | MAINTENANCE | SYSTEM | DEPLOYMENT
    type         TEXT NOT NULL,     -- e.g. SENSOR_DISCONNECTED, BATTERY_LOW
    severity     TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','ALARM','CRITICAL')),
    is_alert     INTEGER NOT NULL DEFAULT 0,
    record_ref   TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS alert_state_log (   -- alert lifecycle, append-only
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT NOT NULL REFERENCES events(event_id),
    prev_state   TEXT,
    new_state    TEXT NOT NULL CHECK (new_state IN ('RAISED','LOCAL_ALERTED','NOTIFIED','ACKNOWLEDGED','RESOLVED','CLOSED')),
    actor        TEXT NOT NULL,
    note         TEXT,
    ts           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS power_samples (
    sample_id    TEXT PRIMARY KEY,
    node_id      TEXT NOT NULL,
    ts           TEXT NOT NULL,
    solar_v REAL, solar_i REAL, solar_p REAL,
    wind_v  REAL, wind_i  REAL, wind_p  REAL,
    battery_v REAL, battery_i REAL, soc_est REAL,
    load_p  REAL,
    source  TEXT NOT NULL,
    charge_state TEXT NOT NULL CHECK (charge_state IN ('CHARGING','DISCHARGING','IDLE','FAULT','UNKNOWN'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id       TEXT PRIMARY KEY,
    ts             TEXT NOT NULL,
    actor_uid      TEXT NOT NULL,
    actor_role     TEXT NOT NULL,
    action         TEXT NOT NULL,
    target_ref     TEXT NOT NULL,
    previous_value TEXT,
    new_value      TEXT,
    reason         TEXT NOT NULL,
    prev_hash      TEXT NOT NULL,
    hash           TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS trg_audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE IF NOT EXISTS sync_outbox (
    outbox_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    collection       TEXT NOT NULL,    -- readings | results | alerts | power | audit | events
    doc_id           TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','SENT','ACKED','DEAD')),
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_ts  TEXT NOT NULL,
    last_error       TEXT,
    created_ts       TEXT NOT NULL,
    UNIQUE (collection, doc_id)
);
CREATE INDEX IF NOT EXISTS ix_outbox_state ON sync_outbox(state, next_attempt_ts);
```

> **Defence in depth.** SQLite triggers stop *accidental* or *application-level* modification. Someone with root access to the Pi could still alter the file, which is why the hash chain (§13.4) and cloud replication exist: tampering becomes **detectable**, even where it can't be made impossible.

### 10.5 Corrections: never edit, always append

If a reading is later found to be wrong, for example because the calibration was applied incorrectly:

```text
raw_readings[SWN-0001-00017-00004521]  ─── unchanged forever
         ▲
         │ target_ref
audit_log[01J8…]  action = "CORRECTION_ANNOTATION"
                  previous_value = {"ph": 7.214, "cal_version": "#3"}
                  new_value      = {"ph_corrected": 7.051, "cal_version": "#4"}
                  reason         = "pH buffer 7.00 was expired; recalibrated 2026-09-24, re-derived from raw_electrical.ph_mv"
                  actor_uid      = "admin:u_8f2…", actor_role = "ADMIN"
```

The dashboard shows the original value and an **"annotated"** badge linking to the audit record. It never silently swaps the number.

---

## 11. Raspberry Pi: Trusted Edge Layer

### 11.1 Responsibilities (15)

| # | Responsibility | Service / module | Output |
|:-:|---|---|---|
| 1 | Receive raw data from the ESP32 | `receiver/serial_receiver.py` | parsed frames |
| 2 | Timestamp incoming data | `receiver/` | `received_ts` |
| 3 | Validate message format | `validator/schema.py` | FMT-* hits |
| 4 | Check sensor identity | `validator/identity.py` | NID-* hits |
| 5 | Check expected data ranges | `validator/rules/range.py` | RNG-001 hits |
| 6 | Detect missing values | `validator/rules/missing.py` | MIS-001 hits |
| 7 | Detect impossible values | `validator/rules/format.py` | FMT-005 hits |
| 8 | Detect sudden abnormal changes | `validator/rules/rate.py` | ROC-001 hits |
| 9 | Run predefined formulas/algorithms | `algorithms/` | temperature compensation, TDS/EC consistency, rolling statistics |
| 10 | Store raw data locally | `storage/raw_store.py` | `raw_readings` |
| 11 | Store verification results | `storage/result_store.py` | `verification_results` |
| 12 | Store diagnostic events | `diagnostics/events.py` | `events` |
| 13 | Queue unsynchronised cloud data | `sync/outbox.py` | `sync_outbox` |
| 14 | Synchronise when connectivity returns | `sync/engine.py` | Firestore docs |
| 15 | Monitor system health | `diagnostics/health.py` | CPU, disk, temperature, service status |

### 11.2 What the Pi does **not** do

- It does **not** decide whether water is safe to drink.
- It does **not** "correct" readings.
- It does **not** infer contaminants from general parameters.
- It does **not** delete records to free space. Instead it archives them to compressed files, with hashes, and raises a storage alert.

### 11.3 Services (systemd)

| Unit | Purpose | Restart policy | Depends on |
|---|---|---|---|
| `sw-receiver.service` | Serial receiver + storage + verification | `always`, 5 s | local FS |
| `sw-sync.service` | Outbox → Firebase | `always`, 10 s | network-online (soft) |
| `sw-health.service` | Health metrics, watchdog, disk checks | `always` | — |
| `sw-api.service` | Local read-only API for the debugger (LAN) | `always` | receiver DB |
| `sw-alert.service` | Local alert fan-out (GPIO buzzer on Pi, optional) | `always` | receiver |

```ini
# smart-water-raspberry-pi/deploy/systemd/sw-receiver.service
[Unit]
Description=Smart Water - serial receiver, raw store and verification engine
After=local-fs.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=swedge
Group=swedge
WorkingDirectory=/opt/smart-water
EnvironmentFile=/etc/smart-water/edge.env
ExecStart=/opt/smart-water/.venv/bin/python -m swedge.receiver
Restart=always
RestartSec=5
WatchdogSec=60
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/smart-water /var/log/smart-water
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 11.4 Edge configuration (example)

```yaml
# smart-water-raspberry-pi/config/edge.example.yaml
edge:
  gateway_id: GW-01
  db_path: /var/lib/smart-water/edge.db
  archive_dir: /var/lib/smart-water/archive
  storage_alert_percent: 80
receiver:
  port: /dev/serial0
  baud: 115200
  max_frame_bytes: 1024
  heartbeat_timeout_s: 900          # > 2× the longest configured sampling interval
verification:
  config_file: /etc/smart-water/verification.yaml
sync:
  enabled: true
  batch_size: 100
  base_delay_s: 2
  max_delay_s: 900
  jitter_s: 3
  stale_after_s: 1800
  dead_after_attempts: 0            # 0 = never mark DEAD automatically
health:
  interval_s: 60
  cpu_temp_warn_c: 70               # TBD / CONFIGURABLE
api:
  bind: 0.0.0.0
  port: 8088
  token_env: SW_DEBUG_API_TOKEN     # value lives in /etc/smart-water/edge.env (never in Git)
```

---

## 12. Data Verification Engine

### 12.1 Contract

```text
            ┌──────────────────────────────┐
RAW SENSOR  │                              │  VERIFICATION RESULT
DATA  ─────►│    VERIFICATION ENGINE       │──────────────────────►  status, verification,
(unchanged) │  (pure function + per-node   │                         rules_triggered[ {rule_id,
            │   short history)             │                         parameter, status, reason} ],
            └──────────────────────────────┘                         verified_at, raw_snapshot,
                                                                     raw_sha256, engine_version
```

**Output fields (required):** verification status · reason · rule triggered · timestamp · original raw value.
**The raw input object is never mutated.** Unit test `test_raw_value_not_modified` enforces this.

### 12.2 Decision flow

<p align="center"><img src="diagrams/04_verification_flowchart.png" alt="Verification flowchart" width="70%"/></p>

<sub>Figure 12.1: Verification decision flow. Hard-fail rules stop early; soft rules all run so that every issue is reported together.</sub>

### 12.3 Classification outputs

| Status | Meaning | Typical cause | Verification |
|---|---|---|---|
| `VALID` | No rule triggered | Normal operation | `VERIFICATION_PASSED` |
| `ABNORMAL` | Data is structurally fine but behaves unusually (sudden change, outside a *configured* attention band) | Real water event **or** sensor event; human follow-up needed | `VERIFICATION_FAILED` |
| `SUSPECTED_SENSOR_ERROR` | Value missing, outside sensor operating range, stuck, or inconsistent with related sensors | Disconnected/fouled/failed sensor | `VERIFICATION_FAILED` |
| `COMMUNICATION_ERROR` | Sequence gap: messages lost | Link noise, buffer overflow, reboot during send | `VERIFICATION_FAILED` |
| `INVALID` | Structurally unusable: malformed, duplicate, unregistered, bad timestamp | Firmware bug, spoofing attempt, clock fault | `VERIFICATION_FAILED` |

**Severity order** used to aggregate several hits into one overall status:
`VALID (0) < ABNORMAL (1) < SUSPECTED_SENSOR_ERROR (2) < COMMUNICATION_ERROR (3) < INVALID (4)`

> The overall status is the most severe hit, but **all** hits are stored in `rules_triggered`, so no information is lost by aggregating.

### 12.4 Verification Rule Catalogue

> Every rule implemented in code must appear here with the same ID. Thresholds are **configuration**, not code.

| Rule ID | Family | Check | Triggers when | Result status | Hard-fail? | Config keys |
|---|---|---|---|---|:-:|---|
| **FMT-001** | Format | Message type | Payload isn't a JSON object | INVALID | ✅ | — |
| **FMT-002** | Format | Required fields | Any of `schema_version, record_id, node_id, sensor_ids, timestamp, seq, mode, raw, power, comm` missing | INVALID | ✅ | — |
| **FMT-003** | Format | Schema version | `schema_version` not supported | INVALID | | `supported_schema_versions` |
| **FMT-004** | Format | Raw block | `raw` isn't an object | INVALID | ✅ | — |
| **FMT-005** | Format | Numeric type | Parameter value is non-numeric, boolean or NaN | INVALID | | — |
| **DUP-001** | Duplicate | Record uniqueness | `record_id` already processed | INVALID | ✅ | — |
| **NID-001** | Node identity | Registered node | `node_id` not in registry (when a registry is configured) | INVALID | | `registered_nodes` |
| **NID-002** | Node identity | Registered sensors | A `sensor_id` isn't registered to this node | INVALID | | `registered_nodes[*].sensor_ids` |
| **TS-001** | Timestamp | Parse | Timestamp missing, malformed or without a timezone | INVALID | | — |
| **TS-002** | Timestamp | Future | Device timestamp > received time + `max_clock_skew_s` | INVALID | | `max_clock_skew_s` |
| **TS-003** | Timestamp | Stale | Device timestamp older than `max_age_s` | INVALID | | `max_age_s` |
| **TS-004** | Timestamp | Monotonic | Timestamp ≤ previous accepted timestamp for this node | INVALID | | — |
| **COM-001** | Communication | Sequence continuity | `seq > last_seq + 1` within the same boot | COMMUNICATION_ERROR | | — |
| **MIS-001** | Missing | Presence | Parameter value is `null`/absent | SUSPECTED_SENSOR_ERROR | | — |
| **RNG-001** | Range | Sensor operating range | Value outside the **sensor's** configured operating range | SUSPECTED_SENSOR_ERROR | | `ranges.<param>` |
| **ROC-001** | Rate of change | Plausible dynamics | `|Δvalue| / Δt(min) > max_rate_per_min.<param>` | ABNORMAL | | `max_rate_per_min.<param>` |
| **HLT-001** | Sensor health | Stuck value | Identical value for `stuck_value_window` consecutive samples | SUSPECTED_SENSOR_ERROR | | `stuck_value_window` |
| **CON-001** | Consistency | TDS ↔ EC | `|TDS − k·EC| / (k·EC) > tds_ec_tolerance` | SUSPECTED_SENSOR_ERROR | | `tds_ec_factor`, `tds_ec_tolerance` |
| **ABN-001** | Attention band | Project band | Value outside a **project-configured** attention band (disabled by default) | ABNORMAL | | `attention_bands.<param>` + `source` |

**Rule families: 11. Rule IDs: 19.** All are implemented in [`reference/edge/verification_engine.py`](reference/edge/verification_engine.py) and covered by [`reference/tests/test_verification_engine.py`](reference/tests/test_verification_engine.py).

### 12.5 Rule rationale

<details>
<summary><b>FMT: Format validation</b></summary>

*Is the message correctly structured?* Malformed frames can come from electrical noise that gets past the CRC (rare), from firmware bugs, or from deliberate injection. They're rejected as `INVALID`, and the **payload is still logged** in the event store for debugging. It isn't written into `raw_readings`, because it can't be trusted as a reading.
</details>

<details>
<summary><b>RNG: Range validation</b></summary>

*Is the value within the configured sensor operating range?* This is **not** a water-safety check. A pH of 15.2 can't come from a working 0–14 pH sensor, so the likely explanation is a sensor or wiring fault. The ranges must come from the **datasheet of the sensor actually installed**.
</details>

<details>
<summary><b>ROC: Rate-of-change validation</b></summary>

*Did the parameter change unrealistically quickly?* Water bodies have physical inertia. A jump of several pH units in 5 minutes is more likely a sensor event (air bubble, probe removed, cable fault) than a real change. It **could** also be a real event, such as a contamination slug. That's why ROC-001 is classified `ABNORMAL` (human follow-up) rather than `INVALID`. Rates are normalised per minute, so the rule works the same way in all three operating modes.
</details>

<details>
<summary><b>HLT: Sensor health</b></summary>

*Is the sensor responding?* A disconnected analog input often floats or rails to a constant value, and a frozen driver repeats the last reading. Readings that are *exactly* identical over N samples are suspicious for noisy analog sensors. N must be tuned per sensor. A digital temperature sensor with 0.0625 °C resolution in a very stable tank may legitimately repeat, so tune `stuck_value_window` for each parameter where needed.
</details>

<details>
<summary><b>CON: Consistency check</b></summary>

*Are related measurements behaving consistently according to predefined rules?* TDS meters usually derive TDS from conductivity using a conversion factor k (often in the range of roughly 0.5–0.7, depending on water composition; **`TBD / CONFIGURABLE`, determine for your site**). If the separate TDS and EC probes disagree beyond a tolerance, at least one of them is probably faulty or fouled.
</details>

<details>
<summary><b>TS: Timestamp validation</b></summary>

*Is the timestamp valid?* Requires timezone-aware ISO-8601, a timestamp not in the future (beyond the skew allowance), not older than the maximum age, and monotonic per node. The ESP32 uses an RTC; the Pi's `received_ts` is always stored as an independent second clock.
</details>

<details>
<summary><b>NID: Node ID validation</b></summary>

*Is the data associated with a registered node?* Nodes and their sensors are provisioned in a registry. Frames from unknown nodes or with swapped sensor IDs are rejected. This catches mis-wired replacements and basic spoofing.
</details>

<details>
<summary><b>COM / DUP: Communication and duplicates</b></summary>

A gap in `seq` means frames were lost; the reading itself may be fine. A repeated `record_id` means a retransmission. It's rejected as a duplicate but **acknowledged**, so the ESP32 stops retrying.
</details>

<details>
<summary><b>ABN: Attention bands (opt-in)</b></summary>

Disabled by default. When enabled, every band **must** carry a `source` field (for example a named standard, a regulator's guidance document, or a documented project decision with its date and approver). The engine refuses to load a band without a source (Phase 5 config validation).
</details>

### 12.6 Verification configuration (example)

```yaml
# /etc/smart-water/verification.yaml   (version-controlled as verification.example.yaml)
engine_version: 0.1.0
supported_schema_versions: [1]
ranges:                     # SENSOR OPERATING RANGES from datasheets — NOT safety limits
  ph:            [0.0, 14.0]
  turbidity_ntu: [0.0, TBD]
  tds_ppm:       [0.0, TBD]
  ec_us_cm:      [0.0, TBD]
  temperature_c: [TBD, TBD]
max_rate_per_min:           # TBD / CONFIGURABLE — tune from baseline data
  ph: 0.5
  turbidity_ntu: 200
  tds_ppm: 100
  ec_us_cm: 200
  temperature_c: 2.0
stuck_value_window: 6
tds_ec_factor: TBD          # determine per site
tds_ec_tolerance: 0.35
max_clock_skew_s: 300
max_age_s: 604800
attention_bands:            # DISABLED unless a verified source is supplied
  ph:            { enabled: false, low: null, high: null, source: null }
  turbidity_ntu: { enabled: false, low: null, high: null, source: null }
  tds_ppm:       { enabled: false, low: null, high: null, source: null }
  ec_us_cm:      { enabled: false, low: null, high: null, source: null }
  temperature_c: { enabled: false, low: null, high: null, source: null }
```

### 12.7 Engine behaviour on a simulated stream

The reference engine was run over a **simulated** 24-hour stream (288 samples at 5-minute intervals), with six injected faults:

| Injected at sample | Fault | Expected rule |
|:-:|---|---|
| 60 | pH jumps to 9.9 | ROC-001 |
| 120–123 | Turbidity sensor returns `null` | MIS-001 |
| 150 | TDS = 1450 (outside the 0–1000 placeholder range) | RNG-001 |
| 200 | 3 frames lost (seq jumps) | COM-001 |
| 230–237 | Temperature frozen at 25.00 | HLT-001 |
| 260 | TDS multiplied by 1.9 | CON-001 |

<p align="center"><img src="diagrams/09_sensor_timeseries_flags.png" alt="Sensor time series with flags" width="100%"/></p>

<sub>Figure 12.2: SIMULATED raw stream. Markers show records where the engine raised a rule hit.</sub>

<p align="center"><img src="diagrams/10_verification_distribution.png" alt="Verification distribution" width="100%"/></p>

<sub>Figure 12.3: SIMULATED status distribution and rule-hit counts. Every injected fault was detected by the expected rule (asserted in <code>test_simulated_stream_triggers_expected_rules</code>).</sub>

> Note how one physical event can trigger several rules. The pH jump at sample 60 raises ROC-001 both on the way up and on the way back down. The CON-001 injection also raises ROC-001 for TDS. That's intended: the engine reports every rule a record breaks, and the engineer sees the full picture.

### 12.8 Reference implementation (excerpt)

The full file is [`reference/edge/verification_engine.py`](reference/edge/verification_engine.py). Key excerpt:

```python
class VerificationEngine:
    """Stateful per-node verification engine (keeps short history per node)."""

    def verify(self, msg, received_at=None) -> VerificationResult:
        received_at = received_at or datetime.now(timezone.utc)
        hits: List[RuleHit] = []

        # FMT: format validation
        if not isinstance(msg, dict):
            return self._result(None, None, [RuleHit("FMT-001", None, Status.INVALID,
                                "Message is not a JSON object")], {}, received_at)
        missing = [f for f in REQUIRED_FIELDS if f not in msg]
        if missing:
            hits.append(RuleHit("FMT-002", None, Status.INVALID,
                                f"Missing required fields: {', '.join(missing)}"))
            return self._result(msg.get("record_id"), msg.get("node_id"), hits, msg, received_at)
        ...
        # RNG: sensor operating range (NOT a water-safety limit)
        lo, hi = self.cfg["ranges"][p]
        if v < lo or v > hi:
            hits.append(RuleHit("RNG-001", p, Status.SUSPECTED_SENSOR_ERROR,
                                f"{p}={v} outside sensor operating range [{lo}, {hi}]"))
        ...
        # ROC: rate of change, normalised per minute
        rate = abs(v - pv) / minutes
        if rate > self.cfg["max_rate_per_min"][p]:
            hits.append(RuleHit("ROC-001", p, Status.ABNORMAL, ...))
        ...
        return self._result(msg["record_id"], msg["node_id"], hits, msg, received_at)
```

### 12.9 Example result

```json
{
  "record_id": "SWN-0001-00001-00000061",
  "node_id": "SWN-0001",
  "verified_at": "2026-09-01T05:00:03+00:00",
  "status": "ABNORMAL",
  "verification": "VERIFICATION_FAILED",
  "rules_triggered": [
    { "rule_id": "ROC-001", "parameter": "ph", "status": "ABNORMAL",
      "reason": "ph changed 0.54/min (limit 0.5)" }
  ],
  "raw_snapshot": { "ph": 9.9, "turbidity_ntu": 5.12, "tds_ppm": 214.6,
                    "ec_us_cm": 431.0, "temperature_c": 26.83 },
  "raw_sha256": "3f1c…e9a0",
  "engine_version": "0.1.0"
}
```

### 12.10 Engine versioning & re-verification

- Every result stores `engine_version` and `config_hash`.
- When the rules or thresholds change, historical records **may be re-verified**. This creates **new** result rows (`<record_id>#v0.2.0`); the old results stay.
- The dashboard shows the result from the **currently active** engine version by default, and the history view can show all versions.

---

## 13. Data Integrity & Tamper Resistance

### 13.1 Permissions by role

| Action | ENGINEER (on-site) | SERVICE (debugger) | SUPERVISOR | ADMIN | DEVICE (edge) |
|---|:-:|:-:|:-:|:-:|:-:|
| View live data, alerts, diagnostics, history | ✅ | ✅ | ✅ | ✅ | — |
| Acknowledge alerts | ✅ | ✅ | ✅ | ✅ | — |
| Log approved maintenance action | ✅ | ✅ | ✅ | ✅ | — |
| Run diagnostic commands | ❌ | ✅ | ❌ | ✅ | — |
| Start calibration session | ❌ | ✅ | ❌ | ✅ | — |
| Change configuration (thresholds, intervals) | ❌ | ❌ | ❌ | ✅ (audited) | — |
| File correction annotation (audit event) | ❌ | ❌ | ❌ | ✅ (audited, reason required) | — |
| Create raw readings | ❌ | ❌ | ❌ | ❌ | ✅ (create only) |
| **Modify historical raw readings** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Delete readings** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Rewrite timestamps** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Change verification results manually** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Alter audit records** | ❌ | ❌ | ❌ | ❌ | ❌ |

> Not even ADMIN can edit raw data. The only path is an **annotation** in the audit log.

### 13.2 Enforcement layers

| Layer | Mechanism |
|---|---|
| UI | Edit/delete controls don't exist for raw, results or audit |
| Firebase Auth | Custom claims `role ∈ {engineer, service, supervisor, admin}` |
| Firestore Security Rules | `allow update, delete: if false` on `readings`, `results`, `audit`; create only by the device service account (Admin SDK) or by a Cloud Function |
| Cloud Functions | Audit entries written server-side; the client can't forge `actor_uid` or `ts` |
| Edge SQLite | Append-only triggers |
| Edge OS | Services run as unprivileged `swedge`; DB file owned by `swedge`, mode `0640` |
| Cryptographic | Per-node hash chain on raw records; per-gateway hash chain on the audit log |

### 13.3 Audit event schema

| Field | Description |
|---|---|
| `audit_id` | UUIDv7 |
| `ts` | Server timestamp (cloud) or edge UTC timestamp |
| `actor_uid` | Authenticated user ID (never free text) |
| `actor_role` | Role at the time of the action |
| `action` | e.g. `ALERT_ACK`, `CONFIG_CHANGE`, `CORRECTION_ANNOTATION`, `CALIBRATION_APPLIED`, `NODE_STATE_CHANGE`, `MAINTENANCE_LOGGED`, `LOGIN_FAILED` |
| `target_ref` | Path or ID of the affected object |
| `previous_value` | JSON snapshot before |
| `new_value` | JSON snapshot after |
| `reason` | Required, free text (minimum length enforced) |
| `prev_hash`, `hash` | Chain values |

### 13.4 Hash chain

<p align="center"><img src="diagrams/25_hash_chain.png" alt="Hash chain" width="100%"/></p>

<sub>Figure 13.1: Tamper evidence via a per-node hash chain.</sub>

```python
# swedge/storage/chain.py
import hashlib, json

GENESIS = "0" * 64

def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def raw_hash(message: dict) -> str:
    return hashlib.sha256(canonical(message)).hexdigest()

def chain_hash(prev_chain: str, raw_sha256: str) -> str:
    return hashlib.sha256(bytes.fromhex(prev_chain) + bytes.fromhex(raw_sha256)).hexdigest()

def verify_chain(rows) -> tuple[bool, str | None]:
    """rows ordered by (boot_id, seq). Returns (ok, first_bad_record_id)."""
    prev = GENESIS
    for r in rows:
        if raw_hash(json.loads(r["payload_json"])) != r["raw_sha256"]:
            return False, r["record_id"]
        if r["prev_chain_hash"] != prev or chain_hash(prev, r["raw_sha256"]) != r["chain_hash"]:
            return False, r["record_id"]
        prev = r["chain_hash"]
    return True, None
```

The debugger's **`verify chain`** command runs `verify_chain()` over a node's history and reports the first broken link, if there is one. Periodically publishing the latest chain head to Firestore (`nodes/{id}.chain_head`) anchors the local chain to a second location.

> **Honest limitation.** A hash chain makes tampering *detectable*; it doesn't make it *impossible*. An attacker with full control of both the edge device and the cloud project could rebuild a consistent chain. Anchoring chain heads to an independent store is a future option ([§50](#50-future-scalability)).

---

## 14. Operating Modes

### 14.1 State machine

<p align="center"><img src="diagrams/05_mode_state_machine.png" alt="Mode state machine" width="90%"/></p>

<sub>Figure 14.1: Operating mode state machine with hysteresis.</sub>

### 14.2 Mode summary

| Property | MODE 1: NORMAL | MODE 2: LOW-POWER / BURST | MODE 3: EMERGENCY |
|---|---|---|---|
| Trigger | Default after self-test; power healthy | SoC < `LOW_ENTER` **or** renewable input < threshold for `T_low` | Configured critical condition (see 14.5) |
| Sampling interval | ~5 min (`normal.interval_s = 300`) | `low_power.interval_s` (e.g. 1800) | `emergency.interval_s` (e.g. 30) |
| ESP32 between samples | Light sleep | **Deep sleep** | Awake |
| Raspberry Pi | ON | Duty-cycled or OFF (P2 shed), per profile | ON (unless SoC < CRITICAL) |
| Modem | On-demand | Burst only (batched uplink) | ON / high priority |
| Local alert | On events | On events | **Active pattern** |
| Uplink | When connectivity is available | Batched burst | Immediate attempt, then queued |
| Exit | → LOW-POWER on low energy; → EMERGENCY on critical condition | → NORMAL when SoC > `LOW_EXIT` **and** renewable restored | → previous mode after condition clears + `hold_time_s` |

### 14.3 Mode 2 cycle

```text
      ┌─────────┐
      │  SLEEP  │◄──────────────────────────────────────────────┐
      └────┬────┘                                               │
           │ RTC timer / external wake (e.g. door, float switch)│
           ▼                                                    │
      ┌─────────┐   sensor excitation ON, settle                │
      │  WAKE   │                                               │
      └────┬────┘                                               │
           ▼                                                    │
      ┌──────────────┐  median of N samples per parameter       │
      │ COLLECT DATA │                                          │
      └────┬─────────┘                                          │
           ▼                                                    │
      ┌──────────────────┐  on-node sanity (range/null flags),  │
      │ LOCAL PROCESSING │  emergency trigger evaluation        │
      └────┬─────────────┘                                      │
           ▼                                                    │
      ┌─────────┐  append to RTC-RAM / flash ring buffer        │
      │  STORE  │                                               │
      └────┬────┘                                               │
           ▼                                                    │
      ┌────────────────────┐  every Kth wake (or when buffer ≥  │
      │ TRANSMIT / BURST   │  threshold): power Pi/modem, send  │
      └────┬───────────────┘  buffered frames, await ACKs       │
           └────────────────────────────────────────────────────┘
```

<p align="center"><img src="diagrams/14_mode_energy_model.png" alt="Mode energy model" width="100%"/></p>

<sub>Figure 14.2: ILLUSTRATIVE relative energy per mode, and the shape of a low-power burst cycle. Real values must be measured on the built hardware (Phase 14).</sub>

### 14.4 Mode configuration (example)

```yaml
# smart-water-esp32/config/modes.example.yaml
normal:
  interval_s: 300                 # ≈ 5 min target, configurable
low_power:
  interval_s: 1800
  burst_every_n_wakes: 4
  burst_when_buffer_ge: 16
  pi_policy: duty_cycle           # on | duty_cycle | off
  enter:
    soc_below_pct: TBD            # LOW_ENTER, battery-chemistry dependent
    renewable_below_w: TBD
    for_s: 900
  exit:
    soc_above_pct: TBD            # LOW_EXIT > LOW_ENTER (hysteresis)
    renewable_above_w: TBD
    for_s: 1800
emergency:
  interval_s: 30
  hold_time_s: 1800               # stay in EMERGENCY at least this long after the trigger clears
  max_duration_s: 21600           # re-evaluate / notify after 6 h
  soc_floor_pct: TBD              # below this, emergency is rate-capped to protect P1 loads
  triggers:                       # ALL thresholds must be configured by the project; none are defaulted
    - { type: rule_hit, rule_id: ABN-001, parameter: any, consecutive: 2 }
    - { type: rule_hit, rule_id: ROC-001, parameter: any, consecutive: 2 }
    - { type: external_input, name: float_switch_high, enabled: false }
    - { type: remote_command, enabled: true }   # supervisor/admin, audited
```

### 14.5 Emergency mode: design constraints

1. **Local-first.** The ESP32 (and Pi, if powered) evaluate triggers locally. The cloud isn't needed to enter or run emergency mode.
2. **No arbitrary "toxic" thresholds.** Emergency triggers use rule hits (e.g. ABN-001), whose bands must be sourced, or explicit external inputs and commands.
3. **Priority order:** 1) rapid sensing → 2) local processing → 3) local alert → 4) data storage → 5) remote transmission when available.
4. **Energy guard.** If SoC < `emergency.soc_floor_pct`, the sampling rate is capped so that P1 loads can keep running. This is itself logged as an event.
5. **Auditability.** Entering and leaving emergency mode are `SYSTEM` events with the triggering rule/record reference.

### 14.6 Mode-selection logic (ESP32, C++)

```cpp
// smart-water-esp32/modes/ModeManager.cpp
#include "ModeManager.h"

Mode ModeManager::evaluate(const PowerStatus& p, const TriggerState& t, uint32_t nowS) {
  // 1) Emergency has priority, but is rate-capped under critical SoC
  if (t.emergencyActive) {
    lastEmergencyS_ = nowS;
    return Mode::EMERGENCY;
  }
  if (current_ == Mode::EMERGENCY && (nowS - lastEmergencyS_) < cfg_.emergency.holdTimeS) {
    return Mode::EMERGENCY;                         // hold time not elapsed
  }

  // 2) Low-power entry/exit with hysteresis and dwell time
  const bool lowEnergy  = p.socPct < cfg_.lowPower.enterSocPct ||
                          p.renewableW < cfg_.lowPower.enterRenewableW;
  const bool recovered  = p.socPct > cfg_.lowPower.exitSocPct &&
                          p.renewableW > cfg_.lowPower.exitRenewableW;

  if (lowEnergy)  { if (!lowSinceS_) lowSinceS_ = nowS; } else lowSinceS_ = 0;
  if (recovered)  { if (!okSinceS_)  okSinceS_  = nowS; } else okSinceS_  = 0;

  if (current_ != Mode::LOW_POWER && lowSinceS_ && nowS - lowSinceS_ >= cfg_.lowPower.enterForS)
    return Mode::LOW_POWER;
  if (current_ == Mode::LOW_POWER && !(okSinceS_ && nowS - okSinceS_ >= cfg_.lowPower.exitForS))
    return Mode::LOW_POWER;

  return Mode::NORMAL;
}
```

---

## 15. Offline-First Operation

### 15.1 Failure scenarios

| Scenario | Data path | Data loss? | User-visible |
|---|---|:-:|---|
| Internet unavailable | ESP32 → Pi → **local storage** → outbox (PENDING) | No | "N records queued" |
| Cellular fails | same as above | No | Modem panel shows `NOT REGISTERED` |
| Firebase temporarily unavailable | same as above | No | Sync state `CLOUD_QUEUED` |
| Firebase credentials revoked | same; outbox grows | No | Admin alert, `CLOUD_AUTH_ERROR` |
| Pi down | ESP32 ring buffer → replay on recovery | Only if the ring buffer overflows | Node OFFLINE on cloud dashboard |
| Pi storage full | Archive old rows to compressed files; alert | No (until archive disk full) | Storage alert |

```text
OFFLINE:   ESP32 ──► Raspberry Pi ──► LOCAL STORAGE (raw + result + outbox PENDING)
RECOVERY:  LOCAL STORAGE ──► SYNC ENGINE ──► FIREBASE (idempotent upsert by record_id)
```

### 15.2 Sequence

<p align="center"><img src="diagrams/07_offline_sync_sequence.png" alt="Offline sync sequence" width="100%"/></p>

<sub>Figure 15.1: Offline-first synchronisation sequence, including a retry that produces no duplicate.</sub>

### 15.3 Queue behaviour (simulated)

<p align="center"><img src="diagrams/15_sync_queue_backlog.png" alt="Sync queue backlog" width="100%"/></p>

<sub>Figure 15.2: SIMULATED outbox depth during two outages (13 h and 3 h). The queue drains in batches once connectivity returns.</sub>

### 15.4 Duplicate prevention: three layers

| Layer | Mechanism |
|---|---|
| ESP32 → Pi | `record_id` primary key in `raw_readings`; a replayed frame → `DUP-001` + ACK, no second row |
| Outbox | `UNIQUE(collection, doc_id)`: a record can't be enqueued twice |
| Firestore | Document ID **is** `record_id`; `create()` fails with `ALREADY_EXISTS`, which the sync engine treats as success |

### 15.5 Sync engine (reference implementation)

```python
# smart-water-raspberry-pi/src/sync/engine.py
"""Outbox → Firestore synchroniser. Idempotent, resumable, backoff with jitter."""
from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("swedge.sync")


class CloudUnavailable(Exception):
    """Transient error: network down, timeout, 5xx."""


class CloudAuthError(Exception):
    """Permanent until fixed: credentials rejected."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SyncEngine:
    def __init__(self, db: sqlite3.Connection, cloud, cfg: dict):
        self.db, self.cloud, self.cfg = db, cloud, cfg
        self.db.row_factory = sqlite3.Row

    def _due_batch(self):
        return self.db.execute(
            "SELECT * FROM sync_outbox WHERE state='PENDING' AND next_attempt_ts <= ? "
            "ORDER BY outbox_id LIMIT ?",
            (utcnow().isoformat(), self.cfg["batch_size"]),
        ).fetchall()

    def _backoff(self, attempts: int) -> float:
        d = min(self.cfg["max_delay_s"], self.cfg["base_delay_s"] * (2 ** attempts))
        return d + random.uniform(0, self.cfg["jitter_s"])

    def run_once(self) -> int:
        batch = self._due_batch()
        if not batch:
            return 0
        docs = [(r["collection"], r["doc_id"], json.loads(r["payload_json"])) for r in batch]
        ids = [r["outbox_id"] for r in batch]
        try:
            self.cloud.upsert_many(docs)             # create-if-absent; ALREADY_EXISTS == success
        except CloudAuthError as e:
            log.error("cloud auth error: %s", e)
            self._defer(batch, str(e), fixed_delay=self.cfg["max_delay_s"])
            raise
        except CloudUnavailable as e:
            log.warning("cloud unavailable (%d queued): %s", len(batch), e)
            self._defer(batch, str(e))
            return 0
        with self.db:
            self.db.executemany("UPDATE sync_outbox SET state='ACKED', last_error=NULL WHERE outbox_id=?",
                                [(i,) for i in ids])
        log.info("synced %d docs", len(ids))
        return len(ids)

    def _defer(self, batch, err: str, fixed_delay: float | None = None):
        with self.db:
            for r in batch:
                delay = fixed_delay if fixed_delay is not None else self._backoff(r["attempts"])
                self.db.execute(
                    "UPDATE sync_outbox SET attempts=attempts+1, last_error=?, next_attempt_ts=? "
                    "WHERE outbox_id=?",
                    (err[:500], (utcnow() + timedelta(seconds=delay)).isoformat(), r["outbox_id"]),
                )

    def pending_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM sync_outbox WHERE state='PENDING'").fetchone()[0]

    def loop(self, stop):
        while not stop.is_set():
            try:
                n = self.run_once()
            except CloudAuthError:
                n = 0
            stop.wait(0.5 if n else 5.0)
```

> **Why `sync_outbox` allows UPDATE when the other tables don't:** the outbox is **operational state**, not evidence. It records *delivery progress*. The evidence tables (`raw_readings`, `verification_results`, `audit_log`) stay append-only.

### 15.6 Ordering guarantees

- Records are delivered **at least once** and stored **exactly once** (because the ID is idempotent).
- Delivery order is *approximately* chronological (outbox FIFO). Consumers sort by `device_ts` and never assume arrival order.
- The dashboard shows a **"data delayed"** banner when `now − last_sync > stale_after_s`.

---

## 16. Firebase Cloud Design

### 16.1 Collections

```text
firestore/
├── nodes/{nodeId}
│     location_id, deployment_state, fw_version, last_comm_ts, power_status,
│     sensor_ids{}, chain_head, gateway_id, commissioned_by, commissioned_ts
├── readings/{recordId}                    ← append-only
│     node_id, device_ts, received_ts, raw{}, raw_electrical{}, mode, power{}, comm{},
│     verification{status, verification, rules[], engine_version}, raw_sha256, chain_hash
├── alerts/{alertId}
│     node_id, ts, type, severity, status, ack{by, ts, note}, record_ref
│     └── events/{eventId}                 ← append-only lifecycle
├── power/{sampleId}                       ← append-only
│     node_id, ts, solar{v,i,p,status}, wind{v,i,p,status}, battery{v,i,soc_est,status},
│     load_p, source, charge_state
├── power_events/{eventId}                 ← append-only
│     node_id, ts, type (SOLAR_UNAVAILABLE | WIND_UNAVAILABLE | BATTERY_LOW | ...), detail
├── audit/{auditId}                        ← append-only, written by Cloud Functions only
│     event, actor_uid, actor_role, ts, action, target_ref, previous_state, new_state, reason
├── maintenance/{taskId}
│     node_id, type, due_ts, done_ts, done_by, notes
└── config/{nodeId}                        ← admin-only, every change mirrored into audit
      verification{}, modes{}, power{}
```

### 16.2 Field reference (required minimum)

| Collection | Required fields |
|---|---|
| **NODES** | node ID · location identifier · deployment status · firmware version · last communication · power status |
| **READINGS** | timestamp · raw sensor values · verification result · operating mode · node ID |
| **ALERTS** | alert ID · node ID · timestamp · alert type · severity · status · acknowledgement |
| **POWER** | solar status · wind status · battery status · current power source · charging/discharging · power events |
| **AUDIT** | event · user · timestamp · action · previous state · new state |

### 16.3 Security Rules

```javascript
// smart-water-firebase/firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    function signedIn()      { return request.auth != null; }
    function role()          { return request.auth.token.role; }
    function isEngineer()    { return signedIn() && role() in ['engineer','service','supervisor','admin']; }
    function isAdmin()       { return signedIn() && role() == 'admin'; }
    function onlyChanges(keys) { return request.resource.data.diff(resource.data).affectedKeys().hasOnly(keys); }

    // Devices write through the Admin SDK (service account), which bypasses rules.
    // Therefore NO client may create readings/power/audit.

    match /nodes/{nodeId} {
      allow read: if isEngineer();
      allow write: if false;                       // provisioning via Cloud Function only
    }

    match /readings/{recordId} {
      allow read: if isEngineer();
      allow create, update, delete: if false;      // immutable for all clients
    }

    match /power/{sampleId}        { allow read: if isEngineer(); allow write: if false; }
    match /power_events/{eventId}  { allow read: if isEngineer(); allow write: if false; }

    match /alerts/{alertId} {
      allow read: if isEngineer();
      // Engineers may ONLY acknowledge: set status=ACKNOWLEDGED + ack block, nothing else.
      allow update: if isEngineer()
                    && resource.data.status in ['RAISED','NOTIFIED']
                    && request.resource.data.status == 'ACKNOWLEDGED'
                    && request.resource.data.ack.by == request.auth.uid
                    && request.resource.data.ack.ts == request.time
                    && onlyChanges(['status','ack']);
      allow create, delete: if false;
      match /events/{eventId} { allow read: if isEngineer(); allow write: if false; }
    }

    match /audit/{auditId} {
      allow read: if signedIn() && role() in ['supervisor','admin'];
      allow write: if false;                       // Cloud Functions (Admin SDK) only
    }

    match /maintenance/{taskId} {
      allow read: if isEngineer();
      allow update: if isEngineer()
                    && onlyChanges(['done_ts','done_by','notes'])
                    && request.resource.data.done_by == request.auth.uid;
      allow create, delete: if isAdmin();
    }

    match /config/{nodeId} {
      allow read: if signedIn() && role() in ['service','admin'];
      allow write: if false;                       // via audited Cloud Function `updateConfig`
    }
  }
}
```

### 16.4 Audit trigger (Cloud Function)

```typescript
// smart-water-firebase/functions/src/audit.ts
import { onDocumentUpdated } from "firebase-functions/v2/firestore";
import { getFirestore, FieldValue } from "firebase-admin/firestore";

export const auditAlertAck = onDocumentUpdated("alerts/{alertId}", async (event) => {
  const before = event.data?.before.data();
  const after = event.data?.after.data();
  if (!before || !after || before.status === after.status) return;
  const db = getFirestore();
  await db.collection("audit").add({
    event: "ALERT_STATE_CHANGE",
    action: "ALERT_ACK",
    actor_uid: after.ack?.by ?? "unknown",
    target_ref: `alerts/${event.params.alertId}`,
    previous_state: { status: before.status },
    new_state: { status: after.status, ack: after.ack ?? null },
    reason: after.ack?.note ?? "",
    ts: FieldValue.serverTimestamp(),
  });
});
```

### 16.5 Indexes

```json
{
  "indexes": [
    { "collectionGroup": "readings", "queryScope": "COLLECTION",
      "fields": [ { "fieldPath": "node_id", "order": "ASCENDING" },
                  { "fieldPath": "device_ts", "order": "DESCENDING" } ] },
    { "collectionGroup": "readings", "queryScope": "COLLECTION",
      "fields": [ { "fieldPath": "node_id", "order": "ASCENDING" },
                  { "fieldPath": "verification.status", "order": "ASCENDING" },
                  { "fieldPath": "device_ts", "order": "DESCENDING" } ] },
    { "collectionGroup": "alerts", "queryScope": "COLLECTION",
      "fields": [ { "fieldPath": "status", "order": "ASCENDING" },
                  { "fieldPath": "ts", "order": "DESCENDING" } ] },
    { "collectionGroup": "power", "queryScope": "COLLECTION",
      "fields": [ { "fieldPath": "node_id", "order": "ASCENDING" },
                  { "fieldPath": "ts", "order": "DESCENDING" } ] }
  ],
  "fieldOverrides": []
}
```

### 16.6 Secrets: never in Git

| Secret | Where it lives | Never |
|---|---|---|
| Firebase service-account JSON (edge) | `/etc/smart-water/sa.json`, mode `0600`, owner `swedge`; path in `GOOGLE_APPLICATION_CREDENTIALS` | Committed, emailed, pasted in issues |
| Firebase web config (dashboard) | `.env.local` (`VITE_FIREBASE_*`) | Treated as a secret: it's an identifier, protected by Security Rules and App Check |
| Debug API token | `/etc/smart-water/edge.env` | Hard-coded |
| Modem APN credentials | NVS, provisioned via serial | Committed |
| Wi-Fi credentials (if used) | NVS | Committed |

```bash
# .env.example (committed) — copy to .env (git-ignored) and fill in
GOOGLE_APPLICATION_CREDENTIALS=/etc/smart-water/sa.json
FIREBASE_PROJECT_ID=your-project-id
SW_DEBUG_API_TOKEN=change-me-generate-with-openssl-rand-hex-32
MODEM_APN=
```

```gitignore
# .gitignore (all repos)
.env
.env.*
!.env.example
*.pem
*.key
*.p12
*service-account*.json
sa.json
secrets/
config/*.yaml
!config/*.example.yaml
*.db
*.db-wal
*.db-shm
logs/
.venv/
node_modules/
dist/
build/
.pio/
```

---

## 17. Security

> **Scope statement:** the project applies *reasonable* security practices suited to a prototype heading for a pilot. It does **not** claim military-grade security, formal certification, or resistance to a determined, well-resourced attacker with physical access.

### 17.1 Threat model (STRIDE summary)

| Threat | Example | Mitigation | Residual risk |
|---|---|---|---|
| **S**poofing | Fake node sends readings | Registered node/sensor IDs (NID-*), per-gateway service account, physical link | Physical attacker on the UART can inject frames. Future: signed frames (HMAC with per-node key) |
| **T**ampering | Editing historical readings | Append-only DB triggers, Security Rules, hash chain, audit log | Root on Pi + cloud admin together |
| **R**epudiation | "I never acknowledged that alert" | Auth-bound `ack.by`, server timestamps, audit trail | — |
| **I**nformation disclosure | Leaked keys in GitHub | No secrets in Git, secret scanning, `.gitignore`, key rotation | Human error. Mitigated by pre-commit hooks |
| **D**enial of service | Flooding the edge API; jamming cellular | Rate limiting, LAN-only API, offline-first design | RF jamming can't be prevented, only detected |
| **E**levation of privilege | Engineer modifies config | Custom claims + rules; config via audited function | Compromised admin account → MFA recommended |

### 17.2 Controls checklist

| Control | Implementation | Phase |
|---|---|:-:|
| Authentication | Firebase Auth (email/password + MFA for admin; SSO future) | 7–8 |
| Role-based access | Custom claims `role`; Security Rules; UI hides disallowed actions | 7–9 |
| Secure API keys | Service account on edge only; web config restricted by Rules + App Check | 7 |
| Environment variables | `.env` / `EnvironmentFile=`; `.env.example` committed | 1 |
| No secrets in GitHub | `.gitignore`, `gitleaks` pre-commit hook + CI job | 1 |
| Input validation | Frame CRC, JSON schema, verification engine, UI form validation | 3–5 |
| Unique device IDs | Provisioned `node_id`, `sensor_id`; eFuse MAC recorded at provisioning | 2 |
| Audit logging | Edge `audit_log` + Firestore `audit` via Functions | 4, 7 |
| Secure communication | TLS for all cloud traffic (Firebase SDKs); local API token over LAN (TLS optional, future) | 7, 9 |
| Firmware version tracking | `fw` in every frame; `nodes.fw_version`; build hash in version string | 2 |
| Least privilege on edge | Dedicated `swedge` user; systemd hardening directives | 4 |
| Dependency hygiene | `pip-audit`, `npm audit`, Dependabot | 16 |
| OTA integrity (future) | Signed firmware images, ESP32 secure boot / flash encryption | Future |

### 17.3 Pre-commit secret scanning

```yaml
# .pre-commit-config.yaml (all repositories)
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-added-large-files
      - id: detect-private-key
      - id: end-of-file-fixer
      - id: trailing-whitespace
```

### 17.4 If a secret is leaked

1. **Revoke/rotate immediately** (Firebase console → service accounts → delete key).
2. Treat it as compromised even if the repo is private.
3. Remove it from history (`git filter-repo`) *after* rotation. Rotation matters more than history rewriting.
4. File an internal audit event: what leaked, when, when it was rotated.
5. Review Firestore audit and access logs for misuse during the exposure window.
