"""
Static site build: data/resorts/<id>.json + templates/ -> lp_prototype_<id>.html, index.html

    python build.py            # build everything
    python build.py naeba      # build one resort (and the index)
"""
import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

env = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=False,
    lstrip_blocks=False,
)

# keys the browser-side script needs; everything else stays server-rendered
PAYLOAD_KEYS = ("price", "rental", "weather", "snow", "season", "livecam")


def out_name(rid: str) -> str:
    return f"lp_prototype_{rid}.html"


def load_resort(rid: str) -> dict:
    return json.loads((DATA / "resorts" / f"{rid}.json").read_text(encoding="utf-8"))


# 標準的なリフト輸送力（人/時）。公式値がある場合は capacity_official を優先
LIFT_CAPACITY = {"gondola": 2000, "ropeway": 1000, "quad": 2400, "triple": 1800, "pair": 1200, "single": 600}
LIFT_LABEL = {"gondola": "ゴンドラ", "ropeway": "ロープウェイ", "quad": "クワッド", "triple": "トリプル", "pair": "ペア", "single": "シングル"}


def crowd_index(all_resorts: dict) -> dict:
    """混雑しにくさ: 滑走面の余裕(㎡/台)とリフトの余裕(人時/台)を算出し、対象ゲレンデ内で順位付けする。"""
    rows = {}
    for rid, r in all_resorts.items():
        c = r.get("crowd")
        if not c or c.get("exclude"):
            continue
        cap = c.get("capacity_official") or sum(LIFT_CAPACITY[k] * n for k, n in c["lifts"].items())
        rows[rid] = {"slope": c["area_ha"] * 10000 / c["parking"], "lift": cap / c["parking"], "capacity": cap}
    n = len(rows)
    for i, k in enumerate(sorted(rows, key=lambda k: -rows[k]["slope"]), 1):
        rows[k]["slope_rank"] = i
    for i, k in enumerate(sorted(rows, key=lambda k: -rows[k]["lift"]), 1):
        rows[k]["lift_rank"] = i
    by_total = sorted(rows, key=lambda k: (rows[k]["slope_rank"] + rows[k]["lift_rank"], -rows[k]["slope"]))
    for i, k in enumerate(by_total, 1):
        rows[k]["total_rank"] = i
        rows[k]["n"] = n
        rows[k]["tier"] = "good" if i <= n / 3 else ("mid" if i <= 2 * n / 3 else "low")
    return rows


def inject_crowd_stats(r: dict, idx: dict):
    c = r.get("crowd")
    if not c:
        return
    if c.get("exclude"):
        r["scale"]["crowd_note"] = f"混雑しにくさ指標：{c['exclude']}。"
        return
    x = idx[r["id"]]
    lifts = "・".join(f"{LIFT_LABEL[k]}{n}" for k, n in c["lifts"].items() if n)
    cap_src = "公式発表値" if c.get("capacity_official") else f"{lifts}の標準値から推定"
    r["scale"]["stats"] += [
        {"num": f"{x['slope']:,.0f}", "num_unit": None, "unit": "ゲレンデの余裕 ㎡/台<br>（総面積÷駐車場台数）",
         "wide": False, "tier": None, "idx_tag": f"{x['n']}件中{x['slope_rank']}位"},
        {"num": f"{x['lift']:,.1f}", "num_unit": None, "unit": f"リフトの余裕 人時/台<br>（輸送力{x['capacity']:,}人/時÷駐車場台数）",
         "wide": False, "tier": None, "idx_tag": f"{x['n']}件中{x['lift_rank']}位"},
        {"num": f"{x['total_rank']}", "num_unit": f"位 / {x['n']}件", "unit": "混雑しにくさ 総合（ゲレンデとリフトの順位平均）",
         "wide": True, "tier": x["tier"], "idx_tag": None},
    ]
    est = f"（{c['note']}）" if c.get("estimated") else ""
    r["scale"]["crowd_note"] = (
        f"混雑しにくさは駐車場台数を来場者数の代理指標として算出した参考値。輸送力は{cap_src}{est}。"
        f"順位は算出対象{x['n']}ゲレンデ中。"
    )


def even_out_stat_grid(stats: list):
    """2列グリッドで空セルが出ないよう、奇数個並んだ通常セルの最後を全幅にする。"""
    run = []
    for s in stats + [{"wide": True}]:
        if s.get("wide"):
            if len(run) % 2 == 1:
                run[-1]["wide"] = True
            run = []
        else:
            run.append(s)


def build_resort(rid: str, idx: dict) -> Path:
    r = load_resort(rid)
    inject_crowd_stats(r, idx)
    even_out_stat_grid(r["scale"]["stats"])
    payload = {k: r[k] for k in PAYLOAD_KEYS}
    html = env.get_template("resort.html.j2").render(r=r, payload=payload)
    out = ROOT / out_name(rid)
    out.write_text(html, encoding="utf-8", newline="\n")
    return out


def build_index(site: dict) -> Path:
    resorts = [{"name": load_resort(rid)["name"], "out": out_name(rid)} for rid in site["resorts"]]
    html = env.get_template("index.html.j2").render(site=site, resorts=resorts)
    out = ROOT / "index.html"
    out.write_text(html, encoding="utf-8", newline="\n")
    return out


def main(argv):
    site = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    idx = crowd_index({rid: load_resort(rid) for rid in site["resorts"]})
    targets = argv or site["resorts"]
    for rid in targets:
        print("built", build_resort(rid, idx).name)
    print("built", build_index(site).name)


if __name__ == "__main__":
    main(sys.argv[1:])
