---

## Phase 12: Hybrid Energy Management

**1. Objective.** Combine solar, wind and battery measurements into a single power status: classify the active source, determine charge state, and handle all four availability scenarios deterministically.

**2. Architecture.**

```text
PowerSnapshot ─► SourceClassifier ─► source ∈ {SOLAR, WIND, SOLAR+WIND, RENEWABLE+BATTERY, BATTERY}
              ─► ChargeState      ─► {CHARGING, DISCHARGING, IDLE, FAULT, UNKNOWN}
              ─► Switch debouncer ─► POWER_SOURCE_SWITCH / RENEWABLE_RESTORED events
              ─► PowerStatus{source, charge_state, soc_est, renewable_w, load_w} ─► ModeManager (Phase 14)
```

**3. Folder structure.** `firmware/src/SourceClassifier.*`, `src/power/classify.py` (§20.4), `src/power/hybrid.py`.

**4. Required files.** Classifier, charge-state logic, switch debouncer, tests.

**5. Complete code.**

```python
# smart-water-power/src/power/hybrid.py
from __future__ import annotations

from dataclasses import dataclass, field

from .classify import Source, classify


def charge_state(battery_i: float | None, eps_a: float = 0.05) -> str:
    if battery_i is None:
        return "UNKNOWN"
    if battery_i > eps_a:
        return "CHARGING"
    if battery_i < -eps_a:
        return "DISCHARGING"
    return "IDLE"


@dataclass
class HybridManager:
    eps_w: float = 0.2
    debounce_s: int = 120
    current: Source | None = None
    _candidate: Source | None = None
    _candidate_since: int = 0
    events: list = field(default_factory=list)

    def update(self, now: int, solar_w, wind_w, load_w, battery_i):
        s = 0.0 if solar_w is None else solar_w
        w = 0.0 if wind_w is None else wind_w
        l = 0.0 if load_w is None else load_w
        src = classify(s, w, l, self.eps_w)
        if self.current is None:
            self.current = src
        elif src != self.current:
            if src != self._candidate:
                self._candidate, self._candidate_since = src, now
            elif now - self._candidate_since >= self.debounce_s:
                prev, self.current = self.current, src
                self.events.append((now, "POWER_SOURCE_SWITCH", prev.value, src.value))
                if prev == Source.BATTERY and src != Source.BATTERY:
                    self.events.append((now, "RENEWABLE_RESTORED", prev.value, src.value))
                self._candidate = None
        else:
            self._candidate = None
        return {"source": self.current.value, "charge_state": charge_state(battery_i),
                "renewable_w": s + w, "load_w": l}
```

**6. Configuration.** `measurement.noise_floor_w`, `events.switch_debounce_s` (§21.4).

**7. Installation commands.** As Phase 10.

**8. Run commands.** `python -m pytest -q tests/test_hybrid.py`

**9. Expected output.** `6 passed`

**10. Test procedure: the four availability scenarios.**

```python
# tests/test_hybrid.py
import pytest
from power.classify import classify, Source
from power.hybrid import HybridManager, charge_state

LOAD = 3.0

@pytest.mark.parametrize("solar,wind,expected", [
    (10.0, 0.0,  Source.SOLAR),               # 1 solar available, wind unavailable
    (0.0,  8.0,  Source.WIND),                # 2 solar unavailable, wind available
    (6.0,  4.0,  Source.SOLAR_WIND),          # 3 both available
    (0.0,  0.0,  Source.BATTERY),             # 4 neither available
])
def test_four_scenarios(solar, wind, expected):
    assert classify(solar, wind, LOAD) == expected

def test_insufficient_renewable_uses_battery_too():
    assert classify(1.0, 0.5, LOAD) == Source.RENEWABLE_BATTERY

def test_switch_is_debounced_and_restoration_logged():
    m = HybridManager(debounce_s=120)
    m.update(0, 0, 0, LOAD, -0.3)                        # BATTERY
    m.update(60, 10, 0, LOAD, 0.5)                       # candidate SOLAR
    assert m.current == Source.BATTERY
    m.update(200, 10, 0, LOAD, 0.5)                      # debounce elapsed
    assert m.current == Source.SOLAR
    assert [e[1] for e in m.events] == ["POWER_SOURCE_SWITCH", "RENEWABLE_RESTORED"]
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P12-T1 | Solar ✔, wind ✘ (bench PSU emulating PV; turbine braked) | Observe | source SOLAR | _record_ | _ |
| P12-T2 | Solar ✘, wind ✔ | Observe | source WIND | _record_ | _ |
| P12-T3 | Both ✔ | Observe | SOLAR+WIND; CHARGING | _record_ | _ |
| P12-T4 | Neither | Observe | BATTERY; DISCHARGING | _record_ | _ |
| P12-T5 | Solar flickers (cloud edge) every 30 s | Observe | No switch events within debounce | _record_ | _ |
| P12-T6 | pytest | — | 6/6 pass | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| Rapid source switching | Debounce too short / noise floor too low | Increase `switch_debounce_s`, calibrate `eps` |
| Source BATTERY while panel is in sun | Controller in float (battery full): low current | Expected. Charge state is IDLE, not a fault |
| CHARGING shown at night | Battery current sensor offset | Zero-offset calibration of the INA |

**12. Git commands.**

```bash
git checkout -b feat/phase-12-hybrid
git add src/power/classify.py src/power/hybrid.py firmware/src/SourceClassifier.* tests/test_hybrid.py
git commit -m "feat(power): hybrid source classification, charge state and debounced switching events"
```

**13. Commit message.** `feat(power): hybrid source classification, charge state and debounced switching events`

**14. README update.** Add the four-scenario table (§6.3) and figures 6.2/6.3 to `smart-water-power/README.md`. Mark Phase 12 ✅.

---

## Phase 13: Battery Backup

**1. Objective.** Estimate battery state, apply the configurable LOW_ENTER / LOW_EXIT / CRITICAL thresholds with hysteresis, raise battery events, perform load shedding (including the graceful Pi shutdown handshake), and **measure** the real energy budget.

**2. Architecture.**

```text
battery V/I/T ─► SocEstimator (voltage LUT + coulomb counting, re-sync at rest) ─► soc_est
soc_est ─► BatteryPolicy (hysteresis) ─► PowerLevel {NORMAL, LOW, CRITICAL}
PowerLevel ─► LoadManager (§22.4) ─► load switches P2/P3/P4, Pi shutdown handshake (§22.3)
Hardware LVD (independent) ─► protects battery if firmware fails
```

**3. Folder structure.** `firmware/src/SocEstimator.*`, `firmware/src/BatteryPolicy.*`, `src/power/soc.py`, `src/power/budget.py`, `docs/battery.md`.

**4. Required files.** Estimator, policy, budget tool, tests, and a measured energy-budget sheet.

**5. Complete code.**

```python
# smart-water-power/src/power/soc.py
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass


@dataclass
class SocEstimator:
    """Combined estimator. The LUT (rest voltage -> SoC%) MUST come from the battery datasheet
    for the chosen chemistry; capacity_ah is TBD / CONFIGURABLE."""
    capacity_ah: float
    lut_v: list[float]            # ascending rest voltages
    lut_soc: list[float]          # matching SoC %
    soc: float = 50.0
    rest_a: float = 0.05          # |I| below this counts as 'at rest'
    rest_needed_s: int = 1800
    _rest_s: int = 0

    def _from_voltage(self, v: float) -> float:
        if v <= self.lut_v[0]:
            return self.lut_soc[0]
        if v >= self.lut_v[-1]:
            return self.lut_soc[-1]
        i = bisect_left(self.lut_v, v)
        v0, v1, s0, s1 = self.lut_v[i - 1], self.lut_v[i], self.lut_soc[i - 1], self.lut_soc[i]
        return s0 + (s1 - s0) * (v - v0) / (v1 - v0)

    def update(self, v: float | None, i: float | None, dt_s: float) -> float:
        if i is not None:
            self.soc += 100.0 * (i * dt_s / 3600.0) / self.capacity_ah       # coulomb counting (+ = charge)
            self._rest_s = self._rest_s + dt_s if abs(i) < self.rest_a else 0
        if v is not None and self._rest_s >= self.rest_needed_s:
            self.soc = 0.7 * self.soc + 0.3 * self._from_voltage(v)          # gentle re-sync at rest
        self.soc = max(0.0, min(100.0, self.soc))
        return self.soc


