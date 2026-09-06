import base64
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from PIL import Image
from pathlib import Path
from imagesearch.network import (fetch_image, make_preview, referer_candidates, remove_files,
                                ImageJob, DerivePreviewJob, AdoptFileJob, PREVIEW_EDGE)


def png(size=(160, 120), color='teal'):
    buf = io.BytesIO(); Image.new('RGB', size, color).save(buf, 'PNG'); return buf.getvalue()


def big_jpeg(size=(2400, 1800)):
    buf = io.BytesIO(); Image.new('RGB', size, 'purple').save(buf, 'JPEG', quality=90); return buf.getvalue()


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route = self.path.split('?')[0]
            bodies = {'/image': png(), '/tiny': png((48, 36), 'olive'), '/large': big_jpeg(),
                      '/html': b'<html>not an image</html>'}
            self.send_response(200 if route in bodies else 403)
            self.end_headers()
            self.wfile.write(bodies.get(route, b''))

        def log_message(self, *args):
            pass

    service = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{service.server_port}'
    service.shutdown(); service.server_close()


def test_download_real_http_and_format(server, tmp_path):
    data, ext = fetch_image(server + '/image')
    assert ext == 'png' and data == png()
    job = ImageJob({'id': 'image', 'url': server + '/image'}, tmp_path, 'download'); job.run()
    assert (tmp_path / 'image.png').read_bytes() == png()
    assert not list(tmp_path.glob('*.part'))


def test_preview_uses_the_original_not_the_thumbnail(server, tmp_path):
    """The old build cached Google's ~250px thumbnail; the preview must be the real image."""
    job = ImageJob({'id': 'quality', 'url': server + '/image', 'thumbnail': server + '/tiny'}, tmp_path)
    job.run()
    saved = next(tmp_path.glob('quality.*'))
    with Image.open(saved) as image:
        assert image.size == (160, 120)


def test_preview_falls_back_to_thumbnail_when_the_host_refuses(server, tmp_path):
    job = ImageJob({'id': 'thumb', 'url': server + '/denied', 'thumbnail': server + '/image'}, tmp_path)
    job.run()
    saved = next(tmp_path.glob('thumb.*'))
    with Image.open(saved) as image:
        assert image.size == (160, 120)


def test_preview_downscales_only_oversized_images(server, tmp_path):
    job = ImageJob({'id': 'huge', 'url': server + '/large'}, tmp_path); job.run()
    saved = next(tmp_path.glob('huge.*'))
    with Image.open(saved) as image:
        assert max(image.size) == PREVIEW_EDGE and image.size == (PREVIEW_EDGE, 1200)


def test_small_original_is_cached_byte_for_byte():
    source = png()
    data, ext = make_preview(source, 'png')
    assert ext == 'png' and data == source


def test_preview_keeps_transparency():
    buf = io.BytesIO()
    Image.new('RGBA', (2000, 2000), (255, 0, 0, 90)).save(buf, 'PNG')
    data, ext = make_preview(buf.getvalue(), 'png')
    assert ext == 'png'
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == 'RGBA' and max(image.size) == PREVIEW_EDGE


def test_derive_preview_reuses_a_downloaded_file(tmp_path):
    original = tmp_path / 'source.jpg'
    original.write_bytes(big_jpeg())
    out = tmp_path / 'cache'; out.mkdir()
    job = DerivePreviewJob('derived', str(original), out); job.run()
    saved = next(out.glob('derived.*'))
    with Image.open(saved) as image:
        assert max(image.size) == PREVIEW_EDGE


def test_stale_cache_files_are_replaced(server, tmp_path):
    (tmp_path / 'swap.gif').write_bytes(b'stale')
    job = ImageJob({'id': 'swap', 'url': server + '/image'}, tmp_path); job.run()
    assert not (tmp_path / 'swap.gif').exists()
    assert (tmp_path / 'swap.png').exists()


def test_html_and_http_errors_rejected(server):
    with pytest.raises(Exception):
        fetch_image(server + '/html')
    with pytest.raises(Exception):
        fetch_image(server + '/denied')


