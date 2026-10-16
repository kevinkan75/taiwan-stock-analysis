#!/usr/bin/env python3
"""Run every check_*.py and the Node interaction contract; no third-party packages."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-only', action='store_true', help='explicitly skip the Node interaction contract')
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    node = shutil.which('node')
    if not args.python_only and not node:
        print(json.dumps({'passed': False, 'error': 'Full checks require Node.js; install it or explicitly use --python-only.'}))
        return 2
    scripts = sorted((ROOT / 'tests').glob('check_*.py'))
    if not scripts:
        print(json.dumps({'passed': False, 'error': 'No regression scripts found.'}))
        return 2
    # Windows may use a legacy console/file encoding. Child checks and their
    # nested CLI calls must use the same UTF-8 as the source JSON files.
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    commands = [(script.name, [sys.executable, '-X', 'utf8', '-B', str(script)]) for script in scripts]
    if not args.python_only:
        commands.append(('check_html_interactions.js', [node, str(ROOT / 'tests/check_html_interactions.js')]))
    results = []
    for name, command in commands:
        result = subprocess.run(command, cwd=str(ROOT), env=env, capture_output=True, text=True, encoding='utf-8')
        print(('PASS ' if result.returncode == 0 else 'FAIL ') + name, flush=True)
        data = None
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
            except ValueError:
                pass
        if result.returncode or not isinstance(data, dict) or not data.get('passed'):
            print(result.stdout, end='')
            print(result.stderr, end='')
            results.append({'suite': name, 'passed': False, 'exit_code': result.returncode})
        else:
            results.append({'suite': name, 'passed': True, 'checks': data.get('checks', 0),
                            'exhaustive_signal_combinations': data.get('exhaustive_signal_combinations', 0)})
    passed = all(x['passed'] for x in results)
    print(json.dumps({'passed': passed, 'python_suites': len(scripts),
        'python_checks': sum(x.get('checks', 0) for x in results if x['suite'].endswith('.py')),
        'node_checks': sum(x.get('checks', 0) for x in results if x['suite'].endswith('.js')),
        'node_skipped': args.python_only,
        'exhaustive_signal_combinations': sum(x.get('exhaustive_signal_combinations', 0) for x in results),
        'failed': [x['suite'] for x in results if not x['passed']],
        'scope': 'Synthetic local rules and interaction logic; no live evidence, investment performance or browser visual acceptance.'}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
