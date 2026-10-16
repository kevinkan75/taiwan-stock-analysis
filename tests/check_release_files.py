"""Public distribution invariants; --git also simulates a Windows LF checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git', action='store_true')
    args = parser.parse_args()
    checks = 0
    def check(ok, reason):
        nonlocal checks
        checks += 1
        if not ok:
            raise AssertionError(reason)
    attrs = (ROOT / '.gitattributes').read_text(encoding='utf-8')
    ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    check('* text=auto eol=lf' in attrs and '*.json text eol=lf' in attrs, 'LF policy covers exact-byte fixtures')
    check('允許商業使用' in readme and '但請勿將本技能或其輸出包裝成收費服務' not in readme, 'README agrees with permissive MIT terms')
    check('實驗功能' in readme and '尚未' in readme, 'HTML acceptance limitation visible')
    for rel in ['scripts/run_checks.py', '.github/workflows/checks.yml', 'references/html-report.md']:
        check((ROOT / rel).is_file(), 'release resource exists: ' + rel)
    for directory in ['scripts', 'tests', 'references', 'assets']:
        for path in sorted((ROOT / directory).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            if path.suffix in ('.py', '.json', '.js', '.css', '.html', '.md', '.svg'):
                check(b'\r\n' not in path.read_bytes(), 'source or fixture unexpectedly converted: ' + str(path.relative_to(ROOT)))
    # Existing archive checks are independent, fixed hashes recorded before this release prep.
    for version in ['1.12.0', '1.13.0']:
        baseline=json.loads((ROOT / ('tests/release-' + version + '.baseline.json')).read_bytes())
        for rel, expected in baseline['files'].items():
            check(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == expected, 'historical bytes retained: ' + rel)
    if args.git:
        git=shutil.which('git')
        if not git:
            raise AssertionError('--git requires Git; checkout acceptance was not performed')
        def run(argv, cwd):
            return subprocess.run([git] + argv, cwd=str(cwd), check=True, capture_output=True, text=True, encoding='utf-8')
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);source=temp/'source';source.mkdir();target=temp/'checkout'
            run(['init','-q'],source)
            (source/'.gitattributes').write_bytes((ROOT/'.gitattributes').read_bytes())
            (source/'.gitignore').write_bytes((ROOT/'.gitignore').read_bytes())
            (source/'assets').mkdir()
            fixture=(ROOT/'assets/snapshot.example.json').read_bytes()
            (source/'assets/snapshot.example.json').write_bytes(fixture)
            run(['-c','core.autocrlf=false','add','.'],source)
            run(['-c','user.name=Release Test','-c','user.email=release-test@example.invalid','commit','-qm','LF fixture'],source)
            run(['clone','-q','--config','core.autocrlf=true',str(source),str(target)],temp)
            check((target/'assets/snapshot.example.json').read_bytes()==fixture, 'autocrlf=true clone retains exact UTF-8/LF bytes')
            attr=run(['check-attr','eol','--','assets/snapshot.example.json'],target).stdout
            check(attr.strip().endswith(': lf'), 'checkout has explicit LF attribute')
            for rel in ['__pycache__/x.pyc','.env','.env.local','outputs/demo.html','reports/private.json','local-data/input.json','dist/package.zip']:
                result=subprocess.run([git,'check-ignore',rel],cwd=str(target),capture_output=True)
                check(result.returncode==0,'generated/private path ignored: '+rel)
            for rel in ['assets/snapshot.example.json','scripts/run_checks.py','.github/workflows/checks.yml']:
                result=subprocess.run([git,'check-ignore','--no-index',rel],cwd=str(target),capture_output=True)
                check(result.returncode==1,'public source stays visible: '+rel)
    print(json.dumps({'passed':True,'checks':checks,'git_checkout_tested':args.git,
                     'scope':'release files and frozen bytes; git mode uses a local clone, not a real Windows host'},ensure_ascii=False))


if __name__=='__main__':
    main()
