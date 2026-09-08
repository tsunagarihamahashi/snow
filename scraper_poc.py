"""
運営お知らせ横断集約 - 技術検証プロトタイプ
RSS非対応ゲレンデ2件（尾瀬岩鞍・石打丸山）からニュース見出し＋リンクを抽出できるか検証する。

検証で分かったこと:
- 両サイトともJSレンダリング不要（requestsで取得した生HTMLにニュースデータが含まれる）
- サイトごとにCMSが異なり、共通セレクタは使えない（ゲレンデごとに個別パーサーが必要）
- HTTPヘッダにcharsetが無いサイトがあり、requestsのr.encodingを信用すると文字化けする
  → 必ず r.apparent_encoding を使うこと
"""
import re
import requests
from bs4 import BeautifulSoup


def fetch(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    r.encoding = r.apparent_encoding
    return BeautifulSoup(r.text, "html.parser")


def scrape_oze_iwakura():
    base = "https://www.oze-iwakura.co.jp/ski/news/"
    soup = fetch(base)
    items = []
    for block in soup.select(".block_news"):
        day = block.select_one(".day")
        title = block.select_one("h3")
        link = block.select_one(".btn_more a[href]")
        if not (day and title and link):
            continue
        items.append({
            "resort": "尾瀬岩鞍",
            "date": day.get_text(strip=True),
            "title": title.get_text(strip=True),
            "url": base + link["href"],
        })
    return items


def scrape_ishiuchi_maruyama():
    base = "https://ishiuchi.or.jp/green/green/news-list/"
    soup = fetch(base)
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/green/news/" not in href or href in seen:
            continue
        text = a.get_text(" ", strip=True)
        m = re.match(r"News\s*([\d.]+)\s*(.+)", text)
        if not m:
            continue
        seen.add(href)
        items.append({
            "resort": "石打丸山",
            "date": m.group(1),
            "title": m.group(2),
            "url": href,
        })
    return items


if __name__ == "__main__":
    all_items = scrape_oze_iwakura() + scrape_ishiuchi_maruyama()
    for item in all_items:
        print(f"[{item['resort']}] {item['date']} {item['title']}")
        print(f"  -> {item['url']}")
