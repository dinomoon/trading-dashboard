# dashboard

두 봇의 기록을 보여 주는 정적 대시보드. GitHub Pages로 공개 배포된다 (`dinomoon/trading-dashboard`, `main`의 `docs/`).

## 절대 규칙
- 이 저장소는 **공개**다. 비밀 값, 계좌번호, PC 절대 경로, 실행 로그 원문을 넣지 않는다. `export.py`의 `scrub`을 거치지 않은 문자열을 내보내지 않는다.
- 두 봇 폴더는 **읽기만** 한다. 봇의 코드·설정·기록을 여기서 고치지 않는다.
- 종가베팅 `forward.duckdb`는 임시 복사본을 읽기 전용으로 연다. 드림로드 시세 DB는 열지 않는다.
- 성적·판정 숫자를 여기서 새로 계산해 "합격/미달"을 말하지 않는다. 판정은 각 봇의 리포트 원문을 그대로 보여 준다.

## 구조
- `export.py` — `uv run export.py` (의존성은 파일 머리의 인라인 메타데이터). 결과 `docs/data/dashboard.json`. 내용이 같으면 다시 쓰지 않는다.
- `docs/index.html` — 화면 전부 (빌드 없음, 외부 라이브러리 없음).
- 갱신: `../scripts/commit_daily.ps1`이 매일 23:30에 내보내기 → 커밋 → 푸시.
