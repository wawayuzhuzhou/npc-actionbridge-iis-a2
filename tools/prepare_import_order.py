"""Prepare new external B/A copies with assets imported before scene preloads.

No historical cache is accepted. This is preparation tooling, not a game change.
It runs at most three headless imports, stops at the first non-clean result and
never opens a GUI, starts an API, loads an index or constructs a model client.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', required=True, type=Path)
    ap.add_argument('--source-game', required=True, type=Path)
    ap.add_argument('--source-db', required=True, type=Path)
    ap.add_argument('--godot', required=True, type=Path)
    ap.add_argument('--work', required=True, type=Path)
    a = ap.parse_args()
    root, source, db, work = (p.resolve() for p in
                             (a.candidate, a.source_game, a.source_db, a.work))
    if work.exists():
        ap.error('Use a new work directory; existing attempts are preserved')
    for protected in (root, source, db.parent):
        if protected == work or protected in work.parents or work in protected.parents:
            ap.error('The work directory must be separate from candidate and sources')
    if not (source / 'project.godot').is_file() or not db.is_file():
        ap.error('A complete separately acquired game and seed DB are required')
    work.mkdir(parents=True)
    logs = work / 'logs'
    logs.mkdir()
    env = os.environ.copy()
    for k in list(env):
        u = k.upper()
        if u.startswith(('A2_', 'QWEN_', 'DASHSCOPE_', 'OPENAI_', 'AZURE_OPENAI_')) or any(
                t in u for t in ('API_KEY', 'ACCESS_KEY', 'TOKEN', 'SECRET',
                                 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION')):
            env.pop(k)
    for k in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'HTTP_PROXY',
              'HTTPS_PROXY', 'ALL_PROXY'):
        env.pop(k, None)
        env.pop(k.lower(), None)
    profile = work / 'profile'
    for k, name in [('APPDATA', 'roaming'), ('LOCALAPPDATA', 'local'),
                    ('TEMP', 'temp'), ('TMP', 'temp')]:
        dest = profile / name
        dest.mkdir(parents=True, exist_ok=True)
        env[k] = str(dest)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    game = work / 'B/game'
    game.mkdir(parents=True)
    source_db_hash = sha(db)
    record = {'id': work.name, 'hypothesis':
              'Import raw assets before autoload/scene preloads encounter missing generated caches',
              'old_cache_copied': False, 'core_changes': [], 'provider_requests': 0,
              'source_db_sha256_before': source_db_hash,
              'started_utc': datetime.now(timezone.utc).isoformat(), 'runs': []}

    def finish(status):
        record['status'] = status
        record['source_db_sha256_after'] = sha(db)
        record['source_db_unchanged'] = sha(db) == source_db_hash
        record['ended_utc'] = datetime.now(timezone.utc).isoformat()
        (work / 'preparation_result.json').write_text(
            json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': status, 'imports_run': len(record['runs']),
                          'runs': record['runs']}, indent=2), flush=True)
        return 0 if status == 'PASS' else 1

    def run(label, path):
        command = [str(a.godot.resolve()), '--headless', '--editor', '--path',
                   str(path), '--log-file', str(logs / (label + '.godot.log')),
                   '--import', '--quit']
        start = datetime.now(timezone.utc).isoformat()
        with (logs / (label + '.stdout.txt')).open('w', encoding='utf-8') as out, \
             (logs / (label + '.stderr.txt')).open('w', encoding='utf-8') as err:
            try:
                process = subprocess.run(command, cwd=work, env=env, stdout=out,
                                         stderr=err, timeout=180, check=False)
                code, timeout = process.returncode, False
            except subprocess.TimeoutExpired:
                code, timeout = None, True
        text = '\n'.join((logs / (label + suffix)).read_text(encoding='utf-8', errors='replace')
                         for suffix in ('.stdout.txt', '.stderr.txt'))
        errors = re.findall(r'^(?:SCRIPT )?ERROR:.*$', text, flags=re.M)
        warnings = re.findall(r'^(?:USER )?WARNING:.*$', text, flags=re.M)
        row = {'step': label, 'started_utc': start,
               'ended_utc': datetime.now(timezone.utc).isoformat(),
               'command': command, 'exit_code': code, 'timeout': timeout,
               'errors': len(errors), 'warnings': len(warnings),
               'distinct_messages': sorted(set(errors + warnings)),
               'generated_cache_files': sum(p.is_file() for p in (path / '.godot/imported').glob('*'))}
        record['runs'].append(row)
        print(json.dumps({'step': label, 'exit_code': code, 'errors': len(errors),
                          'warnings': len(warnings)}, indent=None), flush=True)
        return code == 0 and not timeout and not errors and not warnings

    # Copy only raw assets and their original importer metadata, never .godot.
    shutil.copytree(source / 'Assets', game / 'Assets',
                    ignore=shutil.ignore_patterns('.godot', '.git', '*.gd', '*.tscn', '*.tres'))
    for p in source.glob('icon.*'):
        if p.is_file():
            shutil.copyfile(p, game / p.name)
    (game / 'project.godot').write_text(
        'config_version=5\n\n[application]\nconfig/name="Asset import bootstrap"\n'
        'config/features=PackedStringArray("4.3", "GL Compatibility")\n\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        'renderer/rendering_method.mobile="gl_compatibility"\n', encoding='utf-8')
    record['bootstrap_godot_cache_present_before'] = (game / '.godot').exists()
    record['bootstrap_source_files'] = sum(p.is_file() for p in game.rglob('*'))
    if not run('01_assets_only', game):
        return finish('FAILED_PRESERVED_assets_only')
    # Restore all original code, scenes and project settings byte-for-byte.
    shutil.copytree(source, game, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.godot', '.git'))
    core = [p for p in source.rglob('*') if p.is_file() and
            p.suffix in ('.gd', '.tscn', '.tres', '.godot') and '.godot' not in p.parts]
    record['baseline_core_files_checked'] = len(core)
    record['baseline_core_byte_equal'] = all(sha(p) == sha(game / p.relative_to(source)) for p in core)
    if not record['baseline_core_byte_equal']:
        return finish('FAILED_PRESERVED_source_integrity')
    if not run('02_baseline_full', game):
        return finish('FAILED_PRESERVED_baseline_full')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    from adapter.actionbridge.prepare_runtime import prepare
    prepare(game, db, work / 'A')
    record['enhanced_cache_provenance'] = 'generated by this round assets-only and B full import; no historical cache'
    if not run('03_enhanced_full', work / 'A/game'):
        return finish('FAILED_PRESERVED_enhanced_full')
    return finish('PASS')


if __name__ == '__main__':
    raise SystemExit(main())
