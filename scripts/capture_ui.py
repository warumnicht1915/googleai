"""Capture the real widgets against synthetic local fixtures.

Nothing here reads or writes the user's library: every image is generated in a
temporary directory and thrown away when the script exits.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_SCALE_FACTOR', '2')  # render the docs shots at 2x

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFilter
from PySide6.QtWidgets import QApplication
from imagesearch.store import Store
from imagesearch.ui import Window

OUT = Path('docs/images')
SWATCHES = [
    ((92, 78, 140), (196, 150, 190), '미코토 · 밤거리 팬아트'),
    ((36, 92, 108), (150, 208, 208), '미코토 여름 교복 일러스트'),
    ((132, 70, 74), (238, 172, 150), '미코토 · 노을빛 일러스트'),
    ((58, 84, 62), (170, 214, 150), '미코토 캐릭터 시트 · 컨셉'),
    ((74, 68, 122), (176, 168, 232), '미코토 · 전격 이펙트 연습'),
    ((122, 96, 52), (232, 202, 138), '미코토 사복 코디 러프'),
    ((104, 58, 96), (216, 158, 200), '미코토 · 축제의 밤'),
    ((48, 62, 98), (146, 172, 226), '미코토 · 비 오는 거리'),
]


def artwork(path: Path, top, bottom, seed: int, size=(1000, 1250)):
    width, height = size
    image = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        blend = y / height
        draw.line([(0, y), (width, y)],
                  fill=tuple(int(a + (b - a) * blend) for a, b in zip(top, bottom)))
    glow = Image.new('RGB', (width, height), (0, 0, 0))
    halo = ImageDraw.Draw(glow)
    halo.ellipse((width * 0.16, height * 0.10, width * 0.84, height * 0.62),
                 fill=tuple(min(255, c + 46) for c in bottom))
    halo.rounded_rectangle((width * 0.12, height * 0.52, width * 0.88, height * 1.06),
                           width * 0.22, fill=tuple(max(0, c - 26) for c in top))
    image = Image.blend(image, glow.filter(ImageFilter.GaussianBlur(width * 0.05)), 0.55)
    draw = ImageDraw.Draw(image)
    accent = tuple(min(255, c + 70) for c in bottom)
    draw.ellipse((width * 0.30, height * 0.26, width * 0.36, height * 0.33), fill=accent)
    draw.ellipse((width * 0.62, height * 0.26, width * 0.68, height * 0.33), fill=accent)
    for step in range(6):
        offset = (seed * 37 + step * 53) % 100 / 100
        radius = width * (0.012 + 0.010 * offset)
        cx, cy = width * (0.08 + 0.16 * step), height * (0.14 + 0.11 * ((step + seed) % 5))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     fill=tuple(min(255, c + 90) for c in bottom))
    image.save(path, 'PNG')


def seed(store: Store, workspace: Path):
    items = []
    for index, (top, bottom, title) in enumerate(SWATCHES):
        preview = workspace / f'art{index}.png'
        artwork(preview, top, bottom, index)
        item = store.upsert({'url': f'https://example.invalid/art{index}.png',
                             'thumbnail': f'https://example.invalid/art{index}-thumb.png',
                             'title': title, 'source': '로컬 테스트 픽스처',
                             'width': 1000, 'height': 1250})
        store.update(item['id'], preview_path=str(preview))
        if index % 3 != 2:
            store.update(item['id'], liked=1)
        if index % 4 != 1:
            store.update(item['id'], download_path=str(preview))
        items.append(store.get(item['id']))
    categories = [store.add_category(name) for name in ('미코토', '포즈 참고', '색감 레퍼런스')]
    for index, item in enumerate(items):
        chosen = [categories[index % 3]] + ([categories[2]] if index % 2 == 0 else [])
        store.assign(item['id'], sorted(set(chosen)))
    for query in ('미코토 일러스트', '미사카 미코토 팬아트', '애니메이션 배경'):
        store.remember(query)
    return items


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    workspace = tempfile.TemporaryDirectory()
    root = Path(workspace.name)
    store = Store(root / 'library')
    window = Window(store, browser=False)
    window.resize(1360, 900)
    window.show()
    app.processEvents()

    window.grab().save(str(OUT / 'app-welcome.png'))

    items = seed(store, root)
    window.refresh_sidebar()
    window.query = '미코토 일러스트'
    window.receive_results(items)
    window.set_more_available(True)
    window.set_status('Google 이미지 8개를 찾았습니다. 아래로 스크롤하면 더 불러옵니다.')
    for _ in range(4):
        app.processEvents()
    window.after_layout()
    for _ in range(4):
        app.processEvents()
    window.grab().save(str(OUT / 'app-dark.png'))

    window.apply_theme('light')
    window.refresh_sidebar()
    window.render()
    window.set_more_available(True)
    window.set_status('Google 이미지 8개를 찾았습니다. 아래로 스크롤하면 더 불러옵니다.')
    for _ in range(4):
        app.processEvents()
    window.grab().save(str(OUT / 'app-light.png'))

    window.apply_theme('dark')
    window.navigate('liked')
    window.set_status('검색하지 않아도 좋아요와 다운로드는 오프라인에서 그대로 열립니다.')
    for _ in range(4):
        app.processEvents()
    window.grab().save(str(OUT / 'app-library.png'))

    window.close()
    app.processEvents()
    store.close()
    workspace.cleanup()
    for name in ('app-welcome', 'app-dark', 'app-light', 'app-library'):
        path = OUT / f'{name}.png'
        print(f'{path}  {path.stat().st_size // 1024} KB')


if __name__ == '__main__':
    main()
