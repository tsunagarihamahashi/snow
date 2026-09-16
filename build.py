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


def build_resort(rid: str) -> Path:
    r = load_resort(rid)
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
    targets = argv or site["resorts"]
    for rid in targets:
        print("built", build_resort(rid).name)
    print("built", build_index(site).name)


if __name__ == "__main__":
    main(sys.argv[1:])
