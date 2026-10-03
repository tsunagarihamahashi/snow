"""
各ページの「お知らせ」を扱う道具箱。

    python tools/news_tool.py stale [--days 90]   # 取得日が古いページを一覧
    python tools/news_tool.py discover [--write]  # WordPress REST APIが使えるゲレンデを探す
    python tools/news_tool.py fetch [id ...] [--write]  # feed登録済みゲレンデの最新記事を取得

WordPressのサイトは /wp-json/wp/v2/posts で記事一覧が取れるため、個別パーサーを書かずに
お知らせを更新できる。使えると分かったゲレンデには news.feed を書き込んでおく。
feedが無いゲレンデは従来どおり手作業で更新する（stale で抜けを検知する）。
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (compatible; gerende-news/1.0)"}
TIMEOUT = 15
ITEMS = 3
# 直近に更新があるかの判定ライン（1年半）
RECENT = (dt.date.today() - dt.timedelta(days=550)).strftime("%Y年%m月%d日")


def resort_ids() -> list:
    return json.loads((DATA / "site.json").read_text(encoding="utf-8"))["resorts"]


def path_of(rid: str) -> Path:
    return DATA / "resorts" / f"{rid}.json"


def load(rid: str) -> dict:
    return json.loads(path_of(rid).read_text(encoding="utf-8"))


def save(rid: str, r: dict):
    path_of(rid).write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_date(r: dict):
    """news.source 末尾の取得日（例: "from norn.co.jp/winter/news, 2026-09-20"）を読む。"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", r["news"].get("source") or "")
    return dt.date(*map(int, m.groups())) if m else None


def wp_bases(r: dict) -> list:
    """WordPressの設置先候補。ドメイン直下だけでなく /winter/ のようなサブディレクトリも試す。"""
    urls = [i["url"] for i in r["news"]["items"]]
    urls += [c["href"] for c in r["scale"]["cards"]]
    urls.append(r["snow"]["fallback_url"])
    if r["scale"]["map_img"]:
        urls.append(r["scale"]["map_img"]["src"])
    for kv in r["access"]["kv"]:
        urls += re.findall(r'href="([^"]+)"', kv["v"])
    bases = []
    for u in urls:
        p = urlsplit(u)
        if not p.scheme.startswith("http"):
            continue
        origin = f"{p.scheme}://{p.netloc}"
        cands = [origin]
        seg = [s for s in p.path.split("/") if s]
        # wp-content より前の階層が設置先（例: /ogna/wp/wp-content/... → /ogna/wp）
        if "wp-content" in seg:
            cands.append(origin + "/" + "/".join(seg[: seg.index("wp-content")]))
        elif seg:
            cands.append(f"{origin}/{seg[0]}")
        for c in cands:
            if c.rstrip("/") not in bases:
                bases.append(c.rstrip("/"))
    return bases


PLACEHOLDER = re.compile(r"^(hello world!?|test\d*|sample page|サンプルページ|テスト投稿?)$", re.I)
SKIP_TYPES = {"pages", "media", "blocks", "menu-items", "navigation", "templates",
              "template-parts", "global-styles", "font-families", "font-faces", "patterns"}


def wp_types(base: str) -> list:
    """そのWordPressが持つ投稿タイプのREST baseを列挙する（お知らせが独自タイプのことが多い）。"""
    try:
        res = requests.get(base + "/wp-json/wp/v2/types", headers=UA, timeout=TIMEOUT)
        types = res.json() if res.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        return []
    out = []
    for t in (types or {}).values():
        rb = (t or {}).get("rest_base")
        if rb and rb not in SKIP_TYPES and rb not in out:
            out.append(rb)
    return out


def norm_url(u: str) -> str:
    """scheme と www. の有無を無視した比較用のURL（APIの link は www 無しで返ることがある）。"""
    return re.sub(r"^https?://(www\.)?", "", u.strip().lower())


def news_prefix(r: dict) -> str:
    """既存のお知らせURLに共通する前半部分。どの投稿タイプが「お知らせ」かの判定に使う。

    ドメインだけしか一致しない場合は判定に使えないので空文字を返す。
    """
    urls = [norm_url(i["url"]) for i in r["news"]["items"]]
    if not urls:
        return ""
    head = urls[0]
    for u in urls[1:]:
        i = 0
        while i < min(len(head), len(u)) and head[i] == u[i]:
            i += 1
        head = head[:i]
    head = head.rsplit("/", 1)[0] if "/" in head else ""
    path = head.split("/", 1)[1] if "/" in head else ""
    return head if len(path) >= 3 else ""


def wp_posts(endpoint: str, n: int = ITEMS) -> list:
    """WordPress REST APIから最新記事を取得する。取れなければ空リスト。"""
    try:
        res = requests.get(endpoint, params={"per_page": n, "_fields": "date,link,title"},
                           headers=UA, timeout=TIMEOUT)
        if res.status_code != 200:
            return []
        posts = res.json()
    except (requests.RequestException, ValueError):
        return []
    if not isinstance(posts, list):
        return []
    out = []
    for p in posts:
        try:
            d = dt.datetime.fromisoformat(p["date"])
            title = html.unescape(re.sub(r"<[^>]+>", "", p["title"]["rendered"])).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if title and not PLACEHOLDER.match(title):
            out.append({"date": f"{d.year}年{d.month:02d}月{d.day:02d}日", "title": title, "url": p["link"]})
    return out


