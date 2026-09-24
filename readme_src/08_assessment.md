---

# PART G: HONEST ASSESSMENT AND THE ROAD AHEAD

## 47. Prototype vs Future Industrial Capability

> This table is the single source of truth for what the project **is** today and what it **could become**. Anything in the right-hand column is a *target*, not a claim.

| Area | ✅ Prototype functionality (this project) | 🔭 Future industrial deployment capability (requires further work) |
|---|---|---|
| Sensors | Low-cost analog pH/EC/TDS/turbidity + digital temperature; bench calibration | Industrial-grade probes with digital outputs (e.g. RS-485/Modbus), self-cleaning, drift diagnostics |
| Contaminant screening | **Not included.** Architecture slot only | Integrated dedicated analysers / lab workflow with chain of custody |
| Node hardware | ESP32 dev board / module on a prototype carrier PCB | Custom PCB with isolated analog front-ends, conformal coating, EMC design |
| Edge | Raspberry Pi with SSD | Industrial-temperature edge computer, eMMC, hardware watchdog, UPS supervision |
| Enclosure | Weather-resistant enclosure per §9. **No rating claimed** | Tested to a relevant IP rating by an accredited lab; UV/corrosion testing |
| Power | Solar + wind hybrid, measured, with load shedding | Engineered sizing from site resource data; certified charge controllers; lightning protection design review |
| Communication | UART to Pi; optional 2G/LTE modem; Firebase over TLS | LTE-M/NB-IoT with fallback; private APN/VPN; store-and-forward gateways; satellite option |
| Data integrity | Append-only tables, Security Rules, hash chain, audit log | Signed frames (per-device keys in secure element), external timestamp anchoring, WORM storage |
| Security | Reasonable practices (§17) | Formal threat model, penetration testing, secure boot + flash encryption, SBOM, vulnerability disclosure process |
| Software quality | Unit + integration tests, CI | Coverage targets, HIL rigs in CI, formal release process, long-term support branches |
| Operations | Manual deployment checklist; debugger | Fleet management, OTA with staged roll-out, remote configuration with approvals |
| Compliance | **None claimed** | Electrical safety, EMC, radio approvals for the target country; water-sector requirements as applicable |
| Scale | 1–few nodes | Hundreds of nodes, multi-tenant, regional dashboards |

---

## 48. Limitations

### 48.1 Measurement limitations

1. **No contaminant identification.** pH, turbidity, TDS, EC and temperature are general indicators. They can't identify or quantify arsenic, heavy metals, fluoride, nitrate, organic pollutants or microbiological contamination.
2. **"Normal" readings don't mean "safe water".** Water can have unremarkable pH/EC/turbidity and still be unsafe.
3. **Low-cost sensor accuracy.** Accuracy, drift and lifetime of low-cost probes are limited and must be characterised. Published "accuracy" figures on module listings are often unverified.
4. **Turbidity units.** Many low-cost turbidity modules don't produce true NTU without calibration against standards.
5. **TDS is derived.** TDS is typically estimated from EC with a composition-dependent factor.
6. **Fouling and drift.** Readings degrade between maintenance visits; verification rules detect some, but not all, degradation.

### 48.2 Verification limitations

1. The engine classifies **data quality against rules**. It can't prove a reading is correct.
2. Slow drift within range and within rate limits won't trigger any rule. Periodic calibration is the only control.
3. Thresholds (rates, windows, tolerances) need site-specific tuning. Bad tuning produces false positives or missed faults.
4. Attention bands are only as good as their documented source.

### 48.3 Power limitations

1. **No guaranteed operation in every weather condition.** Long periods of low sun *and* low wind will deplete the battery.
2. Small wind turbines often perform below their rated output at low sites or in turbulent air; real output must be measured.
3. SoC estimation is approximate.
4. Battery capacity, chemistry and lifetime are **not specified** here and must be engineered per site.

### 48.4 Communication limitations

1. 2G availability is declining in many regions.
2. Cellular coverage at remote sites may be absent; data then waits in the local queue until a connection or site visit.
3. Firebase is a third-party cloud service with quotas, pricing and availability outside the project's control.

### 48.5 Integrity and security limitations

1. Physical access to the edge device enables tampering, which the hash chain makes **detectable**, not impossible.
2. The local UART link isn't authenticated in the prototype.
3. The security posture hasn't been independently assessed.

