"""Export the bundled Chromium's own third-party license notice page."""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
app=QApplication([]); view=QWebEngineView(); outcome=[1]
root=Path(__file__).resolve().parents[1]/'third_party/Chromium'
root.mkdir(parents=True,exist_ok=True)
def save(html):
    if len(html)>10000 and 'license' in html.lower():
        (root/'credits.html').write_text(html)
        outcome[0]=0
        print('Chromium license notices exported.',flush=True)
    app.quit()
view.loadFinished.connect(lambda ok: view.page().toHtml(save))
view.load(QUrl('chrome://credits'))
QTimer.singleShot(15000,app.quit)
app.exec(); raise SystemExit(outcome[0])
