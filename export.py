# /// script
# requires-python = ">=3.11"
# dependencies = ["duckdb", "pyyaml"]
# ///
"""두 봇의 기록을 읽어 대시보드용 JSON 하나로 내보낸다.

- 읽기만 한다. 봇 폴더에는 아무것도 쓰지 않는다.
- 종가베팅 기록 DB는 임시 폴더에 복사한 뒤 읽기 전용으로 연다.
- 이 JSON은 공개 웹페이지에 올라간다. 비밀 값·PC 경로·실행 로그 원문은 넣지 않는다.

실행: uv run export.py   (결과: docs/data/dashboard.json)
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DREAM = ROOT / "dreamroad-bot-claude"
CLOSING = ROOT / "closing-bet-bot"
OUT = HERE / "docs" / "data" / "dashboard.json"
KST = dt.timezone(dt.timedelta(hours=9))

_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'|)]*")


def scrub(v):
    """PC 절대 경로(사용자 이름이 들어 있다)를 지운다."""
    if isinstance(v, str):
        return _PATH_RE.sub("(경로)", v)
    if isinstance(v, list):
        return [scrub(x) for x in v]
    if isinstance(v, dict):
        return {k: scrub(x) for k, x in v.items()}
    return v


def jsonable(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, float) and v != v:  # NaN
        return None
    return v


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_jsonl(p: Path) -> list[dict]:
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def read_csv(p: Path) -> list[dict]:
    try:
        with p.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def num(s):
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def latest(folder: Path, pattern: str) -> Path | None:
    files = sorted(folder.glob(pattern))
    return files[-1] if files else None


def file_date(p: Path | None) -> str | None:
    if not p:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}", p.name)
    return m.group(0) if m else None


# ───────────────────────── 드림로드 ─────────────────────────

def parse_draft(p: Path) -> tuple[list[dict], dict[str, str]]:
    """초안 yaml + 각 종목 위에 달린 설명 주석(종목명 포함)을 함께 읽는다."""
    text = p.read_text(encoding="utf-8")
    names: dict[str, str] = {}
    notes: dict[str, list[str]] = {}
    buf: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            buf.append(s.lstrip("# ").rstrip())
            continue
        m = re.match(r'-\s*code:\s*"?([0-9A-Za-z]+)"?', s)
        if m:
            code = m.group(1)
            block = [b for b in buf if b and not b.startswith("─")]
            for b in block:
                nm = re.match(r"(.+?)\s+—\s", b)
                if nm:
                    names[code] = nm.group(1).strip()
                    break
            notes[code] = block
            buf = []
        elif s == "":
            buf = []
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        data = {}
    items = []
    for it in data.get("items") or []:
        code = str(it.get("code", ""))
        items.append({
            "code": code,
            "name": names.get(code, code),
            "adopt": bool(it.get("adopt")),
            "technique": it.get("technique"),
            "zone": it.get("zone"),
            "wave_high": it.get("wave_high"),
            "gap_pct": it.get("gap_pct"),
            "max_steps": it.get("max_steps"),
            "expire": str(it.get("expire") or ""),
            "notes": notes.get(code, [])[:8],
        })
    return items, names


def export_dreamroad() -> dict:
    d = DREAM / "data"
    names: dict[str, str] = {}

    # 종목명: 전진 검증 기록과 초안 주석에서 모은다 (시세 DB는 열지 않는다)
    trades = []
    for tech in ("중하단", "급등주"):
        for r in read_csv(d / "forward" / f"trades_{tech}.csv"):
            names[r["code"]] = r.get("name") or r["code"]
            trades.append({
                "code": r["code"], "name": r.get("name"), "technique": r.get("technique") or tech,
                "signal": r.get("signal"), "entry": r.get("entry"), "exit": r.get("exit") or None,
                "n_buys": num(r.get("n_buys")), "avg": num(r.get("avg")), "invested": num(r.get("invested")),
                "pnl": num(r.get("pnl")), "ret_pct": num(r.get("ret_pct")), "days": num(r.get("days")),
                "exit_reason": r.get("exit_reason") or None,
            })
    trades.sort(key=lambda t: (t["entry"] or "", t["code"]), reverse=True)

    draft_items, draft_date = [], None
    drafts = sorted((d / "watchlist_drafts").glob("draft_*.yaml"))
    for p in drafts:
        items, nm = parse_draft(p)
        names.update(nm)
        draft_items, draft_date = items, file_date(p)

    # 승인된 watchlist
    wl = {}
    try:
        wl = yaml.safe_load((d / "watchlist.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        pass
    watchlist = [{
        "code": str(it.get("code")), "name": names.get(str(it.get("code")), str(it.get("code"))),
        "technique": it.get("technique"), "grade": it.get("grade") or "", "theme": it.get("theme") or "",
        "zone": it.get("zone"), "wave_high": it.get("wave_high"),
        "max_steps": it.get("max_steps"), "gap_pct": it.get("gap_pct"), "expire": str(it.get("expire") or ""),
    } for it in (wl.get("items") or [])]

    # 모의 장부
    state = read_json(d / "paper" / "state.json", {}) or {}
    positions = []
    for p in state.get("positions") or []:
        if p.get("closed"):
            continue
        buys = [f for f in p.get("fills") or [] if f.get("side") == "buy"]
        sells = [f for f in p.get("fills") or [] if f.get("side") == "sell"]
        bq = sum(f["qty"] for f in buys)
        avg = sum(f["price"] * f["qty"] for f in buys) / bq if bq else None
        plan = p.get("plan") or {}
        positions.append({
            "code": p.get("code"), "name": names.get(p.get("code"), p.get("name") or p.get("code")),
            "technique": p.get("technique"), "qty": p.get("qty"), "avg": avg,
            "entry_date": p.get("entry_date"), "days_held": p.get("days_held"),
            "n_buys": p.get("n_buys"), "steps": plan.get("steps"),
            "plan_prices": plan.get("prices"), "plan_qty": plan.get("qty"),
            "sold_any": bool(sells),
        })
    paper = {
        "last_date": (state.get("meta") or {}).get("last_date"),
        "cash": state.get("cash"),
        "start_equity": wl.get("account_equity"),
        "equity_curve": [{"date": a, "equity": b} for a, b in state.get("equity_curve") or []],
        "positions": positions,
        "fills": [{**f, "name": names.get(f.get("code"), f.get("code"))}
                  for f in read_jsonl(d / "paper" / "fills.jsonl")][-50:][::-1],
    }

    # 일일 루틴
    last = read_json(d / "routine" / "last.json", {}) or {}
    routine = {
        "last": {
            "date": last.get("date"), "status": last.get("status"),
            "started": last.get("started"), "finished": last.get("finished"),
            "steps": [{"name": s.get("name"), "ok": s.get("ok"), "detail": (s.get("detail") or "").strip(),
                       "sec": s.get("sec")} for s in last.get("steps") or []],
        },
        "history": [{"date": h.get("date"), "status": h.get("status"), "note": h.get("note"),
                     "started": h.get("started"), "finished": h.get("finished")}
                    for h in read_jsonl(d / "routine" / "history.jsonl")][-30:],
        "running": (d / "routine" / "running.lock").exists(),
    }

    # 전진 검증 누적
    fwd_hist = []
    for h in read_jsonl(d / "forward" / "history.jsonl"):
        row = {"date": h.get("date")}
        for tech in ("DR", "중하단", "급등주"):
            t = h.get(tech) or {}
            row[tech] = {k: t.get(k) for k in ("n", "open", "wins", "win_rate", "mean_ret", "pnl", "profit_factor")}
        fwd_hist.append(row)

    sheet_p = latest(d / "sheets", "sheet_*.md")
    sheet = {"date": file_date(sheet_p), "markdown": sheet_p.read_text(encoding="utf-8") if sheet_p else ""}
    # 주문표는 종목 코드만 적혀 있다 → 화면에서 이름을 붙일 수 있게 이름표를 같이 보낸다

    return {
        "names": names, "routine": routine, "paper": paper, "watchlist": {"as_of": str(wl.get("as_of") or ""), "items": watchlist},
        "draft": {"date": draft_date, "items": draft_items}, "sheet": sheet,
        "forward": {"history": fwd_hist, "trades": trades},
    }


# ───────────────────────── 종가베팅 ─────────────────────────

def q(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    return [{c: jsonable(v) for c, v in zip(cols, row)} for row in cur.fetchall()]


def export_closing() -> dict:
    out: dict = {"available": False}
    src = CLOSING / "data" / "forward.duckdb"
    rep = CLOSING / "reports" / "forward_report.md"
    out["report_markdown"] = rep.read_text(encoding="utf-8") if rep.exists() else ""
    if not src.exists():
        return out
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "forward_copy.duckdb"
        shutil.copy2(src, copy)  # 원본은 열지 않는다
        con = duckdb.connect(str(copy), read_only=True)
        try:
            tables = {r[0] for r in con.execute("select table_name from information_schema.tables").fetchall()}

            def has(t):
                return t in tables

            out["runs"] = q(con, """
                select trade_date, job, started_at, finished_at, status, message
                from runs where trade_date >= (select max(trade_date) from runs) - interval 45 day
                order by trade_date desc, started_at desc""") if has("runs") else []
            out["gate"] = q(con, """
                select trade_date, phase, market, index_value, ma, ma_n, chg_pct, rising, fall,
                       trend, crash, breadth, state
                from gate where trade_date >= (select max(trade_date) from gate) - interval 30 day
                order by trade_date desc, phase, market""") if has("gate") else []
            out["screen"] = q(con, """
                select trade_date, phase, code, name, market, price, change_pct, trading_value,
                       from_high_pct, tv_ratio, passed, fail_reasons, cand_rank, gate_state,
                       is_signal, is_virtual
                from screen where trade_date >= (select max(trade_date) from screen) - interval 14 day
                order by trade_date desc, phase, trading_value desc""") if has("screen") else []
            out["outcomes"] = q(con, """
                select trade_date, code, name, signal_1500, virtual_1500, signal_close, virtual_close,
                       gate_1500, close_1535, exit_date, exit_open, days_held, exit_kind,
                       gross_ret_pct, net_ret_pct
                from outcomes order by trade_date desc, code""") if has("outcomes") else []
            out["materials"] = q(con, """
                select trade_date, code, name, is_signal, is_virtual, status, grade, theme, is_leader, reason
                from materials where trade_date >= (select max(trade_date) from materials) - interval 14 day
                order by trade_date desc, code""") if has("materials") else []
            out["available"] = True
        finally:
            con.close()
    return out


# ───────────────────────── 자동 커밋 기록 ─────────────────────────

def export_commit_log() -> list[dict]:
    p = ROOT / "logs" / "commit_daily.log"
    rows = []
    try:
        lines = p.read_text(encoding="utf-8-sig").splitlines()[-40:]
    except OSError:
        return rows
    for line in lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)", line)
        if m:
            rows.append({"at": m.group(1), "repo": m.group(2), "message": m.group(3)})
    return rows[::-1]


def main() -> int:
    data = {
        "generated_at": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "dreamroad": export_dreamroad(),
        "closing": export_closing(),
        "commit_log": export_commit_log(),
    }
    data = scrub(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, default=jsonable)
    # 내용이 그대로면 파일을 다시 쓰지 않는다 (생성 시각만 바뀐 커밋을 만들지 않으려고)
    old = read_json(OUT)
    if old is not None:
        a = {k: v for k, v in old.items() if k != "generated_at"}
        b = {k: v for k, v in json.loads(text).items() if k != "generated_at"}
        if a == b:
            print("바뀐 내용 없음")
            return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"내보냄: {OUT.relative_to(HERE)} ({len(text.encode('utf-8')):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