### 48.6 Physical limitations

1. No IP, UV, salt-spray, vibration or temperature-cycling tests have been performed.
2. No surge/lightning testing.
3. Theft and vandalism mitigation is basic.

### 48.7 Simulated evidence

Figures 6.2, 6.3, 12.2, 12.3, 14.2 and 15.2 come from **deterministic simulators** in this repository. They illustrate *behaviour of the logic*, not field performance.

---

## 49. Risk Register

<p align="center"><img src="diagrams/20_risk_matrix.png" alt="Risk matrix" width="75%"/></p>

<sub>Figure 49.1: Qualitative pre-deployment risk matrix.</sub>

| ID | Risk | L (1–5) | I (1–5) | Mitigation | Owner | Status |
|---|---|:-:|:-:|---|---|---|
| R-01 | Sensor drift / fouling | 4 | 3 | Calibration schedule; HLT/CON/ROC rules; guard pipe | Service | Open |
| R-02 | Cellular coverage gaps | 4 | 2 | Offline-first queue; site survey; LTE option | Architect | Mitigated (design) |
| R-03 | Battery degradation | 3 | 3 | SoC trend monitoring; capacity checks; replacement plan | Power | Open |
| R-04 | Enclosure water ingress | 2 | 4 | Glands on bottom, vent, drip loops; EN tests | Mechanical | Open |
| R-05 | Lightning / surge | 2 | 4 | Arrestor, TVS, earthing; design review | Electrical | Open |
| R-06 | Theft / vandalism | 3 | 4 | Lockable enclosure; height; door-open event | Ops | Open |
| R-07 | SD-card corruption | 3 | 3 | SSD; WAL + synchronous FULL; graceful shutdown; cloud replica | Edge | Mitigated (design) |
| R-08 | Clock drift | 3 | 2 | RTC; NTP/GSM time; TS rules | Firmware | Mitigated (design) |
| R-09 | Firebase quota / cost | 2 | 2 | Batching; emergency max duration; monitoring | Cloud | Open |
| R-10 | Credential leak | 1 | 4 | gitleaks, .gitignore, rotation procedure | All | Mitigated (process) |
| R-11 | Wind turbine over-speed | 2 | 3 | Controller + dump load + brake; inspection | Power | Open |
| R-12 | Operator misreads UI | 2 | 2 | Plain language; usability test P8-T6 | UI | Open |
| R-13 | Over-claiming capability | 2 | 5 | Claims policy §3.2; release claim review | Docs | Mitigated (process) |

---

## 50. Future Scalability

### 50.1 Scaling dimensions

<p align="center"><img src="diagrams/26_scaling_write_volume.png" alt="Scaling write volume" width="85%"/></p>

<sub>Figure 50.1: Arithmetic write volume vs fleet size for different sampling intervals (readings only; excludes power samples, events and results).</sub>

| Dimension | Current (prototype) | Scaling approach |
|---|---|---|
| Nodes per gateway | 1 (T1) | RS-485 multi-drop / local wireless star (T2); node addressing already in the schema |
| Gateways | 1 | Gateway ID in every record; per-gateway service accounts |
| Cloud writes | 1 doc per reading | Batch documents (e.g. hourly bundles) for NORMAL mode, keep per-reading docs for emergencies; archive to cold storage/BigQuery |
| Dashboard | Per-node views | Site → region hierarchy; map view; aggregated KPIs |
| Configuration | Per-node files | Central config with approval workflow → pushed to edge, audited |
| Firmware updates | USB | Signed OTA with staged rollout and automatic rollback |
| Analytics | Rule-based verification | Statistical baselines per site; anomaly scores as **advisory** extra fields (never replacing raw or rule results) |
| Sensors | 5 parameters | Plug-in sensor abstraction (`SensorBase`); additional parameters (e.g. dissolved oxygen, ORP) via schema v2 |
| Screening | None | Dedicated screening subsystem with its own collection and chain of custody (§9.6) |

### 50.2 Schema evolution

- `schema_version` in every frame; the edge accepts a configured list of versions.
- New optional fields are backward-compatible; new required fields → new major schema version.
- Schemas live in `smart-water-main/schema/` and are tagged; consumers pin a tag.

### 50.3 Roadmap after Phase 17

