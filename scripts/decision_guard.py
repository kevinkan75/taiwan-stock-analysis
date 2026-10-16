#!/usr/bin/env python3
"""Validate numeric gates, research binding and ordered decision rules offline.

--research is required. Current records derive gates 2, 6 and 7 from supplied
inputs; archived records retain their original rules. Research sources are
revalidated when supported. Source facts and qualitative gates remain manual.
Never fetches data, rewrites research scores, or evaluates prose as code.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
import report_checks

import snapshot_guard as stock
import etf_guard as etf
import decision_numeric as numeric
from rules_core import (
    SKILL_VERSION, RULE_VERSION, DECISION_MODEL_VERSION, DECISION_VALIDATOR_VERSION,
    CORE_GATES, ENTRY_GREEN_GATES, ENTRY_OBSERVED_GATES, SIGNAL_LABELS, ACTION_LABELS,
    ETF_SUPPORTED_SUBTYPES, ETF_MODEL_VERSION, DECISION_PROFILES, timestamp, rule_headers,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / 'assets/decision.schema.json'
GATE_NAMES = ('研究基礎', '估值紀律', '論點可驗證', '市場環境', '事件風險', '價格位置', '預期反映', '退場條件')


def classify(signals, quote_ready):
    """Single ordered implementation of decision.md's four conclusion clauses."""
    if set(signals) != set(range(1, 9)) or any(x not in ('green', 'yellow', 'red', 'unknown') for x in signals.values()):
        raise ValueError('exactly eight canonical gate signals required')
    if not isinstance(quote_ready, bool):
        raise ValueError('quote_ready must be boolean')
    missing = [n for n in range(1, 9) if signals[n] == 'unknown']
    blockers = [n for n in range(1, 9) if signals[n] == 'red'
                or (n in ENTRY_GREEN_GATES and signals[n] != 'green')
                or (n in ENTRY_OBSERVED_GATES and signals[n] not in ('green', 'yellow'))]
    abandon = []
    if signals[1] == 'red': abandon.append('research_red')
    if signals[2] == signals[3] == 'red': abandon.append('valuation_and_thesis_red')
    if signals[8] == 'red': abandon.append('exit_thesis_unverifiable')
    wait = []
    if not quote_ready: wait.append('quote_not_ready')
    wait += ['core_gate_%d_missing' % n for n in CORE_GATES if signals[n] == 'unknown']
    if signals[5] == 'red': wait.append('near_event_red')
    if signals[5] == 'yellow' and signals[4] == 'red': wait.append('event_and_market_risk')
    if signals[2] == signals[7] == 'red': wait.append('valuation_and_expectations_red')
    if sum(x == 'red' for x in signals.values()) >= 3: wait.append('three_or_more_red')
    if abandon:
        action, clause, codes = 'abandon', 1, abandon
    elif wait:
        action, clause, codes = 'wait', 2, wait
    elif (all(signals[n] == 'green' for n in ENTRY_GREEN_GATES)
          and all(signals[n] in ('green', 'yellow') for n in ENTRY_OBSERVED_GATES)):
        action, clause, codes = 'enter', 3, ['all_entry_conditions']
    else:
        action, clause, codes = 'staged', 4, ['core_checks_passed_conditional_batches']
    first = ['gate_%d' % n for n in (4, 7) if signals[n] == 'unknown'] if action == 'staged' else []
    if action == 'staged' and signals[6] == 'red': first.append('gate_6')
    return {'action': action, 'clause': clause, 'trigger_codes': codes,
            'missing_gates': missing, 'blocking_direct_entry': blockers, 'first_batch_requirements': first}


def research_gate(research):
    overall = research['overall']
    signal = overall['signal']
    if signal in ('red', 'major_risk'): return 'red'
    if signal == 'unknown': return 'unknown'
    return 'yellow' if overall.get('provisional') else signal


