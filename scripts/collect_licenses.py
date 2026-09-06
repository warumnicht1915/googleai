"""Collect redistributable license notices from installed runtime dependencies."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sysconfig

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ['requests','urllib3','idna','certifi','charset-normalizer','Pillow','PyInstaller']

def main():
    for name in PACKAGES:
        dist=distribution(name)
        for file in dist.files or []:
            if any(part.lower().startswith(('license','copying','notice')) for part in file.parts):
                source=Path(dist.locate_file(file))
                if source.is_file():
                    target=ROOT/'third_party'/name/source.name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,target)
    license_path=Path(sysconfig.get_path('stdlib'))/'LICENSE.txt'
    if license_path.exists():
        target=ROOT/'third_party/Python/LICENSE.txt'; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(license_path,target)
    print('Installed dependency notices collected.')

if __name__=='__main__': main()