| Milestone | Content |
|---|---|
| M1: Pilot | 1–3 sites, 30–90 days, EN tests, measured energy budgets, first field test report |
| M2: Hardening | Custom PCB with isolated analog front-end; signed frames; secure boot; LTE-M modem |
| M3: Fleet | OTA, central config, multi-site dashboard, alert routing (SMS/e-mail) |
| M4: Compliance path | Identify applicable standards per target country; pre-compliance testing; accredited testing |
| M5: Screening integration | Partner with domain experts/labs to integrate a dedicated contaminant screening method |

---

## 51. Figure Generation (Python)

All figures in this README except the concept render (Figure 0) are **generated by Python** with matplotlib and numpy. No figures are hand-drawn or pulled from external services.

```bash
python scripts/generate_diagrams.py
```

| # | File | Generator function | Type | Data source |
|:-:|---|---|---|---|
| 0 | `00_hero_concept.png` | (AI image model) | Concept illustration | none, labelled as illustration |
| 1 | `01_system_architecture.png` | `fig_system_architecture` | Architecture diagram | design |
| 2 | `02_power_architecture.png` | `fig_power_architecture` | Architecture diagram | design |
| 3 | `03_data_pipeline.png` | `fig_data_pipeline` | Flow diagram | design |
| 4 | `04_verification_flowchart.png` | `fig_verification_flowchart` | Flowchart | rule catalogue |
| 5 | `05_mode_state_machine.png` | `fig_mode_state_machine` | State machine | design |
| 6 | `06_deployment_workflow.png` | `fig_deployment_workflow` | Workflow | §42 |
| 7 | `07_offline_sync_sequence.png` | `fig_offline_sync_sequence` | Sequence diagram | design |
| 8 | `08_repository_map.png` | `fig_repo_map` | Map | §23 |
| 9 | `09_sensor_timeseries_flags.png` | `fig_sensor_timeseries` | Time series | **SIMULATED** stream + real engine |
| 10 | `10_verification_distribution.png` | `fig_verification_distribution` | Bar charts | **SIMULATED** stream + real engine |
| 11 | `11_hybrid_power_4day.png` | `fig_hybrid_power` | Area + line chart | **SIMULATED** |
| 12 | `12_power_source_timeline.png` | `fig_power_source_timeline` | Timeline + donut | **SIMULATED** |
| 13 | `13_weather_scenario_matrix.png` | `fig_weather_matrix` | Heat map | qualitative design expectation |
| 14 | `14_mode_energy_model.png` | `fig_mode_energy` | Stacked bars + waveform | **ILLUSTRATIVE** model |
| 15 | `15_sync_queue_backlog.png` | `fig_sync_backlog` | Line chart | **SIMULATED** |
| 16 | `16_load_priority_matrix.png` | `fig_load_priority` | Matrix | configuration default |
| 17 | `17_dashboard_mockup.png` | `fig_dashboard_mockup` | UI mock-up | layout reference |
| 18 | `18_debugger_mockup.png` | `fig_debugger_mockup` | UI mock-up | layout reference |
| 19 | `19_phase_roadmap.png` | `fig_roadmap` | Gantt | plan |
| 20 | `20_risk_matrix.png` | `fig_risk_matrix` | Risk matrix | §49 |
| 21 | `21_test_plan_coverage.png` | `fig_test_matrix` | Bar chart | §46 |
| 22 | `22_enclosure_concept.png` | `fig_enclosure` | Concept layout | design |
| 23 | `23_alert_lifecycle.png` | `fig_alert_escalation` | State flow | §18.5 |
| 24 | `24_data_model.png` | `fig_data_model` | ER-style diagram | §10.4 |
| 25 | `25_hash_chain.png` | `fig_hash_chain` | Diagram | §13.4 |
| 26 | `26_scaling_write_volume.png` | `fig_scaling` | Log-log chart | arithmetic |

**Reproducibility:** all simulators use fixed random seeds, so a fresh run reproduces the figures exactly (given the same matplotlib version and fonts).

**Generator excerpt: how data-driven figures use the real engine:**

```python
def _stream_results():
    msgs = water_stream()                      # deterministic SIMULATED stream (seed=7)
    eng = VerificationEngine()                 # the SAME engine the tests exercise
    res = []
    for m in msgs:
        ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        res.append(eng.verify(m, ts + timedelta(seconds=3)))
    return msgs, res
```

