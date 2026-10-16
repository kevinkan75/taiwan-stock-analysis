"""Offline claim bindings and bounded arithmetic; external truth remains manual."""
from datetime import date
import math

from rules_core import finite


def same(a, b):
    return a == b and (type(a) is type(b) or finite(a) and finite(b))


def pointer(document, path):
    if not path.startswith('/'):
        raise ValueError('JSON pointer must start with /')
    for token in path[1:].split('/'):
        token = token.replace('~1', '/').replace('~0', '~')
        document = document[int(token)] if isinstance(document, list) else document[token]
    return document


def required_targets(research, dec=None):
    """Mechanical minimum, not a semantic inventory of every report sentence."""
    targets = set()
    for key, metric in research['metrics'].items():
        if metric['value'] is not None:
            key = key.replace('~', '~0').replace('/', '~1')
            targets.add('research:/metrics/' + key + '/value')
    for dimension, body in research['scores'].items():
        for i, item in enumerate(body['items']):
            if item['score'] is not None:
                targets.add(f'research:/scores/{dimension}/items/{i}/score')
    for i, scenario in enumerate(research.get('valuation', {}).get('scenarios', [])):
        if scenario['model_price'] is not None:
            targets.add(f'research:/valuation/scenarios/{i}/model_price')
    for i, event in enumerate(research.get('events', [])):
        targets.add(f'research:/events/{i}/description')
    if dec:
        targets.update(f'decision:/gates/{i}/signal' for i in range(8))
    return targets


def calculate(recipe):
    """No eval, executable formula strings, implicit unit conversion or rounding."""
    values = recipe['inputs']
    if not values or not all(finite(x) for x in values):
        raise ValueError('finite operands required')
    op = recipe['method']
    if op == 'sum':
        result = math.fsum(values)
    elif op == 'product':
        result = 1
        for x in values:
            result *= x
    elif op == 'subtract' and len(values) == 2:
        result = values[0] - values[1]
    elif op in ('divide', 'ratio_pct', 'change_pct') and len(values) == 2:
        if values[1] == 0:
            raise ValueError('zero denominator')
        if op == 'change_pct' and values[1] < 0:
            raise ValueError('negative growth base requires manual treatment')
        result = values[0] / values[1]
        result = (result - 1) * 100 if op == 'change_pct' else result * 100 if op == 'ratio_pct' else result
    else:
        raise ValueError('unsupported operation or operand count')
    if not finite(result):
        raise ValueError('nonfinite result')
    return result


def audit_state(audit):
    unresolved = [x['id'] for x in audit['claims'] if x['verdict'] in ('unresolved', 'refuted')]
    material = [x['id'] for x in audit['claims'] if x['material'] and x['id'] in unresolved]
    material += ['counter_case_'+str(i+1) for i,x in enumerate(audit['counter_cases']) if x['disposition']=='unresolved']
    return {'status': audit['status'], 'claims': len(audit['claims']),
            'unresolved_claims': unresolved, 'material_unresolved': material,
            'thesis_status': audit['thesis_status']}


