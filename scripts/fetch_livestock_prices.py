#!/usr/bin/env python3
"""Create a Kaohsiung livestock snapshot from official Taiwan price sources."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_URL = "https://data.moa.gov.tw/Service/OpenData/FromM/AnimalTransData.aspx?IsTransData=1&UnitId=026"
SOURCE_PAGE = "https://data.gov.tw/dataset/7296"
POULTRY_SOURCE_URL = "https://data.moa.gov.tw/Service/OpenData/FromM/PoultryTransBoiledChickenData.aspx?IsTransData=1&UnitId=056"
POULTRY_SOURCE_PAGE = "https://data.gov.tw/dataset/7536"
LIVESTOCK_MARKET_SOURCE_URL = "https://ppg.naif.org.tw/naif/marketinformation/reference/reference.aspx"
LIVESTOCK_MARKET_SOURCE_PAGE = LIVESTOCK_MARKET_SOURCE_URL
KAOHSIUNG_MARKETS = ("高雄市", "高雄鳳山", "高雄岡山", "高雄旗山")
TAIPEI_TZ = timezone(timedelta(hours=8))


def parse_source_date(value: object) -> tuple[date, str] | None:
    """Parse the source's ROC date (for example 1150928)."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    try:
        if len(digits) == 7:
            year = int(digits[:3]) + 1911
            month, day = int(digits[3:5]), int(digits[5:7])
            parsed = date(year, month, day)
            return parsed, f"{digits[:3]}.{digits[3:5]}.{digits[5:7]}"
        if len(digits) == 8:
            parsed = date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
            roc = parsed.year - 1911
            return parsed, f"{roc:03d}.{parsed.month:02d}.{parsed.day:02d}"
    except ValueError:
        return None
    return None


def load_rows(source_file: Path | None, source_url: str) -> list[dict[str, object]]:
    if source_file:
        return json.loads(source_file.read_text(encoding="utf-8-sig"))
    request = Request(source_url, headers={"User-Agent": "KaohsiungPriceLookup/1.0"})
    with urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def latest_chicken_reference(rows: list[dict[str, object]], today: date) -> dict[str, object] | None:
    earliest = today - timedelta(days=14)
    latest: tuple[date, dict[str, object]] | None = None
    for row in rows:
        try:
            trade_date = datetime.strptime(str(row.get("日期") or ""), "%Y/%m/%d").date()
            price = float(row.get("白肉雞(門市價高屏)") or 0)
        except (TypeError, ValueError):
            continue
        if trade_date < earliest or trade_date > today or price <= 0:
            continue
        if latest and latest[0] >= trade_date:
            continue
        latest = (trade_date, {
            "date": trade_date.isoformat(),
            "market_label": "門市價（高屏）",
            "name": "白肉雞",
            "price_per_catty": round(price, 2),
            "price_per_kg": round(price / 0.6, 2),
        })
    return latest[1] if latest else None


class SnapshotTableParser(HTMLParser):
    """Read the two livestock tables from the NAIF market information page."""

    target_ids = {
        "ContentPlaceHolder_main_GridView_cattle",
        "ContentPlaceHolder_main_GridView_sheep_new",
    }

    def __init__(self) -> None:
        super().__init__()
        self.table_depth = 0
        self.target_id: str | None = None
        self.target_depth: int | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.tables: dict[str, list[list[str]]] = {table_id: [] for table_id in self.target_ids}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            self.table_depth += 1
            table_id = attributes.get("id")
            if table_id in self.target_ids:
                self.target_id = table_id
                self.target_depth = self.table_depth
            return
        if self.target_id is None or self.table_depth != self.target_depth:
            return
        if tag == "tr":
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.target_id is not None and self.table_depth == self.target_depth:
            if tag in ("th", "td") and self.row is not None and self.cell is not None:
                self.row.append(" ".join("".join(self.cell).split()))
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.tables[self.target_id].append(self.row)
                self.row = None
                self.cell = None
            elif tag == "table":
                self.target_id = None
                self.target_depth = None
                self.row = None
                self.cell = None
        if tag == "table":
            self.table_depth = max(0, self.table_depth - 1)


def parse_market_source(html: str, today: date) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    parser = SnapshotTableParser()
    parser.feed(html)

    cattle_records: list[dict[str, object]] = []
    for row in parser.tables["ContentPlaceHolder_main_GridView_cattle"]:
        if len(row) < 3 or row[0] == "週數":
            continue
        try:
            trade_date = datetime.strptime(row[0], "%Y/%m/%d").date()
            price = float(row[2].replace(",", ""))
        except (TypeError, ValueError):
            continue
        if trade_date < today - timedelta(days=60) or trade_date > today or price <= 0:
            continue
        cattle_records.append({
            "date": trade_date.isoformat(),
            "name": row[1],
            "price": price,
            "unit": "元／頭" if "(隻)" in row[1] or "(頭/元)" in row[1] else "元／公斤",
        })
    if cattle_records:
        latest_cattle_date = max(str(record["date"]) for record in cattle_records)
        cattle_records = [record for record in cattle_records if record["date"] == latest_cattle_date]

    sheep_date_match = re.search(
        r'<input\b(?=[^>]*id="ContentPlaceHolder_main_TextBox_sheep_new")(?=[^>]*value="(\d{4}-\d{2}-\d{2})")[^>]*>',
        html,
        re.IGNORECASE,
    )
    try:
        reference_date = date.fromisoformat(sheep_date_match.group(1)) if sheep_date_match else today
    except ValueError:
        reference_date = today

    sheep_rows: list[dict[str, object]] = []
    for row in parser.tables["ContentPlaceHolder_main_GridView_sheep_new"]:
        if len(row) < 5 or not re.fullmatch(r"\d{1,2}/\d{1,2}", row[0]):
            continue
        try:
            month, day = (int(part) for part in row[0].split("/"))
            trade_date = date(reference_date.year, month, day)
            if trade_date > reference_date:
                trade_date = date(reference_date.year - 1, month, day)
            head_count = int(float(row[3].replace(",", "")))
            price = float(row[4].replace(",", ""))
        except (TypeError, ValueError):
            continue
        if trade_date < reference_date - timedelta(days=30) or trade_date > reference_date or price <= 0:
            continue
        sheep_rows.append({
            "date": trade_date.isoformat(),
            "market": row[1],
            "name": row[2],
            "head_count": head_count,
            "price_per_kg": round(price, 2),
        })
    latest_sheep_date_by_market: dict[str, str] = {}
    for record in sheep_rows:
        market = str(record["market"])
        latest_sheep_date_by_market[market] = max(latest_sheep_date_by_market.get(market, ""), str(record["date"]))
    sheep_records = [
        record for record in sheep_rows
        if record["date"] == latest_sheep_date_by_market[str(record["market"])]
    ]
    return cattle_records, sheep_records


