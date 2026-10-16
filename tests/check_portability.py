#!/usr/bin/env python3
"""Run offline fixed synthetic cases; this is not cross-model validation."""
import ast
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import finance_math  # noqa: E402
import snapshot_guard as guard  # noqa: E402


def merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def cases():
    with open(ROOT / 'tests/portability_cases.json', encoding='utf-8') as source:
        return json.load(source)


# --- Rule version 1.3.0 reference implementation (phase 1 text rules; not enforced by snapshot_guard) ---
WEIGHTS = {'fundamentals': 0.25, 'growth': 0.20, 'valuation': 0.25, 'industry': 0.15, 'risk': 0.15}


def r1_triggered(bvps_quarters, oci_share, holding_ratio):
    return abs(bvps_quarters[-1] / bvps_quarters[-2] - 1) > 0.15 or oci_share > 0.5 or holding_ratio >= 0.20


def upside_score(pct):
    return 0 if pct < -10 else (1 if pct <= 15 else 2)


def resilience_score(pct):
    drop = -pct
    return 0 if drop > 30 else (1 if drop > 15 else 2)


def median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def r2_triggered(annual_roe, ttm_roe):
    return ttm_roe < median(annual_roe) / 2


def r3_conflict(price, model_a, model_b):
    ups = [model_a / price - 1, model_b / price - 1]
    return (max(ups) > 0.15 and min(ups) < -0.10)


def r5_status(count, minimum=240):
    return 'computed' if count >= minimum else 'insufficient_data'


def r10_cross(hist, close):
    """Rule 1.3.1 cross strength: returns (cross_day_weak, status) for the latest cross, or None."""
    cross = None
    for i in range(1, len(hist)):
        if (hist[i - 1] <= 0 < hist[i]) or (hist[i - 1] >= 0 > hist[i]):
            cross = i
    if cross is None:
        return None
    floor = close * 0.001
    weak_day = abs(hist[cross]) < floor
    days = len(hist) - cross
    if days < 3:
        return weak_day, 'pending'
    return weak_day, ('confirmed' if abs(hist[-1]) >= floor else 'weak')


def r7_boundary(value, threshold):
    return abs(value - threshold) <= threshold * 0.10 + 1e-9 if threshold else False


def facet_score(items):
    valid = [x for x in items if x is not None]
    return sum(valid) / len(valid) / 2 * 100 if len(valid) >= 2 else None


def overall_signal(items_by_facet):
    scores = {k: facet_score(v) for k, v in items_by_facet.items()}
    total = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    if total < 40 or scores['valuation'] < 40 or scores['risk'] < 40:
        return 'red'
    if total >= 75 and scores['valuation'] >= 75 and scores['risk'] >= 75 and scores['fundamentals'] >= 40 and scores['growth'] >= 40:
        return 'green'
    return 'yellow'


