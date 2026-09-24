---

## Phase 6: Offline Queue

**1. Objective.** Guarantee that every stored record (raw + result), event, power sample and audit entry is queued for cloud delivery, survives reboots, and can never be enqueued twice.

**2. Architecture.**

```text
Pipeline ─► Outbox.enqueue(collection, doc_id, payload)
              INSERT OR IGNORE INTO sync_outbox  (UNIQUE collection+doc_id)
              state = PENDING, next_attempt_ts = now
SyncEngine (Phase 7) ─► reads PENDING due rows ─► ACKED / deferred with backoff
Health ─► queue depth, oldest pending age → debugger + events
```

**3. Folder structure.** `src/swedge/sync/outbox.py`, `tests/test_outbox.py`.

**4. Required files.** `outbox.py`, the `sync_outbox` table (see §10.4), and a health check for queue depth.

**5. Complete code.**

```python
# swedge/sync/outbox.py
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Outbox:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    def enqueue(self, collection: str, doc_id: str, payload: dict) -> bool:
        """Returns True if newly queued, False if already present (idempotent)."""
        cur = self.con.execute(
            "INSERT OR IGNORE INTO sync_outbox (collection, doc_id, payload_json, state, attempts, "
            "next_attempt_ts, created_ts) VALUES (?,?,?,'PENDING',0,?,?)",
            (collection, doc_id, json.dumps(payload, sort_keys=True, default=str), _now(), _now()),
        )
        return cur.rowcount == 1

    def depth(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM sync_outbox WHERE state='PENDING'").fetchone()[0]

    def oldest_pending_age_s(self) -> float | None:
        row = self.con.execute(
            "SELECT MIN(created_ts) FROM sync_outbox WHERE state='PENDING'").fetchone()
        if not row or row[0] is None:
            return None
        return (datetime.now(timezone.utc) - datetime.fromisoformat(row[0])).total_seconds()

    def purge_acked(self, older_than_days: int = 7) -> int:
        """Operational cleanup of DELIVERY STATE only (evidence tables are untouched)."""
        cur = self.con.execute(
            "DELETE FROM sync_outbox WHERE state='ACKED' AND created_ts < datetime('now', ?)",
            (f"-{older_than_days} days",),
        )
        return cur.rowcount
```

**6. Configuration.** `sync.batch_size`, `sync.stale_after_s`, and the queue-depth alert threshold `health.outbox_warn_depth` (`TBD / CONFIGURABLE`, based on storage).

**7. Installation commands.** None beyond Phase 4.

**8. Run commands.**

```bash
python -m pytest -q tests/test_outbox.py
swedge-admin outbox --summary
```

**9. Expected output.**

```text
outbox: PENDING=0  SENT=0  ACKED=12447  DEAD=0  oldest_pending=—
```

**10. Test procedure.**