def load_text(source_url: str) -> str:
    request = Request(source_url, headers={"User-Agent": "KaohsiungPriceLookup/1.0"})
    with urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8-sig")


def create_snapshot(
    rows: list[dict[str, object]],
    poultry_rows: list[dict[str, object]],
    market_html: str = "",
) -> dict[str, object]:
    now = datetime.now(TAIPEI_TZ)
    earliest = now.date() - timedelta(days=14)
    latest_by_market: dict[str, tuple[date, dict[str, object]]] = {}

    for row in rows:
        market = str(row.get("市場名稱") or "").strip()
        if market not in KAOHSIUNG_MARKETS:
            continue
        parsed = parse_source_date(row.get("交易日期"))
        if not parsed:
            continue
        trade_date, roc_date = parsed
        if trade_date < earliest or trade_date > now.date():
            continue
        head_count = int(float(row.get("規格豬-頭數") or 0))
        average_price = float(row.get("規格豬-平均價格") or 0)
        average_weight = float(row.get("規格豬-平均重量") or 0)
        if head_count <= 0 or average_price <= 0:
            continue
        existing = latest_by_market.get(market)
        if existing and existing[0] >= trade_date:
            continue
        latest_by_market[market] = (trade_date, {
            "trade_date": trade_date.isoformat(),
            "trade_date_roc": roc_date,
            "market": market,
            "standard_pig_count": head_count,
            "standard_pig_avg_weight_kg": round(average_weight, 2),
            "standard_pig_avg_price_per_kg": round(average_price, 2),
        })

    records = [latest_by_market[market][1] for market in KAOHSIUNG_MARKETS if market in latest_by_market]
    if not records:
        raise ValueError("No recent Kaohsiung hog market records were found; refusing to write an empty snapshot.")
    chicken = latest_chicken_reference(poultry_rows, now.date())
    cattle_records, sheep_records = parse_market_source(market_html, now.date()) if market_html else ([], [])

    return {
        "schema_version": 2,
        "collected_at": now.isoformat(timespec="minutes"),
        "source": {
            "name": "農業部毛豬交易行情",
            "url": SOURCE_PAGE,
            "api": SOURCE_URL,
            "note": "每日肉品市場毛豬拍賣交易資料；規格豬平均成交價，非分切肉零售價。",
        },
        "poultry_source": {
            "name": "農業部家禽交易行情（白肉雞／雞蛋）",
            "url": POULTRY_SOURCE_PAGE,
            "api": POULTRY_SOURCE_URL,
            "note": "每日白肉雞高屏門市價，元／台斤；不是單一市場攤商報價。",
        },
        "cattle_sheep_source": {
            "name": "中央畜產會畜產行情資訊網",
            "url": LIVESTOCK_MARKET_SOURCE_PAGE,
            "page": LIVESTOCK_MARKET_SOURCE_URL,
            "note": "牛隻為每週活體產地均價；羊隻為彰化、雲林拍賣市場交易價，按官方交易日更新。兩者均非分切肉零售價。",
        },
        "records": records,
        "poultry_reference": chicken,
        "cattle_records": cattle_records,
        "sheep_records": sheep_records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/livestock-prices.json", type=Path)
    parser.add_argument("--input", type=Path, help="Read a saved source JSON file instead of downloading it.")
    parser.add_argument("--poultry-input", type=Path, help="Read a saved poultry source JSON file instead of downloading it.")
    parser.add_argument("--market-html-input", type=Path, help="Read a saved NAIF market page instead of downloading it.")
    args = parser.parse_args()

    hog_rows = load_rows(args.input, SOURCE_URL)
    try:
        poultry_rows = load_rows(args.poultry_input, POULTRY_SOURCE_URL)
    except Exception as error:
        print(f"Warning: poultry reference prices are temporarily unavailable: {error}")
        poultry_rows = []
    try:
        market_html = args.market_html_input.read_text(encoding="utf-8-sig") if args.market_html_input else load_text(LIVESTOCK_MARKET_SOURCE_URL)
    except Exception as error:
        print(f"Warning: cattle and sheep reference prices are temporarily unavailable: {error}")
        market_html = ""
    snapshot = create_snapshot(hog_rows, poultry_rows, market_html)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Saved {len(snapshot['records'])} Kaohsiung pig market prices, "
        f"{len(snapshot['cattle_records'])} cattle references, and "
        f"{len(snapshot['sheep_records'])} sheep auction prices to {args.output}."
    )


if __name__ == "__main__":
    main()