def validate(audit, research, dec, registered, cutoff):
    """Input shape is checked by review.schema.json before this function."""
    errors = []
    report = (dec or research)['report_markdown']
    claims = {x['id']: x for x in audit['claims']}
    if len(claims) != len(audit['claims']):
        errors.append('audit: duplicate claim id')
    targets = {}
    graph = {}
    for claim in audit['claims']:
        label = 'audit.' + claim['id']
        kind, verdict, sources = claim['kind'], claim['verdict'], claim['sources']
        graph[claim['id']] = claim['premises']
        if not claim['targets'] and not claim['report_excerpt'] and verdict!='refuted':
            errors.append(label + ': requires a target or actual report excerpt')
        if verdict=='refuted' and (claim['targets'] or claim['report_excerpt'] or claim['statement'] in report):
            errors.append(label + ': refuted claim must be removed from report and active targets')
        if claim['report_excerpt'] and claim['report_excerpt'] not in report:
            errors.append(label + ': report excerpt missing from final report')
        for target in claim['targets']:
            try:
                scope, path = target.split(':', 1)
                obj = {'research': research, 'decision': dec}[scope]
                value = pointer(obj, path)
                if isinstance(value, (dict, list)) or type(value) is not type(claim['value']) and not (finite(value) and finite(claim['value'])):
                    raise ValueError('scalar value type mismatch')
                if not same(value, claim['value']):
                    raise ValueError('claim value differs from target')
                if target in required_targets(research, dec) and not claim['material']:
                    raise ValueError('required numeric/score/event claims are material')
                if scope=='research' and path.startswith('/metrics/') and path.endswith('/value'):
                    metric=pointer(research,path.rsplit('/',1)[0])
                    if metric.get('value_status')=='calculated':
                        allowed={'calculation'}
                    elif metric.get('source_type')=='company_guidance':
                        allowed={'guidance'}
                    elif metric.get('actual_or_estimate')=='estimate' or metric.get('value_status')=='estimated' or metric.get('source_type')=='external_estimate':
                        allowed={'estimate'}
                    else:
                        allowed={'fact'}
                    if kind not in allowed:
                        raise ValueError('metric kind contradicts its declared evidence type')
                    if any(claim[field]!=metric[field] for field in ('unit','period','basis')):
                        raise ValueError('claim unit, period or basis differs from metric')
                if '/scores/' in path or scope=='decision' and path.startswith('/gates/'):
                    if kind!='inference':
                        raise ValueError('scores/gates are judgments, not verified facts')
                if path.startswith('/valuation/scenarios/') and path.endswith('/model_price') and kind!='calculation':
                    raise ValueError('model price requires a documented calculation')
                if path.startswith('/events/') and kind not in ('fact','guidance'):
                    raise ValueError('announced event requires factual verification')
                if target in targets:
                    raise ValueError('target already audited; reuse the claim id')
                targets[target] = claim['id']
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                errors.append(label + ': invalid binding ' + target + ': ' + str(exc))
        for source in sources:
            if source['url'] not in registered:
                errors.append(label + ': unregistered source')
            if date.fromisoformat(source['published_at']) > cutoff.date():
                errors.append(label + ': evidence published after cutoff')
            if source['retrieval'] == 'memory' and verdict == 'supported':
                errors.append(label + ': model memory cannot verify a fact')
        index = claim['selected_source']
        selected = None
        if index is not None:
            if index >= len(sources):
                errors.append(label + ': selected source index out of range')
            else:
                selected = sources[index]
        if kind in ('assumption', 'inference'):
            if verdict == 'supported':
                errors.append(label + ': assumptions and judgments are reviewed, not verified facts')
            if kind == 'inference' and verdict == 'reviewed' and not claim['premises']:
                errors.append(label + ': reviewed inference requires premises')
        elif verdict == 'reviewed':
            errors.append(label + ': factual/calculated claims cannot use reviewed verdict')
        if kind in ('fact', 'guidance', 'estimate') and verdict == 'supported':
            if selected is None:
                errors.append(label + ': supported fact requires a selected source')
            else:
                if selected['retrieval']=='memory' or not same(selected['value'],claim['value']) or selected['period'] != claim['period'] or selected['basis'] != claim['basis']:
                    errors.append(label + ': selected evidence value, period or basis differs')
                comparable = [x for x in sources if x['period'] == claim['period'] and x['basis'] == claim['basis'] and x['retrieval'] != 'memory']
                if comparable:
                    best = max(comparable, key=lambda x: (x['rank'] == 'primary', x['published_at']))
                    peers=[x for x in comparable if (x['rank'],x['published_at'])==(best['rank'],best['published_at'])]
                    if any(not same(x['value'],selected['value']) for x in peers):
                        errors.append(label + ': conflict must prefer primary then latest dated comparable source; do not average')
        recipe = claim['calculation']
        if kind == 'calculation' and verdict == 'supported':
            if recipe is None or not claim['premises']:
                errors.append(label + ': calculation requires recipe and input claims')
            else:
                if recipe['method'] != 'manual':
                    try:
                        result = calculate(recipe)
                        if not finite(claim['value']) or not math.isclose(result, claim['value'], rel_tol=1e-9, abs_tol=1e-9):
                            errors.append(label + ': arithmetic mismatch')
                        operands = [claims[x]['value'] for x in claim['premises'] if x in claims]
                        if not all(finite(x) for x in operands) or len(operands)!=len(recipe['inputs']) or not all(same(a,b) for a,b in zip(operands,recipe['inputs'])):
                            errors.append(label + ': operands differ from ordered input claims')
                    except (ValueError, OverflowError) as exc:
                        errors.append(label + ': ' + str(exc))
                elif not recipe['reason'].strip():
                    errors.append(label + ': manual calculation requires documented verification')
        elif recipe is not None:
            errors.append(label + ': calculation recipe only belongs to supported calculation')
        for parent in claim['premises']:
            if parent not in claims or parent == claim['id']:
                errors.append(label + ': unknown/self premise')
            elif verdict in ('supported', 'reviewed') and claims[parent]['verdict'] in ('unresolved', 'refuted'):
                errors.append(label + ': unresolved input cannot support a resolved claim')
    visiting, visited = set(), set()

    def visit(key):
        if key in visiting:
            errors.append('audit: circular claim dependency')
            return
        if key in visited:
            return
        visiting.add(key)
        for parent in graph.get(key, []):
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)
    if audit['status'] == 'complete':
        missing = sorted(required_targets(research, dec) - targets.keys())
        if missing:
            errors.append('audit: missing claim coverage: ' + ', '.join(missing))
        if audit['thesis_status'] == 'established':
            if len(audit['counter_cases']) != 3 or not audit['invalidation_conditions']:
                errors.append('audit: established thesis requires three counter cases and an invalidation condition')
        elif research['overall']['signal'] != 'unknown':
            errors.append('audit: insufficient thesis cannot accompany an overall investment signal')
    for category in ('counter_cases', 'invalidation_conditions'):
        for item in audit[category]:
            if item['thesis_index'] >= len(research['thesis']):
                errors.append('audit: counter case/invalidation must link to an actual thesis')
            if item['report_excerpt'] not in report:
                errors.append('audit: counter case/invalidation excerpt missing from report')
            if not item['claim_ids'] or any(x not in claims for x in item['claim_ids']):
                errors.append('audit: counter case/invalidation requires existing claim references')
    state = audit_state(audit)
    if dec and dec['conclusion']['action'] in ('enter', 'staged'):
        if audit['status'] != 'complete' or audit['thesis_status'] != 'established' or state['material_unresolved']:
            errors.append('audit: incomplete or materially unresolved audit cannot support entry/staging')
    return errors