@dataclass
class BatteryPolicy:
    low_enter: float
    low_exit: float
    critical: float
    level: str = "NORMAL"

    def __post_init__(self):
        if not (self.critical < self.low_enter < self.low_exit):
            raise ValueError("require critical < low_enter < low_exit (hysteresis)")

    def update(self, soc: float) -> tuple[str, str | None]:
        prev = self.level
        if soc < self.critical:
            self.level = "CRITICAL"
        elif soc < self.low_enter:
            self.level = "LOW" if prev != "CRITICAL" or soc >= self.low_enter else prev
        elif soc > self.low_exit:
            self.level = "NORMAL"
        elif prev == "CRITICAL" and soc >= self.low_enter:
            self.level = "LOW"
        event = None
        if self.level != prev:
            event = {"CRITICAL": "BATTERY_CRITICAL", "LOW": "BATTERY_LOW", "NORMAL": "BATTERY_RECOVERED"}[self.level]
        return self.level, event
```

```python
# smart-water-power/src/power/budget.py — turns MEASURED values into autonomy estimates
from __future__ import annotations


def autonomy_days(nominal_v: float, capacity_ah: float, dod: float, eta_discharge: float, avg_load_w: float) -> float:
    if avg_load_w <= 0:
        raise ValueError("avg_load_w must be > 0 (measured)")
    usable_wh = nominal_v * capacity_ah * dod * eta_discharge
    return usable_wh / (avg_load_w * 24.0)


def required_daily_harvest_wh(avg_load_w: float, eta_charge: float, eta_controller: float) -> float:
    return avg_load_w * 24.0 / (eta_charge * eta_controller)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Energy budget from MEASURED inputs")
    for k in ("nominal_v", "capacity_ah", "dod", "eta_discharge", "avg_load_w", "eta_charge", "eta_controller"):
        ap.add_argument(f"--{k}", type=float, required=True)
    a = ap.parse_args()
    print(f"autonomy (no input): {autonomy_days(a.nominal_v, a.capacity_ah, a.dod, a.eta_discharge, a.avg_load_w):.2f} days")
    print(f"required daily harvest: {required_daily_harvest_wh(a.avg_load_w, a.eta_charge, a.eta_controller):.1f} Wh/day")
```

**6. Configuration.** `battery.*` in `power.example.yaml`. **The LUT, capacity and thresholds must come from the selected battery's datasheet and from measurement. None are provided here.**

**7. Installation commands.** As Phase 10.

**8. Run commands.**

```bash
python -m pytest -q tests/test_battery.py
# after measuring (example invocation — values are placeholders you must replace):
python -m power.budget --nominal_v <V> --capacity_ah <Ah> --dod <0-1> --eta_discharge <0-1> \
       --avg_load_w <measured W> --eta_charge <0-1> --eta_controller <0-1>
```

**9. Expected output.**

```text
tests/test_battery.py .....                                              [100%]
5 passed
autonomy (no input): X.XX days
required daily harvest: YYY.Y Wh/day
```

**10. Test procedure.**

```python
# tests/test_battery.py
import pytest
from power.soc import BatteryPolicy, SocEstimator

def test_policy_requires_hysteresis_order():
    with pytest.raises(ValueError):
        BatteryPolicy(low_enter=30, low_exit=25, critical=15)

def test_low_then_critical_then_recover_with_hysteresis():
    p = BatteryPolicy(low_enter=30, low_exit=45, critical=15)
    assert p.update(29)[1] == "BATTERY_LOW"
    assert p.update(14)[1] == "BATTERY_CRITICAL"
    assert p.update(20)[0] == "CRITICAL"          # still below low_enter
    assert p.update(31)[0] == "LOW"               # above low_enter but below low_exit
    assert p.update(40)[0] == "LOW"               # hysteresis band
    assert p.update(46)[1] == "BATTERY_RECOVERED"

def test_coulomb_counting_direction():
    e = SocEstimator(capacity_ah=10, lut_v=[11.8, 13.4], lut_soc=[0, 100], soc=50)
    e.update(None, +1.0, 3600)    # +1 A for 1 h into 10 Ah → +10 %
    assert abs(e.soc - 60) < 1e-6

def test_soc_clamped():
    e = SocEstimator(capacity_ah=1, lut_v=[11.8, 13.4], lut_soc=[0, 100], soc=99)
    e.update(None, +5.0, 3600)
    assert e.soc == 100

def test_rest_resync_moves_toward_voltage_estimate():
    e = SocEstimator(capacity_ah=10, lut_v=[11.8, 13.4], lut_soc=[0, 100], soc=90, rest_needed_s=60)
    e.update(12.6, 0.0, 120)       # at rest; LUT says 50 %
    assert e.soc < 90
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P13-T1 | All renewables disconnected, full battery | Run until LOW | `BATTERY_LOW` at configured threshold; P4 off, P3 burst | _record_ | _ |
| P13-T2 | Continue discharge | Run until CRITICAL | Pi shutdown handshake completes; P2 off; ESP32 keeps sampling | _record_ | _ |
| P13-T3 | Reconnect renewable | Charge | P2 restored only after SoC > LOW_EXIT | _record_ | _ |
| P13-T4 | Firmware halted (debug) during deep discharge | Hardware LVD | Loads cut at LVD threshold; battery protected | _record_ | _ |
| P13-T5 | Measure average load per mode for 24 h | Energy logger | Fill §6.5 table with measured values | _record_ | _ |
| P13-T6 | Pi file-system after 20 forced CRITICAL cycles | `fsck`, `PRAGMA integrity_check` | No corruption | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| SoC estimate drifts over days | Coulomb-counting offset | Zero-offset calibration; ensure rest periods for re-sync |
| Pi reboots under load | Buck converter undersized / voltage drop | Use an adequately rated supply; thicker cables |
| Frequent LOW↔NORMAL flapping | Hysteresis band too narrow | Widen LOW_EXIT − LOW_ENTER |
| ESP32 brownout resets during modem TX | Modem peak current | Separate supply / bulk capacitance for modem |

**12. Git commands.**

```bash
git checkout -b feat/phase-13-battery
git add src/power/soc.py src/power/budget.py firmware/src/SocEstimator.* firmware/src/BatteryPolicy.* tests/test_battery.py docs/battery.md
git commit -m "feat(power): SoC estimator, hysteresis battery policy, load shedding and energy budget tool"
```

**13. Commit message.** `feat(power): SoC estimator, hysteresis battery policy, load shedding and energy budget tool`

**14. README update.** Publish the **measured** energy-budget table in `docs/battery.md` and link it from §6.5. Mark Phase 13 ✅.

---

## Phase 14: Operating Modes

**1. Objective.** Implement NORMAL, LOW-POWER/BURST and EMERGENCY modes on the ESP32 per §14, with hysteresis, hold times, local-first emergency behaviour, an energy guard, and mode fields in every frame.

**2. Architecture.** See §14.1 (state machine) and §14.6 (logic).

**3. Folder structure.** `modes/ModeManager.{h,cpp}`, `diagnostics/LocalAlert.{h,cpp}`, `src/main.cpp` (scheduler), `tests/test_modes/`.

