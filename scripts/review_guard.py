#!/usr/bin/env python3
"""Bind shared retrieval/workflow review to validated stock/ETF and decision files.

No network access. Attempt logs and external evidence are supplied by the analyst;
passing this tool never certifies that a request was actually executed.
"""
import argparse
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys

import snapshot_guard as stock
import decision_guard as decision
import report_checks
import evidence_audit
import financial_history
import research_views
from rules_core import SKILL_VERSION, RULE_VERSION, timestamp

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'workflow_attempts_binding_and_report_checks'
SCOPE_LINE = '作業驗證範圍：紀錄格式、來源連結、作業狀態與報告一致性；未自動查證外部證據或投資勝率。'
STATUS_LABELS = {'obtained':'已取得並核對', 'not_run':'尚未執行', 'partial':'尚未完成', 'not_published':'尚未公布',
                 'access_failed':'存取失敗', 'conflicting':'來源衝突', 'incompatible':'口徑不符', 'not_applicable':'不適用'}
WAIT_LABELS = {'data_pending':'資料待補', 'event_pending':'事件待明',
               'price_conditions':'價格或動能條件未到', 'risk_conditions':'風險條件待改善'}
BASE_TASKS = ('quote', 'financials', 'valuation', 'events')
STOCK_TASKS = ('growth', 'industry')
ETF_TASKS = ('fund_rules', 'cost_tracking', 'holdings', 'distribution')
DECISION_TASKS = ('market', 'technical', 'expectations', 'exit_conditions')


def required_tasks(research, has_decision):
    return BASE_TASKS + (ETF_TASKS if research['security']['instrument']=='etf' else STOCK_TASKS) + (DECISION_TASKS if has_decision else ())


def evidence_available(task, research, dec):
    """Check only machine-visible links, not truth of the supplied evidence."""
    q = research['eligibility']
    gates = {x['number']:x['signal'] for x in dec['gates']} if dec else {}
    if task == 'quote': return q['quote_verified'] in ('pass','limited') and q['quote_is_current'] in ('pass','limited')
    if task == 'financials': return q.get('financials_verified', q.get('holdings_financials_verified')) in ('pass','limited')
    if task == 'valuation': return q['valuation_supported'] in ('pass','limited')
    if task in DECISION_TASKS:
        return gates.get({'market':4,'technical':6,'expectations':7,'exit_conditions':8}[task]) not in (None,'unknown')
    if task == 'growth':
        return next((x['score'] for x in research['scores']['growth']['items'] if x['check']=='realized_revenue'),None) is not None
    if task == 'industry': return research['scores']['industry']['coverage'] >= 2
    # ETF methods/holdings/distribution and a negative event search remain manual.
    return True


