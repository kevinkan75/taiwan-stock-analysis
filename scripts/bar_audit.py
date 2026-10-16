#!/usr/bin/env python3
"""Audit daily JSON bars; optionally sort/deduplicate with an explicit change log."""
import argparse
import json
import sys
from finance_math import inspect_bars, unique_object


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', help='JSON object with bars and optional bar_context; defaults to stdin')
    parser.add_argument('--normalize', action='store_true', help='explicitly sort and remove only identical duplicates in output; input is never rewritten')
    args = parser.parse_args(argv)
    def invalid_constant(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    try:
        def read(stream):
            return json.load(stream, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if args.input:
            with open(args.input, encoding='utf-8') as stream:
                data = read(stream)
        else:
            data = read(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError('input must be an object')
        result = inspect_bars(data.get('bars'), data.get('bar_context'), args.normalize)
    except (ValueError, TypeError, OSError, OverflowError) as error:
        result = {'valid': False, 'errors': [str(error)], 'normalized_bars': None}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0 if result['valid'] else 2


if __name__ == '__main__':
    sys.exit(main())