def cmd_stale(args):
    today = dt.date.today()
    rows = []
    for rid in resort_ids():
        r = load(rid)
        d = source_date(r)
        age = (today - d).days if d else None
        rows.append((age if age is not None else 10**6, rid, r["name"], d, r["news"].get("feed")))
    rows.sort(reverse=True)
    print(f"お知らせの取得日（本日 {today}、しきい値 {args.days}日）\n")
    print(f"{'経過':>5}  {'取得日':<12} {'feed':<5} ゲレンデ")
    for age, rid, name, d, feed in rows:
        mark = "⚠" if age > args.days else " "
        print(f"{mark}{age if age < 10**6 else '-':>4}  {str(d or '不明'):<12} {'WP' if feed else '手動':<5} {name}")
    old = [x for x in rows if x[0] > args.days]
    print(f"\n要再確認: {len(old)}件 / {len(rows)}件")


def cmd_discover(args):
    hits, misses = [], []
    for rid in resort_ids():
        r = load(rid)
        if r["news"].get("feed") and not args.recheck:
            hits.append((rid, r["name"], r["news"]["feed"], "登録済み"))
            continue
        prefix = news_prefix(r)
        cur_urls = {norm_url(i["url"]) for i in r["news"]["items"]}
        best, best_score = None, 0
        for base in wp_bases(r):
            for rb in ["posts"] + [t for t in wp_types(base) if t != "posts"]:
                ep = f"{base}/wp-json/wp/v2/{rb}"
                items = wp_posts(ep)
                if not items:
                    continue
                # 「いま載せているお知らせ」と素性が一致する投稿タイプを選ぶ
                fetched = {norm_url(i["url"]) for i in items}
                score = 3 if fetched & cur_urls else 0                      # 同じ記事が取れた
                score += sum(2 for u in fetched if prefix and u.startswith(prefix))  # 同じ階層
                score += 2 if any(f"/{rb}/" in u for u in cur_urls) else 0   # 型名がURLに出る
                score += 1 if max(i["date"] for i in items) >= RECENT else 0  # 更新が止まっていない
                if score > best_score:
                    best, best_score = ep, score
            if best_score >= 3:
                break
        if best and best_score >= 3:
            hits.append((rid, r["name"], best, "新規"))
            if args.write:
                r["news"]["feed"] = best
                save(rid, r)
        else:
            misses.append((rid, r["name"], f"候補={best or 'なし'} 一致度={best_score}"))
            if args.write and r["news"].pop("feed", None):
                save(rid, r)
        print(".", end="", flush=True)
    print("\n\n[WordPress REST APIが使える]")
    for rid, name, ep, state in hits:
        print(f"  {name:<22} {state:<6} {ep}")
    print(f"\n[使えない / 手作業のまま] {len(misses)}件")
    for rid, name, why in misses:
        print(f"  {name:<22} {why}")
    if hits and not args.write:
        print("\n--write を付けると news.feed を書き込みます。")


def cmd_fetch(args):
    today = dt.date.today().isoformat()
    targets = args.ids or resort_ids()
    changed = 0
    for rid in targets:
        r = load(rid)
        feed = r["news"].get("feed")
        if not feed:
            continue
        items = wp_posts(feed)
        if not items:
            print(f"[取得失敗] {r['name']}（{feed}）")
            continue
        cur = r["news"]["items"]
        if cur and max(i["date"] for i in items) < max(i["date"] for i in cur) and not args.force:
            print(f"[スキップ] {r['name']}：取得できた記事が既存より古い（--force で上書き）")
            continue
        def key(xs):
            return [(x["date"], x["title"], norm_url(x["url"])) for x in xs]

        same = key(items) == key(cur)
        print(f"\n{r['name']}{'（変更なし）' if same else ''}")
        cur_keys = {(x["date"], x["title"], norm_url(x["url"])) for x in cur}
        for it in items:
            flag = " " if (it["date"], it["title"], norm_url(it["url"])) in cur_keys else "+"
            print(f"  {flag} {it['date']}  {it['title'][:48]}")
        if args.write and not same:
            host = urlsplit(feed).netloc.removeprefix("www.")
            r["news"]["items"] = items
            r["news"]["source"] = f"from {host}/wp-json, {today}"
            save(rid, r)
            changed += 1
    if args.write:
        print(f"\n{changed}件を更新しました。python build.py で再生成してください。")
    else:
        print("\n--write を付けると data/resorts/*.json を更新します。")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stale", help="取得日が古いページを一覧")
    s.add_argument("--days", type=int, default=90)
    s.set_defaults(func=cmd_stale)
    d = sub.add_parser("discover", help="WordPress REST APIが使えるゲレンデを探す")
    d.add_argument("--write", action="store_true")
    d.add_argument("--recheck", action="store_true", help="登録済みのfeedも探し直す")
    d.set_defaults(func=cmd_discover)
    f = sub.add_parser("fetch", help="feed登録済みゲレンデの最新記事を取得")
    f.add_argument("ids", nargs="*")
    f.add_argument("--write", action="store_true")
    f.add_argument("--force", action="store_true", help="既存より古い記事でも上書きする")
    f.set_defaults(func=cmd_fetch)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