def derive(record, research, dec, decision_result=None):
    tasks = record['tasks']
    pending = [x['id'] for x in tasks if x['status'] in ('not_run','partial')]
    annual = financial_history.derive(record['financial_history']) if 'financial_history' in record else None
    if annual and annual['status']=='not_run': pending.append('financial_history')
    audit = evidence_audit.audit_state(record['evidence_audit']) if 'evidence_audit' in record else None
    if audit and audit['status'] != 'complete':
        pending.append('evidence_audit')
    workflow = 'incomplete' if pending else 'complete'
    sufficient = not pending and research['overall']['signal'] not in ('unknown','major_risk')
    if annual and annual['status']=='conflicting': sufficient=False
    if audit:
        sufficient = sufficient and not audit['material_unresolved'] and audit['thesis_status']=='established'
    waits = []
    if dec:
        gates = {x['number']:x['signal'] for x in dec['gates']}
        ready = bool(decision_result and decision_result.get('quote_ready'))
        # Descriptive completeness only; do not change the original decision
        # rule that can permit conditional staging with non-core unknowns.
        sufficient = sufficient and ready and all(gates[n]!='unknown' for n in range(1,9))
        if dec['conclusion']['action']=='wait':
            audit_data_gap=bool(audit and (audit['thesis_status']=='insufficient' or any(not x.startswith('counter_case_') for x in audit['material_unresolved'])))
            audit_risk=bool(audit and any(x.startswith('counter_case_') for x in audit['material_unresolved']))
            if not ready or any(gates[n]=='unknown' for n in range(1,9)) or pending or audit_data_gap or annual and annual['status']=='conflicting':
                waits.append('data_pending')
            if gates[5]=='red' or gates[5]=='yellow' and gates[4]=='red': waits.append('event_pending')
            if any(gates[n]=='red' for n in (2,6,7)): waits.append('price_conditions')
            if gates[4]=='red' or audit_risk: waits.append('risk_conditions')
    official = {x['source_url'] for t in tasks for x in t['attempts']
                if x['stage']=='primary' and x['result']=='success' and x['source_url']}
    alternatives = {x['source_url'] for t in tasks for x in t['attempts']
                    if x['stage']=='alternative' and x['result']=='success' and x['source_url']}
    result = {'workflow_status':workflow, 'evidence_status':'sufficient' if sufficient else 'insufficient',
            'pending_tasks':pending, 'unresolved_tasks':[x['id'] for x in tasks if x['status'] not in ('obtained','not_applicable')],
            'waiting_reasons':waits, 'research_confidence':research['overall']['confidence'],
            'primary_source_count':len(official), 'alternative_source_count':len(alternatives),
            'attempt_count':sum(len(x['attempts']) for x in tasks)}
    if audit:
        result['claim_audit'] = audit
    if annual:
        result['financial_history'] = annual
        if annual['status'] in ('not_run','partial','conflicting'):
            result['unresolved_tasks'].append('financial_history')
    return result


def report_block(assessment):
    lines = [
        '作業檢核：'+('已完成規定查核' if assessment['workflow_status']=='complete' else '尚未完成'),
        '決策證據：'+('足夠' if assessment['evidence_status']=='sufficient' else '不足'),
        '等待原因：'+('、'.join(WAIT_LABELS[x] for x in assessment['waiting_reasons']) or '不適用'),
        '資料查核紀錄：主要來源%d個、替代來源%d個；未解決項目%d項。' %
        (assessment['primary_source_count'],assessment['alternative_source_count'],len(assessment['unresolved_tasks'])),
        SCOPE_LINE]
    if 'claim_audit' in assessment:
        audit=assessment['claim_audit']
        lines.append('主張查核：%s；紀錄%d項；關鍵未解決%d項。' %
                     ('已完成' if audit['status']=='complete' else '尚未完成',audit['claims'],len(audit['material_unresolved'])))
    if 'financial_history' in assessment:
        annual=assessment['financial_history']
        lines.append('三年財務檢核：%s；已列%d個年度；未齊%d個年度；缺欄%d項。' %
                     (financial_history.LABELS[annual['status']],annual['periods'],annual['missing_periods'],len(annual['missing_inputs'])))
    return '\n'.join(lines)


