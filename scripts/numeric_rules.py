"""Pure numeric gates/subtype thresholds; all evidence and calendars are supplied offline."""
from datetime import date
from fractions import Fraction


def f(x): return None if x is None else Fraction(str(x))


def premium_score(mean, maximum, cross_border=False):
    if mean is None or maximum is None: return None
    lo_mean, lo_max, hi_mean, hi_max = (Fraction('0.5'),Fraction('1.5'),Fraction('1.5'),4) if cross_border else (Fraction('0.3'),1,1,3)
    return 2 if f(mean)<=lo_mean and f(maximum)<=lo_max else 0 if f(mean)>hi_mean or f(maximum)>hi_max else 1


def active_score(excess):
    return None if excess is None else 2 if excess>=0 else 1 if excess>=-2 else 0


def full_years(start, end, years=1):
    if not start or not end or years<1:return False
    start,end=date.fromisoformat(start),date.fromisoformat(end)
    try:anniversary=start.replace(year=start.year+years)
    except ValueError:anniversary=start.replace(year=start.year+years,day=28)
    return (anniversary-end).days<=1 and end>=start


def gate_2(point, kind, sample_ok):
    current,lo,mid,hi,pct,down=(f(point[k]) for k in ('current','low','median','high','percentile_pct','downside_pct'))
    method='percentile' if pct is not None else 'linear_band_approximation'
    valid_band=all(x is not None for x in (current,lo,mid,hi)) and lo<=mid<=hi and lo<hi
    top=(pct>=80 if pct is not None else current>=lo+Fraction(4,5)*(hi-lo)) if valid_band else False
    if kind=='bond_yield':
        # Credit/maturity comparability is a separate, manually verified prerequisite.
        if down is not None and down>30:signal='red'
        elif not point['comparable'] or not valid_band or down is None:signal='unknown'
        elif current>mid and sample_ok and down<=15:signal='green'
        else:signal='yellow'
    else:
        if (point['comparable'] and valid_band and (current>hi or top)) or (down is not None and down>30):signal='red'
        elif not point['comparable'] or not valid_band or down is None:signal='unknown'
        elif current<mid and sample_ok and (kind=='etf_equity_multiple' or down<=15):signal='green'
        else:signal='yellow'
    return {'signal':signal,'downside_pct':float(down) if down is not None else None,'band_method':method}


def gate_6(point, is_etf):
    close,s20,s60,s120,rsi,macd,signal,premium=(f(point[k]) for k in ('close','sma20','sma60','sma120','rsi14','macd','macd_signal','premium_pct'))
    deviation=(close/s20-1)*100 if close is not None and s20 is not None else None
    reference=s120 if s120 is not None else s60
    weak=close is not None and reference is not None and close<reference
    red=(rsi is not None and rsi>75) or (deviation is not None and deviation>15) or (weak and macd is not None and signal is not None and macd<signal)
    if is_etf and premium is not None and premium>3:red=True
    if red:result='red'
    elif any(x is None for x in (close,s20,s60,rsi)) or (weak and (macd is None or signal is None)) or (is_etf and premium is None):result='unknown'
    elif close>s60 and 40<=rsi<65 and abs(deviation)<8:result='green'
    else:result='yellow'
    if is_etf and premium is not None and premium>1 and result=='green':result='yellow'
    return {'signal':result,'deviation_pct':float(deviation) if deviation is not None else None,
            'reference':'sma120' if s120 is not None else 'sma60'}


def gate_7(point):
    old_price,new_price,old,new=(f(point[k]) for k in ('previous_price','current_price','previous_earnings','current_earnings'))
    p=(new_price/old_price-1)*100 if old_price is not None and new_price is not None else None
    g=(new/old-1)*100 if old is not None and old>0 and new is not None else None
    if point['quality_issue_confirmed']:signal='red'
    elif not point['comparable'] or point['near_zero_base'] or p is None or g is None:signal='unknown'
    elif g>0:signal='green' if p<=g else 'yellow' if p<=2*g else 'red'
    else:signal='red' if (g==0 and p>0) or (g<0 and p>=0) else 'yellow'
    return {'signal':signal,'price_return_pct':float(p) if p is not None else None,'earnings_growth_pct':float(g) if g is not None else None}


def adverse(results):
    return min((x['signal'] for x in results),key={'red':0,'unknown':1,'yellow':2,'green':3}.get)
