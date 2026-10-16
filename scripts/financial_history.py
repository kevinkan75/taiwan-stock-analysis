"""Three comparable actual annual statements; no network, estimates or scoring.

Amounts are raw printed numbers plus an explicit scale. Sources, accounting
scope and latest available fiscal year remain supplied and checked by the analyst.
"""
from datetime import date, timedelta
import math
import re

from rules_core import finite, timestamp

FIELDS = ('revenue', 'gross_profit', 'operating_income', 'net_income_parent',
          'diluted_eps', 'total_assets', 'total_liabilities', 'total_equity',
          'parent_equity_begin', 'parent_equity_end', 'cash_bs_end',
          'cash_cf_end', 'cfo', 'cash_ppe_purchases')
FLOWS = {'revenue', 'gross_profit', 'operating_income', 'net_income_parent',
         'diluted_eps', 'cfo', 'cash_ppe_purchases'}
NONNEGATIVE = {'total_assets', 'total_liabilities', 'cash_bs_end', 'cash_cf_end'}
START = '<!-- financial-history:start -->'
END = '<!-- financial-history:end -->'
LABELS = {'complete': '已完成', 'partial': '資料未齊', 'conflicting': '勾稽不一致',
          'not_run': '尚未執行', 'not_applicable': '不適用'}


def initialize(is_etf=False, waived=False):
    return dict(status='not_applicable' if is_etf or waived else 'not_run',
                reason='ETF不套用單一公司年度財報' if is_etf else '依研究規則未使用報表衍生內容' if waived
                else '尚未核對最近三個完整年度；不得以季度或預估值補齊',
                currency=None, basis='consolidated', latest_period_end=None, periods=[])


def amount(cell):
    return None if cell['raw_value'] is None else cell['raw_value'] * cell['scale']


def schema():
    nullable_date = {'anyOf': [{'type': 'string', 'format': 'date'}, {'type': 'null'}]}
    cell = dict(type='object', properties={
        'raw_value': {'anyOf': [{'type': 'number'}, {'type': 'null'}]},
        'scale': {'enum': [None, 1, 1000, 1000000, 100000000]},
        'source_url': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
        'locator': {'type': 'string', 'minLength': 1},
        'period_start': nullable_date, 'period_end': nullable_date},
        required=['raw_value', 'scale', 'source_url', 'locator', 'period_start', 'period_end'],
        additionalProperties=False)
    period = dict(type='object', properties={
        'period_start': {'type': 'string', 'format': 'date'},
        'period_end': {'type': 'string', 'format': 'date'},
        'one_off_note': {'type': 'string', 'minLength': 1},
        'inputs': dict(type='object', properties={key: cell for key in FIELDS},
                       required=list(FIELDS), additionalProperties=False)},
        required=['period_start', 'period_end', 'one_off_note', 'inputs'], additionalProperties=False)
    return dict(type='object', properties={
        'status': {'enum': ['not_run', 'attempted', 'not_applicable']},
        'reason': {'type': 'string', 'minLength': 1},
        'currency': {'anyOf': [{'type': 'string', 'pattern': '^[A-Z]{3}$'}, {'type': 'null'}]},
        'basis': {'const': 'consolidated'}, 'latest_period_end': nullable_date,
        'periods': dict(type='array', items=period, maxItems=3)},
        required=['status', 'reason', 'currency', 'basis', 'latest_period_end', 'periods'],
        additionalProperties=False)