def initialize(research, raw, research_name, dec=None, draw=None, decision_name=None, at=None):
    """Create an honest all-not-run worklist; never fabricate source attempts."""
    errors, verification=decision.validate_research(research)
    if errors:raise ValueError('; '.join(errors))
    if verification=='manual_etf':raise ValueError('legacy manual ETF cannot be certified')
    if 'report_markdown' not in research or 'confidence' not in research.get('overall',{}):
        raise ValueError('review requires a source report and explicit research confidence; legacy fields must not be invented')
    decision_result=decision.validate(dec,research,hashlib.sha256(raw).hexdigest()) if dec else None
    if decision_result and not decision_result['valid']:raise ValueError('; '.join(decision_result['errors']))
    def ref(source, payload, name):
        return {'reference':'attachment:'+name,'sha256':hashlib.sha256(payload).hexdigest(),
                'rule_version':source.get('rule_version'),'model_version':source['model_version']}
    analysis_at=at or datetime.now().astimezone().isoformat(timespec='seconds')
    if timestamp(analysis_at)<timestamp((dec or research)['analysis_at']):raise ValueError('review analysis cannot precede source analysis')
    record={'snapshot_type':'review','schema_version':'1.2','model_version':'review-1.2',
            'skill_version':SKILL_VERSION,'rule_version':RULE_VERSION,'validator_version':'1.2.0',
            'security':deepcopy(research['security']),
            'analysis_at':analysis_at,
            'data_cutoff_at':(dec or research)['data_cutoff_at'],'mode':'decision' if dec else 'research',
            'research_reference':ref(research,raw,research_name),
            'decision_reference':ref(dec,draw,decision_name) if dec else None,
            'tasks':[{'id':name,'status':'not_run','reason':'尚未執行本次規定查核；先確認期間、口徑及適用來源','attempts':[]}
                     for name in required_tasks(research,dec is not None)],'sources':[],
            'evidence_audit':{'status':'not_run','thesis_status':'insufficient',
                'coverage_note':'尚未盤點逐項主張；不得宣稱查核完成',
                'claims':[],'counter_cases':[],'invalidation_conditions':[]}}
    record['financial_history']=financial_history.initialize(research['security']['instrument']=='etf',
                                                            verification=='stock_snapshot' and stock.financials_waived(research))
    record['assessment']=derive(record,research,dec,decision_result)
    return record


