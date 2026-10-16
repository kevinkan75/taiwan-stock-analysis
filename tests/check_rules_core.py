"""Frozen pre-refactor outputs plus numeric boundaries of the shared production functions."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import rules_core as core
import snapshot_guard as g

count = 0


def check(ok, why):
    global count
    count += 1
    if not ok: raise AssertionError(why)


for case in json.loads((ROOT/'tests/shared_rules.baseline.json').read_text())['cases']:
    path = ROOT/case['input']; raw = path.read_bytes()
    check(hashlib.sha256(raw).hexdigest()==case['input_sha256'], 'archived fixture bytes preserved')
    s = json.loads(raw); result = g.validate(s, True)
    check(result['valid'], str(result['errors']))
    out = g.derived_snapshot(s,result)
    canonical = json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    check(hashlib.sha256(canonical).hexdigest()==case['derived_sha256'], 'exact pre-refactor output including provenance')
    check(g.validate(out)['valid'], 'archived derived output validates')
    check(path.read_bytes()==raw, 'validation does not rewrite archive')
for check_name, prices in [
    ('model_upside', [(89,0),(90,1),(115,1),(116,2)]),
    ('scenario_resilience', [(69,0),(70,1),(84,1),(85,2)]),
]:
    for price, expected in prices:
        check(core.valuation_threshold_score(check_name,price,100)==expected, 'exact valuation boundary')
for values, expected in [([2,None,None],None),([2,0,None],Fraction(50)),([2,2,1],Fraction(250,3))]:
    score, result = core.dimension_result(values,Fraction(1,4))
    check(score==expected and result['coverage']==sum(x is not None for x in values),'null is not neutral score')
check(core.weighted_total({'a':Fraction(50),'b':Fraction(100)},{'a':Fraction(1,4),'b':Fraction(3,20)},True)==Fraction(275,4),'explicit normalization uses original weights')
check(core.weighted_total({'a':None},{'a':Fraction(1)}) is None, 'no data cannot become zero total')
check(core.rounded(Fraction(149,2))==75 and core.light(Fraction(149,2))=='yellow','display rounding must not cross raw threshold')
print(json.dumps({'passed':True,'checks':count,'scope':'exact archived-output hashes and shared numeric production rules'}))
