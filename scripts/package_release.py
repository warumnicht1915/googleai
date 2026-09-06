"""Create a macOS release ZIP with symlinks preserved and SHA-256 checksum."""
import hashlib
from pathlib import Path
import platform
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from imagesearch import __version__
ROOT=Path(__file__).resolve().parents[1]
if sys.platform!='darwin':
    raise SystemExit('This packaging helper currently supports macOS only.')
app=ROOT/'dist/ImageSearch.app'
if not app.is_dir(): raise SystemExit('Build the app first: python scripts/build.py')
output=ROOT/'release-assets'; output.mkdir(exist_ok=True)
archive=output/f'ImageSearch-{__version__}-macos-{platform.machine()}.zip'
subprocess.run(['ditto','-c','-k','--keepParent','--norsrc','--noextattr',str(app),str(archive)],check=True)
digest=hashlib.sha256()
with archive.open('rb') as stream:
    for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
hash=digest.hexdigest()
(output/'SHA256SUMS.txt').write_text(f'{hash}  {archive.name}\n')
print(archive.name)
