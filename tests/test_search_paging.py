"""Pagination logic, driven with recorded payloads instead of live Google."""
import json
import os
from urllib.parse import urlencode

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--no-sandbox --disable-gpu --disable-dev-shm-usage')

import pytest
from PySide6.QtWidgets import QApplication, QWidget

app = QApplication.instance() or QApplication([])

QUERY = '미쿠 2D anime character illustration'


def payload(urls, query=QUERY):
    items = [{'url': url, 'thumbnail': url + '?t', 'title': 'title', 'source': 'example.com',
              'page_url': '', 'width': 0, 'height': 0} for url in urls]
    page = 'https://www.google.com/search?' + urlencode({'q': query, 'udm': '2'})
    return json.dumps({'items': items, 'url': page, 'count': len(items)})


@pytest.fixture
def searcher(tmp_path):
    from imagesearch.search import GoogleSearch
    parent = QWidget()
    engine = GoogleSearch(tmp_path, parent)
    engine.expected_query = QUERY
    yield engine
    engine.shutdown()
    parent.deleteLater()
    app.processEvents()


def test_first_page_then_more_pages_without_duplicates(searcher):
    first, more, availability = [], [], []
    searcher.results.connect(first.extend)
    searcher.more_results.connect(more.extend)
    searcher.more_state.connect(availability.append)

    searcher.active, searcher.mode = True, 'initial'
    searcher.receive(payload(['https://cdn.test/1.png', 'https://cdn.test/2.png']), searcher.generation)
    assert [i['url'] for i in first] == ['https://cdn.test/1.png', 'https://cdn.test/2.png']
    assert searcher.ready and availability[-1] is True

    # Scrolling re-reads the whole grid, so page one comes back with page two attached.
    searcher.active, searcher.mode = True, 'more'
    searcher.receive(payload(['https://cdn.test/1.png', 'https://cdn.test/3.png']), searcher.generation)
    assert [i['url'] for i in more] == ['https://cdn.test/3.png']
    assert len(searcher.seen) == 3


def test_repeated_empty_pages_end_the_search(searcher):
    searcher.active, searcher.mode = True, 'initial'
    searcher.receive(payload(['https://cdn.test/1.png']), searcher.generation)
    assert not searcher.exhausted
    for _ in range(searcher.IDLE_LIMIT):
        searcher.active, searcher.mode = True, 'more'
        searcher.receive(payload(['https://cdn.test/1.png']), searcher.generation)
    assert searcher.exhausted


def test_results_from_a_cancelled_search_are_ignored(searcher):
    received = []
    searcher.results.connect(received.extend)
    stale = searcher.generation
    searcher.cancel(stop=False)
    searcher.active, searcher.mode = True, 'initial'
    searcher.receive(payload(['https://cdn.test/1.png']), stale)
    assert received == []


def test_a_different_query_on_the_page_is_ignored(searcher):
    received = []
    searcher.results.connect(received.extend)
    searcher.active, searcher.mode = True, 'initial'
    searcher.receive(payload(['https://cdn.test/1.png'], query='다른 검색어'), searcher.generation)
    assert received == []


def test_a_new_search_resets_collected_state(searcher):
    searcher.active, searcher.mode = True, 'initial'
    searcher.receive(payload(['https://cdn.test/1.png']), searcher.generation)
    assert searcher.seen
    searcher.api_mode = True
    searcher.api_key = ''
    searcher.search('새 검색어', anime=False)
    assert searcher.seen == set() and not searcher.ready and not searcher.exhausted
