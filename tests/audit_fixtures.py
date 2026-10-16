"""Synthetic audit authoring fixtures. Never use as retrieved market evidence."""
from copy import deepcopy


def make_audit(research, dec=None):
    claims=[]
    url=research['sources'][0]['url']
    period='2026合成同口徑期間'
    basis='合成數值，非外部事實；單位及證券口徑同參照欄位'

    def claim(key, value, target, kind='fact', premises=None, recipe=None):
        inference=kind in ('assumption','inference')
        x={'id':key,'kind':kind,'statement':'合成查核：'+target,'value':value,
           'unit':'同目標欄位（合成）','period':period,'basis':basis,'targets':[target],
           'report_excerpt':'','material':True,'verdict':'reviewed' if inference else 'supported',
           'sources':[] if inference or kind=='calculation' else [dict(url=url,locator='合成附件表格之對應列',published_at='2026-07-30',period=period,basis=basis,value=value,rank='primary',retrieval='document')],
           'selected_source':None if inference or kind=='calculation' else 0,
           'premises':premises or [],'calculation':recipe,'reason':'合成作者核對紀錄；不表示外部數據已查證'}
        claims.append(x)
        return key

    for key,m in research['metrics'].items():
        if m['value'] is None:continue
        kind=('calculation' if m.get('value_status')=='calculated' else 'guidance' if m.get('source_type')=='company_guidance'
              else 'estimate' if m.get('actual_or_estimate')=='estimate' or m.get('value_status')=='estimated' or m.get('source_type')=='external_estimate' else 'fact')
        recipe=dict(method='manual',inputs=[],reason='合成自訂公式已按附件輸入逐步人工核算；本項不宣稱自動驗算') if kind=='calculation' else None
        premises=['metric_price'] if kind=='calculation' else []
        if key=='pe_ttm':
            recipe=dict(method='divide',inputs=[research['metrics']['price']['value'],research['metrics']['eps_ttm']['value']],reason='同幣別每股價格除以同期EPS')
            premises=['metric_price','metric_eps_ttm']
        claim('metric_'+key,m['value'],'research:/metrics/'+key+'/value',kind,premises,recipe)
        claims[-1].update(unit=m['unit'],period=m['period'],basis=m['basis'])
        for source in claims[-1]['sources']:
            source.update(period=m['period'],basis=m['basis'])
    base='metric_price'
    for dim,body in research['scores'].items():
        for i,item in enumerate(body['items']):
            if item['score'] is not None:
                claim('score_'+dim+str(i),item['score'],f'research:/scores/{dim}/items/{i}/score','inference',[base])
    for i,scenario in enumerate(research.get('valuation',{}).get('scenarios',[])):
        for field in ('eps','multiple'):
            claim(f'assumption_{i}_{field}',scenario['assumptions'][field],f'research:/valuation/scenarios/{i}/assumptions/{field}','assumption')
        claim('scenario_'+str(i),scenario['model_price'],f'research:/valuation/scenarios/{i}/model_price','calculation',
              [f'assumption_{i}_eps',f'assumption_{i}_multiple'],dict(method='product',inputs=[scenario['assumptions']['eps'],scenario['assumptions']['multiple']],reason='假設EPS乘以假設本益比，模型結果不等於目標價保證'))
    for i,event in enumerate(research.get('events',[])):
        claim('event_'+str(i),event['description'],f'research:/events/{i}/description')
    if dec:
        for i,g in enumerate(dec['gates']):
            claim('gate_'+str(i+1),g['signal'],f'decision:/gates/{i}/signal','inference',[base])
    counter=[]
    for i,scenario in enumerate(('成本上升使獲利假設落空','需求循環轉弱使成長假設落空','市場倍數下修使模型價失去支撐')):
        excerpt='反方假設（合成）：'+scenario+'。'
        counter.append(dict(thesis_index=0,claim_ids=[base],report_excerpt=excerpt,scenario=scenario,
                            impact='原合成估值與行動需重新評估',disposition='disclosed',follow_up='取得下一期正式資料後核對；未觀察到前不當作已發生事實'))
    if research['security']['instrument']=='etf':
        condition=dict(thesis_index=0,claim_ids=['score_instrument0'],report_excerpt='失效條件（合成）：基金正式修訂曝險範圍，使原投資定位不再適用時重評。',
                       driver='本次基金曝險定位',observable='公開說明書與選股／指數規則',trigger='正式修訂後曝險範圍不再符合原投資定位',review_on='公開說明書或指數規則變更生效前')
    else:
        condition=dict(thesis_index=0,claim_ids=['metric_eps_ttm'],report_excerpt='失效條件（合成）：後續兩期財報的同口徑TTM稀釋EPS均低於5元時重評。',
                       driver='支持估值的獲利能力',observable='後續兩期財報之可比TTM稀釋EPS',trigger='兩期TTM稀釋EPS均低於5元；此為分析假設門檻',review_on='後續兩期正式季報公布後各核對一次')
    obj=dec or research
    obj['report_markdown']+='\n'+'\n'.join(x['report_excerpt'] for x in counter+[condition])
    return dict(status='complete',thesis_status='established',coverage_note='合成範例逐項盤點結構化數值與分數，正文主張仍需人工盤點，非真實取數紀錄',claims=claims,counter_cases=counter,invalidation_conditions=[condition])


def finish_review(record,research,dec=None):
    import hashlib
    import json
    import review_guard as review
    import financial_history
    def encode(x):return (json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    def bind():
        raw=encode(research)
        record['research_reference'].update(sha256=hashlib.sha256(raw).hexdigest(),rule_version=research['rule_version'],model_version=research['model_version'])
        if dec:
            dec['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
            draw=encode(dec)
            record['decision_reference'].update(sha256=hashlib.sha256(draw).hexdigest(),rule_version=dec['rule_version'],model_version=dec['model_version'])
        else:draw=None
        return raw,draw
    obj=dec or research
    if 'financial_history' in record:
        obj['report_markdown']=financial_history.strip_report(obj['report_markdown'])+'\n'+financial_history.render(financial_history.derive(record['financial_history']))
    obj['report_sha256']=hashlib.sha256(obj['report_markdown'].encode()).hexdigest()
    raw,draw=bind()
    result=review.validate(record,research,raw,dec,draw,True)
    if not result['valid']:raise AssertionError(result['errors'])
    record['assessment']=result['derived']
    obj['report_markdown']='\n'.join(line for line in obj['report_markdown'].splitlines()
        if not line.startswith(('作業檢核：','決策證據：','等待原因：','資料查核紀錄：','主張查核：','三年財務檢核：',review.SCOPE_LINE)))
    obj['report_markdown']+='\n'+review.report_block(record['assessment'])
    obj['report_sha256']=hashlib.sha256(obj['report_markdown'].encode()).hexdigest()
    raw,draw=bind()
    result=review.validate(record,research,raw,dec,draw)
    if not result['valid']:raise AssertionError(result['errors'])
    return raw,draw
