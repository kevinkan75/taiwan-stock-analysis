#!/usr/bin/env python3
"""Offline research report renderer. No fetching, scoring or source repair."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from io import StringIO
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import snapshot_guard as stock
import review_guard as review
from rules_core import SUMMARY_LABELS, timestamp

ROOT = Path(__file__).resolve().parents[1]
RENDERER_VERSION = '1.0.0'
ASSETS = ROOT / 'assets/html-report'
LABELS = {'fundamentals':'基本面','growth':'成長','valuation':'估值','industry':'產業','risk':'風險',
 'technical':'技術面','green':'🟢 綠燈','yellow':'🟡 黃燈','red':'🔴 紅燈','unknown':'⚪ 未評定',
 'major_risk':'🔴 重大風險','high':'高','medium':'中','low':'低','complete':'已完成',
 'incomplete':'未完成','sufficient':'足夠','insufficient':'不足','partial':'部分取得','conflicting':'衝突',
 'not_run':'未執行','not_applicable':'不適用','computed':'已計算','insufficient_data':'資料不足',
 'pass':'通過','conflict':'衝突','unavailable':'無法核對','base':'基準','conservative':'保守','optimistic':'樂觀',
 'balance_equation':'資產＝負債＋權益','cash_end_match':'期末現金勾稽','equity_opening_match':'期初權益銜接',
 'price':'股價','pe_ttm':'本益比 TTM','pe_forward':'預估本益比','pb':'股價淨值比','dividend_yield':'殖利率',
 'method':'方法','horizon':'期間','assumptions':'假設','model_price':'模型價格','formula':'公式','source_urls':'來源',
 'assumption_sources':'假設來源','band':'歷史區間','low':'低／低值','median':'中位數','current':'目前值',
 'period':'期間','observations':'觀測筆數','basis':'口徑','metric':'指標','current_metric':'目前指標欄位',
 'eps':'EPS','multiple':'倍數','currency':'幣別','instrument':'證券口徑','note':'說明',
 'multiple_basis':'倍數依據','eps_basis':'EPS依據','guardrails':'估值保護規則','applied_adjustments':'已套用調整',
 'sensitivity_only':'僅供敏感度參考','primary_metric':'主要指標','status':'狀態','reason':'理由',
 'one_off_note':'一次性因素','scenario':'反方情境','impact':'影響','disposition':'處理方式','follow_up':'後續核對',
 'driver':'論點動因','observable':'可觀察證據','trigger':'失效觸發條件','review_on':'核對時點',
 'statement':'主張','value':'數值','unit':'單位','verdict':'查核判斷','published_at':'公告時間','retrieved_at':'取得時間',
 'locator':'來源定位','source_url':'來源','url':'網址','title':'標題','source_type':'來源類型','id':'識別碼',
 'event_date':'事件日期','description':'說明','scheduled':'已排定','ordinary':'普通股','adr':'ADR',
 'period_start':'期初','period_end':'期末','raw_value':'原始值','scale':'換算倍數','inputs':'輸入',
 'reported':'已報導','calculated':'已計算','estimated':'預估','missing':'缺值','actual':'實際','estimate':'預估',
 'actual_or_estimate':'實際／預估','value_status':'數值狀態','as_of':'資料日期','retrieval':'讀取方式','rank':'來源層級'}
# Fields already derived by the annual validator; amounts are full currency units.
SERIES = [('revenue','營收','百萬',1e6),('gross_margin','毛利率','%',1),
 ('operating_margin','營業利益率','%',1),('net_income_parent','歸母淨利','百萬',1e6),
 ('diluted_eps','稀釋 EPS','元／普通股',1),('roe','ROE','%',1),('fcf','自由現金流','百萬',1e6),
 ('revenue_yoy','營收年增率','%',1),('eps_yoy','EPS 年增率','%',1)]


def esc(value):
    return html.escape(str(value), quote=True)


def number(value, scale=1):
    if value is None:return '— 未取得'
    return format(value / scale, ',.2f')


def digest(raw):return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def safe_link(value):
    value=str(value)
    try:
        parsed=urlsplit(value)
        safe=parsed.scheme.lower() in ('http','https') and bool(parsed.netloc) and not any(ord(c)<33 for c in value)
    except ValueError:safe=False
    return '<a rel="noopener noreferrer" href="'+esc(value)+'">'+esc(value)+'</a>' if safe else esc(value)


def value_html(value):
    if value is None:return '<span class="muted">— 未取得／未設定</span>'
    if isinstance(value,bool):return '是' if value else '否'
    if isinstance(value,dict):
        return '<dl class="record">'+''.join('<dt>'+esc(LABELS.get(k,k))+'</dt><dd>'+value_html(v)+'</dd>' for k,v in value.items())+'</dl>'
    if isinstance(value,list):
        return '<ol>'+''.join('<li>'+value_html(v)+'</li>' for v in value)+'</ol>' if value else '<span class="muted">來源未提供項目</span>'
    if isinstance(value,str) and re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',value):return safe_link(value)
    return esc(LABELS.get(value,value) if isinstance(value,str) else value)


def table(headers,rows,caption):
    return '<div class="table-scroll" tabindex="0" role="region" aria-label="'+esc(caption)+'"><table><caption>'+esc(caption)+'</caption><thead><tr>'+''.join('<th scope="col">'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def details(title,body):return '<details><summary>'+esc(title)+'</summary>'+body+'</details>'


def chart(rows,key,label,unit,scale):
    values=[r.get(key) for r in rows]; valid=[v/scale for v in values if v is not None]
    if not valid:return '<p class="empty">'+esc(label)+'：尚無可用年度值；不以 0 補齊。</p>'
    lo=min([0]+valid); hi=max([0]+valid)
    if hi==lo:hi=lo+1
    def pos(i,v):return (90+i*260/max(1,len(rows)-1),190-(v/scale-lo)/(hi-lo)*140)
    chunks=[]; segment=[]
    for i,v in enumerate(values):
        if v is None:
            if len(segment)>1:chunks.append('<polyline points="'+' '.join(segment)+'"/>')
            segment=[];continue
        x,y=pos(i,v);segment.append(f'{x:.2f},{y:.2f}')
        chunks.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4"/><text x="{x:.2f}" y="{y-12:.2f}" text-anchor="middle">{esc(number(v,scale))}</text>')
    if len(segment)>1:chunks.append('<polyline points="'+' '.join(segment)+'"/>')
    for i,r in enumerate(rows):
        x=90+i*260/max(1,len(rows)-1)
        chunks.append(f'<text x="{x:.2f}" y="222" text-anchor="middle">{esc(r["period_end"])}</text>')
        if values[i] is None:chunks.append(f'<text x="{x:.2f}" y="120" text-anchor="middle">未取得</text>')
    return '<svg viewBox="0 0 450 250" role="img" aria-label="'+esc(label+'，'+unit+'；精確數值及缺值見下表')+'"><title>'+esc(label+'（'+unit+'）')+'</title><path d="M65 45V200H410"/>'+''.join(chunks)+'</svg>'


def load_pair(research_path,review_path):
    raw=Path(research_path).read_bytes();rr=Path(review_path).read_bytes()
    s=stock.load_json(StringIO(raw.decode('utf-8')));r=stock.load_json(StringIO(rr.decode('utf-8')))
    if s.get('security',{}).get('instrument') not in ('ordinary','adr'):
        raise ValueError('首版 HTML 僅支援單一普通股／ADR研究，不支援ETF或多檔比較')
    if r.get('mode')!='research' or r.get('decision_reference') is not None:
        raise ValueError('首版 HTML 僅支援研究模式，不支援決策報告；不得移除決策資料以規避限制')
    if r.get('schema_version')!='1.2':raise ValueError('HTML 需要 review schema 1.2；請完成當次年度查核，不得回填改寫歷史紀錄')
    result=review.validate(r,s,raw)
    if not result['valid']:raise ValueError('來源驗證未通過：'+'; '.join(result['errors']))
    return s,r,raw,rr


def render(s,r,raw,review_raw,exported_at=None):
    # This API also validates; callers cannot accidentally bypass the CLI gate.
    result=review.validate(r,s,raw)
    if not result['valid']:raise ValueError('來源驗證未通過：'+'; '.join(result['errors']))
    if s['security']['instrument'] not in ('ordinary','adr') or r['mode']!='research' or r['schema_version']!='1.2':
        raise ValueError('首版 HTML 僅支援 review 1.2 單一個股研究')
    if json.loads(raw)!=s or json.loads(review_raw)!=r:raise ValueError('來源物件與原始檔案位元組不一致')
    exported_at=exported_at or datetime.now(timezone.utc).isoformat(timespec='seconds')
    timestamp(exported_at)
    css=(ASSETS/'report.css').read_bytes().decode('utf-8');js=(ASSETS/'report.js').read_bytes().decode('utf-8');template=(ASSETS/'report.html').read_bytes().decode('utf-8')
    manifest={'renderer_version':RENDERER_VERSION,'exported_at':exported_at,'research_sha256':digest(raw),
      'review_sha256':digest(review_raw),'report_sha256':s['report_sha256'],
      'template_sha256':digest((css+js+template).encode()),
      'source_versions':{k:s[k] for k in ('schema_version','model_version','skill_version','rule_version','validator_version')},
      'review_versions':{k:r[k] for k in ('schema_version','model_version','skill_version','rule_version','validator_version')}}
    a=r['assessment'];f=a['financial_history'];sec=s['security'];overall=s['overall']
    warnings=list(s['data_gaps'])+list(a['waiting_reasons'])
    if a['workflow_status']!='complete':warnings.insert(0,'最低查核尚未完成；請勿把程式驗證通過視為查核完成。')
    if a['evidence_status']!='sufficient':warnings.insert(0,'證據不足；沿用原研究結論及其限制。')
    if f['status']!='complete':warnings.append('三年財務狀態：'+LABELS.get(f['status'],f['status'])+'；'+f['reason'])
    for event in s['events']:
        if event.get('status')=='scheduled' and event.get('event_date') and event['event_date']>=s['data_cutoff_at'][:10]:
            warnings.append('資料截止時已排定事件：'+event['event_date']+' '+event['description']+'。未宣稱目前仍未發生。')
    alerts='<aside class="warnings" aria-label="限制與提醒"><strong>⚠ 限制與提醒</strong>'+value_html(list(dict.fromkeys(warnings)))+'</aside>' if warnings else ''
    header='<p class="eyebrow">個股研究 · 離線資料快照</p><h1>'+esc(sec['name'])+'</h1><p>'+esc(sec['symbol']+' · '+sec['exchange']+' · '+LABELS.get(sec['instrument'],sec['instrument']))+'</p>'
    header+='<div class="meta">'+''.join('<div><span>'+esc(label)+'</span><b>'+esc(s.get(key) if s.get(key) is not None else '未取得')+'</b></div>' for label,key in [('分析時間','analysis_at'),('資料截止','data_cutoff_at'),('行情時間','quote_at'),('行情狀態','quote_status'),('財報截止日','financial_period_end')])+'<div><span>報價／模型幣別</span><b>'+esc(sec['currency'])+'</b></div><div><span>年度財報幣別</span><b>'+esc(f.get('currency') or '未取得')+'</b></div></div>'
    statuses='<div class="status-grid"><div>✓ 結構與計算驗證<b>通過（不代表來源真實）</b></div><div>查核作業<b>'+esc(LABELS[a['workflow_status']])+'</b></div><div>證據充分性<b>'+esc(LABELS[a['evidence_status']])+'</b></div></div>'
    signal=LABELS.get(overall['signal'],overall['signal'])
    overview='<div class="hero"><div><span>原研究訊號</span><h2>'+esc(signal)+'</h2><p>'+esc(overall['reason'])+'</p></div><div><span>總分</span><strong>'+esc(overall['score'] if overall['score'] is not None else '未評定')+'</strong><p>信心：'+esc({'high':'高','medium':'中','low':'低'}.get(overall['confidence'],'未評定'))+' · 暫定：'+('是' if overall['provisional'] else '否')+'</p></div></div>'
    summary=[]
    for label in SUMMARY_LABELS:
        lines=[line for line in s['report_markdown'].splitlines() if re.match(r'^\s*(?:[-*#>]+\s*)?(?:\*\*)?'+re.escape(label)+r'(?:\*\*)?\s*[:：]',line)]
        summary.append('<div class="card"><h3>'+esc(label)+'</h3><p>'+esc(lines[0] if lines else '請見原報告；來源未提供獨立摘要行')+'</p></div>')
    overview+='<div class="cards">'+''.join(summary)+'</div><h2>六面向與證據</h2><div class="cards">'
    for key,d in list(s['scores'].items())+[('technical',s['technical'])]:
        istech=key=='technical'
        overview+='<article class="card"><h3>'+esc(LABELS[key])+'</h3><p>'+esc(LABELS.get(d.get('signal'),d.get('signal','未評定')))+'</p><p>'+('狀態：'+esc(LABELS.get(d['status'],d['status'])) if istech else '分數：'+esc(d['display_score'] if d['display_score'] is not None else '未評定')+' · 覆蓋：'+esc(str(d['coverage'])+'/'+str(d['total_items'])))+'</p>'+details('展開證據',value_html(d))+'</article>'
    overview+='</div><h2>投資論點與支持依據</h2>'+value_html(s['thesis'])+'<h2>限制與缺口</h2>'+value_html(s['data_gaps'])
    annual='<p>年度財務：'+esc(LABELS.get(f['status'],f['status']))+'；'+esc(f['reason'])+'</p><p>金額以百萬 '+esc(f.get('currency') or '未取得')+' 顯示；EPS 為財報幣別／普通股，ADR 不自動換算。百分比不是小數比例。顯示四捨五入至小數兩位；缺值不補 0、不跨缺值連線。</p>'
    annual+='<div class="controls"><label for="indicator">圖表指標</label><select id="indicator">'+''.join('<option value="'+key+'">'+esc(label)+'</option>' for key,label,_,_ in SERIES)+'</select><button type="button" id="view-toggle" aria-pressed="false">顯示資料表</button></div><div id="charts">'
    for key,label,unit,scale in SERIES:
        annual+='<figure data-series="'+key+'"><figcaption>'+esc(label+'（'+unit+'）')+'</figcaption>'+chart(f['rows'],key,label,unit,scale)+'</figure>'
    annual+='</div><div id="annual-table">'+table(['完整年度期間']+[label+'（'+unit+'）' for _,label,unit,_ in SERIES],[[esc(x['period_start']+' ～ '+x['period_end'])]+[esc(number(x.get(k),scale)) for k,_,_,scale in SERIES] for x in f['rows']],'年度財務數值（不足三年時僅列已取得年度）')+'</div>'
    annual+='<p>三個年度、兩個間隔的營收 CAGR：'+esc(number(f['revenue_cagr_two_intervals']))+'%</p>'+value_html({'missing_periods':f['missing_periods'],'missing_inputs':f['missing_inputs'],'limitation':f['limitation']})
    annual+=details('年度原始輸入、來源定位與一次性因素',value_html(r['financial_history']))
    val='<p>沿用已驗證模型與原始假設；不在瀏覽器重算研究評分。模型價格為情境結果，並非保證目標價。</p><h2>已知指標</h2>'
    val+=table(['指標','數值','單位／幣別','期間與口徑','來源'],[[esc(LABELS.get(k,k)),esc(number(m['value'])),esc(m['unit']+' / '+str(m.get('currency'))),value_html({'period':m['period'],'basis':m['basis'],'actual_or_estimate':m['actual_or_estimate'],'value_status':m['value_status'],'formula':m.get('formula'),'inputs':m.get('inputs')}),value_html(m.get('source_url'))] for k,m in s['metrics'].items() if k in ('price','pe_ttm','pe_forward','pb','dividend_yield','eps_ttm','eps_forward')],'報價、獲利與估值指標')
    val+='<h2>歷史區間</h2>'+(value_html(s['valuation']['band']) if s['valuation']['band'] else '<p class="empty">未取得可比歷史區間；不推造上下緣。</p>')
    val+='<h2>有依據的估值情境</h2>'+(value_html(s['valuation']['scenarios']) if s['valuation']['scenarios'] else '<p class="empty">假設不足，未建立模型價格。</p>')
    val+=details('方法、假設來源與估值限制',value_html({k:v for k,v in s['valuation'].items() if k not in ('band','scenarios')}))
    risk='<h2>事件與風險</h2>'+value_html(s['events'])+value_html(s['risks'])+'<h2>反方情境與論點失效條件</h2>'+value_html(r['evidence_audit']['counter_cases'])+value_html(r['evidence_audit']['invalidation_conditions'])+'<h2>缺口與等待原因</h2>'+value_html(s['data_gaps'])+value_html(a['waiting_reasons'])
    risk+='<h2>報表勾稽</h2>'+table(['期末','核對項目','狀態','差額（原幣）','容許差額（原幣）'],[[esc(c['period_end']),esc(LABELS.get(c['check'],c['check'])),esc(LABELS[c['status']]),esc(number(c['difference'])),esc(number(c['tolerance']))] for c in f['checks']],'報表差額與容許誤差（'+str(f.get('currency'))+'）')
    risk+='<h2>來源清單</h2>'+value_html(s['sources'])+value_html(r['sources'])+details('逐項主張查核',value_html(r['evidence_audit']['claims']))+details('取數作業紀錄',value_html(r['tasks']))
    original=details('完整原始報告（純文字）','<pre id="original-report">'+esc(s['report_markdown'])+'</pre>')
    metadata=encode(manifest).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    footer='<p>匯出時間：'+esc(exported_at)+' · 呈現器 '+RENDERER_VERSION+' · 原研究規則 '+esc(s['rule_version'])+'</p><p>此檔為資料截止時的快照；開啟不會更新行情。來源連結需連網才能查看。</p>'+original+details('版本與來源雜湊',value_html(manifest))
    replacements={'TITLE':esc(sec['name']+'｜個股研究'),'CSS':css,'JS':js,'HEADER':header,'STATUSES':statuses,'WARNINGS':alerts,
        'OVERVIEW':overview,'FINANCIALS':annual,'VALUATION':val,'RISKS':risk,'FOOTER':footer,'MANIFEST':metadata,
        'SCRIPT_HASH':base64.b64encode(hashlib.sha256(js.encode()).digest()).decode(),
        'STYLE_HASH':base64.b64encode(hashlib.sha256(css.encode()).digest()).decode()}
    return re.sub(r'@@([A-Z_]+)@@',lambda m:replacements[m.group(1)],template)


class ManifestParser(HTMLParser):
    def __init__(self):super().__init__();self.inside=False;self.parts=[];self.count=0
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('id')=='export-manifest':self.inside=True;self.count+=1
    def handle_endtag(self,tag):
        if tag=='script':self.inside=False
    def handle_data(self,data):
        if self.inside:self.parts.append(data)


def verify(output,s,r,raw,review_raw):
    parser=ManifestParser();parser.feed(output)
    if parser.count!=1:raise ValueError('HTML 匯出資訊區塊缺失或重複')
    metadata=json.loads(''.join(parser.parts))
    if metadata.get('renderer_version')!=RENDERER_VERSION:raise ValueError('不支援此呈現器版本；請使用對應版本核對')
    expected=render(s,r,raw,review_raw,metadata['exported_at'])
    if output!=expected:raise ValueError('HTML 與來源、版本或固定模板不一致')
    return {'valid':True,'scope':'exact_render_and_source_binding','renderer_version':RENDERER_VERSION,'sha256':digest(output.encode())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--research',required=True);parser.add_argument('--review',required=True)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--output');group.add_argument('--verify')
    parser.add_argument('--exported-at',help='optional timezone-aware timestamp for reproducible exports')
    args=parser.parse_args()
    try:
        s,r,raw,rr=load_pair(args.research,args.review)
        if args.verify:
            output=Path(args.verify).read_bytes().decode('utf-8');answer=verify(output,s,r,raw,rr)
        else:
            target=Path(args.output)
            if target.resolve() in (Path(args.research).resolve(),Path(args.review).resolve()):raise ValueError('不可覆寫來源檔案')
            output=render(s,r,raw,rr,args.exported_at);answer=verify(output,s,r,raw,rr)
            # Atomic existence check; refuse to overwrite a user artifact.
            with target.open('x',encoding='utf-8',newline='') as stream:stream.write(output)
            answer['output']=str(target)
        print(json.dumps(answer,ensure_ascii=False))
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(json.dumps({'valid':False,'error':str(error)},ensure_ascii=False));return 2
    return 0


if __name__=='__main__':sys.exit(main())
