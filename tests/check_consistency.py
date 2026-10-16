"""Direct synthetic regressions: prose, qualification, sensitivity and provenance."""
from copy import deepcopy
import hashlib
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


def item(s, name):
    return next(x for dim in s['scores'].values() for x in dim['items'] if x['check'] == name)


def status(s, name, value):
    s['eligibility'][name] = value
    next(x for x in s['validation'] if x['check'] == name)['status'] = value


def run(s):
    r = g.validate(s, True)
    check(r['valid'], repr(r['errors']))
    out = g.derived_snapshot(s, r)
    if out['model_version'] == '1.3':
        overall = out['overall']
        light = {'unknown':'⚪','green':'🟢','yellow':'🟡','red':'🔴','major_risk':'🔴重大風險'}[overall['signal']]
        confidence = {'high':'高','medium':'中','low':'低',None:'未評定'}[overall['confidence']]
        out['report_markdown'] = '\n'.join(line for line in out['report_markdown'].splitlines() if '整體投資訊號' not in line)
        out['report_markdown'] += '\n整體投資訊號：%s；總分：%s；暫定：%s；信心：%s' % (light, overall['score'] if overall['score'] is not None else '不計分', '是' if overall['provisional'] else '否', confidence)
        if out['rule_version'] == g.RULE_VERSION and not any(label + '：' in out['report_markdown'] for label in g.SUMMARY_LABELS):
            out['report_markdown'] += '\n' + '\n'.join(label + '：本次未評估（合成回歸）' for label in g.SUMMARY_LABELS)
        out['report_sha256'] = g.report_hash(out)
    check(g.validate(out)['valid'], 'roundtrip: ' + repr(g.validate(out)['errors']))
    check(g.derived_snapshot(out, g.validate(out, True)) == out, 'idempotent')
    return out


def reject(s, fragment):
    r = g.validate(s, True)
    check(not r['valid'] and any(fragment in x for x in r['errors']), repr(r['errors']))


def waiver():
    s = deepcopy(BASE)
    status(s, 'financials_verified', 'fail')
    s['eligibility']['financials_dependent'] = False
    s['eligibility']['reasons']['financials_dependent'] = '未核對完整報表；已清空ROE、自由現金流、負債比、流動比、淨值'
    for name in g.STATEMENT_CHECKS:
        item(s, name)['score'] = None
    for key, value in s['metrics'].items():
        if g.STATEMENT_METRIC_RE.search(key):
            value.update(value=None, value_status='missing', formula=None, inputs=None)
    s['valuation']['guardrails']['r2'].update(status='unconfirmed', ttm_roe_pct=None, annual_roe_pct=[], reason='未取得歷史ROE，區間可比性待確認')
    status(s, 'valuation_supported', 'limited')
    s['report_markdown'] = '規則版本 1.14.0\n未核對完整報表；ROE未取得；自由現金流已清空；P/B不使用。'
    return s


