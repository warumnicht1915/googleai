"""Check public files and frozen Python archives without printing private values."""
import argparse
from pathlib import Path
import re
import zipfile

SKIP={'.git','.venv','__pycache__','.pytest_cache','build','dist','release-assets'}
TOKENS=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
PRIVATE_NAMES={'Cookies','Login Data','Web Data','library.sqlite3','app.lock','.env'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path)
    parser.add_argument('--private-marker',action='append',default=[])
    args=parser.parse_args(); root=args.root.resolve()
    markers=[s.encode() for s in args.private_marker if s]
    failures=[]; count=0
    def check(data,label):
        if TOKENS.search(data) or any(m in data for m in markers): failures.append(label)
    for path in root.rglob('*'):
        relative=path.relative_to(root)
        if set(relative.parts)&SKIP or path.name in {'.build-stage'}: continue
        if not path.is_file(): continue
        count+=1
        label=str(relative)
        if path.name in PRIVATE_NAMES or path.suffix in {'.sqlite3','.db','.log'}:
            failures.append(label+' (private/generated file)')
        data=path.read_bytes(); check(data,label)
        if path.suffix=='.zip':
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist(): check(archive.read(name),label+'!'+name)
        # PyInstaller compresses Python code, so inspect decompressed entries too.
        if path.name=='ImageSearch' and path.parent.name=='MacOS':
            from PyInstaller.archive.readers import CArchiveReader
            archive=CArchiveReader(str(path))
            for name,entry in archive.toc.items():
                if entry[-1]=='z':
                    pyz=archive.open_embedded_archive(name)
                    for module in pyz.toc:
                        check(pyz.extract(module,raw=True) or b'',label+'!'+module)
                else:
                    check(archive.extract(name) or b'',label+'!'+name)
    if failures:
        for label in sorted(set(failures)): print('REVIEW:',label)
        raise SystemExit(1)
    print(f'PASS: {count} public files; private markers, credential patterns, private data files and frozen Python archives checked.')

if __name__=='__main__': main()
