import os
from pathlib import Path

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


def test_download_spinner_animates_without_raising(tmp_path):
    """Qt swallows exceptions raised inside a slot, so drive the animation and watch excepthook."""
    import sys
    escaped = []
    original = sys.excepthook
    sys.excepthook = lambda *info: escaped.append(info)
    try:
        window, store, items = seeded(tmp_path)
        card = window.cards[0]
        card.start_spinner()
        assert card.spinner is not None
        for step in range(0, 960, 60):
            card.spinner.setCurrentTime(step)
            app.processEvents()
        card.stop_spinner()
        card.pop_saved()
        card.animate_like(True)
        card.animate_like(False)
        card.fade_in()
        for _ in range(6):
            app.processEvents(); QTest.qWait(20)
        window.close(); app.processEvents()
    finally:
        sys.excepthook = original
    assert not escaped, escaped


def saved_item(tmp_path, store, window, name='saved'):
    original = tmp_path / f'{name}-original.png'
    preview = tmp_path / f'{name}-preview.png'
    Image.new('RGB', (900, 700), '#7788cc').save(original)
    Image.new('RGB', (300, 240), '#7788cc').save(preview)
    item = store.upsert({'url': f'https://example.com/{name}.png', 'title': f'{name} 이미지', 'source': 'example.com'})
    store.update(item['id'], download_path=str(original), preview_path=str(preview), liked=1)
    window.receive_results([store.get(item['id'])]); app.processEvents()
    return store.get(item['id']), original, preview


def test_deleting_a_download_keeps_the_rest_of_the_library(tmp_path):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False); window.show(); app.processEvents()
    item, original, preview = saved_item(tmp_path, store, window)
    card = window.cards[0]
    assert card.trash.isVisible() and ' 저장됨' == card.download.text()

    assert window.delete_download(item['id'], confirm=False) is True
    assert not original.exists()
    fresh = store.get(item['id'])
    assert fresh['download_path'] == ''
    assert fresh['liked'] == 1 and Path(fresh['preview_path']).exists()
    app.processEvents()
    assert not window.cards[0].trash.isVisible()
    assert window.cards[0].download.text() == ' 저장'
    assert not window.store.list_images('downloads')
    window.close(); app.processEvents()


def test_deleting_a_download_that_is_already_gone_repairs_the_row(tmp_path):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False); window.show(); app.processEvents()
    item, original, _ = saved_item(tmp_path, store, window)
    original.unlink()  # the user removed it in Finder
    assert window.delete_download(item['id'], confirm=False) is False
    assert store.get(item['id'])['download_path'] == ''
    window.close(); app.processEvents()


def test_forgetting_an_image_removes_its_files_and_row(tmp_path):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False); window.show(); app.processEvents()
    item, original, preview = saved_item(tmp_path, store, window)
    category = store.add_category('정리함'); store.assign(item['id'], [category])
    window.refresh_sidebar()

    assert window.forget_image(item['id'], confirm=False) is True
    assert not original.exists() and not preview.exists()
    assert store.get(item['id']) == {}
    assert store.category_ids(item['id']) == set()
    assert window.results == [] and window.cards == []
    window.close(); app.processEvents()


def test_a_refusal_without_a_browser_is_reported_not_retried(tmp_path):
    store = Store(tmp_path / 'data')
    window = Window(store, browser=False); window.show(); app.processEvents()
    window.queue_image = lambda item, kind: None  # no real network from this test
    item = store.upsert({'url': 'https://blocked.example/a.png', 'title': '차단', 'source': 'blocked.example'})
    window.receive_results([store.get(item['id'])]); app.processEvents()
    window.jobs[(item['id'], 'download')] = object()
    window.image_refused(item['id'], 'download', 'https://blocked.example/a.png')
    assert (item['id'], 'download') not in window.jobs
    assert '거부' in window.status.text()
    window.close(); app.processEvents()
