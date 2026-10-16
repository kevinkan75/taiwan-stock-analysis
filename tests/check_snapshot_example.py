"""1.4.6 regression checks for assets/snapshot.example.json.

The example replaces reading the whole schema when building a snapshot, so it must (a) pass snapshot_guard,
(b) stay obviously synthetic, (c) not anchor a uniform outcome, and (d) stay compact. Calls snapshot_guard directly.
"""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import snapshot_guard as guard  # noqa: E402
import financial_history

path = ROOT / 'assets/snapshot.example.json'
text = path.read_text(encoding='utf-8')
example = json.loads(text)
results = []
MAX_CHARS = 12000  # load goal: clearly smaller than the schema (about 27,700 chars)


def check(cond, msg):
    results.append((bool(cond), msg))


check(example['schema_version'] == '1.5' and example['model_version'] == '1.3', 'example targets schema 1.5 / model 1.3')

r = guard.validate(copy.deepcopy(example), derive_only=True)
check(r['valid'], 'example passes snapshot_guard --derive: ' + repr(r['errors'][:2]))
if r['valid']:
    derived = guard.derived_snapshot(copy.deepcopy(example), r)
    check(guard.validate(derived)['valid'], 'derived example round-trips through full validation')
    overall = derived['overall']
    check(overall['provisional'] is False and overall['confidence'] == 'high', 'example shows a complete, high-confidence record')
    check(overall['signal'] != 'green' or overall['score'] < 100, 'example does not model a perfect-score outcome')

# anti-anchoring: scores must not be uniform
scores = {item['score'] for dim in example['scores'].values() for item in dim['items']}
check(len(scores) >= 2, 'example scores are mixed, not all identical')

# obviously synthetic
hosts = {u.split('/')[2] for u in re.findall(r'https?://[^\s"]+', text)}
check(hosts and all(h.endswith('.invalid') for h in hosts), 'example URLs all use reserved .invalid hosts')
check('合成' in example['security']['name'], 'example company name is marked as synthetic')

# the formats people otherwise have to look up in the schema
check(len(example['events']) >= 1 and set(example['events'][0]) == {'event_date', 'published_at', 'status', 'description', 'source_url'},
      'example shows the event object format')
check(len(example['risks']) >= 1 and isinstance(example['risks'][0], str), 'example shows the risks format')
check(example['valuation']['band'] is not None, 'example shows a valuation band')
check({s['label'] for s in example['valuation']['scenarios']} == {'conservative', 'base', 'optimistic'}, 'example shows all three scenarios')
statuses = {m['value_status'] for m in example['metrics'].values()}
check({'reported', 'calculated', 'missing'} <= statuses, 'example shows reported, calculated and missing metrics')
check(example['technical']['status'] == 'computed' and example['technical']['observation_count'] >= 240, 'example shows computed technical data with 240+ bars')

# The unchanged core keeps its original 12k budget. Rule 1.13 also binds the
# actual annual report, so give only that new appendix a separate 2k budget.
core=copy.deepcopy(example)
core['report_markdown']='\n'.join(x for x in financial_history.strip_report(core['report_markdown']).splitlines()
                                  if not x.startswith('三年財務檢核：'))
core_chars=len(json.dumps(core,ensure_ascii=False,separators=(',',':'))+'\n')
check(core_chars <= MAX_CHARS, f'core example stays compact ({core_chars:,} <= {MAX_CHARS:,} chars)')
check(len(text)-core_chars <= 2000, 'bound annual report appendix and avoid whitespace inflation (<=2,000 chars)')

fails = [m for ok, m in results if not ok]
print(json.dumps({'checks': len(results), 'failed': fails, 'passed': not fails}, ensure_ascii=False))
sys.exit(1 if fails else 0)
