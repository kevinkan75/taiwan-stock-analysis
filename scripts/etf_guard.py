#!/usr/bin/env python3
"""Offline ETF format, arithmetic and score validation; external evidence remains manual."""
import argparse
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import report_checks

import snapshot_guard as stock
from rules_core import (ETF_MODEL_VERSION, ETF_RELEASE_PROFILE, ETF_HTML_PROFILE, ETF_ANNUAL_PROFILE, ETF_CLAIM_PROFILE, ETF_REVIEW_PROFILE, ETF_ARCHIVED_PROFILE, ETF_PREVIOUS_PROFILE, ETF_DIMENSIONS,
    ETF_QUALIFIERS, ETF_COVERAGE_MIN, dimension_result, weighted_total, rounded,
    finite, close, timestamp, rule_headers)
from numeric_rules import premium_score, active_score, full_years

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'etf_structure_arithmetic_scores'
SCOPE_LINE = 'ETF驗證範圍：格式、算術及評分機械規則；來源與定性證據仍人工核對。'


def fraction(value):
    if not finite(value): raise ValueError('finite numeric input required')
    return Fraction(str(value))


def concentration_score(s):
    c = s['concentration']
    a, b = c['max_weight_pct'], c['top10_weight_pct']
    if a is None or b is None: return None
    low, high = (70, 90) if s['subtype'] == '產業／主題型' else (60, 80)
    return 0 if a > 40 or b > high else 1 if a > 25 or b > low else 2


def earnings_score(s):
    e = s['earnings_support_inputs']
    if s['subtype'] == '債券型': return None  # subtype-specific evidence stays manual
    if e['basis'] != 'comparable' or any(e[k] is None for k in ('previous_earnings','current_earnings','nav_return_pct')):
        return None
    old, new, nav = (fraction(e[k]) for k in ('previous_earnings','current_earnings','nav_return_pct'))
    if old <= 0: return None
    if e['low_base_or_one_off']: return 0
    growth = (new / old - 1) * 100
    return (2 if nav <= growth else 1 if nav <= 2 * growth else 0) if growth > 0 else (0 if nav > 0 else 1)


def arithmetic(name, metric):
    """Interpret a small input vocabulary; never evaluate formula strings."""
    i = metric['inputs']
    if not isinstance(i, dict): raise ValueError('calculated metric requires input object')
    if name == 'premium_discount_pct':
        price, nav = fraction(i['price']), fraction(i['nav'])
        if price <= 0 or nav <= 0: raise ValueError('positive price and NAV required')
        return (price / nav - 1) * 100, None
    if name == 'yield_ttm_pct':
        paid, price = fraction(i['distribution_ttm_per_unit']), fraction(i['price'])
        if paid < 0 or price <= 0: raise ValueError('nonnegative actual paid distribution and positive price required')
        return paid / price * 100, None
    if name == 'weighted_pe':
        entries = i['constituents']
        if not isinstance(entries, list) or not entries: raise ValueError('constituents required')
        ids = [x['id'] for x in entries]
        if len(set(ids)) != len(ids): raise ValueError('duplicate constituent')
        covered, ey, total = Fraction(0), Fraction(0), Fraction(0)
        for x in entries:
            weight = fraction(x['weight_pct'])
            if not 0 <= weight <= 100: raise ValueError('weight outside 0..100')
            total += weight
            if x['pe_ttm'] is None: continue
            pe = fraction(x['pe_ttm'])
            if pe == 0: raise ValueError('zero constituent PE cannot be inverted')
            covered += weight
            ey += weight / pe  # Losses contribute a negative earnings yield.
        if total > 100: raise ValueError('constituent weights exceed 100%')
        if covered < 70: return None, covered
        return (covered / ey if ey > 0 else None), covered
    if name in ('premium_abs_mean20_pct', 'premium_abs_max20_pct'):
        values = i['daily_premium_pct']
        if not isinstance(values, list) or len(values) != 20: raise ValueError('exactly 20 same-basis daily observations required')
        values = [abs(fraction(x)) for x in values]
        return (sum(values) / 20 if name == 'premium_abs_mean20_pct' else max(values)), None
    if name == 'tracking_difference_pct':
        periods = i['annual_periods']
        if not isinstance(periods, list) or not 1 <= len(periods) <= 3: raise ValueError('one to three complete annual periods required')
        result, previous = [], None
        for p in periods:
            start, end = date.fromisoformat(p['start']), date.fromisoformat(p['end'])
            if not 364 <= (end - start).days <= 366 or (previous and start <= previous):
                raise ValueError('complete non-overlapping annual periods in order required')
            previous = end
            if p['total_return'] is not True or p['fund_currency'] != p['index_currency']:
                raise ValueError('total returns in matching currencies required')
            result.append(fraction(p['fund_return_pct']) - fraction(p['index_return_pct']))
        return sum(result) / len(result), None
    raise ValueError('unsupported calculated metric; retain reported/missing status or define a new model')


