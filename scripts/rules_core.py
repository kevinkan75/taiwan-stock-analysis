"""Shared numeric rules and release profiles; no data fetching or prose evaluation."""
from datetime import datetime
from fractions import Fraction
import math
import re

SKILL_VERSION = '1.14.0'
RULE_VERSION = '1.14.0'
VALIDATOR_VERSION = '1.6.0'
DECISION_MODEL_VERSION = 'decision-1.1'
DECISION_VALIDATOR_VERSION = '2.1.0'
ETF_MODEL_VERSION = 'etf-1.2'
ETF_VALIDATOR_VERSION = '1.2.0'
ETF_RELEASE_PROFILE = (SKILL_VERSION, RULE_VERSION, ETF_VALIDATOR_VERSION)
DECISION_PROFILES = {('1.13.0','1.13.0','2.1.0'), ('1.12.0', '1.12.0', '2.1.0'), ('1.11.0', '1.11.0', '2.1.0'), (SKILL_VERSION, RULE_VERSION, DECISION_VALIDATOR_VERSION), ('1.10.0', '1.10.0', '2.0.0'), ('1.8.0', '1.8.0', '1.0.0'), ('1.9.0', '1.9.0', '1.1.0')}
ETF_ANNUAL_PROFILE = ('1.13.0', '1.13.0', '1.2.0')
ANNUAL_PROFILE = ('1.13.0', '1.13.0', '1.6.0')
ETF_CLAIM_PROFILE = ('1.12.0', '1.12.0', '1.2.0')
CLAIM_PROFILE = ('1.12.0', '1.12.0', '1.6.0')
ETF_REVIEW_PROFILE = ('1.11.0', '1.11.0', '1.2.0')
WORKFLOW_PROFILE = ('1.11.0', '1.11.0', '1.6.0')
ETF_PREVIOUS_PROFILE = ('1.10.0', '1.10.0', '1.1.0')
ETF_ARCHIVED_PROFILE = ('1.9.0', '1.9.0', '1.0.0')
RELEASE_PROFILE = (SKILL_VERSION, RULE_VERSION, VALIDATOR_VERSION)
ARITHMETIC_PROFILE = ('1.6.0', '1.6.0', '1.4.0')
SUMMARY_PROFILE = ('1.7.0', '1.7.0', '1.4.1')
SHARED_PROFILE = ('1.8.0', '1.8.0', '1.5.0')
ETF_INTRO_PROFILE = ('1.9.0', '1.9.0', '1.5.0')
PREVIOUS_PROFILE = ('1.10.0', '1.10.0', '1.5.0')
ARCHIVED_PROFILES = {('1.5.0', '1.5.0', '1.3.0'), ARITHMETIC_PROFILE, SUMMARY_PROFILE, SHARED_PROFILE, ETF_INTRO_PROFILE, PREVIOUS_PROFILE, WORKFLOW_PROFILE, CLAIM_PROFILE, ANNUAL_PROFILE}
ARITHMETIC_PROFILES = {RELEASE_PROFILE, ARITHMETIC_PROFILE, SUMMARY_PROFILE, SHARED_PROFILE, ETF_INTRO_PROFILE, PREVIOUS_PROFILE, WORKFLOW_PROFILE, CLAIM_PROFILE, ANNUAL_PROFILE}
SUMMARY_PROFILES = {RELEASE_PROFILE, SUMMARY_PROFILE, SHARED_PROFILE, ETF_INTRO_PROFILE, PREVIOUS_PROFILE, WORKFLOW_PROFILE, CLAIM_PROFILE, ANNUAL_PROFILE}
VERSION_PAIRS = {'1.2': '1.0', '1.3': '1.1', '1.4': '1.2', '1.5': '1.3'}
TECH_MIN_BARS = {'1.0': 60, '1.1': 240, '1.2': 240, '1.3': 240}
QUALIFIERS = ('quote_verified', 'quote_is_current', 'financials_verified', 'valuation_supported')
SUMMARY_LABELS = ('估值位置', '下一個催化劑', '最大單一風險', '關鍵缺口')
DIMENSIONS = {
    'fundamentals': (Fraction(25, 100), ['earnings_quality', 'balance_sheet', 'capital_efficiency']),
    'growth': (Fraction(20, 100), ['realized_revenue', 'realized_eps', 'future_drivers']),
    'valuation': (Fraction(25, 100), ['model_upside', 'comparable_valuation', 'scenario_resilience']),
    'industry': (Fraction(15, 100), ['end_demand', 'competitive_position', 'supply_policy']),
    'risk': (Fraction(15, 100), ['operations_concentration', 'regulatory_governance', 'financial_event_buffer']),
}
CORE_GATES = (1, 2, 3, 5, 6, 8)
ENTRY_GREEN_GATES = (1, 2, 3, 5, 8)
ENTRY_OBSERVED_GATES = (4, 6, 7)
SIGNAL_LABELS = {'green': '🟢', 'yellow': '🟡', 'red': '🔴', 'unknown': '⚪', 'major_risk': '🔴重大風險'}
ACTION_LABELS = {'abandon': '放棄', 'wait': '等待', 'enter': '進場', 'staged': '分批'}
ETF_SUPPORTED_SUBTYPES = ('市值型', '高股息／因子型', '產業／主題型', '主動式', '債券型', '跨境股票型')
ETF_DIMENSIONS = {
    'instrument': (Fraction(20, 100), ['index_methodology', 'total_cost', 'tracking_quality']),
    'tradability': (Fraction(15, 100), ['fund_scale', 'liquidity', 'premium_discount']),
    'portfolio': (Fraction(20, 100), ['concentration', 'exposure_fit', 'holdings_quality']),
    'valuation': (Fraction(25, 100), ['band_position', 'relative_valuation', 'earnings_support']),
    'risk': (Fraction(20, 100), ['drawdown_volatility', 'distribution_quality', 'structural_risk']),
}
ETF_QUALIFIERS = ('quote_verified', 'quote_is_current', 'holdings_financials_verified', 'valuation_supported')
ETF_COVERAGE_MIN = {'holdings_quality': 70, 'band_position': 80, 'relative_valuation': 70, 'earnings_support': 70}


