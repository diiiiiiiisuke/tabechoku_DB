"""商品テキストから内容量・品種・都道府県などを抽出するパーサ群。"""
import re
import unicodedata

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

# 長い名前を先に照合する（「いちごさん」と「いちご」等の誤検出を防ぐ）
VARIETIES = sorted([
    "あまおう", "とちおとめ", "とちあいか", "スカイベリー", "さがほのか", "いちごさん",
    "ゆめのか", "紅ほっぺ", "章姫", "かおり野", "やよいひめ", "おいCベリー", "ベリーツ",
    "恋みのり", "よつぼし", "淡雪", "天使の実", "桃薫", "古都華", "まりひめ", "ゆうべに",
    "さくらももいちご", "あきひめ", "女峰", "ほしうらら", "雪うさぎ", "初恋の香り",
    "真紅の美鈴", "さちのか", "紅き夢", "きらぴ香", "おおきみ", "ゆうぼうし", "かおりん",
    "ひのしずく", "サマープリンセス", "あまりん", "べにたま", "越後姫", "あすかルビー", "あまおとめ",
    "みくのか", "恋ひめ", "マロンベリー", "スターナイト", "チーバベリー", "うずしおベリー", "ゆめのか",
    "かおりん", "おおきみ", "ふちのか", "よつぼし", "華かがり", "まりこ", "ももいちご", "すずあかね", "なつあかり", "夏秋いちご", "さぬき姫", "美人姫", "白いちご", "冬のきらめき", "星の煌めき",
], key=len, reverse=True)

_NUM = r"(\d+(?:\.\d+)?)"
_UNIT = r"(kg|g)(?![a-z])"
_MULT = r"(?:\s*[×xX*✕]\s*(\d+)\s*(?:パック|p|箱|個|袋|ケース|トレー|トレイ|段|セット)?)?"
_WEIGHT_RE = re.compile(r"約?\s*" + _NUM + r"\s*" + _UNIT + r"(?:\s*(?:前後|以上|程度|強))?" + _MULT, re.I)
_PER_PACK_RE = re.compile(r"1\s*(?:パック|p)\s*(?:あたり|当たり|につき)?\s*[:：]?\s*約?\s*" + _NUM + r"\s*" + _UNIT, re.I)
_PACKS_RE = re.compile(r"(\d+)\s*(?:パック|p(?![a-z])|トレー|トレイ)", re.I)
_BERRIES_RE = re.compile(r"(\d+)\s*(?:粒|個入|玉)")


def normalize(text):
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("キロ", "kg").replace("グラム", "g").replace("ｇ", "g")
    t = t.replace(",", "")
    return t


def _to_grams(num, unit):
    v = float(num)
    return v * 1000 if unit.lower() == "kg" else v


def parse_weight(text, default_pack_grams=270, default_berry_grams=20):
    """テキストから総重量(g)を推定する。

    戻り値: (grams or None, estimated: bool)
    estimated=True はパック数・粒数からの推計値であることを表す。
    """
    t = normalize(text)
    if not t:
        return None, False

    packs = None
    m = _PACKS_RE.search(t)
    if m:
        packs = int(m.group(1))

    m = _PER_PACK_RE.search(t)
    if m and packs and packs > 1:
        return _to_grams(m.group(1), m.group(2)) * packs, False

    m = _WEIGHT_RE.search(t)
    if m:
        grams = _to_grams(m.group(1), m.group(2))
        mult = int(m.group(3)) if m.group(3) else 1
        if 30 <= grams <= 20000:
            return grams * mult, False

    if packs and 0 < packs <= 50:
        return float(packs * default_pack_grams), True

    m = _BERRIES_RE.search(t)
    if m:
        n = int(m.group(1))
        if 0 < n <= 200:
            return float(n * default_berry_grams), True
    return None, False


def parse_variety(text):
    t = normalize(text)
    for v in VARIETIES:
        if v in t:
            return v
    return ""


def parse_prefecture(text):
    t = normalize(text)
    best = None
    for p in PREFECTURES:
        i = t.find(p)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, p)
    return best[1] if best else ""


def parse_price(text):
    """「1,980円」「¥1,980」のような表記から価格(int)を取り出す。"""
    t = normalize(text)
    m = re.search(r"[¥￥]\s*(\d{3,6})", t) or re.search(r"(\d{3,6})\s*円", t)
    return int(m.group(1)) if m else None


def is_shipping_included(text):
    t = normalize(text)
    return bool(re.search(r"送料(込|無料|当方負担)", t))


NOT_STRAWBERRY = "いちご以外"
_STRAWBERRY_RE = re.compile(r"いちご|イチゴ|苺|ストロベリー|strawberry|🍓", re.I)
# 「◯◯ベリー」はいちごのブランド名に多いが、他のベリー類は除く
_BERRY_RE = re.compile(r"(?<!ブルー)(?<!ラズ)(?<!ブラック)(?<!クラン)(?<!ハスカップ)ベリー")
_PROCESSED_RE = re.compile(
    r"ジャム|ドライ|甘酒|ケーキ|みるく|ミルク|ジュース|ソース|大福|アイス|シロップ|スムージー|ピューレ|"
    r"コンフィチュール|ゼリー|プリン|タルト|パフェ|菓子|スイーツ|酢|ワイン|サイダー|ジェラート|"
    r"フリーズドライ|パウダー|苗|ドレッシング|チョコ|クッキー|ようかん|羊羹")


def classify(title):
    """商品名から種類を判定する: 生果 / 冷凍 / 加工品 / いちご以外"""
    t = normalize(title)
    if not _STRAWBERRY_RE.search(t) and not parse_variety(t) and not _BERRY_RE.search(t):
        return NOT_STRAWBERRY
    if _PROCESSED_RE.search(t):
        return "加工品"
    if "冷凍" in t:
        return "冷凍"
    return "生果"