**4. Required files.** ModeManager, LocalAlert, the deep-sleep scheduler, and emergency trigger evaluation.

**5. Complete code.**

```cpp
// src/main.cpp — Phase 14 scheduler (condensed; acquisition/link from Phases 2–3)
#include <Arduino.h>
#include <esp_sleep.h>
#include "ModeManager.h"
#include "LocalAlert.h"
#include "NodeApp.h"

RTC_DATA_ATTR uint32_t g_wakeCount = 0;          // survives deep sleep
RTC_DATA_ATTR uint8_t  g_mode = (uint8_t)Mode::NORMAL;

NodeApp app;                                     // wraps sensors, link, power, ring buffer
ModeManager modes(app.config().modes);
LocalAlert alert(PIN_BUZZER, PIN_LED_G, PIN_LED_Y, PIN_LED_R);

static void cycle() {
  const PowerStatus p = app.samplePower();
  const Frame f = app.acquire((Mode)g_mode, p);            // COLLECT
  const TriggerState t = app.evaluateTriggers(f);          // LOCAL PROCESSING (no cloud needed)
  app.store(f);                                            // STORE (ring buffer)
  const Mode next = modes.evaluate(p, t, app.nowEpoch());
  if (next != (Mode)g_mode) app.logModeChange((Mode)g_mode, next, t.reason);
  g_mode = (uint8_t)next;
  alert.show(next, t);                                     // LOCAL ALERT
  const bool burst = next != Mode::LOW_POWER ||
                     (++g_wakeCount % app.config().modes.lowPower.burstEveryNWakes == 0) ||
                     app.bufferDepth() >= app.config().modes.lowPower.burstWhenBufferGe;
  if (burst) app.flush(next == Mode::LOW_POWER);           // TRANSMIT (powers Pi/modem if needed)
}

void setup() {
  Serial.begin(115200);
  app.begin();
  alert.begin();
  cycle();
  if ((Mode)g_mode == Mode::LOW_POWER) {
    app.prepareDeepSleep();                                // excitation off, radios off, P3 off
    esp_sleep_enable_timer_wakeup((uint64_t)app.config().modes.lowPower.intervalS * 1000000ULL);
    esp_deep_sleep_start();                                // → SLEEP; setup() runs again on wake
  }
}

void loop() {                                              // NORMAL / EMERGENCY stay awake (light sleep)
  const uint32_t interval = ((Mode)g_mode == Mode::EMERGENCY)
                              ? app.emergencyIntervalS()   // rate-capped under soc_floor
                              : app.config().modes.normal.intervalS;
  app.idleFor(interval);                                   // light sleep + serve link/heartbeats
  cycle();
  if ((Mode)g_mode == Mode::LOW_POWER) setup();            // transition into deep-sleep path
}
```

```cpp
// diagnostics/LocalAlert.cpp — works with no network at all
#include "LocalAlert.h"

void LocalAlert::show(Mode m, const TriggerState& t) {
  digitalWrite(g_, m == Mode::NORMAL && !t.anyWarning);
  digitalWrite(y_, m == Mode::LOW_POWER || t.anyWarning);
  digitalWrite(r_, m == Mode::EMERGENCY);
  if (m == Mode::EMERGENCY && !silenced_) pattern(3, 150, 150);   // 3 short beeps each cycle
  else if (t.sensorFault && !silenced_) pattern(1, 60, 0);         // 1 chirp: maintenance attention
}
```

| LED / buzzer | Meaning |
|---|---|
| 🟢 green steady | NORMAL, no warnings |
| 🟡 yellow steady | LOW-POWER mode **or** warning present |
| 🔴 red steady + 3 beeps/cycle | EMERGENCY mode |
| 1 chirp per cycle | Sensor fault needing maintenance |
| Silence button (debounced, logged) | Mutes buzzer for `silence_s`; LEDs stay on |

**6. Configuration.** `modes.example.yaml` (§14.4). Emergency triggers must be configured explicitly. **No default toxic thresholds.**

**7. Installation commands.** As Phase 2.

**8. Run commands.**

```bash
pio test -e native -f test_modes
pio run -e esp32dev -t upload && pio device monitor
```

**9. Expected output.**

```text
[mode] NORMAL -> LOW_POWER  reason=soc 28.4% < enter 30.0% for 900s
[sleep] deep sleep 1800 s (wake #1, buffer 1)
...
[mode] LOW_POWER -> EMERGENCY  reason=ROC-001 ph x2 (configured trigger)
[alert] RED + buzzer pattern
[mode] EMERGENCY -> LOW_POWER  reason=cleared + hold 1800s, soc still low
```

**10. Test procedure.**

```cpp
// tests/test_modes/test_main.cpp
#include <unity.h>
#include "ModeManager.h"

static ModesConfig cfg() {
  ModesConfig c; c.lowPower.enterSocPct = 30; c.lowPower.exitSocPct = 45;
  c.lowPower.enterRenewableW = 0.5f; c.lowPower.exitRenewableW = 1.0f;
  c.lowPower.enterForS = 900; c.lowPower.exitForS = 1800; c.emergency.holdTimeS = 1800; return c;
}

void test_enters_low_power_after_dwell() {
  ModeManager m(cfg()); PowerStatus p{25, 0.0f}; TriggerState t{};
  TEST_ASSERT_EQUAL(Mode::NORMAL, m.step(p, t, 0));
  TEST_ASSERT_EQUAL(Mode::NORMAL, m.step(p, t, 600));
  TEST_ASSERT_EQUAL(Mode::LOW_POWER, m.step(p, t, 901));
}
void test_hysteresis_prevents_flapping() {
  ModeManager m(cfg()); TriggerState t{};
  m.step({25, 0}, t, 0); m.step({25, 0}, t, 901);
  TEST_ASSERT_EQUAL(Mode::LOW_POWER, m.step({40, 5}, t, 1000));      // above enter, below exit
  TEST_ASSERT_EQUAL(Mode::LOW_POWER, m.step({50, 5}, t, 1100));      // exit dwell not met
  TEST_ASSERT_EQUAL(Mode::NORMAL,    m.step({50, 5}, t, 2901));
}
void test_emergency_overrides_and_holds() {
  ModeManager m(cfg()); TriggerState on{true}, off{false};
  TEST_ASSERT_EQUAL(Mode::EMERGENCY, m.step({80, 5}, on, 0));
  TEST_ASSERT_EQUAL(Mode::EMERGENCY, m.step({80, 5}, off, 1000));    // hold time
  TEST_ASSERT_EQUAL(Mode::NORMAL,    m.step({80, 5}, off, 1801));
}
int main() { UNITY_BEGIN(); RUN_TEST(test_enters_low_power_after_dwell);
  RUN_TEST(test_hysteresis_prevents_flapping); RUN_TEST(test_emergency_overrides_and_holds); return UNITY_END(); }
```

> `ModeManager::step()` is `evaluate()` (§14.6) plus the assignment `current_ = result`, which keeps the unit tests simple.

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| MD-01 | Healthy power | 1 h | NORMAL; ~12 frames at 300 s | _record_ | _ |
| MD-02 | SoC below enter for dwell | Observe | LOW_POWER; deep sleep; burst every N wakes | _record_ | _ |
| MD-03 | Configured trigger (test band) | Observe | EMERGENCY within one cycle; red LED + buzzer **with network unplugged** | _record_ | _ |
| MD-04 | Emergency + SoC below floor | Observe | Rate capped; event logged | _record_ | _ |
| MD-05 | Measure current per mode | Energy logger | Values recorded; replace illustrative Fig. 14.2 with measured version | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| Node never wakes from deep sleep | Timer wake not enabled / brownout | Check `esp_sleep_enable_timer_wakeup`; supply |
| Frames out of order after sleep | seq not persisted | Keep seq in RTC memory; `boot_id` in NVS |
| Emergency never clears | Trigger re-fires from stale buffer | Evaluate triggers on fresh samples only |