---

## 52. Contributing, Git Workflow & Commit Conventions

### 52.1 Branching

```text
main ─────●────────●────────────●──────── (protected, always releasable)
           \        \            \
            feat/…   fix/…        docs/…   (short-lived, PR → main)
tags: v0.1.0 (release), tr-v0.1.0 (test report), schema-v1 (contracts)
```

### 52.2 Conventional Commits

| Type | Use for | Example |
|---|---|---|
| `feat` | New capability | `feat(validator): add CON-001 TDS/EC consistency rule` |
| `fix` | Bug fix | `fix(sync): treat ALREADY_EXISTS as success` |
| `test` | Tests only | `test(power): add four-scenario classifier tests` |
| `docs` | Documentation | `docs(main): add calibration record example` |
| `refactor` | No behaviour change | `refactor(receiver): extract frame decoder` |
| `chore` | Tooling, scaffolding | `chore: add gitleaks pre-commit hook` |
| `perf` | Performance | `perf(sync): batch creates with BulkWriter` |
| `security` | Security hardening | `security(api): constant-time token comparison` |

Scopes: `sensors`, `link`, `modes`, `power`, `receiver`, `validator`, `storage`, `sync`, `rules`, `dashboard`, `debugger`, `main`.

### 52.3 Full commit log for the 17 phases

```text
chore: scaffold repository structure, CI and secret scanning                               (P1)
feat(sensors): add acquisition for pH, turbidity, TDS, EC, temperature with null-on-disconnect and NVS calibration (P2)
feat(link): add CRC16-framed UART link with ACK/NACK, retries and replay ring buffer       (P3)
feat(receiver): add frame decoder and serial receiver with idempotent ACK                 (P3)
feat(storage): append-only SQLite raw store with SHA-256 hash chain and DB-level immutability (P4)
feat(validator): implement documented verification rule catalogue with append-only results (P5)
feat(sync): add durable idempotent outbox queue for offline-first operation               (P6)
feat(sync): idempotent Firestore sync with backoff and auth-error handling                (P7)
feat(rules): immutable readings/audit, ack-only alerts, role claims, emulator tests       (P7)
feat(dashboard): five-tab engineer dashboard with verification status, stale banner and ack-only alerts (P8)
feat(debugger): LAN diagnostic API (read-only DB), swdebug CLI, chain verification and reports (P9)
feat(power): solar channel measurement and debounced availability events                  (P10)
feat(power): wind channel with protection status and long-debounce availability           (P11)
feat(power): hybrid source classification, charge state and debounced switching events    (P12)
feat(power): SoC estimator, hysteresis battery policy, load shedding and energy budget tool (P13)
feat(modes): normal, low-power burst and local-first emergency modes with hysteresis      (P14)
test(integration): end-to-end offline/recovery test against Firestore emulator and soak KPIs (P15)
test: execute full test plan and publish TR-v0.1.0                                        (P16)
docs: complete system documentation, regenerate figures, claim review                     (P17)
```

### 52.4 Definition of Done (every PR)

- [ ] Code builds; all tests pass in CI
- [ ] New behaviour has tests (INPUT → EXPECTED)
- [ ] No secrets; `.example` files updated
- [ ] Docs updated (README/docs; rule catalogue if rules changed)
- [ ] No unsupported claims introduced
- [ ] Reviewer approved

### 52.5 Reporting security issues

Don't open public issues for vulnerabilities. Email the maintainers (address in `SECURITY.md`) with details and reproduction steps. We aim to acknowledge reports within a reasonable time frame. No specific response time is guaranteed for this student/prototype project.

---

## 53. Glossary

