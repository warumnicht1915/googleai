import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from imagesearch.ui import Window
from imagesearch.store import Store
from test_network import server

app=QApplication.instance() or QApplication([])

def test_download_button_and_offline_restart(server,tmp_path):
    w=Window(Store(tmp_path),browser=False); w.show()
    w.receive_results([{'url':server+'/image','title':'다운로드 테스트','source':'local fixture'}])
    ident=w.results[0]['id']
    QTest.mouseClick(w.cards[0].download,Qt.MouseButton.LeftButton)
    for _ in range(100):
        app.processEvents(); QTest.qWait(20)
        if not w.jobs: break
    assert not w.jobs
    saved=w.store.get(ident)
    assert Path(saved['download_path']).exists() and Path(saved['preview_path']).exists()
    w.toggle_like(ident); w.close(); app.processEvents()
    # A fresh window opens persisted previews without new network jobs.
    again=Window(Store(tmp_path),browser=False); again.navigate('downloads')
    assert len(again.cards)==1 and not again.jobs
    again.navigate('liked'); assert len(again.cards)==1 and not again.cards[0].pixmap.isNull()
    again.close(); app.processEvents()

def test_close_finishes_queued_downloads(server,tmp_path):
    w=Window(Store(tmp_path),browser=False); w.show()
    w.pool.setMaxThreadCount(1)
    records=[w.store.upsert({'url':server+'/image?'+str(n),'title':str(n)}) for n in range(4)]
    for item in records:
        item['url']=server+'/image'
        w.queue_image(item,'download')
    w.close()
    for _ in range(200):
        app.processEvents(); QTest.qWait(20)
        if not w.isVisible(): break
    assert not w.isVisible()
    reopened=Store(tmp_path)
    for item in records:
        assert Path(reopened.get(item['id'])['download_path']).exists()
    reopened.close()
