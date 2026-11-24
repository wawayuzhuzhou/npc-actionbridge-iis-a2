# Zero provider reproduction

This is an inspectable code/report snapshot, not a complete game distribution.
Python 3.11, the recorded direct pins and the separately resolved 63-package
inventory document one host; they are not a cross-platform transitive lock.
Start in a fresh extraction of the release ZIP or GitHub source archive.
The exact-file verifier expects no extra Git metadata or local environment files.

```powershell
$ReviewEnv = Join-Path $env:TEMP ('actionbridge-python-' + [guid]::NewGuid().ToString('N'))
py -3.11 -m venv $ReviewEnv
$ReviewPython = Join-Path $ReviewEnv 'Scripts/python.exe'
& $ReviewPython -m pip install -r requirements.txt
& $ReviewPython tools/verify_snapshot.py
& $ReviewPython -I tools/offline_unit_guard.py --repo . --result (Join-Path $env:TEMP ('actionbridge-units-' + [guid]::NewGuid().ToString('N') + '.json'))
```

Package installation uses package indexes. The guarded tests remove credentials,
deny external Python sockets, and use mocks and new synthetic temporary databases.
The guard is byte-identical to the helper used in the recorded candidate test.
No provider credentials are needed for these checks.

For headless integration, first acquire the complete pinned upstream game, seed
DB and Godot 4.3 separately using [external acquisition](EXTERNAL_ASSETS.md).
Set the local variables below to those new paths. The source checkout stays clean.

```powershell
$Prepared = Join-Path $ReviewRoot 'assets-first'
& $ReviewPython -I tools/prepare_import_order.py --candidate . --source-game (Join-Path $Upstream 'game') --source-db (Join-Path $Upstream 'api/data/game_data.db') --godot $Godot --work $Prepared
& $ReviewPython -B phase2/evaluation/run_offline.py --baseline-game (Join-Path $Prepared 'B/game') --enhanced-game (Join-Path $Prepared 'A/game') --seed-db (Join-Path $Upstream 'api/data/game_data.db') --godot $Godot --work (Join-Path $ReviewRoot 'paired') --output (Join-Path $ReviewRoot 'paired_results.json')
```

All work/output destinations must be new. The helper imports raw assets under a
temporary no-autoload project before restoring the original source, importing B
and preparing/importing A. A inherits only the cache generated in that new run.
The helper stops at the first non-clean import, logs each attempt and never opens
a GUI or modifies upstream/core code. Continue to integration only after preparation succeeds.

The candidate runner reads its local minimised two-action fixture, not private E3
SQL. It uses in-process ASGI, actual headless state/action functions, programmed
choices and disposable SQLite, with no Qwen client. Fixture contexts are not live
FAISS outputs. Inspect stdout/stderr and Godot logs as well as result assertions:
the runner's PASS alone does not certify a clean engine. Source seed equality is
checked. The six pairs are not twelve model samples or human choices.

[Recorded verification](../evidence/REPRODUCTION_STATUS.md) distinguishes retained
old failures from the actual candidate run. Graphical gameplay, Linux, export and
another engine version were not tested. H-UI-01 remains a separate guided local
GUI fixture, with no provider/API/SQL; no new GUI replay is part of this recipe.
