"""Google renders in Chromium; no CAPTCHA bypass or account credentials needed.

Results are paged: the first batch arrives as `results`, and every later batch
(from scrolling Google's grid) arrives as `more_results`.
"""
from __future__ import annotations
import json
import os
from urllib.parse import urlencode, urlparse, parse_qs
from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Qt, QThreadPool
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineDownloadRequest
from PySide6.QtWebEngineWidgets import QWebEngineView

RESULT_CAP = 500

# DOM thumbnails + Google's image tuple metadata. Keep parsing isolated: Google can change it.
EXTRACT_JS = r'''(() => {
 const output=[], seen=new Set();
 const add=(url,thumb,title,source,page,width=0,height=0)=>{
   if(!url || !/^https?:\/\//.test(url) || seen.has(url))return;
   if(/google\.[^/]+\/(logos|images|search)|gstatic.com\/(images\/branding|ui)/.test(url))return;
   seen.add(url); output.push({url,thumbnail:thumb||url,title:title||'Google 이미지',source:source||'',page_url:page||'',width,height});
 };
 const decode=s=>{try{return JSON.parse('"'+s+'"')}catch(e){return s.replace(/\\u003d/g,'=').replace(/\\u0026/g,'&')}};
 const metadata=new Map();
 for(const script of document.scripts){
   const re=/\[\s*"(https?:[^"\n]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*\]\s*,\s*\[\s*"(https?:[^"\n]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*\]/g;
   let m; while((m=re.exec(script.textContent))!==null){
     const thumb=decode(m[1]),original=decode(m[4]);
     if(/encrypted-tbn|gstatic/.test(thumb))metadata.set(thumb,{url:original,width:+m[6],height:+m[5]});
   }
 }
 for(const img of document.images){
   const thumb=img.currentSrc||img.src||img.dataset.src;
   if(!thumb || img.naturalWidth<70 || img.naturalHeight<60)continue;
   const a=img.closest('a'), box=img.closest('[data-ri]')||img.closest('[data-docid]')||a?.parentElement||img.parentElement;
   let original='',page='',title=img.alt||'',source='';
   const href=a?.href||'';
   try{const u=new URL(href);original=u.searchParams.get('imgurl')||'';page=u.searchParams.get('imgrefurl')||'';}catch(e){}
   const meta=metadata.get(thumb);
   if(meta)original=meta.url;
   if(!page && box){
     const link=Array.from(box.querySelectorAll('a[href^="http"]')).find(x=>!/^https?:\/\/([^/]*\.)?google\./.test(x.href));
     if(link)page=link.href;
   }
   if(!title && box)title=(box.innerText||'').split('\n').filter(Boolean).slice(0,2).join(' · ');
   try{source=new URL(page||original).hostname;}catch(e){}
   if(original)add(original,thumb,title,source,page,meta?.width||0,meta?.height||0);
 }
 // Some Google layouts keep originals in script tuples before images become visible.
 for(const [thumb,meta] of metadata){add(meta.url,thumb,'Google 이미지',(()=>{try{return new URL(meta.url).hostname}catch(e){return ''}})(),'',meta.width,meta.height);}
 return JSON.stringify({items:output.slice(0,__CAP__),url:location.href,count:output.length});
})()'''.replace('__CAP__', str(RESULT_CAP))

# Google's image grid appends rows on scroll and hides the rest behind a "more results" button.
SCROLL_JS = r'''(() => {
 const root=document.scrollingElement||document.documentElement;
 const before=root.scrollHeight;
 window.scrollTo(0,root.scrollHeight);
 for(const node of document.querySelectorAll('div,section')){
   if(node.scrollHeight>node.clientHeight+200 && node.clientHeight>400)node.scrollTop=node.scrollHeight;
 }
 const labels=/더\s*보기|결과 더보기|더 많은 결과|More results|Show more|See more/i;
 const clickable=Array.from(document.querySelectorAll('input[type=button],button,div[role=button],a[role=button]'));
 for(const node of clickable){
   const text=(node.innerText||node.value||node.getAttribute('aria-label')||'').trim();
   if(labels.test(text) && node.offsetParent!==null){node.click(); break;}
 }
 return before;
})()'''


