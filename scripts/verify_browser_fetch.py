"""Prove the browser fallback really recovers a download that plain HTTP cannot get.

A local host serves the image only to a request carrying a cookie it hands out on
its own page. `requests` never sees that cookie, so the normal path is refused;
Chromium visited the page, so the fallback succeeds.
"""
import io
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox --disable-gpu --disable-dev-shm-usage')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication, QWidget
from imagesearch.network import ImageJob
from imagesearch.search import GoogleSearch

COOKIE = 'gate=open'


def artwork():
    buffer = io.BytesIO()
    Image.new('RGB', (700, 500), '#4466aa').save(buffer, 'PNG')
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/post':
            self.send_response(200)
            self.send_header('Set-Cookie', COOKIE + '; Path=/')
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'<!doctype html><title>post</title><p>gate opened')
            return
        if self.path == '/art.png':
            if COOKIE not in self.headers.get('Cookie', ''):
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'no hotlinking')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            self.wfile.write(artwork())
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


def main():
    service = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=service.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{service.server_port}'
    image_url, page_url = base + '/art.png', base + '/post'

    workspace = tempfile.TemporaryDirectory()
    root = Path(workspace.name)
    downloads = root / 'downloads'
    downloads.mkdir()

    app = QApplication([])
    parent = QWidget()
    searcher = GoogleSearch(root, parent)
    report = []

    # 1. The plain HTTP path must refuse, not silently succeed.
    refusals = []
    job = ImageJob({'id': 'gated', 'url': image_url, 'page_url': page_url}, downloads, 'download')
    job.signals.refused.connect(lambda ident, kind, url: refusals.append(url))
    job.signals.done.connect(lambda *a: refusals.append('UNEXPECTED SUCCESS'))
    job.run()
    report.append(f'plain HTTP refused: {refusals == [image_url]}')

    # 2. Let Chromium visit the page so the profile holds the cookie.
    outcome = {}
    searcher.fetched.connect(lambda ident, path: outcome.setdefault('path', path))
    searcher.fetch_failed.connect(lambda ident, message: outcome.setdefault('error', message))

    def after_visit(ok):
        searcher.view.loadFinished.disconnect(after_visit)
        searcher.browser_fetch('gated', image_url, page_url, downloads)

    searcher.view.loadFinished.connect(after_visit)
    searcher.view.load(QUrl(page_url))

    QTimer.singleShot(25000, app.quit)
    timer = QTimer()
    timer.setInterval(200)
    timer.timeout.connect(lambda: app.quit() if outcome else None)
    timer.start()
    app.exec()

    saved = outcome.get('path', '')
    ok = bool(saved) and Path(saved).exists() and Path(saved).read_bytes() == artwork()
    report.append(f'browser fallback recovered the file: {ok}')
    if not ok:
        report.append(f'  detail: {outcome or "no response before the timeout"}')

    searcher.shutdown()
    app.processEvents()
    service.shutdown()
    service.server_close()
    print('\n'.join(report))
    workspace.cleanup()
    return 0 if ok and refusals == [image_url] else 1


if __name__ == '__main__':
    sys.exit(main())
