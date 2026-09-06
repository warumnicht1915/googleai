from __future__ import annotations
import hashlib
import os
import sqlite3
from pathlib import Path


def data_root() -> Path:
    override = os.environ.get('IMAGESEARCH_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    import sys
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/ImageSearch'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ImageSearch'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'imagesearch'


def image_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:24]


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or data_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache = self.root / 'previews'
        self.downloads = self.root / 'downloads'
        self.cache.mkdir(exist_ok=True)
        self.downloads.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / 'library.sqlite3')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.execute('PRAGMA journal_mode = WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS images (
            id TEXT PRIMARY KEY, url TEXT NOT NULL, thumbnail TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', page_url TEXT NOT NULL DEFAULT '',
            width INTEGER DEFAULT 0, height INTEGER DEFAULT 0,
            liked INTEGER NOT NULL DEFAULT 0, preview_path TEXT NOT NULL DEFAULT '',
            download_path TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE);
        CREATE TABLE IF NOT EXISTS image_categories (
            image_id TEXT REFERENCES images(id) ON DELETE CASCADE,
            category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
            PRIMARY KEY (image_id, category_id));
        CREATE TABLE IF NOT EXISTS searches (
            query TEXT PRIMARY KEY, searched_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
        ''')
        self.db.commit()

    def upsert(self, item: dict) -> dict:
        item = dict(item)
        item['id'] = image_id(item['url'])
        fields = ('id', 'url', 'thumbnail', 'title', 'source', 'page_url', 'width', 'height')
        vals = [item.get(k, 0 if k in ('width', 'height') else '') for k in fields]
        self.db.execute('''INSERT INTO images(id,url,thumbnail,title,source,page_url,width,height)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            thumbnail=excluded.thumbnail,title=excluded.title,source=excluded.source,
            page_url=excluded.page_url,width=excluded.width,height=excluded.height''', vals)
        self.db.commit()
        return self.get(item['id'])

    def get(self, ident: str) -> dict:
        row = self.db.execute('SELECT * FROM images WHERE id=?', (ident,)).fetchone()
        return dict(row) if row else {}

    def update(self, ident: str, **values):
        if not values or not set(values) <= {'liked', 'preview_path', 'download_path'}:
            raise ValueError('Invalid update')
        self.db.execute('UPDATE images SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?',
                        [*values.values(), ident])
        self.db.commit()

    def list_images(self, view='all', category=None, term='') -> list[dict]:
        clauses, args = [], []
        if view == 'liked':
            clauses.append('liked=1')
        elif view == 'downloads':
            clauses.append("download_path<>''")
        elif view == 'all':
            clauses.append("(liked=1 OR download_path<>'' OR EXISTS(SELECT 1 FROM image_categories c WHERE c.image_id=images.id))")
        if category is not None:
            clauses.append('id IN (SELECT image_id FROM image_categories WHERE category_id=?)')
            args.append(category)
        if term:
            clauses.append("(title LIKE ? ESCAPE '\\' OR source LIKE ? ESCAPE '\\')")
            term = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            args += [f'%{term}%', f'%{term}%']
        sql = 'SELECT * FROM images' + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
        return [dict(r) for r in self.db.execute(sql + ' ORDER BY created_at DESC, rowid DESC', args)]

    def categories(self):
        return [dict(r) for r in self.db.execute('''SELECT c.id,c.name,COUNT(ic.image_id) AS count
            FROM categories c LEFT JOIN image_categories ic ON c.id=ic.category_id
            GROUP BY c.id ORDER BY c.name COLLATE NOCASE''')]

    def add_category(self, name):
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError('카테고리는 1~60자로 입력해 주세요.')
        try:
            with self.db:
                cur = self.db.execute('INSERT INTO categories(name) VALUES(?)', (name,))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError('같은 이름의 카테고리가 이미 있습니다.') from None

    def rename_category(self, ident, name):
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError('카테고리는 1~60자로 입력해 주세요.')
        try:
            with self.db:
                self.db.execute('UPDATE categories SET name=? WHERE id=?', (name, ident))
        except sqlite3.IntegrityError:
            raise ValueError('같은 이름의 카테고리가 이미 있습니다.') from None

    def delete_category(self, ident):
        with self.db:
            self.db.execute('DELETE FROM categories WHERE id=?', (ident,))

    def category_ids(self, ident):
        return {r[0] for r in self.db.execute('SELECT category_id FROM image_categories WHERE image_id=?', (ident,))}

    def assign(self, ident, categories):
        with self.db:
            self.db.execute('DELETE FROM image_categories WHERE image_id=?', (ident,))
            self.db.executemany('INSERT INTO image_categories VALUES(?,?)', [(ident, c) for c in categories])

    def remember(self, query):
        with self.db:
            self.db.execute('INSERT INTO searches(query) VALUES(?) ON CONFLICT(query) DO UPDATE SET searched_at=CURRENT_TIMESTAMP', (query,))
            self.db.execute('DELETE FROM searches WHERE query NOT IN (SELECT query FROM searches ORDER BY searched_at DESC,rowid DESC LIMIT 15)')

    def setting(self, key, default=''):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def save_setting(self, key, value):
        with self.db:
            self.db.execute('INSERT INTO settings(key,value) VALUES(?,?) '
                            'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))

    def history(self):
        return [r[0] for r in self.db.execute('SELECT query FROM searches ORDER BY searched_at DESC,rowid DESC LIMIT 8')]

    def close(self):
        self.db.close()
