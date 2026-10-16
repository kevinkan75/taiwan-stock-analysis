"""1.4.0/1.4.1/1.4.2 regression checks for financials_dependent: dependence is derived from content. Synthetic data only."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import snapshot_guard as guard  # noqa: E402

template = json.loads((ROOT / 'tests/portability_cases.json').read_text(encoding='utf-8'))['template']
results = []


def check(cond, msg):
    results.append((bool(cond), msg))


def build(mutate):
    s = copy.deepcopy(template)
    mutate(s)
    r = guard.validate(s, derive_only=True)
    if r['derived'] is None:
        return s, r
    s = guard.derived_snapshot(s, r)
    return s, guard.validate(s)


def item(s, check_name):
    for dim in s['scores'].values():
        for x in dim['items']:
            if x['check'] == check_name:
                return x
    raise KeyError(check_name)


def clear_metric(s, key):
    s['metrics'][key]['value'] = None
    s['metrics'][key]['value_status'] = 'missing'
    s['metrics'][key]['formula'] = None
    s['metrics'][key]['inputs'] = None


def unverified(s):
    s['eligibility']['financials_verified'] = False
    s['eligibility']['reasons']['financials_verified'] = '合成測試：未讀完整報表'
    s['validation'] = [x for x in s['validation'] if x['check'] != 'financials_verified']
    s['financial_period_end'] = None


def dependent_false_ok(s):
    unverified(s)
    s['eligibility']['financials_dependent'] = False
    s['eligibility']['reasons']['financials_dependent'] = '合成測試：結論不使用ROE、自由現金流、負債比或淨值'
    for name in guard.STATEMENT_CHECKS:
        item(s, name)['score'] = None
    for key in ('roe_ttm', 'fcf_ttm'):
        clear_metric(s, key)


# A. Baseline unchanged
_, r = build(lambda s: None)
check(r['valid'], 'A baseline template remains valid: ' + '; '.join(r['errors'][:2]))

# B. Unverified, dependence omitted (default true): must not be eligible
s_b, r_b = build(lambda s: unverified(s))
check(r_b['derived'] is not None, 'B derive runs: ' + '; '.join(r_b['errors'][:3]))
check(r_b['derived'] is not None and r_b['derived']['overall']['signal'] == 'unknown', 'B unverified with default dependence yields no signal')
check('financials_dependent' not in s_b['eligibility'], 'B omitted flag stays omitted')

# C. Unverified, not dependent, consistent fundamentals: valid
s_c, r_c = build(dependent_false_ok)
check(r_c['valid'], 'C not-dependent with unscored statement items is valid: ' + '; '.join(r_c['errors'][:2]))

# D. Not dependent but no reason stated: rejected
def no_reason(s):
    dependent_false_ok(s)
    s['eligibility']['reasons'].pop('financials_dependent')
_, r_d = build(no_reason)
check(not r_d['valid'] and any('reasons.financials_dependent' in e for e in r_d['errors']), 'D missing reason is rejected')

# E. Not dependent but statement-derived item still scored: rejected
def scored_anyway(s):
    dependent_false_ok(s)
    item(s, 'balance_sheet')['score'] = 1
_, r_e = build(scored_anyway)
check(not r_e['valid'] and any('balance_sheet' in e for e in r_e['errors']), 'E statement item scored while not dependent is rejected')

# F. Verified statements still need a statement source (unchanged rule)
def verified_no_source(s):
    s['eligibility']['financials_dependent'] = False
    s['eligibility']['reasons']['financials_dependent'] = '合成測試'
    s['sources'] = [x for x in s['sources'] if x.get('source_type') != 'financial_statement']
_, r_f = build(verified_no_source)
check(not r_f['valid'] and any('financial statement source' in e for e in r_f['errors']), 'F verified flag without statement source still rejected')

# G. Schema accepts the new optional flag and reason
s_g = copy.deepcopy(template)
dependent_false_ok(s_g)
errs = guard.schema_errors(s_g, json.loads((ROOT / 'assets/snapshot.schema.json').read_text(encoding='utf-8')), json.loads((ROOT / 'assets/snapshot.schema.json').read_text(encoding='utf-8')))
check(not errs, 'G schema accepts financials_dependent: ' + '; '.join(errs[:2]))

# H. (1.4.1) Declared not dependent, but financial_event_buffer (risk) still scored: rejected
def buffer_scored(s):
    dependent_false_ok(s)
    item(s, 'financial_event_buffer')['score'] = 2
_, r_h = build(buffer_scored)
check(not r_h['valid'] and any('financial_event_buffer' in e for e in r_h['errors']), 'H risk.financial_event_buffer scored while unverified is rejected')

# I. (1.4.1) Declared not dependent, but ROE metric still carries a value: rejected
def roe_present(s):
    dependent_false_ok(s)
    s['metrics']['roe_ttm']['value'] = 18
    s['metrics']['roe_ttm']['value_status'] = 'reported'
_, r_i = build(roe_present)
check(not r_i['valid'] and any('metrics.roe_ttm' in e for e in r_i['errors']), 'I ROE value present while unverified is rejected')

# J. (1.4.1) Declared not dependent, but valuation rests on P/B band (net assets): rejected
def pb_band(s):
    dependent_false_ok(s)
    s['valuation']['band'] = {'metric': 'pb', 'low': 1.0, 'median': 1.5, 'high': 2.0, 'current': 1.4,
                              'period': '5y', 'observations': None, 'basis': 'vendor_band',
                              'source_urls': ['https://example.com/band']}
_, r_j = build(pb_band)
check(not r_j['valid'] and any('valuation.band(pb)' in e for e in r_j['errors']), 'J P/B band while unverified is rejected')

# K. (1.4.1) Valuation method text mentions net assets / ROE: rejected
def method_text(s):
    dependent_false_ok(s)
    s['valuation']['method'] = 'ROE 與淨值倍數模型'
_, r_k = build(method_text)
check(not r_k['valid'] and any('valuation.method' in e for e in r_k['errors']), 'K valuation method using ROE/net assets while unverified is rejected')

# L. (1.4.1) A rejected waiver must not quietly yield a signal: derive treats it as dependent
def waiver_with_use(s):
    dependent_false_ok(s)
    item(s, 'financial_event_buffer')['score'] = 2
s_l = copy.deepcopy(template)
waiver_with_use(s_l)
r_l = guard.validate(s_l, derive_only=True)
check(r_l['derived'] is None or r_l['derived']['overall']['signal'] == 'unknown', 'L waiver with statement use derives no signal')

# M. (1.4.1) Non-statement metric names are not caught (book_to_bill is an industry indicator)
s_m = copy.deepcopy(template)
dependent_false_ok(s_m)
s_m['metrics']['book_to_bill'] = copy.deepcopy(s_m['metrics']['gross_margin_q2'])
check(not any('book_to_bill' in u for u in guard.statement_uses(s_m)), 'M book_to_bill is not treated as a statement metric')

# N. (1.4.2) Dependent but unread statements: financials_verified is fail, never limited; no signal derived
def fin_unread(s):
    s['eligibility']['financials_verified'] = False
    s['eligibility']['financials_dependent'] = True
_, r_n = build(fin_unread)
check(r_n['derived'] is None or r_n['derived']['overall']['signal'] == 'unknown', 'N dependent-but-unread statements derive no signal')

# O. (1.4.2) financials_verified validation may not be limited
def fin_limited(s):
    for v in s['validation']:
        if v['check'] == 'financials_verified':
            v['status'] = 'limited'
_, r_o = build(fin_limited)
check(not r_o['valid'] and any('limited is not allowed' in e for e in r_o['errors']), 'O financials_verified limited status is rejected')

fails = [m for ok, m in results if not ok]
print(json.dumps({'checks': len(results), 'failed': fails, 'passed': not fails}, ensure_ascii=False))
sys.exit(1 if fails else 0)
