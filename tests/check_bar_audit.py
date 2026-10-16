"""Independent synthetic boundaries, data preservation and public CLI checks."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import finance_math as fm

count = 0


def check(ok, reason):
    global count
    count += 1
    if not ok:
        raise AssertionError(reason)


def kinds(result):
    return {x['kind'] for x in result['issues']}


def row(day='2026-10-01', close=100, volume=10):
    return {'date': day, 'close': close, 'volume': volume}


def reject(rows, reason, context=None):
    source = deepcopy(rows)
    out = fm.inspect_bars(rows, context)
    check(not out['valid'], reason)
    check(rows == source, reason + ': input preserved')
    try:
        fm.calculate({'bars': rows, 'bar_context': context})
    except (ValueError, TypeError, OverflowError):
        check(True, reason + ': calculation refuses same bad input')
    else:
        check(False, reason + ': bad input reached indicators')


context = {'price_basis': 'raw', 'exchange': 'TWSE', 'source_url': 'https://fixture.invalid/prices',
           'expected_sessions': ['2026-10-01', '2026-10-02'], 'calendar_source_url': 'https://fixture.invalid/calendar'}
base = [row(), row('2026-10-02', 101)]
out = fm.inspect_bars(base, context)
check(out['valid'] and not out['summary']['requires_review'], 'complete supplied context, not independent source verification')
check(out['summary']['input_count'] == 2 and out['summary']['output_count'] == 2, 'first row retained')
check(out['normalized_bars'] is None and not out['changes'], 'default is audit only')
reject(base[::-1], 'descending input rejected')
reject([base[0], base[0]], 'strict duplicate dates rejected')
for bad in [None, [], {}, [None], [dict(close=1)], [row('20261001')], [row('2026-02-30')], [row('2026-10-01T00:00:00Z')], [row(123)]]:
    reject(bad, 'invalid date/shape ' + repr(bad))
for field, values in [('close', [0, -1, True, '100', None, float('inf')]), ('volume', [-1, True, '10', float('inf')])]:
    for value in values:
        reject([dict(row(), **{field: value})], 'invalid ' + field + ' ' + repr(value))
for update in [{'open': 100}, {'open': 100, 'high': 99, 'low': 90}, {'open': 100, 'high': 110, 'low': 101},
               {'open': 100, 'high': float('inf'), 'low': 90}, {'open': True, 'high': 100, 'low': 100}]:
    reject([dict(row(), **update)], 'OHLC rejects invalid or partial fields')
flat = dict(row(volume=0), open=100, high=100, low=100)
for volume, kind in [(None, 'volume_missing'), (0, 'zero_volume_flat_bar')]:
    bars = [dict(flat, volume=volume)];before=deepcopy(bars);x=fm.inspect_bars(bars, context)
    check(x['valid'] and kind in kinds(x) and bars == before and x['summary']['output_count'] == 1, 'missing vs zero retained separately')
x=fm.inspect_bars([row()], {})
check({'price_basis_unknown', 'calendar_not_supplied', 'source_url_missing', 'exchange_missing'} <= kinds(x), 'missing context stays explicit')
reject([dict(flat, price_basis='raw')], 'mixed OHLC/close basis rejected', dict(context, close_basis='split_adjusted'))
reject([row(), dict(row('2026-10-02'), price_basis='total_return_adjusted')], 'mixed row basis rejected', context)
reject([row()], 'invalid price basis', dict(context, price_basis='invented'))
for bad in [[], {}, None, True]:
    reject(base, 'invalid context price basis type',dict(context,price_basis=bad))
for bad in [[], {}, True]:
    x=fm.inspect_bars(base,dict(context,calendar_source_url=bad))
    check(x['valid'] and 'calendar_source_missing' in kinds(x),'invalid calendar attribution stays unverified')
# A known holiday absent from supplied sessions is not a missing trading session.
x=fm.inspect_bars([row('2026-10-08'),row('2026-10-12')],dict(context,expected_sessions=['2026-10-08','2026-10-12']))
check('missing_expected_sessions' not in kinds(x), 'calendar gap is not automatically suspension')
x=fm.inspect_bars([row('2026-10-02')], context)
check(next(i for i in x['issues'] if i['kind']=='missing_expected_sessions')['dates']==['2026-10-01'], 'missing boundary session retained in diagnosis')
x=fm.inspect_bars([row('2026-10-01'),row('2026-10-03')],context)
check({'missing_expected_sessions','outside_supplied_calendar'} <= kinds(x), 'source vs supplied calendar differences, no auto deletion')
for expected in [[], ['2026-10-02','2026-10-01'], ['2026-10-01']*2, ['bad']]:
    reject(base, 'invalid supplied calendar',dict(context,expected_sessions=expected))
# Explicit normalization records mutations in output and never changes raw input.
raw = [base[1],base[0],deepcopy(base[0])];before=deepcopy(raw);x=fm.inspect_bars(raw,context,normalize=True)
check(x['valid'] and x['normalized_bars']==base and raw==before, 'explicit normalization only sorts/deduplicates output')
check([a['kind'] for a in x['changes']]==['sort_dates','remove_identical_duplicate'], 'auditable change reasons')
x=fm.inspect_bars([row(),row(close=101)],context,normalize=True)
check(not x['valid'] and x['normalized_bars'] is None, 'conflicting duplicate refused, no winner selected')
for threshold, closes, expected_flags in [(100,[100,200],0),(100,[100,201],1),(100,[100,500],1),(40,[100,141,80],2)]:
    bars=[row((date(2026,10,1)+timedelta(days=i)).isoformat(),v) for i,v in enumerate(closes)]
    x=fm.inspect_bars(bars,dict(context,jump_threshold_pct=threshold))
    flags=[i for i in x['issues'] if i['kind']=='large_price_change']
    check(x['valid'] and len(flags)==expected_flags and x['summary']['output_count']==len(bars), 'percent units/boundaries; neither tail event nor history deleted')
    if closes==[100,500]:check(flags[0]['return_pct']==400 and flags[0]['threshold_pct']==100,'100 means 100 percent, not 10000 percent')
for bad in [True,0,-1,'100',float('inf')]:reject(base,'invalid diagnostic threshold',dict(context,jump_threshold_pct=bad))
# Existing close-only indicators retain exact simple independent results.
bars=[row((date(2025,1,1)+timedelta(days=i)).isoformat(),100,0) for i in range(240)]
x=fm.calculate({'bars':bars})
check(x['technical']['count']==240 and x['technical']['sma20']==100 and x['technical']['rsi14']==50,'close-only SMA/RSI unchanged')
check(x['technical']['relative_volume20'] is None and x['technical']['volume_sma20']==0,'zero denominator not fabricated')
bars[-1]['volume']=None;x=fm.calculate({'bars':bars})
check(x['technical']['relative_volume20'] is None and x['technical']['volume_sma20'] is None,'missing volume never becomes zero')
check('240' in x['technical']['warmup_note'],'240-bar text matches research rule')
# Real public command, with immutable stdin and no source file rewrite.
for argv,payload,code in [([],{'bars':base},0),([],{'bars':base[::-1]},2),(['--normalize'],{'bars':base[::-1]},0)]:
    p=subprocess.run([sys.executable,str(ROOT/'scripts/bar_audit.py')]+argv,input=json.dumps(payload),capture_output=True,text=True)
    result=json.loads(p.stdout);check(p.returncode==code and result['valid']==(code==0),'public audit CLI '+repr(argv))
for payload in ['{"bars":[],"bars":[]}','{"bars":[{"date":"2026-10-01","close":NaN}]}']:
    p=subprocess.run([sys.executable,str(ROOT/'scripts/bar_audit.py')],input=payload,capture_output=True,text=True)
    check(p.returncode==2 and not json.loads(p.stdout)['valid'],'CLI duplicate/nonfinite JSON rejection')
for payload in ['{"bars":[],"bars":[]}', '{"bars":[{"date":"2026-10-01","date":"2026-10-02","close":100}]}']:
    p=subprocess.run([sys.executable,str(ROOT/'scripts/finance_math.py')],input=payload,capture_output=True,text=True)
    check(p.returncode==2 and 'duplicate JSON key' in p.stderr,'finance CLI uses same strict JSON boundary')
print(json.dumps({'passed':True,'checks':count,'scope':'synthetic input validation, explicit normalization, diagnostic units/calendar, unchanged indicators and CLI; no external data verification or returns backtest'}))
