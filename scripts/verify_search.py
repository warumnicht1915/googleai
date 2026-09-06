"""Exercise extraction in real Chromium against a controlled Google-layout fixture."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from imagesearch.search import EXTRACT_JS
app=QApplication([]); v=QWebEngineView(); errors=[]
fixture='''<html><body><div data-ri="0"><a href="https://example.com/page"><img alt="미쿠 캐릭터" src="https://encrypted-tbn0.gstatic.com/images?q=tbn:test"></a></div><script type="application/json">["https://encrypted-tbn0.gstatic.com/images?q=tbn:test",120,160],["https://example.com/original.png",900,1200]</script></body></html>'''
def ready(ok):
    v.page().runJavaScript("Object.defineProperty(document.images[0],'naturalWidth',{value:160}); Object.defineProperty(document.images[0],'naturalHeight',{value:120});",lambda _:v.page().runJavaScript(EXTRACT_JS,check))
def check(raw):
    try:
        data=json.loads(raw); i=data['items'][0]
        assert i['url']=='https://example.com/original.png',i
        assert i['title']=='미쿠 캐릭터' and i['width']==1200 and i['height']==900,i
        assert i['page_url']=='https://example.com/page',i
        print('PASS: Chromium extraction, original URL, Korean title, dimensions, source page',flush=True)
    except Exception as exc:
        errors.append(str(exc)); print('FAIL',repr(exc),raw,flush=True)
    app.quit()
v.loadFinished.connect(ready); v.setHtml(fixture,QUrl('https://www.google.com/search?q=test'))
QTimer.singleShot(15000,lambda:(errors.append('timeout'),app.quit()))
app.exec(); sys.exit(bool(errors))