def validate(history, sources, cutoff, analysis_at, is_etf=False, waived=False):
    """Shape first checked by review schema. Unknown evidence is never a pass."""
    errors = []
    if not history['reason'].strip(): errors.append('financial_history: concrete reason required')
    if history['status'] != 'attempted':
        if history['periods'] or history['currency'] is not None or history['latest_period_end'] is not None:
            errors.append('financial_history: unattempted/not-applicable must not retain annual values')
        if history['status'] == 'not_applicable' and not (is_etf or waived):
            errors.append('financial_history: ordinary stock annual review cannot be waived without the financial-statement waiver')
        if is_etf and history['status'] != 'not_applicable':
            errors.append('financial_history: ETF requires explicit not_applicable')
        return errors
    if is_etf:
        errors.append('financial_history: ETF must not use company statement ratios')
    if not history['currency'] or not history['latest_period_end']:
        errors.append('financial_history: attempted review requires statement currency and latest complete annual period end')
    latest = date.fromisoformat(history['latest_period_end']) if history['latest_period_end'] else None
    if latest and latest > cutoff.date():
        errors.append('financial_history: latest annual period after cutoff')
    periods = history['periods']
    if periods and latest and periods[-1]['period_end'] != latest.isoformat():
        errors.append('financial_history: latest supplied year must match latest annual period end')
    previous = None
    for i, period in enumerate(periods):
        label = 'financial_history.periods.' + str(i)
        begin = date.fromisoformat(period['period_start']); end = date.fromisoformat(period['period_end'])
        if (end - begin).days + 1 not in (364, 365, 366, 371):
            errors.append(label + ': actual complete annual period required; no YTD/quarter/TTM substitution')
        if end > cutoff.date(): errors.append(label + ': future annual period')
        if previous and begin != previous + timedelta(days=1):
            errors.append(label + ': fiscal periods must be ascending, adjacent and non-overlapping')
        previous = end
        if not period['one_off_note'].strip(): errors.append(label + ': one-off/scope note required')
        for key, cell in period['inputs'].items():
            prefix = label + '.' + key
            value = cell['raw_value']
            if value is None:
                if any(cell[x] is not None for x in ('scale', 'source_url', 'period_start', 'period_end')):
                    errors.append(prefix + ': missing value must not retain numeric/source/date claims')
                continue
            if not cell['locator'].strip(): errors.append(prefix + ': source table/row locator required')
            if not finite(value) or not finite(cell['scale']) or not finite(value * cell['scale']):
                errors.append(prefix + ': finite numeric value and scale required; booleans are not numbers')
                continue
            if key == 'diluted_eps' and cell['scale'] != 1:
                errors.append(prefix + ': per-share EPS must not use monetary table scaling')
            if key in NONNEGATIVE and value < 0:
                errors.append(prefix + ': nonnegative balance required')
            expected_end = (begin - timedelta(days=1)).isoformat() if key == 'parent_equity_begin' else period['period_end']
            expected_start = period['period_start'] if key in FLOWS else None
            if cell['period_start'] != expected_start or cell['period_end'] != expected_end:
                errors.append(prefix + ': source period differs from annual/instant input; do not relabel years')
            url = cell['source_url']
            candidates = [s for s in sources if s['url'] == url]
            if not candidates:
                errors.append(prefix + ': registered source and locator required')
            for source in candidates:
                if source['source_type'] in ('external_estimate', 'company_guidance', 'analysis_assumption'):
                    errors.append(prefix + ': forecasts/assumptions cannot substitute for actual annual statements')
                published = source['published_at']
                if timestamp(source['retrieved_at']) > analysis_at:
                    errors.append(prefix + ': source retrieved after review')
                if published and (timestamp(published) > cutoff if 'T' in published else date.fromisoformat(published) > cutoff.date()):
                    errors.append(prefix + ': source published after cutoff')
                if published and cell['period_end'] and (timestamp(published).date() if 'T' in published else date.fromisoformat(published)) < date.fromisoformat(cell['period_end']):
                    errors.append(prefix + ': source published before the actual reporting period ended')
    if not errors:
        try:
            result = derive(history)
            def numbers_ok(value):
                if isinstance(value, dict): return all(numbers_ok(v) for v in value.values())
                if isinstance(value, list): return all(numbers_ok(v) for v in value)
                return finite(value) if isinstance(value, (int, float)) else True
            if not numbers_ok(result): errors.append('financial_history: nonfinite derived value')
        except (OverflowError, ValueError, ZeroDivisionError):
            errors.append('financial_history: derived arithmetic overflow/nonfinite value')
    return errors


def ratio(a, b):
    return a / b * 100 if a is not None and b is not None and b > 0 else None


def reconcile(name, cells, signs):
    values = [amount(c) for c in cells]
    if any(v is None for v in values):
        return dict(check=name, status='unavailable', difference=None, tolerance=None)
    difference = math.fsum(v * sign for v, sign in zip(values, signs))
    # At most half one printed unit for each rounded operand; no analyst-set
    # percentage tolerance, rounding, or clipping to make a mismatch pass.
    tolerance = math.fsum(c['scale'] for c in cells) / 2
    return dict(check=name, status='pass' if abs(difference) <= tolerance else 'conflict',
                difference=difference, tolerance=tolerance)


