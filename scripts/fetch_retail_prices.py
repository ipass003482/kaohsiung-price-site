#!/usr/bin/env python3
"""Build a small snapshot from public retailer product pages for GitHub Pages."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}
PX_BASE = "https://shop.pxgo.com.tw"
CARREFOUR_BASE = "https://online.carrefour.com.tw"
PRODUCE_QUERIES = [
    "菜", "青菜", "蔬菜", "水果", "青蔥", "小黃瓜", "番茄", "玉米筍",
    "洋蔥", "紅蘿蔔", "萵苣", "香蕉", "鳳梨", "芭樂", "木瓜", "芒果",
    "大白菜", "白蘿蔔", "冬瓜", "南瓜", "苦瓜", "茄子", "芹菜", "韭菜",
    "四季豆", "馬鈴薯", "地瓜", "地瓜葉", "芋頭", "大蒜", "薑", "青椒",
    "甜椒", "豆芽菜", "茭白筍", "小番茄", "葡萄", "草莓", "水梨", "酪梨",
    "火龍果", "百香果", "柚子", "蓮霧", "龍眼", "荔枝", "水蜜桃",
]
MUSHROOM_QUERIES = ["杏鮑菇", "香菇", "金針菇", "菇類"]
MEAT_SEARCH_QUERIES = [
    "豬肉", "豬五花", "豬梅花", "豬里肌", "牛肉", "牛五花", "牛小排",
    "雞肉", "雞胸", "雞腿", "羊肉", "羊排", "鴨肉", "鴨胸",
]
PX_QUERIES = PRODUCE_QUERIES + MUSHROOM_QUERIES + MEAT_SEARCH_QUERIES
CARREFOUR_QUERIES = list(dict.fromkeys(PRODUCE_QUERIES + MUSHROOM_QUERIES + MEAT_SEARCH_QUERIES))

MEAT_ITEMS = [
    ("豬五花", "meat", ("豬五花", "五花豬", "五花肉")),
    ("豬梅花", "meat", ("豬梅花", "梅花豬")),
    ("豬里肌", "meat", ("豬里肌", "里肌豬", "黑豬里肌")),
    ("豬排骨", "meat", ("豬小排", "豬肋排", "豬排骨")),
    ("豬絞肉", "meat", ("豬絞肉",)),
    ("豬肉片", "meat", ("豬肉片", "豬肉火鍋肉片", "豬肉絲")),
    ("豬軟骨", "meat", ("豬軟骨",)),
    ("豬肉", "meat", ("豬肉", "豬腱", "黑豬")),
    ("牛五花", "meat", ("牛五花", "牛五花肉")),
    ("牛小排", "meat", ("牛小排", "帶骨牛排")),
    ("牛腱", "meat", ("牛腱",)),
    ("牛肋條", "meat", ("牛肋條", "牛肋")),
    ("牛腩", "meat", ("牛腩",)),
    ("牛絞肉", "meat", ("牛絞肉",)),
    ("牛肉片", "meat", ("牛肉片", "牛肉火鍋片", "牛肉絲", "牛肉雙拼", "牛肉炒片", "牛梅花火鍋肉片", "牛梅花火鍋片", "牛肩里肌炒肉片", "牛肩里肌炒肉絲", "牛肩里肌火鍋肉片", "牛胸腹雪花火鍋肉片")),
    ("牛排", "meat", ("牛排", "板腱牛", "安格斯牛", "肩胛牛", "翼板牛", "嫩肩牛", "嫩肩骰子牛", "骰子牛")),
    ("牛肉其他", "meat", ("牛肉", "澳洲穀飼牛", "美國牛", "澳洲牛")),
    ("雞絞肉", "meat", ("雞絞肉", "雞腿絞肉", "雞胸絞肉")),
    ("雞胸", "meat", ("雞胸",)),
    ("雞腿", "meat", ("雞腿", "雞腿排", "雞骨腿", "雞翅小腿")),
    ("雞翅", "meat", ("雞翅", "三節翅", "蝴蝶翅", "翅腿")),
    ("雞里肌", "meat", ("雞里肌",)),
    ("雞腱雞胗", "meat", ("雞腱", "雞胗")),
    ("全雞", "meat", ("全雞", "雞全隻", "土雞全隻")),
    ("雞肉塊", "meat", ("雞肉塊", "雞腿切塊", "雞骨腿切塊")),
    ("雞肉其他", "meat", ("雞肉", "土雞", "仿土雞")),
    ("羊排", "meat", ("羊排", "羊肩排", "羊肋排")),
    ("羊肉片", "meat", ("羊肉片", "羊肉炒片", "羊炒片", "羊肉火鍋片")),
    ("羊肉塊", "meat", ("羊肉塊", "羊腿肉塊")),
    ("羊肉其他", "meat", ("羊肉", "羊肩", "羊腿")),
    ("鴨胸", "meat", ("鴨胸", "鴨菲力")),
    ("鴨腿", "meat", ("鴨腿", "鴨骨腿")),
    ("鴨肝", "meat", ("鴨肝",)),
    ("鴨肉片", "meat", ("鴨肉片", "鴨肉絲")),
    ("鴨肉塊", "meat", ("鴨肉塊",)),
    ("鴨肉其他", "meat", ("鴨肉", "櫻桃鴨", "番鴨")),
]
MEAT_EXCLUDED_TITLE_PARTS = (
    "水餃", "餃子", "包子", "湯包", "湯餃", "燒賣", "香腸", "熱狗", "火腿", "培根", "肉鬆", "肉乾",
    "肉丸", "貢丸", "雞塊", "雞米花", "炸雞", "鹹酥雞", "熟食", "即食", "調理", "料理包", "料理所",
    "滷味", "滷肉", "肉燥", "冷凍調理", "火鍋料", "火鍋湯", "鍋底", "湯底", "微波", "三明治", "漢堡", "排骨酥",
    "牛肉麵", "羊肉爐", "雞湯", "肉湯", "鴨肉羹", "肉羹", "肉餅", "肉泥", "肉條", "肉角", "肉醬",
    "餅乾", "炒烏龍", "蔥燒", "冬粉", "冬菜", "泡麵", "即食麵", "雞肉飯", "飯料", "粥", "碗裝", "杯麵", "貢丸", "摃丸",
    "牛肉煲", "雞腿煲", "紅燒", "滷", "料理", "罐頭", "易開罐", "罐", "湯汁", "高湯", "雞精", "鹹水雞", "煙燻", "鹹豬肉", "香辣", "高梁酒",
    "碗", "炭烤", "吮指", "薑燒", "薑母鴨", "沙拉", "洋蔥圈", "雞肉捲", "甘藷棒",
    "餡餅", "拉餅", "餅皮", "炸", "燜", "燉", "乾薑", "薑絲丸", "薑茶", "黑糖", "花月嵐", "燒烤", "肥腸", "熟品",
    "鹽麴", "蒜味", "蒜香", "香蒜", "香草", "迷迭香", "花椒", "孜然", "照燒", "醬燒", "蜜汁", "十三香", "黑胡椒", "紅藜", "醃漬", "寵物", "狗食", "犬食", "貓食", "寶路", "西莎", "葛莉思", "雅方", "滿漢大餐", "來一客",
    "肉品寵物", "雞肉包", "肉乾", "口味", "風味", "咖哩", "貓", "狗", "喵", "餐包", "餐盒", "便當", "營養食", "脆腸", "卡啦", "脆皮", "三杯", "炸雞", "剝皮辣椒", "石二鍋", "肉鍋", "肉羹鍋", "舒肥", "手撕熟", "油雞", "醉雞", "熟土雞", "麻辣", "輕食", "酥嫩", "香嫩", "重組",
    "味味一品", "酸菜鴨肉", "鴨肉杯", "鴨肉冬粉", "串燒", "肉串", "義大利麵",
)

CANONICAL_ITEMS = [
    ("高麗菜", "vegetable", ("高麗菜", "甘藍")),
    ("大白菜", "vegetable", ("大白菜", "包心白菜", "結球白菜", "山東白菜")),
    ("小白菜", "vegetable", ("小白菜",)),
    ("青江菜", "vegetable", ("青江菜", "青江白菜")),
    ("青蔥", "vegetable", ("青蔥", "青葱")),
    ("小黃瓜", "vegetable", ("小黃瓜", "胡瓜", "花胡瓜")),
    ("小番茄", "fruit", ("小番茄", "聖女番茄", "玉女番茄")),
    ("番茄", "vegetable", ("番茄", "蕃茄")),
    ("玉米筍", "vegetable", ("玉米筍",)),
    ("洋蔥", "vegetable", ("洋蔥",)),
    ("紅蘿蔔", "vegetable", ("紅蘿蔔", "胡蘿蔔")),
    ("白蘿蔔", "vegetable", ("白蘿蔔", "蘿蔔")),
    ("萵苣", "vegetable", ("萵苣", "A菜", "生菜")),
    ("菠菜", "vegetable", ("菠菜",)),
    ("空心菜", "vegetable", ("空心菜",)),
    ("青花菜", "vegetable", ("青花菜", "花椰菜")),
    ("絲瓜", "vegetable", ("絲瓜",)),
    ("冬瓜", "vegetable", ("冬瓜",)),
    ("南瓜", "vegetable", ("南瓜",)),
    ("苦瓜", "vegetable", ("苦瓜",)),
    ("茄子", "vegetable", ("茄子",)),
    ("芹菜", "vegetable", ("芹菜",)),
    ("韭菜", "vegetable", ("韭菜",)),
    ("四季豆", "vegetable", ("四季豆", "敏豆", "菜豆")),
    ("地瓜葉", "vegetable", ("地瓜葉", "甘藷葉")),
    ("馬鈴薯", "vegetable", ("馬鈴薯",)),
    ("地瓜", "vegetable", ("地瓜", "甘藷")),
    ("芋頭", "vegetable", ("芋頭",)),
    ("大蒜", "vegetable", ("大蒜", "蒜頭")),
    ("薑", "vegetable", ("薑", "生薑")),
    ("青椒", "vegetable", ("青椒",)),
    ("甜椒", "vegetable", ("甜椒", "彩椒")),
    ("豆芽菜", "vegetable", ("豆芽菜", "豆芽")),
    ("茭白筍", "vegetable", ("茭白筍",)),
    ("香蕉", "fruit", ("香蕉",)),
    ("鳳梨", "fruit", ("鳳梨",)),
    ("芭樂", "fruit", ("芭樂", "番石榴")),
    ("木瓜", "fruit", ("木瓜",)),
    ("芒果", "fruit", ("芒果",)),
    ("西瓜", "fruit", ("西瓜",)),
    ("檸檬", "fruit", ("檸檬",)),
    ("柳橙", "fruit", ("柳橙",)),
    ("蘋果", "fruit", ("蘋果",)),
    ("奇異果", "fruit", ("奇異果", "奇異果")),
    ("葡萄", "fruit", ("葡萄",)),
    ("草莓", "fruit", ("草莓",)),
    ("水梨", "fruit", ("水梨", "梨子", "新興梨", "豐水梨")),
    ("酪梨", "fruit", ("酪梨",)),
    ("火龍果", "fruit", ("火龍果",)),
    ("百香果", "fruit", ("百香果",)),
    ("柚子", "fruit", ("柚子", "文旦")),
    ("蓮霧", "fruit", ("蓮霧",)),
    ("龍眼", "fruit", ("龍眼",)),
    ("荔枝", "fruit", ("荔枝",)),
    ("水蜜桃", "fruit", ("水蜜桃", "桃子")),
    ("香菇", "vegetable", ("香菇",)),
    ("金針菇", "vegetable", ("金針菇",)),
    ("杏鮑菇", "vegetable", ("杏鮑菇",)),
]
EXCLUDED_TITLE_PARTS = (
    "水餃", "餃子", "抓餅", "蔥抓", "餅乾", "蘇打", "米果", "脆片", "麵包",
    "蛋糕", "派", "醬", "泡菜", "湯", "湯底", "底料", "火鍋", "鍋底",
    "飲料", "飲品", "果汁", "果昔", "牛奶", "牛乳", "調味乳", "乳飲", "奶昔",
    "果凍", "蒟蒻", "軟糖", "糖果", "洋芋", "薯片", "薯條", "口味", "風味",
    "洗髮", "護髮", "衛生棉", "護墊", "冷凍", "沙拉醬", "堅果", "零食", "炒飯", "炒麵", "麵",
    "調味", "醬料", "罐頭", "番茄罐", "蕃茄罐", "水果罐", "肉", "香腸", "果乾", "蜜餞", "脫水", "水果盤",
    "咖哩", "起司", "優酪", "乳酪", "冰品", "冰淇淋", "冰棒", "棒冰", "雪糕",
    "冬瓜茶", "南瓜子", "葡萄乾", "葡萄酒", "龍眼乾", "龍眼蜜", "花蜜", "柚子茶", "芋頭酥", "芋頭餅", "芋頭片", "芋泥", "地瓜球",
    "種子", "種籽", "盆栽", "菜苗", "果苗", "浮排", "泳圈", "充氣", "水上", "皮革", "卡包", "零錢包",
    "香水", "香薰", "精油", "沐浴乳", "薄切", "餐包", "吐司", "貝果", "餡餅", "餅皮", "餅", "餃", "饅頭", "雪酪", "雪花餅", "冰沙", "泡泡冰", "寒天", "QQ",
    "氣泡水", "優格", "沙拉", "多果實", "大蒜條", "花生米", "蘿蔔絲", "蟹殼黃", "炸", "薑茶", "黑糖", "喉糖",
    "百琪", "香蕉棒", "紅茶", "茶", "花月嵐", "椒香水蘿蔔", "好運蓮蓮", "調理", "地瓜片", "花生", "美乃滋", "膠囊", "蒜精", "大蒜鹽",
    "荔枝蜜", "蜜蜂工坊", "檸檬酸酸李", "蔭冬瓜", "波蜜", "椰果", "蘇菲", "維德卡", "Alcurnia", "奶油", "糖果",
    "凍乾", "烤地瓜", "冰烤", "罐", "切片", "蘿蔔乾", "罐裝", "醃漬", "半雞", "烤雞", "熟雞", "米粉", "手工製作", "小銅鍋", "食譜", "乾酪", "豆乾",
    "蜂蜜", "果醋", "醋飲", "酵素", "濃縮", "料理包", "即食", "冷飲", "汽水",
    "打拋", "豬", "魚", "冬粉", "去皮", "固形", "燴飯", "料理塊", "蔬菜汁",
    "番茄汁", "蕃茄汁", "芭樂汁", "綜合飲", "汁", "飲", "易開罐", "一般蓋", "柳葉魚", "口味", "風味",
    "果茶", "烏龍", "綠茶", "茶道", "茶園", "茶飲", "冰鎮", "芭樂乾", "甘草芭樂",
    "梅粉", "優格飲", "果飲", "鳳梨酥", "台鳳", "台糖鳳梨", "蔭鳳梨", "剝皮辣椒",
    "芒果青", "芒果棒", "洋蔥圈", "洋蔥薄燒", "青蔥燒", "青蔥餅", "蕎麥", "螺旋藻",
    "脆條", "晴雨傘", "百奇", "pocky", "鹽酥", "椒鹽", "三杯", "油飯", "蘿蔔糕", "五辛素", "貢丸", "摃丸",
    "蠔油", "味精", "豆豉", "乾香菇", "香菇乾", "快煮", "脆餅", "薯餅", "酸奶味",
)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).replace("\u3000", " ").strip()


def identify_item(title: str) -> tuple[str, str] | None:
    normalized = normalize_text(title)
    normalized_lower = normalized.lower()
    for canonical, category, aliases in MEAT_ITEMS:
        if any(alias in normalized for alias in aliases):
            if any(part.lower() in normalized_lower for part in MEAT_EXCLUDED_TITLE_PARTS):
                return None
            return canonical, category
    if any(part.lower() in normalized_lower for part in EXCLUDED_TITLE_PARTS):
        return None
    for canonical, category, aliases in CANONICAL_ITEMS:
        if any(alias in normalized for alias in aliases):
            return canonical, category
    return None


def parse_price(value: str) -> float | None:
    cleaned = re.sub(r"[^0-9.]", "", normalize_text(value))
    if not cleaned:
        return None
    try:
        price = Decimal(cleaned)
    except InvalidOperation:
        return None
    return float(price) if price > 0 else None


def parse_package_weight_g(title: str) -> float | None:
    text = normalize_text(title)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(公斤|公克|克|kg|g)(?![A-Za-z])", text, re.IGNORECASE)
    if not match:
        return None

    # A per-piece range is not enough to infer the total package weight.
    tail = text[match.end():]
    if re.match(r"\s*[-~～]\s*\d", tail):
        return None
    prefix = text[:match.start()]
    tail_after_weight = text[match.end():]
    is_per_piece = bool(re.search(r"每(?:粒|顆|個)\s*(?:約)?[^()]{0,20}$", prefix))
    count_pattern = r"\s*(?:±\s*\d+(?:\.\d+)?%\s*)?(?:x|×|\*|/)\s*(\d+)\s*(?:粒|入|個|包)?"
    multiplier = re.match(
        count_pattern,
        tail_after_weight,
        re.IGNORECASE,
    )
    if is_per_piece and not multiplier:
        return None

    amount = float(match.group(1))
    unit = match.group(2).lower()
    grams = amount * 1000 if unit in {"公斤", "kg"} else amount
    # A per-piece weight can use "90g/6入". A stated total box weight such as
    # "3kg/22粒" must stay 3kg; only explicit x/×/* pack notation multiplies it.
    pack_multiplier = multiplier if is_per_piece else re.match(
        r"\s*(?:±\s*\d+(?:\.\d+)?%\s*)?(?:x|×|\*)\s*(\d+)\s*(?:粒|入|個|包)?",
        tail_after_weight,
        re.IGNORECASE,
    )
    if pack_multiplier:
        grams *= int(pack_multiplier.group(1))
    else:
        # A title such as "3包(.../400g/包)" states the weight per pack.
        count_before_title = re.search(r"(?:^|[^\d])(\d+)\s*(?:包|盒|袋)\s*\(", prefix)
        weight_is_per_pack = bool(re.match(r"\s*(?:±\s*\d+(?:\.\d+)?%\s*)?/\s*(?:包|盒|袋)", tail_after_weight))
        if count_before_title and weight_is_per_pack:
            grams *= int(count_before_title.group(1))
    return grams if grams > 0 else None


def parse_price_per_kg(title: str, price: float, weight_g: float | None) -> float | None:
    # Some variable-weight meat is sold at a stated per-100g rate. That rate is
    # the comparable unit price; the product-card price is only an estimate.
    unit_price = re.search(r"每\s*100\s*(?:g|克)\s*(?:約\s*)?(\d+(?:\.\d+)?)\s*元", normalize_text(title), re.IGNORECASE)
    if unit_price:
        return float(unit_price.group(1)) * 10
    return price * 1000 / weight_g if weight_g else None


def now_taipei() -> str:
    # Taiwan uses UTC+08:00 year-round; a fixed offset avoids a tzdata dependency on Windows.
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="minutes")


def fetch_html(url: str) -> str:
    request = Request(url, headers=REQUEST_HEADERS)
    context = None
    if url.startswith(PX_BASE):
        # PXGo's current certificate chain omits an optional Subject Key Identifier.
        # Keep normal certificate and hostname verification, but allow OpenSSL's
        # non-strict chain mode for this host (Windows SChannel accepts the same chain).
        context = ssl.create_default_context()
        strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
        if strict_flag:
            context.verify_flags &= ~strict_flag
    with urlopen(request, timeout=30, context=context) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


class PxCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.card_depth: int | None = None
        self.card: dict[str, Any] | None = None
        self.capture: str | None = None
        self.capture_tag: str | None = None
        self.active_product_url: str | None = None
        self.items: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        href = values.get("href") or ""
        if tag == "a" and "/hourArrive/goods/" in href:
            self.active_product_url = urljoin(PX_BASE, href)

        if self.card_depth is None:
            if tag == "div" and {"flex", "flex-col", "rounded-b-md", "p-2", "relative"}.issubset(classes):
                self.card_depth = 1
                self.card = {"name": [], "price": [], "text": [], "url": self.active_product_url or ""}
            return

        if tag not in VOID_TAGS:
            self.card_depth += 1
        if tag == "span" and "text-lg" in classes:
            self.capture = "price"
            self.capture_tag = "span"
        elif tag == "div" and any(class_name.startswith("line-clamp-2") for class_name in classes):
            self.capture = "name"
            self.capture_tag = "div"

    def handle_data(self, data: str) -> None:
        if self.card is None:
            return
        self.card["text"].append(data)
        if self.capture:
            self.card[self.capture].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.card_depth is None:
            if tag == "a":
                self.active_product_url = None
            return

        if tag == self.capture_tag:
            self.capture = None
            self.capture_tag = None
        if tag not in VOID_TAGS:
            self.card_depth -= 1
        if self.card_depth == 0:
            if self.card is not None:
                self.items.append({
                    "name": "".join(self.card["name"]).strip(),
                    "price": "".join(self.card["price"]).strip(),
                    "text": " ".join(self.card["text"]),
                    "url": self.card["url"],
                })
            self.card_depth = None
            self.card = None
            self.capture = None
            self.capture_tag = None


class CarrefourProductParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = dict(attrs)
        if not values.get("data-pid") or not values.get("data-name"):
            return
        if values.get("data-ifavailable", "true").lower() == "false":
            return
        self.items.append({
            "id": values.get("data-pid") or "",
            "name": values.get("data-name") or "",
            "price": values.get("data-price") or "",
            "href": values.get("href") or "",
            "category": values.get("data-category") or "",
        })


def normalize_product(source: str, raw: dict[str, str]) -> dict[str, Any] | None:
    name = normalize_text(raw.get("name", ""))
    matched = identify_item(name)
    price = parse_price(raw.get("price", ""))
    if not matched or price is None:
        return None
    canonical, category = matched
    if category != "meat" and re.search(r"\d\s*(?:m\s*l|毫升|公升|升)", name, re.IGNORECASE):
        return None
    weight_g = parse_package_weight_g(name)
    per_kg = parse_price_per_kg(name, price, weight_g)
    return {
        "source": source,
        "canonical": canonical,
        "category": category,
        "name": name,
        "price": round(price, 2),
        "weight_g": round(weight_g, 1) if weight_g else None,
        "price_per_kg": round(per_kg, 2) if per_kg else None,
        "url": raw.get("url", ""),
        "product_id": raw.get("id", ""),
    }


def source_status(products: list[dict[str, Any]], errors: list[str]) -> str:
    if products and errors:
        return "partial"
    if products:
        return "ok"
    return "error" if errors else "empty"


def collect_pxmart() -> dict[str, Any]:
    products_by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    latest_url = f"{PX_BASE}/hourArrive/"
    for query in PX_QUERIES:
        query_url = f"{PX_BASE}/hourArrive/search/result?{urlencode({'q': query})}"
        latest_url = query_url
        try:
            parser = PxCardParser()
            parser.feed(fetch_html(query_url))
            for raw in parser.items:
                if "已售完" in raw.get("text", "") or "售完" in raw.get("text", ""):
                    continue
                normalized = normalize_product("pxmart", raw)
                if not normalized:
                    continue
                product_id = normalized["url"] or normalized["name"]
                products_by_id[product_id] = normalized
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            errors.append(f"搜尋「{query}」失敗：{error}")
        time.sleep(0.25)

    products = sorted(products_by_id.values(), key=lambda item: (item["canonical"], item["price"]))
    return {
        "id": "pxmart",
        "name": "全聯小時達",
        "url": latest_url,
        "homepage": f"{PX_BASE}/hourArrive/",
        "region_note": "公開小時達商品頁面；未選定個人配送門市",
        "status": source_status(products, errors),
        "errors": errors,
        "product_count": len(products),
        "products": products,
    }


def collect_carrefour() -> dict[str, Any]:
    products_by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    latest_url = f"{CARREFOUR_BASE}/zh/"
    for query in CARREFOUR_QUERIES:
        query_url = f"{CARREFOUR_BASE}/zh/search/?{urlencode({'q': query})}"
        latest_url = query_url
        try:
            parser = CarrefourProductParser()
            parser.feed(fetch_html(query_url))
            for raw in parser.items:
                normalized = normalize_product("carrefour", raw)
                if not normalized:
                    continue
                normalized["url"] = urljoin(CARREFOUR_BASE, raw.get("href", ""))
                product_id = normalized["product_id"] or normalized["url"] or normalized["name"]
                products_by_id[product_id] = normalized
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            errors.append(f"搜尋「{query}」失敗：{error}")
        time.sleep(0.2)

    products = sorted(products_by_id.values(), key=lambda item: (item["canonical"], item["price"]))
    return {
        "id": "carrefour",
        "name": "家樂福線上購物",
        "url": latest_url,
        "homepage": f"{CARREFOUR_BASE}/zh/",
        "region_note": "公開線上商品頁面；配送或取貨地區可能影響價格與庫存",
        "status": source_status(products, errors),
        "errors": errors,
        "product_count": len(products),
        "products": products,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/retail-prices.json")
    args = parser.parse_args()

    collected_at = now_taipei()
    sources = {
        "pxmart": collect_pxmart(),
        "carrefour": collect_carrefour(),
    }
    products = [product for source in sources.values() for product in source["products"]]
    snapshot = {
        "schema_version": 1,
        "collected_at": collected_at,
        "refresh_interval_hours": 6,
        "region": "高雄市試行版",
        "note": "這是官方公開線上商品頁快照，不代表指定實體門市的貨架價。",
        "sources": sources,
        "products": products,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(products)} retail listings from {len(sources)} retailer pages to {target}")
    for key, source in sources.items():
        print(f"{key}: {source['status']} ({source['product_count']} products)")


if __name__ == "__main__":
    main()