def validate(record, research, research_raw, dec=None, decision_raw=None, derive_only=False):
    legacy = record.get('schema_version')=='1.0'
    previous = record.get('schema_version')=='1.1'
    current = record.get('schema_version')=='1.2'
    name='assets/review.schema-1.0.json' if legacy else 'assets/review.schema-1.1.json' if previous else 'assets/review.schema.json'
    schema = json.loads((ROOT/name).read_text(encoding='utf-8'))
    stock.audit_keywords(schema)
    errors = stock.schema_errors(record,schema,schema)
    if errors:return {'valid':False,'scope':'structure','errors':errors,'derived':None}
    profile=('1.11.0','1.11.0') if legacy else ('1.12.0','1.12.0') if previous else (SKILL_VERSION,RULE_VERSION)
    if (record['skill_version'],record['rule_version']) not in ({profile,('1.13.0','1.13.0')} if current else {profile}): errors.append('review: release/schema mismatch; do not backfill historical review')
    result, verification = decision.validate_research(research)
    errors += result
    if verification=='manual_etf':errors.append('review: manually unvalidated legacy ETF cannot be certified')
    if 'report_markdown' not in research or 'confidence' not in research.get('overall',{}):
        errors.append('review: source report and explicit confidence required; do not backfill legacy fields')
    if errors:return {'valid':False,'scope':'research_binding','errors':errors,'derived':None}
    refs = [(record['research_reference'],research,research_raw,'research')]
    if (legacy or previous) and research.get('rule_version') in ('1.13.0',RULE_VERSION):
        errors.append('review: current research requires annual review schema 1.2')
    if legacy and research.get('rule_version')=='1.12.0':
        errors.append('review: claim-audit research requires schema 1.1 or later')
    dec_result = None
    if dec is not None:
        if (legacy or previous) and dec.get('rule_version') in ('1.13.0',RULE_VERSION):
            errors.append('review: current decision requires annual review schema 1.2')
        if legacy and dec.get('rule_version')=='1.12.0':
            errors.append('review: claim-audit decision requires schema 1.1 or later')
        if decision_raw is None:errors.append('decision: exact source bytes required')
        else:
            dec_result = decision.validate(dec,research,hashlib.sha256(research_raw).hexdigest())
            errors += ['decision: '+x for x in dec_result['errors']]
            refs.append((record['decision_reference'],dec,decision_raw,'decision'))
    elif record['decision_reference'] is not None:errors.append('decision: supplied reference requires actual file')
    if (record['mode']=='decision') != (dec is not None):errors.append('review: mode must agree with actual decision file')
    try:
        at=timestamp(record['analysis_at']);cutoff=timestamp(record['data_cutoff_at'])
        if cutoff>at:errors.append('review: cutoff after analysis')
        for ref,source,raw,label in refs:
            if ref is None:
                errors.append(label+': missing reference');continue
            if not derive_only and ref['sha256']!=hashlib.sha256(raw).hexdigest():errors.append(label+': byte hash mismatch')
            if record['security']!=source['security']:errors.append(label+': security mismatch')
            if timestamp(source['analysis_at'])>at or timestamp(source['data_cutoff_at'])>cutoff:errors.append(label+': source after review cutoff')
            if ref['rule_version']!=source.get('rule_version') or ref['model_version']!=source['model_version']:errors.append(label+': source version mismatch')
        known={x['url'] for x in record['sources']}
        known |= {x['url'] for x in research['sources']}
        if dec:known |= {x['url'] for x in dec['sources']}
        for source in record['sources']:
            if timestamp(source['retrieved_at'])>at:errors.append('review: source retrieved after analysis')
            published=source['published_at']
            if published and (timestamp(published)>cutoff if 'T' in published else date.fromisoformat(published)>cutoff.date()):errors.append('review: source published after cutoff')
        ids=[x['id'] for x in record['tasks']]
        if ids!=list(required_tasks(research,dec is not None)):errors.append('tasks: complete canonical task list required for asset and mode')
        for task in record['tasks']:
            label='tasks.'+task['id'];status=task['status'];attempts=task['attempts']
            stages={x['stage'] for x in attempts};results={x['result'] for x in attempts}
            if status=='not_run' and attempts:errors.append(label+': not_run must not claim attempts')
            if status=='not_applicable':
                waived=task['id']=='financials' and verification=='stock_snapshot' and stock.financials_waived(research)
                if not waived:errors.append(label+': this task cannot be waived')
            elif status!='not_run':
                if not attempts:errors.append(label+': attempted status requires evidence log')
                if status=='obtained':
                    if 'success' not in results:errors.append(label+': obtained requires successful attempt')
                    if not any(x['source_url'] and x['result']=='success' for x in attempts):errors.append(label+': obtained requires a linked successful source')
                    if not evidence_available(task['id'],research,dec):errors.append(label+': obtained contradicts source gaps')
                elif status=='partial':
                    pass  # Work was started; never upgrade to completed retrieval.
                elif status=='not_published':
                    if task['id'] not in ('financials','events','expectations'):errors.append(label+': publication status invalid for this task')
                    if 'primary' not in stages or not results & {'success','unavailable'}:errors.append(label+': publication status requires primary announcement/calendar check')
                else:
                    if not {'primary','alternative'}<=stages:errors.append(label+': unresolved retrieval requires primary and alternative attempts')
                    expected={'access_failed':{'blocked','unavailable'},'conflicting':{'conflict'},'incompatible':{'incompatible'}}[status]
                    if not results & expected:errors.append(label+': status lacks matching attempt outcome')
            seen=set();previous=None
            for attempt in attempts:
                when=timestamp(attempt['at'])
                if when>at:errors.append(label+': attempt after analysis')
                if previous and when<previous:errors.append(label+': attempts must be chronological')
                previous=when
                url=attempt['source_url']
                if url and url not in known:errors.append(label+': unregistered attempt source')
                if attempt['stage']!='calculation' and not url:errors.append(label+': retrieval attempt requires source URL')
                if attempt['stage']=='primary' and url and not url.startswith('attachment:'):
                    if not attempt['authority_basis'].strip():errors.append(label+': primary source requires authority basis')
                key=(attempt['stage'],url,attempt['request'],attempt['result'])
                if key in seen:errors.append(label+': duplicate request/outcome; reuse prior attempt')
                seen.add(key)
    except (ValueError,TypeError,KeyError) as exc:
        errors.append('review: '+str(exc))
    if not errors and not legacy:
        try:
            errors += evidence_audit.validate(record['evidence_audit'],research,dec,known,cutoff)
        except (ValueError,TypeError,KeyError,IndexError) as exc:
            errors.append('audit: '+str(exc))
    if not errors and current:
        all_sources=research['sources']+record['sources']+(dec['sources'] if dec else [])
        try:
            errors+=financial_history.validate(record['financial_history'],all_sources,cutoff,at,
                research['security']['instrument']=='etf',verification=='stock_snapshot' and stock.financials_waived(research))
            if record['financial_history']['status']=='attempted' and not any(t['attempts'] for t in record['tasks'] if t['id'] in ('financials','growth')):
                errors.append('financial_history: attempted annual review requires financials/growth retrieval log')
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            errors.append('financial_history: '+str(exc))
    if errors:return {'valid':False,'scope':SCOPE,'errors':errors,'derived':None}
    assessment=derive(record,research,dec,dec_result)
    report=dec['report_markdown'] if dec else research['report_markdown']
    action=dec['conclusion']['action'] if dec else None
    if current and action in ('enter','staged') and assessment['financial_history']['status'] in ('not_run','conflicting'):
        errors.append('financial_history: unattempted or conflicting annual review cannot certify entry/staging')
    errors+=report_checks.report_errors(report,action,research['overall']['confidence'])
    if not derive_only:
        if record['assessment']!=assessment:errors.append('assessment: differs from derived status')
        expected=report_block(assessment)
        for line in expected.splitlines():
            if report.splitlines().count(line)!=1:errors.append('report: missing/duplicated review line '+line)
        for prefix in ('作業檢核：','決策證據：','等待原因：','資料查核紀錄：'):
            if len([x for x in report.splitlines() if x.startswith(prefix)])!=1:errors.append('report: inconsistent review status '+prefix)
        if not legacy and len([x for x in report.splitlines() if x.startswith('主張查核：')])!=1:
            errors.append('report: inconsistent claim audit status')
        if current:
            if len([x for x in report.splitlines() if x.startswith('三年財務檢核：')])!=1:
                errors.append('report: inconsistent annual review status')
            errors+=financial_history.report_errors(report,assessment['financial_history'])
    return {'valid':not errors,'scope':SCOPE,'errors':errors,'derived':assessment,
            'report_block':report_block(assessment),
            **({'financial_history_report':financial_history.render(assessment['financial_history'])} if current else {}),
            **({'thesis_comparison_report':research_views.thesis_markdown(research,record)} if not legacy else {}),
            'limitation':'Attempt logs, source authority and facts remain manually supplied; no accuracy or speed claim.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',nargs='?');p.add_argument('--research',required=True);p.add_argument('--decision');p.add_argument('--analysis-at')
    modes=p.add_mutually_exclusive_group();modes.add_argument('--derive',action='store_true');modes.add_argument('--render',action='store_true');modes.add_argument('--init',action='store_true')
    args=p.parse_args()
    try:
        raw=Path(args.research).read_bytes();research=json.loads(raw)
        draw=Path(args.decision).read_bytes() if args.decision else None
        dec=json.loads(draw) if draw is not None else None
        if args.init:
            if args.input:raise ValueError('--init creates a new draft; do not supply an input record')
            output=initialize(research,raw,Path(args.research).name,dec,draw,Path(args.decision).name if args.decision else None,args.analysis_at)
            print(json.dumps(output,ensure_ascii=False,allow_nan=False,indent=2));return 0
        if not args.input:raise ValueError('review input required unless --init')
        with Path(args.input).open(encoding='utf-8') as source:record=stock.load_json(source)
        result=validate(record,research,raw,dec,draw,args.derive or args.render)
        output=result
        if args.derive and result['valid']:
            output=deepcopy(record);output['assessment']=result['derived']
            output['research_reference']['sha256']=hashlib.sha256(raw).hexdigest()
            if draw:output['decision_reference']['sha256']=hashlib.sha256(draw).hexdigest()
        print(json.dumps(output,ensure_ascii=False,allow_nan=False,indent=2))
        return 0 if result['valid'] else 2
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'valid':False,'scope':'input','errors':[str(exc)]},ensure_ascii=False));return 2


if __name__=='__main__':sys.exit(main())
