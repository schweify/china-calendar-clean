#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from functools import lru_cache
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from lunar_python import Solar

ROOT = Path(__file__).resolve().parents[1]
STATUTORY_DIR = ROOT / "data" / "statutory"
DEFAULT_OUTPUT = ROOT / "dist" / "china-calendar.ics"
CAL_NAME = "中国日历·精简版"
PRODID = "-//schweify//China Calendar Clean//CN"

LUNAR_FESTIVALS = {
    (1, 1): "春节",
    (1, 15): "元宵节",
    (2, 2): "龙抬头",
    (5, 5): "端午节",
    (7, 7): "七夕节",
    (7, 15): "中元节",
    (8, 15): "中秋节",
    (9, 9): "重阳节",
    (12, 8): "腊八节",
}

@dataclass(frozen=True)
class Event:
    day: date
    summary: str
    category: str
    description: str
    source_key: str


def daterange(start: date, end_inclusive: date) -> Iterable[date]:
    d = start
    while d <= end_inclusive:
        yield d
        d += timedelta(days=1)


def parse_day(s: str) -> date:
    return date.fromisoformat(s)


def load_statutory() -> list[dict]:
    items = []
    for path in sorted(STATUTORY_DIR.glob("*.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        if obj.get("year") != int(path.stem):
            raise ValueError(f"year mismatch in {path}")
        items.append(obj)
    return items


def build_statutory_events(start_year: int, end_year: int) -> tuple[list[Event], dict[date, str]]:
    events: list[Event] = []
    holiday_names: dict[date, str] = {}
    for year_data in load_statutory():
        year = year_data["year"]
        if not (start_year <= year <= end_year):
            continue
        src = year_data["source"]
        source_text = f"{src['issuer']}《{src['document']}》；{src['url']}"
        for h in year_data["holidays"]:
            days = list(daterange(parse_day(h["start"]), parse_day(h["end"])))
            total = len(days)
            for idx, d in enumerate(days, 1):
                summary = f"{h['name']} 假期 第{idx}天/共{total}天"
                events.append(Event(d, summary, "法定节假日", source_text, f"statutory:{year}:{h['name']}:holiday:{idx}"))
                holiday_names[d] = h["name"]
            workdays = [parse_day(x) for x in h.get("workdays", [])]
            wtotal = len(workdays)
            for idx, d in enumerate(workdays, 1):
                summary = f"{h['name']} 补班 第{idx}天/共{wtotal}天"
                events.append(Event(d, summary, "补班", source_text, f"statutory:{year}:{h['name']}:workday:{idx}"))
    return events, holiday_names


@lru_cache(maxsize=8192)
def lunar_for_day(d: date):
    return Solar.fromYmd(d.year, d.month, d.day).getLunar()


def build_cultural_events(start_year: int, end_year: int, holiday_names: dict[date, str]) -> list[Event]:
    events: list[Event] = []
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    d = start
    while d <= end:
        lunar = lunar_for_day(d)
        lunar_month = lunar.getMonth()
        lunar_day = lunar.getDay()

        festival = None
        if lunar_month > 0:
            festival = LUNAR_FESTIVALS.get((lunar_month, lunar_day))

        next_day = d + timedelta(days=1)
        if next_day <= end + timedelta(days=1):
            next_lunar = lunar_for_day(next_day)
            if next_lunar.getMonth() == 1 and next_lunar.getDay() == 1:
                festival = "除夕"

        term = lunar.getJieQi()
        if term == "清明":
            # 清明兼具节气和传统节日属性；只显示一条，避免重复。
            festival = "清明节"
            term = ""

        if festival:
            official = holiday_names.get(d, "")
            if festival not in official:
                events.append(Event(
                    d,
                    festival,
                    "传统节日",
                    "农历日期由 lunar_python 1.4.8 换算；参考香港天文台公历与农历对照表。",
                    f"festival:{festival}:{d.isoformat()}",
                ))

        if term:
            events.append(Event(
                d,
                term,
                "二十四节气",
                "节气日期由 lunar_python 1.4.8 计算；参考香港天文台年历及公历与农历对照表。",
                f"solar-term:{term}:{d.isoformat()}",
            ))

        d += timedelta(days=1)
    return events


def ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_line(line: str, limit: int = 75) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= limit:
        return line
    parts: list[str] = []
    current = ""
    current_len = 0
    first = True
    for ch in line:
        b = ch.encode("utf-8")
        budget = limit if first else limit - 1
        if current and current_len + len(b) > budget:
            parts.append(current)
            current = ch
            current_len = len(b)
            first = False
        else:
            current += ch
            current_len += len(b)
    if current:
        parts.append(current)
    return "\r\n ".join(parts)


def event_uid(e: Event) -> str:
    h = hashlib.sha1(f"{e.day.isoformat()}|{e.source_key}".encode("utf-8")).hexdigest()[:20]
    return f"{h}@china-calendar-clean.schweify"


def render(events: list[Event]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CAL_NAME}",
        "X-WR-TIMEZONE:Asia/Shanghai",
        "X-WR-CALDESC:法定放假/补班（国务院通知）+传统节日+二十四节气；同类信息去重。",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]
    for e in sorted(events, key=lambda x: (x.day, x.category, x.summary)):
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event_uid(e)}",
            f"DTSTAMP:{e.day.strftime('%Y%m%d')}T000000Z",
            f"DTSTART;VALUE=DATE:{e.day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(e.day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{ics_escape(e.summary)}",
            f"CATEGORIES:{ics_escape(e.category)}",
            f"DESCRIPTION:{ics_escape(e.description)}",
            "TRANSP:TRANSPARENT",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_line(x) for x in lines) + "\r\n"


def validate(events: list[Event]) -> None:
    seen_uids = set()
    seen_keys = set()
    for e in events:
        uid = event_uid(e)
        if uid in seen_uids:
            raise ValueError(f"duplicate UID: {uid}")
        seen_uids.add(uid)
        key = (e.day, e.summary)
        if key in seen_keys:
            raise ValueError(f"duplicate visible event: {e.day} {e.summary}")
        seen_keys.add(key)
    if not any(e.category == "法定节假日" for e in events):
        raise ValueError("no statutory holiday events")
    if not any(e.category == "传统节日" for e in events):
        raise ValueError("no traditional festival events")
    if not any(e.category == "二十四节气" for e in events):
        raise ValueError("no solar-term events")


def build(start_year: int, end_year: int) -> list[Event]:
    statutory, holiday_names = build_statutory_events(start_year, end_year)
    cultural = build_cultural_events(start_year, end_year, holiday_names)
    events = statutory + cultural
    validate(events)
    return events


def main() -> None:
    current = datetime.now(timezone.utc).year
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=current - 1)
    ap.add_argument("--end-year", type=int, default=current + 9)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    if args.start_year > args.end_year:
        raise SystemExit("start year must be <= end year")
    events = build(args.start_year, args.end_year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = render(events)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        f.write(content)
    print(f"OUTPUT={args.output}")
    print(f"YEARS={args.start_year}-{args.end_year}")
    print(f"EVENTS={len(events)}")
    print(f"SHA256={hashlib.sha256(content.encode('utf-8')).hexdigest()}")

if __name__ == "__main__":
    main()
