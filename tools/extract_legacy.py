"""
One-time migration: parse the hand-written lp_prototype_<id>.html pages and emit
data/resorts/<id>.json for the template-based build (build.py).

HTML sections are parsed with BeautifulSoup; JS data literals (priceTable, cams, ...)
are evaluated with node so unquoted keys / trailing commas are handled exactly.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "resorts"


# ---------------------------------------------------------------- helpers
def js_literal(script: str, name: str):
    """Return the JS value assigned to `const <name> = ...;` (or None)."""
    m = re.search(rf"^\s*(?:const|let)\s+{name}\s*=\s*", script, re.M)
    if not m:
        return None
    start = m.end()
    # find the end: first line that is exactly `  ];` / `  };` / or the statement end `;` for scalars
    tail = script[start:]
    if tail.lstrip().startswith(("[", "{")):
        opener = tail.lstrip()[0]
        closer = "]" if opener == "[" else "}"
        depth = 0
        in_str = None
        i = 0
        while i < len(tail):
            ch = tail[i]
            if in_str:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
            elif ch in "\"'`":
                in_str = ch
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    src = tail[: i + 1]
                    break
            i += 1
        else:
            raise ValueError(f"unterminated literal for {name}")
    else:
        src = tail.split(";", 1)[0]
    res = subprocess.run(
        ["node", "-e", "let lineSeq=0, rentalLineSeq=0; const v=(function(){return (" + src + ");})(); process.stdout.write(JSON.stringify(v));"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if res.returncode != 0:
        raise RuntimeError(f"node failed for {name}: {res.stderr[:400]}")
    return json.loads(res.stdout)


def inner(el):
    return "".join(str(c) for c in el.contents).strip() if el else None


def text(el):
    return el.get_text(" ", strip=True) if el else None


def li_items(section):
    items = []
    for li in section.select("ul.shop-list > li"):
        main = li.find("div", class_="shop-main")
        spans = main.find_all("span", recursive=False)
        name = inner(spans[0])
        tag = inner(spans[1]) if len(spans) > 1 else None
        right = None
        link = None
        for sib in main.next_siblings:
            if isinstance(sib, NavigableString):
                continue
            if sib.name == "span":
                right = inner(sib)
            elif sib.name == "a":
                link = {"href": sib["href"], "label": text(sib)}
            break
        items.append({"name": name, "tag": tag, "right": right, "link": link})
    return items


def cards(container):
    out = []
    for a in container.find_all("a", class_="map-card", recursive=False):
        out.append({
            "href": a["href"],
            "title": inner(a.find(class_="mc-title")),
            "sub": inner(a.find(class_="mc-sub")),
        })
    return out


def calc_foot(section, **kw):
    p = section.find("p", class_="calc-foot", **kw)
    return inner(p) if p else None


# ---------------------------------------------------------------- main extract
def extract(path: Path) -> dict:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    script = re.search(r"<script>(.*)</script>\s*</body>", html, re.S).group(1)
    rid = path.stem.replace("lp_prototype_", "")
    d = {"id": rid}

    d["title"] = text(soup.title)
    d["name"] = text(soup.find("h1", class_="resort-name"))
    d["eyebrow"] = text(soup.find("p", class_="eyebrow"))
    d["pref"] = text(soup.find("p", class_="pref"))

    hs = soup.find("div", class_="hours-strip")
    d["hours"] = {
        "items": [{"label": inner(i.find(class_="hour-label")), "value": inner(i.find(class_="hour-value"))}
                  for i in hs.find_all("div", class_="hour-item")],
        "foot": inner(hs.find("p", class_="hours-foot")),
    }

    # ---- scale
    sc = soup.find("section", id="scale")
    stats = []
    for st in sc.select(".stat-grid > .stat"):
        cls = st.get("class", [])
        tier = next((c[5:] for c in cls if c.startswith("tier-")), None)
        num = st.find("div", class_="num")
        num_unit = num.find("span", class_="num-unit")
        stats.append({
            "num": "".join(str(c) for c in num.contents if not (getattr(c, "name", None) == "span")).strip(),
            "num_unit": inner(num_unit) if num_unit else None,
            "unit": inner(st.find("div", class_="unit")),
            "wide": "stat-wide" in cls,
            "tier": tier,
            "idx_tag": inner(st.find(class_="idx-tag")),
        })
    level = None
    lb = sc.find("div", class_="level-bar")
    if lb:
        widths = [re.search(r"width:\s*([\d.]+)%", s["style"]).group(1) for s in lb.find_all("span")]
        colors = [re.search(r"background:\s*([^;]+)", s["style"]).group(1) for s in lb.find_all("span")]
        legend = [text(s) for s in sc.select(".level-legend > span")]
        level = [{"pct": float(w), "color": c, "label": l} for w, c, l in zip(widths, colors, legend)]
    img = sc.find("img", class_="trail-map-img")
    src_note = sc.find("p", class_="piste-source")
    grid = sc.find("div", class_="stat-grid")
    foots = sc.find_all("p", class_="calc-foot")
    notice = [inner(x) for x in foots if x.sourceline < grid.sourceline]
    after = [inner(x) for x in foots if x.sourceline > grid.sourceline]
    d["scale"] = {
        "stats": stats,
        "level_bar": level,
        "notice": notice[0] if notice else None,
        "foot": after[0] if after else None,
        "map_img": {"src": img["src"], "alt": img["alt"]} if img else None,
        "map_source_note": inner(src_note) if src_note else None,
        "cards": cards(sc),
    }

    # ---- reviews
    rv = soup.find("section", id="reviews")
    d["reviews"] = {
        "good": [inner(li) for li in rv.select(".review-col.good li")],
        "bad": [inner(li) for li in rv.select(".review-col.bad li")],
        "foot": calc_foot(rv),
    }

    # ---- weather / snow
    wx = soup.find("section", id="weather")
    lat = float(re.search(r"const LAT = ([\d.]+)", script).group(1))
    lon = float(re.search(r"LON = ([\d.]+)", script).group(1))
    d["weather"] = {"lat": lat, "lon": lon, "foot": inner(wx.find_all("p", class_="weather-foot")[-1])}
    snow_key = re.search(r"json\.resorts\.([a-z_]+)", script).group(1)
    fb = re.search(r'snowdepth-unavailable">積雪の実測値は.*?<a href="([^"]+)"', script)
    d["snow"] = {
        "key": snow_key,
        "fallback_url": fb.group(1) if fb else None,
        "layout": "top_mid_base" if "${d.top}" in script else "amount",
    }

    # ---- livecam
    lc = soup.find("section", id="livecam")
    card = lc.find("div", class_="livecam-card")
    lcd = {"cards": cards(lc), "foot": calc_foot(lc)}
    if card:
        ifr = card.find("iframe")
        img_el = card.find("img")
        label = card.find(id="lcLabel") or card.find(class_="lc-text")
        lcd["label"] = text(label)
        cams = js_literal(script, "cams")
        if ifr and "youtube" in ifr["src"]:
            lcd["type"] = "youtube"
            lcd["cams"] = cams or [{"label": lcd["label"], "id": re.search(r"embed/([\w-]+)", ifr["src"]).group(1)}]
            lcd["iframe_title"] = ifr.get("title")
        elif ifr:
            lcd["type"] = "skiday"
            lcd["cams"] = cams or [{"label": lcd["label"], "src": ifr["src"]}]
            lcd["iframe_title"] = ifr.get("title")
        else:
            lcd["type"] = "image"
            lcd["cams"] = cams or [{"label": lcd["label"], "url": img_el["src"].split("?")[0]}]
            lcd["alt"] = img_el.get("alt")
            m = re.search(r"setInterval\(refresh,\s*(\d+)\)", script)
            lcd["refresh_ms"] = int(m.group(1)) if m else 60000
        # aspect ratio override from inline CSS (ishiuchi uses 4/3)
        m = re.search(r"\.livecam-card \.lc-player \{[^}]*aspect-ratio:\s*([\d /]+);", html)
        lcd["aspect"] = m.group(1).replace(" ", "") if m else "16/9"
    else:
        lcd["type"] = "linkout"
    d["livecam"] = lcd

    # ---- price
    pr = soup.find("section", id="price")
    calc = pr.find("div", class_="calc-card")
    intro = pr.find("p", class_="calc-foot", recursive=False)
    price = {"intro": inner(intro) if intro else None,
             "total_label": text(calc.find(class_="calc-total").find(class_="label"))}
    if pr.find(id="lineList"):
        price["mode"] = "lines"
        price["ticket_types"] = js_literal(script, "ticketTypes")
        lines = js_literal(script, "lines")
        price["default_line"] = {k: v for k, v in lines[0].items() if k != "id"}
        add = js_literal(script, "lines")  # default for add button is in code; reuse first line w/ count 1
        price["add_line"] = dict(price["default_line"], count=1)
        price["foot"] = None  # rendered dynamically from notes
        m = re.search(r'\.textContent = notes\.length \? notes\.join\(" / "\) : "([^"]+)"', script)
        price["empty_note"] = m.group(1) if m else ""
    else:
        tog = calc.find("div", class_="daytype-toggle")
        price["mode"] = "toggle" if tog else "flat"
        price["categories"] = js_literal(script, "categories")
        price["counts"] = js_literal(script, "counts")
        if tog:
            price["options"] = [{"key": b["data-day"], "label": text(b)} for b in tog.find_all("button")]
            price["aria_label"] = tog.get("aria-label")
            price["price_table"] = js_literal(script, "priceTable")
            price["default_option"] = re.search(r'let dayType = "([^"]+)"', script).group(1)
        else:
            price["prices"] = js_literal(script, "prices")
        foot = calc.find("p", class_="calc-foot", recursive=False)
        price["foot"] = inner(foot) if foot else None
    d["price"] = price

    # ---- rental
    det = pr.find("details", class_="rental-acc")
    if not det:
        d["rental"] = {"mode": "none"}
    else:
        summ = det.find("summary")
        summ.find("span", class_="chev").decompose()
        rd = {"summary": text(summ)}
        legend = det.find("p", class_="rental-legend")
        rd["legend"] = inner(legend) if legend else None
        sim = det.find("div", class_="rental-sim")
        foot = sim.find("p", class_="calc-foot")
        rd["foot"] = inner(foot) if foot else None
        if det.find(id="rentalLineList"):
            rd["mode"] = "cart"
            rd["plans"] = js_literal(script, "rentalPlans")
            rl = js_literal(script, "rentalLines")
            rd["default_line"] = {k: v for k, v in rl[0].items() if k != "id"}
        else:
            rd["mode"] = "stepper"
            cats = js_literal(script, "rentalCategories")
            table = js_literal(script, "rentalPriceTable")
            items = []
            for c in cats:
                price_v = c.get("price")
                if price_v is None and table:
                    price_v = table[c["plan"]][c["person"]]
                items.append({"key": c["key"], "label": c["label"], "price": price_v})
            rd["items"] = items
            disc = det.find("label", class_="rental-discount")
            if disc:
                m = re.search(r"checked \? setCount \* (\d+)", script)
                rd["discount"] = {"label": disc.get_text(strip=True), "per_item": int(m.group(1))}
        d["rental"] = rd

    # ---- kids / onsen
    for sid in ("kids", "onsen"):
        sec = soup.find("section", id=sid)
        d[sid] = {"items": li_items(sec), "foot": calc_foot(sec)}

    # ---- gochiso
    go = soup.find("section", id="gochiso")
    badge = go.find("div", class_="cospa-badge")
    d["gochiso"] = {
        "badge": ({"tier": next(c[5:] for c in badge["class"] if c.startswith("tier-")),
                   "spans": [inner(s) for s in badge.find_all("span", recursive=False)]} if badge else None),
        "shops": js_literal(script, "shops"),
        "foot": calc_foot(go),
    }

    # ---- access
    ac = soup.find("section", id="access")
    d["access"] = {
        "kv": [{"k": inner(dt), "v": inner(dt.find_next_sibling("dd"))} for dt in ac.find_all("dt")],
        "foot": calc_foot(ac),
    }

    # ---- news
    nw = soup.find("section", id="news")
    m = re.search(r"// ---- scraped news \(([^)]*)\) ----", script)
    d["news"] = {"source": m.group(1) if m else None, "items": js_literal(script, "news"), "foot": calc_foot(nw)}

    # ---- sns
    sn = soup.find("section", id="sns")
    d["sns"] = cards(sn)[0]

    # ---- footer
    d["footer"] = [inner(p) for p in soup.find("footer").find_all("p")]

    # ---- season
    ss = re.search(r'seasonStart = new Date\("(\d{4}-\d{2}-\d{2})', script).group(1)
    se = re.search(r'seasonEnd = new Date\("(\d{4}-\d{2}-\d{2})', script).group(1)
    nxt = re.search(r'now > seasonEnd \? "([^"]+)"', script).group(1)
    si = script.find("const seasonStart")
    d["season"] = {"start": ss, "end": se, "approximate": "目安" in script[si:si + 1500], "next_note": nxt}

    return d


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    OUT.mkdir(parents=True, exist_ok=True)
    order = []
    for p in sorted(src.glob("lp_prototype_*.html")):
        d = extract(p)
        (OUT / f"{d['id']}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        order.append(d["id"])
        print("ok", d["id"], "price=" + d["price"]["mode"], "rental=" + d["rental"]["mode"], "livecam=" + d["livecam"]["type"])
    print(len(order), "resorts")


if __name__ == "__main__":
    main()