**12. Git commands.**

```bash
git checkout -b feat/phase-14-modes
git add modes diagnostics/LocalAlert.* src/main.cpp tests/test_modes config/modes.example.yaml
git commit -m "feat(modes): normal, low-power burst and local-first emergency modes with hysteresis"
```

**13. Commit message.** `feat(modes): normal, low-power burst and local-first emergency modes with hysteresis`

**14. README update.** Add the mode table and LED legend to `smart-water-esp32/README.md`. Mark Phase 14 ✅.

---

## Phase 15: Full System Integration

**1. Objective.** Run the whole chain (sensors → ESP32 → Pi → verification → storage → sync → Firebase → dashboard/debugger), powered from the hybrid system, for a sustained soak test, including injected faults.

**2. Architecture.** §4.1 in full. Integration bench:

```text
┌──────── Test bench ───────────────────────────────────────────────────────────┐
│ Reference water vessels (buffers, standards) │ Bench PSU (PV emulator) │      │
│ Motor rig or real turbine │ Battery │ Load switches │ ESP32 │ Pi │ Router     │
│ Network kill-switch (smart plug / iptables script) │ Fault-injection jig      │
└───────────────────────────────────────────────────────────────────────────────┘
```

**3. Folder structure.** `smart-water-testing/integration/`, `smart-water-testing/hil/`.

**4. Required files.** `integration/test_e2e_offline.py`, `hil/fault_injector.py`, `integration/soak_monitor.py`, `reports/`.

**5. Complete code.**

```python
# smart-water-testing/integration/test_e2e_offline.py
"""End-to-end: frames → edge pipeline → outbox → Firestore EMULATOR, with an outage in the middle.
Requires: FIRESTORE_EMULATOR_HOST set; smart-water-raspberry-pi installed in the venv."""
import os
import pytest

from swedge.storage.db import connect
from swedge.storage.raw_store import RawStore
from swedge.storage.result_store import ResultStore
from swedge.sync.outbox import Outbox
from swedge.sync.engine import SyncEngine, CloudUnavailable
from swedge.validator.engine import VerificationEngine
from swedge.pipeline import Pipeline
from edge.simulator import water_stream           # from smart-water-main/reference (installed as fixture pkg)

pytestmark = pytest.mark.skipif("FIRESTORE_EMULATOR_HOST" not in os.environ, reason="emulator not running")


class Switchable:
    def __init__(self, real): self.real, self.up = real, True
    def upsert_many(self, docs):
        if not self.up: raise CloudUnavailable("network down (test)")
        return self.real.upsert_many(docs)


class NullEvents:
    def from_rule_hit(self, *a): pass


def test_outage_no_loss_no_duplicates(tmp_path):
    from swedge.sync.firestore_client import FirestoreClient
    con = connect(str(tmp_path / "e2e.db"))
    con.execute("INSERT INTO nodes VALUES ('SWN-0001','LOC','DEPLOYED_VERIFIED','{}','t','t')")
    cloud = Switchable(FirestoreClient("demo-smart-water"))
    pipe = Pipeline(RawStore(con), ResultStore(con, "cfg"), NullEvents(), Outbox(con), VerificationEngine())
    sync = SyncEngine(con, cloud, {"batch_size": 50, "base_delay_s": 0, "max_delay_s": 0, "jitter_s": 0})

    msgs = water_stream(n=288)
    for i, m in enumerate(msgs):
        cloud.up = not (100 <= i < 200)                  # outage for 100 samples
        pipe.handle(m, m["timestamp"].replace("Z", "+00:00"))
        pipe.handle(m, m["timestamp"].replace("Z", "+00:00"))   # replay: must be a no-op
        sync.run_once()
    cloud.up = True
    while sync.run_once():
        pass

    local = con.execute("SELECT COUNT(*) FROM raw_readings").fetchone()[0]
    remote = len(list(cloud.real.db.collection("readings").stream()))
    assert local == 288 and remote == 288
```

```python
# smart-water-testing/integration/soak_monitor.py — samples KPIs every 10 min into a CSV for the report
import csv, os, time, requests
from datetime import datetime, timezone

GW, TOKEN = os.environ["SW_GATEWAY"], os.environ["SW_DEBUG_API_TOKEN"]
with open("soak_kpis.csv", "a", newline="") as f:
    w = csv.writer(f)
    while True:
        s = requests.get(f"{GW}/api/v1/status", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10).json()
        w.writerow([datetime.now(timezone.utc).isoformat(), s["outbox_pending"], s["disk_used_pct"],
                    s["cpu_temp_c"], (s["last_reading"] or {}).get("received_ts")])
        f.flush(); time.sleep(600)
```

**6. Configuration.** Site-like configs in `integration/configs/`. Sensor ranges from the actual datasheets; `tds_ec_factor` from bench calibration.

**7. Installation commands.**

```bash
cd smart-water-testing
python -m venv .venv && . .venv/bin/activate
pip install -e ../smart-water-raspberry-pi -e ../smart-water-main/reference pytest requests
firebase emulators:start --only firestore &
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
```

**8. Run commands.**

```bash
python -m pytest -q integration/test_e2e_offline.py
python integration/soak_monitor.py          # during the 7-day soak
```

**9. Expected output.**

```text
integration/test_e2e_offline.py .                                        [100%]
1 passed
```

**10. Test procedure: integration scenarios.**

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| IT-01 | 7-day soak, NORMAL | Continuous | ≥ 99% of expected frames stored locally (target, TBD); 100% of stored frames synced; 0 duplicates | _record_ | _ |
| IT-02 | 3 network outages (1 h, 6 h, 13 h) | Kill-switch | No loss; queue drains; dashboard stale banner during outage | _record_ | _ |
| IT-03 | Pi power-cycled 5× | Relay | ESP32 buffer replays; chain valid; DB integrity ok | _record_ | _ |
| IT-04 | Sensor unplug/replug (each) | Manual | MIS-001 + alert; recovery; debugger confirms | _record_ | _ |
| IT-05 | Renewable off for 24 h | PSU off, turbine braked | LOW-POWER → (CRITICAL) → recovery; events correct | _record_ | _ |
| IT-06 | Emergency trigger with network down | Test band | Local alert immediately; cloud alert after reconnect | _record_ | _ |
| IT-07 | Engineer acknowledges alert | Dashboard | Audit record exists with uid + server ts | _record_ | _ |
| IT-08 | Emulator e2e | pytest | 1/1 pass (288 local = 288 remote) | _record_ | _ |

