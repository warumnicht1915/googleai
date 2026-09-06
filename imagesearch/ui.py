from __future__ import annotations
import math
from pathlib import Path
from PySide6.QtCore import (Qt, QTimer, Signal, QThreadPool, QUrl, QSize, QPoint,
                            QVariantAnimation, QPropertyAnimation, QEasingCurve, QAbstractAnimation)
from PySide6.QtGui import QPixmap, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QStackedWidget, QLineEdit, QPlainTextEdit,
    QCheckBox, QDialog, QInputDialog, QMessageBox, QMenu, QProgressBar, QDialogButtonBox,
    QGraphicsOpacityEffect)
from . import icons
from .store import Store
from .network import ImageJob, DerivePreviewJob
from .theme import build_style, palette, DEFAULT_MODE, PALETTES

CARD_IMAGE_H = 205
CARD_H = 308
CARD_MIN_W = 205
CARD_MAX_W = 360
GAP = 16


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, slot=None, name=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if slot:
        widget.clicked.connect(slot)
    if name:
        widget.setObjectName(name)
    return widget


class Composer(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
        else:
            super().keyPressEvent(event)


class ImageLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class Card(QFrame):
    def __init__(self, item, window):
        super().__init__()
        self.item, self.window = item, window
        self.queued = False
        self.spinner = None
        self.pixmap = QPixmap()
        self.setObjectName('card')
        self.setMinimumWidth(CARD_MIN_W); self.setMaximumWidth(CARD_MAX_W)
        self.setFixedHeight(CARD_H)
        layout = QVBoxLayout(self); layout.setContentsMargins(11, 11, 11, 11); layout.setSpacing(8)
        self.picture = ImageLabel('불러오는 중…')
        self.picture.setObjectName('preview')
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setFixedHeight(CARD_IMAGE_H); self.picture.setMinimumWidth(1)
        self.picture.setCursor(Qt.CursorShape.PointingHandCursor)
        self.picture.clicked.connect(lambda: window.show_detail(item['id']))
        layout.addWidget(self.picture)
        self.title_label = label(item['title'])
        self.title_label.setToolTip(item['title']); self.title_label.setFixedHeight(18)
        layout.addWidget(self.title_label)
        self.source_label = label(self.meta_text(), 'muted')
        self.source_label.setFixedHeight(15); layout.addWidget(self.source_label)
        row = QHBoxLayout(); row.setSpacing(6)
        self.like = button('', lambda: window.toggle_like(item['id']), 'heart')
        self.like.setCheckable(True); self.like.setFixedSize(42, 31)
        self.like.setToolTip('좋아요 · 오프라인 미리보기 저장')
        self.download = button(' 저장', lambda: window.download_image(item['id']), 'small')
        self.download.setFixedHeight(31)
        self.tag = button('', lambda: window.assign_categories(item['id']), 'small')
        self.tag.setFixedSize(36, 31); self.tag.setToolTip('카테고리로 정리')
        row.addWidget(self.like); row.addWidget(self.download); row.addStretch(); row.addWidget(self.tag)
        layout.addLayout(row)
        self.refresh()

    # ---------- content ----------

    def meta_text(self):
        source = self.item.get('source') or 'Google 이미지'
        if self.item.get('width') and self.item.get('height'):
            return f'{source} · {self.item["width"]}×{self.item["height"]}'
        return source

    def refresh(self, animate=False):
        current = self.window.store.get(self.item['id'])
        if current:
            self.item = current
        colors = self.window.colors
        liked = bool(self.item['liked'])
        self.like.setChecked(liked)
        self.like.setIcon(icons.icon('heart', colors['like'] if liked else colors['muted'], 17, fill=liked))
        self.like.setIconSize(QSize(17, 17))
        self.tag.setIcon(icons.icon('tag', colors['muted'], 15)); self.tag.setIconSize(QSize(15, 15))
        downloading = (self.item['id'], 'download') in self.window.jobs
        saved = bool(self.item['download_path'] and Path(self.item['download_path']).exists())
        if downloading:
            self.start_spinner()
        else:
            self.stop_spinner()
            self.download.setText(' 저장됨' if saved else ' 저장')
            self.download.setIcon(icons.icon('check' if saved else 'download',
                                             colors['ok'] if saved else colors['muted'], 15))
            self.download.setIconSize(QSize(15, 15))
        self.download.setEnabled(not downloading)
        path = next((self.item[k] for k in ('download_path', 'preview_path')
                     if self.item[k] and Path(self.item[k]).exists()), '')
        if path:
            loaded = QPixmap(path)
            if loaded.isNull():
                self.picture.setText('저장 파일을 열 수 없습니다')
            else:
                first = self.pixmap.isNull()
                self.pixmap = loaded
                self.paint_image()
                if first and animate:
                    self.fade_in()

    def paint_image(self):
        if self.pixmap.isNull():
            return
        ratio = self.devicePixelRatioF() or 1.0
        target_w = max(1, int(self.picture.width() * ratio))
        target_h = int(CARD_IMAGE_H * ratio)
        # Never blow a small source up more than 1.4x its real pixels — that is what looked blurry.
        scale = min(target_w / self.pixmap.width(), target_h / self.pixmap.height())
        if scale > 1.4:
            target_w = int(self.pixmap.width() * 1.4)
            target_h = int(self.pixmap.height() * 1.4)
        scaled = self.pixmap.scaled(target_w, target_h, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio)
        self.picture.setPixmap(icons.rounded(scaled, 9))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.paint_image()
        metrics = self.title_label.fontMetrics()
        self.title_label.setText(metrics.elidedText(self.item['title'], Qt.TextElideMode.ElideRight, self.width() - 26))
        self.source_label.setText(metrics.elidedText(self.meta_text(), Qt.TextElideMode.ElideRight, self.width() - 26))

    # ---------- animation ----------

    def fade_in(self):
        effect = QGraphicsOpacityEffect(self.picture)
        self.picture.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b'opacity', self)
        animation.setDuration(300); animation.setStartValue(0.0); animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: effect.setEnabled(False))
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def animate_like(self, liked):
        base = 17
        animation = QVariantAnimation(self)
        animation.setDuration(460); animation.setStartValue(0.0); animation.setEndValue(1.0)

        def tick(value):
            step = float(value)
            wave = math.sin(math.pi * min(1.0, step))
            scale = 1 + (0.52 if liked else -0.24) * wave * (1 - 0.25 * step)
            edge = max(8, int(round(base * scale)))
            self.like.setIconSize(QSize(edge, edge))

        animation.valueChanged.connect(tick)
        animation.finished.connect(lambda: self.like.setIconSize(QSize(base, base)))
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        if liked:
            self.float_heart()

    def float_heart(self):
        ghost = QLabel(self)
        ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ghost.setPixmap(icons.pixmap('heart', self.window.colors['like'], 26, fill=True))
        ghost.adjustSize()
        effect = QGraphicsOpacityEffect(ghost); ghost.setGraphicsEffect(effect)
        origin = self.like.geometry().center() - QPoint(ghost.width() // 2, ghost.height() // 2)
        ghost.move(origin); ghost.show(); ghost.raise_()
        animation = QVariantAnimation(self)
        animation.setDuration(700); animation.setStartValue(0.0); animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def tick(value):
            step = float(value)
            ghost.move(origin.x(), int(origin.y() - 48 * step))
            effect.setOpacity(max(0.0, 1.0 - step ** 1.4))

        animation.valueChanged.connect(tick)
        animation.finished.connect(ghost.deleteLater)
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def start_spinner(self):
        if self.spinner is not None:
            return
        color = self.window.colors['accent']
        self.download.setText(' 저장 중')
        animation = QVariantAnimation(self)
        animation.setDuration(950); animation.setStartValue(0.0); animation.setEndValue(360.0)
        animation.setLoopCount(-1)
        animation.valueChanged.connect(
            lambda value: self.download.setIcon(
                icons.icon('loader-circle', color, 15, angle=round(float(value) / 30) * 30)))
        animation.start()
        self.spinner = animation

    def stop_spinner(self):
        if self.spinner is not None:
            self.spinner.stop()
            self.spinner.deleteLater()
            self.spinner = None

    def pop_saved(self):
        animation = QVariantAnimation(self)
        animation.setDuration(380); animation.setStartValue(0.0); animation.setEndValue(1.0)

        def tick(value):
            edge = max(9, int(round(15 * (1 + 0.45 * math.sin(math.pi * float(value))))))
            self.download.setIconSize(QSize(edge, edge))

        animation.valueChanged.connect(tick)
        animation.finished.connect(lambda: self.download.setIconSize(QSize(15, 15)))
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


class Window(QMainWindow):
    def __init__(self, store=None, browser=True):
        super().__init__()
        self.store = store or Store()
        mode = self.store.setting('theme', DEFAULT_MODE)
        self.mode = mode if mode in PALETTES else DEFAULT_MODE
        self.colors = palette(self.mode)
        self.icon_bindings = []
        self.setWindowTitle('ImageSearch')
        self.resize(1360, 920); self.setMinimumSize(1000, 700)
        self.pool = QThreadPool(self); self.pool.setMaxThreadCount(6)
        self.jobs = {}
        self.cards = []
        self.results = []
        self.placed = 0
        self.has_more = False
        self.view_name = 'search'; self.category = None; self.query = ''
        self.columns = 0; self.closing = False
        self.detail_refresh = None
        self.searcher = None
        if browser:
            from .search import GoogleSearch
            self.searcher = GoogleSearch(self.store.root, self)
            self.searcher.results.connect(self.receive_results)
            self.searcher.more_results.connect(self.append_results)
            self.searcher.status.connect(self.set_status)
            self.searcher.busy.connect(self.set_busy)
            self.searcher.more_state.connect(self.set_more_available)
        self.build()
        self.apply_theme(self.mode, persist=False)
        self.refresh_sidebar(); self.navigate('search')

    # ---------- construction ----------

    def build(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        sidebar = QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(248)
        left = QVBoxLayout(sidebar); left.setContentsMargins(18, 26, 18, 18); left.setSpacing(6)
        brand = QHBoxLayout(); brand.setSpacing(9)
        self.brand_mark = QLabel(); self.brand_mark.setFixedSize(26, 26)
        brand.addWidget(self.brand_mark); brand.addWidget(label('ImageSearch', 'brand')); brand.addStretch()
        left.addLayout(brand)
        left.addWidget(label('발견하고, 모아두고, 다시 꺼내보기', 'faint'))
        left.addSpacing(22)
        self.nav = {}
        for key, text, icon_name in [('search', '이미지 탐색', 'search'), ('all', '내 라이브러리', 'layout-grid'),
                                     ('liked', '좋아요', 'heart'), ('downloads', '다운로드', 'download')]:
            item = button('   ' + text, lambda checked=False, k=key: self.navigate(k), 'nav')
            item.setCheckable(True)
            self.bind_icon(item, icon_name, 'muted', 17)
            self.nav[key] = item; left.addWidget(item)
        left.addSpacing(20)
        row = QHBoxLayout(); row.addWidget(label('카테고리', 'section')); row.addStretch()
        add = button('', self.add_category, 'small'); add.setFixedSize(28, 26)
        self.bind_icon(add, 'plus', 'muted', 14); row.addWidget(add)
        left.addLayout(row)
        area = QScrollArea(); area.setWidgetResizable(True); area.setMaximumHeight(210)
        holder = QWidget(); self.cat_layout = QVBoxLayout(holder)
        self.cat_layout.setContentsMargins(0, 0, 0, 0); self.cat_layout.setSpacing(2)
        area.setWidget(holder); left.addWidget(area)
        left.addSpacing(14); left.addWidget(label('최근 검색', 'section'))
        self.history_layout = QVBoxLayout(); self.history_layout.setSpacing(1); left.addLayout(self.history_layout)
        left.addStretch()
        self.theme_button = button('', self.toggle_theme, 'history'); left.addWidget(self.theme_button)
        settings = button('   검색 설정', self.settings, 'history')
        self.bind_icon(settings, 'settings', 'muted', 16); left.addWidget(settings)
        folder = button('   저장 폴더 열기', lambda: self.open_path(self.store.root), 'history')
        self.bind_icon(folder, 'folder-open', 'muted', 16); left.addWidget(folder)
        left.addWidget(label('이 기기에만 보관됩니다', 'faint'))
        outer.addWidget(sidebar)

        main = QWidget(); body = QVBoxLayout(main); body.setContentsMargins(30, 26, 30, 18); body.setSpacing(13)
        header = QHBoxLayout(); heading = QVBoxLayout(); heading.setSpacing(5)
        self.title = label('이미지 탐색', 'title')
        self.subtitle = label('좋아하는 캐릭터를 발견하는 나만의 공간', 'muted')
        heading.addWidget(self.title); heading.addWidget(self.subtitle)
        header.addLayout(heading); header.addStretch()
        self.google_button = button('  Google 확인', self.show_google, 'ghost')
        self.bind_icon(self.google_button, 'external-link', 'muted', 15)
        header.addWidget(self.google_button)
        body.addLayout(header)

        toolbar = QHBoxLayout()
        self.count_label = label('GOOGLE IMAGES  /  2D COLLECTION', 'section')
        toolbar.addWidget(self.count_label); toolbar.addStretch()
        self.filter = QLineEdit(); self.filter.setPlaceholderText('현재 목록에서 찾기')
        self.filter.setMaximumWidth(230); self.filter.textChanged.connect(self.render)
        self.filter.setClearButtonEnabled(True)
        toolbar.addWidget(self.filter); body.addLayout(toolbar)

        self.stack = QStackedWidget()
        self.empty = QWidget()
        welcome = QVBoxLayout(self.empty)
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter); welcome.setSpacing(16)
        self.hero_icon = QLabel(); self.hero_icon.setObjectName('heroIcon')
        self.hero_icon.setFixedSize(88, 88); self.hero_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bind_icon(self.hero_icon, 'sparkles', 'accent', 38)
        welcome.addWidget(self.hero_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self.empty_title = label('어떤 캐릭터를 찾고 있나요?', 'hero')
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter); welcome.addWidget(self.empty_title)
        self.empty_sub = label('아래에 키워드를 입력하세요. 마음에 드는 이미지는 오래 간직하고요.', 'muted')
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty_sub.setWordWrap(True)
        welcome.addWidget(self.empty_sub)
        self.chips = QWidget(); chips = QHBoxLayout(self.chips); chips.setSpacing(9)
        for text in ['하츠네 미쿠', '스튜디오 지브리', '애니메이션 배경']:
            chips.addWidget(button(text, lambda checked=False, q=text: self.start_search(q), 'chip'))
        welcome.addWidget(self.chips)
        self.stack.addWidget(self.empty)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_widget = QWidget(); self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 6, 12); self.grid.setSpacing(GAP)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.grid_widget); self.stack.addWidget(self.scroll)
        self.scroll.verticalScrollBar().valueChanged.connect(self.on_scroll)
        body.addWidget(self.stack, 1)

        self.more_button = button('  더 불러오기', self.request_more, 'more')
        self.bind_icon(self.more_button, 'chevron-down', 'muted', 16)
        self.more_button.hide()
        more_row = QHBoxLayout(); more_row.addStretch(); more_row.addWidget(self.more_button); more_row.addStretch()
        body.addLayout(more_row)

        self.progress = QProgressBar(); self.progress.setRange(0, 0)
        self.progress.setTextVisible(False); self.progress.hide(); body.addWidget(self.progress)
        self.status = label('검색 결과의 원본 출처를 확인하고 이미지를 저장하세요.', 'muted')
        self.status.setWordWrap(True); body.addWidget(self.status)

        composer = QFrame(); composer.setObjectName('composer')
        compose = QVBoxLayout(composer); compose.setContentsMargins(18, 13, 14, 12); compose.setSpacing(8)
        self.input = Composer(); self.input.setObjectName('composerInput')
        self.input.setPlaceholderText('캐릭터 이름, 작품, 분위기를 입력하세요…')
        self.input.setFixedHeight(56); self.input.submitted.connect(self.submit)
        compose.addWidget(self.input)
        controls = QHBoxLayout()
        self.anime = QCheckBox('2D · 애니메이션 키워드 추가'); self.anime.setChecked(True)
        controls.addWidget(self.anime); controls.addStretch()
        controls.addWidget(label('Enter 검색 · Shift+Enter 줄바꿈', 'faint'))
        self.cancel_btn = button('', self.cancel_search, 'small')
        self.cancel_btn.setFixedSize(34, 32); self.cancel_btn.setToolTip('검색 중지')
        self.bind_icon(self.cancel_btn, 'x', 'muted', 15)
        self.cancel_btn.hide(); controls.addWidget(self.cancel_btn)
        self.send = button('', self.submit, 'accent'); self.send.setFixedSize(42, 38)
        self.send.setToolTip('Google 이미지 검색')
        self.bind_icon(self.send, 'arrow-up', 'accent_text', 18)
        controls.addWidget(self.send)
        compose.addLayout(controls); body.addWidget(composer)
        outer.addWidget(main, 1)

        self.resize_timer = QTimer(self); self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.reflow)
        self.lazy_timer = QTimer(self); self.lazy_timer.setSingleShot(True)
        self.lazy_timer.timeout.connect(self.load_visible)
        QShortcut(QKeySequence('Ctrl+L'), self, activated=self.input.setFocus)
        QShortcut(QKeySequence('Ctrl+T'), self, activated=self.toggle_theme)
        QShortcut(QKeySequence('Ctrl+1'), self, activated=lambda: self.navigate('search'))
        QShortcut(QKeySequence('Ctrl+2'), self, activated=lambda: self.navigate('liked'))
        QShortcut(QKeySequence('Ctrl+3'), self, activated=lambda: self.navigate('downloads'))

    # ---------- theming ----------

    def role_color(self, role):
        return self.colors.get(role, self.colors['text'])

    def bind_icon(self, widget, name, role='muted', size=18, fill=False):
        self.icon_bindings.append((widget, name, role, size, fill))
        self.paint_icon(widget, name, role, size, fill)

    def paint_icon(self, widget, name, role, size, fill):
        color = self.role_color(role)
        if isinstance(widget, QLabel):
            widget.setPixmap(icons.pixmap(name, color, size, fill))
        else:
            widget.setIcon(icons.icon(name, color, size, fill))
            widget.setIconSize(QSize(size, size))

    def apply_theme(self, mode, persist=True):
        self.mode = mode
        self.colors = palette(mode)
        icons.clear_cache()
        self.setStyleSheet(build_style(mode))
        if persist:
            self.store.save_setting('theme', mode)
        alive = []
        for widget, name, role, size, fill in self.icon_bindings:
            try:
                self.paint_icon(widget, name, role, size, fill)
                alive.append((widget, name, role, size, fill))
            except RuntimeError:
                continue
        self.icon_bindings = alive
        self.brand_mark.setPixmap(icons.pixmap('image', self.colors['accent'], 24))
        dark = mode == 'dark'
        self.theme_button.setText('   라이트 모드' if dark else '   다크 모드')
        self.theme_button.setIcon(icons.icon('sun' if dark else 'moon', self.colors['muted'], 16))
        self.theme_button.setIconSize(QSize(16, 16))
        self.theme_button.setToolTip('테마 전환 · Ctrl+T')

    def toggle_theme(self):
        self.apply_theme('light' if self.mode == 'dark' else 'dark')
        self.refresh_sidebar()
        self.render()
        self.set_status('라이트 모드로 전환했습니다.' if self.mode == 'light' else '다크 모드로 전환했습니다.')

    # ---------- search ----------

    def set_status(self, text):
        self.status.setText(text)

    def set_busy(self, busy):
        self.progress.setVisible(busy)
        self.cancel_btn.setVisible(busy)
        self.send.setEnabled(not busy)
        self.more_button.setEnabled(not busy)

    def set_more_available(self, available):
        self.has_more = bool(available)
        self.more_button.setVisible(self.has_more and self.view_name == 'search' and bool(self.cards))

    def submit(self):
        self.start_search(self.input.toPlainText())

    def start_search(self, query):
        query = ' '.join(query.split())[:250]
        if not query:
            self.input.setFocus(); return
        if not self.searcher:
            self.set_status('테스트 모드에서는 검색을 실행하지 않습니다.'); return
        self.query = query; self.input.clear(); self.results = []
        self.has_more = False; self.more_button.hide()
        self.store.remember(query); self.refresh_sidebar(); self.navigate('search')
        self.searcher.search(query, self.anime.isChecked())

    def cancel_search(self):
        if self.searcher:
            self.searcher.cancel()
        self.set_status('검색을 중지했습니다. 다른 키워드로 다시 검색할 수 있습니다.')

    def show_google(self):
        if self.searcher:
            self.searcher.show_browser()

    def request_more(self):
        if self.searcher and self.has_more:
            self.searcher.load_more()

    def on_scroll(self, value):
        self.lazy_timer.start(80)
        bar = self.scroll.verticalScrollBar()
        if self.view_name == 'search' and self.has_more and bar.maximum() and value >= bar.maximum() - 460:
            self.request_more()

    def receive_results(self, items):
        self.results = [self.store.upsert(i) for i in items]
        self.navigate('search')

    def append_results(self, items):
        stored = [self.store.upsert(i) for i in items]
        known = {i['id'] for i in self.results}
        stored = [i for i in stored if i['id'] not in known]
        self.results.extend(stored)
        if self.view_name != 'search' or not stored:
            return
        if self.stack.currentWidget() is not self.scroll:
            self.render(); return
        term = self.filter.text().casefold()
        fresh = [i for i in stored if term in (i['title'] + ' ' + i['source']).casefold()]
        for item in fresh:
            self.cards.append(Card(item, self))
        self.count_label.setText(f'{len(self.cards)}개의 이미지')
        self.reflow()
        QTimer.singleShot(0, self.load_visible)

    # ---------- views ----------

    def navigate(self, view, category=None):
        self.view_name = view; self.category = category
        for key, item in self.nav.items():
            item.setChecked(view == key and category is None)
        names = {'search': f'“{self.query}”' if self.query else '이미지 탐색', 'all': '내 라이브러리',
                 'liked': '좋아요', 'downloads': '다운로드', 'category': '카테고리'}
        title = names[view]
        if category is not None:
            title = next((c['name'] for c in self.store.categories() if c['id'] == category), '카테고리')
        self.title.setText(title)
        self.subtitle.setText('Google에서 발견한 이미지' if view == 'search' and self.query
                              else '좋아하는 캐릭터를 발견하는 나만의 공간' if view == 'search'
                              else '검색하지 않아도, 언제든 다시 볼 수 있어요')
        self.filter.blockSignals(True); self.filter.clear(); self.filter.blockSignals(False)
        self.render()

    def render(self):
        term = self.filter.text().casefold()
        if self.view_name == 'search':
            items = [self.store.get(i['id']) or i for i in self.results]
            items = [i for i in items if term in (i['title'] + ' ' + i['source']).casefold()]
        else:
            items = self.store.list_images(self.view_name, self.category, self.filter.text())
        for card in self.cards:
            card.stop_spinner(); self.grid.removeWidget(card); card.deleteLater()
        self.cards = []; self.columns = 0; self.placed = 0
        self.count_label.setText(f'{len(items)}개의 이미지' if items else 'GOOGLE IMAGES  /  2D COLLECTION')
        self.more_button.setVisible(self.has_more and self.view_name == 'search' and bool(items))
        if not items:
            self.stack.setCurrentWidget(self.empty)
            searching = self.view_name == 'search'
            self.empty_title.setText('어떤 캐릭터를 찾고 있나요?' if searching and not self.query else '아직 표시할 이미지가 없어요')
            self.empty_sub.setText('아래에 키워드를 입력하세요. 마음에 드는 이미지는 오래 간직하고요.' if searching
                                   else '검색한 이미지에 좋아요를 누르거나, 다운로드·카테고리로 모아보세요.')
            self.chips.setVisible(searching and not self.query)
            return
        self.stack.setCurrentWidget(self.scroll)
        for item in items:
            self.cards.append(Card(item, self))
        self.reflow(); self.scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(0, self.after_layout)

    def after_layout(self):
        self.reflow()
        self.load_visible()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'resize_timer'):
            self.resize_timer.start(70)

    def reflow(self):
        if not self.cards:
            self.placed = 0; return
        available = self.scroll.viewport().width() - 8
        columns = max(1, min(6, (available + GAP) // (CARD_MIN_W + GAP)))
        if columns != self.columns:
            for card in self.cards:
                self.grid.removeWidget(card)
            for index in range(max(self.columns, columns, 6)):
                self.grid.setColumnStretch(index, 0); self.grid.setColumnMinimumWidth(index, 0)
            self.columns = columns; self.placed = 0
        for index in range(self.placed, len(self.cards)):
            self.grid.addWidget(self.cards[index], index // columns, index % columns)
        self.placed = len(self.cards)
        width = max(CARD_MIN_W, min(CARD_MAX_W, (available - (columns - 1) * GAP) // columns))
        for card in self.cards:
            card.setFixedWidth(width)
        rows = (len(self.cards) + columns - 1) // columns
        self.grid_widget.setMinimumHeight(rows * (CARD_H + GAP) - GAP + 12)

    def load_visible(self):
        """Only fetch previews for cards the user can actually reach right now."""
        if not self.cards:
            return
        bar = self.scroll.verticalScrollBar()
        top = bar.value()
        height = self.scroll.viewport().height() or 1000
        bottom = top + height
        for card in self.cards:
            if card.queued or not card.pixmap.isNull():
                continue
            edge = card.y()
            if edge + card.height() >= top - 500 and edge <= bottom + 900:
                card.queued = True
                self.queue_image(card.item, 'preview')

    # ---------- jobs ----------

    def queue_image(self, item, kind):
        key = (item['id'], kind)
        if key in self.jobs:
            return
        job = ImageJob(item, self.store.cache if kind == 'preview' else self.store.downloads, kind)
        self.jobs[key] = job
        job.signals.done.connect(self.image_done)
        job.signals.error.connect(self.image_error)
        self.pool.start(job)

    def image_done(self, ident, kind, path):
        self.jobs.pop((ident, kind), None)
        self.store.update(ident, **{('preview_path' if kind == 'preview' else 'download_path'): path})
        for card in self.cards:
            if card.item['id'] == ident:
                card.refresh(animate=True)
                if kind == 'download':
                    card.pop_saved()
        if kind == 'download':
            self.set_status('다운로드 완료 · 왼쪽 “다운로드”에서 다시 볼 수 있습니다.')
            self.refresh_sidebar()
            self.ensure_preview(ident, path)
        if self.detail_refresh:
            self.detail_refresh()

    def ensure_preview(self, ident, source_path):
        """Reuse the freshly downloaded original instead of hitting the network twice."""
        item = self.store.get(ident)
        if item.get('preview_path') and Path(item['preview_path']).exists():
            return
        key = (ident, 'preview')
        if key in self.jobs:
            return
        job = DerivePreviewJob(ident, source_path, self.store.cache)
        self.jobs[key] = job
        job.signals.done.connect(self.image_done)
        job.signals.error.connect(self.image_error)
        self.pool.start(job)

    def image_error(self, ident, kind, message):
        self.jobs.pop((ident, kind), None)
        for card in self.cards:
            if card.item['id'] == ident:
                card.refresh()
                if kind == 'preview':
                    card.picture.setText('미리보기를 불러오지 못했어요\n클릭해서 원본 출처 확인')
        if kind == 'download':
            self.set_status('다운로드 실패 · ' + message)
        elif self.store.get(ident).get('liked'):
            self.set_status('좋아요는 저장했지만 미리보기를 받지 못했습니다. 연결 후 목록을 다시 열어 주세요.')

    # ---------- actions ----------

    def toggle_like(self, ident):
        item = self.store.get(ident)
        liked = not item['liked']
        self.store.update(ident, liked=1 if liked else 0)
        if liked:
            self.set_status('좋아요에 추가했습니다. 미리보기가 저장되면 오프라인에서도 볼 수 있습니다.')
            entry = self.store.get(ident)
            if not (entry['preview_path'] and Path(entry['preview_path']).exists()):
                self.queue_image(entry, 'preview')
        if self.view_name in ('liked', 'all'):
            self.render()
        else:
            for card in self.cards:
                if card.item['id'] == ident:
                    card.refresh(); card.animate_like(liked)
        self.refresh_sidebar()

    def download_image(self, ident):
        item = self.store.get(ident)
        if item['download_path'] and Path(item['download_path']).exists():
            self.open_path(Path(item['download_path'])); return
        self.queue_image(item, 'download')
        for card in self.cards:
            if card.item['id'] == ident:
                card.refresh()
        self.set_status('원본 이미지를 다운로드하고 있습니다…')

    @staticmethod
    def clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                # deleteLater() alone leaves the old widget painted over the new one.
                widget.setParent(None)
                widget.deleteLater()

    def refresh_sidebar(self):
        self.clear_layout(self.cat_layout)
        cats = self.store.categories()
        if not cats:
            self.cat_layout.addWidget(label('＋ 버튼으로 새 카테고리', 'faint'))
        for cat in cats:
            item = button(f'   {cat["name"]}   {cat["count"]}',
                          lambda checked=False, c=cat['id']: self.navigate('category', c), 'history')
            item.setIcon(icons.icon('tag', self.colors['muted'], 15)); item.setIconSize(QSize(15, 15))
            item.setToolTip(cat['name'] + ' · 우클릭으로 이름 변경/삭제')
            item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            item.customContextMenuRequested.connect(lambda pos, b=item, c=cat: self.category_menu(b, pos, c))
            self.cat_layout.addWidget(item)
        self.cat_layout.addStretch()
        self.clear_layout(self.history_layout)
        history = self.store.history()
        for query in history:
            item = button('   ' + (query if len(query) < 20 else query[:19] + '…'),
                          lambda checked=False, q=query: self.start_search(q), 'history')
            item.setIcon(icons.icon('search', self.colors['faint'], 14)); item.setIconSize(QSize(14, 14))
            item.setToolTip(query); self.history_layout.addWidget(item)
        if not history:
            self.history_layout.addWidget(label('검색 기록이 여기에 표시됩니다', 'faint'))
        self.nav['liked'].setText(f'   좋아요   {len(self.store.list_images("liked"))}')
        self.nav['downloads'].setText(f'   다운로드   {len(self.store.list_images("downloads"))}')

    def add_category(self):
        name, ok = QInputDialog.getText(self, '새 카테고리', '카테고리 이름')
        if ok:
            try:
                ident = self.store.add_category(name); self.refresh_sidebar(); return ident
            except ValueError as exc:
                QMessageBox.information(self, '카테고리', str(exc))
        return None

    def category_menu(self, widget, pos, cat):
        menu = QMenu(self)
        rename = menu.addAction('이름 변경'); remove = menu.addAction('카테고리 삭제')
        action = menu.exec(widget.mapToGlobal(pos))
        if action == rename:
            name, ok = QInputDialog.getText(self, '이름 변경', '카테고리 이름', text=cat['name'])
            if ok:
                try:
                    self.store.rename_category(cat['id'], name)
                except ValueError as exc:
                    QMessageBox.information(self, '카테고리', str(exc))
        elif action == remove:
            self.store.delete_category(cat['id'])
            self.set_status('카테고리를 삭제했습니다. 좋아요와 다운로드 파일은 유지됩니다.')
            if self.category == cat['id']:
                self.navigate('all')
        self.refresh_sidebar()
        if self.category == cat['id']:
            self.navigate('category', cat['id'])

    def assign_categories(self, ident):
        dialog = QDialog(self); dialog.setWindowTitle('카테고리로 정리'); dialog.setMinimumWidth(370)
        layout = QVBoxLayout(dialog); layout.addWidget(label('여러 카테고리에 함께 보관할 수 있어요.'))
        checks = []; selected = self.store.category_ids(ident)
        area = QScrollArea(); area.setWidgetResizable(True)
        holder = QWidget(); rows = QVBoxLayout(holder); area.setWidget(holder); layout.addWidget(area)

        def populate():
            current = {cid for cid, check in checks if check.isChecked()} if checks else set(selected)
            checks.clear(); self.clear_layout(rows)
            for cat in self.store.categories():
                check = QCheckBox(cat['name']); check.setChecked(cat['id'] in current)
                rows.addWidget(check); checks.append((cat['id'], check))
            rows.addStretch()

        def create():
            made = self.add_category()
            if made:
                populate()

        populate(); layout.addWidget(button('＋ 새 카테고리', create))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.assign(ident, [cid for cid, check in checks if check.isChecked()])
            self.refresh_sidebar()
            if self.view_name in ('category', 'all'):
                self.render()
            self.set_status('카테고리를 저장했습니다.')

    def show_detail(self, ident):
        item = self.store.get(ident)
        dialog = QDialog(self); dialog.setWindowTitle('이미지 미리보기'); dialog.resize(920, 800)
        layout = QVBoxLayout(dialog)
        picture = QLabel(); picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setMinimumSize(420, 420); layout.addWidget(picture, 1)
        title = label(item['title']); title.setWordWrap(True); layout.addWidget(title)
        info = label(item['source'] + (f' · 원본 {item["width"]} × {item["height"]}' if item['width'] else ''), 'muted')
        layout.addWidget(info)
        row = QHBoxLayout()
        like = button('  좋아요', lambda: (self.toggle_like(ident), refresh()))
        save = button('  원본 다운로드', lambda: self.download_image(ident))
        save.setIcon(icons.icon('download', self.colors['muted'], 16)); save.setIconSize(QSize(16, 16))
        tag = button('  카테고리', lambda: self.assign_categories(ident))
        tag.setIcon(icons.icon('tag', self.colors['muted'], 16)); tag.setIconSize(QSize(16, 16))
        source = button('  원본 출처', lambda: self.open_url(item['page_url'] or item['url']))
        source.setIcon(icons.icon('external-link', self.colors['muted'], 16)); source.setIconSize(QSize(16, 16))
        row.addWidget(like); row.addWidget(save); row.addWidget(tag); row.addStretch(); row.addWidget(source)
        layout.addLayout(row)

        def refresh():
            current = self.store.get(ident)
            liked = bool(current['liked'])
            like.setText('  좋아요 취소' if liked else '  좋아요')
            like.setIcon(icons.icon('heart', self.colors['like'] if liked else self.colors['muted'], 16, fill=liked))
            like.setIconSize(QSize(16, 16))
            path = next((current[k] for k in ('download_path', 'preview_path')
                         if current[k] and Path(current[k]).exists()), '')
            loaded = QPixmap(path) if path else QPixmap()
            if loaded.isNull():
                picture.setText('미리보기를 불러올 수 없습니다. 원본 출처를 열어보세요.')
                return
            ratio = dialog.devicePixelRatioF() or 1.0
            box_w = max(320, picture.width()); box_h = max(320, picture.height())
            scaled = loaded.scaled(int(box_w * ratio), int(box_h * ratio),
                                   Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(ratio)
            picture.setPixmap(scaled)

        self.detail_refresh = refresh
        refresh()
        QTimer.singleShot(0, refresh)
        dialog.exec()
        self.detail_refresh = None

    def settings(self):
        if self.searcher:
            self.searcher.settings_dialog(self)
        else:
            self.set_status('테스트 모드에서는 검색 설정을 사용할 수 없습니다.')

    @staticmethod
    def open_path(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @staticmethod
    def open_url(url):
        if url.startswith(('https://', 'http://')):
            QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        busy = bool(self.jobs) or (self.searcher and self.searcher.api_pool.activeThreadCount())
        if busy:
            self.set_status('이미지 저장을 마무리한 뒤 종료합니다…')
            if self.searcher:
                self.searcher.cancel()
            self.centralWidget().setEnabled(False)
            # Running downloads have bounded connection/read timeouts; do not destroy active jobs.
            event.ignore()
            if not self.closing:
                self.closing = True
                self.close_timer = QTimer(self); self.close_timer.setInterval(150)
                self.close_timer.timeout.connect(self.finish_close); self.close_timer.start()
            return
        for card in self.cards:
            card.stop_spinner()
        if self.searcher:
            self.searcher.shutdown()
        self.store.close(); event.accept()

    def finish_close(self):
        if self.pool.activeThreadCount() == 0 and (not self.searcher or self.searcher.api_pool.activeThreadCount() == 0):
            self.jobs.clear(); self.close_timer.stop(); self.close()
