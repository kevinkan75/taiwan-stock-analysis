"""Direct regression checks for model-1.2 valuation guardrails. Synthetic only."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import snapshot_guard as guard

BASE = json.loads((ROOT / 'tests/snapshot.model-1.2.json').read_text())
URL = BASE['sources'][0]['url']
count = 0


def check(value, message):
    global count
    count += 1
    if not value:
        raise AssertionError(message)


def item(s, name):
    return next(x for x in s['scores']['valuation']['items'] if x['check'] == name)


def model(s, name):
    return next(x for x in s['valuation']['scenarios'] if x['label'] == name)


def run(s, expected):
    result = guard.validate(s, derive_only=True)
    check(result['valid'], 'derive: ' + repr(result['errors']))
    out = guard.derived_snapshot(s, result)
    scores = [item(out, k)['score'] for k in ['model_upside', 'comparable_valuation', 'scenario_resilience']]
    check(scores == expected, 'effective scores: ' + repr(scores))
    check(guard.validate(out)['valid'], 'round-trip')
    check(guard.derived_snapshot(out, guard.validate(out, True)) == out, 'derive is idempotent')
    return out


def rejected(s, fragment):
    result = guard.validate(s, True)
    check(not result['valid'] and any(fragment in x for x in result['errors']), 'rejection: ' + repr(result['errors']))


def pb(s, status):
    s['valuation']['primary_metric'] = 'pb'
    s['valuation']['guardrails']['r1'].update(status=status, source_urls=[URL])
    s['valuation']['guardrails']['r1']['checks'].update(latest_book_value=50, previous_book_value=40,
                                                      oci_share_of_book_change=.1, listed_holding_share=.1)
    if status in ('adjusted', 'four_quarter_average'):
        r1 = s['valuation']['guardrails']['r1']
        r1['reference_book_value'] = 35 if status == 'four_quarter_average' else 40
        if status == 'four_quarter_average':
            r1['quarterly_book_values'] = [20, 30, 40, 50]
        for x in s['valuation']['scenarios']:
            x['assumptions'] = {'book_value_basis': status, 'book_value_per_share': r1['reference_book_value'],
                                'multiple': x['model_price'] / r1['reference_book_value']}
            x['formula'] = 'book_value_per_share * multiple'


def conflict(s, primary=130, secondary=80):
    model(s, 'base')['model_price'] = primary
    s['valuation']['guardrails']['r3'].update(status='checked', source_urls=[URL], models=[
        {'method': s['valuation']['method'], 'base_model_price': primary, 'currency': 'TWD', 'instrument': 'ordinary',
         'source_urls': [URL], 'post_adjustment': True, 'reason': '合成主方法已完成適用的R1/R2檢查'},
        {'method': '合成交叉方法', 'base_model_price': secondary, 'currency': 'TWD', 'instrument': 'ordinary',
         'source_urls': [URL], 'post_adjustment': True, 'reason': '合成交叉方法已完成適用的R1/R2檢查'}])


def main():
    run(deepcopy(BASE), [2, 1, 2])
    s = deepcopy(BASE); pb(s, 'unadjusted')
    out = run(s, [1, 1, 1])
    check({x['check'] for x in out['valuation']['applied_adjustments']} == {'model_upside', 'scenario_resilience'}, 'R1 affects both scenarios')
    s['valuation']['guardrails']['r1']['checks']['latest_book_value'] = None
    rejected(s, 'known latest_book_value')
    s = deepcopy(BASE); pb(s, 'unconfirmed')
    out = run(s, [None, 1, None])
    check(out['scores']['valuation']['coverage'] == 1 and out['overall']['signal'] == 'unknown', 'nulls do not manufacture coverage')
    for status in ['adjusted', 'four_quarter_average']:
        s = deepcopy(BASE); pb(s, status)
        run(s, [2, 1, 2])
        model(s, 'conservative')['assumptions']['book_value_per_share'] = 10
        rejected(s, 'every priced scenario')
    s = deepcopy(BASE); pb(s, 'four_quarter_average')
    s['valuation']['guardrails']['r1']['reference_book_value'] = None
    rejected(s, 'positive reference_book_value')
    s = deepcopy(BASE); pb(s, 'four_quarter_average')
    model(s, 'base')['assumptions']['multiple'] += 1
    rejected(s, 'reference_book_value *')
    s = deepcopy(BASE); pb(s, 'four_quarter_average')
    s['valuation']['guardrails']['r1']['reference_book_value'] = 36
    rejected(s, 'four-quarter average')
    s['valuation']['guardrails']['r1']['quarterly_book_values'] = [20, 30, 40]
    rejected(s, 'exactly four')
    s = deepcopy(BASE); s['valuation']['primary_metric'] = 'pb'
    rejected(s, 'P/B valuation')
    s = deepcopy(BASE); s['valuation']['method'] = 'P/B × ROE'
    rejected(s, 'P/B valuation')
    s = deepcopy(BASE); pb(s, 'clean')
    rejected(s, 'trigger found')
    s['valuation']['guardrails']['r1']['checks']['latest_book_value'] = 46
    run(s, [2, 1, 2])
    s['valuation']['guardrails']['r1']['checks']['listed_holding_share'] = .2
    rejected(s, 'trigger found')
    s['valuation']['guardrails']['r1']['checks']['listed_holding_share'] = .1
    s['valuation']['guardrails']['r1']['checks']['oci_share_of_book_change'] = None
    rejected(s, 'all book-quality')
    s = deepcopy(BASE); s['valuation']['guardrails']['r2']['status'] = 'unconfirmed'
    run(s, [1, 1, 2])
    s = deepcopy(BASE); s['valuation']['guardrails']['r2']['ttm_roe_pct'] = 8
    rejected(s, 'below half')
    r2 = s['valuation']['guardrails']['r2']; band = s['valuation']['band']
    selected = (band['low'] + band['median']) / 2
    r2.update(status='adjusted_multiple', adjustment_method='approx_p25', selected_multiple=selected)
    model(s, 'base')['assumptions']['multiple'] = selected
    model(s, 'base')['assumptions']['eps'] = model(s, 'base')['model_price'] / selected
    run(s, [2, 1, 2])
    model(s, 'base')['assumptions']['eps'] += 1
    rejected(s, 'base price must equal')
    model(s, 'base')['assumptions']['eps'] -= 1
    r2['selected_multiple'] = selected + 1
    rejected(s, 'approx_p25')
    s = deepcopy(BASE); s['valuation']['guardrails']['r2']['status'] = 'not_applicable'
    rejected(s, 'historical valuation')
    s = deepcopy(BASE); s['valuation']['guardrails']['r2']['annual_roe_pct'] = []
    rejected(s, 'historical annual ROE')
    s = deepcopy(BASE); conflict(s); item(s, 'comparable_valuation')['score'] = 2
    out = run(s, [1, 1, 2])
    item(out, 'model_upside')['score'] = 2
    check(not guard.validate(out)['valid'], 'default validation rejects uncapped score')
    # The originally rejected, manually lowered R3 score is now accepted.
    item(s, 'model_upside')['score'] = 1
    run(s, [1, 1, 2])
    s = deepcopy(BASE); conflict(s, 115, 80); item(s, 'comparable_valuation')['score'] = 2
    run(s, [1, 2, 2])
    s = deepcopy(BASE); conflict(s, 130, 90); item(s, 'comparable_valuation')['score'] = 2
    run(s, [2, 2, 2])
    for field, value, error in [('currency', 'USD', 'currency'), ('instrument', 'adr', 'instrument'),
                               ('post_adjustment', False, 'wrong constant'), ('source_urls', ['https://example.invalid/absent'], 'source missing')]:
        s = deepcopy(BASE); conflict(s)
        s['valuation']['guardrails']['r3']['models'][1][field] = value
        rejected(s, error)
    s = deepcopy(BASE); conflict(s)
    s['valuation']['guardrails']['r3']['models'][0]['base_model_price'] = 140
    rejected(s, 'matching post-adjustment')
    s = deepcopy(BASE); conflict(s)
    s['valuation']['guardrails']['r3']['models'][1]['method'] = s['valuation']['method']
    rejected(s, 'distinct')
    s = deepcopy(BASE); conflict(s)
    s['valuation']['guardrails']['r3']['status'] = 'unconfirmed'
    rejected(s, 'do not hide')
    s = deepcopy(BASE); pb(s, 'unadjusted'); conflict(s)
    s['valuation']['guardrails']['r2']['status'] = 'unconfirmed'
    item(s, 'comparable_valuation')['score'] = 2
    out = run(s, [1, 1, 1])
    check({x['rule'] for x in out['valuation']['applied_adjustments']} == {'R1', 'R2', 'R3'}, 'all applicable constraints retained')
    out['valuation']['applied_adjustments'] = []
    check(not guard.validate(out)['valid'], 'default validation requires derived audit record')
    s = deepcopy(BASE); pb(s, 'unadjusted'); model(s, 'base')['model_price'] = 70
    run(s, [0, 1, 1])
    s = deepcopy(BASE); conflict(s); item(s, 'model_upside')['score'] = None
    run(s, [None, 1, 2])
    s = deepcopy(BASE); del s['valuation']['guardrails']
    rejected(s, 'guardrails')
    # Archived models keep their original calculation rules.
    s = deepcopy(BASE); s['schema_version'], s['model_version'] = '1.3', '1.1'
    for name in ['primary_metric', 'guardrails', 'applied_adjustments']:
        del s['valuation'][name]
    result = guard.validate(s, True)
    check(result['valid'] and guard.validate(guard.derived_snapshot(s, result))['valid'], 'archived schema1.3/model1.1 remains valid')
    print(json.dumps({'passed': True, 'checks': count, 'scope': 'direct calls to production snapshot_guard, synthetic only'}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, ValueError, KeyError) as error:
        print(json.dumps({'passed': False, 'checks': count, 'error': str(error)}, ensure_ascii=False))
        sys.exit(2)
