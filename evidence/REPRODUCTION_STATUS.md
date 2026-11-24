# Recorded reproduction boundaries

The accepted v0.3 check installed a clean isolated Python 3.11 environment and
passed 46 tests. Its two direct fresh Godot imports crashed at 0xC0000005; later
B logs contained 270 resource ERROR lines despite passing state assertions.
Those failures are retained, not overwritten by this candidate result.

RC1 verified that nine raw source assets were present and matched the clean
pinned checkout. Old B lacked their generated caches; old A had them. The native
crash cause remains unknown. One declared assets-first round generated a new
cache from raw sources, then imported complete B and A: three exits 0, zero
ERROR/WARNING. No old cache was copied; no core source changed. A inherited only
this newly generated B cache. A second repair round was not needed or run.

The executable candidate passed 46 guarded unit tests and one six-pair/twelve-run
headless integration replay. State, ASGI HTTP and SQLite assertions passed, and
all twelve stdout/stderr files and engine logs had zero errors/warnings. Final
payload code/data are checked against the tested hashes. Documentation/manifests
were assembled afterwards. The RC1 Python check reused the verified clean v0.3
environment with a passing pip check; it was not a second fresh installation.

See [preparation](RC1_PREPARATION.json), [units](RC1_CANDIDATE_UNITS.json),
[integration](RC1_CANDIDATE_INTEGRATION.json) and [tested hashes](../review/tested_code.sha256).
No provider call, index build, live HTTP server, real GUI or live ledger was used.
No full graphical, Linux, export or other-version result is claimed. The old H
case warning is preserved privately; candidate helpers contain the reviewed
HUD filename correction. Windows checks do not establish case-sensitive execution.