def derive(history):
    rows = []; checks = []; missing = []
    for period in history['periods']:
        cells = period['inputs']; v = {k: amount(c) for k, c in cells.items()}
        missing.extend(period['period_end'] + ':' + k for k, x in v.items() if x is None)
        average_equity = None if v['parent_equity_begin'] is None or v['parent_equity_end'] is None else v['parent_equity_begin'] / 2 + v['parent_equity_end'] / 2
        roe = ratio(v['net_income_parent'], average_equity) if all(v[k] is not None and v[k] > 0 for k in ('parent_equity_begin', 'parent_equity_end')) else None
        row = dict(period_start=period['period_start'], period_end=period['period_end'],
                   revenue=v['revenue'], gross_margin=ratio(v['gross_profit'], v['revenue']),
                   operating_margin=ratio(v['operating_income'], v['revenue']),
                   net_income_parent=v['net_income_parent'], diluted_eps=v['diluted_eps'],
                   roe=roe, fcf=None if v['cfo'] is None or v['cash_ppe_purchases'] is None else v['cfo'] - abs(v['cash_ppe_purchases']),
                   one_off_note=period['one_off_note'], revenue_yoy=None, eps_yoy=None,
                   revenue_change=None, eps_change=None, gross_margin_change_pp=None)
        if rows:
            for field, prefix in [('revenue', 'revenue'), ('diluted_eps', 'eps')]:
                old = rows[-1][field]; new = row[field]
                row[prefix + '_change'] = None if old is None or new is None else new - old
                row[prefix + '_yoy'] = None if old is None or old <= 0 or new is None else (new / old - 1) * 100
            old = rows[-1]['gross_margin']; new = row['gross_margin']
            row['gross_margin_change_pp'] = None if old is None or new is None else new - old
        for name, keys, signs in [('balance_equation', ['total_assets', 'total_liabilities', 'total_equity'], [1, -1, -1]),
                                   ('cash_end_match', ['cash_bs_end', 'cash_cf_end'], [1, -1])]:
            checks.append(dict(period_end=period['period_end'], **reconcile(name, [cells[k] for k in keys], signs)))
        # Parent equity repeated as prior closing and current opening must agree.
        if len(rows) > 0:
            prior = history['periods'][len(rows) - 1]['inputs']['parent_equity_end']
            checks.append(dict(period_end=period['period_end'], **reconcile('equity_opening_match', [cells['parent_equity_begin'], prior], [1, -1])))
        rows.append(row)
    conflict = any(c['status'] == 'conflict' for c in checks)
    status = history['status'] if history['status'] != 'attempted' else 'conflicting' if conflict else 'complete' if len(rows) == 3 and not missing else 'partial'
    cagr = None
    if len(rows) == 3 and all(rows[i]['revenue'] is not None and rows[i]['revenue'] > 0 for i in (0, 2)):
        cagr = ((rows[-1]['revenue'] / rows[0]['revenue']) ** .5 - 1) * 100
    return dict(status=status, currency=history['currency'], reason=history['reason'],
                periods=len(rows), missing_periods=0 if status=='not_applicable' else 3-len(rows), rows=rows, checks=checks, missing_inputs=missing,
                revenue_cagr_two_intervals=cagr,
                limitation='原文、合併範圍、歸母口徑、一次性因素與最近已公布年度仍須人工核對；勾稽通過不證明外部數據真實。')


def fmt(value, suffix=''):
    return '未取得／不適用' if value is None else f'{value:,.2f}' + suffix


def render(result):
    """Render only derived values. Report binding prevents divergent HTML/table copies."""
    lines = [START, '三年財務趨勢：' + LABELS[result['status']] + '。' + result['reason']]
    rows = result['rows']
    if rows:
        lines.append('年度以財年結束日標示；金額為' + result['currency'] + '百萬元，每股EPS為原幣元／股；不混入TTM或季度。')
        lines += ['| 指標 | ' + ' | '.join(r['period_end'] for r in rows) + ' |',
                  '| --- | ' + ' | '.join('---:' for _ in rows) + ' |']
        for key, label, suffix in [('revenue', '營收', ''), ('revenue_yoy', '營收年增率', '%'),
                                   ('gross_margin', '毛利率', '%'), ('gross_margin_change_pp', '毛利率年變動', '百分點'),
                                   ('operating_margin', '營業利益率', '%'), ('net_income_parent', '歸母淨利', ''),
                                   ('diluted_eps', '稀釋EPS', ''), ('eps_yoy', 'EPS年增率', '%'),
                                   ('roe', '平均歸母權益ROE', '%'), ('fcf', 'CFO減現金購置PP&E', '')]:
            lines.append('| ' + label + ' | ' + ' | '.join(fmt(r[key] / 1000000 if r[key] is not None and key in ('revenue','net_income_parent','fcf') else r[key], suffix) for r in rows) + ' |')
        lines.append('首末年度營收CAGR（兩個年度間隔）：' + fmt(result['revenue_cagr_two_intervals'], '%') + '。')
        lines.append('成長率前期非正或缺值時不計百分比；變動金額保留於查核附檔。ROE期初或期末權益非正時不作正向效率判斷。')
        for r in rows:
            lines.append('一次性因素／口徑 ' + r['period_end'] + '：' + r['one_off_note'])
        names = {'balance_equation': '資產＝負債＋總權益', 'cash_end_match': '兩表期末現金', 'equity_opening_match': '跨年度歸母權益'}
        states = {'pass': '通過', 'conflict': '不一致', 'unavailable': '缺資料，未通過驗證'}
        for c in result['checks']:
            lines.append('報表勾稽 ' + c['period_end'] + ' ' + names[c['check']] + '：' + states[c['status']] +
                         '；差額' + fmt(c['difference']) + '，原表單位捨入容許值' + fmt(c['tolerance']) + '。')
        if result['missing_inputs']:
            lines.append('年度資料缺口：' + '、'.join(result['missing_inputs']) + '。')
    lines += [result['limitation'], END]
    return '\n'.join(lines)


def strip_report(report):
    return re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', report, flags=re.S)


def report_errors(report, result):
    expected = render(result)
    return [] if report.count(START) == report.count(END) == report.count(expected) == 1 else [
        'financial_history: final annual table/checks differ from derived report or are missing/duplicated']