```python
# tests/test_outbox.py
from swedge.storage.db import connect
from swedge.sync.outbox import Outbox

def test_enqueue_idempotent(tmp_path):
    ob = Outbox(connect(str(tmp_path / "o.db")))
    assert ob.enqueue("readings", "R1", {"a": 1}) is True
    assert ob.enqueue("readings", "R1", {"a": 1}) is False
    assert ob.depth() == 1

def test_survives_reconnect(tmp_path):
    p = str(tmp_path / "o.db")
    Outbox(connect(p)).enqueue("readings", "R1", {})
    assert Outbox(connect(p)).depth() == 1          # simulated reboot

def test_same_doc_different_collection_allowed(tmp_path):
    ob = Outbox(connect(str(tmp_path / "o.db")))
    assert ob.enqueue("readings", "X", {}) and ob.enqueue("power", "X", {})
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P6-T1 | Network unplugged, 24 h of frames | Observe outbox | depth = frames received; no loss | _record_ | _ |
| P6-T2 | Reboot Pi mid-outage | Check depth after boot | Unchanged | _record_ | _ |
| P6-T3 | Same record enqueued twice | — | depth +1 only | _record_ | _ |
| P6-T4 | pytest | — | 3/3 pass | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| Queue grows while online | Sync service stopped or auth error | `systemctl status sw-sync`; debugger comm panel |
| Queue never shrinks after reconnect | `next_attempt_ts` far in the future (long backoff) | `swedge-admin outbox --retry-now` (audited) |
| Disk usage high | Many ACKED rows retained | `purge_acked` job (delivery state only) |

**12. Git commands.**

```bash
git checkout -b feat/phase-6-outbox
git add src/swedge/sync/outbox.py tests/test_outbox.py
git commit -m "feat(sync): add durable idempotent outbox queue for offline-first operation"
```

**13. Commit message.** `feat(sync): add durable idempotent outbox queue for offline-first operation`

**14. README update.** Add an "Offline-first" section linking to §15. Mark Phase 6 ✅.

---

## Phase 7: Firebase Synchronisation

**1. Objective.** Deliver queued data to Firestore with **exactly-once storage semantics** (at-least-once delivery + idempotent document IDs), backoff, auth-error handling, and Security Rules that make raw data immutable in the cloud.

**2. Architecture.** See §15.2 (sequence) and §16 (collections, rules).

**3. Folder structure.** Edge: `src/swedge/sync/{engine.py, firestore_client.py}`. Firebase repo: `firestore.rules`, `firestore.indexes.json`, `functions/src/*`, `tests/rules.test.ts`.

**4. Required files.** `engine.py` (§15.5), `firestore_client.py`, `firestore.rules` (§16.3), `audit.ts` (§16.4), `rules.test.ts`.

**5. Complete code.**

```python
# swedge/sync/firestore_client.py
from __future__ import annotations

import logging

from google.api_core import exceptions as gexc
import firebase_admin
from firebase_admin import credentials, firestore

from .engine import CloudAuthError, CloudUnavailable

log = logging.getLogger("swedge.firestore")


class FirestoreClient:
    """Create-if-absent semantics: ALREADY_EXISTS is success (idempotent)."""

    def __init__(self, project_id: str):
        # Credentials come from GOOGLE_APPLICATION_CREDENTIALS (file outside the repo).
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": project_id})
        self.db = firestore.client()

    def upsert_many(self, docs):
        try:
            for collection, doc_id, payload in docs:
                ref = self.db.collection(collection).document(doc_id)
                try:
                    ref.create(payload)                     # fails if exists → no overwrite
                except gexc.AlreadyExists:
                    log.debug("exists: %s/%s", collection, doc_id)
        except (gexc.Unauthenticated, gexc.PermissionDenied) as e:
            raise CloudAuthError(str(e)) from e
        except (gexc.ServiceUnavailable, gexc.DeadlineExceeded, gexc.InternalServerError,
                gexc.TooManyRequests, ConnectionError, OSError) as e:
            raise CloudUnavailable(str(e)) from e
```

> **Why `create()` instead of `set()`?** `set()` would overwrite an existing document. If a buggy node reused a record ID, `set()` would silently replace cloud history. `create()` refuses, and the conflict shows up in the debugger as a `SYNC_CONFLICT` event if the payload hash differs.

> **Performance note.** Per-document `create()` calls are simple and safe. For higher throughput, use `BulkWriter` with the same create semantics and per-document error handling.

```typescript
// smart-water-firebase/tests/rules.test.ts
import { initializeTestEnvironment, assertFails, assertSucceeds, RulesTestEnvironment } from "@firebase/rules-unit-testing";
import { readFileSync } from "fs";
import { doc, getDoc, setDoc, updateDoc, deleteDoc, serverTimestamp } from "firebase/firestore";

let env: RulesTestEnvironment;

beforeAll(async () => {
  env = await initializeTestEnvironment({
    projectId: "demo-smart-water",
    firestore: { rules: readFileSync("firestore.rules", "utf8") },
  });
  await env.withSecurityRulesDisabled(async (ctx) => {
    await setDoc(doc(ctx.firestore(), "readings/R1"), { node_id: "SWN-0001", raw: { ph: 7.1 } });
    await setDoc(doc(ctx.firestore(), "alerts/A1"), { status: "RAISED", node_id: "SWN-0001" });
    await setDoc(doc(ctx.firestore(), "audit/X1"), { action: "TEST" });
  });
});
afterAll(() => env.cleanup());

const as = (role: string) => env.authenticatedContext(`u_${role}`, { role }).firestore();

test("engineer can read readings", async () => {
  await assertSucceeds(getDoc(doc(as("engineer"), "readings/R1")));
});
test("unauthenticated cannot read", async () => {
  await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), "readings/R1")));
});
test("nobody can modify a reading — not even admin", async () => {
  for (const r of ["engineer", "service", "supervisor", "admin"]) {
    await assertFails(updateDoc(doc(as(r), "readings/R1"), { "raw.ph": 6.5 }));
    await assertFails(deleteDoc(doc(as(r), "readings/R1")));
  }
});
test("client cannot create readings", async () => {
  await assertFails(setDoc(doc(as("admin"), "readings/R2"), { raw: { ph: 7 } }));
});
test("engineer can acknowledge alert with own uid only", async () => {
  const db = as("engineer");
  await assertFails(updateDoc(doc(db, "alerts/A1"), { status: "ACKNOWLEDGED", ack: { by: "someone_else", ts: serverTimestamp() } }));
  await assertSucceeds(updateDoc(doc(db, "alerts/A1"), { status: "ACKNOWLEDGED", ack: { by: "u_engineer", ts: serverTimestamp() } }));
});
test("engineer cannot change alert severity", async () => {
  await assertFails(updateDoc(doc(as("engineer"), "alerts/A1"), { severity: "INFO" }));
});
test("audit is not writable by any client", async () => {
  await assertFails(updateDoc(doc(as("admin"), "audit/X1"), { action: "FORGED" }));
  await assertFails(setDoc(doc(as("admin"), "audit/X2"), { action: "FORGED" }));
});
test("engineer cannot read audit", async () => {
  await assertFails(getDoc(doc(as("engineer"), "audit/X1")));
});
```

```typescript
// smart-water-firebase/scripts/set-role.ts  — run by an administrator locally, never in the browser
import { initializeApp, applicationDefault } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

const [uid, role] = process.argv.slice(2);
const allowed = ["engineer", "service", "supervisor", "admin"];
if (!uid || !allowed.includes(role)) {
  console.error(`usage: set-role <uid> <${allowed.join("|")}>`);
  process.exit(1);
}
initializeApp({ credential: applicationDefault() });
await getAuth().setCustomUserClaims(uid, { role });
console.log(`role ${role} set for ${uid} — user must sign out/in to refresh token`);
```

**6. Configuration.**

```bash
# /etc/smart-water/edge.env  (mode 0600, NOT in Git)
GOOGLE_APPLICATION_CREDENTIALS=/etc/smart-water/sa.json
FIREBASE_PROJECT_ID=your-project-id
```

Service-account role: grant the **minimum** needed (Firestore writes for the project). Don't use an Owner/Editor key on a field device.

**7. Installation commands.**

```bash
# Edge
pip install firebase-admin
sudo install -m 0600 -o swedge -g swedge sa.json /etc/smart-water/sa.json
# Firebase repo
npm i -g firebase-tools
cd smart-water-firebase && npm ci && (cd functions && npm ci)
firebase login
```

**8. Run commands.**

```bash
# Rules tests against the local emulator (no real project needed)
firebase emulators:exec --only firestore "npx jest tests/rules.test.ts"
# Deploy (after review)
firebase deploy --only firestore:rules,firestore:indexes,functions
# Edge
sudo systemctl enable --now sw-sync
journalctl -u sw-sync -f
```

**9. Expected output.**

```text
PASS tests/rules.test.ts
  ✓ engineer can read readings
  ✓ unauthenticated cannot read
  ✓ nobody can modify a reading — not even admin
  ✓ client cannot create readings
  ✓ engineer can acknowledge alert with own uid only
  ✓ engineer cannot change alert severity
  ✓ audit is not writable by any client
  ✓ engineer cannot read audit
Tests: 8 passed, 8 total

sw-sync[812]: INFO swedge.sync synced 100 docs
sw-sync[812]: WARNING swedge.sync cloud unavailable (100 queued): 503 Service Unavailable
sw-sync[812]: INFO swedge.sync synced 100 docs
```

**10. Test procedure.**

```python
# tests/test_sync_engine.py
import json
from swedge.storage.db import connect
from swedge.sync.outbox import Outbox
from swedge.sync.engine import SyncEngine, CloudUnavailable

CFG = {"batch_size": 50, "base_delay_s": 0, "max_delay_s": 0, "jitter_s": 0}

class FakeCloud:
    def __init__(self): self.store, self.up = {}, True
    def upsert_many(self, docs):
        if not self.up: raise CloudUnavailable("down")
        for c, i, p in docs: self.store.setdefault((c, i), p)     # create-if-absent

def test_offline_then_recover_no_duplicates(tmp_path):
    con = connect(str(tmp_path / "s.db")); ob = Outbox(con); cloud = FakeCloud()
    for i in range(120): ob.enqueue("readings", f"R{i}", {"i": i})
    cloud.up = False
    eng = SyncEngine(con, cloud, CFG)
    assert eng.run_once() == 0 and ob.depth() == 120
    cloud.up = True
    while eng.run_once(): pass
    assert ob.depth() == 0 and len(cloud.store) == 120

def test_retry_after_partial_success_is_idempotent(tmp_path):
    con = connect(str(tmp_path / "s.db")); ob = Outbox(con); cloud = FakeCloud()
    ob.enqueue("readings", "R1", {"v": 1})
    cloud.store[("readings", "R1")] = {"v": 1}        # already delivered, ACK was lost
    SyncEngine(con, cloud, CFG).run_once()
    assert len(cloud.store) == 1 and ob.depth() == 0
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P7-T1 | Online, 1000 records | Sync | 1000 docs, outbox ACKED | _record_ | _ |
| P7-T2 | Offline 13 h, then online | Sync | All docs delivered; count matches local | _record_ | _ |
| P7-T3 | Kill sync mid-batch, restart | Sync | No duplicates; count matches | _record_ | _ |
| P7-T4 | Revoke service-account key | Sync | `CLOUD_AUTH_ERROR` event; queue grows; no data loss | _record_ | _ |
| P7-T5 | Rules emulator suite | jest | 8/8 pass | _record_ | _ |
| P7-T6 | pytest sync tests | — | 2/2 pass | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| `DefaultCredentialsError` | Env var/path wrong or file permissions | Check `EnvironmentFile`, path, `0600` owner `swedge` |
| `PERMISSION_DENIED` from the Admin SDK | Service account lacks a Firestore role | Grant the minimum Firestore write role |
| Clock-related TLS errors | Pi clock wrong at boot | Enable NTP / RTC HAT; `timedatectl` |
| Quota / cost higher than expected | Emergency mode for long periods | Review `emergency.max_duration_s`; batch; see §50 |

**12. Git commands.**

```bash
# edge
git checkout -b feat/phase-7-sync && git add src/swedge/sync tests/test_sync_engine.py && \
git commit -m "feat(sync): idempotent Firestore sync with backoff and auth-error handling"
# firebase
git checkout -b feat/phase-7-rules && git add firestore.rules firestore.indexes.json functions tests && \
git commit -m "feat(rules): immutable readings/audit, ack-only alerts, role claims, emulator tests"
```

**13. Commit message.** `feat(sync): idempotent Firestore sync with backoff and auth-error handling`

**14. README update.** In `smart-water-firebase/README.md`, add a Collections table (§16.1), a rules summary, emulator test instructions, and "How to assign roles". Mark Phase 7 ✅.

---

## Phase 8: Dashboard

**1. Objective.** Build a simple five-tab engineer dashboard (LIVE, NODES, POWER, ALERTS, HISTORY) that shows raw values with verification status and freshness, and allows **only** alert acknowledgement.

**2. Architecture.**

```text
Browser ─► Firebase Auth (email/password; MFA for admin) ─► ID token with role claim
        ─► Firestore onSnapshot(readings where node_id == X order by device_ts desc limit 1)
        ─► Firestore onSnapshot(alerts where status in [RAISED, NOTIFIED])
        ─► updateDoc(alert, {status: ACKNOWLEDGED, ack:{by: uid, ts: serverTimestamp()}})   ← only write
```

**3. Folder structure.** §18.7.

**4. Required files.** `src/services/firebase.ts`, `src/services/readings.ts`, `src/services/alerts.ts`, `src/pages/*.tsx`, `src/components/{ParamTile,StatusBadge,StaleBanner,AckButton}.tsx`, `.env.example`, tests.

**5. Complete code.**

```ts
// src/services/firebase.ts
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { initializeFirestore, persistentLocalCache } from "firebase/firestore";

const cfg = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};
for (const [k, v] of Object.entries(cfg)) if (!v) throw new Error(`Missing env VITE_FIREBASE_${k}`);

export const app = initializeApp(cfg);
export const auth = getAuth(app);
export const db = initializeFirestore(app, { localCache: persistentLocalCache() });   // tolerate flaky site internet
```

```ts
// src/services/readings.ts
import { collection, onSnapshot, orderBy, query, where, limit } from "firebase/firestore";
import { db } from "./firebase";
import type { Reading } from "./types";

export function subscribeLatest(nodeId: string, cb: (r: Reading | null) => void) {
  const q = query(collection(db, "readings"), where("node_id", "==", nodeId),
                  orderBy("device_ts", "desc"), limit(1));
  return onSnapshot(q, (s) => cb(s.empty ? null : (s.docs[0].data() as Reading)));
}
```

```ts
// src/services/alerts.ts
import { doc, updateDoc, serverTimestamp } from "firebase/firestore";
import { auth, db } from "./firebase";

export async function acknowledge(alertId: string, note: string) {
  const uid = auth.currentUser?.uid;
  if (!uid) throw new Error("Not signed in");
  const clean = note.trim().slice(0, 500);            // input validation
  await updateDoc(doc(db, "alerts", alertId), {
    status: "ACKNOWLEDGED",
    ack: { by: uid, ts: serverTimestamp(), note: clean },
  });
}
```

> **Rules alignment.** The Security Rule in §16.3 checks `request.resource.data.ack.ts == request.time` and `ack.by == request.auth.uid`. `serverTimestamp()` satisfies the first check, and the client can't forge either value.

```tsx
// src/pages/LivePage.tsx
import { useEffect, useState } from "react";
import { subscribeLatest } from "../services/readings";
import { ParamTile } from "../components/ParamTile";
import { StaleBanner } from "../components/StaleBanner";
import { RULE_TEXT } from "../alerts/plainLanguage";
import type { Reading } from "../services/types";

const PARAMS = [
  { key: "ph", label: "pH", unit: "pH" },
  { key: "turbidity_ntu", label: "Turbidity", unit: "NTU" },
  { key: "tds_ppm", label: "TDS", unit: "ppm" },
  { key: "ec_us_cm", label: "EC", unit: "µS/cm" },
  { key: "temperature_c", label: "Temperature", unit: "°C" },
] as const;

export function LivePage({ nodeId }: { nodeId: string }) {
  const [r, setR] = useState<Reading | null>(null);
  useEffect(() => subscribeLatest(nodeId, setR), [nodeId]);
  if (!r) return <p>No readings yet for {nodeId}.</p>;

  const hitsFor = (p: string) => r.verification.rules_triggered.filter((h) => h.parameter === p);
  return (
    <main>
      <StaleBanner ts={r.received_ts} staleAfterS={1800} />
      <div className="tile-grid">
        {PARAMS.map(({ key, label, unit }) => {
          const hits = hitsFor(key);
          return (
            <ParamTile key={key} label={label} unit={unit} ts={r.device_ts}
              value={r.raw[key] ?? null}
              status={hits.length ? hits[0].status : "VALID"}
              reason={hits.map((h) => `${RULE_TEXT[h.rule_id] ?? h.rule_id} (${h.rule_id})`).join("; ")} />
          );
        })}
      </div>
      <p className="meta">Node {r.node_id} · mode {r.mode} · {r.verification.verification}</p>
    </main>
  );
}
```

**6. Configuration.**

```bash
# .env.example (committed); copy to .env.local (ignored)
VITE_FIREBASE_API_KEY=
VITE_FIREBASE_AUTH_DOMAIN=
VITE_FIREBASE_PROJECT_ID=
VITE_FIREBASE_APP_ID=
VITE_STALE_AFTER_S=1800
```

**7. Installation commands.**

```bash
git clone https://github.com/YOUR-ORG/smart-water-dashboard.git && cd smart-water-dashboard
npm ci
cp .env.example .env.local   # fill in values
```

**8. Run commands.**

```bash
npm run dev -- --host 0.0.0.0      # local development
npm test                           # vitest unit tests
npx playwright test                # e2e against emulators
npm run build && firebase deploy --only hosting   # optional
```

**9. Expected output.**

```text
  VITE v5.x  ready in 412 ms
  ➜  Local:   http://localhost:5173/
 ✓ tests/unit/ParamTile.test.tsx (4)
 ✓ tests/unit/plainLanguage.test.ts (2)
 Test Files  2 passed (2)
```

**10. Test procedure.**

```tsx
// tests/unit/ParamTile.test.tsx
import { render, screen } from "@testing-library/react";
import { ParamTile } from "../../src/components/ParamTile";

test("null value renders em dash, not zero", () => {
  render(<ParamTile label="pH" value={null} unit="pH" status="SUSPECTED_SENSOR_ERROR" ts="2026-09-23T05:00:00Z" />);
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.queryByText("0")).toBeNull();
});
test("status has text label (not colour only)", () => {
  render(<ParamTile label="pH" value={7.2} unit="pH" status="ABNORMAL" ts="2026-09-23T05:00:00Z" />);
  expect(screen.getByText(/abnormal/i)).toBeInTheDocument();
});
test("no edit control exists", () => {
  render(<ParamTile label="pH" value={7.2} unit="pH" status="VALID" ts="2026-09-23T05:00:00Z" />);
  expect(screen.queryByRole("button", { name: /edit|delete/i })).toBeNull();
});
test("annotated badge shown when annotation exists", () => {
  render(<ParamTile label="pH" value={7.2} unit="pH" status="VALID" ts="2026-09-23T05:00:00Z" annotated />);
  expect(screen.getByText("annotated")).toBeInTheDocument();
});
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P8-T1 | New reading written to emulator | Observe LIVE | Tiles update < 5 s; timestamp shown | _record_ | _ |
| P8-T2 | Reading with MIS-001 on turbidity | LIVE | Turbidity "—", "Sensor not responding (MIS-001)" | _record_ | _ |
| P8-T3 | No readings for > stale threshold | LIVE | Stale banner visible | _record_ | _ |
| P8-T4 | Engineer clicks ACK | ALERTS | Alert → ACKNOWLEDGED; audit entry created by function | _record_ | _ |
| P8-T5 | Engineer tries to edit reading via devtools | Firestore | PERMISSION_DENIED | _record_ | _ |
| P8-T6 | Usability: engineer with no programming background | Task: "Is the node healthy? Which sensor has a problem?" | Correct answers < 60 s without help | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| Blank page, "Missing env" | `.env.local` not filled | Copy from `.env.example` |
| `FAILED_PRECONDITION: requires an index` | Composite index missing | Deploy `firestore.indexes.json` |
| ACK fails with permission denied | Role claim missing or stale token | `set-role`, then sign out and back in |
| Data looks old | Edge sync delayed | Check the stale banner; open debugger comm panel |

**12. Git commands.**

```bash
git checkout -b feat/phase-8-dashboard
git add src tests public .env.example package.json vite.config.ts
git commit -m "feat(dashboard): five-tab engineer dashboard with verification status, stale banner and ack-only alerts"
```

**13. Commit message.** `feat(dashboard): five-tab engineer dashboard with verification status, stale banner and ack-only alerts`

**14. README update.** Add screenshots (or the mock-up in §18.2), a role table and setup steps to `smart-water-dashboard/README.md`. Mark Phase 8 ✅.

---

## Phase 9: Industrial Debugger

**1. Objective.** Provide a separate service tool (web UI + CLI) that exposes deep diagnostics from the edge over the LAN, runs a diagnostic suite, verifies the hash chain, and exports a JSON report, **with no data-mutation capability**.

**2. Architecture.**

```text
Service laptop/tablet ──LAN / service Wi-Fi AP──► sw-api (FastAPI, token auth, read-mostly)
      │                                               │
      ├─ web panels (§19.3)                           ├─ SQLite (read-only connection: mode=ro)
      └─ swdebug CLI (§19.4)                          ├─ systemd status, /proc, disk
                                                      └─ diag checks (checks/catalogue.yaml)
```

**3. Folder structure.** §23.7; edge side `src/swedge/diagnostics/api.py`.

**4. Required files.** `diagnostics/api.py`, `diagnostics/health.py`, `debugger/cli/swdebug/*.py`, `checks/catalogue.yaml`, tests.

**5. Complete code.**

```python
# swedge/diagnostics/api.py
from __future__ import annotations

import hmac
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from swedge.storage.chain import verify_chain

DB = os.environ.get("SW_DB", "/var/lib/smart-water/edge.db")
TOKEN = os.environ.get("SW_DEBUG_API_TOKEN", "")
SERVICES = ["sw-receiver", "sw-sync", "sw-health"]

app = FastAPI(title="smart-water edge diagnostics", version="0.1.0")


def auth(authorization: str = Header(default="")):
    if not TOKEN:
        raise HTTPException(503, "API token not configured")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, TOKEN):
        raise HTTPException(401, "unauthorised")


def ro() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)       # READ-ONLY connection
    con.row_factory = sqlite3.Row
    return con


@app.get("/api/v1/status", dependencies=[Depends(auth)])
def status():
    con = ro()
    last = con.execute("SELECT node_id, device_ts, received_ts, mode, fw_version FROM raw_readings "
                       "ORDER BY rowid DESC LIMIT 1").fetchone()
    pending = con.execute("SELECT COUNT(*) FROM sync_outbox WHERE state='PENDING'").fetchone()[0]
    du = shutil.disk_usage(os.path.dirname(DB))
    return {
        "now": datetime.now(timezone.utc).isoformat(),
        "last_reading": dict(last) if last else None,
        "outbox_pending": pending,
        "disk_used_pct": round(100 * du.used / du.total, 1),
        "services": {s: _svc(s) for s in SERVICES},
        "cpu_temp_c": _cpu_temp(),
    }


@app.get("/api/v1/sensors", dependencies=[Depends(auth)])
def sensors(node: str, window: int = Query(12, ge=3, le=500)):
    rows = ro().execute("SELECT payload_json FROM raw_readings WHERE node_id=? ORDER BY rowid DESC LIMIT ?",
                        (node, window)).fetchall()
    import json, statistics
    msgs = [json.loads(r[0]) for r in rows]
    out = {}
    for p in ("ph", "turbidity_ntu", "tds_ppm", "ec_us_cm", "temperature_c"):
        vals = [m["raw"].get(p) for m in msgs]
        nums = [v for v in vals if isinstance(v, (int, float))]
        out[p] = {
            "sensor_id": (msgs[0].get("sensor_ids") or {}).get(p) if msgs else None,
            "state": "CONNECTED" if vals and vals[0] is not None else "NO_RESPONSE",
            "last": vals[0] if vals else None,
            "present_ratio": round(len(nums) / len(vals), 2) if vals else 0,
            "noise_sigma": round(statistics.pstdev(nums), 4) if len(nums) > 1 else None,
        }
    return out


@app.post("/api/v1/chain/verify", dependencies=[Depends(auth)])
def chain(node: str):
    rows = ro().execute("SELECT * FROM raw_readings WHERE node_id=? ORDER BY boot_id, seq", (node,)).fetchall()
    ok, bad = verify_chain([dict(r) for r in rows])
    return {"node": node, "checked": len(rows), "ok": ok, "first_bad_record": bad}


def _svc(name: str) -> str:
    try:
        return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return "unknown"


def _cpu_temp():
    try:
        return int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
    except OSError:
        return None
```

```python
# smart-water-debugger/cli/swdebug/__main__.py
import json
import os
import sys
from datetime import datetime

import click
import requests


class Client:
    def __init__(self, base, token):
        self.base, self.h = base.rstrip("/"), {"Authorization": f"Bearer {token}"}

    def get(self, path, **params):
        r = requests.get(f"{self.base}{path}", headers=self.h, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def post(self, path, **params):
        r = requests.post(f"{self.base}{path}", headers=self.h, params=params, timeout=120)
        r.raise_for_status()
        return r.json()


@click.group()
@click.option("--gateway", default=lambda: os.environ.get("SW_GATEWAY", "http://192.168.4.1:8088"))
@click.option("--token", default=lambda: os.environ.get("SW_DEBUG_API_TOKEN", ""))
@click.pass_context
def cli(ctx, gateway, token):
    if not token:
        click.echo("SW_DEBUG_API_TOKEN not set", err=True)
        sys.exit(2)
    ctx.obj = Client(gateway if gateway.startswith("http") else f"http://{gateway}:8088", token)


@cli.command()
@click.pass_obj
def status(c):
    s = c.get("/api/v1/status")
    lr = s["last_reading"] or {}
    click.echo(f"  node {lr.get('node_id','?')}  mode {lr.get('mode','?')}  fw {lr.get('fw_version','?')}  last {lr.get('received_ts','—')}")
    click.echo(f"  edge disk {s['disk_used_pct']}%  cpu {s['cpu_temp_c']}C  services {s['services']}")
    click.echo(f"  cloud queued {s['outbox_pending']}")


@cli.command()
@click.argument("node")
@click.pass_obj
def sensors(c, node):
    click.echo(f"  {'PARAM':15}{'ID':8}{'STATE':13}{'LAST':>10}{'PRESENT':>9}{'σ':>9}")
    for p, d in c.get("/api/v1/sensors", node=node).items():
        click.echo(f"  {p:15}{str(d['sensor_id']):8}{d['state']:13}{str(d['last']):>10}{d['present_ratio']:>9}{str(d['noise_sigma']):>9}")


@cli.command("verify-chain")
@click.argument("node")
@click.pass_obj
def verify_chain(c, node):
    r = c.post("/api/v1/chain/verify", node=node)
    click.echo(f"  checked {r['checked']:,} records ... " + ("OK" if r["ok"] else f"BROKEN at {r['first_bad_record']}"))


@cli.command()
@click.argument("node")
@click.pass_obj
def report(c, node):
    data = {"generated": datetime.utcnow().isoformat() + "Z", "status": c.get("/api/v1/status"),
            "sensors": c.get("/api/v1/sensors", node=node)}
    fn = f"diag_{node}_{datetime.utcnow():%Y%m%dT%H%M}.json"
    with open(fn, "w") as f:
        json.dump(data, f, indent=2)
    click.echo(f"  report: {fn}")


if __name__ == "__main__":
    cli()
```

**6. Configuration.** `SW_DEBUG_API_TOKEN` (generate with `openssl rand -hex 32`) goes in `/etc/smart-water/edge.env` on the Pi and in the service engineer's environment. The API binds to the LAN/service AP only. **Don't expose it to the internet.**

**7. Installation commands.**

```bash
# edge
pip install fastapi uvicorn
sudo systemctl enable --now sw-api
# service laptop
pipx install ./smart-water-debugger/cli
```

**8. Run commands.**

```bash
uvicorn swedge.diagnostics.api:app --host 0.0.0.0 --port 8088      # (via sw-api.service in production)
export SW_DEBUG_API_TOKEN=...; swdebug --gateway 192.168.4.1 status
swdebug --gateway 192.168.4.1 sensors SWN-0001
swdebug --gateway 192.168.4.1 verify-chain SWN-0001
swdebug --gateway 192.168.4.1 report SWN-0001
```

**9. Expected output.** See §19.4.

**10. Test procedure.**

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P9-T1 | Request without token | GET /status | 401 | _record_ | _ |
| P9-T2 | Wrong token | GET /status | 401 (constant-time compare) | _record_ | _ |
| P9-T3 | Unplug temperature probe | `swdebug sensors` | TP state NO_RESPONSE | _record_ | _ |
| P9-T4 | Attempt write via API connection | Code review + test: API opens DB `mode=ro` | Write raises `attempt to write a readonly database` | _record_ | _ |
| P9-T5 | Stop sw-sync | `swdebug status` | services shows `inactive` | _record_ | _ |
| P9-T6 | Tampered DB (test copy) | `verify-chain` | BROKEN at first modified record | _record_ | _ |
| P9-T7 | No internet on site | Connect laptop to service AP | Debugger fully functional | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| 503 "token not configured" | Env var missing | Add to `edge.env`, restart `sw-api` |
| Connection refused | Service down / firewall | `systemctl status sw-api`; `ufw allow from 192.168.4.0/24 to any port 8088` |
| `sensors` slow | Large window | Reduce `window` |

**12. Git commands.**

```bash
git checkout -b feat/phase-9-debugger
git add cli web checks tests
git commit -m "feat(debugger): LAN diagnostic API (read-only DB), swdebug CLI, chain verification and reports"
```

**13. Commit message.** `feat(debugger): LAN diagnostic API (read-only DB), swdebug CLI, chain verification and reports`

**14. README update.** Add the panel descriptions (§19.3), the check catalogue (§19.5) and the security note ("LAN only") to `smart-water-debugger/README.md`. Mark Phase 9 ✅.

---

## Phase 10: Solar Power Subsystem

**1. Objective.** Integrate the PV panel and solar charge controller with the battery; measure solar voltage, current and power; detect `SOLAR_UNAVAILABLE` and restore events; and publish power samples.

**2. Architecture.**

```text
PV panel ─► [fuse] ─► Solar charge controller (PWM/MPPT) ─► Battery
                 │
            [Power monitor #1: V/I on PV side OR controller output — choose & document]
                 │ I²C
               ESP32 PowerMonitor ─► power sample (every power_interval_s) ─► Pi ─► power_samples
```

> **Measurement point decision.** Measuring on the **controller output** (the battery side) shows the energy actually delivered to the system. Measuring on the **PV side** shows what the panel produces. The prototype records the controller output. Document whichever point you choose in `hardware.yaml` so the data is interpreted correctly.

**3. Folder structure.** `smart-water-power/firmware/src/PowerMonitor.*`, `smart-water-power/src/power/`, `docs/solar.md`.

**4. Required files.** `PowerMonitor.{h,cpp}`, `SolarEvents.{h,cpp}`, `docs/solar.md`, tests.

**5. Complete code.**

```cpp
// firmware/src/PowerMonitor.h
#pragma once
#include <stdint.h>
#include <math.h>

struct Channel { float v = NAN, i = NAN; float p() const { return (isnan(v) || isnan(i)) ? NAN : v * i; } };

struct PowerSnapshot {
  Channel solar, wind, battery, load;
  uint32_t epoch = 0;
};

class IPowerSensor {                     // abstraction: INA219 / INA226 / INA3221 / BMS
 public:
  virtual ~IPowerSensor() = default;
  virtual bool begin() = 0;
  virtual Channel read() = 0;            // NAN on I²C failure — never 0
};

class PowerMonitor {
 public:
  PowerMonitor(IPowerSensor* s, IPowerSensor* w, IPowerSensor* b, IPowerSensor* l) : s_(s), w_(w), b_(b), l_(l) {}
  bool begin() { return s_->begin() & w_->begin() & b_->begin() & l_->begin(); }
  PowerSnapshot sample(uint32_t epoch) {
    PowerSnapshot p; p.solar = s_->read(); p.wind = w_->read(); p.battery = b_->read(); p.load = l_->read();
    p.epoch = epoch; return p;
  }
 private:
  IPowerSensor *s_, *w_, *b_, *l_;
};
```

```cpp
// firmware/src/AvailabilityDetector.h — generic debounced availability (used for solar AND wind)
#pragma once
#include <stdint.h>
#include <math.h>

class AvailabilityDetector {
 public:
  enum class Event : uint8_t { NONE, BECAME_UNAVAILABLE, RESTORED };
  AvailabilityDetector(float epsW, uint32_t absentS, uint32_t restoreS)
      : eps_(epsW), absentS_(absentS), restoreS_(restoreS) {}

  // 'expected' = whether generation is expected now (e.g. inside daylight window for solar; always true for wind)
  Event update(float powerW, bool expected, uint32_t now) {
    const bool on = !isnan(powerW) && powerW > eps_;
    if (on) { lowSince_ = 0; if (!highSince_) highSince_ = now; }
    else    { highSince_ = 0; if (expected && !lowSince_) lowSince_ = now; if (!expected) lowSince_ = 0; }

    if (available_ && lowSince_ && now - lowSince_ >= absentS_) { available_ = false; return Event::BECAME_UNAVAILABLE; }
    if (!available_ && highSince_ && now - highSince_ >= restoreS_) { available_ = true; return Event::RESTORED; }
    return Event::NONE;
  }
  bool available() const { return available_; }
 private:
  float eps_; uint32_t absentS_, restoreS_;
  uint32_t lowSince_ = 0, highSince_ = 0;
  bool available_ = true;
};
```

```python
# smart-water-power/src/power/availability.py  (host-side model mirroring the firmware, used in tests/simulation)
from dataclasses import dataclass


@dataclass
class AvailabilityDetector:
    eps_w: float
    absent_s: int
    restore_s: int
    available: bool = True
    _low_since: int | None = None
    _high_since: int | None = None

    def update(self, power_w: float | None, expected: bool, now: int) -> str | None:
        on = power_w is not None and power_w > self.eps_w
        if on:
            self._low_since = None
            self._high_since = self._high_since if self._high_since is not None else now
        else:
            self._high_since = None
            if expected and self._low_since is None:
                self._low_since = now
            if not expected:
                self._low_since = None
        if self.available and self._low_since is not None and now - self._low_since >= self.absent_s:
            self.available = False
            return "UNAVAILABLE"
        if not self.available and self._high_since is not None and now - self._high_since >= self.restore_s:
            self.available = True
            return "RESTORED"
        return None
```

**6. Configuration.** `power.example.yaml` (§21.4): `daylight_window_local`, `events.solar_absent_s`, `events.restore_s`, `measurement.noise_floor_w`. Panel and controller ratings: `TBD / CONFIGURABLE`.

**7. Installation commands.** `pio pkg install` (firmware lib); `pip install -e smart-water-power[dev]`.

**8. Run commands.**

```bash
cd smart-water-power && python -m pytest -q tests/test_availability.py
pio test -e native -d firmware
```

**9. Expected output.**

```text
tests/test_availability.py ....                                          [100%]
4 passed
```

**10. Test procedure.**

```python
# tests/test_availability.py
from power.availability import AvailabilityDetector

def test_night_does_not_raise_solar_unavailable():
    d = AvailabilityDetector(0.2, 3600, 600)
    assert all(d.update(0.0, expected=False, now=t) is None for t in range(0, 20000, 60))

def test_daylight_absence_raises_after_absent_s():
    d = AvailabilityDetector(0.2, 3600, 600)
    events = [d.update(0.0, True, t) for t in range(0, 4000, 60)]
    assert "UNAVAILABLE" in events and events.index("UNAVAILABLE") * 60 >= 3600

def test_restore_requires_sustained_generation():
    d = AvailabilityDetector(0.2, 60, 600); d.update(0, True, 0); d.update(0, True, 61)
    assert d.update(5.0, True, 100) is None
    assert d.update(5.0, True, 701) == "RESTORED"

def test_nan_is_not_generation():
    d = AvailabilityDetector(0.2, 60, 60)
    d.update(None, True, 0)
    assert d.update(None, True, 61) == "UNAVAILABLE"
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P10-T1 | Clear midday | Read solar channel | V, I, P > 0; source includes SOLAR | _record_ | _ |
| P10-T2 | Cover panel (opaque sheet) for > absent_s in daylight | Observe events | `SOLAR_UNAVAILABLE` | _record_ | _ |
| P10-T3 | Uncover | Observe | `RENEWABLE_RESTORED` after restore_s | _record_ | _ |
| P10-T4 | Night | Observe | No `SOLAR_UNAVAILABLE` events | _record_ | _ |
| P10-T5 | Disconnect INA I²C | Read | NaN → `null`, `POWER_MONITOR_FAULT` event; never 0 | _record_ | _ |
| P10-T6 | Measured vs reference multimeter | Compare | Within tolerance (TBD) | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| Solar power reads negative | Shunt orientation reversed | Swap shunt leads or invert sign in config |
| Controller doesn't charge | Battery-type setting wrong / panel Voc too low | Check controller manual; measure Voc |
| Solar output low on a clear day | Panel dirty / shaded / wrong tilt | Clean; remove shade; adjust tilt |

**12. Git commands.**

```bash
git checkout -b feat/phase-10-solar
git add firmware/src/PowerMonitor.* firmware/src/AvailabilityDetector.h src/power/availability.py tests docs/solar.md
git commit -m "feat(power): solar channel measurement and debounced availability events"
```

**13. Commit message.** `feat(power): solar channel measurement and debounced availability events`

**14. README update.** Add a solar wiring diagram, measurement-point decision and event table to `smart-water-power/docs/solar.md`. Mark Phase 10 ✅.

---

## Phase 11: Wind Power Subsystem

**1. Objective.** Integrate the small wind turbine through a rectifier and wind charge controller with **over-speed protection** (dump load/brake); measure wind V/I/P; raise `WIND_UNAVAILABLE`, `OVERSPEED_PROTECTION` and restore events.

**2. Architecture.**

```text
Turbine (3-phase AC or DC) ─► Rectifier ─► Wind charge controller ─┬─► Battery
                                            │                      └─► Dump load (resistor) when battery full / over-speed
                                            └─ status output (optional) ─► ESP32 GPIO (OVERSPEED/BRAKE)
                                        [Power monitor #2 on controller output]
Manual brake switch (shorting) for maintenance — mounted at the pole base.
```

> ⚠️ **Safety:** a free-spinning turbine that's disconnected from a load can over-speed and produce dangerous voltages. Always use the manufacturer-specified controller and dump load, and brake the turbine before any maintenance.

**3. Folder structure.** Reuses `AvailabilityDetector`; adds `WindStatus.{h,cpp}`, `docs/wind.md`.

**4. Required files.** `WindStatus.{h,cpp}`, `docs/wind.md`, tests.

**5. Complete code.**

```cpp
// firmware/src/WindStatus.h
#pragma once
#include "AvailabilityDetector.h"

enum class WindState : uint8_t { GENERATING, IDLE, UNAVAILABLE, PROTECTION_ACTIVE, UNKNOWN };

class WindStatus {
 public:
  WindStatus(float epsW, uint32_t absentS, uint32_t restoreS, int8_t protectionPin, bool activeLow)
      : det_(epsW, absentS, restoreS), pin_(protectionPin), activeLow_(activeLow) {}

  // protectionInput: raw GPIO level (or -1 if not wired)
  WindState update(float powerW, int protectionInput, uint32_t now, AvailabilityDetector::Event& ev) {
    ev = det_.update(powerW, /*expected=*/true, now);
    if (pin_ >= 0 && protectionInput >= 0) {
      const bool prot = activeLow_ ? (protectionInput == 0) : (protectionInput == 1);
      if (prot) return WindState::PROTECTION_ACTIVE;
    }
    if (isnan(powerW)) return WindState::UNKNOWN;
    if (!det_.available()) return WindState::UNAVAILABLE;
    return powerW > 0.2f ? WindState::GENERATING : WindState::IDLE;
  }
 private:
  AvailabilityDetector det_;
  int8_t pin_;
  bool activeLow_;
};
```

**6. Configuration.**

```yaml
wind:
  controller_status_pin: TBD       # -1 if controller has no status output
  status_active_low: true
  absent_s: 21600                  # wind is intermittent — long debounce avoids alert noise
  restore_s: 600
  rated_power_w: TBD
  cut_in_note: "from turbine datasheet — informational only; control uses measured power"