def validate_research(research):
    if not isinstance(research, dict):
        return ['research must be an object'], 'unknown'
    if research.get('model_version') in ('etf-1.1', ETF_MODEL_VERSION):
        result = etf.validate(research)
        errors = ['research: ' + x for x in result['errors']]
        if research.get('validated') is not True: errors.append('research: finalized ETF required')
        return errors, 'etf_snapshot'
    if research.get('model_version') == 'etf-1.0':
        # This deliberately does not claim ETF scores or evidence are validated.
        errors = []
        for key in ('security', 'overall', 'analysis_at', 'data_cutoff_at', 'quote_at', 'eligibility'):
            if key not in research: errors.append('manual ETF source: missing ' + key)
        if errors: return errors, 'manual_etf'
        if research.get('validated') is not False:
            errors.append('manual ETF source: validated must be false')
        if research.get('subtype') not in ETF_SUPPORTED_SUBTYPES:
            errors.append('manual ETF source: supported, manually verified subtype required')
        if not isinstance(research['security'], dict) or research['security'].get('instrument') != 'etf':
            errors.append('manual ETF source: ETF security envelope required')
            return errors, 'manual_etf'
        overall = research['overall']
        if not isinstance(overall, dict) or overall.get('signal') not in SIGNAL_LABELS or not isinstance(overall.get('provisional'), bool):
            errors.append('manual ETF source: explicit signal and provisional required')
        elif (any(key not in overall for key in ('score', 'confidence'))
              or (overall['score'] is not None and (not stock.finite(overall['score']) or not 0 <= overall['score'] <= 100))
              or overall['confidence'] not in ('high', 'medium', 'low', None)):
            errors.append('manual ETF source: declared score/confidence required for report binding')
        if not isinstance(research['eligibility'], dict):
            errors.append('manual ETF source: qualification envelope required')
        else:
            for key in ('quote_verified', 'quote_is_current'):
                if research['eligibility'].get(key) not in ('pass', 'limited', 'fail'):
                    errors.append('manual ETF source: explicit ' + key + ' status required')
            if research['eligibility'].get('quote_verified') in ('pass', 'limited'):
                metrics = research.get('metrics')
                price = metrics.get('price') if isinstance(metrics, dict) else None
                if (not isinstance(price, dict) or not stock.finite(price.get('value')) or price['value'] <= 0
                        or price.get('currency') != research['security'].get('currency')):
                    errors.append('manual ETF source: verified quote requires positive matching price')
        try:
            analysis, cutoff = timestamp(research['analysis_at']), timestamp(research['data_cutoff_at'])
            if cutoff > analysis: errors.append('manual ETF source: cutoff after analysis')
            if research['quote_at'] is not None and timestamp(research['quote_at']) > cutoff:
                errors.append('manual ETF source: quote after cutoff')
        except (ValueError, TypeError):
            errors.append('manual ETF source: invalid timestamp')
        return errors, 'manual_etf'
    result = stock.validate(research)
    return ['research: ' + x for x in result['errors']], 'stock_snapshot'


def qualified(research, key):
    value = research['eligibility'].get(key)
    return value is True or value in ('pass', 'limited')