**11. Troubleshooting.** See [§45](#45-troubleshooting-guide). Integration-specific: if counts differ, compare `record_id` sets (`local − remote`) and inspect `sync_outbox.last_error` for the missing IDs.

**12. Git commands.**

```bash
git checkout -b test/phase-15-integration
git add integration hil reports/.gitkeep
git commit -m "test(integration): end-to-end offline/recovery test against Firestore emulator and soak KPIs"
```

**13. Commit message.** `test(integration): end-to-end offline/recovery test against Firestore emulator and soak KPIs`

**14. README update.** Publish the soak-test report summary (KPIs, anomalies, open issues) in `smart-water-testing/reports/` and link it here. Mark Phase 15 ✅.

---

## Phase 16: Testing

**1. Objective.** Execute the complete test plan in [§46](#46-comprehensive-test-plan), record every result in the INPUT → PROCESS → EXPECTED → ACTUAL → PASS/FAIL format, and publish a versioned test report.

**2. Architecture.**

```text
Unit (per repo, CI) ─► Integration (emulators) ─► HIL (bench) ─► Pilot/field (future)
         │                     │                     │
         └──────────── tools/report.py collects JUnit XML + manual CSV ──► reports/TR-<version>.md
```

**3. Folder structure.** `smart-water-testing/{unit-links.md, integration/, hil/, e2e/, security/, reports/, tools/}`.

**4. Required files.** `tools/report.py`, `security/test_api_auth.py`, `security/fuzz_framing.py`, `manual/*.csv`.

**5. Complete code.**

```python
# smart-water-testing/tools/report.py
"""Merge JUnit XML (automated) + CSV (manual/HIL) into a Markdown test report."""
import csv
import glob
import sys
import xml.etree.ElementTree as ET
from datetime import date

rows = []
for x in glob.glob("results/*.xml"):
    for tc in ET.parse(x).getroot().iter("testcase"):
        failed = tc.find("failure") is not None or tc.find("error") is not None
        skipped = tc.find("skipped") is not None
        rows.append([tc.get("name"), "automated", tc.get("classname"), "see code", "PASS" if not failed else "FAIL",
                     "SKIP" if skipped else ("FAIL" if failed else "PASS")])
for c in glob.glob("manual/*.csv"):
    with open(c) as f:
        for r in csv.DictReader(f):
            rows.append([r["id"], r["input"], r["process"], r["expected"], r["actual"], r["result"]])

version = sys.argv[1] if len(sys.argv) > 1 else "dev"
total = len(rows); passed = sum(r[5] == "PASS" for r in rows); failed = sum(r[5] == "FAIL" for r in rows)
out = [f"# Test Report TR-{version} ({date.today()})", "",
       f"**Total:** {total} · **PASS:** {passed} · **FAIL:** {failed} · **Other:** {total - passed - failed}", "",
       "| ID | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |", "|---|---|---|---|---|:-:|"]
out += [f"| {' | '.join(str(c).replace('|', '/') for c in r)} |" for r in rows]
open(f"reports/TR-{version}.md", "w").write("\n".join(out) + "\n")
print(f"wrote reports/TR-{version}.md ({passed}/{total} PASS)")
```

```python
# smart-water-testing/security/fuzz_framing.py — robustness: decoder must never crash or yield bad payloads
import os
import random

from swedge.receiver.framing import FrameDecoder, encode


def test_random_bytes_never_crash():
    rnd = random.Random(1234)
    d = FrameDecoder()
    for _ in range(5000):
        for kind, data in d.feed(os.urandom(rnd.randint(1, 64))):
            assert kind in ("ok", "error")


def test_valid_frames_survive_noise():
    rnd = random.Random(99)
    d = FrameDecoder()
    good = [f'{{"n":{i}}}'.encode() for i in range(200)]
    stream = b"".join(bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 20))) + encode(g) for g in good)
    ok = [p for k, p in d.feed(stream) if k == "ok"]
    assert set(good).issubset(set(ok))
```

**6. Configuration.** `pytest.ini` with `--junitxml=results/<suite>.xml`.

**7. Installation commands.** `pip install pytest requests`; `npm ci` for Playwright suites.

**8. Run commands.**

```bash
python -m pytest -q --junitxml=results/unit.xml ../smart-water-main/reference/tests
python -m pytest -q --junitxml=results/security.xml security/
python tools/report.py v0.1.0
```

**9. Expected output.**

```text
wrote reports/TR-v0.1.0.md (NN/NN PASS)
```

**10. Test procedure.** The complete plan is [§46](#46-comprehensive-test-plan).

**11. Troubleshooting.** Flaky tests are **bugs**: quarantine them with an issue link, never delete them silently. Keep HIL results with the bench configuration (firmware hash, config hash, sensor serials).

**12. Git commands.**

```bash
git checkout -b test/phase-16-plan
git add tools security manual reports
git commit -m "test: execute full test plan and publish TR-v0.1.0"
git tag -a tr-v0.1.0 -m "Test report v0.1.0"
```

**13. Commit message.** `test: execute full test plan and publish TR-v0.1.0`

**14. README update.** Link the latest test report from §46 and from each repository's README. Mark Phase 16 ✅.

---

## Phase 17: Documentation

**1. Objective.** Finalise documentation across all repositories so the system can be built, deployed, operated, maintained and audited by someone who didn't build it, and review every claim against test evidence.

**2. Architecture.**

```text
smart-water-main (authoritative)          subsystem repos (specific)
 ├ README.md (this) ◄── readme_src/*.md    ├ README.md (build/run/test)
 ├ architecture/*.md                       ├ docs/*.md
 ├ documentation/*.md                      └ CHANGELOG.md
 └ diagrams/*.png ◄── scripts/generate_diagrams.py
```

**3. Folder structure.** §23.3.

**4. Required files.** `architecture/{system-architecture,data-flow,power-flow,communication-flow}.md`; `documentation/{deployment,calibration,troubleshooting,maintenance}.md`; `repository-links.md`.

**5. Complete code.** `scripts/generate_diagrams.py` (26 figures) and `scripts/build_readme.py`, both in this repository. Claim-review checklist:

```markdown
## Claim review (complete before each release)
- [ ] No text claims contaminant detection by pH/TDS/EC/turbidity
- [ ] No IP rating / certification / "military-grade" claim
- [ ] Every "supported" feature links to a PASS test ID
- [ ] Every SIMULATED/ILLUSTRATIVE figure is labelled
- [ ] Every electrical value is measured, from a datasheet (cited), or marked TBD / CONFIGURABLE
- [ ] Limitations (§48) reviewed and updated
- [ ] Prototype vs industrial table (§47) reviewed
```

**6. Configuration.** `requirements-docs.txt`: `matplotlib>=3.7`, `numpy>=1.24`, `pytest>=7`.

**7. Installation commands.** `pip install -r requirements-docs.txt`

**8. Run commands.**

```bash
python scripts/generate_diagrams.py && python scripts/build_readme.py
```

**9. Expected output.** `README.md written (N lines ...)` and `All image references resolve.`

**10. Test procedure.**

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| DOC-01 | Fresh clone | Regenerate figures + README | Byte-identical figures (deterministic seeds); build succeeds | _record_ | _ |
| DOC-02 | README | Link checker (`lychee`) | No broken internal links | _record_ | _ |
| DOC-03 | New team member | Follow §42 on a bench node | Node reaches READY FOR DEPLOYMENT without asking the authors | _record_ | _ |
| DOC-04 | Claim review | Checklist above | All boxes ticked | _record_ | _ |

**11. Troubleshooting.** If figures differ between machines, pin the matplotlib version and fonts in `requirements-docs.txt`.

**12. Git commands.**

```bash
git checkout -b docs/phase-17-final
git add README.md readme_src architecture documentation diagrams scripts repository-links.md
git commit -m "docs: complete system documentation, regenerate figures, claim review"
```

**13. Commit message.** `docs: complete system documentation, regenerate figures, claim review`

**14. README update.** This document. Mark Phase 17 ✅.

---

# PART F: FIELD OPERATIONS

## 42. Verified Sensor Deployment

### 42.1 Workflow

<p align="center"><img src="diagrams/06_deployment_workflow.png" alt="Deployment workflow" width="100%"/></p>

<sub>Figure 42.1: 12-gate verified deployment workflow.</sub>

### 42.2 Node deployment states

```text
PROVISIONED ──► COMMISSIONING ──► READY_FOR_DEPLOYMENT ──► DEPLOYED_VERIFIED
      ▲               │ gate fail                               │
      │               └──────► (fix, repeat gate)               ├──► MAINTENANCE ──► (re-run affected gates) ──► DEPLOYED_VERIFIED
      └───────────────────────────────────────────────────────  └──► RETIRED
```

Every state change is an audited `NODE_STATE_CHANGE` event, including who, when and the checklist reference.

### 42.3 Deployment checklist

> Print this or use the debugger's guided mode. **All 12 gates must pass.** Record actual values, not just ticks.

**Site:** ____________  **Node ID:** SWN-______  **Gateway:** GW-____  **Date/time (UTC):** ____________
**Engineer:** ____________  **Firmware:** ________  **Edge version:** ________  **Config hash:** ________

| Gate | Step | Procedure | Acceptance criterion | Measured / observed | PASS / FAIL | Initials |
|:-:|---|---|---|---|:-:|:-:|
| 1 | **Install sensor** | Mount the probes in the guard pipe/flow cell at the specified depth; connect waterproof connectors; label cables | Probes fully immersed; no air pockets; labels match registry | | | |
| 2 | **Verify sensor connection** | `swdebug sensors SWN-xxxx` | All 5 sensors `CONNECTED`, present_ratio = 1.0 | | | |
| 3 | **Perform calibration/verification** | Run §43 procedures for pH, EC/TDS, turbidity; verify temperature against a reference thermometer | Each within its acceptance tolerance (TBD per sensor); cal versions recorded | | | |
| 4 | **Check baseline reading** | Log ≥ 30 min in site water | Noise σ < configured limit; no RNG/HLT/CON hits; values plausible for the site | | | |
| 5 | **Verify communication** | Check link counters | ESP32 → Pi frames ACKed; CRC error rate < 1%; 0 seq gaps | | | |
| 6 | **Verify antenna/network** | Modem registration + signal (if used); router uplink | Registered; CSQ ≥ `csq_min`; test upload OK | | | |
| 7 | **Verify timestamp** | Compare device ts, Pi ts and a reference clock | Skew < `max_clock_skew_s` (target ≪); RTC backup battery OK | | | |
| 8 | **Verify Raspberry Pi reception** | `swdebug status` | Last reading < 1 interval old; services active | | | |
| 9 | **Verify data storage** | Query `raw_readings`; `verify-chain` | Rows present; chain OK; integrity_check ok | | | |
| 10 | **Verify Firebase synchronisation** | Compare local/remote counts for the last hour | Equal; outbox pending = 0 | | | |
| 11 | **Run system diagnostic** | `swdebug diag run --full`; attach report | 0 FAIL; WARNs justified in writing | | | |
| 12 | **Mark READY FOR DEPLOYMENT** | Supervisor reviews checklist | All gates PASS → state `READY_FOR_DEPLOYMENT`, then after the observation period (TBD, e.g. 24 h) → `DEPLOYED_VERIFIED` | | | |

**Power checks (performed alongside gates 1–11):**

| Check | Criterion | Observed | PASS/FAIL |
|---|---|---|:-:|
| Battery polarity & voltage | Correct polarity; voltage in expected range for the chemistry | | |
| Solar channel | Non-zero in daylight; controller indicates charging | | |
| Wind channel | Non-zero when turbine spins; dump load wired; brake switch tested | | |
| LVD | Configured; threshold recorded | | |
| Fuses | Correct ratings installed per the wiring schedule | | |
| Earthing / bonding | Continuity verified | | |

**Physical checks:**

| Check | Observed | PASS/FAIL |
|---|---|:-:|
| Enclosure lid gasket seated, fasteners torqued | | |
| Cable glands tightened; unused glands blanked | | |
| Drip loops present | | |
| Breather vent + desiccant installed | | |
| Antenna mounted, surge arrestor earthed | | |
| Mast secure; turbine clearance adequate | | |
| Photos taken (enclosure interior, probes, mast) and attached | | |

**Sign-off:** Engineer ____________  Supervisor ____________  → Node state: **DEPLOYED / VERIFIED** ☐

### 42.4 Automated commissioning helper

```python
# smart-water-debugger/cli/swdebug/commission.py (excerpt)
GATES = [
    ("G2", "sensor connection", lambda c, n: all(s["state"] == "CONNECTED" for s in c.get("/api/v1/sensors", node=n).values())),
    ("G8", "pi reception",      lambda c, n: c.get("/api/v1/status")["last_reading"] is not None),
    ("G9", "data storage",      lambda c, n: c.post("/api/v1/chain/verify", node=n)["ok"]),
    ("G10","firebase sync",     lambda c, n: c.get("/api/v1/status")["outbox_pending"] == 0),
]

def run(client, node):
    results = []
    for gid, name, check in GATES:
        try:
            ok = bool(check(client, node))
        except Exception as e:           # a crashed check is a FAIL, not a skip
            ok, name = False, f"{name} ({e})"
        results.append((gid, name, "PASS" if ok else "FAIL"))
    return results   # manual gates (1,3,4,5,6,7,11,12) are recorded by the engineer in the checklist
```

---

## 43. Calibration Procedures

> Calibration tolerances, intervals and reference-solution values are `TBD / CONFIGURABLE` and must follow the **sensor manufacturer's instructions**. Use in-date, traceable reference solutions. Record the lot number and expiry date.

### 43.1 General rules

1. Calibrate at (or compensate to) a known temperature and record the temperature.
2. Rinse the probe with distilled/deionised water between solutions, and blot gently. Don't wipe glass pH bulbs.
3. Let the reading stabilise (criterion: change < `stability_delta` over `stability_s`).
4. Every calibration creates a new **calibration version**. Old coefficients stay in the audit log.
5. Readings taken with the previous calibration are **not** recomputed in place. If needed, a correction annotation is filed (§10.5).

### 43.2 pH (two- or three-point)

| Step | Action |
|---|---|
| 1 | Start a calibration session: `swdebug calibrate ph --points 2` (audited; requires SERVICE role) |
| 2 | Immerse in buffer A (e.g. pH 7.00): wait for stability → capture mV |
| 3 | Rinse; immerse in buffer B (e.g. pH 4.00 or 10.00): wait → capture mV |
| 4 | Firmware computes slope/offset (`Calibration::solveTwoPoint`) |
| 5 | Check slope against the expected electrode sensitivity (manufacturer guidance); reject if out of range |
| 6 | Verify in a third buffer if available: reading within tolerance |
| 7 | Store → cal version increments → `CALIBRATION_APPLIED` audit event (lots, temperature, mV, coefficients) |

### 43.3 EC / TDS

| Step | Action |
|---|---|
| 1 | Use a conductivity standard near the site's expected range |
| 2 | Confirm temperature compensation is enabled and the temperature sensor is valid |
| 3 | Capture mV at the standard → compute the coefficient; optionally two-point |
| 4 | TDS: determine factor k from EC (site-specific; ideally from paired lab TDS measurements). Record `tds_ec_factor` |
| 5 | Verify: CON-001 must not trigger on the standard |

### 43.4 Turbidity

| Step | Action |
|---|---|
| 1 | Low-cost optical modules are often **not** nephelometric. Treat their output as a relative index unless calibrated against formazin/equivalent standards |
| 2 | Zero point: particle-free (filtered) water in a clean, dark vessel |
| 3 | Span point(s): turbidity standard(s) if available |
| 4 | Record whether the sensor reports **calibrated NTU** or a **relative index**. The dashboard unit label must reflect this |

### 43.5 Temperature

Compare with a reference thermometer in a stirred water bath at two temperatures. Record the offset and apply it if it exceeds the tolerance.

### 43.6 Calibration record (audit payload)

```json
{
  "action": "CALIBRATION_APPLIED",
  "target_ref": "nodes/SWN-0001/sensors/PH-01",
  "previous_value": { "slope": -0.00592, "offset": 15.36, "version": 3 },
  "new_value":      { "slope": -0.00588, "offset": 15.29, "version": 4 },
  "reason": "Scheduled 30-day calibration",
  "evidence": {
    "points": [ { "ref": 7.00, "mv": 1412.2, "temp_c": 25.1, "lot": "B7-2291", "expiry": "2027-03" },
                { "ref": 4.00, "mv": 1922.6, "temp_c": 25.0, "lot": "B4-1180", "expiry": "2027-01" } ],
    "verification": { "ref": 10.00, "reading": 9.97 }
  },
  "actor_uid": "service:u_31a…", "actor_role": "SERVICE"
}
```

---

## 44. Maintenance

### 44.1 Schedule (initial proposal; adjust from field experience)

| Interval | Task | Role | Debugger check after |
|---|---|---|---|
| Weekly (remote) | Review alerts, verification failure rate, queue depth, power trends | Engineer | — |
| Monthly (site) | Visual inspection; clean probes; check glands, vent, desiccant; clean PV panel | Engineer | `diag run` |
| Per sensor calibration interval (TBD, e.g. 2–4 weeks for pH) | Calibrate per §43 | Service | `sensors`, cal age |
| Quarterly | Inspect turbine (blades, bearings, fasteners) with the turbine **braked**; check mast/guys; verify LVD; torque terminals | Service | power panel |
| Quarterly | Verify hash chain; compare local/cloud counts; review audit log | Supervisor | `verify-chain` |
| Semi-annual | Replace desiccant; inspect battery (swelling, terminals, capacity test if supported) | Service | battery check |
| Annual / per manufacturer | Replace pH electrode (typical lifetime is limited), other consumables | Service | full commissioning gates 2–4 |
| After storms | Site inspection: physical damage, water ingress, antenna, surge arrestor | Engineer | full diag |

### 44.2 Maintenance action logging

Maintenance actions are logged through the dashboard/debugger (`POST /api/v1/maintenance` or the Firestore `maintenance` task update). A maintenance log entry **never** modifies readings. While a sensor is out of the water for cleaning, the engineer sets **maintenance mode** for that sensor. Readings during that window are still stored, but flagged `mode: MAINTENANCE` in the event log, so the resulting MIS-001/ROC-001 hits are explainable.

### 44.3 Spare-parts kit (recommended)

| Item | Qty |
|---|:-:|
| pH probe (pre-conditioned, in storage solution) | 1 |
| Conductivity/TDS probe | 1 |
| Temperature probe | 1 |
| Calibration buffers/standards (in date) | 1 set |
| Fuses (each rating used) | 5 each |
| Desiccant packs | 4 |
| Cable glands + blanking plugs | 4 |
| Programmed spare ESP32 board (unprovisioned) | 1 |
| Spare SSD/SD with edge image | 1 |
| Self-amalgamating tape, cable ties (UV-rated) | — |

---

## 45. Troubleshooting Guide

### 45.1 Symptom index

| ID | Symptom | Likely causes | Checks | Resolution |
|---|---|---|---|---|
| **TSG-S01** | One sensor `null` (MIS-001) | Connector loose/corroded; cable damage; sensor board failure | `swdebug sensors`; reseat connector; measure mV at the board | Clean/replace connector; replace probe |
| **TSG-S02** | Out-of-range value (RNG-001) | Wiring short/open; wrong range config; probe failure | Raw mV; compare config to datasheet | Fix wiring; correct config (audited); replace |
| **TSG-S03** | Temperature `null` | 1-Wire pull-up missing; cable | Resistance; continuity | Repair |
| **TSG-S04** | Stuck value (HLT-001) | Frozen driver; railed ADC; very stable water | Raw mV varies? | Reboot node; if legitimate, tune window |
| **TSG-S05** | TDS/EC disagree (CON-001) | Fouled probe; wrong k; interference | Clean; check excitation groups | Clean/recalibrate; set k |
| **TSG-S06** | High noise | EMI; ground loop; poor shielding | Noise σ; switch modem/Pi off to compare | Shielding, isolation, cable routing |
| **TSG-S07** | Frequent ROC-001 | Air bubbles; flow surges; loose probe | Visual; probe holder | Re-seat probe; flow cell; tune limits (audited) |
| **TSG-N01** | Node offline | Power; ESP32 crash; UART cable | LEDs; battery V; serial console | Restore power; reflash; replace cable |
| **TSG-N02** | Frequent resets | Brownout (modem TX); watchdog | `reset_reason` | Supply/bulk capacitance; fix blocking code |
| **TSG-N03** | Firmware mismatch | Partial update | `fw` in frames vs expected | Reflash the release build |
| **TSG-N04** | Everything INVALID (TS-*) | RTC lost time | Device vs Pi time | Replace RTC battery; resync time |
| **TSG-C01** | CRC errors | Noise; long cable; baud | Counters | Shield/twist; RS-485; baud check |
| **TSG-C02** | Seq gaps (COM-001) | Buffer overflow; reboot mid-send | ring buffer dropped count | Larger buffer; investigate resets |
| **TSG-C03** | Cloud not syncing | Internet down; auth error; clock | `sw-sync` logs; `last_error` | Restore network; rotate key; fix time |
| **TSG-C04** | Modem not registered | No coverage; 2G sunset; SIM/APN; antenna | AT+CREG?, AT+CSQ | Relocate antenna; LTE module; APN |
| **TSG-E01** | Service inactive | Crash loop; config error | `journalctl -u sw-*` | Fix config; restart |
| **TSG-E02** | Disk nearly full | Archive not running | `df -h` | Run archive; larger SSD |
| **TSG-E03** | DB integrity error | Power loss on poor media | `PRAGMA integrity_check` | Restore from cloud + archive; replace media |
| **TSG-E04** | Pi overheating | Sun on enclosure; no shade | CPU temp | Sun shield; reduce load; heat-sinking |
| **TSG-P01** | Battery low repeatedly | Undersized harvest; failing battery; high load | Power history; energy budget | Clean panel; resize; replace battery; shed loads |
| **TSG-P02** | No solar in daylight | Panel disconnected/shaded; controller fault | V/I at panel and controller | Repair/clean |
| **TSG-P03** | No wind output in wind | Brake engaged; rectifier/controller fault | AC/DC voltages | Release brake; repair |
| **TSG-P04** | Brownout resets at night | Battery sag under load | Battery V under load | Battery health; thresholds |
| **TSG-D01** | High verification-failure rate | Sensor issue or mis-tuned rules | Rule histogram | Fix sensor; tune rules with audit |
| **TSG-D02** | Chain verification fails | Storage corruption or tampering | First bad record | Preserve evidence; compare with cloud; incident report |

### 45.2 Decision tree: "no data on the dashboard"

```text
No new data on dashboard?
├─ Stale banner shown?
│   ├─ YES → Edge may be fine; cloud sync issue → swdebug status (on site / VPN)
│   │         ├─ outbox_pending growing → TSG-C03
│   │         └─ last_reading old       → go to "Edge receiving?" below
│   └─ NO  → Browser/auth issue → sign out/in; check role claim
└─ Edge receiving? (swdebug status → last_reading)
    ├─ YES, recent → cloud path → TSG-C03
    └─ NO → Node alive? (LEDs, battery V)
        ├─ LEDs off → power path → TSG-P01 / fuses / LVD
        └─ LEDs on  → link → TSG-C01 / UART cable / baud / sw-receiver (TSG-E01)
```

---

## 46. Comprehensive Test Plan

<p align="center"><img src="diagrams/21_test_plan_coverage.png" alt="Test plan coverage" width="90%"/></p>

<sub>Figure 46.1: Documented test cases by suite.</sub>

> **Format.** Every test uses **INPUT → PROCESS → EXPECTED RESULT → ACTUAL RESULT → PASS/FAIL**.
> "ACTUAL" and "PASS/FAIL" are filled in during execution. Rows marked ✅ **(executed)** were run against the reference implementation in this repository. All other rows are **planned** and must be executed on hardware/emulators in Phase 16.

### 46.1 Sensor tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| SN-01 | Normal readings in reference water | Acquire 30 samples | All present; VALID; σ below limit | | |
| SN-02 | Missing sensor (never connected) | Boot + acquire | Field `null`; MIS-001; `SENSOR_DISCONNECTED` alert after N | | |
| SN-03 | Disconnected sensor (unplug while running) | Acquire | `null` within 1 cycle; alert; reconnect → recovers | | |
| SN-04 | Out-of-range value (simulated mV injection) | Verify | RNG-001; SUSPECTED_SENSOR_ERROR; raw preserved | ✅ (executed: `test_out_of_range_is_suspected_sensor_error`) | PASS |
| SN-05 | Sudden change (pH 7.1 → 10.5 in 5 min) | Verify | ROC-001; ABNORMAL | ✅ (executed: `test_sudden_change_flagged`) | PASS |
| SN-06 | Cross-interference (TDS & EC powered together vs sequentially) | Compare | Difference < tolerance with grouping enabled | | |

### 46.2 Communication tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| CM-01 | Network available | Sync | Docs delivered < `stale_after_s` | | |
| CM-02 | Network unavailable 13 h | Queue | No loss; outbox grows; stale banner | ✅ (executed in simulation, Fig. 15.2; unit `test_offline_then_recover_no_duplicates`) | PASS (sim) |
| CM-03 | Firebase unavailable (503/timeout injected) | Sync | Backoff; no loss; recovery | | |
| CM-04 | Recovery after outage | Sync | Queue drains; local count = remote count | | |
| CM-05 | Duplicate prevention (replay frame + retry batch) | Store + sync | 1 local row, 1 remote doc | ✅ (executed: `test_duplicate_record_rejected`; P7 `test_retry_after_partial_success_is_idempotent`) | PASS |

### 46.3 Raspberry Pi tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| PI-01 | Raw frames over UART | Receive | Parsed, `received_ts` stamped, ACK sent | | |
| PI-02 | Malformed / partial / wrong-type messages | Validate | FMT-001/002/005; INVALID; payload logged as event | ✅ (executed: FMT tests) | PASS |
| PI-03 | 1000 frames | Store | 1000 rows; chain valid; UPDATE/DELETE blocked | | |
| PI-04 | Mixed-fault stream (24 h simulated) | Verify | All injected faults detected by the expected rule | ✅ (executed: `test_simulated_stream_triggers_expected_rules`) | PASS |
| PI-05 | Network down | Sync queue | Outbox PENDING rows = new records; survive reboot | | |

### 46.4 Verification-rule tests (reference implementation, executed)

| ID | Rule | INPUT | EXPECTED | ACTUAL | PASS/FAIL |
|---|---|---|---|---|:-:|
| VR-01 | — | Nominal reading | VALID / PASSED | VALID / PASSED | ✅ PASS |
| VR-02 | FMT-001 | `"garbage"` | INVALID | INVALID | ✅ PASS |
| VR-03 | FMT-002 | missing `timestamp` | INVALID | INVALID | ✅ PASS |
| VR-04 | FMT-005 | pH as string | INVALID | INVALID | ✅ PASS |
| VR-05 | RNG-001 | pH 15.2 | SUSPECTED_SENSOR_ERROR | SUSPECTED_SENSOR_ERROR | ✅ PASS |
| VR-06 | MIS-001 | turbidity null | MIS-001 hit | MIS-001 hit | ✅ PASS |
| VR-07 | ROC-001 | +3.4 pH / 5 min | ABNORMAL | ABNORMAL | ✅ PASS |
| VR-08 | TS-001 | naive timestamp | INVALID | INVALID | ✅ PASS |
| VR-09 | TS-002 | +60 min future | INVALID | INVALID | ✅ PASS |
| VR-10 | DUP-001 | repeated record_id | INVALID | INVALID | ✅ PASS |
| VR-11 | NID-001 | unregistered node | INVALID | INVALID | ✅ PASS |
| VR-12 | COM-001 | seq 1 → 5 | COMMUNICATION_ERROR | COMMUNICATION_ERROR | ✅ PASS |
| VR-13 | HLT-001 | identical ×6 | HLT-001 hit | HLT-001 hit | ✅ PASS |
| VR-14 | CON-001 | TDS 400 vs EC 420 (k 0.5) | CON-001 hit | CON-001 hit | ✅ PASS |
| VR-15 | ABN-001 | pH 5.0 with/without band | only when configured | only when configured | ✅ PASS |
| VR-16 | invariant | any | raw input unchanged | unchanged | ✅ PASS |
| VR-17 | integrity | same msg twice | identical SHA-256 | identical | ✅ PASS |

### 46.5 Security tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| SC-01 | Unauthorised access: no token / wrong token / unauthenticated Firestore read | Request | 401 / PERMISSION_DENIED | | |
| SC-02 | Data modification attempt: update/delete reading as each role; SQL UPDATE on edge | Request / SQL | Denied at every layer; attempt logged | (edge SQL: executed in P4 unit tests) | |
| SC-03 | Invalid input: fuzzed frames, oversized payload, script in ack note | Receive / UI | No crash; rejected or escaped; ack note length-limited | | |
| SC-04 | Audit logging: acknowledge alert, change config, apply calibration | Action | Audit entry with uid, role, server ts, prev/new, reason; not editable | | |

### 46.6 Power tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| PW-01 | Solar available | Measure | Solar V/I/P > 0; source contains SOLAR | | |
| PW-02 | Solar unavailable (daylight, covered) | Observe | `SOLAR_UNAVAILABLE` after debounce | | |
| PW-03 | Wind available | Measure | Wind V/I/P > 0; source contains WIND | | |
| PW-04 | Wind unavailable (braked/calm) | Observe | `WIND_UNAVAILABLE` after debounce | | |
| PW-05 | Both available | Classify | SOLAR+WIND; CHARGING | (classifier unit test) | |
| PW-06 | Both unavailable | Classify | BATTERY; DISCHARGING | (classifier unit test) | |
| PW-07 | Battery backup (renewable < load) | Observe | RENEWABLE+BATTERY or BATTERY; system keeps running | | |
| PW-08 | Low battery | Discharge | `BATTERY_LOW`; LOW-POWER; P4 off | | |
| PW-09 | Critical battery | Discharge | `BATTERY_CRITICAL`; Pi graceful shutdown; P1 continues | | |

### 46.7 Mode tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| MD-01 | Normal | 1 h run | ~12 samples at 300 s; NORMAL | | |
| MD-02 | Low-power | SoC below enter | Deep sleep cycle; burst uplink | | |
| MD-03 | Emergency | Configured trigger, network down | Increased rate; local alert; stored; sent after reconnect | | |

### 46.8 Integration / end-to-end tests

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| IT-01 … IT-08 | See Phase 15 | | | | |

### 46.9 Environmental & enclosure tests (future / pilot)

> These are **informal engineering checks**, not certification tests. They don't establish an IP rating.

| ID | INPUT | PROCESS | EXPECTED RESULT | ACTUAL RESULT | PASS/FAIL |
|---|---|---|---|---|:-:|
| EN-01 | Garden-hose spray, 10 min, all faces | Inspect inside | No water inside (informal) | | |
| EN-02 | Enclosure in direct sun, 1 day | Log internal temp | Within component ratings (TBD) | | |
| EN-03 | Humidity logging, 2 weeks | Internal RH trend | No sustained condensation | | |
| EN-04 | 30-day outdoor pilot | Full system | KPIs met; inspection report | | |