def run_rule_cases(data, check):
    cases = {c['id']: c for c in data['rule_cases']}
    c = cases['bvps_revaluation']; i, e = c['input'], c['expected']
    check(r1_triggered(i['bvps_quarters'], i['oci_share'], i['holding_ratio']) is e['triggered'], 'R1 trigger')
    adj = sum(i['bvps_quarters']) / 4
    base, cons = i['pb_base'] * adj, i['pb_conservative'] * adj
    check(round(adj, 1) == e['adjusted_bvps'] and round(base, 1) == e['base_price'], 'R1 adjusted prices')
    up, dn = (base / i['price'] - 1) * 100, (cons / i['price'] - 1) * 100
    check(round(up, 1) == e['base_upside_pct'] and upside_score(up) == e['model_upside'], 'R1 base upside')
    check(round(cons, 1) == e['conservative_price'] and round(dn, 1) == e['conservative_downside_pct']
          and resilience_score(dn) == e['scenario_resilience'], 'R1 conservative case')
    raw = i['pb_base'] * i['bvps_quarters'][-1]
    check(upside_score((raw / i['price'] - 1) * 100) == e['unadjusted_model_upside'], 'R1 unadjusted inflation')
    c = cases['roe_not_comparable']; i, e = c['input'], c['expected']
    check(median(i['annual_roe']) == e['range_median'], 'R2 median')
    check(r2_triggered(i['annual_roe'], i['ttm_roe_a']) is e['triggered_a'] and r2_triggered(i['annual_roe'], i['ttm_roe_b']) is e['triggered_b'], 'R2 trigger')
    c = cases['method_conflict']; i, e = c['input'], c['expected']
    check([r3_conflict(i['price'], a, b) for a, b in i['pairs']] == e['conflict'], 'R3 conflict')
    c = cases['insufficient_bars']
    check([r5_status(n) for n in c['input']['counts']] == c['expected']['status'], 'R5 240 threshold')
    c = cases['gate4_boundary']; i, e = c['input'], c['expected']
    check([r7_boundary(v, i['threshold_bp']) for v in i['us10y_bp']] == e['boundary'], 'R7 boundary band')
    lo, hi = i['sources_straddle']
    check(((lo < i['threshold_bp']) != (hi < i['threshold_bp']) or lo == i['threshold_bp']) is e['straddle_boundary'], 'R7 sources straddle')
    n = i['gate_unfavorable_known'] + 1
    check(('red' if n >= 2 else 'yellow' if n == 1 else 'green') == e['gate_with_boundary_unfavorable']
          and ('red' if n - 1 >= 2 else 'yellow' if n - 1 == 1 else 'green') == e['gate_if_neutral'], 'R7 gate lights')
    c = cases['macd_cross_strength']
    for sample, exp in zip(c['input']['samples'], c['expected']):
        got = r10_cross(sample['hist'], sample['close'])
        check(list(got) == exp, 'R10 cross strength ' + repr(sample['hist']))
    c = cases['fragile_conclusion']; i, e = c['input'], c['expected']
    items = i['items']
    check(overall_signal(items) == e['base_signal'], 'R6 base signal')
    facet, idx = i['reserved'][0].split('.'); idx = int(idx)
    flipped = {k: list(v) for k, v in items.items()}
    flipped[facet][idx] = e['flip_to']
    check((overall_signal(flipped) != e['base_signal']) is e['fragile'] and overall_signal(flipped) == e['flipped_signal'], 'R6 flip')