def semantic_errors(s):
    errors = []
    profile=ETF_ARCHIVED_PROFILE if s['model_version']=='etf-1.1' else ETF_RELEASE_PROFILE
    if (s['skill_version'],s['rule_version'],s['validator_version']) not in ({profile,ETF_HTML_PROFILE,ETF_ANNUAL_PROFILE,ETF_PREVIOUS_PROFILE,ETF_REVIEW_PROFILE,ETF_CLAIM_PROFILE} if s['model_version']==ETF_MODEL_VERSION else {profile}):
        errors.append('unsupported ETF release profile')
    cutoff, analysis = timestamp(s['data_cutoff_at']), timestamp(s['analysis_at'])
    if cutoff > analysis: errors.append('cutoff after analysis')
    if s['quote_at'] and timestamp(s['quote_at']) > cutoff: errors.append('quote after cutoff')
    if s['holdings_at'] and date.fromisoformat(s['holdings_at']) > cutoff.date(): errors.append('holdings after cutoff')
    known = {x['url'] for x in s['sources']}
    if len(known) != len(s['sources']): errors.append('duplicate source URLs')
    def urls(values, label, required=False):
        if required and not values: errors.append(label + ': source required')
        if any(x not in known for x in values): errors.append(label + ': unregistered source')
    for x in s['sources']:
        if timestamp(x['retrieved_at']) > analysis: errors.append('source retrieved after analysis')
        p = x['published_at']
        if p and (timestamp(p) > cutoff if 'T' in p else date.fromisoformat(p) > cutoff.date()): errors.append('source published after cutoff')
    urls(s['fund']['source_urls'],'fund',True)
    if (s['subtype'] == '債券型') != (s['fund']['underlying_asset'] == 'bond'): errors.append('subtype and underlying asset disagree')
    for dim,(weight,checks) in ETF_DIMENSIONS.items():
        group=s['scores'][dim]
        if [x['check'] for x in group['items']] != checks: errors.append(dim + ': fixed checks in canonical order required')
        if not close(group['weight'],float(weight)): errors.append(dim + ': fixed weight required')
        for x in group['items']: urls(x['source_urls'],x['check'],x['score'] is not None)
    items={x['check']:x for group in s['scores'].values() for x in group['items']}
    if set(items)!=set(check for _,checks in ETF_DIMENSIONS.values() for check in checks): return errors
    inception=s['fund']['inception_date']
    if inception and date.fromisoformat(inception)>cutoff.date(): errors.append('fund inception after cutoff')
    if items['tracking_quality']['score'] is not None and (not inception or (cutoff.date()-date.fromisoformat(inception)).days<365):
        errors.append('tracking_quality: a complete year since inception required')
    statuses={}
    for x in s['validation']:
        if x['check'] in statuses: errors.append('duplicate validation check')
        statuses[x['check']]=x['status']; urls(x.get('source_urls',[]),x['check'],x['status']!='fail')
    for k in ETF_QUALIFIERS:
        if statuses.get(k)!=s['eligibility'][k]: errors.append(k + ': matching validation status required')
    metrics=s['metrics']
    for name,m in metrics.items():
        urls(stock.urls(m['source_url']),name,m['value'] is not None or m['value_status']=='calculated')
        if timestamp(m['retrieved_at']) > analysis: errors.append(name + ': retrieved after analysis')
        if m['as_of'] and (timestamp(m['as_of'])>cutoff if 'T' in m['as_of'] else date.fromisoformat(m['as_of'])>cutoff.date()): errors.append(name + ': value after cutoff')
        if m['value_status'] in ('missing','not_applicable') and m['value'] is not None: errors.append(name + ': missing must be null')
        if m['value_status'] in ('reported','estimated') and m['value'] is None: errors.append(name + ': known status requires value')
        if m['value_status']=='calculated':
            try:
                expected,covered=arithmetic(name,m)
                if not close(m['value'],float(expected) if expected is not None else None): errors.append(name + ': arithmetic mismatch')
                for key in ('price','nav','distribution_ttm_per_unit'):
                    if key in m['inputs'] and not close(m['inputs'][key],metrics[key]['value']): errors.append(name + ': input '+key+' differs from metric')
                if covered is not None:
                    for check in ('band_position','relative_valuation'):
                        if items[check]['score'] is not None and not close(s['coverage'][check]['weight_pct'],float(covered)):
                            errors.append(check + ': PE constituent coverage mismatch')
                if name=='tracking_difference_pct':
                    for p in m['inputs']['annual_periods']:
                        if date.fromisoformat(p['end'])>cutoff.date() or p['fund_currency']!=s['security']['currency']:
                            errors.append(name + ': period/currency mismatch')
            except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError) as e: errors.append(name + ': ' + str(e))
        if name in ('premium_discount_pct','yield_ttm_pct','tracking_difference_pct','premium_abs_mean20_pct','premium_abs_max20_pct') and (m['unit']!='%' or m['currency'] is not None):
            errors.append(name + ': percentage-point unit % and null currency required')
        if name=='weighted_pe' and (m['unit']!='倍' or m['currency'] is not None): errors.append('weighted_pe: multiple unit and null currency required')
    for name in ('price','nav','distribution_ttm_per_unit'):
        m=metrics[name]
        if m['value'] is not None and (m['value'] < 0 or (name!='distribution_ttm_per_unit' and m['value']==0)):
            errors.append(name + ': invalid per-unit value')
        if m['value'] is not None and m['currency']!=s['security']['currency']: errors.append(name + ': currency mismatch')
    if metrics['price']['value'] is not None and metrics['nav']['value'] is not None:
        a,b=metrics['price']['as_of'],metrics['nav']['as_of']
        if not a or not b or a[:10]!=b[:10]: errors.append('price/NAV: same trading day required')
        if metrics['premium_discount_pct']['value'] is not None:
            expected=(fraction(metrics['price']['value'])/fraction(metrics['nav']['value'])-1)*100 if metrics['nav']['value']>0 else None
            if expected is None or not close(metrics['premium_discount_pct']['value'],float(expected)): errors.append('premium_discount_pct: differs from same-day price/NAV')
    if metrics['yield_ttm_pct']['value'] is not None:
        paid,price=metrics['distribution_ttm_per_unit']['value'],metrics['price']['value']
        if paid is None or price is None or price<=0 or not close(metrics['yield_ttm_pct']['value'],float(fraction(paid)/fraction(price)*100)):
            errors.append('yield_ttm_pct: actual paid TTM distribution/price required')
        if metrics['distribution_ttm_per_unit']['actual_or_estimate']!='actual': errors.append('yield_ttm_pct: distributions must be actual, not annualized estimates')
    if metrics['weighted_pe']['value'] is not None and metrics['weighted_pe']['value']<=0: errors.append('weighted_pe: nonpositive aggregate valuation must remain null')
    if s['eligibility']['quote_verified']!='fail' and (not s['quote_at'] or metrics['price']['value'] is None): errors.append('verified quote requires price and timestamp')
    if s['quote_at'] and metrics['price']['as_of'] and s['quote_at'][:10]!=metrics['price']['as_of'][:10]: errors.append('price date differs from quote timestamp')
    if s['eligibility']['holdings_financials_verified']=='pass' and not s['holdings_at']: errors.append('verified holdings require date')
    for check,minimum in ETF_COVERAGE_MIN.items():
        c=s['coverage'][check];urls(c['source_urls'],'coverage.'+check,c['weight_pct'] is not None)
        if c['method'] in ('missing','not_applicable') and c['weight_pct'] is not None: errors.append(check+': missing coverage must be null')
        if c['method']=='reported' and c['weight_pct'] is None: errors.append(check+': reported coverage required')
        if c['method']=='calculated':
            rows=c['contributors'];ids=[x['id'] for x in rows]
            total=sum((fraction(x['weight_pct']) for x in rows),Fraction(0))
            covered=sum((fraction(x['weight_pct']) for x in rows if x['data_available']),Fraction(0))
            if not rows or len(ids)!=len(set(ids)) or total>100: errors.append(check+': invalid coverage contributors')
            if not close(c['weight_pct'],float(covered)): errors.append(check+': coverage arithmetic mismatch')
        if (c['weight_pct'] is None or c['weight_pct']<minimum) and items[check]['score'] is not None:
            errors.append(check+': insufficient weight coverage; score must be null')
    if items['relative_valuation']['score'] is not None and s['coverage']['relative_valuation']['weight_pct'] is not None and s['coverage']['relative_valuation']['weight_pct']<80 and s['eligibility']['valuation_supported']=='pass':
        errors.append('relative_valuation: low coverage requires limited/fail valuation qualification')
    h=s['valuation_history'];urls(h['source_urls'],'valuation_history',h['method']!='missing')
    history_ok=(h['method']=='monthly_series' and h['observations']>=36) or (h['method']=='published' and h['years']>=3)
    if items['band_position']['score'] is not None and not history_ok: errors.append('band_position: 36 monthly observations or published 3-year band required')
    c=s['concentration'];urls(c['source_urls'],'concentration',c['method']!='missing')
    ids=[x['id'] for x in c['holdings']];weights=sorted((fraction(x['weight_pct']) for x in c['holdings']),reverse=True)
    if len(set(ids))!=len(ids) or sum(weights)>100: errors.append('concentration: duplicate holdings or weights exceed 100%')
    if c['holdings_complete'] and (not weights or not close(float(sum(weights)),100)): errors.append('concentration: complete holdings must total 100%')
    if c['method']=='missing':
        if c['max_weight_pct'] is not None or c['top10_weight_pct'] is not None: errors.append('concentration: missing values must be null')
    else:
        if c['max_weight_pct'] is None or c['top10_weight_pct'] is None or not c['as_of']: errors.append('concentration: weights and date required')
        elif c['max_weight_pct']>c['top10_weight_pct']: errors.append('concentration: top ten cannot be smaller than maximum')
        if c['as_of']!=s['holdings_at']: errors.append('concentration: date differs from holdings')
    if c['method']=='calculated':
        if not c['holdings_complete']: errors.append('concentration: exact calculation requires complete holdings')
        if not close(c['max_weight_pct'],float(max(weights)) if weights else None) or not close(c['top10_weight_pct'],float(sum(weights[:10]))): errors.append('concentration: arithmetic mismatch')
    if c['method']=='reported' and weights and c['max_weight_pct'] is not None and c['top10_weight_pct'] is not None:
        if c['max_weight_pct']<float(weights[0]) or c['top10_weight_pct']<float(sum(weights[:10])): errors.append('concentration: published values below supplied holdings lower bounds')
        if c['holdings_complete'] and (not close(c['max_weight_pct'],float(weights[0])) or not close(c['top10_weight_pct'],float(sum(weights[:10])))):
            errors.append('concentration: published values disagree with complete holdings')
    pe_metric=metrics['weighted_pe']
    if pe_metric['value_status']=='calculated' and c['method']!='missing' and c['max_weight_pct'] is not None and c['top10_weight_pct'] is not None:
        try:
            pe_weights=sorted((fraction(x['weight_pct']) for x in pe_metric['inputs']['constituents']),reverse=True)
            if pe_weights:
                if c['max_weight_pct']<float(pe_weights[0]) or c['top10_weight_pct']<float(sum(pe_weights[:10])):
                    errors.append('concentration: below PE constituent weight lower bounds')
                if close(float(sum(pe_weights)),100) and (not close(c['max_weight_pct'],float(pe_weights[0])) or not close(c['top10_weight_pct'],float(sum(pe_weights[:10])))):
                    errors.append('concentration: disagrees with complete PE constituent weights')
        except (ValueError,TypeError,KeyError): pass  # Input errors are already reported by arithmetic().
    if items['concentration']['score']!=concentration_score(s): errors.append('concentration: score disagrees with subtype thresholds')
    e=s['earnings_support_inputs'];urls(e['source_urls'],'earnings_support_inputs',e['basis']!='unconfirmed')
    if s['subtype']=='債券型':
        if e['basis']!='bond_manual': errors.append('bond earnings_support requires manual duration/rate basis')
        if metrics['weighted_pe']['value'] is not None: errors.append('bond valuation cannot use equity weighted PE')
    elif items['earnings_support']['score'] is not None and items['earnings_support']['score']!=earnings_score(s): errors.append('earnings_support: original earnings/NAV inputs or score inconsistent')
    if s['model_version']==ETF_MODEL_VERSION:
        errors+=subtype_errors(s,items,urls)
    if s['major_risk']['confirmed']: urls(s['major_risk']['source_urls'],'major_risk',True)
    t=s['technical'];urls(t['source_urls'],'technical',t['status']=='computed')
    if t['status']=='computed':
        if t['observation_count']<240 or t['indicators'] is None or not t['as_of'] or not t['adjustment']: errors.append('technical: 240 verified observations and adjustment basis required')
        elif any(t['indicators'][k] is None for k in ('sma20','sma60','rsi14','macd','macd_signal')): errors.append('technical: required indicator missing')
    elif t['indicators'] is not None: errors.append('technical: uncomputed indicators must be null')
    if t['as_of'] and date.fromisoformat(t['as_of'])>cutoff.date(): errors.append('technical after cutoff')
    return errors