def main():
    metadata = (ROOT/'SKILL.md').read_text()
    for key, value in [('version',g.SKILL_VERSION),('rule-version',g.RULE_VERSION),('validator-version',g.VALIDATOR_VERSION)]:
        check(('  '+key+': '+json.dumps(value)) in metadata, 'metadata and validator release profile agree')
    etf = (ROOT/'references/etf.md').read_text()
    check('規則版本 1.3.1' not in etf and '規則版本 1.4.4' not in etf and '規則版本 1.14.0' in etf, 'ETF rule headers consistent')
    out = run(deepcopy(BASE))
    check(out['overall']['confidence'] == 'high', 'stable full evidence can remain high')
    wrong = deepcopy(out); wrong['report_markdown'] = wrong['report_markdown'].replace('信心：高', '信心：低'); wrong['report_sha256'] = g.report_hash(wrong)
    check(not g.validate(wrong)['valid'], 'reject report confidence mismatch even with correct hash')
    wrong = deepcopy(out); wrong['report_markdown'] = wrong['report_markdown'].replace('暫定：否', '暫定：是'); wrong['report_sha256'] = g.report_hash(wrong)
    check(not g.validate(wrong)['valid'], 'reject report provisional mismatch')
    wrong = deepcopy(out); wrong['report_markdown'] = wrong['report_markdown'].replace('整體投資訊號：🟡', '整體投資訊號：🟢'); wrong['report_sha256'] = g.report_hash(wrong)
    check(not g.validate(wrong)['valid'], 'reject report signal mismatch')
    check(out['report_sha256'] == hashlib.sha256(out['report_markdown'].encode()).hexdigest(), 'hash exact UTF-8 final report')
    clean = waiver()
    out = run(clean)
    check(not g.statement_uses(clean) and out['overall']['confidence'] == 'low', 'negative declarations do not fabricate dependence or high confidence')
    for text in ['ROE為18%，自由現金流充足。', 'ＲＯＥ為１８％。', 'Free cash flow is strong.', '淨值為50元。', '流動比率為2倍。', '現金轉換率改善。', 'ROE未取得但自由現金流充足。']:
        s = deepcopy(clean); s['report_markdown'] += '\n' + text
        reject(s, 'report_markdown')
    for text in ['ROE：未取得', 'FCF unavailable', '淨值已清空', '不使用自由現金流', 'ROE N/A', 'R2：ROE未知，已清空FCF', 'R2相關的ROE與自由現金流已清空']:
        s = deepcopy(clean); s['report_markdown'] += '\n' + text
        run(s)
    s = deepcopy(clean); item(s, 'end_demand')['reason'] = '自由現金流充足，支持需求'
    reject(s, 'end_demand.reason')
    s = deepcopy(clean); s['valuation']['scenarios'][0]['assumptions']['note'] = 'ROE為18%'
    reject(s, 'assumptions.note')
    s = deepcopy(clean); s['eligibility']['financials_dependent'] = True
    s['report_markdown'] += '\nROE為18%'
    reject(s, 'report_markdown')
    s = deepcopy(clean); s['valuation']['scenarios'][0]['assumptions']['book_value_per_share'] = 50
    reject(s, 'book_value_per_share')
    s = deepcopy(clean); s['valuation']['scenarios'][0]['assumptions']['nested'] = {'book_value_per_share':50}
    reject(s, 'nested.book_value_per_share')
    s = deepcopy(clean); s['risks'].append('負債僅10億元，可控')
    reject(s, 'risks')
    s = deepcopy(clean); s['events'][0]['description'] = '現金流量改善'
    reject(s, 'events')
    for n, expected, provisional in [(1, 'medium', False), (2, 'low', True), (3, 'low', True)]:
        s = deepcopy(BASE)
        for key in ['quote_verified', 'valuation_supported', 'quote_is_current'][:n]: status(s, key, 'limited')
        out = run(s)
        check(out['overall']['confidence'] == expected and out['overall']['provisional'] == provisional, 'R4 exact confidence/provisional')
    s = deepcopy(BASE); status(s, 'valuation_supported', 'fail')
    check(run(s)['overall']['signal'] == 'unknown', 'fail blocks conclusion even with scored valuation')
    s = deepcopy(BASE); status(s, 'quote_verified', 'fail'); status(s, 'quote_is_current', 'fail')
    check(run(s)['overall']['signal'] == 'unknown', 'quote failure blocks conclusion')
    s = deepcopy(BASE); s['eligibility']['quote_verified'] = True
    reject(s, 'quote_verified')
    s = deepcopy(BASE); status(s, 'financials_verified', 'limited')
    reject(s, 'allowed shape')
    s = deepcopy(BASE); s['eligibility']['valuation_supported'] = 'limited'
    reject(s, 'must match validation')
    s = deepcopy(BASE); s['valuation']['guardrails']['r2']['status'] = 'unconfirmed'
    reject(s, 'requires limited')
    status(s, 'valuation_supported', 'limited'); run(s)
    s = deepcopy(BASE); s['analysis_scope'] = 'historical'; status(s, 'quote_is_current', 'limited')
    check(run(s)['overall']['confidence'] == 'high', 'irrelevant current-quote qualification does not penalize historical analysis')
    s = deepcopy(BASE)
    for group in s['scores'].values():
        for x in group['items']: x['score'] = 2
    item(s, 'financial_event_buffer')['score'] = 1
    item(s, 'operations_concentration')['reason'] = '有限制，仍有具體營運緩衝'
    out = run(s)
    check(out['overall']['signal'] == 'green' and out['overall']['confidence'] == 'medium', 'R6 fragile green has medium confidence')
    check(out['sensitivity']['fragile'] and any(x['check'] == 'operations_concentration' and x['signal'] == 'yellow' for x in out['sensitivity']['cases']), 'R6 records counterfactual flip')
    status(s, 'quote_verified', 'limited'); status(s, 'valuation_supported', 'limited')
    check(run(s)['overall']['confidence'] == 'low', 'R6 never raises R4 low confidence')
    out['sensitivity']['fragile'] = False
    check(not g.validate(out)['valid'], 'reject forged sensitivity')
    s = deepcopy(BASE); item(s, 'model_upside')['score'] = None
    out = run(s)
    check(not any(x['check'] == 'model_upside' for x in out['sensitivity']['cases']), 'R6 never fills null')
    s = deepcopy(BASE); s['valuation']['guardrails']['r2']['status'] = 'unconfirmed'; status(s, 'valuation_supported', 'limited')
    out = run(s)
    check(not any(x['check'] == 'model_upside' and x['to_score'] > 1 for x in out['sensitivity']['cases']), 'R6 obeys R2 cap')
    s = deepcopy(BASE); s['major_risk'].update(confirmed=True, source_urls=[s['sources'][0]['url']], reason='合成違約事件')
    out = run(s)
    check(out['overall']['signal'] == 'major_risk' and out['overall']['confidence'] is None, 'major risk priority retained')
    out = run(deepcopy(BASE)); out['report_markdown'] += '\n補充文字'
    check(not g.validate(out)['valid'], 'changed final report must revalidate hash')
    run(out)
    for key in ['skill_version', 'rule_version', 'validator_version', 'report_sha256', 'report_markdown', 'sensitivity']:
        s = deepcopy(BASE); del s[key]; reject(s, 'required')
    s = deepcopy(BASE); s['rule_version'] = '1.5.1'; reject(s, 'unsupported release profile')
    s = deepcopy(BASE); s['report_markdown'] = '規則版本 1.4.4'; reject(s, 'inconsistent')
    previous = run(deepcopy(BASE)); current = deepcopy(previous); current['analysis_at'] = '2026-10-09T18:00:00+08:00'
    current = run(current)
    check(g.comparison_status(current, previous)['comparable'], 'same supported profile and earlier same security comparable')
    changed = deepcopy(previous); changed['rule_version'] = '1.4.4'
    check(not g.comparison_status(current, changed)['comparable'], 'different rule family not comparable')
    changed = deepcopy(previous); changed['model_version'] = '1.2'
    check(not g.comparison_status(current, changed)['comparable'], 'different model not comparable')
    changed = deepcopy(previous); del changed['rule_version']
    check('unknown' in ' '.join(g.comparison_status(current, changed)['reasons']), 'unknown historic rule is not backfilled')
    changed = deepcopy(previous); changed['security']['instrument'] = 'adr'
    check(not g.comparison_status(current, changed)['comparable'], 'ADR/ordinary comparison blocked')
    s = deepcopy(BASE); s['previous_report_reference'] = {'reference':'attachment:older.json','analysis_at':'2026-10-07T18:00:00+08:00','schema_version':'1.4','model_version':'1.2','rule_version':None,'skill_version':None,'validator_version':None}
    check(run(s)['previous_report_reference']['rule_version'] is None, 'preserve unknown provenance')
    del s['previous_report_reference']['rule_version']; reject(s, 'rule_version: required')
    archive = json.loads((ROOT / 'tests/snapshot.model-1.2.json').read_text())
    archived = run(archive)
    check('rule_version' not in archived and 'sensitivity' not in archived, 'legacy fields not backfilled')
    check(not g.comparison_status(current, archived)['comparable'], 'old archive only permits listing')
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); input_file = d/'input.json'; input_file.write_text(json.dumps(BASE))
        report = d/'report.md'; report.write_text(BASE['report_markdown'])
        output = subprocess.run([sys.executable, str(ROOT/'scripts/snapshot_guard.py'), str(input_file), '--report', str(report), '--derive'], capture_output=True, text=True)
        check(output.returncode == 0 and g.validate(json.loads(output.stdout))['valid'], 'CLI binds final report and derives')
        output = subprocess.run([sys.executable, str(ROOT/'scripts/snapshot_guard.py'), str(input_file), '--sensitivity'], capture_output=True, text=True)
        check(output.returncode == 0 and 'sensitivity' in json.loads(output.stdout), 'CLI sensitivity')
        input_file.write_text(json.dumps(current)); prior = d/'previous.json'; prior.write_text(json.dumps(previous))
        output = subprocess.run([sys.executable, str(ROOT/'scripts/snapshot_guard.py'), str(input_file), '--compare', str(prior)], capture_output=True, text=True)
        check(output.returncode == 0 and json.loads(output.stdout)['comparison']['comparable'], 'CLI compares validated snapshots')
    print(json.dumps({'passed':True,'checks':count,'scope':'direct production validator calls, synthetic only'},ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'passed':False,'checks':count,'error':str(error)},ensure_ascii=False))
        sys.exit(2)
