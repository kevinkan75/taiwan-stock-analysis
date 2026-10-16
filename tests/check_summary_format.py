"""Actual validator/CLI coverage for rule 1.7.0 summary presence, not decision semantics."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import snapshot_guard as g

BASE = json.loads((ROOT/'assets/snapshot.example.json').read_text())
count = 0


def check(ok, reason):
    global count
    count += 1
    if not ok:
        raise AssertionError(reason)


def derived(s):
    result = g.validate(s, True)
    check(result['valid'], repr(result['errors']))
    return g.derived_snapshot(s, result)


def report(s, lines):
    out = deepcopy(s)
    kept = [line for line in out['report_markdown'].splitlines()
            if not any(line.startswith(label + '：') for label in g.SUMMARY_LABELS)]
    out['report_markdown'] = '\n'.join(kept + lines)
    out['report_sha256'] = g.report_hash(out)
    return out


def main():
    out = derived(deepcopy(BASE))
    check(g.validate(out)['valid'], 'current example valid')
    check(g.validate(out)['summary_checks'] == 'four_line_presence', 'format-only scope explicit')
    lines = [label + '：本次未評估' for label in g.SUMMARY_LABELS]
    for i in range(4):
        bad = report(out, lines[:i] + lines[i+1:])
        check(not g.validate(bad)['valid'], 'missing summary label ' + str(i))
    for altered in [lines[::-1], lines + [lines[0]], [lines[0].split('：')[0] + '：'] + lines[1:],
                    [lines[0].split('：')[0] + '：—'] + lines[1:]]:
        check(not g.validate(report(out, altered))['valid'], 'order, duplicate, blank, placeholder rejection')
    check(g.validate(report(out, ['- **' + label + '：** 本次未評估' for label in g.SUMMARY_LABELS]))['valid'], 'bold bullets accepted')
    check(g.validate(report(out, [label + ': 本次未評估' for label in g.SUMMARY_LABELS]))['valid'], 'ASCII colon accepted')
    check(g.validate(report(out, lines))['valid'], 'unassessed scope is not a blank')
    check(not g.text_financial_uses('ROE本次未評估', 'summary'), 'explicit nonassessment is not an affirmative financial claim')
    check(bool(g.text_financial_uses('ROE本次未評估但改善', 'summary')), 'nonassessment cannot hide affirmative evidence')
    for version in ('1.5.0', '1.6.0'):
        old = json.loads((ROOT/('tests/snapshot.rule-' + version + '.json')).read_text())
        copy = json.dumps(old, sort_keys=True)
        archived = derived(old)
        result = g.validate(archived)
        check(result['valid'] and result['summary_checks'] == 'not_checked', 'archived format preserved ' + version)
        check(json.dumps(old, sort_keys=True) == copy, 'archived input unchanged ' + version)
        if version == '1.6.0':
            archived['valuation']['scenarios'][0]['model_price'] += 1
            check(not g.validate(archived, True)['valid'], '1.6 arithmetic still enforced')
    # --derive may bind a draft but cannot certify it as a final report.
    draft = report(out, [])
    check(g.validate(draft, True)['valid'], 'draft can be derived before formatting')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'draft.json'; path.write_text(json.dumps(draft))
        p = subprocess.run([sys.executable, str(ROOT/'scripts/snapshot_guard.py'), str(path)], capture_output=True, text=True)
        check(p.returncode == 2 and not json.loads(p.stdout)['valid'], 'CLI rejects final report without four lines')
    print(json.dumps({'passed': True, 'checks': count, 'scope': 'summary format and archived compatibility; decision semantics remain manual'}))


if __name__ == '__main__':
    main()
