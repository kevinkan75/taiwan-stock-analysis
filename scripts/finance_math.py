#!/usr/bin/env python3
"""Compute transparent valuation and daily indicators from verified JSON inputs."""
import argparse
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
    if not isinstance(bars, list) or not bars:
        raise ValueError('bars must be a nonempty array')
    values, volumes, previous = [], [], None
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError('each bar must be an object')
        timestamp = date.fromisoformat(bar['date'])
        if previous is not None and timestamp <= previous:
            raise ValueError('bar dates must be unique and strictly ascending')
        previous = timestamp
        values.append(number(bar.get('close'), 'close', positive=True))
        volume = bar.get('volume')
        if volume is not None:
            number(volume, 'volume')
            if volume < 0:
                raise ValueError('volume must not be negative')
        volumes.append(volume)
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
        'warmup_note': 'Prefer >=250 daily observations; EMA seeded by SMA. Flat RSI=50.',
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
                data = json.load(source, parse_constant=invalid_constant)
        else:
            data = json.load(sys.stdin, parse_constant=invalid_constant)
        print(json.dumps(calculate(data), ensure_ascii=False, allow_nan=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
        print(f'Invalid input: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
