"""Build on the target OS. macOS produces dist/ImageSearch.app."""
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
os.chdir(root)
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','ImageSearch',
      '--icon','assets/icon.png',
      '--add-data', f'assets/icons{os.pathsep}assets/icons',
      '--exclude-module','tkinter','--exclude-module','pytest',
      '--osx-bundle-identifier','local.imagesearch.desktop','main.py']
subprocess.run(args,check=True)