def report_errors(s, result, research):
    errors = stock.summary_errors(s)
    headers = rule_headers(s['report_markdown'], '決策規則版本')
    if headers != [s['rule_version']]: errors.append('report: exactly one matching decision rule header required')
    research_headers = rule_headers(s['report_markdown'])
    source_version = research.get('rule_version')
    if source_version is None:
        if research_headers or '研究規則版本：未知' not in s['report_markdown'].splitlines():
            errors.append('report: unknown research rule version must remain explicit, not inferred')
    elif not research_headers or any(x != source_version for x in research_headers):
        errors.append('report: research rule version disagrees with source')
    lines = [x for x in s['report_markdown'].splitlines() if re.match(r'^\s*行動結論\s*[:：]', x)]
    expected = '行動結論：%s；命中條款：%d' % (ACTION_LABELS[result['action']], result['clause'])
    if len(lines) != 1 or lines[0].strip() != expected:
        errors.append('report: action/clause line disagrees with derived conclusion')
    scope_line = numeric.SCOPE_LINE if s['model_version']==DECISION_MODEL_VERSION else '決策驗證範圍：結論、條款及格式；八關證據仍人工核對。'
    if scope_line not in s['report_markdown'].splitlines():
        errors.append('report: explicit decision validation scope required')
    if s['research_reference']['verification'] == 'manual_etf' and 'ETF研究評分未經程式驗證。' not in s['report_markdown'].splitlines():
        errors.append('report: manual ETF research scope required')
    if s['research_reference']['verification'] == 'etf_snapshot' and etf.SCOPE_LINE not in s['report_markdown'].splitlines():
        errors.append('report: ETF mechanical validation scope required')
    rows = []
    for line in s['report_markdown'].splitlines():
        match = re.match(r'^\s*\|\s*([1-8])\s*\|[^|]*\|\s*([🟢🟡🔴⚪])\s*\|', line)
        if match: rows.append((int(match[1]), match[2]))
    if rows != [(x['number'], SIGNAL_LABELS[x['signal']]) for x in s['gates']]:
        errors.append('report: eight gate table rows must match canonical order and signals')
    bound_overall = dict(research['overall'], provisional=research['overall'].get('provisional', False),
                         confidence=research['overall'].get('confidence'))
    errors += stock.report_result_errors(s, {'derived': {'overall': bound_overall}})
    return errors