```

**7. Installation commands.** As Phase 10.

**8. Run commands.** `python -m pytest -q tests/test_wind.py`; `pio test -e native -d firmware`.

**9. Expected output.** `3 passed`.

**10. Test procedure.**

```python
# tests/test_wind.py
from power.availability import AvailabilityDetector

def test_short_lulls_do_not_raise_unavailable():
    d = AvailabilityDetector(0.2, 21600, 600)
    ev = [d.update(0.0 if (t // 600) % 2 else 3.0, True, t) for t in range(0, 86400, 60)]
    assert "UNAVAILABLE" not in ev

def test_long_calm_raises_unavailable():
    d = AvailabilityDetector(0.2, 21600, 600)
    ev = [d.update(0.0, True, t) for t in range(0, 30000, 60)]
    assert "UNAVAILABLE" in ev

def test_restore():
    d = AvailabilityDetector(0.2, 60, 600); d.update(0, True, 0); d.update(0, True, 61)
    assert [d.update(4.0, True, t) for t in (100, 800)][-1] == "RESTORED"
```

| # | INPUT | PROCESS | EXPECTED | ACTUAL | PASS/FAIL |
|:-:|---|---|---|---|:-:|
| P11-T1 | Turbine spinning (natural wind or bench motor rig) | Read wind channel | V/I/P > 0; `GENERATING` | _record_ | _ |
| P11-T2 | Calm > absent_s | Events | `WIND_UNAVAILABLE` | _record_ | _ |
| P11-T3 | Battery full + generation | Controller | Dump load engages; battery not over-charged (measured V ≤ controller set-point) | _record_ | _ |
| P11-T4 | Simulate over-speed status input | Status | `PROTECTION_ACTIVE`, `OVERSPEED_PROTECTION` event | _record_ | _ |
| P11-T5 | Manual brake switch | Observe | Turbine stops; P = 0; no false alarm beyond INFO | _record_ | _ |

**11. Troubleshooting.**

| Symptom | Cause | Fix |
|---|---|---|
| Wind power spiky/noisy | Normal turbulence | Use averages for display; raw samples still stored |
| Turbine spins but no charge | Rectifier fault / controller in dump mode | Measure AC and DC sides; check battery voltage |
| Dump resistor very hot | Expected when battery full and windy | Make sure it's mounted outside the electronics enclosure with clearance |
| Audible noise / vibration | Blade imbalance, loose mounting | Inspect; balance; tighten |

**12. Git commands.**

```bash
git checkout -b feat/phase-11-wind
git add firmware/src/WindStatus.* tests/test_wind.py docs/wind.md
git commit -m "feat(power): wind channel with protection status and long-debounce availability"
```

**13. Commit message.** `feat(power): wind channel with protection status and long-debounce availability`

**14. README update.** `smart-water-power/docs/wind.md`: safety warning, controller/dump-load requirement, event table. Mark Phase 11 ✅.