def subtype_errors(s,items,urls):
    errors=[];x=s['subtype_inputs'];p=x['premium'];a=x['active_return'];h=x['fx_hedging'];b=x['bond']
    if s['subtype']=='主動式' and not x['active_management']:errors.append('subtype: active management flag required')
    if s['subtype']=='跨境股票型' and not x['cross_border']:errors.append('subtype: cross-border flag required')
    premium_ready=p['observations']==20 and p['same_basis'] and p['mean_abs20_pct'] is not None and p['max_abs20_pct'] is not None
    expected=premium_score(p['mean_abs20_pct'],p['max_abs20_pct'],x['cross_border']) if premium_ready else None
    if items['premium_discount']['score']!=expected:errors.append('premium_discount: subtype numeric score mismatch/missing inputs')
    urls(p['source_urls'],'subtype.premium',premium_ready)
    if p['mean_abs20_pct'] is not None and p['max_abs20_pct'] is not None and p['mean_abs20_pct']>p['max_abs20_pct']:errors.append('premium: mean exceeds maximum')
    for name,value in [('premium_abs_mean20_pct',p['mean_abs20_pct']),('premium_abs_max20_pct',p['max_abs20_pct'])]:
        m=s['metrics'].get(name)
        if m and m['value'] is not None and not close(m['value'],value):errors.append(name+': subtype input differs from metric')
    if x['cross_border']:
        urls(h['source_urls'],'subtype.fx_hedging',h['status'] in ('hedged','unhedged') or h['adverse_structure_confirmed'])
        score=items['structural_risk']['score']
        if h['status']=='not_applicable':errors.append('cross-border: explicit hedging status required')
        if h['adverse_structure_confirmed'] and score!=0:errors.append('structural_risk: confirmed adverse structure must score zero')
        elif not h['adverse_structure_confirmed'] and h['status']=='unknown' and score is not None:errors.append('structural_risk: unknown hedge must remain null')
        if h['status']=='unhedged' and score is not None and score>1:errors.append('structural_risk: unhedged cross-border cap is one')
    elif h['status']!='not_applicable':errors.append('non-cross-border: hedging not applicable')
    if x['active_management']:
        ready=(a['complete_years']>=1 and a['same_currency'] and a['total_return'] and a['net_of_fees']
               and full_years(a['start'],a['end'],a['complete_years']))
        if a['end'] and date.fromisoformat(a['end'])>timestamp(s['data_cutoff_at']).date():errors.append('active return: end after cutoff')
        if a['start'] and s['fund']['inception_date'] and a['start']<s['fund']['inception_date']:errors.append('active return: before inception')
        expected=active_score(a['net_annual_excess_pct']) if ready else None
        if items['tracking_quality']['score']!=expected:errors.append('tracking_quality: active net annual excess score mismatch/missing inputs')
        urls(a['source_urls'],'subtype.active_return',expected is not None)
        if expected is not None:
            m=s['metrics'].get('tracking_difference_pct')
            if not m or not close(m['value'],a['net_annual_excess_pct']):errors.append('active return: matching tracking/excess metric required')
    if s['subtype']=='債券型':
        urls(b['source_urls'],'subtype.bond',any(b[k] is not None for k in ('modified_duration','current_ytm_pct','credit_spread_pct')))
        for check,assessment in b['manual_assessments'].items():
            urls(assessment['source_urls'],'bond.manual.'+check,assessment['status']=='checked')
            if items[check]['score'] is not None and assessment['status']!='checked':errors.append('bond.'+check+': explicit manual assessment required')
        if b['approx_price_change_pct'] is not None:
            if b['modified_duration'] is None or b['yield_shift_pct'] is None or not close(b['approx_price_change_pct'],float(-fraction(b['modified_duration'])*fraction(b['yield_shift_pct']))):errors.append('bond: duration approximation mismatch')
        if b['credit_spread_pct'] is not None:
            if b['current_ytm_pct'] is None or b['benchmark_ytm_pct'] is None or b['credit_maturity_comparable'] is not True or not close(b['credit_spread_pct'],float(fraction(b['current_ytm_pct'])-fraction(b['benchmark_ytm_pct']))):errors.append('bond: comparable yield spread mismatch')
        if items['band_position']['score'] is not None and b['current_ytm_pct'] is None:errors.append('bond band_position: current yield required')
        if items['relative_valuation']['score'] is not None and b['credit_spread_pct'] is None:errors.append('bond relative_valuation: comparable spread required')
        if items['earnings_support']['score'] is not None and (b['approx_price_change_pct'] is None or b['rate_trend']=='unknown'):errors.append('bond earnings_support: duration scenario and observed rate direction required')
    return errors


