#!/usr/bin/env python3
"""Validate the bundled snapshot schema and derive model-1.0/1.1/1.2/1.3 signals, offline.

Only the keywords used by the bundled schema are implemented. This does not
verify external facts, causal arguments, forecasts, or suitability to investors.
"""
import argparse
from copy import deepcopy
from datetime import date, datetime
from fractions import Fraction
import json
import hashlib
import unicodedata
import math
from pathlib import Path
import re
import sys
import report_checks

ROOT = Path(__file__).resolve().parents[1]
from rules_core import (
    DIMENSIONS, VERSION_PAIRS, TECH_MIN_BARS, SKILL_VERSION, RULE_VERSION, VALIDATOR_VERSION,
    RELEASE_PROFILE, ARITHMETIC_PROFILE, ARCHIVED_PROFILES, ARITHMETIC_PROFILES, SUMMARY_PROFILES,
    QUALIFIERS, SUMMARY_LABELS, finite, timestamp, equal, close, rounded, light,
    dimension_result, weighted_total, research_signal, valuation_threshold_score, rule_headers,
)

KEYWORDS = {
    '$schema', '$defs', '$ref', 'title', 'description', 'type', 'properties',
    'required', 'additionalProperties', 'items', 'minItems', 'maxItems',
    'enum', 'const', 'minimum', 'maximum', 'exclusiveMinimum', 'minLength',
    'pattern', 'format', 'anyOf',
}


def strict_consistency(snapshot):
    return snapshot['model_version'] == '1.3' and tuple(snapshot.get(k) for k in
        ('skill_version', 'rule_version', 'validator_version')) in ARITHMETIC_PROFILES


def summary_errors(snapshot):
    """Check only labelled, ordered, nonempty summary lines, never their factual meaning."""
    lines = []
    pattern = r'^\s*(?:[-*]\s+)?(' + '|'.join(SUMMARY_LABELS) + r')\s*[:：]\s*(.*?)\s*$'
    for line in snapshot['report_markdown'].splitlines():
        match = re.match(pattern, line.replace('**', ''))
        if match:
            lines.append(match.groups())
    if [x[0] for x in lines] != list(SUMMARY_LABELS):
        return ['report_markdown: four summary labels must appear once in the specified order']
    return ['report_markdown: summary ' + label + ' must be nonempty'
            for label, value in lines if not value.strip() or value.strip() in ('-', '—', '…', '...')]


def calculation_close(a, b):
    # Inputs retain their source precision; this tolerance is floating-point noise,
    # not permission to round a model price or manufacture missing precision.
    return finite(a) and finite(b) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def consistency_errors(s, cutoff):
    """1.6.0 arithmetic/input links and event-time checks; never evaluate formula text."""
    errors = []
    metrics, valuation = s['metrics'], s['valuation']
    price = metrics['price']['value']

    def numeric_inputs(inputs, names, context, positive=()):
        ok = isinstance(inputs, dict)
        for name in names:
            value = inputs.get(name) if isinstance(inputs, dict) else None
            if not finite(value) or (name in positive and value <= 0):
                errors.append(context + ': finite%s input %s required' %
                              (' positive' if name in positive else '', name))
                ok = False
        return ok

    # Every direct reference to another metric must retain that metric's value.
    # Unknown input names remain method-specific, not invented metric links.
    for key, metric in metrics.items():
        inputs = metric['inputs']
        if metric['value_status'] == 'calculated' and isinstance(inputs, dict):
            for name, value in inputs.items():
                if name in metrics and not calculation_close(value, metrics[name]['value']):
                    errors.append('metrics.%s.inputs.%s: disagrees with referenced metric' % (key, name))
    pe = metrics['pe_ttm']
    if pe['value_status'] == 'calculated':
        inputs = pe['inputs']
        if numeric_inputs(inputs, ('price', 'eps_ttm'), 'metrics.pe_ttm', ('price', 'eps_ttm')):
            if not calculation_close(pe['value'], inputs['price'] / inputs['eps_ttm']):
                errors.append('metrics.pe_ttm: value disagrees with declared inputs')

    recipes = {
        'roe_ttm': (('net_income_common', 'equity_begin_common', 'equity_end_common'),
                    ('equity_begin_common', 'equity_end_common'),
                    lambda i: i['net_income_common'] / ((i['equity_begin_common'] + i['equity_end_common']) / 2) * 100),
        'fcf_ttm': (('cfo_ttm', 'cash_capex_ttm'), (), lambda i: i['cfo_ttm'] - i['cash_capex_ttm']),
        'revenue_growth_q2': (('current', 'previous'), ('previous',), lambda i: (i['current'] / i['previous'] - 1) * 100),
        'eps_growth_q2': (('current', 'previous'), ('previous',), lambda i: (i['current'] / i['previous'] - 1) * 100),
        'gross_margin_q2': (('gross_profit', 'revenue'), ('revenue',), lambda i: i['gross_profit'] / i['revenue'] * 100),
        'cash_yield': (('cash_dividend_12m', 'price'), ('price',), lambda i: i['cash_dividend_12m'] / i['price'] * 100),
    }
    for key, (names, positive, calculate) in recipes.items():
        metric = metrics[key]
        if metric['value_status'] != 'calculated':
            continue
        inputs = metric['inputs']
        if numeric_inputs(inputs, names, 'metrics.' + key, positive):
            if key == 'fcf_ttm' and inputs['cash_capex_ttm'] < 0:
                errors.append('metrics.fcf_ttm: cash_capex_ttm must be a nonnegative cash outflow')
            if key == 'cash_yield' and inputs['cash_dividend_12m'] < 0:
                errors.append('metrics.cash_yield: paid cash dividends must be nonnegative')
            if not calculation_close(metric['value'], calculate(inputs)):
                errors.append('metrics.' + key + ': value disagrees with declared formula inputs')
    market_cap = metrics['market_cap']
    if market_cap['value_status'] == 'calculated':
        inputs = market_cap['inputs']
        if numeric_inputs(inputs, ('price', 'shares', 'adr_ratio'), 'metrics.market_cap', ('price', 'shares', 'adr_ratio')):
            if s['security']['instrument'] == 'ordinary' and inputs['adr_ratio'] != 1:
                errors.append('metrics.market_cap: ordinary shares require adr_ratio=1')
            if market_cap['currency'] != metrics['price']['currency']:
                errors.append('metrics.market_cap: currency must match price')
            if not calculation_close(market_cap['value'], inputs['price'] / inputs['adr_ratio'] * inputs['shares']):
                errors.append('metrics.market_cap: value disagrees with price / adr_ratio * shares')

    primary = valuation['primary_metric']
    # Detect an incorrectly relabelled simple method as well as checking primary_metric.
    method = unicodedata.normalize('NFKC', valuation['method'] or '')
    if re.search(r'P\s*/\s*E', method, re.I) and primary != 'pe':
        errors.append('valuation.primary_metric: disagrees with P/E method')
    if re.search(r'P\s*/\s*B', method, re.I) and primary != 'pb':
        errors.append('valuation.primary_metric: disagrees with P/B method')
    for pattern, expected in ((r'EV\s*/\s*Sales', 'ev_sales'), (r'EV\s*/\s*EBITDA', 'ev_ebitda')):
        if re.search(pattern, method, re.I) and primary != expected:
            errors.append('valuation.primary_metric: disagrees with ' + expected + ' method')
    for scenario in valuation['scenarios']:
        if scenario['model_price'] is None:
            continue
        context = 'valuation.' + scenario['label']
        inputs = scenario['assumptions']
        for field in ('currency', 'instrument'):
            if inputs.get(field) != s['security'][field]:
                errors.append(context + ': assumptions.' + field + ' must match security')
        if primary in ('pe', 'pb'):
            basis = 'eps' if primary == 'pe' else 'book_value_per_share'
            if numeric_inputs(inputs, (basis, 'multiple'), context, (basis, 'multiple')):
                expected = inputs[basis] * inputs['multiple']
                if not calculation_close(scenario['model_price'], expected):
                    errors.append(context + ': model_price must equal %s * multiple' % basis)
            # The optional legacy P/E alias may not disagree with the canonical field.
            if primary == 'pe' and 'pe' in inputs and not calculation_close(inputs['pe'], inputs.get('multiple')):
                errors.append(context + ': pe alias disagrees with multiple')
        elif primary in ('ev_sales', 'ev_ebitda'):
            basis = 'revenue' if primary == 'ev_sales' else 'ebitda'
            names = (basis, 'multiple', 'net_debt', 'shares', 'adr_ratio')
            if numeric_inputs(inputs, names, context, (basis, 'multiple', 'shares', 'adr_ratio')):
                if s['security']['instrument'] == 'ordinary' and inputs['adr_ratio'] != 1:
                    errors.append(context + ': ordinary shares require adr_ratio=1')
                expected = ((inputs[basis] * inputs['multiple'] - inputs['net_debt'])
                            / inputs['shares'] * inputs['adr_ratio'])
                if expected <= 0 or not calculation_close(scenario['model_price'], expected):
                    errors.append(context + ': model_price disagrees with EV-to-equity conversion')

    band = valuation.get('band')
    if band:
        key = band.get('current_metric')
        allowed = ('pe_ttm', 'pe_forward') if band['metric'] == 'pe' else ('pb_current',)
        if key not in allowed or key not in metrics or metrics[key]['value'] is None:
            errors.append('valuation.band: current_metric must reference a known matching PE/PB metric')
        elif not calculation_close(band['current'], metrics[key]['value']):
            errors.append('valuation.band.current: disagrees with current_metric')
        elif metrics[key]['value_status'] == 'calculated':
            value = metrics[key]
            inputs = value['inputs']
            basis = {'pe_ttm': 'eps_ttm', 'pe_forward': 'eps_forward',
                     'pb_current': 'book_value_per_share'}[key]
            if numeric_inputs(inputs, ('price', basis), 'metrics.' + key, ('price', basis)):
                if not calculation_close(inputs['price'], price):
                    errors.append('metrics.' + key + ': price input must match current price')
                if not calculation_close(value['value'], inputs['price'] / inputs[basis]):
                    errors.append('metrics.' + key + ': value disagrees with declared ratio inputs')

    for index, event in enumerate(s['events']):
        context = 'events[%d]' % index
        published = event['published_at']
        if published:
            later = timestamp(published) > cutoff if 'T' in published else date.fromisoformat(published) > cutoff.date()
            if later:
                errors.append(context + ': published_at after data cutoff')
        elif event['status'] != 'unknown':
            errors.append(context + ': occurred/scheduled requires a verified publication date')
        event_date = event['event_date']
        if event['status'] == 'occurred':
            if event_date is None or date.fromisoformat(event_date) > cutoff.date():
                errors.append(context + ': occurred requires an event_date on/before data cutoff')
        elif event['status'] == 'scheduled':
            if event_date is None or date.fromisoformat(event_date) < cutoff.date():
                errors.append(context + ': scheduled requires an event_date on/after data cutoff date; past outcome must be rechecked')
    return errors


