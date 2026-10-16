"""Bind supplied gate numbers to research and derive gates 2, 6 and 7 offline."""
from datetime import date
from fractions import Fraction

from rules_core import close, timestamp
from numeric_rules import gate_2, gate_6, gate_7, adverse

SCOPE_LINE='決策驗證範圍：第2、6、7關數值、研究連動及行動結論；其餘關卡與來源證據仍人工核對。'


def evaluate(s,research):
    errors=[];checks={};is_etf=research['security']['instrument']=='etf'
    is_bond=is_etf and research.get('subtype')=='債券型'
    known={x['url'] for x in s['sources']};cutoff=timestamp(s['data_cutoff_at'])
    price=(research.get('metrics',{}).get('price') or {}).get('value')
    quote_day=timestamp(research['quote_at']).date().isoformat() if research.get('quote_at') else None
    def bind(actual,expected,label):
        if not close(actual,expected):errors.append(label+': differs from referenced research')
    for number in (2,6,7):
        label='gate_%d'%number;n=s['numeric_inputs'][label];point=n['point'];points=[point]+n['alternatives']
        if n['as_of'] and date.fromisoformat(n['as_of'])>cutoff.date():errors.append(label+': after cutoff')
        if any(x not in known for x in n['source_urls']):errors.append(label+': unregistered numeric source')
        numeric=[v for p in points for v in p.values() if isinstance(v,(int,float)) and not isinstance(v,bool)]
        if (numeric or (number==7 and point['quality_issue_confirmed'])) and not n['source_urls']:errors.append(label+': numeric evidence source required')
        if n['origin']=='missing' and (numeric or n['alternatives']):errors.append(label+': missing origin must not retain known numeric inputs')
        if n['quality']=='exact' and n['alternatives']:errors.append(label+': alternatives require approximate/conflicting quality')
        if n['quality'] in ('approximate','conflicting') and not n['alternatives']:errors.append(label+': uncertainty requires explicit numeric alternatives')
        if n['alternatives'] and any(p==point for p in n['alternatives']):errors.append(label+': duplicate uncertainty alternative')
        active=n['origin']!='missing' and n['quality']!='unconfirmed' and n['as_of'] is not None
        results=[]
        if number==2:
            kind='bond_yield' if is_bond else 'etf_equity_multiple' if is_etf else 'stock_multiple'
            if n['kind']!=kind:errors.append(label+': asset-specific valuation kind required')
            valuation_day=research.get('holdings_at') if is_bond else quote_day
            if n['as_of']!=valuation_day:active=False
            sample=n['sample'];sample_ok=(sample['kind']=='monthly_series' and sample['observations']>=36) or (sample['kind']=='published' and sample['years']>=3) or (not is_bond and sample['kind']=='peers' and sample['peers']>=3)
            for p in points:
                if all(p[k] is not None for k in ('low','median','high')) and not p['low']<=p['median']<=p['high']:errors.append(label+': band ordering invalid')
                if not is_bond and any(p[k] is not None and p[k]<=0 for k in ('current','low','median','high')):errors.append(label+': positive multiples required')
                if n['origin']!='missing':bind(p['reference_price'],price,label+'.reference_price')
                existing=(research.get('subtype_inputs',{}).get('bond',{}).get('current_ytm_pct') if is_bond else research.get('metrics',{}).get(n['metric_key'],{}).get('value'))
                if existing is not None and n['origin']!='missing':bind(p['current'],existing,label+'.known_current_metric')
                if kind=='etf_equity_multiple':
                    expected=max(Fraction(0),(1-Fraction(str(p['median']))/Fraction(str(p['current'])))*100) if p['median'] is not None and p['current'] is not None and p['current']>0 else None
                else:
                    expected=max(Fraction(0),(1-Fraction(str(p['scenario_price']))/Fraction(str(p['reference_price'])))*100) if p['scenario_price'] is not None and p['reference_price'] is not None else None
                if not close(p['downside_pct'],float(expected) if expected is not None else None):errors.append(label+': downside arithmetic mismatch')
                results.append(gate_2(p,kind,sample_ok))
            if n['origin']=='research':
                if is_bond:
                    bond=research.get('subtype_inputs',{}).get('bond',{})
                    for p in points:bind(p['current'],bond.get('current_ytm_pct'),label+'.current_yield')
                    if point['comparable'] is not (bond.get('credit_maturity_comparable') is True):errors.append(label+': bond comparability disagrees with research')
                else:
                    metric=research.get('metrics',{}).get(n['metric_key'],{})
                    for p in points:bind(p['current'],metric.get('value'),label+'.current')
                    if not is_etf:
                        band=research.get('valuation',{}).get('band') or {}
                        for p in points:
                            for key in ('low','median','high'):bind(p[key],band.get(key),label+'.'+key)
                        if band.get('current_metric') and band['current_metric']!=n['metric_key']:errors.append(label+': research multiple basis differs')
                        scenario=next((x['model_price'] for x in research['valuation']['scenarios'] if x['label']=='conservative'),None)
                        for p in points:bind(p['scenario_price'],scenario,label+'.conservative_price')
            checks[label]={'signal':adverse(results) if active else 'unknown','cases':results,'sample_sufficient':sample_ok}
        elif number==6:
            sessions=n['recent_sessions'];latest=s['quote_context']['latest_completed_session_at']
            latest_day=timestamp(latest).date().isoformat() if latest else None
            if sessions!=sorted(set(sessions)) or any(date.fromisoformat(x)>cutoff.date() for x in sessions):errors.append(label+': ordered unique completed sessions required')
            if sessions and sessions[-1]!=latest_day:errors.append(label+': recent sessions must end at latest completed session')
            fresh=n['as_of'] in sessions and latest_day is not None
            for p in points:results.append(gate_6(p,is_etf))
            for p in points:
                if n['origin']!='missing' and is_etf:bind(p['premium_pct'],research['metrics']['premium_discount_pct']['value'],label+'.current_premium')
                if n['origin']!='missing' and n['as_of']==quote_day and 'close' in research.get('quote_status',''):
                    bind(p['close'],price,label+'.same_day_close')
            if n['origin']=='research':
                technical=research.get('technical',{});i=technical.get('indicators') or {}
                if technical.get('status')!='computed':active=False
                if n['as_of']!=technical.get('as_of'):errors.append(label+': research indicator date differs')
                for p in points:
                    for key in ('close','sma20','sma60','sma120','rsi14','macd','macd_signal'):
                        bind(p[key],i.get('last_close' if key=='close' else key),label+'.'+key)
                if is_etf:bind(point['premium_pct'],research['metrics']['premium_discount_pct']['value'],label+'.premium')
                elif point['premium_pct'] is not None:errors.append(label+': stock premium is not applicable')
            checks[label]={'signal':adverse(results) if active and fresh else 'unknown','cases':results,'recent_session_verified':fresh}
        else:
            if is_etf:
                if n['kind']!='etf_score' or n['origin']!='research' or numeric or n['alternatives']:errors.append(label+': ETF must directly use research earnings_support score')
                score=next((x['score'] for x in research.get('scores',{}).get('valuation',{}).get('items',[]) if x['check']=='earnings_support'),None)
                checks[label]={'signal':{2:'green',1:'yellow',0:'red',None:'unknown'}[score],'research_score':score}
            else:
                if n['kind'] not in ('stock_eps','stock_book'):errors.append(label+': stock earnings/book basis required')
                if n['as_of']!=quote_day:active=False
                window=n['window_start'] is not None and n['window_end'] is not None
                window_ok=window and 364<=(date.fromisoformat(n['window_end'])-date.fromisoformat(n['window_start'])).days<=366 and n['window_end']==n['as_of']
                for p in points:
                    if n['origin']!='missing' and p['current_price'] is not None:bind(p['current_price'],price,label+'.current_price')
                    reported=research.get('metrics',{}).get('eps_ttm' if n['kind']=='stock_eps' else 'book_value_per_share',{}).get('value')
                    if reported is not None and n['origin']!='missing' and p['current_earnings'] is not None:bind(p['current_earnings'],reported,label+'.known_current_earnings')
                    r=gate_7(p)
                    if not window_ok and not p['quality_issue_confirmed']:r['signal']='unknown'
                    results.append(r)
                if n['origin']=='research':bind(point['current_earnings'],research.get('metrics',{}).get('eps_ttm' if n['kind']=='stock_eps' else 'book_value_per_share',{}).get('value'),label+'.current_earnings')
                signal=adverse(results) if active else 'unknown'
                if point['quality_issue_confirmed'] and n['origin']!='missing':signal='red'
                checks[label]={'signal':signal,'cases':results,'window_verified':bool(window_ok)}
    return errors,{'gates':checks,'manual_gates':[3,4,5,8]}
