"""Direct production regressions for rule 1.6.0; all values are synthetic."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import snapshot_guard as g

BASE = json.loads((ROOT / 'assets/snapshot.example.json').read_text())
count = 0


def check(ok, message):
    global count
    count += 1
    if not ok:
        raise AssertionError(message)


def run(s):
    result = g.validate(s, True)
    check(result['valid'], repr(result['errors']))
    out = g.derived_snapshot(s, result)
    o = out['overall']
    lights = {'green': '🟢', 'yellow': '🟡', 'red': '🔴', 'unknown': '⚪', 'major_risk': '🔴重大風險'}
    out['report_markdown'] = ('規則版本 %s\n合成回歸案例。\n整體投資訊號：%s；總分：%s；暫定：%s；信心：%s' % (
        out['rule_version'], lights[o['signal']], o['score'] if o['score'] is not None else '不計分',
        '是' if o['provisional'] else '否', {'high': '高', 'medium': '中', 'low': '低', None: '未評定'}[o['confidence']]))
    if out['rule_version'] == g.RULE_VERSION:
        out['report_markdown'] += '\n' + '\n'.join(label + '：本次未評估（合成回歸）' for label in g.SUMMARY_LABELS)
    out['report_sha256'] = g.report_hash(out)
    result = g.validate(out)
    check(result['valid'], repr(result['errors']))
    check(g.derived_snapshot(out, g.validate(out, True)) == out, 'idempotent derivation')
    return out


def reject(s, fragment):
    for derive in (True, False):
        result = g.validate(s, derive)
        check(not result['valid'] and any(fragment in x for x in result['errors']), repr(result['errors']))


def calculated(s, key, value, inputs):
    s['metrics'][key].update(value=value, value_status='calculated', actual_or_estimate='actual',
                             formula='documented standard formula', inputs=inputs)


def pb():
    s = deepcopy(BASE)
    s['valuation'].update(method='P/B', primary_metric='pb', band=None, multiple_basis='peers')
    s['valuation']['guardrails']['r2'].update(status='not_applicable', ttm_roe_pct=None, annual_roe_pct=[])
    s['valuation']['guardrails']['r1'].update(status='clean', source_urls=[s['sources'][0]['url']])
    s['valuation']['guardrails']['r1']['checks'].update(latest_book_value=50, previous_book_value=50,
        oci_share_of_book_change=0, listed_holding_share=0)
    for sc in s['valuation']['scenarios']:
        sc['assumptions'] = {'book_value_per_share': 50, 'multiple': sc['model_price'] / 50,
                             'currency': 'TWD', 'instrument': 'ordinary'}
        sc['formula'] = 'book_value_per_share * multiple'
    return s


def main():
    run(deepcopy(BASE))
    for index in range(3):
        s = deepcopy(BASE); s['valuation']['scenarios'][index]['model_price'] += 1
        reject(s, 'model_price must equal eps * multiple')
    for field, value in [('eps', None), ('eps', -1), ('eps', True), ('multiple', 0),
                         ('currency', 'USD'), ('instrument', 'adr'), ('pe', 999)]:
        s = deepcopy(BASE); s['valuation']['scenarios'][0]['assumptions'][field] = value
        reject(s, 'valuation.base')
    s = deepcopy(BASE); del s['valuation']['scenarios'][0]['assumptions']['multiple']
    reject(s, 'input multiple required')
    s = deepcopy(BASE); s['valuation']['scenarios'][0]['assumptions']['eps'] = 10 ** 400
    reject(s, 'input eps required')
    s = deepcopy(BASE); s['valuation']['primary_metric'] = 'other'
    reject(s, 'disagrees with P/E')
    s = deepcopy(BASE); s['valuation']['scenarios'][0]['model_price'] += 1e-10
    run(s)  # harmless floating-point noise
    s = deepcopy(BASE); s['valuation']['scenarios'][0]['model_price'] = 129.99
    reject(s, 'model_price must equal')
    run(pb())
    s = pb(); s['valuation']['scenarios'][1]['model_price'] = 91
    reject(s, 'model_price must equal book_value_per_share')

    for method, basis, amount in [('ev_sales', 'revenue', 1000), ('ev_ebitda', 'ebitda', 100)]:
        s = deepcopy(BASE)
        s['valuation'].update(primary_metric=method, method=method, band=None, multiple_basis='peers')
        s['valuation']['guardrails']['r2'].update(status='not_applicable', ttm_roe_pct=None, annual_roe_pct=[])
        for sc in s['valuation']['scenarios']:
            sc['assumptions'] = {basis: amount, 'multiple': (sc['model_price'] * 10 + 100) / amount,
                'net_debt': 100, 'shares': 10, 'adr_ratio': 1, 'currency': 'TWD', 'instrument': 'ordinary'}
        run(s)
        bad = deepcopy(s); bad['valuation']['scenarios'][2]['model_price'] += 1
        reject(bad, 'EV-to-equity')
        bad = deepcopy(s); bad['valuation']['scenarios'][0]['assumptions']['shares'] = 0
        reject(bad, 'input shares required')
        cash = deepcopy(s)
        for sc in cash['valuation']['scenarios']:
            sc['assumptions'].update(net_debt=-100, multiple=(sc['model_price'] * 10 - 100) / amount)
        run(cash)  # negative net debt is net cash, not invalid data
        adr = deepcopy(s); adr['security']['instrument'] = 'adr'
        for sc in adr['valuation']['scenarios']:
            sc['assumptions'].update(instrument='adr', adr_ratio=2, shares=20)
        run(adr)

    for inputs in [{'price': 1, 'eps_ttm': 999}, {'price': 100}, {'price': 100, 'eps_ttm': True}]:
        s = deepcopy(BASE); s['metrics']['pe_ttm']['inputs'] = inputs
        reject(s, 'metrics.pe_ttm')
    s = deepcopy(BASE); s['valuation']['band']['current'] = 999
    reject(s, 'band.current')
    s = deepcopy(BASE); del s['valuation']['band']['current_metric']
    reject(s, 'current_metric')
    s = deepcopy(BASE); s['valuation']['band']['current_metric'] = 'gross_margin_q2'
    reject(s, 'current_metric')
    s = deepcopy(BASE)
    s['metrics']['pe_forward'] = deepcopy(s['metrics']['pe_ttm'])
    s['metrics']['pe_forward'].update(value=25, inputs={'price': 100, 'eps_forward': 4}, period='next year', actual_or_estimate='estimate')
    s['valuation']['band'].update(current=25, current_metric='pe_forward')
    run(s)
    s['metrics']['pe_forward']['inputs']['eps_forward'] = 5
    reject(s, 'declared ratio inputs')
    s = pb(); s['metrics']['pb_current'] = deepcopy(s['metrics']['pe_ttm'])
    s['metrics']['pb_current'].update(value=2, inputs={'price': 100, 'book_value_per_share': 50})
    s['valuation']['band'] = deepcopy(BASE['valuation']['band'])
    s['valuation']['band'].update(metric='pb', low=1, median=2, high=3, current=2, current_metric='pb_current')
    s['valuation']['guardrails']['r2'].update(status='comparable', ttm_roe_pct=18, annual_roe_pct=[18])
    run(s)
    s['metrics']['pb_current']['inputs']['price'] = 90
    reject(s, 'metrics.pb_current')

    cases = [
        ('market_cap', 1000, {'price': 100, 'shares': 10, 'adr_ratio': 1}),
        ('roe_ttm', 20, {'net_income_common': 20, 'equity_begin_common': 80, 'equity_end_common': 120}),
        ('fcf_ttm', -10, {'cfo_ttm': 20, 'cash_capex_ttm': 30}),
        ('revenue_growth_q2', 20, {'current': 120, 'previous': 100}),
        ('eps_growth_q2', -20, {'current': 4, 'previous': 5}),
        ('gross_margin_q2', 30, {'gross_profit': 30, 'revenue': 100}),
        ('cash_yield', 2, {'cash_dividend_12m': 2, 'price': 100}),
    ]
    for key, value, inputs in cases:
        s = deepcopy(BASE); calculated(s, key, value, inputs)
        run(s)
        s['metrics'][key]['value'] += 1
        reject(s, 'metrics.' + key)
    for key, inputs in [('eps_growth_q2', {'current': 1, 'previous': 0}),
                        ('roe_ttm', {'net_income_common': 20, 'equity_begin_common': -80, 'equity_end_common': 120}),
                        ('fcf_ttm', {'cfo_ttm': 20, 'cash_capex_ttm': -30})]:
        s = deepcopy(BASE); calculated(s, key, 50, inputs)
        reject(s, 'metrics.' + key)

    # Published future events remain usable; future knowledge does not.
    for published in ['2026-10-09', '2026-10-08T13:30:01+08:00', '2026-10-08T05:30:01Z']:
        s = deepcopy(BASE); s['events'][0]['published_at'] = published
        reject(s, 'published_at after data cutoff')
    s = deepcopy(BASE); s['events'][0]['published_at'] = '2026-10-08T05:30:00Z'
    run(s)
    for status, event_date in [('occurred', '2026-11-12'), ('occurred', None), ('scheduled', None), ('scheduled', '2026-10-07')]:
        s = deepcopy(BASE); s['events'][0].update(status=status, event_date=event_date)
        reject(s, 'events[0]')
    s = deepcopy(BASE); s['events'][0].update(status='occurred', event_date='2026-10-07')
    run(s)
    s = deepcopy(BASE); s['events'][0]['published_at'] = None
    reject(s, 'verified publication date')
    s['events'][0].update(status='unknown', event_date=None)
    run(s)

    # An invalid model cannot reach green through derive, including the CLI.
    bad = deepcopy(BASE)
    for group in bad['scores'].values():
        for x in group['items']: x['score'] = 2
    bad['scores']['valuation']['items'][1]['score'] = 1
    bad['valuation']['scenarios'][0]['assumptions'].update(eps=5, multiple=20)
    reject(bad, 'model_price must equal')
    good = deepcopy(bad); good['valuation']['scenarios'][0]['model_price'] = 100
    check(run(good)['overall']['signal'] == 'yellow', 'corrected arithmetic produces yellow')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'bad.json'; path.write_text(json.dumps(bad))
        command = subprocess.run([sys.executable, str(ROOT/'scripts/snapshot_guard.py'), str(path), '--derive'], capture_output=True, text=True)
        check(command.returncode == 2 and not json.loads(command.stdout)['valid'], 'CLI derive refuses invalid arithmetic')

    archived = json.loads((ROOT / 'tests/snapshot.rule-1.5.0.json').read_text())
    original = json.dumps(archived, sort_keys=True)
    old = run(archived)
    check(json.dumps(archived, sort_keys=True) == original, 'archived input unchanged')
    check(g.validate(old)['calculation_checks'] == 'archived_rules_only', 'old pass not labelled new checks')
    check('rule_version: incompatible' in g.comparison_status(run(deepcopy(BASE)), old)['reasons'],
          'rule 1.5/1.6 scores not directly comparable because of rule versions')
    print(json.dumps({'passed': True, 'checks': count, 'scope': 'direct validator and CLI calls; synthetic only'}))


if __name__ == '__main__':
    main()
