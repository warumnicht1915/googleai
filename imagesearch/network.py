"""Bounded background image fetches. SQLite and widgets stay on the main thread.

Previews now come from the ORIGINAL image, not Google's ~250px thumbnail; the
thumbnail is only a fallback when the original host refuses us.
"""
from __future__ import annotations
import base64
import io
import os
import uuid
import time
import warnings
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal

MAX_BYTES = 35 * 1024 * 1024          # hard ceiling for a download
PREVIEW_MAX_BYTES = 18 * 1024 * 1024  # a preview never pulls more than this
PREVIEW_EDGE = 1600                   # longest side kept in the preview cache
KEEP_ORIGINAL_BYTES = 1_600_000       # below this the original file is cached untouched
Image.MAX_IMAGE_PIXELS = 50_000_000
USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/125.0 Safari/537.36')


def fetch_image(url: str, referer='', limit=MAX_BYTES, progress=None) -> tuple[bytes, str]:
    if url.startswith('data:image/'):
        header, payload = url.split(',', 1)
        if ';base64' not in header or len(payload) > limit * 1.4:
            raise ValueError('지원하지 않는 이미지 데이터입니다.')
        data = base64.b64decode(payload, validate=True)
    else:
        if urlparse(url).scheme not in ('https', 'http'):
            raise ValueError('HTTP/HTTPS 이미지 주소만 지원합니다.')
        headers = {'User-Agent': USER_AGENT, 'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8'}
        if referer.startswith(('https://', 'http://')):
            headers['Referer'] = referer
        with requests.get(url, headers=headers, timeout=(8, 20), stream=True) as response:
            response.raise_for_status()
            try:
                expected = int(response.headers.get('Content-Length') or 0)
            except ValueError:
                expected = 0
            chunks, total = [], 0
            started = time.monotonic()
            for chunk in response.iter_content(65536):
                if time.monotonic() - started > 60:
                    raise ValueError('다운로드 시간 제한(60초)을 초과했습니다.')
                total += len(chunk)
                if total > limit:
                    raise ValueError(f'이미지가 {limit // (1024 * 1024)}MB 제한을 초과했습니다.')
                chunks.append(chunk)
                if progress and expected:
                    progress(min(99, int(total * 100 / expected)))
            data = b''.join(chunks)
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    ext = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif',
           'AVIF': 'avif', 'BMP': 'bmp', 'TIFF': 'tiff'}.get(fmt)
    if not ext:
        raise ValueError('지원하지 않는 이미지 형식입니다.')
    return data, ext


def make_preview(data: bytes, ext: str) -> tuple[bytes, str]:
    """Keep small originals byte-for-byte; downscale only what is genuinely oversized."""
    if ext == 'gif':
        return data, ext
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
    except Exception:
        return data, ext
    if len(data) <= KEEP_ORIGINAL_BYTES and max(width, height) <= PREVIEW_EDGE:
        return data, ext
    with Image.open(io.BytesIO(data)) as image:
        if ext == 'jpg':
            image.draft('RGB', (PREVIEW_EDGE, PREVIEW_EDGE))
        image.load()
        transparent = image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info)
        work = image.convert('RGBA') if transparent else image.convert('RGB')
        if max(work.size) > PREVIEW_EDGE:
            work.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.LANCZOS)
        buffer = io.BytesIO()
        if transparent:
            work.save(buffer, 'PNG', optimize=True)
            return buffer.getvalue(), 'png'
        work.save(buffer, 'JPEG', quality=92, subsampling=0, optimize=True, progressive=True)
        return buffer.getvalue(), 'jpg'


def save_atomic(path: Path, data: bytes):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.part')
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def clear_siblings(directory: Path, ident: str, keep: Path):
    for stale in directory.glob(f'{ident}.*'):
        if stale != keep and not stale.name.endswith('.part'):
            stale.unlink(missing_ok=True)


class Signals(QObject):
    done = Signal(str, str, str)     # id, kind, path
    error = Signal(str, str, str)    # id, kind, message
    progress = Signal(str, str, int)  # id, kind, percent


class ImageJob(QRunnable):
    def __init__(self, item, directory: Path, kind='preview'):
        super().__init__()
        self.item, self.directory, self.kind = dict(item), directory, kind
        self.signals = Signals()

    def sources(self) -> list[str]:
        original, thumbnail = self.item.get('url'), self.item.get('thumbnail')
        if self.kind == 'download':
            return [original]
        # Preview quality comes first: the original, then Google's thumbnail as a fallback.
        return [original, thumbnail]

    def run(self):
        ident = self.item['id']
        limit = MAX_BYTES if self.kind == 'download' else PREVIEW_MAX_BYTES
        report = (lambda pct: self.signals.progress.emit(ident, self.kind, pct)) if self.kind == 'download' else None
        try:
            error = None
            for url in dict.fromkeys(filter(None, self.sources())):
                try:
                    data, ext = fetch_image(url, self.item.get('page_url', ''), limit, report)
                    if self.kind == 'preview':
                        data, ext = make_preview(data, ext)
                    path = self.directory / f'{ident}.{ext}'
                    save_atomic(path, data)
                    clear_siblings(self.directory, ident, path)
                    self.signals.done.emit(ident, self.kind, str(path))
                    return
                except Exception as exc:
                    error = exc
            raise error or ValueError('이미지 주소가 없습니다.')
        except Exception as exc:
            message = str(exc)
            if isinstance(exc, requests.RequestException):
                message = '서버 연결 실패 또는 원본 사이트에서 접근을 거부했습니다.'
            self.signals.error.emit(ident, self.kind, message)


class DerivePreviewJob(QRunnable):
    """Build a preview from a file already on disk — no second network round trip."""

    def __init__(self, ident: str, source_path: str, directory: Path):
        super().__init__()
        self.ident, self.source_path, self.directory = ident, source_path, directory
        self.signals = Signals()

    def run(self):
        try:
            data = Path(self.source_path).read_bytes()
            ext = Path(self.source_path).suffix.lstrip('.').lower() or 'jpg'
            data, ext = make_preview(data, ext)
            path = self.directory / f'{self.ident}.{ext}'
            save_atomic(path, data)
            clear_siblings(self.directory, self.ident, path)
            self.signals.done.emit(self.ident, 'preview', str(path))
        except Exception as exc:
            self.signals.error.emit(self.ident, 'preview', str(exc))
