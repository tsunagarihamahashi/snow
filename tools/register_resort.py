"""
新しいゲレンデ JSON を作った後の登録作業をまとめて行う。

    python tools/register_resort.py <id> [<id> ...]

- data/site.json の resorts に id を追加（未登録の場合のみ）
- scrape_snow.py に scrape_<id>() のスタブ（available: False）と main() への登録を追加（未登録の場合のみ）
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STUB = '''def scrape_{id}():
    # 公式サイトの積雪表示の構造が未確認のため、現時点では未対応として正直に記録する。
    return {{"available": False, "note": "積雪量を表示するページ構造が未確認のため今回は取得していません"}}


def main():'''


def register(rid: str):
    jpath = ROOT / "data" / "resorts" / f"{rid}.json"
    if not jpath.exists():
        sys.exit(f"{jpath} がありません")
    site_p = ROOT / "data" / "site.json"
    site = json.loads(site_p.read_text(encoding="utf-8"))
    if rid not in site["resorts"]:
        site["resorts"].append(rid)
        site_p.write_text(json.dumps(site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("site.json: added", rid)
    sp = ROOT / "scrape_snow.py"
    s = sp.read_text(encoding="utf-8")
    if f"def scrape_{rid}(" not in s:
        s = s.replace("def main():", STUB.format(id=rid), 1)
        s = re.sub(r'(\n(\s+)"[a-z_]+": scrape_[a-z_]+\(\),\n)(\s+\},)', rf'\1\2"{rid}": scrape_{rid}(),\n\3', s, count=1)
        sp.write_text(s, encoding="utf-8")
        print("scrape_snow.py: added scrape_" + rid)
    import ast
    ast.parse(sp.read_text(encoding="utf-8"))


if __name__ == "__main__":
    for rid in sys.argv[1:]:
        register(rid)