def derive(s, overrides=None, confidence_rules=True):
    raw,groups={},{}
    for dim,(weight,_) in ETF_DIMENSIONS.items():
        values=[(overrides or {}).get(x['check'],x['score']) for x in s['scores'][dim]['items']]
        if s['model_version']==ETF_MODEL_VERSION and dim=='risk' and s['subtype_inputs']['cross_border']:
            h=s['subtype_inputs']['fx_hedging'];index=ETF_DIMENSIONS['risk'][1].index('structural_risk')
            if values[index] is not None and (h['status']=='unhedged' or h['adverse_structure_confirmed']):values[index]=min(values[index],0 if h['adverse_structure_confirmed'] else 1)
        raw[dim],groups[dim]=dimension_result(values,weight)
    coverage=sum(x['coverage'] for x in groups.values());available=sum(x is not None for x in raw.values())
    flags={k:s['eligibility'][k]!='fail' for k in ETF_QUALIFIERS}
    flags['quote_is_current']=s['analysis_scope']=='historical' or flags['quote_is_current']
    eligible=all(flags.values())
    formal=eligible and available==5 and coverage>=12
    provisional=eligible and raw['valuation'] is not None and available>=4 and coverage>=10
    cap='unknown' if concentration_score(s) is None else 'yellow' if concentration_score(s)==0 else 'none'
    fx_unknown=(s['model_version']==ETF_MODEL_VERSION and s['subtype_inputs']['cross_border']
                and s['subtype_inputs']['fx_hedging']['status']=='unknown'
                and not s['subtype_inputs']['fx_hedging']['adverse_structure_confirmed'])
    overall={'signal':'unknown','score':None,'raw_score':None,'provisional':False,'confidence':None,
             'concentration_cap':cap,'reason':'資料／覆蓋／資格門檻未齊；覆蓋%d/15'%coverage}
    if s['major_risk']['confirmed']:
        overall.update(signal='major_risk',reason='已確認重大風險優先：'+s['major_risk']['reason'])
    elif formal or provisional:
        total=weighted_total(raw,{k:v[0] for k,v in ETF_DIMENSIONS.items()},normalize=not formal)
        signal='yellow'
        if total<40 or raw['valuation']<40 or (raw['risk'] is not None and raw['risk']<40): signal='red'
        elif (available==5 and total>=75 and raw['valuation']>=75 and raw['risk']>=75
              and raw['instrument']>=40 and raw['tradability']>=40 and cap=='none'): signal='green'
        overall.update(signal=signal,score=rounded(total),raw_score=float(total),provisional=not formal,
                       confidence='high' if formal else 'medium' if available==5 and coverage>=12 else 'low',
                       reason=('正式' if formal else '暫定')+'；覆蓋%d/15；集中度上限%s'%(coverage,cap))
        if fx_unknown:
            if overall['signal']=='green':overall['signal']='yellow'
            overall['reason']+='；跨境避險未核對，整體最高yellow'
    result={'scores':groups,'overall':overall,'technical_signal':stock.technical_light(s['technical'])}
    if confidence_rules:
        cases=[]
        if overall['score'] is not None:
            for dim,group in s['scores'].items():
                for item in group['items']:
                    n=item['score']
                    if n is None or not (dim=='valuation' or any(x in item['reason'] for x in ('需打折','待確認','近似','邊界','有限制'))): continue
                    for changed in (n-1,n+1):
                        if not 0<=changed<=2: continue
                        other=derive(s,{item['check']:changed},False)['overall']['signal']
                        cases.append({'dimension':dim,'check':item['check'],'from_score':n,'to_score':changed,'signal':other,'changed':other!=overall['signal']})
        fragile=any(x['changed'] for x in cases)
        result['sensitivity']={'checked':overall['score'] is not None,'fragile':fragile,'confidence_cap':'medium' if fragile else None,'cases':cases}
        if overall['score'] is not None:
            limited=[k for k in ETF_QUALIFIERS if s['eligibility'][k]=='limited' and not(k=='quote_is_current' and s['analysis_scope']=='historical')]
            caps=[overall['confidence']]
            if limited or fragile or cap=='unknown' or fx_unknown: caps.append('medium')
            if len(limited)>=2: caps.append('low');overall['provisional']=True
            overall['confidence']=min(caps,key={'low':0,'medium':1,'high':2}.get)
            overall['reason']+='；資格限制%d項；R6%s；信心%s'%(len(limited),'脆弱' if fragile else '未翻轉',overall['confidence'])
    return result


