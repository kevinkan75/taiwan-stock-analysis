#!/usr/bin/env python3
"""Compute transparent valuation and daily indicators from verified JSON inputs."""
import argparse
from copy import deepcopy
import json
import math
import sys
from datetime import date


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if positive and value <= 0:
        raise ValueError(f'{name} must be positive')
    return value


def sma(values, period):
    return sum(values[-period:]) / period if len(values) >= period else None


def ema(values, period):
    result = [None] * len(values)
    if len(values) < period:
        return result
    current = sum(values[:period]) / period
    result[period - 1] = current
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        current += alpha * (values[i] - current)
        result[i] = current
    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [b - a for a, b in zip(values, values[1:])]
    gain = sum(max(x, 0) for x in changes[:period]) / period
    loss = sum(max(-x, 0) for x in changes[:period]) / period
    for delta in changes[period:]:
        gain = (gain * (period - 1) + max(delta, 0)) / period
        loss = (loss * (period - 1) + max(-delta, 0)) / period
    if gain == 0 and loss == 0:
        return 50.0
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)



BAR_VALIDATOR_VERSION = '1.0.0'
PRICE_BASES = ('raw', 'split_adjusted', 'total_return_adjusted', 'unknown')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def session_date(value):
    """Only an exchange-local session date; do not truncate or convert timestamps."""
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('date must be an exchange-local YYYY-MM-DD session date')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('date must be canonical YYYY-MM-DD')
    return parsed


def inspect_bars(bars, context=None, normalize=False):
    """Audit without imputing, adjusting prices, classifying suspensions or deleting events.

    normalize=True explicitly sorts and removes identical duplicate rows; conflicting
    same-date rows always fail. The caller's input remains unchanged.
    """
    result = {'validator_version': BAR_VALIDATOR_VERSION, 'valid': False,
              'errors': [], 'issues': [], 'changes': [], 'normalized_bars': None,
              'summary': {}, 'scope': 'Input structure and diagnostics only; not source truth, exchange calendar verification or trading eligibility.'}
    errors, issues, changes = result['errors'], result['issues'], result['changes']
    if not isinstance(bars, list) or not bars:
        errors.append('bars must be a nonempty array')
        return result
    if context is None:
        context = {}
    if not isinstance(context, dict):
        errors.append('bar_context must be an object')
        return result
    rows = deepcopy(bars)
    for i, bar in enumerate(rows):
        try:
            if not isinstance(bar, dict):
                raise ValueError('each bar must be an object')
            session_date(bar.get('date'))
            number(bar.get('close'), 'close', positive=True)
            if any(k in bar for k in ('open', 'high', 'low')):
                for k in ('open', 'high', 'low'):
                    number(bar.get(k), k, positive=True)
                if not (bar['low'] <= min(bar['open'], bar['close']) and
                        bar['high'] >= max(bar['open'], bar['close']) and bar['high'] >= bar['low']):
                    raise ValueError('OHLC ordering is inconsistent')
            volume = bar.get('volume')
            if volume is not None and number(volume, 'volume') < 0:
                raise ValueError('volume must not be negative')
        except (ValueError, TypeError, OverflowError) as error:
            errors.append('bars[%d]: %s' % (i, error))
    if errors:
        return result
    if normalize:
        ordered = sorted(enumerate(rows), key=lambda pair: pair[1]['date'])
        if [i for i, _ in ordered] != list(range(len(rows))):
            changes.append({'kind': 'sort_dates', 'original_indices': [i for i, _ in ordered]})
        kept = []
        for index, bar in ordered:
            if kept and bar['date'] == kept[-1]['date']:
                if bar != kept[-1]:
                    errors.append('conflicting duplicate date: ' + bar['date'])
                else:
                    changes.append({'kind': 'remove_identical_duplicate', 'date': bar['date'], 'original_index': index})
            else:
                kept.append(bar)
        rows = kept
    elif any(b['date'] <= a['date'] for a, b in zip(rows, rows[1:])):
        errors.append('bar dates must be unique and strictly ascending; explicit normalization is separate')
    basis = context.get('price_basis', 'unknown')
    if basis not in PRICE_BASES:
        errors.append('price_basis must be raw, split_adjusted, total_return_adjusted or unknown')
    used_bases = {basis} if isinstance(basis, str) and basis in PRICE_BASES and basis != 'unknown' else set()
    for key in ('ohlc_basis', 'close_basis'):
        value = context.get(key, 'unknown')
        if value not in PRICE_BASES:
            errors.append(key + ': invalid price basis')
        elif value != 'unknown':
            used_bases.add(value)
    for bar in rows:
        value = bar.get('price_basis', 'unknown')
        if value not in PRICE_BASES:
            errors.append('bar price_basis: invalid price basis')
        elif value != 'unknown':
            used_bases.add(value)
    if len(used_bases) > 1:
        errors.append('mixed price adjustment bases; never combine raw OHLC and adjusted close')
    if basis == 'unknown':
        issues.append({'kind': 'price_basis_unknown', 'requires_review': True})
    for key in ('source_url', 'exchange'):
        if not isinstance(context.get(key), str) or not context[key].strip():
            issues.append({'kind': key + '_missing', 'requires_review': True})
    expected = context.get('expected_sessions')
    calendar_status = 'not_supplied'
    if expected is not None:
        try:
            if not isinstance(expected, list) or not expected:
                raise ValueError('expected_sessions must be a nonempty array')
            dates = [session_date(x) for x in expected]
            if any(b <= a for a, b in zip(dates, dates[1:])):
                raise ValueError('expected_sessions must be unique and ascending')
            calendar_status = 'caller_supplied_not_independently_verified'
            if not isinstance(context.get('calendar_source_url'), str) or not context['calendar_source_url'].strip():
                issues.append({'kind': 'calendar_source_missing', 'requires_review': True})
            # Check the supplied coverage span, including missing boundary sessions.
            missing = sorted(set(expected) - {bar['date'] for bar in rows})
            outside = sorted({bar['date'] for bar in rows} - set(expected))
            for kind, dates in [('missing_expected_sessions', missing), ('outside_supplied_calendar', outside)]:
                if dates:
                    issues.append({'kind': kind, 'dates': dates, 'requires_review': True,
                                   'note': 'Could be source gaps, listing boundaries, calendar mismatch or events; not a suspension diagnosis.'})
        except (ValueError, TypeError) as error:
            errors.append(str(error))
    else:
        issues.append({'kind': 'calendar_not_supplied', 'requires_review': True,
                       'note': 'Cannot distinguish holidays, suspension, listing boundaries and missing sessions.'})
    jump = context.get('jump_threshold_pct')
    if jump is not None:
        try:
            number(jump, 'jump_threshold_pct', positive=True)
        except (ValueError, OverflowError) as error:
            errors.append(str(error))
    if errors:
        return result
    for bar in rows:
        if bar.get('volume') is None:
            issues.append({'kind': 'volume_missing', 'date': bar['date'], 'requires_review': True})
        elif bar['volume'] == 0:
            flat = all(k in bar for k in ('open', 'high', 'low')) and len({bar[k] for k in ('open', 'high', 'low', 'close')}) == 1
            issues.append({'kind': 'zero_volume_flat_bar' if flat else 'zero_volume',
                           'date': bar['date'], 'requires_review': True,
                           'note': 'Retained, not automatically removed or classified as a ghost/suspension.'})
    for previous, current in zip(rows, rows[1:]):
        value = (current['close'] / previous['close'] - 1) * 100
        if not math.isfinite(value):
            errors.append('nonfinite adjacent return: ' + current['date'])
        elif jump is not None and abs(value) > jump:
            issues.append({'kind': 'large_price_change', 'date': current['date'],
                           'previous_date': previous['date'], 'return_pct': value,
                           'threshold_pct': jump, 'requires_review': True,
                           'note': 'Caller-defined diagnostic threshold, not a trading limit or evidence of erroneous data.'})
    result['valid'] = not errors
    result['summary'] = {'input_count': len(bars), 'output_count': len(rows),
                         'first_date': rows[0]['date'], 'last_date': rows[-1]['date'],
                         'price_basis': basis, 'calendar_status': calendar_status,
                         'return_unit': 'percent: 1 means 1%',
                         'requires_review': any(x.get('requires_review') for x in issues)}
    if normalize and not errors:
        result['normalized_bars'] = rows
    return result