def validate(s, research, research_sha256, derive_only=False):
    schema_file=ROOT/'assets/decision.schema-1.0.json' if isinstance(s,dict) and s.get('model_version')=='decision-1.0' else SCHEMA
    schema = json.loads(schema_file.read_text(encoding='utf-8'))
    stock.audit_keywords(schema)
    errors = stock.schema_errors(s, schema, schema)
    if errors: return {'valid': False, 'scope': 'structure', 'errors': errors, 'derived': None}
    if (s['skill_version'], s['rule_version'], s['validator_version']) not in DECISION_PROFILES:
        errors.append('unsupported decision release profile')
    current_profile=(SKILL_VERSION,RULE_VERSION,DECISION_VALIDATOR_VERSION)
    is_current=(s['skill_version'],s['rule_version'],s['validator_version']) in {current_profile, ('1.13.0','1.13.0','2.1.0'), ('1.12.0','1.12.0','2.1.0'), ('1.11.0','1.11.0','2.1.0'), ('1.10.0','1.10.0','2.0.0')}
    if s['model_version'] != (DECISION_MODEL_VERSION if is_current else 'decision-1.0'):
        errors.append('decision model and release profile disagree')
    rerrors, verification = validate_research(research)
    if rerrors: return {'valid': False, 'scope': 'research_reference', 'errors': errors + rerrors, 'derived': None}
    reference = s['research_reference']
    if reference['sha256'] != research_sha256: errors.append('research_reference: source file hash mismatch')
    if reference['verification'] != verification: errors.append('research_reference: verification scope mismatch')
    if verification == 'etf_snapshot' and (s['validator_version'] not in ('1.1.0','2.0.0',DECISION_VALIDATOR_VERSION)
            or (research['model_version']==ETF_MODEL_VERSION and not is_current)):
        errors.append('research_reference: ETF snapshot needs matching decision validator')
    for key in ('model_version', 'rule_version', 'analysis_at', 'data_cutoff_at'):
        if reference[key] != research.get(key): errors.append('research_reference.' + key + ': source mismatch')
    if s['security'] != research['security']: errors.append('security: decision and research must match exactly')
    cutoff, analysis = timestamp(s['data_cutoff_at']), timestamp(s['analysis_at'])
    if cutoff > analysis: errors.append('data cutoff after analysis')
    if timestamp(research['data_cutoff_at']) > cutoff or timestamp(research['analysis_at']) > analysis:
        errors.append('research_reference: source is later than decision')
    known = {x['url'] for x in s['sources']}
    if len(known) != len(s['sources']): errors.append('sources: duplicate URLs')
    for source in s['sources']:
        if timestamp(source['retrieved_at']) > analysis: errors.append('source retrieved after analysis')
        published = source['published_at']
        if published and (timestamp(published) > cutoff if 'T' in published else published > cutoff.date().isoformat()):
            errors.append('source published after cutoff')
    def urls(values, name, required=False):
        if required and not values: errors.append(name + ': evidence URLs required')
        if any(x not in known for x in values): errors.append(name + ': source missing from catalog')
    if [x['number'] for x in s['gates']] != list(range(1, 9)):
        errors.append('gates: exactly eight unique gates in canonical order required')
    for gate in s['gates']:
        urls(gate['source_urls'], 'gate_%d' % gate['number'], gate['signal'] != 'unknown')
    if s['gates'][0]['signal'] != research_gate(research): errors.append('gate_1: disagrees with referenced research signal/provisional state')
    context = s['quote_context']
    if timestamp(context['verified_at']) > analysis: errors.append('quote context verified after analysis')
    latest = timestamp(context['latest_completed_session_at']) if context['latest_completed_session_at'] else None
    if latest and latest > cutoff: errors.append('latest completed session after cutoff')
    if latest and latest > timestamp(context['verified_at']): errors.append('latest session after quote-context verification')
    quote_at = timestamp(research['quote_at']) if research['quote_at'] else None
    if quote_at and quote_at > cutoff: errors.append('research quote after decision cutoff')
    urls(context['source_urls'], 'quote_context', latest is not None)
    quote_ready = (qualified(research, 'quote_verified') and qualified(research, 'quote_is_current')
                   and quote_at is not None and latest is not None and quote_at >= latest)
    # A previous session may support a waiting/abandon record, never a new entry.
    # Compare the supplied session in the quote's timezone, not UTC date labels.
    research_refresh_required = bool(quote_at and latest and quote_at < latest
                                    and quote_at.date() < latest.astimezone(quote_at.tzinfo).date())
    if verification == 'stock_snapshot' and not stock.qualified(research, 'financials_verified'):
        claims = stock.text_financial_uses(s['report_markdown'], 'report')
        claims += stock.text_financial_uses(s['gates'], 'gates')
        claims += stock.text_financial_uses(s['conditions'], 'conditions')
        claims += stock.text_financial_uses(context['reason'], 'quote_context.reason')
        errors += [x + ': affirmative financial claim without verified statements' for x in claims]
    if errors: return {'valid': False, 'scope': 'evidence_and_binding', 'errors': errors, 'derived': None}
    signals = {x['number']: x['signal'] for x in s['gates']}
    numeric_checks=None
    if is_current:
        nerrors,numeric_checks=numeric.evaluate(s,research)
        if nerrors:return {'valid':False,'scope':'numeric_inputs_and_binding','errors':nerrors,'derived':None}
        for n in (2,6,7):
            expected=numeric_checks['gates']['gate_%d'%n]['signal']
            if not derive_only and signals[n]!=expected:errors.append('gate_%d: signal differs from numeric derivation'%n)
            signals[n]=expected
        if not derive_only and s['numeric_checks']!=numeric_checks:errors.append('numeric_checks: derived mismatch')
    result = classify(signals, bool(quote_ready))
    if not derive_only and s['rule_version'] in report_checks.PROFILE_RULES:
        errors += report_checks.report_errors(s['report_markdown'], result['action'], research['overall']['confidence'])
    conditions = s['conditions']
    if not derive_only and result['action'] == 'wait':
        if not conditions['waiting_for']: errors.append('waiting_for: at least one concrete follow-up required')
        relevant = {'quote'} if not quote_ready else set()
        if research_refresh_required: relevant.add('research')
        relevant |= {'gate_%d' % n for n in CORE_GATES if signals[n] == 'unknown'}
        relevant |= {'gate_%d' % n for n in range(1, 9) if signals[n] == 'red'}
        if signals[5] == 'yellow': relevant.add('gate_5')
        if not any(x['target'] in relevant for x in conditions['waiting_for']): errors.append('waiting_for: no target matches blocking condition')
    if not derive_only and result['action'] == 'staged':
        if len(conditions['batches']) < 2: errors.append('batches: staged plan requires at least two conditional batches')
        elif not set(result['first_batch_requirements']) <= set(conditions['batches'][0]['requires_clearance']):
            errors.append('first batch: missing required gate clearance')
    elif not derive_only and conditions['batches']:
        errors.append('batches: permitted only for staged action')
    if not derive_only and any(x['description'].strip() in ('再觀察', '待確認', '等看看') for x in conditions['waiting_for']):
        errors.append('waiting_for: placeholder is not a concrete follow-up')
    if not derive_only:
        if s['conclusion'] != result: errors.append('conclusion: does not match ordered decision rules')
        if s['report_sha256'] != hashlib.sha256(s['report_markdown'].encode('utf-8')).hexdigest(): errors.append('report: final text hash mismatch')
        errors += report_errors(s, result, research)
    scope=('decision_numeric_gates_and_conclusion'+('_draft' if derive_only else '')) if is_current else ('decision_conclusion_draft' if derive_only else 'decision_conclusion_only')
    return {'valid': not errors, 'scope': scope, 'errors': errors, 'derived': result,
            'numeric_checks':numeric_checks,
            'research_verification': verification, 'quote_ready': bool(quote_ready),
            'research_refresh_required': research_refresh_required,
            'limitation': 'External numeric evidence, calendars, thesis and qualitative gates remain manually verified.'}


