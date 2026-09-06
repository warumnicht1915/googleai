import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication
from imagesearch import icons
from imagesearch.theme import PALETTES, DARK, LIGHT, build_style

app = QApplication.instance() or QApplication([])


@pytest.mark.parametrize('mode', sorted(PALETTES))
def test_every_palette_defines_every_token(mode):
    assert set(PALETTES[mode]) == set(DARK) == set(LIGHT)
    style = build_style(mode)
    assert '$' not in style and 'QPushButton#heart' in style


def test_light_and_dark_are_actually_different():
    assert build_style('light') != build_style('dark')
    assert DARK['bg'] != LIGHT['bg'] and DARK['text'] != LIGHT['text']


def test_every_icon_the_ui_asks_for_is_bundled():
    used = {'search', 'layout-grid', 'heart', 'download', 'plus', 'settings', 'folder-open',
            'sun', 'moon', 'tag', 'arrow-up', 'x', 'external-link', 'sparkles', 'chevron-down',
            'check', 'loader-circle', 'image'}
    assert used <= set(icons.available())


def test_icons_render_in_the_requested_colour():
    icons.clear_cache()
    dark = icons.pixmap('heart', DARK['like'], 18, fill=True)
    light = icons.pixmap('heart', LIGHT['like'], 18, fill=True)
    assert not dark.isNull() and not light.isNull()
    assert dark.toImage() != light.toImage()
    assert dark.size().width() == int(18 * icons.ratio())


def test_rotated_icons_are_cached_per_angle():
    icons.clear_cache()
    upright = icons.pixmap('loader-circle', '#ffffff', 15)
    turned = icons.pixmap('loader-circle', '#ffffff', 15, angle=90)
    assert upright.toImage() != turned.toImage()


def test_rounded_keeps_device_pixel_ratio():
    source = icons.pixmap('image', '#ffffff', 40)
    out = icons.rounded(source, 8)
    assert out.devicePixelRatio() == source.devicePixelRatio()
    assert out.size() == source.size()


def test_icon_accepts_every_pixmap_argument():
    """icon() forwards to pixmap(); a missing keyword only ever fails at runtime in a slot."""
    import inspect
    pixmap_args = set(inspect.signature(icons.pixmap).parameters)
    icon_args = set(inspect.signature(icons.icon).parameters)
    assert pixmap_args <= icon_args, f'icon() is missing {pixmap_args - icon_args}'
    assert not icons.icon('loader-circle', '#ffffff', 15, angle=90).isNull()
