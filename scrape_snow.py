"""
積雪量（実測値）を各ゲレンデ公式サイトから毎日スクレイピングして snow_data.json を更新する。
GitHub Actionsのスケジュール実行から呼ばれる想定。

尾瀬岩鞍: トップページの dl.flex 内、dt="積雪量" の dd テキストを解析（上部/中間/ベース）。
石打丸山: オフシーズン中はページ上に積雪要素が存在しないため、取得できない場合は available=false で正直に記録する。
"""
import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; gerende-app-prototype/1.0)"}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = r.apparent_encoding
    return BeautifulSoup(r.text, "html.parser")


def scrape_oze_iwakura():
    soup = fetch("https://www.oze-iwakura.co.jp/ski/")
    dt = soup.find("dt", string=lambda s: s and "積雪量" in s)
    if not dt:
        return {"available": False, "note": "積雪量の要素が見つかりませんでした"}
    dd = dt.find_next_sibling("dd")
    text = dd.get_text(" ", strip=True) if dd else ""
    nums = {}
    for label, key in [("上部", "top"), ("中間", "mid"), ("ベース", "base")]:
        m = re.search(label + r"\s*([\d.]+)\s*cm", text)
        if m:
            nums[key] = float(m.group(1))
    updated = None
    day_el = soup.find("p", class_="day")
    if day_el:
        updated = day_el.get_text(strip=True).replace("更新", "").strip()
    if not nums:
        return {"available": False, "note": "積雪量の数値を解析できませんでした"}
    return {"available": True, **nums, "updated": updated}


def scrape_ishiuchi_maruyama():
    try:
        soup = fetch("https://ishiuchi.or.jp/winter/")
    except Exception as e:
        return {"available": False, "note": f"取得エラー: {e}"}
    dt = soup.find(string=lambda s: s and "積雪" in s)
    if not dt:
        return {"available": False, "note": "オフシーズンのため積雪情報が未掲載です"}
    # シーズン中に構造が判明したらここを実装する
    return {"available": False, "note": "積雪要素は見つかったが未対応の構造です（要確認）"}


def scrape_kawaba():
    try:
        soup = fetch("https://www.kawaba.co.jp/")
    except Exception as e:
        return {"available": False, "note": f"取得エラー: {e}"}
    dd = soup.find("dd", class_="weather-amount")
    if not dd:
        return {"available": False, "note": "積雪量の要素が見つかりませんでした"}
    text = dd.get_text(" ", strip=True)
    m = re.search(r"([\d.]+)\s*CM", text, re.IGNORECASE)
    if not m:
        return {"available": False, "note": "積雪量の数値を解析できませんでした"}
    updated = None
    update_el = soup.find("span", class_="update-info")
    if update_el:
        updated = update_el.get_text(strip=True)
    return {"available": True, "amount": float(m.group(1)), "updated": updated}


def scrape_marunuma():
    try:
        soup = fetch("https://www.marunuma.jp/winter/")
    except Exception as e:
        return {"available": False, "note": f"取得エラー: {e}"}
    title_el = soup.find("h4", class_="weatherarea-bottom-snow-title")
    if not title_el:
        return {"available": False, "note": "積雪量の要素が見つかりませんでした"}
    desc_el = title_el.find_next_sibling("p", class_="weatherarea-bottom-snow-desc")
    if not desc_el:
        return {"available": False, "note": "積雪量の要素が見つかりませんでした"}
    span = desc_el.find("span", class_="oswald")
    text = span.get_text(strip=True) if span else ""
    m = re.match(r"^([\d.]+)$", text)
    if not m:
        return {"available": False, "note": "積雪量の数値を解析できませんでした（オフシーズンの可能性）"}
    return {"available": True, "amount": float(m.group(1)), "updated": None}


def scrape_hodaigi():
    # このサイトはオフシーズンでも前シーズン最終日の数値を表示し続けるため、
    # 更新日が古い（3日以上前）場合はスクレイピングできても「古いデータ」として扱う。
    try:
        soup = fetch("https://hodaigi.jp/gelande-guide/")
    except Exception as e:
        return {"available": False, "note": f"取得エラー: {e}"}
    dt = soup.find("dt", string=lambda s: s and "積雪" in s)
    if not dt:
        return {"available": False, "note": "積雪量の要素が見つかりませんでした"}
    dd = dt.find_next_sibling("dd")
    text = dd.get_text(strip=True) if dd else ""
    m = re.match(r"^([\d.]+)\s*cm$", text, re.IGNORECASE)
    if not m:
        return {"available": False, "note": "積雪量の数値を解析できませんでした（オフシーズンの可能性）"}
    update_text = ""
    date_m = None
    for el in soup.find_all("span", class_="update"):
        t = el.get_text(strip=True)
        m2 = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", t)
        if m2:
            update_text = t
            date_m = m2
            break
    if date_m:
        updated_date = datetime(int(date_m.group(1)), int(date_m.group(2)), int(date_m.group(3)), tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - updated_date).days > 3:
            return {"available": False, "note": f"公式サイトの表示が{update_text}のまま更新されていません（オフシーズンの可能性）"}
    return {"available": True, "amount": float(m.group(1)), "updated": update_text.replace("更新", "").strip() or None}


def scrape_naeba():
    # 公式サイト（princehotels.co.jp）に積雪量の直接表示要素が見当たらなかったため、
    # 現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_gala():
    # 公式サイト（gala.co.jp）に積雪量の直接表示要素が見当たらなかったため、
    # 現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_kandatsu():
    # 公式サイト（kandatsu.com）に積雪量の直接表示要素が見当たらなかったため、
    # 現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_kagura():
    # 公式サイト（princehotels.co.jp）に積雪量の直接表示要素が見当たらなかったため、
    # 現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_maiko():
    # 公式サイト（maiko-resort.com）に積雪量の直接表示要素が見当たらなかったため、
    # 現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_ryuoo():
    # 公式サイト（ryuoo.com）に積雪量の直接表示要素が見当たらなかったため、
    # 現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_sugadaira():
    # 公式サイト（sugadaira-snowresort.com）トップに積雪cmを表示するウィジェットがあるが、
    # 現時点では実装方法が未確認のため、スクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def scrape_shigakogen():
    # 18スキー場が個別に積雪量を公開しており、全山共通の単一の積雪量データソースが
    # 見当たらなかったため、現時点ではスクレイピング未対応として正直に記録する。
    return {"available": False, "note": "18スキー場共通の積雪データソースが未確認のため今回は取得していません"}


def scrape_grandeco():
    # 公式サイト（grandecoresort.co.jp）のコース/リフト情報ページに積雪cmを表示する
    # ウィジェットがあるが、現時点では実装方法が未確認のため、
    # スクレイピング未対応として正直に記録する。
    return {"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}


def main():
    data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "resorts": {
            "oze_iwakura": scrape_oze_iwakura(),
            "ishiuchi_maruyama": scrape_ishiuchi_maruyama(),
            "kawaba": scrape_kawaba(),
            "marunuma": scrape_marunuma(),
            "hodaigi": scrape_hodaigi(),
            "naeba": scrape_naeba(),
            "gala": scrape_gala(),
            "kandatsu": scrape_kandatsu(),
            "kagura": scrape_kagura(),
            "maiko": scrape_maiko(),
            "ryuoo": scrape_ryuoo(),
            "sugadaira": scrape_sugadaira(),
            "shigakogen": scrape_shigakogen(),
            "grandeco": scrape_grandeco(),
        },
    }
    with open("snow_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
