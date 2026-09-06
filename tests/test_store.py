import pytest
from imagesearch.store import Store

@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path); yield s; s.close()

@pytest.fixture
def item():
    return {'url':'https://example.com/miku.png','thumbnail':'https://example.com/small.png','title':'미쿠 100%_blue','source':'example.com'}

def test_persistence_and_upsert_preserves_library(tmp_path,item):
    s=Store(tmp_path); i=s.upsert(item); c=s.add_category('캐릭터')
    s.update(i['id'],liked=1,download_path='/test/original.png',preview_path='/test/thumb.jpg'); s.assign(i['id'],[c]); s.close()
    s=Store(tmp_path); new=s.upsert(dict(item,title='새 제목'))
    assert new['liked']==1 and new['download_path']=='/test/original.png'
    assert new['preview_path']=='/test/thumb.jpg' and s.category_ids(i['id'])=={c}
    assert len(s.list_images('liked'))==1 and len(s.list_images('downloads'))==1
    s.close()

def test_multiple_categories_and_delete_preserves_files(store,item):
    i=store.upsert(item); a=store.add_category('A'); b=store.add_category('B')
    store.assign(i['id'],[a,b]); store.update(i['id'],liked=1,download_path='disk.png')
    assert len(store.list_images('category',a))==1
    store.delete_category(a)
    assert store.category_ids(i['id'])=={b}
    assert store.get(i['id'])['download_path']=='disk.png'
    store.rename_category(b,'새 이름'); assert store.categories()[0]['name']=='새 이름'

def test_unsaved_search_is_not_library(store,item):
    i=store.upsert(item); assert store.list_images()==[]
    c=store.add_category('분류'); store.assign(i['id'],[c]); assert len(store.list_images())==1
    store.assign(i['id'],[]); assert store.list_images()==[]

@pytest.mark.parametrize('name',['','   ','x'*61])
def test_category_validation(store,name):
    with pytest.raises(ValueError): store.add_category(name)

def test_category_duplicate(store):
    store.add_category('Anime')
    with pytest.raises(ValueError): store.add_category('anime')

def test_literal_filter(store,item):
    i=store.upsert(item); store.update(i['id'],liked=1)
    assert len(store.list_images('liked',term='%_'))==1
    assert store.list_images('liked',term='%oops')==[]

def test_history_bounded(store):
    for n in range(22): store.remember(str(n))
    store.remember('21')
    assert len(store.history())==8 and store.history()[0]=='21'
    assert store.db.execute('SELECT COUNT(*) FROM searches').fetchone()[0]==15
