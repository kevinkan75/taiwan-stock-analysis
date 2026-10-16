"""Synthetic view semantics, source bindings and failure-state regression checks."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
import audit_fixtures
import html_export
import research_views as views
import review_guard

checks = 0


def check(value, message):
    global checks
    checks += 1
    if not value:
        raise AssertionError(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n').encode()


def fixture():
    return (json.loads((ROOT/'assets/snapshot.example.json').read_bytes()),
            json.loads((ROOT/'assets/review.example.json').read_bytes()))


def finish(s, r):
    audit_fixtures.finish_review(r, s)
    return s, r, encode(s), encode(r)


def bind_thesis(s, r):
    claim = deepcopy(r['evidence_audit']['claims'][0])
    claim.update(id='thesis_0', kind='inference', statement=s['thesis'][0], value=s['thesis'][0],
                 targets=['research:/thesis/0'], verdict='reviewed', sources=[], selected_source=None,
                 premises=['metric_eps_ttm'], calculation=None,
                 reason='依本次獲利主張檢視論點；本例僅為合成資料')
    r['evidence_audit']['claims'].append(claim)


def main():
    s, r = fixture()
    before = deepcopy((s, r))
    rows = views.thesis_rows(s, r)
    check(rows[0]['support'] == [], 'legacy unbound thesis must not borrow counter-case evidence')
    check(len(rows[0]['counter_cases']) == 3, 'existing counter cases retained')
    check(rows[0]['counter_cases'][0]['evidence'][0]['id'] == 'metric_price', 'counter evidence stays on counter side')
    check((s, r) == before, 'view never mutates source records')
    check('未建立明確主張連結' in views.thesis_markdown(s, r), 'missing binding explicit in text')
    check('已揭露；不代表已調整評分' in views.thesis_markdown(s, r), 'disclosure never relabeled as adjustment')
    bind_thesis(s, r)
    rows = views.thesis_rows(s, r)
    check([x['id'] for x in rows[0]['support']] == ['thesis_0', 'metric_eps_ttm'], 'explicit thesis link follows only actual premises')
    s['thesis'].append('第二項尚未建立證據連結的合成論點')
    check(views.thesis_rows(s, r)[1]['support'] == [] and views.thesis_rows(s, r)[1]['counter_cases'] == [], 'no cross-thesis evidence borrowing')
    args = finish(s, r)
    output = html_export.render(*args, '2026-10-16T12:00:00+08:00')
    check(html_export.verify(output, *args)['valid'], 'bound and partially unbound theses export honestly')
    check('未記錄對應反方' in output and '未記錄對應失效條件' in output, 'per-thesis gaps visible')
    check('前提主張：metric_eps_ttm' in output and '本次獲利主張' in output, 'support explanation rendered')
    check('合成附件表格之對應列' in output, 'selected source locator preserved')
    check('查核階段與結果' in output and '不是即時進度或持續監控' in output, 'workflow is an export-time record')
    check('data-label="支持依據"' in output and 'data-label="實際狀態"' in output, 'new tables carry mobile field labels')
    check('thesis_comparison_report' in review_guard.validate(r, s, args[2]), 'review API exposes shared text block')
    bad = deepcopy(r)
    bad['evidence_audit']['claims'][-1]['value'] = '錯誤的論點內容'
    check(not review_guard.validate(bad, s, args[2])['valid'], 'mismatched thesis target rejected by existing validator')
    bad = deepcopy(r)
    bad['evidence_audit']['counter_cases'][0]['claim_ids'] = ['invented']
    check(not review_guard.validate(bad, s, args[2])['valid'], 'unknown counter evidence rejected')
    for state, expected in [('not_run', '尚未執行'), ('partial', '尚未完成'),
                            ('access_failed', '存取失敗'), ('conflicting', '來源衝突'),
                            ('incompatible', '口徑不符'), ('not_published', '尚未公布')]:
        s, r = fixture()
        task = r['tasks'][3]  # events: valid not_published task
        task['status'] = state
        if state == 'not_run':
            task['attempts'] = []
        elif state not in ('partial', 'not_published'):
            task['attempts'][0]['result'] = {'access_failed':'blocked', 'conflicting':'conflict', 'incompatible':'incompatible'}[state]
            other = deepcopy(task['attempts'][0]);other.update(stage='alternative', request='合成替代來源核對')
            task['attempts'].append(other)
        task['reason'] = '合成作業缺口；取得後續資料再核對'
        args = finish(s, r)
        output = html_export.render(*args, '2026-10-16T12:00:00+08:00')
        check(views.task_rows(r)[3]['status'] == expected and expected in output, 'preserve task state '+state)
        check(r['assessment']['workflow_status'] == ('incomplete' if state in ('not_run','partial') else 'complete'), 'workflow completion differs from retrieval success '+state)
    s, r = fixture();r['evidence_audit']['counter_cases'][0]['disposition'] = 'unresolved'
    args = finish(s, r);output = html_export.render(*args, '2026-10-16T12:00:00+08:00')
    check('counter_case_1' in output and '證據充分性<b>不足' in output, 'unresolved counter never hidden by completed workflow')
    check('尚未解決' in output, 'unresolved disposition rendered')
    check(views.markdown_cell('a|b\n<script>') == 'a&#124;b &lt;script&gt;', 'markdown table and raw HTML escaped')
    s, r = fixture();s['thesis'][0] = '<img src=x onerror=alert(1)>'
    args = finish(s, r);output = html_export.render(*args, '2026-10-16T12:00:00+08:00')
    check('<img src=x' not in output and '&lt;img src=x' in output, 'untrusted thesis stays literal text')
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp);(temp/'s.json').write_bytes(args[2]);(temp/'r.json').write_bytes(args[3])
        command = [sys.executable, str(ROOT/'scripts/review_guard.py'), str(temp/'r.json'), '--research', str(temp/'s.json'), '--render']
        result = subprocess.run(command, capture_output=True, text=True)
        check(result.returncode == 0 and '多空論點對照' in json.loads(result.stdout)['thesis_comparison_report'], 'actual render CLI supplies authoring table')
    print(json.dumps({'passed': True, 'checks': checks, 'scope': 'synthetic record views, failure states, bindings and actual CLI; no live source or browser verification'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
