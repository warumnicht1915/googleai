"""Real Chromium regression: results arrive without a popup or import click."""
import base64
import io
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton
from imagesearch.search import GoogleSearch

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
parent = QMainWindow()
root = tempfile.TemporaryDirectory()
search = GoogleSearch(Path(root.name), parent)
buf = io.BytesIO(); Image.new('RGB', (160,120), 'teal').save(buf, 'PNG')
source = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
fixture = f'<html><body><a href="https://www.google.com/imgres?imgurl=https%3A%2F%2Fexample.com%2Fimage.png&amp;imgrefurl=https%3A%2F%2Fexample.com%2Fpage"><img src="{source}" alt="자동 검색 테스트"></a></body></html>'
errors = []
stage = [0]

# Only replace navigation with a local fixture; the actual load signals,
# extraction script, timer, result handler, and visibility remain real Qt.
search.view.load = lambda url: search.page.setHtml(fixture, url)

def done(items):
    try:
        assert items[0]['url'] == 'https://example.com/image.png'
        assert not search.dialog.isVisible()
        assert not search.active
        assert not any(b.text() == '결과 가져오기' for b in search.dialog.findChildren(QPushButton))
        if stage[0] == 0:
            stage[0] = 1
            QTimer.singleShot(0, after_timeout)
        else:
            search.cancel()
            search.loaded(True)
            assert not search.active and not search.timer.isActive()
            print('PASS: automatic results, no import button, no timeout popup, automatic late-load recovery, cancelled search stays cancelled', flush=True)
            finish()
    except Exception as exc:
        errors.append(repr(exc)); finish()

def after_timeout():
    try:
        search.view.load = lambda url: None
        search.search('late', False)
        search.timeout()
        assert not search.dialog.isVisible() and search.awaiting_results
        # Google verification/late navigation finishes. No import click needed.
        search.page.setHtml(fixture, QUrl('https://www.google.com/search?q=late'))
    except Exception as exc:
        errors.append(repr(exc)); finish()

def finish():
    search.shutdown()
    QTimer.singleShot(200, app.quit)

search.results.connect(done)
search.search('automatic', False)
QTimer.singleShot(15000, lambda: (errors.append('timeout'), finish()))
app.exec()
for error in errors: print('FAIL:', error, flush=True)
root.cleanup()
sys.exit(bool(errors))