def qualified(snapshot, flag):
    value = snapshot['eligibility'][flag]
    return value in ('pass', 'limited') if snapshot['model_version'] == '1.3' else value


# Conservative lexical screening, not a general semantic proof of prose.
FINANCIAL_TERM_RE = re.compile(
    r'(?<![A-Za-z])(?:ROE|ROA|FCF)(?![A-Za-z])|P\s*/?\s*B(?![A-Za-z])|自由現金流|負債(?:比|率)|流動比(?:率)?|現金(?:轉換|轉化)|'
    r'淨值|每股淨資產|股東權益|現金流|現金餘額|負債|到期義務|cash\s+flow|net\s+cash|\bdebt\b|restricted\s+cash|return\s+on\s+(?:equity|assets)|'
    r'debt\s+(?:ratio|to\s+equity)|current\s+ratio|cash\s+conversion|book\s+value|net\s+assets?', re.I)
ABSENCE_RE = re.compile(r'未取得|未獲得|未核對|未驗證|未確認|未評估|無法取得|尚未|缺少|缺乏|缺資料|缺歷史|未知|待確認|不使用|不引用|不採用|不提供|已清空|已移除|null|N/?A|unavailable|unverified|missing|not\s+(?:available|verified|used)|no\s+(?:data|verified)', re.I)
ASSERTION_RE = re.compile(r'\d|充足|良好|改善|惡化|上升|下降|穩定|強勁|健康|支持|adequate|strong|improv|positive|healthy', re.I)


