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


def main():
    data = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "resorts": {
            "oze_iwakura": scrape_oze_iwakura(),
            "ishiuchi_maruyama": scrape_ishiuchi_maruyama(),
        },
    }
    with open("snow_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