| Term | Definition |
|---|---|
| **ADC** | Analog-to-digital converter |
| **Attention band** | Project-configured range, with a documented source, outside which a reading is flagged ABNORMAL for follow-up |
| **Audit event** | Immutable record of a human or system action (who, what, when, why, before, after) |
| **Boot ID** | Counter persisted in ESP32 NVS, incremented on each boot, part of the record ID |
| **Burst** | Transmitting several buffered frames in one radio/Pi power-up window |
| **Chain hash** | SHA-256 over the previous chain hash and the current record hash |
| **CRC-16/CCITT** | Checksum used to detect transmission errors in local frames |
| **DoD** | Depth of discharge |
| **EC** | Electrical conductivity (µS/cm), temperature-compensated to 25 °C |
| **Edge** | Local computing layer (Raspberry Pi) between field node and cloud |
| **FRU** | Field-replaceable unit |
| **HIL** | Hardware-in-the-loop testing |
| **Hysteresis** | Different entry and exit thresholds to prevent rapid switching |
| **Idempotent** | An operation that has the same effect however many times it is repeated |
| **LVD** | Low-voltage disconnect: hardware battery protection |
| **MPPT / PWM** | Solar charge-controller types (maximum power point tracking / pulse-width modulation) |
| **NTU** | Nephelometric turbidity unit |
| **NVS** | Non-volatile storage (ESP32 flash key-value store) |
| **Outbox** | Local queue of records awaiting cloud delivery |
| **Raw reading** | The original value as produced by the node, stored unchanged |
| **RBAC** | Role-based access control |
| **RTC** | Real-time clock |
| **Screening** | Dedicated method targeting a specific contaminant; separate from core monitoring |
| **SoC** | State of charge (estimated) |
| **TDS** | Total dissolved solids (ppm), typically derived from EC |
| **TVS** | Transient-voltage-suppression diode |
| **Verification** | Applying documented data-quality rules to a raw reading |
| **WAL** | Write-ahead logging (SQLite journal mode) |

---

## 54. Appendices