def finite(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value
    ):
        raise ValueError('expected timezone-aware ISO date-time')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def rule_headers(report, label='規則版本'):
    return re.findall(r'^\s*(?:[#*]+\s*)?' + re.escape(label) + r'\s*[:：]?\s*(\d+\.\d+\.\d+)', report, re.M)


def equal(a, b):
    return isinstance(a, bool) == isinstance(b, bool) and a == b


def close(a, b):
    if a is None or b is None:
        return a is b
    return finite(a) and finite(b) and math.isclose(a, b, rel_tol=0, abs_tol=1e-9)


def rounded(value):
    """Exact halves up; thresholds always use the unrounded Fraction."""
    return (value.numerator * 2 + value.denominator) // (value.denominator * 2)


def light(score):
    return 'unknown' if score is None else 'green' if score >= 75 else 'yellow' if score >= 40 else 'red'


def dimension_result(scores, weight, total_items=3, minimum_items=2):
    values = [x for x in scores if x is not None]
    score = Fraction(sum(int(x) for x in values) * 50, len(values)) if len(values) >= minimum_items else None
    return score, {'weight': float(weight), 'coverage': len(values), 'total_items': total_items,
                   'raw_score': float(score) if score is not None else None,
                   'display_score': rounded(score) if score is not None else None, 'signal': light(score)}


def weighted_total(raw, weights, normalize=False):
    names = [name for name in weights if raw[name] is not None]
    if not names:
        return None
    total = sum((raw[name] * weights[name] for name in names), Fraction(0))
    return total / sum(weights[name] for name in names) if normalize else total


def research_signal(total, raw, complete_five=True):
    if total < 40 or raw['valuation'] < 40 or (raw['risk'] is not None and raw['risk'] < 40):
        return 'red'
    if (complete_five and total >= 75 and raw['valuation'] >= 75 and raw['risk'] >= 75
            and raw['fundamentals'] >= 40 and raw['growth'] >= 40):
        return 'green'
    return 'yellow'


def valuation_threshold_score(check, model_price, price):
    if model_price is None or price is None or price <= 0:
        return None
    change = (Fraction(str(model_price)) / Fraction(str(price)) - 1) * 100
    if check == 'model_upside':
        return 0 if change < -10 else 1 if change <= 15 else 2
    if check == 'scenario_resilience':
        return 0 if change < -30 else 1 if change < -15 else 2
    raise ValueError('unknown valuation threshold check')