def calculate(data):
    if not isinstance(data, dict):
        raise ValueError('input must be an object')
    price = data.get('price')
    if price is not None:
        number(price, 'price', positive=True)
    eps = data.get('eps_ttm')
    if eps is not None:
        number(eps, 'eps_ttm')
    result = {
        'pe_ttm': price / eps if price is not None and eps is not None and eps > 0 else None,
        'scenarios': [],
        'technical': None,
    }
    scenarios = data.get('scenarios', [])
    if not isinstance(scenarios, list):
        raise ValueError('scenarios must be an array')
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError('each scenario must be an object')
        earnings = number(scenario.get('eps'), 'scenario.eps')
        multiple = number(scenario.get('pe'), 'scenario.pe', positive=True)
        model_price = earnings * multiple if earnings > 0 else None
        result['scenarios'].append({
            'label': scenario.get('label'),
            'eps': earnings, 'pe': multiple, 'model_price': model_price,
            'upside_pct': (model_price / price - 1) * 100 if model_price is not None and price is not None else None,
            'status': 'computed' if model_price is not None else 'not_applicable_nonpositive_eps',
        })
    if 'bars' not in data:
        return result
    bars = data['bars']
    audit = inspect_bars(bars, data.get('bar_context'))
    if not audit['valid']:
        raise ValueError('; '.join(audit['errors']))
    result['bar_validation'] = audit
    values = [bar['close'] for bar in bars]
    volumes = [bar.get('volume') for bar in bars]
    fast, slow = ema(values, 12), ema(values, 26)
    macd_values = [f - s for f, s in zip(fast, slow) if f is not None and s is not None]
    macd = macd_values[-1] if macd_values else None
    signal_values = ema(macd_values, 9)
    signal = signal_values[-1] if signal_values else None
    volume_mean = None
    if len(volumes) >= 20 and all(v is not None for v in volumes[-20:]):
        volume_mean = sum(volumes[-20:]) / 20
    result['technical'] = {
        'count': len(values), 'last_date': bars[-1]['date'], 'last_close': values[-1],
        'sma20': sma(values, 20), 'sma60': sma(values, 60), 'sma120': sma(values, 120),
        'rsi14': rsi(values), 'macd': macd, 'macd_signal': signal,
        'macd_histogram': macd - signal if macd is not None and signal is not None else None,
        'volume_sma20': volume_mean,
        'relative_volume20': volumes[-1] / volume_mean if volume_mean and volumes[-1] is not None else None,
        'warmup_note': 'Research signals require >=240 valid daily observations plus source/context checks; EMA seeded by SMA. Flat RSI=50.',
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', help='JSON path; omit to read stdin')
    args = parser.parse_args()
    def invalid_constant(value):
        raise ValueError(f'nonfinite JSON constant: {value}')
    try:
        if args.input:
            with open(args.input, encoding='utf-8') as source:
                data = json.load(source, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        else:
            data = json.load(sys.stdin, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        print(json.dumps(calculate(data), ensure_ascii=False, allow_nan=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        print(f'Invalid input: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