### Appendix A: JSON Schema: raw reading v1

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/YOUR-ORG/smart-water-main/schema/raw-reading.v1.json",
  "title": "Smart Water raw reading v1",
  "type": "object",
  "required": ["schema_version", "record_id", "node_id", "sensor_ids", "timestamp", "seq", "mode", "raw", "power", "comm"],
  "additionalProperties": true,
  "properties": {
    "schema_version": { "const": 1 },
    "record_id": { "type": "string", "pattern": "^SWN-[0-9]{4}-[0-9]{5}-[0-9]{8}$" },
    "node_id":   { "type": "string", "pattern": "^SWN-[0-9]{4}$" },
    "boot_id":   { "type": "integer", "minimum": 0 },
    "seq":       { "type": "integer", "minimum": 0 },
    "sensor_ids": {
      "type": "object",
      "additionalProperties": { "type": "string", "pattern": "^[A-Z]{2}-[0-9]{2}$" }
    },
    "timestamp":   { "type": "string", "format": "date-time" },
    "time_source": { "enum": ["RTC", "NTP", "GSM", "UNSYNCED"] },
    "mode":        { "enum": ["NORMAL", "LOW_POWER", "EMERGENCY", "MAINTENANCE", "COMMISSIONING"] },
    "raw": {
      "type": "object",
      "required": ["ph", "turbidity_ntu", "tds_ppm", "ec_us_cm", "temperature_c"],
      "properties": {
        "ph":            { "type": ["number", "null"] },
        "turbidity_ntu": { "type": ["number", "null"] },
        "tds_ppm":       { "type": ["number", "null"] },
        "ec_us_cm":      { "type": ["number", "null"] },
        "temperature_c": { "type": ["number", "null"] }
      }
    },
    "raw_electrical": { "type": "object", "additionalProperties": { "type": ["number", "null"] } },
    "cal_version":    { "type": "object", "additionalProperties": { "type": "string" } },
    "power": {
      "type": "object",
      "properties": {
        "battery_v": { "type": ["number", "null"] },
        "battery_state": { "enum": ["CHARGING", "DISCHARGING", "IDLE", "FAULT", "UNKNOWN"] },
        "source": { "enum": ["SOLAR", "WIND", "SOLAR+WIND", "RENEWABLE+BATTERY", "BATTERY"] },
        "solar_w": { "type": ["number", "null"] },
        "wind_w":  { "type": ["number", "null"] },
        "load_w":  { "type": ["number", "null"] }
      }
    },
    "comm": {
      "type": "object",
      "properties": {
        "link":     { "enum": ["UART", "RS485", "WIFI", "CELLULAR"] },
        "modem":    { "type": "string" },
        "rssi_csq": { "type": ["integer", "null"] },
        "retries":  { "type": "integer", "minimum": 0 }
      }
    },
    "fw": { "type": "string" }
  }
}
```

### Appendix B: Event type catalogue

| Category | Type | Severity (default) | Alert? |
|---|---|---|:-:|
| SENSOR | `SENSOR_DISCONNECTED` | ALARM | ✅ |
| SENSOR | `SENSOR_RECOVERED` | INFO | |
| SENSOR | `SENSOR_STUCK` | WARNING | ✅ |
| SENSOR | `SENSOR_INCONSISTENT` | WARNING | ✅ |
| VERIFICATION | `ABNORMAL_READING` | WARNING | ✅ |
| VERIFICATION | `SUDDEN_CHANGE` | WARNING | ✅ |
| VERIFICATION | `VERIFICATION_FAILURE_RATE` | WARNING | ✅ |
| VERIFICATION | `ENGINE_ERROR` | ALARM | ✅ |
| COMM | `NODE_OFFLINE` | ALARM | ✅ |
| COMM | `NODE_ONLINE` | INFO | |
| COMM | `COMMUNICATION_FAILURE` | WARNING | ✅ |
| COMM | `CLOUD_AUTH_ERROR` | ALARM | ✅ (admin) |
| COMM | `SYNC_CONFLICT` | ALARM | ✅ (admin) |
| COMM | `FRAME_ERROR` | INFO | |
| POWER | `SOLAR_UNAVAILABLE` | INFO | |
| POWER | `WIND_UNAVAILABLE` | INFO | |
| POWER | `POWER_SOURCE_SWITCH` | INFO | |
| POWER | `RENEWABLE_RESTORED` | INFO | |
| POWER | `POWER_FAILURE` | WARNING | ✅ |
| POWER | `BATTERY_LOW` | WARNING | ✅ |
| POWER | `BATTERY_CRITICAL` | CRITICAL | ✅ |
| POWER | `BATTERY_RECOVERED` | INFO | |
| POWER | `CHARGING_FAILURE` | ALARM | ✅ |
| POWER | `OVERSPEED_PROTECTION` | INFO | |
| POWER | `LOAD_PROFILE_APPLIED` | INFO | |
| POWER | `POWER_MONITOR_FAULT` | WARNING | ✅ |
| SYSTEM | `MODE_CHANGE` | INFO | |
| SYSTEM | `EMERGENCY_ENTERED` | ALARM | ✅ |
| SYSTEM | `EMERGENCY_EXITED` | INFO | |
| SYSTEM | `STORAGE_LOW` | WARNING | ✅ |
| SYSTEM | `SERVICE_RESTARTED` | INFO | |
| SYSTEM | `ENCLOSURE_OPENED` (if switch fitted) | WARNING | ✅ |
| MAINTENANCE | `MAINTENANCE_DUE` | INFO | ✅ |
| MAINTENANCE | `MAINTENANCE_LOGGED` | INFO | |
| MAINTENANCE | `CALIBRATION_APPLIED` | INFO | |
| DEPLOYMENT | `NODE_STATE_CHANGE` | INFO | |
| DEPLOYMENT | `GATE_FAILED` | WARNING | |

### Appendix C: `architecture/` and `documentation/` file contents (outline)

| File | Sections |
|---|---|
| `architecture/system-architecture.md` | Layers (§4.2), responsibilities (§4.3), topologies (§4.5), interfaces (§4.6) |
| `architecture/data-flow.md` | Pipeline (§5), frame format, IDs, retention |
| `architecture/power-flow.md` | Hybrid architecture (§6), scenarios, budget template, failover (§22) |
| `architecture/communication-flow.md` | Paths (§7), framing, status model, cellular notes |
| `documentation/deployment.md` | Checklist (§42) as a printable form |
| `documentation/calibration.md` | §43 procedures + record template |
| `documentation/troubleshooting.md` | §45 symptom index + decision trees |
| `documentation/maintenance.md` | §44 schedule, logging, spares |

### Appendix D: `repository-links.md`

```markdown
# Repository links
| Repository | URL | Default branch | Latest release |
|---|---|---|---|
| smart-water-main | https://github.com/YOUR-ORG/smart-water-main | main | v0.1.0 |
| smart-water-esp32 | https://github.com/YOUR-ORG/smart-water-esp32 | main | v0.4.2 |
| smart-water-raspberry-pi | https://github.com/YOUR-ORG/smart-water-raspberry-pi | main | v0.3.0 |
| smart-water-dashboard | https://github.com/YOUR-ORG/smart-water-dashboard | main | v0.2.0 |
| smart-water-debugger | https://github.com/YOUR-ORG/smart-water-debugger | main | v0.2.0 |
| smart-water-firebase | https://github.com/YOUR-ORG/smart-water-firebase | main | v0.2.0 |
| smart-water-power | https://github.com/YOUR-ORG/smart-water-power | main | v0.3.0 |
| smart-water-testing | https://github.com/YOUR-ORG/smart-water-testing | main | tr-v0.1.0 |
```

> Version numbers above are placeholders to show the format.

### Appendix E: Pre-deployment site survey

| Item | Record |
|---|---|
| Site ID / GPS / access notes | |
| Water source type (well / tank / stream / other) | |
| Flow conditions, seasonal level variation | |
| Solar exposure (shading objects, horizon) | |
| Wind exposure (obstacles, typical direction), local wind data if available | |
| Cellular coverage per operator (measured CSQ, technology available) | |
| Security (fenced? guarded? community contact) | |
| Earthing possibility (soil type) | |
| Maintenance access frequency | |
| Local contact person | |
| Relevant local authority / water-quality programme contact | |

### Appendix F: Frequently asked questions

<details>
<summary><b>Can this system tell whether water is safe to drink?</b></summary>

No. It monitors general water-quality parameters and verifies data quality. Safety assessment needs appropriate testing (microbiological, chemical) by qualified people and laboratories.
</details>

<details>
<summary><b>Can it detect arsenic or heavy metals near mines?</b></summary>

Not with pH/TDS/EC/turbidity/temperature. Changes in these parameters may *prompt* further investigation, and a dedicated screening subsystem (§9.6) would be needed for specific contaminants.
</details>

<details>
<summary><b>Why not store just SAFE/UNSAFE to save space?</b></summary>

Because the decision can't be audited or re-evaluated without the raw data. Storage is cheap; lost evidence can't be recovered.
</details>

<details>
<summary><b>What happens if the internet is down for a week?</b></summary>

The node keeps sampling, the Pi keeps storing and verifying, and local alerts keep working. The outbox grows and drains when connectivity returns. Storage headroom is the limit (§5.5).
</details>

<details>
<summary><b>Can an administrator fix a wrong reading?</b></summary>

They can file a **correction annotation** in the audit log with a reason. The original reading stays unchanged and visible.
</details>

<details>
<summary><b>Why both solar and wind?</b></summary>

They're often complementary (e.g. cloudy but windy periods, or windy nights), which improves energy availability. It's not a guarantee: calm, overcast periods still happen, so battery reserve and low-power mode remain essential.
</details>

<details>
<summary><b>Is it waterproof?</b></summary>

It's *designed* for outdoor use with weather-protection measures (§9). No ingress-protection rating has been tested or is claimed.
</details>

---

## 55. License & Acknowledgements

### License

Code in these repositories is intended to be released under the **MIT License** (see `LICENSE` in each repository). Documentation and figures may be released under **CC BY 4.0**. *Confirm the license choice with your institution before publishing.*

```text
MIT License

Copyright (c) 2026 Smart Water Monitoring & Purification System contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Safety disclaimer

This is a prototype for research and education. It must not be used as the sole basis for decisions about drinking-water safety. Electrical work on batteries, solar and wind systems carries risk of fire, electric shock and injury. It must be carried out by competent persons in line with local regulations and the manufacturers' instructions.

### Acknowledgements

- Open-source projects: ESP32 Arduino core, PlatformIO, Python, SQLite, Firebase SDKs, React, matplotlib, numpy, pytest, Unity.
- Field communities and engineers whose constraints shaped the offline-first, maintainable design.

---

<div align="center">

**SMART WATER MONITORING & PURIFICATION SYSTEM**

`RUGGED` · `TRACEABLE` · `OFFLINE-FIRST` · `TAMPER-RESISTANT` · `ENERGY-AWARE` · `RENEWABLE-POWERED` · `SIMPLE TO OPERATE` · `MODULAR` · `TESTABLE` · `SCALABLE`

<sub>Engineering correctness over impressive but unsupported claims.</sub>

[⬆ Back to top](#-smart-water-monitoring--purification-system)

</div>