def main():
    checks = 0
    def check(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)
    skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
    links = re.findall(r'\]\((references/[^)]+)\)', skill)
    check(len(set(links)) == 14 and all((ROOT / x).is_file() for x in links), "reference links")
    stdlib = {'argparse', 'os', 'shutil', 'base64', 'html', 'urllib', 'ast', 'copy', 'datetime', 'fractions', 'hashlib', 'unicodedata', 'subprocess', 'tempfile', 'io', 'json', 'math', 'pathlib', 're', 'sys'}
    for path in [*(ROOT / 'scripts').glob('*.py'), *(ROOT / 'tests').glob('*.py')]:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        imports = {n.name.split('.')[0] for x in ast.walk(tree) if isinstance(x, ast.Import) for n in x.names}
        imports |= {x.module.split('.')[0] for x in ast.walk(tree) if isinstance(x, ast.ImportFrom)}
        check(imports <= stdlib | {'finance_math', 'snapshot_guard', 'rules_core', 'decision_guard', 'etf_guard', 'numeric_rules', 'decision_numeric', 'report_checks', 'review_guard', 'evidence_audit', 'audit_fixtures', 'financial_history', 'financial_history_fixtures', 'html_export', 'research_views', 'check_evidence_audit', 'itertools'}, path.name + ': portable dependencies')
    data = cases()
    for case in data['cases']:
        snapshot = merge(data['template'], case['overrides'])
        result = guard.validate(snapshot, derive_only=True)
        expected = case['expected']
        if expected['invalid']:
            check(not result['valid'], case['id'] + ': expected rejection')
            continue
        check(result['valid'], case['id'] + ': ' + repr(result['errors']))
        out = guard.derived_snapshot(snapshot, result)
        check(guard.validate(out)['valid'], case['id'] + ': default validator round trip')
        check(out['overall']['signal'] == expected['overall_signal'], case['id'] + ': overall signal')
        check(out['technical']['signal'] == expected['technical_signal'], case['id'] + ': technical signal')
        if case['id'] == 'rounding_boundary':
            check(out['overall']['score'] == 75 and out['overall']['raw_score'] < 75, 'rounding before threshold regression')
        if case['id'] == 'complete':
            valid = out
    for field, value in [('score', 99), ('signal', 'yellow'), ('raw_score', 99.0)]:
        broken = deepcopy(valid)
        broken['overall'][field] = value
        check(not guard.validate(broken)['valid'], 'reject forged overall ' + field)
    broken = deepcopy(valid)
    broken['scores']['fundamentals']['items'][0]['score'] = True
    check(not guard.validate(broken)['valid'], 'boolean must not act as score one')
    broken = deepcopy(valid)
    broken['scores']['growth']['items'][0]['check'] = 'realized_eps'
    check(not guard.validate(broken)['valid'], 'duplicate canonical score check')
    broken = deepcopy(valid)
    broken['metrics']['price']['value'] = None
    check(not guard.validate(broken)['valid'], 'missing value cannot retain reported status')
    broken = deepcopy(valid)
    broken['metrics']['price']['value'] = 0
    check(not guard.validate(broken)['valid'], 'verified zero price')
    broken['eligibility']['quote_verified'] = False
    broken['eligibility']['quote_is_current'] = False
    check(not guard.validate(broken)['valid'], 'unverified zero is not missing price')
    broken = deepcopy(valid)
    broken['scores']['fundamentals']['items'][0]['score'] = 2.0
    check(guard.validate(broken)['valid'], 'JSON enum accepts numerically equal integer-valued number')
    broken = deepcopy(valid)
    del broken['metrics']['cash_yield']
    check(not guard.validate(broken)['valid'], 'all ten core metrics must be present, even when null')
    broken = deepcopy(valid)
    broken['metrics']['eps_ttm']['value'] = -1
    check(not guard.validate(broken)['valid'], 'nonpositive EPS invalidates numeric PE')
    broken = deepcopy(valid)
    broken['metrics']['pe_ttm']['value'] = 21
    check(not guard.validate(broken)['valid'], 'calculated PE must match inputs')
    broken = deepcopy(valid)
    broken['quote_at'] = '2026-10-08T13:30:00'
    check(not guard.validate(broken)['valid'], 'naive timestamp')
    broken = deepcopy(valid)
    broken['sources'][0]['published_at'] = '2026-10-09'
    check(not guard.validate(broken)['valid'], 'future-publication leakage')
    broken = deepcopy(valid)
    broken['metrics']['price']['source_url'] = ['https://fixture.invalid/missing']
    check(not guard.validate(broken)['valid'], 'missing source catalog entry')
    broken = deepcopy(valid)
    broken['schema_version'] = '1.1'
    check(guard.validate(broken)['scope'] == 'legacy_not_validated', 'do not infer legacy eligibility')
    for payload in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"inputs":{"x":1e999}}']:
        try:
            guard.load_json(StringIO(payload))
            check(False, 'reject duplicate/nonfinite input')
        except ValueError:
            check(True, 'reject duplicate/nonfinite input')
    try:
        guard.audit_keywords({'oneOf': []})
        check(False, 'unsupported schema must fail closed')
    except ValueError:
        check(True, 'unsupported schema must fail closed')
    # Boundary checks use fixed exact values, not the validator's derived answer.
    for price, expected in [(89, 0), (90, 1), (115, 1), (116, 2)]:
        snapshot = deepcopy(data['template'])
        snapshot['valuation']['scenarios'][0]['model_price'] = price
        snapshot['scores']['valuation']['items'][0]['score'] = expected
        check(guard.validate(snapshot, derive_only=True)['valid'], 'upside boundary ' + str(price))
    for price, expected in [(69, 0), (70, 1), (84, 1), (85, 2)]:
        snapshot = deepcopy(data['template'])
        snapshot['valuation']['scenarios'][1]['model_price'] = price
        snapshot['scores']['valuation']['items'][2]['score'] = expected
        check(guard.validate(snapshot, derive_only=True)['valid'], 'downside boundary ' + str(price))
    # Model 1.1: provisional signal tier and valuation-basis fields.
    def v11(base):
        out = deepcopy(base)
        out['schema_version'], out['model_version'] = '1.3', '1.1'
        out['overall'].update({'provisional': False, 'confidence': None})
        out['valuation'].update({'multiple_basis': 'vendor_band', 'eps_basis': 'external_multi', 'band': None})
        return out
    def derived11(snapshot):
        result = guard.validate(snapshot, derive_only=True)
        check(result['valid'], 'model 1.1 derive: ' + repr(result['errors']))
        out = guard.derived_snapshot(snapshot, result)
        check(guard.validate(out)['valid'], 'model 1.1 round trip')
        return out['overall']
    full = derived11(v11(data['template']))
    check(full['provisional'] is False and full['confidence'] == 'high' and full['signal'] in ('green', 'yellow', 'red'), 'model 1.1 full eligibility')
    medium = v11(data['template'])
    medium['eligibility']['valuation_supported'] = False
    overall = derived11(medium)
    check(overall['provisional'] is True and overall['confidence'] == 'medium' and overall['score'] is not None, 'provisional medium')
    low = deepcopy(medium)
    for item in low['scores']['fundamentals']['items']:
        item['score'] = None
    for item in low['scores']['fundamentals']['items'][:1]:
        item['score'] = 2
    for item in low['scores']['growth']['items'] + low['scores']['valuation']['items'] + low['scores']['industry']['items'] + low['scores']['risk']['items']:
        if item['score'] is not None:
            item['score'] = 2
    overall = derived11(low)
    check(overall['provisional'] is True and overall['confidence'] == 'low' and overall['signal'] != 'green', 'provisional low never green')
    no_valuation = deepcopy(medium)
    for item in no_valuation['scores']['valuation']['items']:
        item['score'] = None
    overall = derived11(no_valuation)
    check(overall['signal'] == 'unknown' and overall['provisional'] is False, 'no provisional signal without valuation')
    stale = deepcopy(medium)
    stale['eligibility']['quote_is_current'] = False
    check(derived11(stale)['signal'] == 'unknown', 'no provisional signal on stale quote')
    risk = deepcopy(medium)
    risk['major_risk'].update({'confirmed': True, 'reason': '合成重大風險', 'source_urls': [risk['sources'][0]['url']]})
    check(derived11(risk)['signal'] == 'major_risk', 'major risk precedes provisional')
    broken = deepcopy(valid)
    broken['overall']['provisional'] = False
    check(not guard.validate(broken)['valid'], 'model 1.0 rejects model 1.1 fields')
    broken = v11(data['template'])
    broken['model_version'] = '1.0'
    check(not guard.validate(broken, derive_only=True)['valid'], 'schema/model version pairing')
    broken = v11(data['template'])
    broken['valuation']['multiple_basis'] = None
    check(not guard.validate(broken, derive_only=True)['valid'], 'model scenarios need stated bases')
    broken = v11(data['template'])
    broken['valuation']['band'] = {'metric': 'pe', 'low': 10, 'median': 15, 'high': 20, 'current': 18,
                                   'period': '2024-01..2025-08', 'observations': 20, 'basis': 'self_history',
                                   'source_urls': [broken['sources'][0]['url']]}
    check(not guard.validate(broken, derive_only=True)['valid'], 'self-computed band needs 36 observations')
    broken['valuation']['band'].update({'basis': 'vendor_band', 'observations': None})
    check(guard.validate(broken, derive_only=True)['valid'], 'labelled vendor band accepted')
    broken['valuation']['band']['median'] = 25
    check(not guard.validate(broken, derive_only=True)['valid'], 'band order')
    check(finance_math.calculate({'price': 500, 'eps_ttm': 25})['pe_ttm'] == 20, 'PE math')
    check(finance_math.calculate({'price': 500, 'eps_ttm': -1})['pe_ttm'] is None, 'nonpositive EPS')
    check(finance_math.rsi([100] * 250) == 50, 'flat RSI')
    check(finance_math.sma([100] * 250, 120) == 100, 'SMA math')
    run_rule_cases(data, check)
    docs = {p: (ROOT / p).read_text(encoding='utf-8') for p in ['SKILL.md', 'references/scoring.md', 'references/data-and-methods.md', 'references/market.md', 'references/output-and-history.md', 'references/etf.md']}
    for needle, where in [('規則版本 1.14.0', 'SKILL.md'), ('依賴的定義', 'SKILL.md'), ('以內容判定', 'SKILL.md'), ('輸出前對表', 'SKILL.md'), ('聚焦模式', 'references/output-and-history.md'), ('交叉幅度', 'references/scoring.md'), ('樣本內統計', 'references/data-and-methods.md'), ('預估與目標價標示', 'references/data-and-methods.md'), ('工作立場', 'SKILL.md'), ('反方審查', 'SKILL.md'), ('結論敏感度檢查', 'references/scoring.md'), ('資格三態', 'references/scoring.md'), ('淨值品質檢查', 'references/data-and-methods.md'), ('240筆', 'references/data-and-methods.md'), ('邊界值與來源矛盾', 'references/market.md'), ('ETF快速版輸出', 'references/etf.md'), ('市場快照輸出與存檔格式', 'references/market.md'), ('Asia/Taipei', 'references/data-and-methods.md'), ('時間、截止與最新性', 'references/data-and-methods.md'), ('較新的申報或修正報告', 'references/data-and-methods.md'), ('事件與風險核對', 'references/data-and-methods.md'), ('下次財報日期須查證', 'references/data-and-methods.md'), ('市場正在交易什麼', 'references/output-and-history.md'), ('優先使用同一對話中完整可見的前次報告', 'references/output-and-history.md'), ('不編造前次燈號', 'references/output-and-history.md')]:
        check(needle in docs[where], 'rule text present: ' + needle)
    skill_text = docs['SKILL.md']
    for name, where in [('時間、截止與最新性', 'references/data-and-methods.md'), ('交付檢核', 'references/data-and-methods.md'), ('口徑優先', 'references/data-and-methods.md'), ('估值操作', 'references/data-and-methods.md'), ('技術資料', 'references/data-and-methods.md'), ('事件與風險核對', 'references/data-and-methods.md'), ('投資邏輯與估值', 'references/output-and-history.md'), ('歷次比較', 'references/output-and-history.md'), ('保存報告與快照', 'references/output-and-history.md'), ('聚焦模式', 'references/output-and-history.md'), ('交叉幅度', 'references/scoring.md'), ('結論敏感度檢查', 'references/scoring.md')]:
        check(name in skill_text and name in docs[where], 'SKILL.md pointer resolves: ' + name)
    for name, where in [('ETF快速版輸出', 'references/etf.md'), ('市場快照輸出與存檔格式', 'references/market.md')]:
        check(name in docs['references/output-and-history.md'] and name in docs[where], 'output pointer resolves: ' + name)
    check('## ETF快速版\n' not in docs['references/output-and-history.md'] and '## 市場快照輸出（市場模式）' not in docs['references/output-and-history.md'], 'mode templates are not duplicated in output-and-history')
    json_blocks = [b for p in sorted((ROOT / 'references').glob('*.md')) for b in re.findall(r'```json\n(.*?)```', p.read_text(encoding='utf-8'), flags=re.S)]
    check(len(json_blocks) >= 2, 'JSON templates found in references')
    for block in json_blocks:
        json.loads(block)
    check(True, 'all JSON templates in references parse')
    print(json.dumps({'passed': True, 'checks': checks, 'fixed_cases': len(data['cases']), 'rule_cases': len(data['rule_cases']),
                      'scope': 'offline synthetic and local runtime only', 'cross_model_tested': False}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, ValueError, KeyError, OSError) as error:
        print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=False))
        sys.exit(2)
