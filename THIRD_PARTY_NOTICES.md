# Third-party notices

ImageSearch uses unmodified Python, PySide6/Qt, Qt WebEngine/Chromium, Requests,
Pillow, the Lucide icon set, and the dependencies shipped with them. Their
copyright and license notices remain applicable and are included in
`third_party/`, `assets/icons/LICENSE.txt`, and the app bundle.

- Python: PSF license. https://www.python.org/downloads/source/
- PySide6 / Shiboken 6.11.2: LGPLv3/GPL alternatives. https://code.qt.io/cgit/pyside/pyside-setup.git/
- Qt 6.11.2: LGPLv3/GPL alternatives for the included Qt modules. https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/
- Qt WebEngine / Chromium: Qt and third-party notices. https://doc.qt.io/qt-6/qtwebengine-licensing.html
- Requests, urllib3, idna, certifi, charset-normalizer and Pillow: license texts collected from their installed distributions.
- PyInstaller: GPL with bootloader exception; see the included COPYING text.
- Lucide icons: ISC License. https://lucide.dev — the SVG files in `assets/icons/`
  are used unmodified at build time and recolored at runtime. The full license
  text ships alongside them in `assets/icons/LICENSE.txt`.

Qt and PySide are dynamically linked in this application. This project does not
restrict replacement/debugging of those libraries as permitted by their licenses.
To rebuild with modified libraries, install the corresponding versions in a
virtual environment and run `python scripts/build.py`. On macOS, a modified
bundle may need local re-signing. No external notarization is included.

This notice does not assign a new license to this project's own source code.
