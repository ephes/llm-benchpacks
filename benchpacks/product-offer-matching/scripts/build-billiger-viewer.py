#!/usr/bin/env python3
"""Build a self-contained HTML viewer for a billiger.de pilot offers CSV.

Reads the denormalised offers CSV produced by ``scrape-billiger-pilot.py`` and
writes a single static HTML file that groups offers by cluster (the billiger
``product_id``) within each category, so the clusters/products can be eyeballed
in a browser. Renders the product image, cluster label, per-offer shop/price/raw
title, and flags price outliers to make mis-clustered offers easy to spot.

Usage:
    python3 build-billiger-viewer.py --in offers.csv --out viewer.html
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>billiger.de pilot — cluster viewer</title>
<style>
:root {{ --bg:#0e1117; --panel:#161b22; --line:#2b313a; --fg:#e6edf3; --mut:#8b949e;
  --acc:#58a6ff; --warn:#d29922; --mono:ui-monospace,SFMono-Regular,Menlo,monospace; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
header {{ position:sticky; top:0; z-index:10; background:#0e1117ee; backdrop-filter:blur(6px);
  border-bottom:1px solid var(--line); padding:14px 22px; }}
h1 {{ margin:0 0 8px; font-size:18px; }}
.controls {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
input, select {{ background:var(--panel); color:var(--fg); border:1px solid var(--line);
  border-radius:6px; padding:6px 10px; font-size:13px; }}
input[type=search] {{ min-width:280px; }}
.stat {{ color:var(--mut); font-size:12px; }}
main {{ padding:18px 22px 80px; }}
h2.cat {{ font-size:15px; margin:26px 0 12px; border-left:3px solid var(--acc); padding-left:9px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:14px; }}
.cluster {{ background:var(--panel); border:1px solid var(--line); border-radius:9px; overflow:hidden; }}
.chead {{ display:flex; gap:12px; padding:11px; border-bottom:1px solid var(--line); }}
.thumb {{ width:74px; height:74px; flex:0 0 74px; object-fit:contain; background:#fff;
  border-radius:6px; }}
.cmeta {{ min-width:0; }}
.clabel {{ font-weight:600; }}
.csub {{ color:var(--mut); font-size:12px; margin-top:2px; }}
.cid {{ font-family:var(--mono); color:var(--acc); }}
.prange {{ font-family:var(--mono); font-size:12px; margin-top:4px; }}
ul.offers {{ list-style:none; margin:0; padding:6px 11px 10px; }}
ul.offers li {{ display:flex; gap:9px; padding:4px 0; border-bottom:1px dotted #21262d; font-size:13px; }}
ul.offers li:last-child {{ border:0; }}
.price {{ font-family:var(--mono); width:78px; flex:0 0 78px; text-align:right; }}
.price.out {{ color:var(--warn); font-weight:600; }}
.shop {{ width:118px; flex:0 0 118px; color:var(--mut); font-size:12px; overflow:hidden;
  text-overflow:ellipsis; white-space:nowrap; }}
.otitle {{ min-width:0; }}
.flag {{ color:var(--warn); font-size:11px; margin-left:6px; }}
.empty {{ color:var(--mut); padding:40px; text-align:center; }}
</style></head>
<body>
<header>
  <h1>billiger.de pilot — cluster viewer</h1>
  <div class="controls">
    <input type="search" id="q" placeholder="filter by title / label / shop / cluster id…">
    <select id="cat"></select>
    <select id="sort">
      <option value="size">sort: most offers</option>
      <option value="spread">sort: widest price spread</option>
      <option value="label">sort: label A–Z</option>
    </select>
    <label class="stat"><input type="checkbox" id="onlyout"> only price-outlier clusters</label>
    <span class="stat" id="stat"></span>
  </div>
</header>
<main id="main"></main>
<script>
const DATA = {data_json};

function median(xs) {{
  const s = [...xs].sort((a,b)=>a-b); const n=s.length;
  return n ? (n%2 ? s[(n-1)/2] : (s[n/2-1]+s[n/2])/2) : 0;
}}

// group offers -> clusters
const clusters = {{}};
for (const o of DATA) {{
  const k = o.cluster_id;
  (clusters[k] ||= {{cluster_id:k, label:o.cluster_label, category:o.category_label,
                     query:o.source_query, image:o.image_url, offers:[]}}).offers.push(o);
}}
const CLUSTERS = Object.values(clusters).map(c => {{
  const prices = c.offers.map(o=>parseFloat(o.price_eur)).filter(x=>!isNaN(x));
  const med = median(prices);
  c.min = Math.min(...prices); c.max = Math.max(...prices); c.med = med;
  c.spread = med ? (c.max - c.min) / med : 0;
  for (const o of c.offers) {{
    const p = parseFloat(o.price_eur);
    o._out = med && !isNaN(p) && (p > med*1.8 || p < med*0.55);
  }}
  c.hasOut = c.offers.some(o=>o._out);
  return c;
}});

const cats = [...new Set(CLUSTERS.map(c=>c.category))].sort();
const catSel = document.getElementById('cat');
catSel.innerHTML = '<option value="">all categories</option>' +
  cats.map(c=>`<option>${{c}}</option>`).join('');

const esc = s => (s??'').replace(/[&<>"]/g, m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[m]));
const eur = x => isNaN(x)?'—':x.toFixed(2)+' €';

function render() {{
  const q = document.getElementById('q').value.toLowerCase().trim();
  const cat = catSel.value;
  const sort = document.getElementById('sort').value;
  const onlyOut = document.getElementById('onlyout').checked;

  let cs = CLUSTERS.filter(c => {{
    if (cat && c.category !== cat) return false;
    if (onlyOut && !c.hasOut) return false;
    if (!q) return true;
    if ((c.label+' '+c.cluster_id+' '+c.category).toLowerCase().includes(q)) return true;
    return c.offers.some(o => (o.title+' '+o.shop_name).toLowerCase().includes(q));
  }});
  if (sort==='size') cs.sort((a,b)=>b.offers.length-a.offers.length);
  else if (sort==='spread') cs.sort((a,b)=>b.spread-a.spread);
  else cs.sort((a,b)=>a.label.localeCompare(b.label));

  document.getElementById('stat').textContent =
    `${{cs.length}} clusters · ${{cs.reduce((n,c)=>n+c.offers.length,0)}} offers shown`;

  const byCat = {{}};
  for (const c of cs) (byCat[c.category] ||= []).push(c);
  const main = document.getElementById('main');
  if (!cs.length) {{ main.innerHTML = '<div class="empty">no clusters match</div>'; return; }}

  main.innerHTML = Object.keys(byCat).sort().map(cat => `
    <h2 class="cat">${{esc(cat)}} <span class="stat">(${{byCat[cat].length}})</span></h2>
    <div class="grid">${{byCat[cat].map(c => `
      <div class="cluster">
        <div class="chead">
          <img class="thumb" loading="lazy" src="${{esc(c.image)}}" alt="">
          <div class="cmeta">
            <div class="clabel">${{esc(c.label)}}</div>
            <div class="csub"><span class="cid">${{esc(c.cluster_id)}}</span> · ${{c.offers.length}} offers</div>
            <div class="prange">${{eur(c.min)}} – ${{eur(c.max)}} <span class="stat">(med ${{eur(c.med)}})</span></div>
          </div>
        </div>
        <ul class="offers">${{c.offers.map(o => `
          <li>
            <span class="price ${{o._out?'out':''}}">${{eur(parseFloat(o.price_eur))}}</span>
            <span class="shop" title="${{esc(o.shop_name)}}">${{esc(o.shop_name)}}</span>
            <span class="otitle">${{esc(o.title)}}${{o._out?'<span class="flag">⚠ price</span>':''}}</span>
          </li>`).join('')}}</ul>
      </div>`).join('')}}</div>`).join('');
}}

for (const id of ['q','cat','sort','onlyout'])
  document.getElementById(id).addEventListener('input', render);
render();
</script>
</body></html>"""


def build(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    return HTML_TEMPLATE.format(data_json=payload)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    rows = load(args.inp)
    args.out.write_text(build(rows), encoding="utf-8")
    clusters = {r["cluster_id"] for r in rows}
    print(f"wrote {args.out} — {len(rows)} offers, {len(clusters)} clusters")


if __name__ == "__main__":
    main()
