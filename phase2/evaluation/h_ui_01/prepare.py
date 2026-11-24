"""Copy a v1 runtime for student H-UI-01, then run only headless assertions.

No GUI launch, credentials, Qwen clients, live database or budget mutations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ("source-game", "godot", "target"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source, target = args.source_game.resolve(), args.target.resolve()
    if target.exists() or source == target or source in target.parents or "upstream_frozen" in {p.lower() for p in target.parts}:
        parser.error("Use a fresh independent evaluation destination")
    checked = ["Scripts/ActionBridge.gd", "Scripts/ActionBridgeUI.gd", "Scripts/PersistanceManager.gd", "Scenes/UI/hud.gd", "Scenes/UI/HUD.tscn"]
    hashes = {name: digest(source / name) for name in checked}
    game = target / "game"
    shutil.copytree(source, game, ignore=shutil.ignore_patterns(".git"))
    project = game / "project.godot"
    text = project.read_text(encoding="utf-8")
    text = re.sub(r'config/name="[^"]+"', 'config/name="H-UI-01 Student Fixture Replay"', text, count=1)
    project.write_text(text, encoding="utf-8")
    fixture = Path(__file__).with_name("fixture.gd")
    shutil.copy2(fixture, game / "h_ui_01.gd")
    command = [str(args.godot), "--headless", "--path", str(game), "--log-file", str(target / "headless_godot.log"),
               "--script", "res://h_ui_01.gd", "--", "--check-only", "--session", "H-UI-01-OFFLINE-CHECK",
               "--output", str(target / "headless_assertions.jsonl")]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        completed = subprocess.CompletedProcess(command, 124, exc.stdout or b"", exc.stderr or b"")
    (target / "headless_stdout.txt").write_bytes(completed.stdout)
    (target / "headless_stderr.txt").write_bytes(completed.stderr)
    unchanged = all(digest(source / name) == hashes[name] == digest(game / name) for name in checked)
    events = []
    if (target / "headless_assertions.jsonl").exists():
        events = [json.loads(line) for line in (target / "headless_assertions.jsonl").read_text().splitlines() if line]
    passed = completed.returncode == 0 and unchanged and any(e["event"] == "headless_assertions_passed" for e in events)
    manifest = {"fixture_id": "H-UI-01", "category": "isolated student GUI fixture preparation",
                "headless_status": "PASS" if passed else "FAILED_PRESERVED", "GUI_launched": False,
                "provider_requests": 0, "core_source_and_copied_hashes_equal": unchanged, "core_hashes": hashes,
                "fixture_script_sha256": digest(fixture), "headless_events": events,
                "limits": ["No human button interaction or visual GUI review yet", "No API/SQLite outcome save", "Real HUD visible flags checked headlessly; actual layout awaits student capture"]}
    (target / "preparation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["headless_status"], "GUI_launched": False, "provider_requests": 0, "core_unchanged": unchanged}))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
