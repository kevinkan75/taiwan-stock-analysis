"""Read-only views of existing review records; no inference, scoring or network."""

TASK_LABELS = {
    'quote': '行情', 'financials': '財報', 'valuation': '估值', 'events': '事件',
    'growth': '成長', 'industry': '產業', 'fund_rules': '基金規則',
    'cost_tracking': '成本與追蹤', 'holdings': '持股', 'distribution': '配息',
    'market': '市場', 'technical': '技術面', 'expectations': '市場預期',
    'exit_conditions': '退場條件',
}
TASK_STATUSES = {
    'obtained': '已取得並核對', 'not_run': '尚未執行', 'partial': '尚未完成',
    'not_published': '尚未公布', 'access_failed': '存取失敗',
    'conflicting': '來源衝突', 'incompatible': '口徑不符', 'not_applicable': '不適用',
}
VERDICTS = {'supported': '已核對（依紀錄）', 'reviewed': '已檢視推論／假設',
            'unresolved': '尚未解決', 'refuted': '已移除的錯誤主張'}
DISPOSITIONS = {'adjusted': '已調整（依原紀錄）',
                'disclosed': '已揭露；不代表已調整評分', 'unresolved': '尚未解決'}


def claim_records(ids, claims):
    """Keep explicit links and their premises, not nearby or similarly named data."""
    result, seen = [], set()

    def add(key):
        if key in seen:
            return
        seen.add(key)
        claim = claims.get(key)
        if claim is None:
            return  # The source validator rejects unknown references.
        result.append(claim)
        for parent in claim['premises']:
            add(parent)

    for key in ids:
        add(key)
    return result


def thesis_rows(research, record):
    audit = record.get('evidence_audit', {})
    claims = {x['id']: x for x in audit.get('claims', [])}
    rows = []
    for index, thesis in enumerate(research['thesis']):
        target = 'research:/thesis/' + str(index)
        support = [x['id'] for x in claims.values()
                   if target in x['targets'] and x['verdict'] != 'refuted']
        rows.append({
            'index': index, 'thesis': thesis,
            'support': claim_records(support, claims),
            'counter_cases': [dict(x, evidence=claim_records(x['claim_ids'], claims))
                              for x in audit.get('counter_cases', []) if x['thesis_index'] == index],
            'conditions': [dict(x, evidence=claim_records(x['claim_ids'], claims))
                           for x in audit.get('invalidation_conditions', []) if x['thesis_index'] == index],
        })
    return rows


def task_rows(record):
    return [{'id': t['id'], 'label': TASK_LABELS.get(t['id'], t['id']),
             'status': TASK_STATUSES[t['status']], 'reason': t['reason'],
             'attempts': t['attempts']} for t in record['tasks']]


def markdown_cell(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\r', ' ').replace('\n', ' ')


def thesis_markdown(research, record):
    """Optional authoring block; the finalized report still requires normal binding."""
    lines = ['### 多空論點對照', '',
             '沿用本次主張與查核紀錄；未建立連結不等於沒有證據，亦不表示已完成交叉審查。', '',
             '| 原始論點 | 支持依據 | 反方質疑 | 處理結果 | 重新評估條件 |',
             '| --- | --- | --- | --- | --- |']
    for row in thesis_rows(research, record):
        support = '；'.join(x['id'] + '：' + x['statement'] + '（' + VERDICTS[x['verdict']] + '）' for x in row['support']) or '未建立明確主張連結'
        counter = '；'.join(x['scenario'] + '〔主張：' + '、'.join(x['claim_ids']) + '〕' for x in row['counter_cases']) or '未記錄對應反方'
        outcome = '；'.join(DISPOSITIONS[x['disposition']] + '：' + x['impact'] + '；後續：' + x['follow_up'] for x in row['counter_cases']) or '未記錄處理結果'
        conditions = '；'.join(x['observable'] + '；' + x['trigger'] + '；' + x['review_on'] for x in row['conditions']) or '未記錄對應失效條件'
        lines.append('| ' + ' | '.join(markdown_cell(x) for x in (row['thesis'], support, counter, outcome, conditions)) + ' |')
    if not research['thesis']:
        lines.extend(['', '尚未形成投資論點，未產生多空對照。'])
    return '\n'.join(lines)
