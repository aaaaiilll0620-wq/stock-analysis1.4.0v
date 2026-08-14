# P0-R2 Phase B — Offline Design Freeze (revision 13)

**Status:** APPROVED — 2026-08-15, Stage 1 offline Phase C design freeze. Companion erratum **E2 revision 9** was approved in the same event. Approval does not authorize evidence roots, live writes, R-FWD forward/live collection, Task Scheduler changes, or production calculation/state writes. Archive commit identity is maintained externally to avoid self-reference.
**Design baseline commit:** `099b9b15171c1e2ffb17e932295ec3c76f60725a`.
**Date:** designed 2026-08-14; approved 2026-08-15, revision 13 (round 13 of user feedback).
**Companion file:** `collector_schema.json` (revision 13, 46 definitions, same directory).
**Self-containment note:** every hash table, formula, and algorithm a reader needs is pasted below in full. Nothing in this document says "not re-pasted" or "see revision N."

**What round 13 changed** (one P1 blocker, one P2 documentation-consistency issue, both from the user's round-13 review):
1. [P1] §4.7 — `RFwdQualificationRef` pinned the ATTEMPT by `record_hash` (round 9) but resolved the RESOLUTION half of the reference by scanning for "the latest `RFwdQualificationResolutionEvent`" at *validation* time (round 12) — so the identical immutable run receipt could validate differently depending on whether it was checked before or after a later resolution event was appended, violating the exact "future append must not reinterpret existing evidence" guarantee `RFwdQualificationRef` exists to provide (§4.3). New `resolution_record_hash` field pins the SPECIFIC resolution event (or `null`, if the attempt was already `QUALIFIED` at write time) a receipt relied on, at write time — check #10 (rewritten) resolves this pinned value, never the latest ledger entry, and additionally requires the pinned resolution's `generated_at` be no later than the receipt's own `completed_at`. A reference to a still-unresolved `QUALIFICATION_PENDING` attempt (`resolution_record_hash` left null) is now rejected outright — there is no longer any way to write a reference that becomes valid only later.
2. [P2] §4.3/§4.4 — the historical sections describing check #10's pre-round-13 behavior are now marked superseded rather than left to read as if still current (matching this document's existing practice for §4.1a/§6.1/§8.2/§9.1). §13's test-matrix header, which still said "Notes as of revision 8" while the document itself had moved to revision 12, is corrected to the current revision number.

**What round 11 changed** (all four from the user's round-11 review):
1. §4 — `RFwdAdapterQualificationRecord.qualification_status` gains a third value, `QUALIFICATION_PENDING`. Round 10's binary QUALIFIED/QUALIFICATION_FAILED had no legal encoding for "all four research gates passed, evidence bundle not yet mirror-VERIFIED" — QUALIFIED requires the bundle VERIFIED (unmet), and QUALIFICATION_FAILED's own negation forbade all four gates passing (none had failed). That ordinary in-flight state validated against neither value. The three values now partition exhaustively: QUALIFIED = four gates PASS + bundle VERIFIED; QUALIFICATION_PENDING = four gates PASS + bundle still PENDING; QUALIFICATION_FAILED = at least one gate FAILED (bundle status irrelevant).
2. §4/§9 — the qualification bundle is now closed end-to-end. `QualificationBundleLocation.artifact_set` gains its own recomputable `aggregate_sha256`; `mirror_verification` is pinned to a new closed two-file shape (`MirrorPerFileVerificationQualificationBundle`) instead of the generic minProperties:1 shape a single-file "verification" previously satisfied; new semantic checks #22/#23 tie every file's bytes/sha256 across `artifact_set`, `mirror_verification`, and the audit-evidence artifacts referenced from `process_isolation_audit`/`future_input_access_audit` — a missing file, an extra file, or any hash/bytes divergence is rejected.
3. §8 — `PreflightObservation.lock_holder_pid`/`disk_free_bytes` gain explicit schema `maximum` bounds (`4294967295` / `9223372036854775807`), so the placeholder policy's "measured maximum" claim is schema-provable, not merely asserted (check #18 extended). And `announcement_date_pit_status` inside the capacity-projection types is no longer unconditionally `BLOCKED`: a `COMPARABLE_IDENTITY` projection now sizes against `VERIFIED` — the value a future-viable receipt would actually carry once Gate C-R unblocks — never the shorter `BLOCKED`, and the assembled object continues to validate against `ProjectedRunReceipt` (check #12, extended). Gate C-R's own lock on the LIVE `RunReceiptSuccess` type (§12) is untouched by this — the projection sizes a hypothetical future receipt for NFR-7 planning, and asserts nothing about Gate C-R's current status.
4. §9 — `LedgerHeadCheckpoint` (round 11's shape — since split, see round 12 below) defined its own durable storage location and dual-copy hash identity; previously "is itself dual-copy durable" was prose with no enforcing field. Its new `protection_scope` explicitly narrows the claim: detects single-sided ledger truncation, does **not** detect a ledger and its checkpoint being rolled back together to a consistent earlier state. `AggregateHashFormula.member_selector` (one enum pick) is replaced by `selectors`, three independently-fixed consts (artifact/primary/mirror) — one qualification record needs all three aggregates self-described at once, not one at a time.

**One defect found by round 11's own validator, disclosed:** the first draft of the maximum-length placeholder paired `disk_check_status=UNKNOWN` with a non-null `disk_free_bytes`, which `PreflightObservation` forbids — "longest" has to also be *legal*. Measured across the legal pairs, `LOW` + int64-max (65 bytes) beats `UNKNOWN` + null (54 bytes); the placeholder now uses `LOW`. Recorded because the schema's own conditional rules constrain what a conservative placeholder may say.

**What round 12 changed** (all three from the user's round-12 review, all found IN round 11's own new work):
1. §9 — `LedgerHeadCheckpoint`'s `content_sha256` (a hash of six sibling fields) lived in the SAME object as `storage.mirror_verification`, which checked a per-file hash against that `content_sha256` — but the real on-disk checkpoint file, if it is that whole object, includes `storage`/`protection_scope`/`content_sha256` itself, so a schema-valid, check-#20-passing instance existed whose true file SHA256 diverged from `content_sha256` (the user's exact repro; the same self-reference class of bug as round 10's `record_id`/`record_hash` circularity, reintroduced in a new shape). **Split into `LedgerHeadCheckpointPayload`** (the six content fields ONLY — the sole thing ever serialized as the physical checkpoint file) **and `LedgerHeadCheckpointRecord`** (a separate, external receipt embedding `payload` + independently-recomputed `payload_sha256`/`payload_bytes` + `storage.mirror_verification`, whose per-file hash equality against `payload_sha256` is now non-circular, since `payload_sha256` is defined over `payload` alone — a disjoint object from this record).
2. §4 — `RFwdAdapterQualificationRecord` had no append-only-safe way to move a `QUALIFICATION_PENDING` attempt to `QUALIFIED` once its bundle finished mirroring: editing the record breaks `record_hash`/append-only discipline, and a brand-new record needs a NEW `record_id`, which `bundle_location.bundle_relative_root` is keyed by — pointing at a bundle path that was never actually written. **New `RFwdQualificationResolutionEvent`** (`entry_kind="resolution"`) appends to the SAME hash-chained ledger stream as attempts, referencing the original attempt by its STABLE `record_id` + `record_hash` (never reissued), one-directional `PENDING`→`QUALIFIED` only — modeled directly on `LedgerEvent`'s existing `mirror` event_type / `effective_persistence_status` pattern. `RFwdQualificationLedgerEntry` is the new `oneOf[attempt, resolution]` wrapper; check #10 now resolves the referenced attempt's EFFECTIVE qualification status (attempt + latest resolution event), not its literal field; new check #24 reapplies check #23's bundle bytes/hash consistency to resolution events.
3. §11 — `CodeHashManifest.r_fwd_adapter_sha256`'s description still said this field "MUST match the LATEST `RFwdAdapterQualificationRecord` ... for this `r_fwd_adapter_sha256`" — a residual pre-round-9 sentence directly contradicting round 9's own record_hash-pinned, never-latest-wins design (§4.3). Deleted; replaced with a description matching the actual rule (and round 12's effective-status join, item 2 above).

---

## 1. Primary/Mirror evidence root — candidate paths (unchanged from revision 6/7, inlined)

Stage 2 has not authorized Primary/Mirror evidence roots. Disqualified locations (Phase H): subpaths of `outputs\logs\`, `%LOCALAPPDATA%\FinMind\`, `cloud_cache\`, `outputs\universe_pool\`. Storage independence: same path or filesystem/volume identity → Gate C-P MUST FAIL, no exception (`os.path.realpath()`/`os.path.isabs()`).

**Concrete candidates** (`Get-Volume`/`Get-ChildItem`/`Test-Path`, round 6): `primary_root = D:\p0r2_identity_evidence\primary` (220.9 GB free), `mirror_root = E:\p0r2_identity_evidence\mirror` (808.7 GB free). `D:` root hosts an unrelated TEJ archive (not disqualifying, a mixing concern). `E:` appears system-adjacent (flagged for Stage 2, not resolved here). Both confirmed non-existent, genuinely independent NTFS volumes.

**Stage 2 checklist**: re-run disqualified-location + `realpath`-independence checks against the final paths at approval time; re-evaluate `active_cleanup_or_pruning_affecting_evidence_roots`; confirm `E:`'s system-adjacent status against backup/AV/permission policy; confirm free space against the frozen `capacity_dry_run_report.json` estimate.

---

## 2. `AttemptedInputManifest` / `input_bundle_sha256` / `run_id` (unchanged from revision 6/7, inlined)

`input_bundle_sha256 = sha256_hex(canonical_json(attempted_input_manifest, sort_keys=true))`, always non-null. `attempted_input_manifest` shape:
```json
{
  "p_a": {"status": "AVAILABLE|MISSING|NOT_ATTEMPTED", "observed_date": "<date or null>", "aggregate_sha256": "<hash or null>"},
  "p_b": {"status": "...", "observed_date": "...", "aggregate_sha256": "..."},
  "r_fwd": {"status": "...", "observed_date": "...", "aggregate_sha256": "..."},
  "preflight": {"lock_state": "FREE|HELD|STALE_DETECTED", "lock_holder_pid": "<int or null>",
                "disk_check_status": "OK|LOW|UNKNOWN", "disk_free_bytes": "<int or null>"}
}
```
`AVAILABLE` requires real `observed_date`+`aggregate_sha256`; `MISSING`/`NOT_ATTEMPTED` force both `null`. `run_id = sha256_hex(canonical_json({as_of, collector_version, input_bundle_sha256}, sort_keys=true))` — the only formula, no fallback. Verified non-colliding across distinct failure scenarios with real sha256 (`c80e7809...` vs. `aa5c98f5...`).

---

## 3. Pre-source failures — `identity_epoch` nullability (unchanged from revision 6/7, inlined)

6 dedicated bindings, `identity_epoch=null` + fixed `identity_epoch_unavailable_reason`, cross-checked against `attempted_input_manifest`:

| `failure_code` | reason (const) | cross-check |
|---|---|---|
| `LOCK_HELD` | `LOCK_HELD_BEFORE_CAPTURE` | `preflight.lock_state ∈ {HELD, STALE_DETECTED}` |
| `LOW_DISK` | `LOW_DISK_BEFORE_CAPTURE` | `preflight.disk_check_status == LOW` |
| `MISSING_P_A` | `P_A_NOT_CAPTURED_BEFORE_EPOCH_READ` | `p_a.status == MISSING` |
| `MISSING_P_B` | `P_B_NOT_CAPTURED_BEFORE_EPOCH_READ` | `p_b.status == MISSING` |
| `DATE_MISMATCH` | `DATE_MISMATCH_BEFORE_EPOCH_READ` | both `p_a`/`p_b`.status `≠ NOT_ATTEMPTED` |
| `SOURCE_DATE_CONFLICT` | `SOURCE_DATE_CONFLICT_BEFORE_EPOCH_READ` | same |

`capture_process_started=false`/`process_isolation=null` only for `LOCK_HELD`; other 8 codes have a real process.

---

## 4. R-FWD adapter qualification — now an append-only ledger with FR-26/isolation/future-input gates (blocker 1)

**Problem identified (user's exact repro):** a `RFwdAdapterQualification` record containing only `exact_match_count=255` — no raw-score comparison, no isolation audit, no future-input-access audit — validated as `QUALIFIED`. FR-26 ("parity suite 對共同 raw-score keys MUST value-equivalent；預設 tolerance 1e-12") was never actually checked by the schema; membership exact-match (FR-25) was silently treated as the whole qualification bar.

**Correction — `RFwdAdapterQualificationRecord`, renamed and expanded, four independent gates, all required for `QUALIFIED`:**

```json
{
  "sequence": "<1-based ledger position>",
  "prior_record_hash": "<record_hash of the preceding entry; null iff sequence==1>",
  "record_hash": "<sha256 of this record MINUS its own record_hash field>",
  "record_id": "rfwdq-<independently pre-minted UUIDv4; NOT derived from record_hash>",
  "r_fwd_adapter_sha256": "<hash of the adapter code being qualified>",
  "oracle_hashes": {"high52_lab_sha256": "...", "dual100_lab_sha256": "...", "canonical_universe_sha256": "...", "lab_paths_sha256": "...", "build_arm_panel_sha256": "..."},
  "qualification_status": "QUALIFIED | QUALIFICATION_PENDING | QUALIFICATION_FAILED",
  "bundle_location": {"bundle_relative_root": "r_fwd_qualification/<record_id UUID>", "artifact_set": {"process_import_manifest.json": {...}, "future_input_access_trace.json": {...}, "aggregate_sha256": "<hash of the two files above>"}, "dual_copy_required": true, "mirror_verification": {"...": "...", "per_file_verification": "<CLOSED to exactly the 2 bundle files>"}},
  "aggregate_hash_formula": {"formula": "...", "canonical_json_rule": "...", "selectors": {"artifact_selector": "ArtifactFileEntry.sha256", "primary_selector": "MirrorFileComparisonEntry.primary_sha256", "mirror_selector": "MirrorFileComparisonEntry.mirror_sha256"}, "sort_rule": "...", "encoding": "utf-8"},
  "membership_parity_result": {"months_tested": 255, "exact_match_count": "<0-255>", "mismatched_months": ["empty iff exact_match_count==255"]},
  "raw_score_parity_result": {"common_keys_count": "<>=1>", "max_abs_diff": "<number>", "tolerance": "1e-12", "within_tolerance": "<bool, tied to max_abs_diff<=1e-12>"},
  "process_isolation_audit": {
    "status": "PASS|FAIL",
    "r_fwd_process": {"pid": "<int>", "executable_path": "<abs>", "argv_sha256": "<hash>", "started_at": {...}},
    "production_capture_process": {"pid": "<int, MUST differ>", "...": "..."},
    "import_manifest_artifact": {"artifact_role": "PROCESS_IMPORT_MANIFEST", "relative_path": "process_import_manifest.json", "bytes": "<int>", "sha256": "<hash>"},
    "bt_bundle_absent_from_production_process": "<bool, must be true when PASS>",
    "notes": "<string>"
  },
  "future_input_access_audit": {
    "status": "PASS|FAIL", "method": "STATIC_IMPORT_GRAPH|RUNTIME_IMPORT_MONITOR",
    "audit_tool_sha256": "<hash of the checker's own source>",
    "audited_entrypoint": "<module:function whose reachability was audited>",
    "forbidden_targets": ["exec_ret.parquet", "obs_alpha.parquet", "..."],
    "forbidden_targets_reached": ["<must be empty when PASS>"],
    "evidence_artifact": {"artifact_role": "FUTURE_INPUT_ACCESS_TRACE", "relative_path": "future_input_access_trace.json", "bytes": "<int>", "sha256": "<hash>"},
    "notes": "<string>"
  }
}
```

`qualification_status` is a three-way partition (round 11, item 1 — see §4.4): `QUALIFIED` requires ALL FOUR gates simultaneously (`membership_parity_result.exact_match_count==255`, `raw_score_parity_result.within_tolerance==true`, `process_isolation_audit.status==PASS`, `future_input_access_audit.status==PASS`) **plus** `bundle_location.mirror_verification.status==VERIFIED`; `QUALIFICATION_PENDING` requires the same four gates but the bundle still `PENDING`; `QUALIFICATION_FAILED` requires at least one gate to have actually failed, irrespective of bundle status. `common_keys_count` has `minimum:1`, closing a degenerate-input loophole.

### 4.1 Hash chain — append-only is now mechanical, not textual (round 9, blocker 1)

**Problem identified:** round 8 declared the ledger append-only in prose but gave the record type no `sequence`, `prior_record_hash`, or `record_hash` — while the test matrix already claimed `test_ledger_hash_chain` covered it. There were no fields to assert against.

**Correction:** the record now carries the same chain fields `LedgerEvent` uses. `record_hash = sha256_hex(canonical_json(record_minus_record_hash, sort_keys=true))` — excluding its own hash field, so there is no self-reference circularity (the same construction discipline as `CapacityDryRunReportAttempt.receipt_sha256`). `sequence==1` ⟺ `prior_record_hash==null` is schema-enforced; chain **continuity** across records is cross-object, so it is **semantic validator check #13**, which also recomputes every `record_hash`. Verified: a well-formed 2-record chain passes; a broken link is caught; and a record edited in place after the fact is caught by hash recomputation.

#### 4.1a Round 10 (blocker 1): `record_id` was circular — now independently minted

**Problem identified:** round 9 specified `record_hash = hash(record minus record_hash)` — a body that *includes* `record_id` — while also specifying `record_id = "rfwdq-" + record_hash[:16]`. The two were mutually dependent. The user's repro made this concrete: choose *any* `record_id`, compute `record_hash` over the body containing it, and both the schema and check #13's recomputation pass — while `record_id` bears no relation to the hash prefix. The stated derivation was therefore unverifiable, and an unverifiable derivation is not an identity rule.

**Correction:** `record_id` is now an **independently pre-minted RFC-4122 version-4 UUID** (prefixed `rfwdq-`), generated *before* hashing and then covered *by* `record_hash`. Generation order is strictly: (1) mint `record_id`, (2) assemble the body, (3) hash the body. Nothing is derived from `record_hash`. The schema pattern enforces the UUIDv4 shape including the version and variant nibbles. **New semantic check #17** verifies the UUID form, uniqueness across the ledger, and — specifically — that no `record_id` is a prefix-derivative of its own `record_hash`, so the round-9 construction cannot be reintroduced unnoticed. Verified: the round-9 style id is rejected by the schema; a v1 UUID is rejected; and the circular construction is detected by check #17.

**Round 10 also anchors the record's evidence** (blocker 4): `bundle_location` and `aggregate_hash_formula` are now required fields — see §9.

### 4.2 Audits now require real evidence (round 9, blocker 2)

**Problem identified:** `process_isolation_audit` and `future_input_access_audit` were `{status, notes}` and `{status, method, notes}` — anyone could write `PASS` and obtain a schema-valid `QUALIFIED`.

**Correction:** `process_isolation_audit` now requires two attributable `ProcessIdentity` objects (pid, executable path, argv hash, start time) for the R-FWD and production-capture sides, a hash-identified `import_manifest_artifact` recording what each process actually imported, and `bt_bundle_absent_from_production_process` (schema-forced `true` when `PASS`). `future_input_access_audit` now requires the audit tool's own `audit_tool_sha256`, the exact `audited_entrypoint`, an enumerated `forbidden_targets` list (`minItems:2`), a `forbidden_targets_reached` list that is schema-forced **empty** when `PASS` and non-empty when `FAIL` (this is the field that makes `PASS` falsifiable), and a hash-identified `evidence_artifact`. Two cross-field rules remain schema-inexpressible: the two audit pids must differ (**check #14**) and `forbidden_targets` must name both FR-28 artifacts (**check #15**). Both verified this round.

### 4.3 Runs pin an exact record, not "the latest" (round 9, blocker 1)

**Partially superseded — see §4.7 (round 13).** This section's own subject (pin the attempt by `record_hash`, never "the latest") is still correct and unchanged. But `r_fwd_qualification_ref`'s shape has since grown a field (`resolution_record_hash`, round 13), and the sentence "requiring that record be `QUALIFIED`" below described round 9's world, before `QUALIFICATION_PENDING`/resolution events existed (round 11/12) — it is no longer a complete statement of the rule. Kept verbatim below as the historical record of round 9's fix, per this project's own discipline of not silently rewriting a corrected section as if it were always complete (§4.1a, §6.1, §8.2, §9.1 all do the same). Read together with §4.6/§4.7 for the current rule.

**Problem identified:** round 8 stored only `code_hashes.r_fwd_adapter_sha256` per run and resolved "the latest ledger record for that hash." A later requalification appending a new record therefore **retroactively changed how an already-written run's evidence reads** — evidence written in the past must not be reinterpretable by future appends.

**Correction:** `RunReceiptSuccess` gains `r_fwd_qualification_ref` (`{record_id, record_hash, r_fwd_adapter_sha256}` at round 9; `+ resolution_record_hash` from round 13, §4.7), non-null exactly when `identity_status=COMPARABLE_IDENTITY` (schema-tied). **Semantic check #10 is rewritten** to resolve **by `record_hash`** to one exact record, requiring that record be `QUALIFIED`, that its `record_id`/`r_fwd_adapter_sha256` agree with the ref, and that the ref agrees with the receipt's own `code_hashes.r_fwd_adapter_sha256`. Verified this round: a ref pinning a `QUALIFIED` record passes; **appending a later `QUALIFICATION_FAILED` record does not disturb the earlier pinned run**; a ref pinning a `QUALIFICATION_FAILED` record is rejected; a dangling ref is rejected.

**Verified this round** (`validate_collector_schema_v9.py`): the round-8 record shape (no chain fields) is now rejected; both bare-`PASS` audit repros are rejected; `PASS` with a forbidden target actually reached is rejected; `forbidden_targets` with fewer than 2 entries is rejected; a P-only run carrying a qualification ref is rejected.

### 4.4 Round 11 (item 1): `qualification_status` gains `QUALIFICATION_PENDING` — the binary split had no legal value for an ordinary in-flight state

**Problem identified (user's exact repro pattern):** construct a `RFwdAdapterQualificationRecord` where all four research gates genuinely PASS — `exact_match_count=255`, `within_tolerance=true`, both audits `PASS` — but `bundle_location.mirror_verification.status=PENDING` because the dual-copy write to the mirror root hasn't completed yet. This is not a hypothetical edge case; it is the *ordinary* window between "research proved itself" and "evidence durably landed," and per FR-38's own general rule (a run isn't `COMMITTED` until both copies verify) it will occur on essentially every qualification attempt. Validate that record against round 10's schema: `QUALIFIED` fails (`bundle_location.mirror_verification.status` must be `VERIFIED`, and isn't). `QUALIFICATION_FAILED` *also* fails — its `allOf` requires `not(`all four gates passing`)`, and here all four genuinely pass. **Every legal enum value rejects a record describing a real, non-erroneous state.** The record cannot be written at all until the mirror write completes, which is exactly backwards: the schema should describe the run's true state at every point, not force silence during an ordinary durability window.

**Correction:** `qualification_status` gains `QUALIFICATION_PENDING`. The three values now form an exhaustive, mutually exclusive partition, enforced by three parallel `allOf` `if/then` blocks (one per value — each fires only when `qualification_status` equals that exact value, so exactly one block's `then` applies to any given record):

```text
QUALIFIED             ⟺ (all four gates PASS) AND (bundle mirror_verification.status == VERIFIED)
QUALIFICATION_PENDING ⟺ (all four gates PASS) AND (bundle mirror_verification.status == PENDING)
QUALIFICATION_FAILED  ⟺ NOT(all four gates PASS)                              [bundle status irrelevant]
```

Because `MirrorVerification.status` itself has only two legal values (`VERIFIED`/`PENDING`), the first two rows are exhaustive over "all four gates pass" without a fourth case to worry about. No reverse-direction block is needed: since exactly one `if` matches any given `qualification_status`, and that block's `then` pins the exact required condition, mislabeling in either direction (e.g. `PENDING` claimed while actually `VERIFIED`, or `FAILED` claimed while all four gates actually pass) is caught by the one block that fires — the same proof pattern round 10 already used for the two-way split, extended to three.

**Verified this round** (scratch validator, see §14): a record with all four gates PASS and bundle PENDING, labeled `QUALIFICATION_PENDING`, now validates (round 10 schema rejected it under both other labels — reproduced first, then shown fixed). The same record mislabeled `QUALIFIED` is rejected (bundle not VERIFIED). The same record mislabeled `QUALIFICATION_FAILED` is rejected (no gate actually failed). A record with `raw_score_parity_result.within_tolerance=false` and bundle `VERIFIED`, labeled `QUALIFICATION_PENDING`, is rejected (a real gate failure cannot hide behind PENDING). `RFwdQualificationRef` resolution (check #10) as of round 11 required the referenced attempt be `QUALIFIED` at write time — **superseded round 12/13 (§4.6/§4.7)**: a run may now pin an attempt whose own `qualification_status` reads `QUALIFICATION_PENDING`, provided the reference also pins the exact resolution event that resolved it to `QUALIFIED` (`resolution_record_hash`, round 13) — a bare `QUALIFICATION_PENDING` attempt with no resolution pinned still cannot be referenced.

### 4.5 Round 11 (item 2): the qualification bundle is now closed end-to-end

**Problem identified:** round 10's `QualificationBundleLocation.artifact_set` was a closed two-file *shape* (`additionalProperties:false`, both files `required`), but three gaps remained. (a) `artifact_set` had no aggregate of its own — only `mirror_verification`'s primary/mirror aggregates existed, so the two-file set's own hash-of-hashes was never recorded or recomputable. (b) `mirror_verification` was a bare `$ref` to `MirrorVerification`, whose `per_file_verification` has only `minProperties:1` — a mirror-verification object naming just *one* of the bundle's two files (or naming three, with an extra unrelated entry) validated. (c) nothing tied `artifact_set`'s per-file `bytes`/`sha256` to `mirror_verification`'s per-file `primary_sha256`, nor to the `AuditEvidenceArtifact` objects `process_isolation_audit.import_manifest_artifact` and `future_input_access_audit.evidence_artifact` actually reference — three independent descriptions of the same two files could silently disagree.

**Correction, three parts.** *Aggregate*: `artifact_set` gains `aggregate_sha256`, computed via `AggregateHashFormula.selectors.artifact_selector` over the two files — new **semantic check #22** recomputes it. *Closed mirror shape*: a new definition, `MirrorPerFileVerificationQualificationBundle` (the qualification-bundle analogue of the existing `MirrorPerFileVerificationPOnly`/`Comparable` types), pins `per_file_verification` to `minProperties:2, maxProperties:2`, both filenames `required` — `QualificationBundleLocation.mirror_verification` now uses this via `allOf` instead of the bare `MirrorVerification` ref. A mirror-verification naming one file, or three, is rejected at the schema layer — no semantic check needed for that half. *Cross-reference consistency*: new **semantic check #23** requires, for both bundle files, `artifact_set[f].bytes`/`.sha256` == `mirror_verification.per_file_verification[f].primary_sha256` (hash side) == the matching `AuditEvidenceArtifact`'s `.bytes`/`.sha256` (`import_manifest_artifact` for `process_import_manifest.json`, `evidence_artifact` for `future_input_access_trace.json`) — and `artifact_set.aggregate_sha256` == `mirror_verification.primary_aggregate_sha256` (both describe the same two files on the primary copy).

**Verified this round** (scratch validator, see §14): a bundle whose `mirror_verification.per_file_verification` names only `process_import_manifest.json` (missing the second file) is rejected at the schema layer. A bundle naming a third, unrelated file is rejected at the schema layer. A bundle where every file is present but `future_input_access_trace.json`'s `mirror_verification` `primary_sha256` differs from `artifact_set`'s recorded `sha256` for that file is rejected by check #23. A bundle where `import_manifest_artifact.bytes` differs from `artifact_set["process_import_manifest.json"].bytes` (same hash, different byte count) is rejected by check #23. A fully self-consistent bundle — matching bytes/hashes across all three references, correct `aggregate_sha256` — validates.

### 4.6 Round 12 (item 2): `QUALIFICATION_PENDING` had no append-only path to `QUALIFIED`

**Problem identified (user's exact repro):** §4.4 gave `qualification_status` a legal `QUALIFICATION_PENDING` value, but never gave it anywhere to GO. Once a bundle finishes mirroring and all four research gates are (still) `PASS`, the honest next state is `QUALIFIED` — but the attempt record that says `QUALIFICATION_PENDING` is already written, hash-chained (`record_hash` covers the whole body including `qualification_status`), and append-only by construction: editing it in place breaks the chain and violates FR-35. The obvious alternative — append a brand-new `RFwdAdapterQualificationRecord` with `qualification_status=QUALIFIED` — fails for a structural reason, not merely a stylistic one: round 10 requires `record_id` be an **independently pre-minted UUID**, and `bundle_location.bundle_relative_root` is **keyed by that UUID** (`r_fwd_qualification/<record_id UUID>/`). A new record needs a new UUID, which would point `bundle_relative_root` at a bundle path that was **never actually written** — the evidence that really finished mirroring lives at the ORIGINAL attempt's path. There was no `supersedes_record_hash`, no stable cross-record attempt identifier, and no way to say "the bundle at path X, which attempt Y already described, has now finished."

**Correction — mirror the run-mirror-recovery pattern exactly (user's suggested design):**

- **`record_id` is the stable ATTEMPT identifier.** It already was independently pre-minted (round 10) and never derived from anything — round 12 makes explicit that it is also never REISSUED across an attempt's lifecycle. The attempt record itself (`RFwdAdapterQualificationRecord`, now `entry_kind="attempt"`) remains fully immutable once written — round 12 changes nothing about its own shape's finality.
- **New `RFwdQualificationResolutionEvent`** (`entry_kind="resolution"`) is a second, append-only entry shape sharing the SAME hash-chained ledger stream and sequence space as attempts (`r_fwd_adapter_qualification_ledger.jsonl` is now a mixed stream, exactly like `collector_ledger.jsonl` already mixes `run`/`mirror`/`unlock`/etc. `LedgerEvent`s under one `event_type`-discriminated chain). It carries `resolves_attempt_record_id` + `resolves_attempt_record_hash` (binding to the ORIGINAL attempt's stable id AND its exact immutable bytes — the same two-part binding `LedgerEvent`'s `mirror` payload uses via `original_receipt_sha256`), `previous_qualification_status` (`const QUALIFICATION_PENDING` — the only resolvable starting state), `new_qualification_status` (`const QUALIFIED` — one-directional, symmetric with `LedgerEvent`'s own mirror-event forbidding a `VERIFIED`→`PENDING` regression), and the NOW-COMPLETE `mirror_verification` for that same bundle.
- **`RFwdQualificationLedgerEntry`** is the new `oneOf[RFwdAdapterQualificationRecord, RFwdQualificationResolutionEvent]` wrapper for validating an arbitrary ledger line — mirrors the existing `RunReceipt = oneOf[RunReceiptSuccess, RunReceiptFailure]` pattern.
- **Effective qualification status is a derived join**, never a literal field read in isolation: `effective_qualification_status(attempt) = attempt.qualification_status` if it is already `QUALIFIED`/`QUALIFICATION_FAILED` (terminal); otherwise, for `QUALIFICATION_PENDING`, it is `QUALIFIED` if the latest resolution event referencing that exact `(record_id, record_hash)` exists, else it stays `QUALIFICATION_PENDING`. This is computed by whoever resolves an `r_fwd_qualification_ref` (or otherwise needs an attempt's status), exactly as `HealthSummary` derives `effective_persistence_status` by joining a `RunReceiptSuccess` with the latest `mirror` `LedgerEvent` for it (§7) — never written back onto the immutable attempt.
- **Semantic check #10 is corrected accordingly** (it already resolved `r_fwd_qualification_ref` by `record_hash`, but round 11 left it reading the attempt's literal `qualification_status`): it now requires the referenced attempt's EFFECTIVE status be `QUALIFIED`. **New semantic check #24** requires a resolution event's `resolves_attempt_record_hash` actually resolve to a real attempt with `entry_kind="attempt"` and (at write time) `qualification_status=QUALIFICATION_PENDING`, and reapplies §4.5/check #23's three-way bytes/hash consistency to the resolution's own `mirror_verification` against that attempt's `bundle_location.artifact_set` — a resolution cannot silently attest to different bytes than the attempt it resolves described.
- **A resolution can never legally be first**: `RFwdQualificationResolutionEvent.sequence` has `minimum:2` (not 1, unlike attempts) — schema-structural, not deferred to a semantic check, since a resolution always resolves something earlier in the chain.

**Verified this round** (scratch validator, see §14): a `QUALIFICATION_PENDING` attempt (four gates PASS, bundle PENDING) plus a resolution event referencing it by stable `record_id`+`record_hash`, with the bundle now `VERIFIED`, both validate; hand-computing `effective_qualification_status` over the pair yields `QUALIFIED` even though the attempt's own literal field still reads `QUALIFICATION_PENDING`. The same attempt with NO resolution event stays effectively `QUALIFICATION_PENDING`. A resolution event whose `resolves_attempt_record_hash` points at the wrong hash does not resolve the real attempt (check #24). A resolution event at `sequence=1` is rejected at the schema layer. A resolution attesting to bundle bytes different from what the attempt described is caught by check #24's reapplied three-way consistency. The round-11 attempt shape (no `entry_kind`) is now rejected — `entry_kind` is required.

**The `effective_qualification_status(attempt) = attempt + latest resolution event` derivation above is superseded by round 13 — see §4.7.** It correctly fixed how an ATTEMPT's own status resolves, but left the question "which resolution does a REFERENCING receipt rely on" to be answered dynamically ("the latest one") rather than pinned — reintroducing, one level down, the exact bug this whole append-only-reference design exists to prevent (§4.3). `RFwdQualificationResolutionEvent` itself, the `entry_kind` discriminator, `RFwdQualificationLedgerEntry`, `sequence minimum:2`, and check #24 are all unaffected and remain current; only how a *receipt* resolves *which* resolution it relied on changes.

### 4.7 Round 13 (P1 blocker, user's exact repro): a referencing receipt must pin the SPECIFIC resolution event it relied on, not resolve "the latest" one

**Problem identified:** §4.6 fixed how an ATTEMPT's own effective status resolves (attempt + latest resolution event, joined dynamically) — but a run receipt's `r_fwd_qualification_ref` still only pinned the ATTEMPT, by `record_id`+`record_hash` (round 9). It never pinned WHICH resolution event, if any, justified treating that attempt as effectively `QUALIFIED`. Concretely: suppose a run receipt R is written referencing attempt A while A is still `QUALIFICATION_PENDING` (no resolution exists yet) — R's own validity should be judged by what evidence existed at the moment R was written. But because check #10 (round 11/12) resolved effective status by scanning for "the latest resolution event referencing A" at *validation* time, not *write* time, re-checking the same immutable R at two different points — once before A's resolution is appended, once after — could yield two different verdicts for byte-identical evidence. That is precisely the "future append must not reinterpret already-written evidence" violation §4.3 exists to prevent (round 9's own stated rationale, verbatim), now leaking back in through the one sub-reference round 9 never had to consider, because attempts could not be `QUALIFICATION_PENDING` before round 11 introduced that value.

**Correction (user's suggested design):** `RFwdQualificationRef` gains `resolution_record_hash` (nullable), pinning the EXACT `RFwdQualificationResolutionEvent` a receipt relied on, by immutable hash, exactly as `record_hash` already pins the attempt:

- **`resolution_record_hash = null`** iff the referenced attempt's OWN `qualification_status` was already `QUALIFIED` at attempt-write-time — nothing to pin, and structurally nothing *could* exist to pin, since `RFwdQualificationResolutionEvent.previous_qualification_status` is `const QUALIFICATION_PENDING` (no resolution event can exist for an attempt that was never `PENDING`).
- **`resolution_record_hash` = a real resolution's `record_hash`** iff the referenced attempt's OWN `qualification_status` was `QUALIFICATION_PENDING` at attempt-write-time.

**Semantic check #10, rewritten again:** resolves the attempt by `(record_id, record_hash)` as before; then branches on the attempt's *own* `qualification_status` (never a dynamically-derived "effective" status): `QUALIFIED` → `resolution_record_hash` must be null, resolves directly; `QUALIFICATION_PENDING` → `resolution_record_hash` must resolve to a real resolution event that (a) has `entry_kind="resolution"`, (b) resolves THIS exact attempt (`resolves_attempt_record_id`/`resolves_attempt_record_hash` matching), (c) has `new_qualification_status=QUALIFIED`, and (d) has `generated_at` no later than the receipt's own `completed_at` — an explicit temporal check, on top of the causal ordering hash-pinning already implies, per the user's instruction; `QUALIFICATION_FAILED` → always rejected (unchanged). A `QUALIFICATION_PENDING` attempt referenced with `resolution_record_hash=null` is rejected outright — **there is no longer any way to construct a reference that becomes valid only later**: a valid reference can only ever cite a resolution that already exists, by its exact, unchangeable content, at the moment the reference itself is written.

**Verified this round** (scratch validator, see §14): the exact repro — a reference to a `QUALIFICATION_PENDING` attempt with `resolution_record_hash=null` — is rejected. Re-validating that identical reference again, *after* a resolution for that same attempt is later appended to the ledger, still rejects it (the verdict never changes, because the reference itself never pinned that resolution) — this is the direct fix, demonstrated by construction rather than merely asserted. A reference correctly pinning a matching resolution resolves, consistently, on every re-validation. A dangling `resolution_record_hash` (no matching resolution event) is rejected. A `resolution_record_hash` pinning a resolution that resolves a *different* attempt is rejected. A `resolution_record_hash` supplied for an attempt that was already `QUALIFIED` at write time (over-specified, nonsensical — nothing needed resolving) is rejected. A resolution whose `generated_at` is *after* the receipt's own `completed_at` is rejected (temporal ordering); the same resolution is accepted when the receipt's `completed_at` legitimately postdates it. A `QUALIFICATION_FAILED` attempt is rejected regardless of `resolution_record_hash`'s value.

---

## 5. R-FWD adapter qualification — one-time model itself (unchanged from revision 7, inlined)

FR-25's 255-month parity suite qualifies the adapter **once** (Phase D). Once `QUALIFIED`, future runs use the certified code directly without re-reading `exec_ret`/`obs_alpha` — the adapter's normal execution path never imports either file, making FR-28 compliance structural, verified by `future_input_access_audit` (§4). `QUALIFICATION_FAILED` is permanent-until-requalified for that adapter code, not a per-date condition. Decision-time-only universe definition (unchanged): `listed_ok(as_of) & adv20(as_of) ≥ 1,000,000` — the same expression P-B already uses. `Panel.tier_valid["100萬"]` is only ever the qualification's comparison target, never read by a live run.

---

## 6. Mirror recovery — now carries full per-file evidence, not a bare aggregate hash (blocker 2)

**Problem identified (user's exact repro):** a `mirror` ledger event with `previous_status=PENDING`, `new_status=VERIFIED`, and only `mirror_aggregate_sha256` — zero per-file evidence — validated successfully. A recovered run's `effective_persistence_status=COMMITTED` (§7 below) therefore rested on strictly weaker evidence than the initial commit, which requires full 10/12-file `MirrorPerFileVerificationPOnly`/`Comparable` completeness.

**Correction:** the `mirror` event payload's `mirror_aggregate_sha256` field is replaced with `mirror_verification`, typed as the **full** `MirrorVerification` object (the same type the initial commit uses) — reused verbatim, so its own `VERIFIED`-status rule (every `per_file_verification` entry `match=true` with a real `mirror_sha256`, both aggregates non-null) applies identically to a recovery event. `mirror_verification=null` remains legal only when `new_status=PENDING` (a logged, unsuccessful recovery attempt).

### 6.1 Round 9 (blocker 3): recovery must bind to the original receipt's actual hash VALUES, not just its filenames

**Problem identified:** round 8's check #11 compared only **file-name sets**. A recovery event could present the same 10 filenames carrying entirely different `primary_sha256` values and pass the schema plus checks #7, #9, and #11 — meaning the "recovered" evidence need not describe the same bytes the original run committed.

**Correction, two parts:**

*Schema* — the `mirror` payload gains two required fields: `original_receipt_sha256` (sha256 of the original, immutable `run_receipt.json`, binding the recovery to specific bytes rather than a `run_id` alone) and `original_output_aggregate_sha256` (the original receipt's own output aggregate). The round-8 payload shape is now rejected outright for lacking them.

*Semantic check #11, rewritten* — for **every** file `f`, `mirror_verification.per_file_verification[f].primary_sha256` must equal `original_receipt.output_hashes[f].sha256`; and both `primary_aggregate_sha256` and `mirror_aggregate_sha256` are **recomputed** from the per-file hashes and compared. Filename-set equality is retained as a precondition, not the whole check.

**Verified this round:** the user's exact defect — same filenames, different `primary_sha256` — is now rejected (`a.json: recovery primary_sha256 9999... != original output_hashes sha256 1111...`). A recovery whose per-file primary hashes match the original passes. A tampered `primary_aggregate_sha256` is caught by recomputation. The round-8 payload shape (no original-receipt binding) is rejected; the round-9 shape validates; a still-`PENDING` attempt with `mirror_verification=null` remains legal.

---

## 7. Mirror recovery vs. `HealthSummary` — `effective_persistence_status` (unchanged from revision 7, inlined)

```
effective_persistence_status(receipt) =
    COMMITTED   if receipt.persistence_status == COMMITTED
    COMMITTED   if receipt.persistence_status == PENDING_MIRROR
                   AND the latest "mirror" LedgerEvent for receipt.run_id has payload.new_status == VERIFIED
    FAILED      if receipt.persistence_status == FAILED
    PENDING_MIRROR   otherwise
```
Computed by whoever builds `HealthSummary`, joining receipt + ledger — never written back onto the immutable receipt. `HealthSummary`'s `monthly_eligible_count`/`comparable_identity_count`/`last_success_run_id`/`pending_mirror_count` derive from this, not the receipt's own frozen field (round-6 bug: recovery could never be counted under a literal-field reading). Semantic check #8, three-part verification (pre-recovery exclusion, round-6 bug reproduced and caught, round-7 fix verified) — **now additionally gated by §6's per-file completeness** (check #11): a "recovery" lacking full evidence cannot legitimately flip `effective_persistence_status` even before check #8 runs, since it would fail #11 first.

---

## 8. `projected_live_receipt_bytes` → `LiveReceiptProjectionManifest` — fully auditable (blocker 3)

**Problem identified:** the round-7 field was a bare, non-negative integer — `0` was schema-legal, and the only enforcement was that the bootstrap *formula* used the field, never that the field's *value* was correctly derived from anything. No placeholder policy, no real inputs, and no reconstructible projected object were preserved.

**Correction — `LiveReceiptProjectionManifest`, replacing the bare integer entirely:**

```json
{
  "projection_only": true,
  "projection_template": {
    "template_version": "v1",
    "repo_relative_path": "scripts/identity_collector/live_receipt_projection_template.py",
    "git_blob_sha1": "<40-hex Git object id, retrievable via `git cat-file blob`>",
    "content_sha256": "<hash>"
  },
  "placeholder_policy": {
    "run_id_placeholder": "<64 zeros, const>",
    "identity_epoch_placeholder": "epoch-0000000000000000 (const)",
    "collector_version_placeholder": "<64 zeros, const>",
    "input_bundle_sha256_placeholder": "<64 zeros, const>",
    "attempted_input_manifest_placeholder": "<fixed all-AVAILABLE manifest, const -- the LARGEST form, keeping the projection conservative>",
    "started_at_placeholder": {"utc": "1970-01-01T00:00:00Z", "local_taipei": "1970-01-01T08:00:00+08:00"},
    "completed_at_placeholder": "<same fixed value>",
    "mirror_hash_placeholder": "<64 zeros, const>"
  },
  "actual_inputs": {
    "as_of": "<one of the 3 dry-run dates, MUST equal the enclosing receipt's>",
    "persistence_status": "COMMITTED", "identity_status": "<P_ONLY_EVIDENCE|COMPARABLE_IDENTITY>",
    "monthly_status": "<...>", "source_mutation": "<bool>", "revision_of": "<hash or null>",
    "capture_process_started": true,
    "process_isolation": {"production_capture_pid": "<int>", "r_fwd_pid": "<int or null>", "bt_bundle_absent_from_production_process": true},
    "primary_root": "<real>", "mirror_root": "<real>",
    "source_hashes": "<this attempt's real SourceHashManifest>",
    "code_hashes": "<this attempt's real CodeHashManifest>",
    "collector_config_hash": "<real>", "collector_schema_sha256": "<real>",
    "output_hashes_equivalent": "<same object as payload_files>",
    "announcement_date_pit_status": "BLOCKED if P_ONLY_EVIDENCE, VERIFIED if COMPARABLE_IDENTITY (round 11, see §8.4)",
    "r_fwd_qualification_ref": "<RFwdQualificationRef or null>",
    "temp_cleanup_status": "<CLEANED|NOT_APPLICABLE>"
  },
  "projected_object_sha256": "<sha256_hex(canonical_json(assembled, sort_keys=true))>",
  "projected_object_bytes": "<len of that same canonical JSON, minimum:500 sanity floor>"
}
```

Every placeholder value is a schema `const` — fixed and disclosed, not chosen ad hoc per attempt. `projection_only: const true` structurally marks this as never a `RunReceipt`.

### 8.1 Round 9 (blocker 4): the inputs are now genuinely exhaustive, and the template is genuinely obtainable

**Problem identified, two parts.** (a) `actual_inputs` was missing `as_of`, the three receipt status fields, `source_mutation`/`revision_of`, `capture_process_started`, `process_isolation`, and `temp_cleanup_status` — while `placeholder_policy` was missing `collector_version`, `input_bundle_sha256`, and `attempted_input_manifest`. Together they did **not** cover `RunReceiptSuccess`'s required-key set, so the round-8 claim "recomputable from `placeholder_policy` + `actual_inputs` alone" could not have held. (b) `projection_template_sha256` was a bare hash — a third party could verify they had the right template only if they already had it, with no path, no version, and no way to fetch it.

**Correction:** `actual_inputs` now carries every `RunReceiptSuccess` field knowable at dry-run time (including `r_fwd_qualification_ref`, added to the live receipt this same round — omitting it would systematically under-size every `COMPARABLE_IDENTITY` run), and `placeholder_policy` covers every remaining one. `persistence_status` is `const "COMMITTED"` deliberately: that is the largest live-receipt form, so sizing stays conservative. `projection_template_sha256` is replaced by `ProjectionTemplateIdentity` — `template_version` + `repo_relative_path` + `git_blob_sha1` + `content_sha256`, so the assembly algorithm is retrievable from the repository (`git cat-file blob <sha1>`) independently of working-tree state.

**Third part — the projection must describe its own attempt.** Nothing previously required `actual_inputs` to agree with the `CapacityDryRunReceipt` it sits inside; a projection for a different date, mode, or payload would have silently mis-sized capacity. **New semantic check #16** requires `actual_inputs.as_of == receipt.as_of`, `actual_inputs.identity_status == receipt.sizing_mode`, and `actual_inputs.output_hashes_equivalent == receipt.payload_files`. Verified this round rejecting a projection that disagreed on all three.

**Independent recomputability** (check #12, verified with real hashing): assemble the `RunReceiptSuccess`-shaped dict from only `placeholder_policy`+`actual_inputs` per the pinned template, compute its canonical sha256/byte-length, compare to the stored values; tampering with either stored field is caught. `CapacityDryRunReportAttempt.attempt_total_bytes = receipt.payload_bytes + receipt.live_receipt_projection.projected_object_bytes`.

### 8.2 Round 10 (blocker 2): the projection could describe an object that could never exist

**Problem identified:** `actual_inputs` accepted `identity_status=COMPARABLE_IDENTITY` alongside `r_fwd_qualification_ref=null`, `source_hashes.r_fwd=null`, `code_hashes.r_fwd_adapter_sha256=null`, and a P-only output manifest. The user mechanically confirmed such a manifest passed the schema. Two consequences, both bad: the assembled object could **never** validate as a `RunReceiptSuccess` (so the "projection of a live receipt" was a projection of nothing real), and it was **systematically smaller** than a genuine Comparable receipt — under-sizing capacity in precisely the mode that needs the most space.

**Correction, two parts.** *Schema*: `actual_inputs` now carries `RunReceiptSuccess`'s own `identity_status` conditional verbatim — Comparable requires a non-null qualification ref, non-null `r_fwd` source hashes, a non-null adapter hash, and the 12-file Comparable output manifest; P-only requires all of those null and the 10-file manifest. *Semantic*: **check #12 is extended** to validate the **assembled object** against a new `ProjectedRunReceipt` definition (structurally identical to `RunReceiptSuccess` in every required key and conditional, differing only in that placeholder-supplied fields carry the fixed placeholder values). Recomputing a hash of a structurally invalid object was never sufficient.

Verified: the user's exact repro is rejected at the schema layer; a Comparable projection with a P-only manifest is rejected; and at the semantic layer, a manifest whose hash **recomputes correctly** but whose assembled object is an invalid receipt is now caught by check #12 — the case that would otherwise have slipped through both layers.

### 8.3 Round 10 (blocker 3): placeholders were anti-conservative

**Problem identified:** several placeholders were the *shortest* legal form, not the longest — `disk_free_bytes=0` (1 digit where a real value runs to 19), and `1970-01-01T00:00:00Z` (20 chars) where a real timestamp with microseconds and a numeric offset is 32. A projection built from these under-states the real receipt, which is the wrong direction for capacity planning.

**Correction:** every placeholder is now the **measured maximum-length legal value** for its field, and `live_timestamp_format` (`%Y-%m-%dT%H:%M:%S.%f%:z`) is frozen in the policy as a real constraint on the collector's serializer — so the placeholder is length-exact against the live form rather than guessing at it. A `conservatism_note` is stored in-band so the property travels with the artifact. **New semantic check #18** re-derives each placeholder's length against its field's maximum and fails if any is shorter. Verified: the round-9 placeholders are rejected at both layers.

**Legality constrains "longest," disclosed:** the first draft of this policy used `disk_check_status=UNKNOWN` (the longest enum member) with a maximum `disk_free_bytes` — but `PreflightObservation` forces `disk_free_bytes=null` whenever the status is `UNKNOWN`, so that combination is illegal. This round's own validator caught it. Measured across the legal pairs: `UNKNOWN`+null serializes to 54 bytes, `OK`+int64-max to 64, `LOW`+int64-max to 65. The placeholder uses `LOW`.

### 8.4 Round 11 (item 3): the "maximum" placeholders were asserted, not schema-provable, and the Comparable projection sized against the wrong PIT status

**Problem identified, two parts.** (a) §8.3's `lock_holder_pid=4294967295` and `disk_free_bytes=9223372036854775807` were chosen as "the measured maximum" for those fields — but `PreflightObservation` (through round 10) declared no `maximum` for either. A claim that a value is *the* maximum, made against a field with no declared ceiling, is unfalsifiable: nothing in the schema prevented a real preflight observation from reporting a larger PID or a larger free-space figure, which would have silently made the projection anti-conservative again — exactly the failure mode §8.3 itself was correcting. (b) `actual_inputs.announcement_date_pit_status` was `const:"BLOCKED"` unconditionally, inherited from round 8 and never revisited when round 9/10 made `actual_inputs` otherwise exhaustive and identity-status-conditional. But the LIVE `RunReceiptSuccess` type (§12) requires this field equal `"VERIFIED"` (8 chars) whenever `identity_status=COMPARABLE_IDENTITY` — `"BLOCKED"` (7 chars) is not merely a different value, it is the value a Comparable-mode live receipt is schematically **forbidden** from carrying. Projecting it anyway under-sized every `COMPARABLE_IDENTITY` capacity estimate, in exactly the mode NFR-7(a) singles out as needing R-FWD artifacts included.

**Correction, two parts.** *PID/disk maximum*: `PreflightObservation.lock_holder_pid` gains `maximum:4294967295` (a Windows DWORD PID ceiling — Task Scheduler, per FR-47, is this collector's only target scheduler) and `disk_free_bytes` gains `maximum:9223372036854775807` (int64 max, the ceiling any 64-bit free-space API can report). The placeholder policy's chosen values now equal declared field maxima rather than merely asserting they do — **semantic check #18 is extended** to verify that equality explicitly, not just that the placeholder is "a long value." *Comparable-mode PIT status*: `actual_inputs.announcement_date_pit_status` (and the identical field on `ProjectedRunReceipt`, §8.2) is changed from an unconditional const to a two-value enum (`BLOCKED`/`VERIFIED`), tied to `identity_status` by the same `allOf` block that already conditions `source_hashes`/`code_hashes`/`r_fwd_qualification_ref`/`output_hashes_equivalent` — `P_ONLY_EVIDENCE` still projects `BLOCKED`, `COMPARABLE_IDENTITY` now projects `VERIFIED`. **This is a sizing decision, not a Gate C-R decision**: the LIVE `RunReceiptSuccess.announcement_date_pit_status` stays hard-locked to `const:"BLOCKED"`, and identity_status=COMPARABLE_IDENTITY there remains structurally unsatisfiable (§12, unchanged) — no live Comparable receipt can exist under this schema revision regardless of this fix. The capacity projection's job is different: NFR-7(a) requires the bootstrap dry-run to size a Comparable-mode receipt *as if* Gate C-R had already unblocked, so operators aren't caught short on capacity the day it does. Sizing that hypothetical receipt against the value it is actually defined to carry (`VERIFIED`) is the only self-consistent choice — sizing it against `BLOCKED`, a value that receipt could never legally carry, was never a real receipt shape to begin with.

**Verified this round** (scratch validator, see §14): a `lock_holder_pid` placeholder of `4294967296` (one past the new maximum) is rejected at the schema layer. A `disk_free_bytes` placeholder of `9223372036854775808` (one past int64 max) is rejected at the schema layer. `PreflightObservation.lock_holder_pid=4294967295` (exactly the maximum) validates. A `COMPARABLE_IDENTITY` `actual_inputs` carrying `announcement_date_pit_status="BLOCKED"` is now rejected (round 10 accepted it — reproduced first, then shown fixed). A `COMPARABLE_IDENTITY` `actual_inputs` carrying `"VERIFIED"` validates, and the assembled object continues to pass `ProjectedRunReceipt` (check #12). A `P_ONLY_EVIDENCE` `actual_inputs` carrying `"VERIFIED"` (the value only Comparable may use) is rejected.

---

## 9. Durable evidence identity (round 10, blocker 4)

**Problem identified, four parts:** (a) `AuditEvidenceArtifact.relative_path` was relative to nothing specified, so it identified no resolvable file and belonged to no defined artifact set; (b) `ProjectionTemplateIdentity` pinned only a Git blob id — a loose object not reachable from any ref is eligible for garbage collection, so the reference could silently evaporate; (c) a hash chain proves ordering but **not** completeness: deleting the tail leaves a shorter, still internally-consistent chain; (d) aggregates were repeatedly described as "recomputed" without the canonicalization ever being defined, so two implementations could disagree on what the correct aggregate is.

**Corrections, four new definitions:**

- **`QualificationBundleLocation`** — anchors evidence at `r_fwd_qualification/<record_id UUID>/` under **both** roots, with a **closed** two-file `artifact_set` (`process_import_manifest.json`, `future_input_access_trace.json`) matching the two `artifact_role` values, `dual_copy_required: const true`, and a full `MirrorVerification`. A `QUALIFIED` record now additionally requires that bundle to be mirror-`VERIFIED`. **Check #19** verifies the bundle root's UUID equals `record_id` minus its prefix, and that each artifact's path is the canonical filename for its role. Round 11 closes this further still — see §4.5 and §9.1.
- **`ProjectionTemplateIdentity.reachable_commit_sha1` + `durable_copy`** — a commit reachable from a ref whose tree holds the blob at `repo_relative_path` (GC-safe), plus a byte-identical copy inside the dual-copy evidence roots (so the template survives even if the repository does not). **Check #21** verifies reachability and `durable_copy.sha256 == content_sha256`.
- **`LedgerHeadCheckpointPayload` / `LedgerHeadCheckpointRecord`** — pins `head_sequence` + `head_record_hash` + `record_count` for either ledger. **Check #20** requires `record_count == head_sequence` and that the on-disk tail matches the checkpoint. Verified detecting a truncated ledger — the failure a hash chain alone cannot catch. Round 10 asserted this was "itself dual-copy durable" in prose only, with no field enforcing it; round 11's first fix reintroduced a content-hash/file-hash self-reference bug in the process of fixing that; round 12 splits the payload (the physical file) from the record (the external receipt describing it) — see §9.1 (round 11, superseded) and §9.2 (round 12, current).
- **`AggregateHashFormula`** — freezes `sha256_hex(canonical_json({relative_path: member_sha256}, sort_keys=true))` with the canonical-JSON rule, a member selector (the same formula yields the primary and mirror aggregates from different members of one `per_file_verification` map), the sort rule, and the encoding. Embedded in each qualification record so it stays self-describing. A drifted `canonical_json_rule` is rejected. Round 10's `member_selector` was a single enum pick; see §9.1 for why round 11 replaces it with three simultaneous consts.

### 9.1 Round 11 (item 4): the checkpoint had no enforced home, and one formula object couldn't describe the three aggregates a record actually holds

**Superseded by §9.2 (round 12) for the checkpoint half of this section** — the `content_sha256`/`storage.mirror_verification` construction described immediately below turned out to reintroduce a self-reference bug (the user's round-12 repro). Kept verbatim as the historical record of what round 11 actually shipped and why it was wrong, per this project's own discipline of not leaving a corrected section looking as if it were always right (§4.1a, §6.1, §8.2 all do the same). The `AggregateHashFormula` three-selector fix in the second half of this section is unaffected and remains current.

**Problem identified, two parts.** (a) `LedgerHeadCheckpoint` was defined and referenced nowhere else in the schema — no other type required it, no field said where its file lives, and it carried no hash identity of its own. Round 10's own description claimed it was "itself dual-copy durable," but nothing enforced that claim; it was prose describing a mechanism the schema did not build. (b) `AggregateHashFormula.member_selector` was a single field holding one of three enum values (`ArtifactFileEntry.sha256` / `MirrorFileComparisonEntry.primary_sha256` / `MirrorFileComparisonEntry.mirror_sha256`). But as of §4.5's `artifact_set.aggregate_sha256` addition, one `RFwdAdapterQualificationRecord.aggregate_hash_formula` now needs to self-describe **all three** aggregates the record actually contains (`artifact_set.aggregate_sha256`, `mirror_verification.primary_aggregate_sha256`, `mirror_verification.mirror_aggregate_sha256`) — a formula object holding only one selector cannot describe the other two the same record carries.

**Correction, two parts.** *Checkpoint storage and identity*: `LedgerHeadCheckpoint` gains `content_sha256` (`sha256_hex(canonical_json({schema_version, ledger_name, head_sequence, head_record_hash, record_count, checkpointed_at}, sort_keys=true))` — over exactly those six content fields, excluding itself and the two new fields below, so there is no self-reference), `storage` (`relative_path`, fixed per `ledger_name` via `allOf` to `<ledger_name>.checkpoint.json`, plus `dual_copy_required: const true` and a `mirror_verification` closed to exactly one file), and `protection_scope` — a disclosed, `const`-shaped statement of what the mechanism does and does not cover (below). **Check #20 is extended**: beyond `record_count == head_sequence` and on-disk tail matching, it now recomputes `content_sha256` and requires `storage.mirror_verification`'s sole `per_file_verification` entry to be keyed by `storage.relative_path` with `primary_sha256` (and `mirror_sha256`, when `VERIFIED`) equal to `content_sha256`.

*The narrowed claim (user instruction, item 4):* a hash chain plus a head checkpoint proves the ledger has not been shortened **without also rewriting the checkpoint** — that is what check #20 catches. It proves nothing if an actor rewrites **both** the ledger tail and this checkpoint together to an earlier, internally-consistent state: `head_sequence`/`head_record_hash`/`record_count`/`content_sha256` would all still agree with each other and with the rolled-back ledger tail, just at an earlier point in history. This mechanism has no external, independently-controlled anchor (no third-party timestamping, no WORM storage, no append log outside the collector's own control), so it structurally cannot detect a coordinated rollback of both artifacts at once. `protection_scope.detects`/`does_not_detect`/`note` are `const` precisely so this narrowed scope is carried by every checkpoint instance, not left only in this paragraph — the phrase "truncation-detectable" used elsewhere in this document must be read against this scope, not beyond it.

*Three-selector `AggregateHashFormula`*: `member_selector` (one enum pick) is replaced by `selectors`, an object of three independently-fixed consts — `artifact_selector`, `primary_selector`, `mirror_selector` — each pinned to its own `ArtifactFileEntry.sha256` / `MirrorFileComparisonEntry.primary_sha256` / `MirrorFileComparisonEntry.mirror_sha256` value. Nothing is actually "selected" per instance any more; all three are simultaneously frozen, so the one formula object embedded in a qualification record self-describes every aggregate that record holds.

**Verified round 11** (scratch validator): a `LedgerHeadCheckpoint` missing `storage`/`protection_scope`/`content_sha256` is rejected (round 10 shape). A checkpoint whose `storage.relative_path` doesn't match the fixed name for its `ledger_name` is rejected. A checkpoint whose `storage.mirror_verification` names two files instead of one is rejected. A checkpoint whose `content_sha256` doesn't match a recomputation over its six content fields is rejected. A checkpoint whose `storage.mirror_verification` per-file `primary_sha256` disagrees with `content_sha256` is rejected. A `protection_scope.does_not_detect` array edited to be empty (silently claiming full coverage) is rejected (`const` mismatch). An `AggregateHashFormula` still shaped with a bare `member_selector` string (round 10 shape) is rejected; one with `selectors` holding all three fixed consts validates. **What round 11's validator did NOT catch** (§9.2): none of these fixtures exercised the actual on-disk FILE's bytes separately from the record object — every fixture's "primary_sha256" was computed from the same six-field subset `content_sha256` also covered, so the self-reference bug was invisible to a validator that never modeled "what are the real file's bytes" as a distinct question. This is recorded because it is itself a lesson about validator design, not only about schema design.

### 9.2 Round 12: `LedgerHeadCheckpoint` split into `LedgerHeadCheckpointPayload` (the file) and `LedgerHeadCheckpointRecord` (the receipt describing it)

**Problem identified (user's exact repro):** round 11's `LedgerHeadCheckpoint` computed `content_sha256` over six of its own sibling fields (`schema_version`, `ledger_name`, `head_sequence`, `head_record_hash`, `record_count`, `checkpointed_at`), then required `storage.mirror_verification`'s per-file `primary_sha256`/`mirror_sha256` equal that `content_sha256` — but `storage` and `protection_scope` (and `content_sha256` itself) are fields on the SAME object. If "the checkpoint file" means this whole object — which is the natural reading, since nothing in round 11's schema said otherwise — then the file's real bytes include `storage`/`protection_scope`/`content_sha256`, and its real SHA256 is **not** `content_sha256`. The user constructed exactly this: a checkpoint that is schema-valid, whose `content_sha256` recomputes correctly from the six fields, whose `storage.mirror_verification` hash equals `content_sha256` (so round 11's check #20 would have passed it) — while the true on-disk `checkpoint.json` file's own SHA256 differs. This is the same self-reference class of bug §4.1a already fixed once for `record_id`/`record_hash` (a value cannot legitimately certify a file that also contains that value), reintroduced here because a NEW field pair (`content_sha256` + the file it allegedly identifies) recreated the same shape.

**Correction — split into two objects with disjoint roles**, per the user's suggested design (mirroring `CapacityDryRunReportAttempt.receipt`/`receipt_sha256`, and — for the "verify a file's bytes without embedding a self-hash" half — `AuditEvidenceArtifact`/`QualificationBundleLocation.artifact_set`):

- **`LedgerHeadCheckpointPayload`** — the six content fields, and ONLY the six content fields (`additionalProperties:false` closes the door structurally: nothing that looks like a self-hash can be smuggled in). This object, canonically serialized, IS the physical byte content written to `<primary_root>/<relative_path>` and `<mirror_root>/<relative_path>`. It carries no hash of itself, so there is nothing self-referential to define in the first place.
- **`LedgerHeadCheckpointRecord`** — a SEPARATE record (written alongside, at a sibling path, same discipline as `run_receipt.json` describing but never being the payload files it attests to): embeds a verbatim copy of `payload`, computes `payload_sha256`/`payload_bytes` over that embedded copy ALONE (excluding `storage`/`protection_scope`, which are not part of `payload`), and `storage.mirror_verification`'s per-file hash is checked against `payload_sha256` — now legitimately, because `payload_sha256` describes a disjoint object (the physical payload file) from this record's own bytes. This record's own bytes are not themselves recursively dual-copy-verified — the same design choice `run_receipt.json` makes: trust comes from atomic-write discipline (FR-34) plus independent recomputability of `payload_sha256` from the embedded `payload`, not from a further embedded self-hash. (Turtles have to stop somewhere; this project stops them at the same place `run_receipt.json` already does.)
- **Check #20 is corrected accordingly**: it recomputes `payload_sha256`/`payload_bytes` from the embedded `payload` field alone, checks `payload.record_count == payload.head_sequence` and on-disk tail matching (unchanged truncation logic, now nested under `.payload.`), and requires `storage.mirror_verification`'s sole per-file key equal `storage.relative_path` with `primary_sha256` (and `mirror_sha256` when `VERIFIED`) equal to `payload_sha256`.
- `protection_scope`'s narrowed claim (§9.1's "does NOT detect a simultaneous ledger+checkpoint rollback") is unchanged in substance, only relocated onto `LedgerHeadCheckpointRecord`.

**Verified this round** (scratch validator, see §14): `LedgerHeadCheckpointPayload` rejects an extra field shaped like a self-hash (`additionalProperties:false`). A well-formed `LedgerHeadCheckpointRecord` (embedded `payload` + correctly recomputed `payload_sha256`/`payload_bytes` + `storage.mirror_verification` whose per-file hash equals `payload_sha256`) validates and passes hand-run check #20. A record whose `payload_sha256` field is tampered (doesn't recompute from the embedded `payload`) is caught. Hashing the WHOLE outer `LedgerHeadCheckpointRecord` object confirms it is (correctly) different from `payload_sha256` — proving the schema no longer conflates "the record" with "the payload file," the exact conflation round 11 had. `storage.relative_path` mismatched against `payload.ledger_name`'s fixed name is rejected; a record missing `storage`/`protection_scope` is rejected.

---

## 9a. Capacity formula — current state, fully restated

```
attempt_total_bytes     = receipt.payload_bytes + receipt.live_receipt_projection.projected_object_bytes
bootstrap_bytes_per_run = ceil(1.5 × max(attempts[*].attempt_total_bytes))
```
The outer `ceil(1.5 × max(...))` shape has never changed across any round; only what `attempt_total_bytes` means has been corrected twice — round 6 added the receipt's footprint at all (previously payload-only), round 7 used the wrong receipt type's size (`CapacityDryRunReceipt` instead of the LIVE type), round 8 (this round) makes that LIVE-type projection fully auditable instead of an unaudited flat integer.

---

## 10. R-FWD PIT input datasets — full algorithm (unchanged from revision 7, inlined)

`HistoryBundle`'s 8 datasets consumed by `build_pit_stockdata`: `price`, `per`, `revenue`, `income`, `balance`, `cashflow`, `chip`, `shareholding`. Date-only cutoff (`_slice`, `date≤as_of`) for `price`/`per`/`revenue`/`chip`/`shareholding`; publish-lag cutoff (`_published`, `date+45days≤as_of`) for `income`/`balance`/`cashflow` —`PUBLISH_LAG_DAYS=45` is the same constant §12 hard-blocks `COMPARABLE_IDENTITY` over (open leak suspicion, 3 citations below).

Canonical serialization: columns sorted lexicographically; rows sorted `(stock_id, date)`; canonical CSV (`\n`, `%.10g`, empty-string NaN, UTF-8, no index); per-dataset then per-stock sha256 (fixed dataset order `price, per, revenue, income, balance, cashflow, chip, shareholding`); `r_fwd_pit_input_aggregate_sha256 = sha256_hex(canonical_json({stock_id: per_stock_sha256}, sort_keys=true))` over the decision-time universe (§5). Never `Panel.tier_valid`, never P-A/P-B directly.

---

## 11. Code identity — full hash table, inlined (blocker 4)

| Path | Callable | sha256 | git status |
|---|---|---|---|
| `core/score_store.py` | `screen_by_composite_at` (500), `score_row` (181) | `58de00f76481ea1ce13fd6fa2f946ac0b2f3dae641e1d80f9b56319345bc7874` | clean |
| `scripts/universe_screen_daily.py` | c2 full-pool, `listed_ok` (53, 166-168) | `529c8ea0e83fcf399b6e98175e3e4fe6fb8ced000322023cdb10bacb935a36ae` | uncommitted diff (Phase H) |
| `app.py` | `tab_fusion` (~1651-1701) | `2eb834c3f92c2bf951835aeadc86b985db76a6072216f09636d9e499874a2f6b` | modified, uncommitted, +992/−549 |
| `scripts/l4a_decision.py` | `compute_target_list` (120) | `74695d943c5bae9df5fb274c9a194f10b3004a688e8af1d37e32ba78a54de32e` | untracked, never committed |
| `core/scoring_manager.py` | `ScoringManager` | `aab73b7ff0891a4f45ac83f473866648729076fd5d6ed0b79a299fce8bba3dda` | modified, uncommitted |
| `core/fundamentals.py` | `FundamentalEngine` | `e88a1f16c7b299cbd9245558ed6f050cfd3ab1113af9b8a270dd7393122558c2` | modified, uncommitted |
| `core/valuation.py` | `ValuationEngine` | `3d1bce099b1b7c3471929194b9bffd1f9f29616bf57677a40224af94d2d8e014` | clean |
| `core/advisor.py` | `InvestmentAdvisor.advise` (83, composite arithmetic at 121) | `e4eb24de8344776ea9e617f31e2af8524e81e3e9cb0893512a2481ffa293574b` | modified, uncommitted |
| `core/backtest.py` | `build_pit_stockdata` (346) | `3b0f8e9ebe97ffd1e184a4fec0a4cbdc1b8af15d47fa3974a167fac9802d3fb2` | clean |
| `core/regime.py` | `regime_multipliers` (used in `advise()` before composite sum) | `4d3fcf868c06bbde708ea1da6142a65dc2a2989e79e75c435543cd3aec245ddd` | clean |
| `core/technical_analysis.py` | `TechnicalEngine` (`_tech`) | `ba63b5e913a25967d8714fb919ea9f6c4913652e6ecb61305fecaa887947b3ee` | clean |
| `core/data_provider.py` | `DataProvider` | `93f835b6155fcf30b825a1170e0153da5d58f5db683489d62dee14819dc88eef` | modified, uncommitted, +55/−14 |
| `core/industry_value.py` | `industry_value_pct` | `81789194a0006132cd0766be955ebe341bdf92f0783e2d6670da8cfd03f951e6` | clean |
| `beat_0050/strategies/high52_lab.py` | `Panel`, `HistoryBundle` (unrelated to production) | `09fbe6efa34e5c6e8481adafddad58d073970227c7804c8a269e6ed29b0f72f8` | clean |
| `beat_0050/strategies/dual100_lab.py` | `dual_confirm_mask` | `526164361c54cd62ac38fdbb3661eeca658e0fec040385579fee17fe0b47f7f0` | clean |
| `core/canonical_universe.py` | canonical universe helpers | `a717f1f8e1c04efe4def04ae317e0fbd10d0340dbc6c06222eff35499e54e68b` | clean |
| `scripts/lab_paths.py` | `resolve_realbody` | `8cb132fc436d26f41c579932f636ecfa947a27f964a728f01a8d5e453528d0b0` | clean |
| `beat_0050/realbody/build_arm_panel.py` | arm-panel construction chain | `9f2fcb61581919153e3cd1f81e123f908106ba36aca0a297e0d6e5af9dbbd3b3` | modified, uncommitted |
| `build_cache.py` | `load_universe_from` (184) | `31d4c328348436f746f7353a3dddac5a2575f6a2a64830d36f4cf1a47086d62b` | clean |

(`ranking_adapter.py`'s hash cannot exist yet — no code written, Phase C not authorized. Module path fixed: `scripts/identity_collector/ranking_adapter.py`.)

**`collector_version` formula:**
```
collector_version = sha256_hex(canonical_json({
  "collector_code_files": {rel_path: sha256_of_file(f) for f in sorted(collector_code_files)},
  "collector_schema_sha256": <sha256 of collector_schema.json>,
  "resolved_callables": <full CodeHashManifest>,
  "identity_defining_constants": {
    "adv_floor_c2": 1000000, "fusion_pct": 20, "top_n": null, "p_a_top_limit": 3000,
    "r_fwd_min_cov": 1.0, "r_fwd_canonical": false, "tolerance": "1e-12",
    "listed_ok_data_start_cutoff": "2019-01-10", "publish_lag_days": 45,
    "dual100_cov_min_effective": 1.0
  }
}, sort_keys=true))
```

---

## 12. `PUBLISH_LAG_DAYS=45` / Gate C-R (unchanged from revision 6/7, inlined)

`RunReceiptSuccess.announcement_date_pit_status` hard-locked to `const:"BLOCKED"`; `identity_status=COMPARABLE_IDENTITY` requires it equal `"VERIFIED"` — structurally unsatisfiable, independent of §4/§5's adapter fix. Citations: `docs/血緣稽核_五維度_2026-07-31.md:219`, `docs/預註冊_FaceRedesign.md:107`, `Claude_推薦投組系統V2_Phase1_Review1.md:35`.

---

## 13. Full 30-test matrix (unchanged from revision 7, inlined)

| Test name | Coverage | Phase | Notes as of revision 13 |
|---|---|---|---|
| `test_history_gap_requires_evidence_for_deleted` | FR-5 | C | No change |
| `test_history_diagnosis_does_not_mutate_sources` | FR-7, AC-2 | C | No change |
| `test_exact_date_only_no_nearest_fill` | FR-10, FR-11, AC-3 | C/D | No change |
| `test_daily_not_counted_as_monthly` | FR-12, FR-15 | C | No change |
| `test_month_end_qualification_is_append_only` | FR-13, FR-14, AC-4 | C | No change |
| `test_pa_snapshot_captures_full_native_universe` | FR-17, AC-5 | C/D | Ranking adapter fail-closed on NULL-composite; raw-vs-parity overflow; `weights_version` uniqueness |
| `test_pb_snapshot_captures_fullpool_and_metadata` | FR-18, AC-5 | C/D | No change |
| `test_app_l4a_same_frozen_inputs_exact_set` | FR-19, FR-20, AC-6 | C/D | Isolated-temp-DB parity; dtype fixture; set comparison; `app.py` diff re-verification trigger |
| `test_no_orderintent_positionstate_or_l4b_access` | FR-21, AC-6 | C | No change |
| `test_r_fwd_255_month_membership_parity` | FR-25, AC-7 | D | **Sharpened round 9**: asserts all four gates populated and PASS, and that the emitted ledger record carries valid `sequence`/`prior_record_hash`/`record_hash`/`record_id`. **Sharpened round 11**: also asserts `qualification_status` correctly distinguishes `QUALIFIED`/`QUALIFICATION_PENDING`/`QUALIFICATION_FAILED` (§4.4), and that a qualification bundle missing a file, carrying an extra file, or diverging in bytes/sha256 across `artifact_set`/`mirror_verification`/audit-evidence is rejected (§4.5). **Sharpened round 13**: a fixture must assert that a receipt referencing a `QUALIFICATION_PENDING` attempt with `resolution_record_hash=null` is rejected, AND that re-validating the identical reference again after a resolution is later appended does not change the verdict (§4.7) — the direct regression test for the P1 blocker |
| `test_r_fwd_raw_score_tolerance` | FR-26, AC-7 | D | **Sharpened round 8**: this is what populates `raw_score_parity_result` — previously unenforced by any schema field |
| `test_r_fwd_cannot_read_exec_ret_or_future_inputs` | FR-28, AC-8 | C/D | **Sharpened round 9**: must populate `future_input_access_audit` with a real `audit_tool_sha256`, `audited_entrypoint`, both FR-28 forbidden targets enumerated, an empty `forbidden_targets_reached`, and a hash-identified evidence artifact |
| `test_identical_run_is_idempotent` | FR-31, FR-32, AC-9 | C | No change |
| `test_same_date_changed_source_creates_revision` | FR-33, AC-9 | C | No change |
| `test_partial_write_never_committed` | FR-34, AC-10 | C | `temp_cleanup_status` per receipt type |
| `test_ledger_hash_chain` | FR-35 | C | **Sharpened round 9**: the qualification ledger now HAS assertable chain fields (round 8 claimed this coverage with none present) — must verify continuity and detect an in-place edit via `record_hash` recomputation (semantic check #13). **Sharpened round 11**: also asserts `LedgerHeadCheckpoint.storage`/`content_sha256` identity (tail-truncation detection, check #20 extended) and that `protection_scope` discloses rather than silently over-claims coverage (§9.1, superseded — see next). **Sharpened round 12**: asserts the qualification ledger's chain now spans both `entry_kind`s (attempt/resolution, §4.6) including a resolution's `resolves_attempt_record_id`/`resolves_attempt_record_hash` resolving to a real earlier attempt (check #24); and asserts `LedgerHeadCheckpointRecord.payload_sha256` recomputes from the embedded `payload` alone, disjoint from this record's own `storage`/`protection_scope` (§9.2, check #20 corrected) |
| `test_primary_mirror_must_be_independent` | FR-37, EC-14 | C | Testable against §1's candidates |
| `test_commit_requires_two_verified_copies` | FR-38, AC-11 | C | **Sharpened round 9**: recovery fixtures must assert per-file `primary_sha256` identity with the original receipt's `output_hashes` plus aggregate recomputation (semantic check #11), not just filename-set equality. **Sharpened round 12**: fixtures for `LedgerHeadCheckpointRecord` must assert `storage.mirror_verification`'s per-file hash is checked against `payload_sha256` (a value describing a DISJOINT object, the embedded `payload`) and not against any field living on the record's own top level (§9.2) |
| `test_low_disk_never_prunes` | FR-42, AC-11, NFR-7 | C | No change |
| `test_capacity_bootstrap_requires_three_dry_runs` | NFR-7(a), Gate C-P | D | **Sharpened round 9**: plus a projection/enclosing-receipt agreement assertion (semantic check #16) alongside the check-#12 recomputation. **Sharpened round 11**: also asserts `PreflightObservation`'s `lock_holder_pid`/`disk_free_bytes` placeholders equal the newly-declared schema maxima exactly, and that a `COMPARABLE_IDENTITY` projection's `announcement_date_pit_status` is `VERIFIED`, never `BLOCKED` (§8.4) |
| `test_capacity_uses_bootstrap_for_first_20_runs` | NFR-7(b) | C | No change |
| `test_capacity_switches_to_p95_floor_after_20_runs` | NFR-7(c) | C | No change |
| `test_concurrent_run_single_mutex_winner` | FR-45(a), AC-16 | C | No change |
| `test_live_pid_never_treated_as_stale` | FR-45(b) | C | No change |
| `test_dead_pid_before_120_minutes_not_stale` | FR-45(b) | C | No change |
| `test_stale_lock_requires_manual_unlock_receipt` | FR-45(c)(d)(e), AC-16 | C | No change |
| `test_health_command_schema_and_counts` | FR-48, AC-16 | C | **Sharpened round 8**: recovery-then-recount fixture must also assert per-file completeness (§6) before `effective_persistence_status` flips |
| `test_epoch_change_on_identity_definition_change` | FR-49, FR-51, AC-13 | C | Full `CodeHashManifest` + comprehensive `collector_version` |
| `test_no_cross_epoch_month_counting` | FR-52, AC-13, AC-14 | C | No change |
| `test_collector_failure_does_not_change_production_outputs` | FR-46, AC-15, NFR-10 | C/D | No change |

No new test name this round (round 11 sharpened `test_r_fwd_255_month_membership_parity`, `test_ledger_hash_chain`, and `test_capacity_bootstrap_requires_three_dry_runs`; round 12 further sharpened `test_ledger_hash_chain` and `test_commit_requires_two_verified_copies`; round 13 further sharpens `test_r_fwd_255_month_membership_parity`, as above). All 30 remain individually mapped. Per Stage 1 scope, none of these files exist yet — Phase C (failing-tests-first, then minimal implementation) has not been authorized to begin for round 11/12/13's changes; this row only records what each planned test will additionally need to cover once Phase C starts.

---

## 14. Validation results (mechanical, this round)

**46 definitions** `check_schema()`-clean (was 43 -- round 12 removes `LedgerHeadCheckpoint`, adds `LedgerHeadCheckpointPayload`, `LedgerHeadCheckpointRecord`, `RFwdQualificationResolutionEvent`, `RFwdQualificationLedgerEntry`, net +3). Verified this round by running `Draft7Validator.check_schema()` over every one of the 46 `definitions` entries individually: 46/46 pass, 0 fail.

**Round 11's scratch validator re-run against the round-12 schema** (`validate_p0r2_round11.py`, unmodified except adding the now-required `entry_kind: "attempt"` field to its qualification-record fixtures, and skipping the 6 fixtures that named the now-renamed `LedgerHeadCheckpoint` type -- those are superseded by round 12's own checkpoint fixtures below, not silently dropped): **28/28 of the remaining, still-applicable round-11 counterexamples continue to behave exactly as expected.** This confirms round 12's structural changes (the new required `entry_kind` field; the `LedgerHeadCheckpoint` split) did not regress round 11's items 1, 2, or 3, nor the `AggregateHashFormula` half of item 4.

**Round 12 ran a second scratch validator** (`validate_p0r2_round12.py`, session scratchpad -- not committed, not collector code, not a pytest file; reads only `collector_schema.json`) against 21 constructed counterexamples/positive-fixtures covering all three user-reported blockers. **Result: 21/21 behaved exactly as expected (0 unexpected).** Breakdown:

- *Bug 1 (checkpoint content-hash/file-hash self-reference, §9.2) -- 8/8*: `LedgerHeadCheckpointPayload` rejects an extra field shaped like a self-hash (`additionalProperties:false` closes the door structurally, not just by convention). A well-formed `LedgerHeadCheckpointRecord` accepted, and hand-run check #20 confirms `payload_sha256`/`payload_bytes` recompute correctly from the embedded `payload` alone and the storage per-file hash ties to it. A tampered `payload_sha256` field is caught. Hashing the WHOLE outer record confirms it is (correctly) different from `payload_sha256` -- direct proof the schema no longer conflates "the record" with "the payload file." A `storage.relative_path` mismatched against `payload.ledger_name` is rejected; a record missing `storage`/`protection_scope` is rejected.
- *Bug 2 (`QUALIFICATION_PENDING`→`QUALIFIED` append-only resolution, §4.6) -- 11/11*: an attempt (`entry_kind="attempt"`, four gates PASS, bundle `PENDING`) accepted. A resolution event referencing that exact attempt by stable `record_id`+`record_hash`, with the bundle now `VERIFIED`, accepted. A resolution at `sequence=1` rejected at the schema layer (`minimum:2`, structural). Hand-computing `effective_qualification_status` over (attempt + resolution) yields `QUALIFIED` even though the attempt's own literal field still reads `QUALIFICATION_PENDING`; the same attempt with no resolution event stays effectively `QUALIFICATION_PENDING`. A resolution whose `resolves_attempt_record_hash` points at the wrong hash does not resolve the real attempt (check #24). Check #24's reapplied bundle-consistency check passes for a genuine resolution and catches one attesting to different bytes than the attempt described. `RFwdQualificationLedgerEntry` accepts both a well-formed attempt and a well-formed resolution. The round-11 attempt shape (no `entry_kind`) is now rejected.
- *Bug 3 (stale "LATEST record" text, §11) -- 2/2*: `CodeHashManifest.r_fwd_adapter_sha256`'s description no longer contains "MUST match the LATEST ... record" language; it now references the effective-status, record_hash-pinned rule instead.

**Combined total, rounds 11-12 (unchanged, not re-run this round since neither's fixtures touch `RFwdQualificationRef`): 49/49** (28 round-11-still-applicable + 21 round-12).

**Round 13 ran a third scratch validator** (`validate_p0r2_round13.py`, session scratchpad -- not committed, not collector code, not a pytest file; reads only `collector_schema.json`) against 14 constructed counterexamples/positive-fixtures covering the P1 blocker. **Result: 14/14 behaved exactly as expected (0 unexpected).** Breakdown:

- *Schema layer -- 3/3*: `RFwdQualificationRef` missing `resolution_record_hash` (round-12 shape) is rejected -- the field is now required. A reference to a directly-`QUALIFIED` attempt with `resolution_record_hash=null` validates at the schema layer. A reference pinning a `resolution_record_hash` validates at the schema layer (shape only -- the cross-object semantics are check #10's job).
- *Semantic check #10 (hand-run) -- 11/11*: a directly-`QUALIFIED` attempt with `resolution_record_hash=null` resolves. A `QUALIFICATION_PENDING` attempt with a correctly-pinned matching resolution resolves. **The exact P1 repro** -- a reference to a `QUALIFICATION_PENDING` attempt with `resolution_record_hash=null` -- is rejected. **Re-validation invariance**, demonstrated by construction: the identical rejected reference is checked AGAIN after a resolution for that same attempt is later appended to the simulated ledger -- the verdict is unchanged (still rejected), because the reference itself never pinned that resolution; by contrast, a reference that DOES pin the resolution resolves consistently on repeated checks against the same ledger state. A dangling `resolution_record_hash` (no matching resolution event) is rejected. A `resolution_record_hash` resolving a *different* attempt is rejected. A `resolution_record_hash` supplied for an already-`QUALIFIED` attempt (nonsensical -- nothing needed resolving) is rejected. A resolution whose `generated_at` is *after* the receipt's `completed_at` is rejected (temporal ordering); the same resolution is accepted once the receipt's `completed_at` legitimately postdates it. A `QUALIFICATION_FAILED` attempt is rejected regardless of `resolution_record_hash`.

**Regression check**: round 11/12's live scripts were not re-run this round because neither constructs an `RFwdQualificationRef` fixture with a real attempt/resolution pair behind it (their `rfwd_qual_ref()` helper is a standalone descriptor used only to exercise unrelated fields elsewhere) -- adding the now-required `resolution_record_hash: null` to that helper was sufficient to keep both scripts schema-valid; re-run and reconfirmed 28/28 and 21/21 respectively with that one-line patch, 0 regressions.

**Pre-approval metadata sync confirmed**: `$comment` asserted `revision 13`; `revision: 13` (was `12`); the then-pending dependency asserted `E2 rev.9`. At approval on 2026-08-15, the schema metadata was stamped `approval_status=APPROVED`, `approval_date=2026-08-15`, and `depends_on_erratum=E2 rev.9 APPROVED`; revision 13's design semantics were not changed by that status-only stamp.

**Prereg integrity reconfirmed**: `docs/prereg_P0_R2_ProductionHistoryGap_ForwardIdentityCollector_2026-08-13.md` sha256 = `6e0a232e91ced5cfd8c63a37b113b9113fbfa3e2481e5e4f93fa218f5dd2d91d` -- unchanged, recomputed and compared this round, not merely re-asserted from the prior round's record.

---

## 15. What remains explicitly out of scope for this round

- Erratum E2 revision 9 is **APPROVED as of 2026-08-15** for Stage 1 offline Phase C. The approved prereg remains untouched: hash `6e0a232e91ced5cfd8c63a37b113b9113fbfa3e2481e5e4f93fa218f5dd2d91d` -- recomputed and reconfirmed before approval (§14), not merely re-asserted.
- No `evidence_root`, no `r_fwd_adapter_qualification_ledger.jsonl`, no qualification bundle, no ledger-head checkpoint, no `capacity_dry_run_report.json` exist.
- No collector code, no test files, no `scripts/identity_collector/` package. `validate_p0r2_round11.py`/`validate_p0r2_round12.py`/`validate_p0r2_round13.py` (§14) are scratch validators in the session scratchpad, outside the repository -- none is staged, committed, collector code, or a test file.
- No Task Scheduler installation/modification.
- No Phase C work occurred during design or this approval event. Following approval, Stage 1 offline Phase C may begin under the existing prereg authorization; Stage 2 remains prohibited.
- `COMPARABLE_IDENTITY` remains mechanically unreachable on the LIVE `RunReceiptSuccess` type (§12) even after §4/§5/§6/§9.1/§9.2's fixes — those fixes correct the *mechanism* (and, for the capacity-projection types only, size a hypothetical future-viable receipt per §8.4), not Gate C-R's independent block.
- `LedgerHeadCheckpointRecord`'s durability claim remains narrowed, not complete (§9.2, `protection_scope`): it does not, and is not claimed to, detect a simultaneous rollback of a ledger and its own checkpoint to a consistent earlier state.
- No production calculation or state was read beyond source verification and this round's schema/semantic-validator work.

---

## 16. Approval record

- User approval: **APPROVED**
- Approval date: **2026-08-15**
- Approved revision: **Phase B revision 13 + collector schema revision 13 + E2 revision 9**
- Approved pre-stamp SHA256 — `phase_b_design_freeze.md`: `9f38450809932d593527971e260d5ad77a7bf7a8398a503a9261367797877679`
- Approved pre-stamp SHA256 — `collector_schema.json`: `33f89ae82581a6c0d11f70fe2eb0bfc96ec02ae7eee218113aee251ca406bc15`
- Approved pre-stamp SHA256 — `errata_E2_capacity_dry_run_receipt.md`: `2ff5bbaaaa8c964996694e4eaf23c50fcbf258408e9e3d3602ef6d5affad2dc0`
- Approved scope: Stage 1 offline Phase C tests, minimal implementation, synthetic/frozen-snapshot dry-run, and offline R-FWD parity adapter work only.
- Explicitly unauthorized: Primary/Mirror evidence-root creation; R-FWD forward/live collection; collector live writes; Task Scheduler install/modify; production calculation/state writes.
- Final stamped identities: recorded externally in `approval_receipt.json`; not self-written into these approved artifacts.