def validate(s, derive_only=False):
    if isinstance(s,dict) and s.get('model_version')=='etf-1.0':
        return {'valid':False,'scope':'legacy_manual_etf','errors':['Legacy ETF record remains manual; do not backfill or certify it.'],'derived':None}
    filename='etf.schema-1.0.json' if isinstance(s,dict) and s.get('model_version')=='etf-1.1' else 'etf.schema.json'
    schema=json.loads((ROOT/'assets'/filename).read_text(encoding='utf-8'));stock.audit_keywords(schema)
    errors=stock.schema_errors(s,schema,schema)
    if errors:return {'valid':False,'scope':'structure','errors':errors,'derived':None}
    errors+=semantic_errors(s)
    if errors:return {'valid':False,'scope':SCOPE,'errors':errors,'derived':None}
    expected=derive(s)
    if not derive_only and s['rule_version']in report_checks.PROFILE_RULES:
        errors+=report_checks.report_errors(s['report_markdown'],confidence=expected['overall']['confidence'])
    if not derive_only:
        for dim,group in expected['scores'].items():
            for k,v in group.items():
                actual=s['scores'][dim][k]
                if not (close(actual,v) if k in ('weight','raw_score') else actual==v): errors.append(dim+'.'+k+': derived mismatch')
        for k,v in expected['overall'].items():
            if k=='reason':continue
            if not (close(s['overall'][k],v) if k=='raw_score' else stock.equal(s['overall'][k],v)):errors.append('overall.'+k+': derived mismatch')
        if s['sensitivity']!=expected['sensitivity']:errors.append('sensitivity: derived mismatch')
        if s['technical']['signal']!=expected['technical_signal']:errors.append('technical signal mismatch')
        errors+=stock.summary_errors(s)
        errors+=stock.report_result_errors(s,{'derived':expected})
        if rule_headers(s['report_markdown'])!=[s['rule_version']]:errors.append('report: single matching rule header required')
        if s['report_sha256']!=stock.report_hash(s):errors.append('report: hash mismatch')
        if SCOPE_LINE not in s['report_markdown'].splitlines():errors.append('report: explicit ETF validation scope required')
        cap_line='集中度上限：'+{'none':'未觸發','yellow':'🟡','unknown':'待確認'}[expected['overall']['concentration_cap']]
        if cap_line not in s['report_markdown'].splitlines():errors.append('report: concentration cap line mismatch')
    return {'valid':not errors,'scope':SCOPE+'_draft' if derive_only else SCOPE,'errors':errors,'derived':expected,
            'limitation':'Sources, qualitative scores, coverage declarations and subtype evidence remain manually verified.'}