def derived_record(s, result):
    out = deepcopy(s)
    out['conclusion'] = result['derived']
    if result.get('numeric_checks') is not None:
        out['numeric_checks']=result['numeric_checks']
        for n in (2,6,7):out['gates'][n-1]['signal']=result['numeric_checks']['gates']['gate_%d'%n]['signal']
    out['report_sha256'] = hashlib.sha256(out['report_markdown'].encode('utf-8')).hexdigest()
    return out


def report_block(s, conclusion):
    """Render only the checked result/table; the author supplies evidence prose."""
    lines = ['決策規則版本 ' + s['rule_version'],
             '行動結論：%s；命中條款：%d' % (ACTION_LABELS[conclusion['action']], conclusion['clause']),
             '', '| 關卡 | 名稱 | 燈號 | 依據 |', '| --- | --- | --- | --- |']
    for gate in s['gates']:
        reason = gate['reason'].replace('|', '\\|').replace('\n', ' ')
        lines.append('| %d | %s | %s | %s |' % (gate['number'], GATE_NAMES[gate['number'] - 1], SIGNAL_LABELS[gate['signal']], reason))
    lines.append(numeric.SCOPE_LINE if s['model_version']==DECISION_MODEL_VERSION else '決策驗證範圍：結論、條款及格式；八關證據仍人工核對。')
    if s['research_reference']['verification'] == 'manual_etf': lines.append('ETF研究評分未經程式驗證。')
    if s['research_reference']['verification'] == 'etf_snapshot': lines.append(etf.SCOPE_LINE)
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--research', required=True, help='actual referenced research JSON; read only')
    parser.add_argument('--report', help='UTF-8 final decision report')
    parser.add_argument('--derive', action='store_true')
    parser.add_argument('--render', action='store_true', help='derive a checked action/table fragment; not final report validation')
    args = parser.parse_args()
    try:
        with open(args.input, encoding='utf-8') as f: s = stock.load_json(f)
        raw = Path(args.research).read_bytes()
        with open(args.research, encoding='utf-8') as f: research = stock.load_json(f)
        if args.report: s['report_markdown'] = Path(args.report).read_text(encoding='utf-8')
        if args.render and args.derive: raise ValueError('--render and --derive are mutually exclusive')
        result = validate(s, research, hashlib.sha256(raw).hexdigest(), args.derive or args.render)
        output = derived_record(s, result) if args.derive and result['valid'] else result
        if args.render and result['valid']:
            output = dict(result, report_block=report_block(derived_record(s,result), result['derived']))
        print(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2))
        return 0 if result['valid'] else 2
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as error:
        print(json.dumps({'valid': False, 'scope': 'input', 'errors': [str(error)]}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