def test_data_url():
    data, ext = fetch_image('data:image/png;base64,' + base64.b64encode(png()).decode())
    assert ext == 'png' and data == png()


def test_non_http_rejected():
    with pytest.raises(ValueError):
        fetch_image('file:///etc/passwd')


@pytest.fixture
def picky():
    """A host that serves the image only to a Referer from its own site."""
    class Handler(BaseHTTPRequestHandler):
        seen = []

        def do_GET(self):
            referer = self.headers.get('Referer', '')
            Handler.seen.append(referer)
            allowed = referer.startswith(f'http://127.0.0.1:{self.server.server_port}/')
            if self.path == '/nobody':
                allowed = referer == ''
            if not allowed:
                self.send_response(403); self.end_headers(); return
            self.send_response(200); self.end_headers(); self.wfile.write(png())

        def log_message(self, *args):
            pass

    Handler.seen = []
    service = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{service.server_port}', Handler
    service.shutdown(); service.server_close()


def test_referer_ladder_recovers_a_hotlink_block(picky):
    """The page's Referer is refused; the image host's own origin is accepted."""
    base, handler = picky
    data, ext = fetch_image(base + '/art.png', referer='https://somewhere.example/post/1')
    assert ext == 'png' and data == png()
    assert handler.seen[0] == 'https://somewhere.example/post/1'
    assert handler.seen[-1] == base + '/'


def test_referer_ladder_falls_through_to_no_referer(picky):
    base, handler = picky
    data, ext = fetch_image(base + '/nobody', referer='https://somewhere.example/post/1')
    assert ext == 'png' and data == png()
    assert handler.seen[-1] == ''


def test_known_hosts_get_the_referer_they_expect():
    candidates = referer_candidates('https://i.pximg.net/img/78.png', 'https://www.pixiv.net/artworks/78')
    assert candidates[0] == 'https://www.pixiv.net/'
    assert '' in candidates and candidates[-1] == ''
    plain = referer_candidates('https://cdn.example.com/a.png', 'https://blog.example/post')
    assert plain[0] == 'https://blog.example/post'
    assert 'https://cdn.example.com/' in plain


def test_a_host_that_refuses_everything_asks_for_the_browser(server, tmp_path):
    """A refusal is not a plain error: the window escalates it to the in-app browser."""
    refused, failed = [], []
    job = ImageJob({'id': 'blocked', 'url': server + '/denied', 'page_url': 'https://blog.example/p'},
                   tmp_path, 'download')
    job.signals.refused.connect(lambda ident, kind, url: refused.append((ident, kind, url)))
    job.signals.error.connect(lambda *a: failed.append(a))
    job.run()
    assert refused == [('blocked', 'download', server + '/denied')]
    assert not failed


def test_adopting_a_browser_download(tmp_path):
    staged = tmp_path / 'blocked.browser-part'
    staged.write_bytes(big_jpeg((900, 700)))
    out = tmp_path / 'downloads'; out.mkdir()
    saved = []
    job = AdoptFileJob('blocked', str(staged), out, 'download')
    job.signals.done.connect(lambda ident, kind, path: saved.append(path))
    job.run()
    assert saved and Path(saved[0]).name == 'blocked.jpg'
    assert not staged.exists()  # the temporary file is cleaned up either way


def test_adopting_a_file_that_is_not_an_image_fails_cleanly(tmp_path):
    staged = tmp_path / 'junk.browser-part'
    staged.write_bytes(b'<html>blocked by cloudflare</html>')
    out = tmp_path / 'downloads'; out.mkdir()
    problems = []
    job = AdoptFileJob('junk', str(staged), out)
    job.signals.error.connect(lambda ident, kind, message: problems.append(message))
    job.run()
    assert problems and not list(out.iterdir()) and not staged.exists()


def test_remove_files_ignores_what_is_already_gone(tmp_path):
    present = tmp_path / 'a.png'; present.write_bytes(png())
    assert remove_files(str(present), str(tmp_path / 'missing.png'), '', None) == 1
    assert not present.exists()