class GoogleSearch(QObject):
    results = Signal(list)
    more_results = Signal(list)
    status = Signal(str)
    busy = Signal(bool)
    more_state = Signal(bool)   # True while another page may still be available
    fetched = Signal(str, str)  # id, temporary path — pulled through Chromium
    fetch_failed = Signal(str, str)

    POLL_MS = 750
    FIRST_DEADLINE_MS = 30000
    MORE_DEADLINE_MS = 18000
    IDLE_LIMIT = 5

    def __init__(self, root, parent):
        super().__init__(parent)
        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle('Google 검색 확인 · ImageSearch')
        self.dialog.resize(1120, 780)
        layout = QVBoxLayout(self.dialog)
        label = QLabel('Google 확인을 완료하면 이미지를 자동으로 가져옵니다. 별도의 가져오기 버튼을 누를 필요가 없습니다.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.profile = QWebEngineProfile('ImageSearch', self)
        self.profile.setPersistentStoragePath(str(root / 'browser'))
        self.profile.setCachePath(str(root / 'browser-cache'))
        self.view = QWebEngineView(self.dialog)
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        reload = QPushButton('새로고침'); reload.clicked.connect(self.view.reload)
        close = QPushButton('닫기'); close.clicked.connect(self.dialog.hide)
        row.addWidget(reload); row.addStretch(); row.addWidget(close)
        layout.addLayout(row)
        self.view.loadFinished.connect(self.loaded)
        self.timer = QTimer(self); self.timer.setInterval(self.POLL_MS); self.timer.timeout.connect(self.tick)
        self.deadline = QTimer(self); self.deadline.setSingleShot(True); self.deadline.timeout.connect(self.timeout)
        self.active = False
        self.mode = 'initial'
        self.ready = False
        self.exhausted = True
        self.idle_ticks = 0
        self.generation = 0
        self.query = ''
        self.expected_query = ''
        self.awaiting_results = False
        self.seen: set[str] = set()
        self.api_key = os.environ.get('SERPAPI_API_KEY', '')
        self.api_mode = bool(self.api_key)
        self.api_page = 0
        self.api_jobs = []
        self.api_pool = QThreadPool(self)
        self.api_pool.setMaxThreadCount(2)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.browser_context_menu)
        # A second, never-shown page used only to pull images that refuse plain HTTP.
        self.fetch_page = QWebEnginePage(self.profile, self)
        self.fetch_jobs = {}
        self.profile.downloadRequested.connect(self.on_download_requested)

    # ---------- search lifecycle ----------

    def search(self, query, anime=True):
        self.cancel()
        self.query = query
        self.seen = set()
        self.ready = False
        self.exhausted = False
        self.api_page = 0
        self.mode = 'initial'
        self.idle_ticks = 0
        self.dialog.hide()
        self.more_state.emit(False)
        params = {'q': query + (' 2D anime character illustration' if anime else ''),
                  'udm': '2', 'hl': 'ko', 'safe': 'active'}
        self.active = True
        self.awaiting_results = True
        self.expected_query = params['q']
        self.busy.emit(True)
        self.status.emit('Google에서 이미지를 찾고 있습니다…')
        if self.api_mode:
            self.start_api(params['q'], 0)
            return
        # A tall offscreen viewport makes Google lay out far more of the grid per load.
        if not self.dialog.isVisible():
            self.view.resize(1280, 2400)
        self.view.load(QUrl('https://www.google.com/search?' + urlencode(params)))
        self.timer.start(); self.deadline.start(self.FIRST_DEADLINE_MS)

    def load_more(self):
        if self.active or self.exhausted:
            return
        if self.api_mode:
            self.api_page += 1
            self.active = True
            self.busy.emit(True)
            self.status.emit('다음 페이지를 불러오는 중…')
            self.start_api(self.expected_query, self.api_page)
            return
        if not self.ready:
            return
        self.mode = 'more'
        self.active = True
        self.idle_ticks = 0
        self.busy.emit(True)
        self.status.emit('더 많은 이미지를 불러오는 중…')
        self.tick()
        self.timer.start(); self.deadline.start(self.MORE_DEADLINE_MS)

    def loaded(self, ok):
        # A verification/navigation can finish after the initial search timed out.
        # Resume automatically for this search, never for a cancelled one.
        if self.awaiting_results and not self.api_mode and not self.ready:
            self.mode = 'initial'
            self.active = True
            self.timer.start()
            self.deadline.start(self.FIRST_DEADLINE_MS)
            self.busy.emit(True)
            self.extract()

    def tick(self):
        if not self.active:
            return
        if self.mode == 'more':
            self.page.runJavaScript(SCROLL_JS)
        self.extract()

    def extract(self):
        if not self.active:
            return
        generation = self.generation
        self.page.runJavaScript(EXTRACT_JS, lambda raw: self.receive(raw, generation))

    def receive(self, raw, generation):
        if not self.active or generation != self.generation:
            return
        try:
            data = json.loads(raw or '{}')
        except (ValueError, TypeError):
            return
        if parse_qs(urlparse(data.get('url', '')).query).get('q', [''])[0] != self.expected_query:
            return
        fresh = [i for i in data.get('items', []) if i.get('url') and i['url'] not in self.seen]
        for item in fresh:
            self.seen.add(item['url'])
        if self.mode == 'initial':
            if fresh:
                self.ready = True
                self.exhausted = False
                self.settle()
                self.dialog.hide()
                self.results.emit(fresh)
                self.status.emit(f'Google 이미지 {len(fresh)}개를 찾았습니다. 아래로 스크롤하면 더 불러옵니다.')
                self.more_state.emit(True)
            return
        if fresh:
            self.idle_ticks = 0
            self.more_results.emit(fresh)
            self.status.emit(f'이미지 {len(self.seen)}개를 모았습니다.')
            if len(self.seen) >= RESULT_CAP:
                self.finish_more(done=True)
        else:
            self.idle_ticks += 1
            if self.idle_ticks >= self.IDLE_LIMIT:
                self.finish_more(done=True)

    def settle(self):
        """Stop polling but keep the loaded page alive so more pages can be scrolled in."""
        self.active = False
        self.awaiting_results = False
        self.timer.stop(); self.deadline.stop()
        self.busy.emit(False)

    def finish_more(self, done):
        self.settle()
        self.exhausted = bool(done)
        self.more_state.emit(not self.exhausted)
        if done:
            self.status.emit(f'이미지 {len(self.seen)}개 · Google이 제공한 결과를 모두 불러왔습니다.')

    def timeout(self):
        if self.mode == 'more':
            self.finish_more(done=False)
            self.status.emit(f'이미지 {len(self.seen)}개를 모았습니다. 더 불러오려면 다시 시도해 주세요.')
            return
        self.active = False
        self.timer.stop(); self.deadline.stop()
        self.busy.emit(False)
        # Do not interrupt the user with an automatic browser popup.
        self.status.emit('Google에서 결과를 가져오지 못했습니다. 확인이 필요한 경우 “Google 확인”을 눌러 주세요. 확인 후 결과는 자동으로 표시됩니다.')

    def show_browser(self):
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()
        if self.awaiting_results and not self.api_mode and not self.ready:
            self.mode = 'initial'
            self.active = True
            self.timer.start()
            self.deadline.start(180000)
            self.extract()

    def cancel(self, stop=True):
        self.active = False
        self.awaiting_results = False
        self.generation += 1
        self.timer.stop(); self.deadline.stop()
        if stop:
            self.view.stop()
        self.busy.emit(False)

    def shutdown(self):
        self.cancel()
        self.dialog.close()
        # Page must be destroyed before its profile.
        self.view.setPage(QWebEnginePage(self.view))
        self.page.deleteLater()
        self.fetch_page.deleteLater()

    # ---------- last-resort fetch through Chromium ----------

    def browser_fetch(self, ident: str, url: str, page_url: str, directory):
        """Plain HTTP was refused. Chromium already holds this site's cookies, so ask it."""
        if not url.startswith(('https://', 'http://')):
            self.fetch_failed.emit(ident, '원본 이미지 주소가 없습니다.')
            return
        if ident in self.fetch_jobs:
            return
        self.fetch_jobs[ident] = {'url': url, 'directory': str(directory)}
        # Giving the page the source document as its context makes Chromium send a
        # Referer the host will accept, which is what most hotlink blocks check.
        if page_url.startswith(('https://', 'http://')):
            self.fetch_page.setHtml('<!doctype html><title>fetch</title>', QUrl(page_url))
        self.fetch_page.download(QUrl(url))

    def pending_fetch(self, url: str):
        for ident, job in self.fetch_jobs.items():
            if job['url'] == url:
                return ident, job
        return None, None

    def on_download_requested(self, request):
        ident, job = self.pending_fetch(request.url().toString())
        if ident is None:
            request.cancel()  # nothing in this app downloads through the browser by itself
            return
        request.setDownloadDirectory(job['directory'])
        request.setDownloadFileName(f'{ident}.browser-part')
        request.isFinishedChanged.connect(lambda r=request, i=ident: self.on_download_finished(r, i))
        request.accept()

    def on_download_finished(self, request, ident):
        if not request.isFinished():
            return
        self.fetch_jobs.pop(ident, None)
        completed = request.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted
        path = os.path.join(request.downloadDirectory(), request.downloadFileName())
        if completed and os.path.exists(path):
            self.fetched.emit(ident, path)
        else:
            self.fetch_failed.emit(ident, '원본 사이트가 브라우저 요청도 거부했습니다.')

    # ---------- settings and manual capture ----------

    def settings_dialog(self, parent):
        from PySide6.QtWidgets import QLineEdit, QComboBox, QDialogButtonBox
        dialog = QDialog(parent); dialog.setWindowTitle('검색 설정'); dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        note = QLabel('기본 검색은 앱 내 Google 브라우저를 사용합니다.\nGoogle 확인 화면이 반복되면 SerpApi의 Google Images API를 선택할 수 있습니다.\nAPI 키는 이번 실행 동안만 메모리에 보관됩니다.')
        note.setWordWrap(True); layout.addWidget(note)
        mode = QComboBox(); mode.addItems(['Google 브라우저 · 기본', 'SerpApi · 개인 API 키 필요'])
        mode.setCurrentIndex(1 if self.api_mode else 0); layout.addWidget(mode)
        key = QLineEdit(self.api_key); key.setEchoMode(QLineEdit.EchoMode.Password)
        key.setPlaceholderText('SerpApi API key'); layout.addWidget(key)
        note2 = QLabel('SerpApi 사용량과 비용은 본인 계정에 적용됩니다.\n환경변수 SERPAPI_API_KEY로도 키를 지정할 수 있습니다.')
        note2.setWordWrap(True); layout.addWidget(note2)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.api_key = key.text().strip(); self.api_mode = mode.currentIndex() == 1
            self.status.emit('검색 설정을 적용했습니다.')

    def browser_context_menu(self, pos):
        request = self.view.lastContextMenuRequest()
        url = request.mediaUrl().toString()
        link = request.linkUrl().toString(); title = request.linkText()
        menu = self.view.createStandardContextMenu()
        if url.startswith(('https://', 'http://')):
            menu.addSeparator()
            action = menu.addAction('이 이미지를 ImageSearch로 가져오기')

            def collect():
                item = {'url': url, 'thumbnail': url, 'title': title or self.query or 'Google에서 가져온 이미지',
                        'source': urlparse(url).hostname or '', 'page_url': link or self.view.url().toString()}
                self.seen.add(url)
                self.more_results.emit([item]) if self.ready else self.results.emit([item])
                self.dialog.hide()
                self.status.emit('이미지를 가져왔습니다. 선택한 이미지가 축소판이면 다운로드도 같은 해상도입니다.')
            action.triggered.connect(collect)
        menu.exec(self.view.mapToGlobal(pos))

    # ---------- optional SerpApi backend ----------

    def start_api(self, query, page=0):
        from PySide6.QtCore import QRunnable
        import requests
        if not self.api_key:
            self.cancel(); self.status.emit('검색 설정에서 SerpApi 키를 입력해 주세요.'); return

        class ApiSignals(QObject):
            done = Signal(object)

        class ApiJob(QRunnable):
            def __init__(job, key):
                super().__init__(); job.signals = ApiSignals(); job.key = key

            def run(job):
                try:
                    response = requests.get('https://serpapi.com/search.json',
                                            params={'engine': 'google_images', 'q': query, 'api_key': job.key,
                                                    'safe': 'active', 'hl': 'ko', 'ijn': page}, timeout=(8, 25))
                    if response.status_code != 200:
                        raise ValueError(f'SerpApi 요청 실패 (HTTP {response.status_code}). API 키·사용량을 확인해 주세요.')
                    payload = response.json()
                    if payload.get('error'):
                        raise ValueError('SerpApi에서 결과를 제공하지 못했습니다. 키·사용량·검색어를 확인해 주세요.')
                    items = [{'url': x['original'], 'thumbnail': x.get('thumbnail', ''), 'title': x.get('title', query),
                              'source': x.get('source', ''), 'page_url': x.get('link', ''),
                              'width': x.get('original_width', 0), 'height': x.get('original_height', 0)}
                             for x in payload.get('images_results', []) if x.get('original', '').startswith(('https://', 'http://'))]
                    job.signals.done.emit(items[:RESULT_CAP])
                except Exception as exc:
                    message = str(exc) if isinstance(exc, ValueError) and str(exc).startswith('SerpApi') else 'SerpApi 연결 실패. 인터넷 연결을 확인해 주세요.'
                    job.signals.done.emit(message)

        generation = self.generation
        job = ApiJob(self.api_key)
        self.api_jobs.append(job)

        def received(result):
            self.api_jobs.remove(job)
            if generation != self.generation or not self.active:
                return
            self.settle()
            if not isinstance(result, list):
                self.status.emit(result)
                return
            fresh = [i for i in result if i['url'] not in self.seen]
            for item in fresh:
                self.seen.add(item['url'])
            if page == 0:
                self.ready = True
                self.results.emit(fresh)
            else:
                self.more_results.emit(fresh)
            self.exhausted = not fresh
            self.more_state.emit(not self.exhausted)
            self.status.emit(f'Google 이미지 {len(self.seen)}개 · SerpApi')

        job.signals.done.connect(received)
        self.api_pool.start(job)
