"""Build on the target OS. macOS produces dist/ImageSearch.app."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)

if importlib.util.find_spec('PyInstaller') is None:
    sys.exit('PyInstaller가 설치되어 있지 않습니다. 빌드 도구를 먼저 설치하세요:\n'
             f'  {sys.executable} -m pip install -r requirements-dev.txt')

args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--name', 'ImageSearch',
        '--icon', 'assets/icon.png',
        '--add-data', f'assets/icons{os.pathsep}assets/icons',
        '--exclude-module', 'tkinter', '--exclude-module', 'pytest',
        '--osx-bundle-identifier', 'local.imagesearch.desktop', 'main.py']
subprocess.run(args, check=True)
