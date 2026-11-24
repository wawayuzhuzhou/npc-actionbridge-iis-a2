"""Run existing offline unit tests with credentials removed and sockets guarded.

Use a fresh Python 3.11 venv and ``python -I offline_guard.py --repo ...
--result ...``. This is evaluation-only tooling; it changes no application code.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    args = parser.parse_args()
    if args.result.exists():
        parser.error('Use a new result file; existing attempts are preserved')
    removed = 0
    for key in list(os.environ):
        upper = key.upper()
        if upper.startswith(('A2_', 'QWEN_', 'DASHSCOPE_', 'OPENAI_', 'AZURE_OPENAI_')) or any(
                marker in upper for marker in ('API_KEY', 'ACCESS_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTHORIZATION')):
            os.environ.pop(key, None)
            removed += 1
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        os.environ.pop(key, None)
        os.environ.pop(key.lower(), None)
    sys.dont_write_bytecode = True
    root = args.repo.resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)
    stats = {'blocked_operations': 0, 'loopback_connects': 0, 'loopback_ephemeral_binds': 0}
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_bind = socket.socket.bind
    original_sendto = socket.socket.sendto
    original_getaddrinfo = socket.getaddrinfo

    def allowed(address):
        return isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1')

    def deny():
        stats['blocked_operations'] += 1
        raise AssertionError('Offline guard: only loopback wakeup sockets are permitted')

    def connect(sock, address):
        if not allowed(address):
            deny()
        stats['loopback_connects'] += 1
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if not allowed(address):
            deny()
        stats['loopback_connects'] += 1
        return original_connect_ex(sock, address)

    def bind(sock, address):
        if not allowed(address) or address[1] != 0:
            deny()
        stats['loopback_ephemeral_binds'] += 1
        return original_bind(sock, address)

    def sendto(sock, data, *rest):
        deny()

    def getaddrinfo(host, *rest, **kwargs):
        if host not in ('127.0.0.1', '::1', 'localhost'):
            deny()
        return original_getaddrinfo(host, *rest, **kwargs)

    started = datetime.now(timezone.utc).isoformat()
    with patch.object(socket.socket, 'connect', connect), \
         patch.object(socket.socket, 'connect_ex', connect_ex), \
         patch.object(socket.socket, 'bind', bind), \
         patch.object(socket.socket, 'sendto', sendto), \
         patch.object(socket, 'getaddrinfo', getaddrinfo):
        suite = unittest.defaultTestLoader.discover(str(root/'adapter/tests'), top_level_dir=str(root))
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName('phase2.evaluation.test_budget_guard'))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    record = {'category':'existing offline mocked unit checks',
        'started_utc':started, 'ended_utc':datetime.now(timezone.utc).isoformat(),
        'status':'PASS' if result.wasSuccessful() and stats['blocked_operations'] == 0 else 'FAILED_PRESERVED',
        'tests_run':result.testsRun, 'failures':len(result.failures), 'errors':len(result.errors),
        'skipped':len(result.skipped), 'socket_guard':stats,
        'credential_variables_removed_in_guard':removed,
        'credentials_also_removed_by_parent_process':True,
        'provider_requests':0, 'provider_count_basis':'inspected mocks and process-scoped socket denial; no independent provider meter',
        'limits':['No index build, live provider, live HTTP listener or historical SQLite connection',
                  'Loopback ephemeral sockets are permitted for Windows asyncio wakeups']}
    args.result.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record))
    return 0 if record['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