def text_financial_uses(value, path):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            found += text_financial_uses(child, path + '.' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found += text_financial_uses(child, '%s[%d]' % (path, index))
    elif isinstance(value, str):
        normalized = unicodedata.normalize('NFKC', value)
        for clause in re.split(r'[。；;\n，,！？!?]|\.(?!\d)', normalized):
            if FINANCIAL_TERM_RE.search(clause):
                # Negative declarations are exempt only without affirmative evidence
                # or numbers in the same clause. Ambiguous clauses fail conservatively.
                evidence_clause = re.sub(r'(?<![A-Za-z0-9])R(?:10|[1-9])(?![0-9])', '', clause, flags=re.I)
                if ABSENCE_RE.search(clause) and not ASSERTION_RE.search(evidence_clause):
                    continue
                found.append(path)
                break
    return found


def financial_input_uses(value, path):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + '.' + key
            if child is not None and (STATEMENT_METRIC_RE.search(key.lower()) or FINANCIAL_TERM_RE.search(key)):
                found.append(child_path)
            found += financial_input_uses(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found += financial_input_uses(child, '%s[%d]' % (path, index))
    return found


def report_hash(snapshot):
    return hashlib.sha256(snapshot['report_markdown'].encode('utf-8')).hexdigest()


def report_result_errors(snapshot, result):
    lines = [line for line in snapshot['report_markdown'].splitlines() if '整體投資訊號' in line]
    if len(lines) != 1:
        return ['report_markdown: exactly one final overall-result line required']
    line = lines[0]
    overall = result['derived']['overall']
    expected = {
        '整體投資訊號': {'unknown': '⚪', 'green': '🟢', 'yellow': '🟡', 'red': '🔴', 'major_risk': '🔴重大風險'}[overall['signal']],
        '總分': '不計分' if overall['score'] is None else str(overall['score']),
        '暫定': '是' if overall['provisional'] else '否',
        '信心': {'high': '高', 'medium': '中', 'low': '低', None: '未評定'}[overall['confidence']],
    }
    errors = []
    for label, value in expected.items():
        found = re.findall(re.escape(label) + r'\s*[:：]\s*([^；;|\n]+)', line)
        if len(found) != 1 or found[0].strip().strip('*') != value:
            errors.append('report_markdown: ' + label + ' disagrees with derived result ' + value)
    return errors


def sensitivity_result(snapshot, baseline):
    cases = []
    original_signal = baseline['overall']['signal']
    if baseline['overall']['score'] is not None:
        effective = baseline['valuation_effective_scores']
        caps, missing, _ = valuation_limits(snapshot)
        for dim, group in snapshot['scores'].items():
            for item in group['items']:
                name = item['check']
                score = effective[name] if dim == 'valuation' else item['score']
                if score is None or (dim != 'valuation' and not re.search(r'需打折|待確認|近似|邊界|有限制', item['reason'])):
                    continue
                for candidate in (score - 1, score + 1):
                    if not 0 <= candidate <= 2 or (dim == 'valuation' and name in missing):
                        continue
                    target = min(candidate, caps[name]) if dim == 'valuation' else candidate
                    if target == score:
                        continue
                    signal = derive(snapshot, {name: target}, confidence_rules=False)['overall']['signal']
                    cases.append({'dimension': dim, 'check': name, 'from_score': score,
                                  'to_score': target, 'signal': signal, 'changed': signal != original_signal})
    fragile = any(x['changed'] for x in cases)
    return {'checked': True, 'fragile': fragile, 'confidence_cap': 'medium' if fragile else None, 'cases': cases}


def comparison_status(current, previous):
    reasons = []
    for field in ('model_version', 'rule_version'):
        if not current.get(field) or not previous.get(field):
            reasons.append(field + ': unknown; do not infer a historical version')
        elif (current[field] != previous[field] if field == 'model_version' else
              current[field].split('.')[:2] != previous[field].split('.')[:2]):
            reasons.append(field + ': incompatible')
    for field in ('symbol', 'exchange', 'currency', 'instrument'):
        if current['security'][field] != previous['security'][field]:
            reasons.append('security.' + field + ': different')
    if timestamp(previous['analysis_at']) >= timestamp(current['analysis_at']):
        reasons.append('previous analysis must be earlier')
    return {'comparable': not reasons, 'reasons': reasons,
            'policy': 'Compare aligned facts and assumptions first; incompatible/unknown versions permit listing scores only.'}


def audit_keywords(schema):
    """Fail closed if this skill's schema changes beyond supported vocabulary."""
    if not isinstance(schema, dict):
        raise ValueError('schema must be an object')
    unknown = set(schema) - KEYWORDS
    if unknown:
        raise ValueError('unsupported schema keywords: ' + ', '.join(sorted(unknown)))
    if '$ref' in schema and not schema['$ref'].startswith('#/$defs/'):
        raise ValueError('only local bundled $defs references are supported')
    for key in ('properties', '$defs'):
        for child in schema.get(key, {}).values():
            audit_keywords(child)
    for key in ('items', 'additionalProperties'):
        child = schema.get(key)
        if isinstance(child, dict):
            audit_keywords(child)
    for child in schema.get('anyOf', []):
        audit_keywords(child)


def schema_errors(value, schema, root, path='$'):
    errors = []
    if '$ref' in schema:
        name = schema['$ref'][len('#/$defs/'):]
        if name not in root.get('$defs', {}):
            raise ValueError('unresolved schema reference: ' + name)
        errors += schema_errors(value, root['$defs'][name], root, path)
    if 'anyOf' in schema:
        options = [schema_errors(value, option, root, path) for option in schema['anyOf']]
        if all(options):
            errors.append(path + ': does not match any allowed shape')
            errors += min(options, key=len)
    kind = schema.get('type')
    matches = {
        'object': isinstance(value, dict), 'array': isinstance(value, list),
        'string': isinstance(value, str), 'null': value is None,
        'number': finite(value),
        'integer': finite(value) and float(value).is_integer(),
        'boolean': isinstance(value, bool),
    }
    if kind and not matches.get(kind, False):
        return errors + [path + ': expected ' + str(kind)]
    if 'enum' in schema and not any(equal(value, x) for x in schema['enum']):
        errors.append(path + ': not in enum')
    if 'const' in schema and not equal(value, schema['const']):
        errors.append(path + ': wrong constant')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        for key in schema.get('required', []):
            if key not in value:
                errors.append(path + '.' + key + ': required')
        for key, item in value.items():
            if key in props:
                errors += schema_errors(item, props[key], root, path + '.' + key)
            elif schema.get('additionalProperties') is False:
                errors.append(path + '.' + key + ': unexpected field')
            elif isinstance(schema.get('additionalProperties'), dict):
                errors += schema_errors(item, schema['additionalProperties'], root, path + '.' + key)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            errors.append(path + ': too few items')
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            errors.append(path + ': too many items')
        if 'items' in schema:
            for i, item in enumerate(value):
                errors += schema_errors(item, schema['items'], root, '%s[%d]' % (path, i))
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0):
            errors.append(path + ': string too short')
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            errors.append(path + ': pattern mismatch')
        try:
            if schema.get('format') == 'date-time':
                timestamp(value)
            elif schema.get('format') == 'date':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError('invalid date')
                date.fromisoformat(value)
            elif 'format' in schema:
                raise ValueError('unsupported format')
        except ValueError:
            errors.append(path + ': invalid ' + schema.get('format', 'format'))
    if finite(value):
        for key, fails in [('minimum', lambda x: value < x), ('maximum', lambda x: value > x),
                           ('exclusiveMinimum', lambda x: value <= x)]:
            if key in schema and fails(schema[key]):
                errors.append(path + ': violates ' + key)
    return errors


# 1.4.1: statement dependence is derived from content, never taken from the analyst's declaration alone.
STATEMENT_CHECKS = ('earnings_quality', 'balance_sheet', 'capital_efficiency', 'financial_event_buffer')
STATEMENT_METRIC_RE = re.compile(
    r'(^|_)(roe|roa|fcf|free_cash|debt|current_ratio|cash_conversion|net_assets?|book_value|bps|pb|equity|gearing|leverage)(_|$)')
STATEMENT_METHOD_RE = re.compile(r'P/?B|淨值|ROE|book value|net asset', re.I)


def statement_uses(snapshot):
    """Return every place the record uses statement-derived content (ROE, FCF, debt, net assets...)."""
    uses = []
    for name in DIMENSIONS:
        for item in snapshot['scores'][name]['items']:
            if item['check'] in STATEMENT_CHECKS and item['score'] is not None:
                uses.append('scores.' + name + '.' + item['check'])
    for key, metric in snapshot['metrics'].items():
        if STATEMENT_METRIC_RE.search(key) and metric.get('value') is not None:
            uses.append('metrics.' + key)
    valuation = snapshot.get('valuation') or {}
    band = valuation.get('band')
    if band and band.get('metric') == 'pb':
        uses.append('valuation.band(pb)')
    if valuation.get('method') and STATEMENT_METHOD_RE.search(valuation['method']):
        uses.append('valuation.method')
    if snapshot['model_version'] in ('1.2', '1.3'):
        rules = valuation.get('guardrails') or {}
        if valuation.get('primary_metric') == 'pb':
            uses.append('valuation.primary_metric(pb)')
        r1, r2 = rules.get('r1') or {}, rules.get('r2') or {}
        if r1.get('reference_book_value') is not None or r1.get('quarterly_book_values'):
            uses.append('valuation.guardrails.r1')
        if r2.get('ttm_roe_pct') is not None or r2.get('annual_roe_pct'):
            uses.append('valuation.guardrails.r2')
    if snapshot['model_version'] == '1.3':
        for key, metric in snapshot['metrics'].items():
            if metric.get('value') is not None and (STATEMENT_METRIC_RE.search(key.lower()) or FINANCIAL_TERM_RE.search(key)):
                uses.append('metrics.' + key)
        for name, group in snapshot['scores'].items():
            for item in group['items']:
                uses += text_financial_uses(item['reason'], 'scores.' + name + '.' + item['check'] + '.reason')
        uses += text_financial_uses(valuation, 'valuation')
        uses += text_financial_uses(snapshot['report_markdown'], 'report_markdown')
        uses += text_financial_uses(snapshot['major_risk']['reason'], 'major_risk.reason')
        uses += text_financial_uses(snapshot['risks'], 'risks')
        uses += text_financial_uses(snapshot['data_gaps'], 'data_gaps')
        uses += text_financial_uses(snapshot['overall']['reason'], 'overall.reason')
        for index, event in enumerate(snapshot['events']):
            uses += text_financial_uses(event['description'], 'events[%d].description' % index)
        for index, scenario in enumerate(valuation['scenarios']):
            uses += financial_input_uses(scenario['assumptions'], 'valuation.scenarios[%d].assumptions' % index)
        if any(x is not None for x in valuation['guardrails']['r1']['checks'].values()):
            uses.append('valuation.guardrails.r1.checks')
    return sorted(set(uses))


def financials_waived(snapshot):
    """Unread statements are tolerated only if declared not dependent AND the record really uses none."""
    flags = snapshot['eligibility']
    return (not qualified(snapshot, 'financials_verified') and flags.get('financials_dependent', True) is False
            and not statement_uses(snapshot))


def technical_light(technical):
    if technical['status'] != 'computed':
        return 'unknown'
    i = technical['indicators']
    if i['last_close'] > i['sma20'] > i['sma60'] and i['macd'] > i['macd_signal'] and i['rsi14'] <= 70:
        return 'green'
    if i['last_close'] < i['sma20'] < i['sma60'] and i['macd'] < i['macd_signal']:
        return 'red'
    return 'yellow'


def derive(snapshot, overrides=None, confidence_rules=True):
    groups, raw = {}, {}
    effective = effective_valuation_scores(snapshot) if snapshot['model_version'] in ('1.2', '1.3') else None
    for name, (weight, _) in DIMENSIONS.items():
        scores = [effective[x['check']] if name == 'valuation' and effective is not None else x['score']
                  for x in snapshot['scores'][name]['items']]
        if overrides:
            scores = [overrides.get(item['check'], score) for item, score in zip(snapshot['scores'][name]['items'], scores)]
        raw[name], groups[name] = dimension_result(scores, weight)
    flags = {k: qualified(snapshot, k) for k in QUALIFIERS}
    # 1.4.0/1.4.1: financials_verified may be waived only when the record uses no statement-derived content (derived, not declared).
    financials_ok = flags['financials_verified'] or financials_waived(snapshot)
    quote_fresh = snapshot['analysis_scope'] == 'historical' or flags['quote_is_current']
    complete = all(x is not None for x in raw.values()) and sum(x['coverage'] for x in groups.values()) >= 12
    eligible = complete and flags['quote_verified'] and quote_fresh and financials_ok and flags['valuation_supported']
    model11 = snapshot['model_version'] in ('1.1', '1.2', '1.3')
    coverage = sum(x['coverage'] for x in groups.values())
    available = [name for name in DIMENSIONS if raw[name] is not None]
    provisional_ok = (model11 and not eligible and flags['quote_verified'] and quote_fresh
                      and financials_ok and raw['valuation'] is not None
                      and len(available) >= 4 and coverage >= 10
                      and (snapshot['model_version'] != '1.3' or flags['valuation_supported']))
    if snapshot['major_risk']['confirmed']:
        overall = {'signal': 'major_risk', 'score': None, 'raw_score': None,
                   'reason': '已確認重大風險優先：' + snapshot['major_risk']['reason']}
        if model11:
            overall.update({'provisional': False, 'confidence': None})
    elif provisional_ok:
        total = weighted_total(raw, {name: DIMENSIONS[name][0] for name in DIMENSIONS}, normalize=True)
        complete_five = len(available) == 5
        signal = research_signal(total, raw, complete_five)
        confidence = 'medium' if complete_five and coverage >= 12 else 'low'
        missing = [name for name in DIMENSIONS if raw[name] is None]
        overall = {'signal': signal, 'score': rounded(total), 'raw_score': float(total),
                   'provisional': True, 'confidence': confidence,
                   'reason': '暫定（%s信心）：覆蓋%d/15%s；正式門檻未齊，分數依可評面向原權重比例換算' % (
                       '中' if confidence == 'medium' else '低', coverage,
                       '，缺' + '、'.join(missing) if missing else '')}
    elif not eligible:
        overall = {'signal': 'unknown', 'score': None, 'raw_score': None,
                   'reason': '資料／口徑／估值門檻未齊，不重分配權重；覆蓋%d/15' % coverage}
        if model11:
            overall.update({'provisional': False, 'confidence': None})
    else:
        total = weighted_total(raw, {name: DIMENSIONS[name][0] for name in DIMENSIONS})
        signal = research_signal(total, raw)
        overall = {'signal': signal, 'score': rounded(total), 'raw_score': float(total),
                   'reason': {'red': '現階段條件不利', 'green': '目前條件具吸引力', 'yellow': '值得觀察，等待條件改善或更多證據'}[signal]}
        if model11:
            overall.update({'provisional': False, 'confidence': 'high'})
    result = {'scores': groups, 'overall': overall, 'technical_signal': technical_light(snapshot['technical'])}
    if effective is not None:
        result['valuation_effective_scores'] = effective
        result['valuation_applied_adjustments'] = valuation_limits(snapshot)[2]
    if snapshot['model_version'] == '1.3' and confidence_rules:
        result['sensitivity'] = sensitivity_result(snapshot, result)
        limited = [k for k in QUALIFIERS if snapshot['eligibility'][k] == 'limited'
                   and not (k == 'quote_is_current' and snapshot['analysis_scope'] == 'historical')]
        overall = result['overall']
        if overall['score'] is not None:
            caps = ['medium'] if limited else []
            if len(limited) >= 2:
                overall['provisional'] = True
                caps.append('low')
            if result['sensitivity']['fragile']:
                caps.append('medium')
            rank = {'low': 0, 'medium': 1, 'high': 2}
            overall['confidence'] = min([overall['confidence']] + caps, key=rank.get)
            if limited:
                overall['reason'] += '；資格限制%d項，信心%s%s' % (len(limited), overall['confidence'], '，改為暫定' if len(limited) >= 2 else '')
            if result['sensitivity']['fragile']:
                overall['reason'] += '；單項敏感度可改變燈號，信心最高medium'
    return result


def urls(value):
    return [value] if isinstance(value, str) else value


def median(values):
    values = sorted(Fraction(str(x)) for x in values)
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def method_conflict(snapshot):
    check = snapshot['valuation']['guardrails']['r3']
    if check['status'] != 'checked':
        return False
    price = snapshot['metrics']['price']['value']
    if price is None or price <= 0:
        return False
    changes = [(Fraction(str(x['base_model_price'])) / Fraction(str(price)) - 1) * 100 for x in check['models']]
    return bool(changes) and max(changes) > 15 and min(changes) < -10


def valuation_limits(snapshot):
    caps = {x: 2 for x in ('model_upside', 'comparable_valuation', 'scenario_resilience')}
    missing, applied = set(), []
    checks = snapshot['valuation']['guardrails']
    def limit(rule, names, maximum, reason):
        for name in names:
            if maximum is None:
                missing.add(name)
            else:
                caps[name] = min(caps[name], maximum)
            applied.append({'rule': rule, 'check': name, 'maximum_score': maximum, 'reason': reason})
    if checks['r1']['status'] == 'unadjusted':
        limit('R1', ['model_upside', 'scenario_resilience'], 1, '淨值品質待調整，仍採未調整淨值，兩項最高1分')
    elif checks['r1']['status'] == 'unconfirmed':
        limit('R1', ['model_upside', 'scenario_resilience'], None, '原淨值口徑未確認，兩項維持null')
    if checks['r2']['status'] == 'unconfirmed':
        limit('R2', ['model_upside'], 1, '歷史區間可比性未確認，模型上行最高1分')
    if method_conflict(snapshot):
        limit('R3', ['model_upside', 'comparable_valuation'], 1, '方法衝突：一方法上行超過15%，另一方法下行超過10%，兩項最高1分')
    return caps, missing, applied


def effective_valuation_scores(snapshot):
    items = {x['check']: x['score'] for x in snapshot['scores']['valuation']['items']}
    caps, missing, _ = valuation_limits(snapshot)
    scenarios = {x['label']: x for x in snapshot['valuation']['scenarios']}
    price = snapshot['metrics']['price']['value']
    result = {}
    for check, supplied in items.items():
        if check not in caps:
            result[check] = None
            continue
        if supplied is None or check in missing:
            result[check] = None
            continue
        raw = supplied
        if check in ('model_upside', 'scenario_resilience'):
            label = 'base' if check == 'model_upside' else 'conservative'
            model_price = scenarios.get(label, {}).get('model_price')
            if model_price is None or price is None or price <= 0:
                result[check] = None
                continue
            raw = valuation_threshold_score(check, model_price, price)
        result[check] = min(raw, caps[check])
    return result


def guardrail_errors(snapshot, check_urls):
    errors = []
    v = snapshot['valuation']
    checks = v['guardrails']
    scenarios = {x['label']: x for x in v['scenarios']}
    r1, r2, r3 = (checks[k] for k in ('r1', 'r2', 'r3'))
    for rule, check in checks.items():
        check_urls(check['source_urls'], 'valuation.guardrails.' + rule,
                   check['status'] not in ('not_applicable', 'unconfirmed'))
    book_based = (v['primary_metric'] == 'pb' or (v.get('band') or {}).get('metric') == 'pb'
                  or bool(re.search(r'P/?B|淨值|book value|net asset', v.get('method') or '', re.I)))
    if book_based and r1['status'] == 'not_applicable':
        errors.append('R1: P/B valuation must record book-value quality')
    measures = r1['checks']
    if r1['status'] == 'unadjusted' and measures['latest_book_value'] is None:
        errors.append('R1: unadjusted requires known latest_book_value; otherwise use unconfirmed')
    change = None
    if measures['latest_book_value'] is not None and measures['previous_book_value'] is not None:
        change = abs(Fraction(str(measures['latest_book_value'])) / Fraction(str(measures['previous_book_value'])) - 1)
    triggered = ((change is not None and change > Fraction(15, 100))
                 or (measures['oci_share_of_book_change'] is not None and measures['oci_share_of_book_change'] > .5)
                 or (measures['listed_holding_share'] is not None and measures['listed_holding_share'] >= .2))
    if r1['status'] == 'clean':
        if any(x is None for x in measures.values()):
            errors.append('R1: clean requires all book-quality measurements')
        if triggered:
            errors.append('R1: trigger found; clean status is not allowed')
    if r1['status'] in ('adjusted', 'four_quarter_average'):
        if r1['reference_book_value'] is None or r1['reference_book_value'] <= 0:
            errors.append('R1: adjusted book-value basis requires a positive reference_book_value')
        if r1['status'] == 'four_quarter_average':
            if len(r1['quarterly_book_values']) != 4:
                errors.append('R1: four_quarter_average requires exactly four values')
            elif not close(sum(r1['quarterly_book_values']) / 4, r1['reference_book_value']):
                errors.append('R1: reference_book_value disagrees with four-quarter average')
            if len(r1['quarterly_book_values']) == 4 and measures['latest_book_value'] is not None and not close(r1['quarterly_book_values'][-1], measures['latest_book_value']):
                errors.append('R1: last quarterly_book_value must match latest_book_value')
        for scenario in v['scenarios']:
            if scenario['model_price'] is not None and (scenario['assumptions'].get('book_value_basis') != r1['status'] or not close(scenario['assumptions'].get('book_value_per_share'), r1['reference_book_value'])):
                errors.append('R1: every priced scenario must use the declared adjusted book-value basis')
            if scenario['model_price'] is not None and finite(r1['reference_book_value']):
                multiple = scenario['assumptions'].get('multiple')
                if not finite(multiple) or multiple <= 0 or not close(scenario['model_price'], r1['reference_book_value'] * multiple):
                    errors.append('R1: every model price must equal reference_book_value * assumptions.multiple')
    history_based = v['multiple_basis'] in ('self_history', 'vendor_band') or v.get('band') is not None
    if history_based and r2['status'] == 'not_applicable':
        errors.append('R2: historical valuation needs a comparability check')
    if r2['status'] in ('comparable', 'adjusted_multiple'):
        if r2['ttm_roe_pct'] is None or not r2['annual_roe_pct']:
            errors.append('R2: comparable/adjusted_multiple requires TTM and historical annual ROE')
        elif r2['status'] == 'comparable' and Fraction(str(r2['ttm_roe_pct'])) < median(r2['annual_roe_pct']) / 2:
            errors.append('R2: TTM ROE below half the annual median requires adjusted_multiple or unconfirmed')
    if r2['status'] == 'adjusted_multiple':
        selected = r2['selected_multiple']
        if selected is None or r2['adjustment_method'] is None:
            errors.append('R2: adjusted_multiple requires selected_multiple and adjustment_method')
        else:
            if r2['adjustment_method'] == 'approx_p25':
                band = v.get('band')
                if not band or not close(selected, (band['low'] + band['median']) / 2):
                    errors.append('R2: approx_p25 must equal midpoint of band low and median')
            if not close(scenarios.get('base', {}).get('assumptions', {}).get('multiple'), selected):
                errors.append('R2: base scenario must use selected_multiple in assumptions.multiple')
            assumptions = scenarios.get('base', {}).get('assumptions', {})
            basis_key = {'pe': 'eps', 'pb': 'book_value_per_share'}.get(v['primary_metric'])
            if basis_key:
                value = assumptions.get(basis_key)
                if not finite(value) or value <= 0 or not close(scenarios.get('base', {}).get('model_price'), value * selected):
                    errors.append('R2: base price must equal assumptions.' + basis_key + ' * selected_multiple')
    if r3['status'] == 'checked':
        if len(r3['models']) < 2:
            errors.append('R3: checked requires at least two models')
        if len({x['method'] for x in r3['models']}) != len(r3['models']):
            errors.append('R3: comparison methods must be distinct')
        primary = [x for x in r3['models'] if x['method'] == v['method']]
        if len(primary) != 1 or not close(primary[0]['base_model_price'] if primary else None, scenarios.get('base', {}).get('model_price')):
            errors.append('R3: include primary method with matching post-adjustment base price')
        for model in r3['models']:
            check_urls(model['source_urls'], 'R3.' + model['method'], True)
            if model['currency'] != snapshot['security']['currency'] or model['instrument'] != snapshot['security']['instrument']:
                errors.append('R3: every model must match security currency and instrument')
    elif r3['models']:
        errors.append('R3: models require status checked; do not hide supplied comparison')
    return errors


def semantic_errors(s, derive_only=False):
    errors = []
    if VERSION_PAIRS.get(s['schema_version']) != s['model_version']:
        errors.append('version: schema 1.2/model 1.0, schema 1.3/model 1.1, schema 1.4/model 1.2, schema 1.5/model 1.3')
    model11 = s['model_version'] in ('1.1', '1.2', '1.3')
    model12 = s['model_version'] in ('1.2', '1.3')
    model13 = s['model_version'] == '1.3'
    trace_fields = ('skill_version', 'rule_version', 'validator_version', 'report_sha256', 'sensitivity')
    if model13:
        if not all(k in s for k in trace_fields + ('report_markdown',)):
            return errors + ['model 1.3: version provenance, final report text/hash and sensitivity required']
        if (s['skill_version'], s['rule_version'], s['validator_version']) not in ARCHIVED_PROFILES | {RELEASE_PROFILE}:
            errors.append('version provenance: unsupported release profile; use its matching validator')
        headers = rule_headers(s['report_markdown'])
        if not headers or any(x != s['rule_version'] for x in headers):
            errors.append('report_markdown: rule version header missing or inconsistent')
        if not derive_only and s['report_sha256'] != report_hash(s):
            errors.append('report_sha256: final report text has changed; rederive and revalidate')
        if s['previous_report_reference'] is not None:
            for field in ('model_version', 'rule_version', 'skill_version', 'validator_version'):
                if field not in s['previous_report_reference']:
                    errors.append('previous_report_reference.' + field + ': required, unknown is null')
        for flag in QUALIFIERS:
            if isinstance(s['eligibility'][flag], bool):
                errors.append('model 1.3: eligibility.' + flag + ' must use explicit status')
    else:
        if any(k in s for k in trace_fields):
            errors.append('legacy snapshot: do not backfill model 1.3 provenance/derived fields')
        for flag in QUALIFIERS:
            if not isinstance(s['eligibility'][flag], bool):
                errors.append('legacy snapshot: eligibility.' + flag + ' must be boolean')
    guardrail_fields = ('primary_metric', 'guardrails', 'applied_adjustments')
    if model12 and not all(k in s['valuation'] for k in guardrail_fields):
        return errors + ['model 1.2/1.3: primary_metric, guardrails and applied_adjustments required']
    if not model12 and any(k in s['valuation'] for k in guardrail_fields):
        errors.append('model 1.0/1.1: guardrail fields belong to model 1.2/1.3')
    new_overall = [k for k in ('provisional', 'confidence') if k in s['overall']]
    new_valuation = [k for k in ('multiple_basis', 'eps_basis', 'band') if k in s['valuation']]
    if not model11 and (new_overall or new_valuation):
        errors.append('model 1.0: provisional/confidence/multiple_basis/eps_basis/band are model 1.1 fields')
    if model11:
        if len(new_overall) != 2:
            errors.append('model 1.1/1.2/1.3: overall.provisional and overall.confidence required')
        if len(new_valuation) != 3:
            errors.append('model 1.1/1.2/1.3: valuation.multiple_basis, eps_basis and band required (null allowed)')
        elif any(x['model_price'] is not None for x in s['valuation']['scenarios']) and (
                not s['valuation']['multiple_basis'] or not s['valuation']['eps_basis']):
            errors.append('model 1.1/1.2/1.3: model scenarios must state multiple_basis and eps_basis')
        band = s['valuation'].get('band')
        if band:
            if not band['low'] <= band['median'] <= band['high']:
                errors.append('valuation.band: requires low <= median <= high')
            if band['basis'] == 'self_history' and (band['observations'] is None or band['observations'] < 36):
                errors.append('valuation.band: self_history needs at least 36 monthly observations')
    cutoff, analysis = timestamp(s['data_cutoff_at']), timestamp(s['analysis_at'])
    if cutoff > analysis:
        errors.append('data_cutoff_at: after analysis_at')
    if s['quote_at'] and timestamp(s['quote_at']) > cutoff:
        errors.append('quote_at: after data cutoff')
    if s['financial_period_end'] and date.fromisoformat(s['financial_period_end']) > cutoff.date():
        errors.append('financial_period_end: after data cutoff')
    known = {x['url'] for x in s['sources']}
    for source in s['sources']:
        if timestamp(source['retrieved_at']) > analysis:
            errors.append('sources: retrieved_at after analysis_at')
        published = source['published_at']
        if published:
            later = timestamp(published) > cutoff if 'T' in published else date.fromisoformat(published) > cutoff.date()
            if later:
                errors.append('sources: published after data cutoff: ' + source['url'])
    def check_urls(values, context, require=False):
        if require and not values:
            errors.append(context + ': evidence URLs required')
        for url in values:
            if url not in known:
                errors.append(context + ': source missing from sources catalog: ' + url)
    for name, metric in s['metrics'].items():
        state, value = metric['value_status'], metric['value']
        if (state in ('missing', 'not_applicable')) != (value is None):
            errors.append('metrics.' + name + ': value and missing/not_applicable status disagree')
        if value is not None and metric['actual_or_estimate'] is None:
            errors.append('metrics.' + name + ': actual_or_estimate required for a value')
        check_urls(urls(metric['source_url']), 'metrics.' + name, value is not None)
        if timestamp(metric['retrieved_at']) > analysis:
            errors.append('metrics.' + name + ': retrieved_at after analysis_at')
        if metric['as_of']:
            later = timestamp(metric['as_of']) > cutoff if 'T' in metric['as_of'] else date.fromisoformat(metric['as_of']) > cutoff.date()
            if later:
                errors.append('metrics.' + name + ': as_of after data cutoff')
        if state == 'calculated' and (not metric['formula'] or not metric['inputs']):
            errors.append('metrics.' + name + ': calculated value needs formula and inputs')
    validations = {x['check']: x for x in s['validation']}
    if len(validations) != len(s['validation']):
        errors.append('validation: duplicate check IDs')
    for check in s['validation']:
        check_urls(check.get('source_urls', []), 'validation.' + check['check'])
        if any(name not in s['metrics'] for name in check['metrics']):
            errors.append('validation.' + check['check'] + ': unknown metric reference')
    if model13:
        for flag in QUALIFIERS:
            if validations.get(flag, {}).get('status') != s['eligibility'][flag]:
                errors.append('eligibility.' + flag + ': must match validation status including fail/limited')
    for flag in ('quote_verified', 'quote_is_current', 'financials_verified', 'valuation_supported'):
        if qualified(s, flag) and validations.get(flag, {}).get('status') != (s['eligibility'][flag] if s['model_version'] == '1.3' else 'pass'):
            errors.append('eligibility.' + flag + ': requires corresponding pass validation')
    # 1.4.2: financials_verified never takes limited; unread dependent statements are fail
    if validations.get('financials_verified', {}).get('status') == 'limited':
        errors.append('financials_verified: limited is not allowed (dependent-but-unread statements are fail)')
    price = s['metrics']['price']
    if price['value'] is not None and price['value'] <= 0:
        errors.append('metrics.price: known price must be positive; unknown is null, not zero')
    if qualified(s, 'quote_verified'):
        if price['value'] is None or price['value'] <= 0 or not s['quote_at'] or s['quote_status'] == 'unknown':
            errors.append('quote_verified: positive price and timestamp/status required')
        if price['currency'] != s['security']['currency'] or price['actual_or_estimate'] != 'actual':
            errors.append('quote_verified: price must be actual and match security currency')
    if qualified(s, 'quote_is_current') and not qualified(s, 'quote_verified'):
        errors.append('quote_is_current: quote must also be verified')
    if qualified(s, 'financials_verified') and (not s['financial_period_end'] or not any(x['source_type'] == 'financial_statement' for x in s['sources'])):
        errors.append('financials_verified: period end and financial statement source required')
    # 1.4.0/1.4.1: statement-dependence rules, checked against content (see SKILL.md 依賴的定義)
    elig = s['eligibility']
    if model13 and not qualified(s, 'financials_verified'):
        for use in statement_uses(s):
            errors.append(use + ': financial statement dependence while statements are unverified; clear the claim/value')
    if elig.get('financials_dependent', True) is False and not qualified(s, 'financials_verified'):
        if not (elig.get('reasons') or {}).get('financials_dependent'):
            errors.append('financials_dependent: false without verified statements requires reasons.financials_dependent')
        for use in statement_uses(s):
            errors.append(use + ': statement-derived content used while statements are unverified (financials_dependent false is not allowed)')
    eps, pe = s['metrics']['eps_ttm'], s['metrics']['pe_ttm']
    if eps['value'] is not None and eps['value'] <= 0 and pe['value'] is not None:
        errors.append('metrics.pe_ttm: nonpositive EPS cannot support a PE value')
    if pe['value_status'] == 'calculated':
        if price['value'] is None or eps['value'] is None or eps['value'] <= 0:
            errors.append('metrics.pe_ttm: calculated PE requires positive matching EPS and price')
        elif price['currency'] != eps['currency'] or price['unit'] != eps['unit']:
            errors.append('metrics.pe_ttm: price and EPS currency/security unit mismatch')
        elif not math.isclose(pe['value'], price['value'] / eps['value'], rel_tol=1e-9, abs_tol=1e-9):
            errors.append('metrics.pe_ttm: calculated value disagrees with price / eps_ttm')
    for name, (_, ids) in DIMENSIONS.items():
        items = s['scores'][name]['items']
        if sorted(x['check'] for x in items) != sorted(ids):
            errors.append('scores.' + name + ': needs three unique canonical check IDs')
        for item in items:
            check_urls(item['source_urls'], 'scores.' + name + '.' + item['check'], item['score'] is not None)
    risk = s['major_risk']
    check_urls(risk['source_urls'], 'major_risk', risk['confirmed'])
    valuation = s['valuation']
    check_urls(valuation['assumption_sources'], 'valuation.assumption_sources')
    if valuation.get('band'):
        check_urls(valuation['band']['source_urls'], 'valuation.band', True)
    if model12:
        errors += guardrail_errors(s, check_urls)
    if model13:
        rules = valuation['guardrails']
        limited_valuation = (rules['r1']['status'] in ('adjusted', 'four_quarter_average', 'unadjusted', 'unconfirmed')
                             or rules['r2']['status'] in ('adjusted_multiple', 'unconfirmed'))
        if limited_valuation and elig['valuation_supported'] == 'pass':
            errors.append('valuation_supported: R1/R2 limitation requires limited or fail, not pass')
    scenarios = {x['label']: x for x in valuation['scenarios']}
    if len(scenarios) != len(valuation['scenarios']):
        errors.append('valuation.scenarios: duplicate labels')
    for scenario in valuation['scenarios']:
        check_urls(scenario['source_urls'], 'valuation.' + scenario['label'], scenario['model_price'] is not None)
        if scenario['model_price'] is not None and not scenario['assumptions']:
            errors.append('valuation.' + scenario['label'] + ': assumptions required')
    if qualified(s, 'valuation_supported'):
        if not valuation['method'] or not valuation['horizon'] or not valuation['assumption_sources'] or not any(x['model_price'] is not None for x in scenarios.values()):
            errors.append('valuation_supported: supported method, horizon, sources and model scenario required; sensitivity is not a model')
    valuation_items = {x['check']: x for x in s['scores']['valuation']['items']}
    for check, label in [('model_upside', 'base'), ('scenario_resilience', 'conservative')]:
        item = valuation_items.get(check)
        if item and item['score'] is not None:
            model_price = scenarios.get(label, {}).get('model_price')
            if model_price is None or price['value'] is None or price['value'] <= 0 or not valuation['method'] or not valuation['assumption_sources']:
                errors.append('scores.valuation.' + check + ': matching sourced model scenario and price required')
            else:
                expected = valuation_threshold_score(check, model_price, price['value'])
                if not model12 and item['score'] != expected:
                    errors.append('scores.valuation.' + check + ': score disagrees with scenario threshold')
    if model12 and not derive_only:
        effective = effective_valuation_scores(s)
        for item in s['scores']['valuation']['items']:
            if not equal(item['score'], effective[item['check']]):
                errors.append('scores.valuation.' + item['check'] + ': differs from R1/R2/R3 adjusted score')
        if s['valuation']['applied_adjustments'] != valuation_limits(s)[2]:
            errors.append('valuation.applied_adjustments: differs from derived guardrail record')
    technical = s['technical']
    check_urls(technical['source_urls'], 'technical', technical['status'] == 'computed')
    if technical['status'] == 'computed':
        indicators = technical['indicators']
        necessary = ['sma20', 'sma60', 'rsi14', 'macd', 'macd_signal']
        min_bars = TECH_MIN_BARS[s['model_version']]
        if not indicators or any(indicators[k] is None for k in necessary) or not technical['as_of'] or not technical['adjustment'] or technical['observation_count'] < min_bars:
            errors.append('technical: computed requires dated, adjusted, sourced indicators and at least %d observations%s' % (
                min_bars, ' (model 1.1; fewer than 240 must use status insufficient_data)' if model11 else ''))
        elif any(indicators[k] <= 0 for k in ['sma20', 'sma60']):
            errors.append('technical: moving-average prices must be positive')
    elif technical['status'] == 'not_run' and (technical['indicators'] is not None or technical['observation_count'] != 0):
        errors.append('technical: not_run cannot claim computed indicators or observations')
    if technical['as_of'] and date.fromisoformat(technical['as_of']) > cutoff.date():
        errors.append('technical.as_of: after data cutoff')
    for event in s['events']:
        check_urls([event['source_url']], 'events')
    if strict_consistency(s):
        errors += consistency_errors(s, cutoff)
    return errors


def validate(snapshot, derive_only=False):
    if isinstance(snapshot, dict) and snapshot.get('schema_version') in ('1.0', '1.1'):
        return {'valid': False, 'scope': 'legacy_not_validated', 'errors': ['Legacy snapshot preserved; do not infer missing eligibility or rewrite history.'], 'derived': None}
    with open(ROOT / 'assets/snapshot.schema.json', encoding='utf-8') as source:
        schema = json.load(source)
    audit_keywords(schema)
    errors = schema_errors(snapshot, schema, schema)
    if errors:
        return {'valid': False, 'scope': 'structure', 'errors': errors, 'derived': None}
    errors = semantic_errors(snapshot, derive_only)
    if errors:
        return {'valid': False, 'scope': 'evidence_and_consistency', 'errors': errors, 'derived': None}
    expected = derive(snapshot)
    if not derive_only and snapshot.get('rule_version') in report_checks.PROFILE_RULES:
        errors += report_checks.report_errors(snapshot['report_markdown'], confidence=expected['overall']['confidence'])
    if not derive_only:
        for name, fields in expected['scores'].items():
            for key, value in fields.items():
                actual = snapshot['scores'][name][key]
                agrees = close(actual, value) if key in ('weight', 'raw_score') else equal(actual, value)
                if not agrees:
                    errors.append('scores.%s.%s: differs from derived value %s' % (name, key, value))
        for key in ('signal', 'score', 'raw_score') + (('provisional', 'confidence') if snapshot['model_version'] in ('1.1', '1.2', '1.3') else ()):
            actual, value = snapshot['overall'][key], expected['overall'][key]
            if not (close(actual, value) if key == 'raw_score' else equal(actual, value)):
                errors.append('overall.' + key + ': differs from derived value ' + str(value))
        if snapshot['technical']['signal'] != expected['technical_signal']:
            errors.append('technical.signal: differs from derived value ' + expected['technical_signal'])
        if snapshot['model_version'] == '1.3' and snapshot['sensitivity'] != expected['sensitivity']:
            errors.append('sensitivity: differs from derived counterfactual checks')
        if snapshot['model_version'] == '1.3':
            errors += report_result_errors(snapshot, {'derived': expected})
            if (snapshot['skill_version'], snapshot['rule_version'], snapshot['validator_version']) in SUMMARY_PROFILES:
                errors += summary_errors(snapshot)
    return {'valid': not errors, 'scope': 'structure_and_mechanical_rules', 'errors': errors, 'derived': expected,
            'limitation': 'Offline mechanical validation; external facts and subjective evidence scores are not independently verified.',
            'calculation_checks': ('core_metrics_pe_pb_ev_and_event_dates' if strict_consistency(snapshot)
                                   else 'archived_rules_only'),
            'summary_checks': ('four_line_presence' if snapshot['model_version'] == '1.3' and
                               (snapshot['skill_version'], snapshot['rule_version'], snapshot['validator_version']) in SUMMARY_PROFILES
                               and not derive_only else 'not_checked'),
            'decision_validation': 'not_checked_use_decision_guard'}


def derived_snapshot(snapshot, result):
    out = deepcopy(snapshot)
    if out['model_version'] in ('1.2', '1.3'):
        for item in out['scores']['valuation']['items']:
            item['score'] = result['derived']['valuation_effective_scores'][item['check']]
        out['valuation']['applied_adjustments'] = result['derived']['valuation_applied_adjustments']
    for name, fields in result['derived']['scores'].items():
        out['scores'][name].update(fields)
    out['overall'].update(result['derived']['overall'])
    out['technical']['signal'] = result['derived']['technical_signal']
    if out['model_version'] == '1.3':
        out['sensitivity'] = result['derived']['sensitivity']
        out['report_sha256'] = report_hash(out)
    return out


def load_json(stream):
    def reject(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('nonfinite JSON number: ' + value)
        return parsed
    return json.load(stream, parse_constant=reject, parse_float=finite_float, object_pairs_hook=unique)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', help='JSON path; omit for stdin')
    parser.add_argument('--derive', action='store_true', help='emit snapshot with derived fields; never modifies input')
    parser.add_argument('--report', help='UTF-8 final report path to bind into report_markdown before checking')
    parser.add_argument('--sensitivity', action='store_true', help='emit derived R6 counterfactual checks (model 1.3)')
    parser.add_argument('--compare', help='validated previous snapshot path; compare versions/security before score interpretation')
    args = parser.parse_args()
    try:
        if args.input:
            with open(args.input, encoding='utf-8') as source:
                snapshot = load_json(source)
        else:
            snapshot = load_json(sys.stdin)
        if args.report:
            if snapshot.get('model_version') != '1.3':
                raise ValueError('--report requires model 1.3; do not rewrite archived reports')
            snapshot['report_markdown'] = Path(args.report).read_text(encoding='utf-8')
        if sum(bool(x) for x in (args.derive, args.sensitivity, args.compare)) > 1:
            raise ValueError('--derive, --sensitivity and --compare are mutually exclusive')
        result = validate(snapshot, args.derive or args.sensitivity)
        if args.derive and result['valid']:
            output = derived_snapshot(snapshot, result)
        else:
            output = result
        if args.sensitivity and result['valid']:
            if snapshot['model_version'] != '1.3':
                raise ValueError('--sensitivity requires model 1.3')
            output = {'valid': True, 'sensitivity': result['derived']['sensitivity'], 'overall': result['derived']['overall']}
        if args.compare and result['valid']:
            with open(args.compare, encoding='utf-8') as source:
                previous = load_json(source)
            previous_result = validate(previous)
            if not previous_result['valid']:
                raise ValueError('previous snapshot is not validated: ' + '; '.join(previous_result['errors']))
            output = {'valid': True, 'comparison': comparison_status(snapshot, previous)}
        print(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2))
        return 0 if result['valid'] else 2
    except (ValueError, KeyError, TypeError, OSError, OverflowError, RecursionError) as error:
        print(json.dumps({'valid': False, 'scope': 'input', 'errors': [str(error)]}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
