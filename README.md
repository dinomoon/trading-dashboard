# 매매봇 대시보드

두 매매봇(드림로드, 종가베팅)의 기록을 한 화면에서 보는 정적 웹페이지.

- `export.py` — 두 봇 폴더의 기록을 읽어 `docs/data/dashboard.json` 하나로 내보낸다. 읽기만 한다.
- `docs/` — 웹페이지. GitHub Pages가 `main` 브랜치의 이 폴더를 그대로 배포한다 (푸시하면 자동 반영).
- 매일 밤 예약 작업이 `uv run export.py`를 돌린 뒤 커밋·푸시한다.

모의 기록이며 실제 주문은 하지 않는다. 이 저장소는 공개이므로 비밀 값·계좌 정보·PC 경로는 넣지 않는다.

## 직접 돌리기
```
uv run export.py
uv run --no-project python -m http.server 8765 --directory docs
```