def derived_snapshot(s,result):
    out=deepcopy(s)
    for dim,group in result['derived']['scores'].items():out['scores'][dim].update(group)
    out['overall']=result['derived']['overall'];out['sensitivity']=result['derived']['sensitivity']
    out['technical']['signal']=result['derived']['technical_signal']
    out['validated']=False  # A successful draft cannot certify a final report.
    out['report_sha256']=stock.report_hash(out)
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('--report')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--derive',action='store_true');mode.add_argument('--finalize',action='store_true')
    args=p.parse_args()
    try:
        with open(args.input,encoding='utf-8') as f:s=stock.load_json(f)
        if args.report:s['report_markdown']=Path(args.report).read_text(encoding='utf-8')
        result=validate(s,args.derive)
        output=result
        if result['valid'] and args.derive:output=derived_snapshot(s,result)
        elif result['valid'] and args.finalize:output=deepcopy(s);output['validated']=True
        print(json.dumps(output,ensure_ascii=False,allow_nan=False,indent=2));return 0 if result['valid'] else 2
    except (ValueError,TypeError,KeyError,OSError,OverflowError) as e:
        print(json.dumps({'valid':False,'scope':'input','errors':[str(e)]},ensure_ascii=False));return 2


if __name__=='__main__':sys.exit(main())
