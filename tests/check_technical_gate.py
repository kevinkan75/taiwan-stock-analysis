"""1.4.3 regression checks: snapshot_guard itself enforces the 240-bar technical gate (model 1.1).

Unlike the R-rule cases in check_portability.py (which exercise helper functions defined inside that test
file), every check here calls snapshot_guard.validate, so it fails if the guard stops enforcing the rule.
Synthetic data only.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import snapshot_guard as guard  # noqa: E402

data = json.loads((ROOT / 'tests/portability_cases.json').read_text(encoding='utf-8'))
template = data['template']
green_tech = next(c for c in data['cases'] if c['id'] == 'technical_green')['overrides']['technical']
results = []


def check(cond, msg):
    results.append((bool(cond), msg))


def snapshot(model, status, count):
    s = copy.deepcopy(template)
    if model == '1.1':
        s['schema_version'], s['model_version'] = '1.3', '1.1'
        s['overall'].update({'provisional': False, 'confidence': None})
        s['valuation'].update({'multiple_basis': 'vendor_band', 'eps_basis': 'external_multi', 'band': None})
    if status == 'computed':
        s['technical'].update(copy.deepcopy(green_tech))
    else:
        s['technical'].update({'status': 'insufficient_data', 'reason': '合成：日線筆數不足',
                               'source_urls': ['https://fixture.invalid/synthetic-source']})
    s['technical']['observation_count'] = count
    return s


def verdict(s):
    r = guard.validate(s, derive_only=True)
    return r, any('observations' in e for e in r['errors'])


# model 1.1: computed needs 240+ bars
for count in (0, 60, 100, 239):
    r, bars_error = verdict(snapshot('1.1', 'computed', count))
    check(not r['valid'] and bars_error, f'1.1 computed with {count} bars is rejected on the bar count')
r, bars_error = verdict(snapshot('1.1', 'computed', 240))
check(r['valid'] and not bars_error, '1.1 computed with exactly 240 bars is accepted')
r, _ = verdict(snapshot('1.1', 'computed', 400))
check(r['valid'] and r['derived']['technical_signal'] == 'green', '1.1 computed with 400 bars derives the technical light')

# the error must tell the analyst what to do instead
r, _ = verdict(snapshot('1.1', 'computed', 239))
check(any('insufficient_data' in e for e in r['errors']), '1.1 rejection message points to insufficient_data')

# model 1.1: honest "not enough data" is a valid snapshot and yields a grey technical light
for count in (10, 239):
    r, _ = verdict(snapshot('1.1', 'insufficient_data', count))
    check(r['valid'] and r['derived']['technical_signal'] == 'unknown', f'1.1 insufficient_data with {count} bars is valid and unknown')

# the derived snapshot must still round-trip through full validation at the boundary
s240 = snapshot('1.1', 'computed', 240)
rd = guard.validate(s240, derive_only=True)
check(rd['valid'] and guard.validate(guard.derived_snapshot(s240, rd))['valid'], '1.1 boundary snapshot round-trips')

# model 1.0 archives keep the legacy 60-bar floor (old snapshots must stay verifiable)
r, bars_error = verdict(snapshot('1.0', 'computed', 100))
check(r['valid'] and not bars_error, '1.0 computed with 100 bars stays valid (legacy floor)')
r, bars_error = verdict(snapshot('1.0', 'computed', 59))
check(not r['valid'] and bars_error, '1.0 computed with 59 bars is still rejected')

fails = [m for ok, m in results if not ok]
print(json.dumps({'checks': len(results), 'failed': fails, 'passed': not fails}, ensure_ascii=False))
sys.exit(1 if fails else 0)
