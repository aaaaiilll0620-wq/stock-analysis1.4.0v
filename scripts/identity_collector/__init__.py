"""P0-R2 forward identity collector — Phase C offline package.

Stage 1 offline scope only (approval_receipt.json `phase_b_design_approval_event`).
No live evidence roots, no forward/live R-FWD collection, no Task Scheduler
writes, no production calculation/state writes happen anywhere in this
package — every write path here takes an explicit, caller-supplied directory
(a pytest tmp_path in tests) and never touches a repository-relative default.
"""

SCHEMA_VERSION = "p0r2-collector-schema-v1"
