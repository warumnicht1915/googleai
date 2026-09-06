import base64
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from PIL import Image
from imagesearch.network import fetch_image, make_preview, ImageJob, DerivePreviewJob, PREVIEW_EDGE


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
