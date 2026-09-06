import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QCheckBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PIL import Image
from imagesearch.store import Store
from imagesearch.ui import Window

app = QApplication.instance() or QApplication([])


def seeded(tmp_path, count=1):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False)
    window.show(); app.processEvents()
    items = []
    for index in range(count):
        preview = tmp_path / f'image{index}.png'
        Image.new('RGB', (640, 480), '#ba9bcf').save(preview)
        item = store.upsert({'url': f'https://example.com/image{index}.png', 'title': f'미쿠 {index}',
                             'source': 'example.com'})
        store.update(item['id'], preview_path=str(preview))
        items.append(store.get(item['id']))
    window.receive_results(items); app.processEvents()
    return window, store, items


def test_ui_library_and_keyboard(tmp_path):
    window, store, items = seeded(tmp_path)
    item = items[0]
    assert len(window.cards) == 1
    QTest.mouseClick(window.cards[0].like, Qt.MouseButton.LeftButton)
    assert store.get(item['id'])['liked'] == 1
    window.navigate('liked'); assert len(window.cards) == 1
    cat = store.add_category('캐릭터'); window.refresh_sidebar()

    def accept_categories():
        dialog = app.activeModalWidget()
        dialog.findChild(QCheckBox).setChecked(True)
        dialog.accept()

    QTimer.singleShot(50, accept_categories); window.assign_categories(item['id'])
    assert store.category_ids(item['id']) == {cat}
    window.navigate('category', cat); assert len(window.cards) == 1
    window.filter.setText('없는 검색어'); assert window.stack.currentWidget() == window.empty
    window.filter.clear(); assert len(window.cards) == 1
    window.navigate('downloads'); assert not window.cards
    window.input.setPlainText('hello'); QTest.keyClick(window.input, Qt.Key.Key_Return)
    assert '테스트 모드' in window.status.text()
    window.close(); app.processEvents()


def test_theme_toggles_and_survives_a_restart(tmp_path):
    window, store, _ = seeded(tmp_path)
    assert window.mode == 'dark'
    dark_style = window.styleSheet()
    window.toggle_theme()
    assert window.mode == 'light' and window.styleSheet() != dark_style
    assert len(window.cards) == 1  # cards are rebuilt, not lost
    window.close(); app.processEvents()

    again = Window(Store(tmp_path / 'data'), browser=False)
    assert again.mode == 'light'
    again.toggle_theme()
    assert again.mode == 'dark' and again.store.setting('theme') == 'dark'
    again.close(); app.processEvents()


def test_more_pages_append_instead_of_replacing(tmp_path):
    window, store, _ = seeded(tmp_path, count=2)
    assert len(window.cards) == 2
    window.set_more_available(True)
    assert window.more_button.isVisible()
    window.append_results([{'url': 'https://example.com/next.png', 'title': '다음 페이지', 'source': 'example.com'}])
    app.processEvents()
    assert len(window.cards) == 3 and len(window.results) == 3
    # A repeat of an image already on screen must not create a second card.
    window.append_results([{'url': 'https://example.com/next.png', 'title': '다음 페이지', 'source': 'example.com'}])
    app.processEvents()
    assert len(window.cards) == 3
    window.close(); app.processEvents()


def test_previews_are_only_fetched_for_reachable_cards(tmp_path):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False)
    window.resize(1200, 800); window.show(); app.processEvents()
    asked = []
    window.queue_image = lambda item, kind: asked.append(item['id'])  # never touch the network here
    items = [store.upsert({'url': f'https://example.invalid/{n}.png', 'title': str(n), 'source': 'x'})
             for n in range(120)]
    window.receive_results(items); app.processEvents()
    window.after_layout(); app.processEvents()
    assert len(window.cards) == 120
    assert 0 < len(asked) < 120, f'lazy loading queued {len(asked)} of 120'
    assert all(card.queued for card in window.cards[:4])
    # Scrolling to the end reaches the cards that were skipped.
    bar = window.scroll.verticalScrollBar()
    bar.setValue(bar.maximum()); window.load_visible()
    assert window.cards[-1].queued
    window.close(); app.processEvents()


def test_card_renders_at_physical_pixel_resolution(tmp_path):
    """The old build scaled to logical points, so every image was half resolution on Retina."""
    window, store, items = seeded(tmp_path)
    card = window.cards[0]
    app.processEvents(); card.paint_image()
    shown = card.picture.pixmap()
    ratio = card.devicePixelRatioF() or 1.0
    assert shown.devicePixelRatio() == ratio
    box = (int(card.picture.width() * ratio), int(205 * ratio))
    assert shown.width() == box[0] or shown.height() == box[1], (shown.size(), box)
    window.close(); app.processEvents()


def test_a_tiny_source_is_not_stretched_into_mush(tmp_path):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False); window.show(); app.processEvents()
    small = tmp_path / 'small.png'
    Image.new('RGB', (90, 70), '#88aa66').save(small)
    item = store.upsert({'url': 'https://example.com/small.png', 'title': '작은 이미지', 'source': 'x'})
    store.update(item['id'], preview_path=str(small))
    window.receive_results([store.get(item['id'])]); app.processEvents()
    card = window.cards[0]; card.paint_image()
    shown = card.picture.pixmap()
    assert shown.width() <= int(90 * 1.4) + 1 and shown.height() <= int(70 * 1.4) + 1
    window.close(); app.processEvents()
