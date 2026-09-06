# 개발 가이드

## 환경

Python 3.10 이상. 개발과 CI는 3.11 / 3.13에서 수행합니다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python main.py
```

Linux에서 Qt를 띄우려면 시스템 라이브러리가 필요합니다.

```sh
sudo apt-get install -y libegl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libnss3 libasound2t64
```

## 모듈 구성

| 파일 | 책임 | 알아 둘 점 |
|---|---|---|
| `main.py` | QApplication 부팅, 앱 아이콘, 중복 실행 방지(`QLockFile`) | GUI 이외의 로직 없음 |
| `imagesearch/ui.py` | 창, 사이드바, 카드 격자, 애니메이션, 지연 로딩 | SQLite와 위젯은 항상 메인 스레드 |
| `imagesearch/search.py` | Google 결과 추출, 스크롤 페이징, SerpApi | 파싱 규칙이 모두 여기 모여 있음 |
| `imagesearch/network.py` | 이미지 수집, 미리보기 생성 | `QRunnable` 워커, 네트워크는 여기서만 |
| `imagesearch/store.py` | SQLite 스키마, 라이브러리, 카테고리, 설정 | 스키마 변경은 `CREATE TABLE IF NOT EXISTS` 로 누적 |
| `imagesearch/theme.py` | 라이트/다크 팔레트와 스타일시트 템플릿 | 색상은 전부 팔레트 토큰으로만 |
| `imagesearch/icons.py` | Lucide SVG → 테마 색 고해상도 픽스맵 | `(이름, 색, 크기, 채움, 각도, DPR)` 로 캐시 |

### 스레드 규칙

- 네트워크는 `QThreadPool` 위의 `ImageJob` / `DerivePreviewJob` 에서만 수행합니다.
- 워커는 시그널로만 결과를 알립니다. 워커에서 SQLite나 위젯을 만지지 않습니다.
- 창을 닫을 때 진행 중인 작업이 있으면 종료를 미루고 마무리합니다 (`closeEvent` → `finish_close`).

### 화질 파이프라인

1. `ImageJob(kind='preview')` 가 **원본 URL을 먼저** 시도하고, 실패하면 `thumbnail` 로 대체합니다.
2. `make_preview()` 는 1600px 이하이면서 1.6MB 미만인 원본을 **바이트 그대로** 보관하고, 그보다 크면 긴 변 1600px로 줄입니다. 투명도가 있으면 PNG, 아니면 품질 92 JPEG.
3. `Card.paint_image()` 는 `devicePixelRatioF()` 를 곱한 물리 픽셀 크기로 스케일하고 `setDevicePixelRatio()` 를 붙입니다. 이걸 빠뜨리면 Retina에서 절반 해상도로 보입니다.
4. 원본보다 1.4배를 넘겨 확대하지 않습니다. 작은 이미지를 억지로 늘리지 않기 위해서입니다.
5. 다운로드가 끝나면 `DerivePreviewJob` 이 그 파일로 미리보기를 다시 만듭니다. 네트워크를 두 번 쓰지 않습니다.

### 페이징

`GoogleSearch` 는 두 단계로 동작합니다.

- `mode='initial'` — 결과 페이지를 열고 0.75초 간격으로 추출을 시도합니다. 첫 결과가 나오면 `results` 를 내보내고 **페이지는 살려 둡니다**.
- `mode='more'` — `load_more()` 가 매 틱마다 `SCROLL_JS`(맨 아래로 스크롤 + “더보기” 클릭)를 실행한 뒤 다시 추출합니다. 새 URL만 `more_results` 로 보냅니다.
- `self.seen` 이 URL 중복을 걸러 냅니다. 새 결과가 없는 틱이 `IDLE_LIMIT`(5)회 이어지면 `exhausted` 로 표시하고 UI의 **더 불러오기** 를 숨깁니다.
- `generation` 카운터로 취소된 검색의 늦은 응답을 버리고, 페이지 URL의 `q` 파라미터로 다른 검색어의 결과를 걸러 냅니다.

창이 숨겨진 상태에서도 결과를 모을 수 있도록, 검색 시작 시 웹뷰를 1280×2400으로 키워 Google이 한 번에 더 많은 행을 배치하게 합니다.

### 지연 로딩

`Window.load_visible()` 이 스크롤 위치를 기준으로 위아래 여유분까지 포함한 범위의 카드만 `queue_image()` 로 넘깁니다. 스크롤 시 80ms 디바운스로 다시 계산합니다. 이미 디스크에 파일이 있는 카드는 지연 없이 바로 그립니다.

### 테마와 아이콘

`theme.py` 의 `DARK` / `LIGHT` 는 **같은 키 집합**을 가져야 합니다 (`tests/test_theme.py` 가 강제). 스타일시트는 `string.Template` 로 `$토큰` 을 치환합니다.

아이콘은 `Window.bind_icon()` 으로 등록해 두면 테마 전환 시 자동으로 새 색으로 다시 그려집니다. 카드는 테마 전환 때 통째로 다시 만들어지므로 별도 등록이 필요 없습니다.

## 테스트

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

| 파일 | 검증 대상 |
|---|---|
| `tests/test_store.py` | 영속성, upsert가 좋아요·파일 경로를 지우지 않음, 카테고리 검증, 검색 기록 상한 |
| `tests/test_network.py` | 원본 우선 미리보기, 썸네일 대체, 축소 규칙, 투명도, 파생 미리보기, 형식·스킴 거부 |
| `tests/test_search_paging.py` | 첫 페이지/추가 페이지 중복 제거, 종료 조건, 취소·다른 검색어 결과 무시 |
| `tests/test_theme.py` | 두 팔레트의 토큰 일치, 아이콘 번들 존재, 색·회전별 렌더링, DPR 보존 |
| `tests/test_ui.py` | 라이브러리 흐름, 테마 전환·영속, 추가 페이지 append, 지연 로딩 범위, 물리 해상도 렌더링 |
| `tests/test_download_flow.py` | 실제 HTTP 서버로 다운로드, 재실행 후 오프라인 표시, 종료 시 저장 마무리 |

네트워크 테스트는 `http.server` 로 띄운 로컬 픽스처만 사용합니다. 외부 인터넷에 의존하는 테스트는 없습니다.

## 검색 로직 수동 검증

```sh
.venv/bin/python scripts/verify_search.py       # 통제된 HTML에서 추출 결과 확인
.venv/bin/python scripts/verify_auto_search.py  # 자동 수집 흐름 확인
```

Google의 페이지 구조는 예고 없이 바뀝니다. 결과가 갑자기 비면 `search.py` 의 `EXTRACT_JS` 부터 확인하세요.

## 문서용 화면 캡처

```sh
.venv/bin/python scripts/capture_ui.py
```

임시 디렉터리에 합성 이미지를 만들어 캡처하므로 **개인 라이브러리를 절대 건드리지 않습니다**. `QT_SCALE_FACTOR=2` 로 2배 해상도로 저장합니다.

## 빌드

```sh
.venv/bin/python scripts/build.py
```

PyInstaller가 `dist/ImageSearch.app`(macOS)을 만듭니다. `assets/icons` 는 `--add-data` 로 번들에 포함되며, 런타임에서는 `icons.icon_dir()` 이 `sys._MEIPASS` 를 확인해 경로를 찾습니다.

GitHub Actions 워크플로 `release-macos.yml` 은 `v*` 태그를 올리면 macOS 러너에서 앱을 빌드해 zip으로 릴리스에 첨부합니다.

```sh
git tag v1.1.0 && git push origin v1.1.0
```

## 코드에 손댈 때

- 색상 하드코딩 금지 — `theme.py` 팔레트에 토큰을 추가하세요.
- 아이콘은 `assets/icons` 에 SVG를 넣고 `icons.icon(이름, 색)` 으로 씁니다. 새 아이콘은 `tests/test_theme.py` 의 사용 목록에도 추가하세요.
- 워커 스레드에서 `store` 를 만지지 마세요.
- 사용자에게 보여 줄 새 상태는 `set_status()` 로 전달합니다.
