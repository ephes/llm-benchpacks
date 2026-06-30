#!/usr/bin/env python3
"""Pilot scraper for a price- and image-bearing product-offer fixture from billiger.de.

This is a *feasibility pilot*, not the production fixture builder. It fetches a
small sample from one category and emits a denormalised offers CSV plus summary
stats, so we can judge whether real billiger.de data makes a useful
product-matching benchmark (see
docs/benchmarks/product-offer-matching/dataset-sourcing-analysis.md).

Design notes:
- Cluster key is billiger's variant ``product_id`` (the output of billiger's own
  matching pipeline), NOT GTIN — merchant-feed GTINs are often wrong.
- The category billiger exposes is its own classifier output; kept as a label
  only, never as ground truth.
- Only the offers present in the initial HTML are captured (no lazy-load segment
  endpoint). That is enough for a pilot and already beats PriceRunner's ~2.7
  offers/cluster.
- Polite: single-threaded, fixed delay between requests, hard request cap.
- Writes only a derived, anonymised sample; raw HTML is never persisted.
"""
from __future__ import annotations

import argparse
import base64
import csv
import html as htmllib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
BASE = "https://www.billiger.de"
DELAY_S = 1.5
TIMEOUT_S = 30


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de-DE"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - pilot: skip and continue
        print(f"  ! fetch failed {url}: {exc}", file=sys.stderr)
        return None


def baseproduct_links(category_html: str, limit: int) -> list[str]:
    seen: list[str] = []
    for path in re.findall(r"/baseproducts/\d+-[a-z0-9-]+", category_html):
        if path not in seen:
            seen.append(path)
        if len(seen) >= limit:
            break
    return seen


def variant_links(baseproduct_html: str, limit: int) -> list[str]:
    seen: list[str] = []
    for path in re.findall(r"/products/\d+-[a-z0-9-]+", baseproduct_html):
        if path not in seen:
            seen.append(path)
        if len(seen) >= limit:
            break
    return seen


def _url_product_id(path: str) -> str | None:
    m = re.search(r"/products/(\d+)-", path)
    return m.group(1) if m else None


def _decode_clickouts(html: str) -> list[dict]:
    """Return offer dicts from the per-offer econda clickout payloads + title attr."""
    offers: list[dict] = []
    for tag in re.findall(r'<\w+\b[^>]*data-econda-clickout-params="[^"]+"[^>]*>', html):
        b64 = re.search(r'data-econda-clickout-params="([^"]+)"', tag)
        title = re.search(r'\btitle="([^"]+)"', tag)
        try:
            payload = json.loads(base64.b64decode(b64.group(1)))
        except Exception:  # noqa: BLE001
            continue
        lead = (payload.get("LeadEvent") or [[]])[0]
        if len(lead) < 9:
            continue
        offers.append(
            {
                "merchant_title": htmllib.unescape(title.group(1).strip()) if title else "",
                "cluster_id": lead[1],
                "norm_name": htmllib.unescape(lead[2]) if lead[2] else "",
                "category_path": lead[4],
                "brand": lead[5],
                "shop_name": htmllib.unescape(lead[7]) if lead[7] else "",
                "price": lead[8],
            }
        )
    # dedup on (cluster, shop, merchant_title): cluster_id must be in the key so a
    # same-shop/title clickout for a *different* product (recommendation/ad) cannot
    # evict the real target offer before scrape() filters by cluster_id.
    out, seen = [], set()
    for o in offers:
        key = (o["cluster_id"], o["shop_name"], o["merchant_title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


def _image_url(html: str) -> str:
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    return htmllib.unescape(m.group(1)) if m else ""


def _category_leaf(path: str) -> str:
    # "Handy & Telefon [100050]/Handys ohne Vertrag [4373]" -> "Handys ohne Vertrag"
    if not path:
        return ""
    leaf = path.split("/")[-1]
    return re.sub(r"\s*\[\d+\]\s*$", "", leaf).strip()


def scrape(
    category_url: str,
    n_base: int,
    n_variant: int,
    max_requests: int,
    query: str = "",
    max_offers: int | None = None,
    skip_base: int = 0,
    seen_variants: set[str] | None = None,
) -> list[dict]:
    requests_made = 0
    if seen_variants is None:
        seen_variants = set()

    def get(url: str) -> str | None:
        nonlocal requests_made
        if requests_made >= max_requests:
            return None
        if requests_made:
            time.sleep(DELAY_S)
        requests_made += 1
        return fetch(url)

    print(f"[1] category listing: {category_url}")
    cat_html = get(category_url)
    if not cat_html:
        sys.exit("category fetch failed")
    bases = baseproduct_links(cat_html, skip_base + n_base)[skip_base:]
    print(f"    using {len(bases)} baseproducts (skip {skip_base})")

    variant_paths: list[str] = []
    queued: set[str] = set()  # dedup within this category's queue only
    for i, bp in enumerate(bases, 1):
        html = get(BASE + bp)
        if not html:
            continue
        vs = variant_links(html, n_variant)
        # Skip products already fetched by an earlier search term (seen_variants is
        # shared across categories). Use a per-category `queued` set to avoid
        # queueing a variant twice here, but do NOT mark seen_variants yet — a
        # queued variant that is never fetched (request cap / fetch failure) must
        # stay eligible for a later search term.
        fresh = [v for v in vs if v not in seen_variants and v not in queued]
        queued.update(fresh)
        variant_paths.extend(fresh)
        print(f"[2] ({i}/{len(bases)}) {bp} -> {len(vs)} variants ({len(fresh)} new)")
        if requests_made >= max_requests:
            break

    rows: list[dict] = []
    for j, vp in enumerate(variant_paths, 1):
        target_id = _url_product_id(vp)
        html = get(BASE + vp)
        if not html:
            continue
        seen_variants.add(vp)  # mark globally seen only after a successful fetch
        # Keep only offers whose own payload cluster_id matches this page's target
        # product; the page also carries clickouts for recommendations/ads that
        # belong to other products and must not be mislabelled into this cluster.
        offers = [o for o in _decode_clickouts(html) if str(o["cluster_id"]) == str(target_id)]
        if not offers:
            continue
        cluster_id = target_id
        cluster_label = offers[0]["norm_name"]
        category_label = _category_leaf(offers[0]["category_path"])
        image_url = _image_url(html)
        for o in offers:
            rows.append(
                {
                    "title": o["merchant_title"],
                    "shop_name": o["shop_name"],
                    "price_eur": o["price"],
                    "brand": o["brand"],
                    "category_label": category_label,
                    "image_url": image_url,
                    "cluster_id": cluster_id,
                    "cluster_label": cluster_label,
                    "source_query": query,
                }
            )
        print(f"[3] ({j}/{len(variant_paths)}) cluster {cluster_id}: {len(offers)} offers")
        if requests_made >= max_requests:
            break
        if max_offers is not None and len(rows) >= max_offers:
            print(f"    reached per-category offer budget ({max_offers})")
            break

    print(f"\nrequests made: {requests_made}")
    return rows


def summarise(rows: list[dict]) -> None:
    by_cluster: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cluster[r["cluster_id"]].append(r)
    multi = {c: rs for c, rs in by_cluster.items() if len(rs) >= 2}
    with_price = sum(1 for r in rows if r["price_eur"])
    with_image = sum(1 for r in rows if r["image_url"])
    print("\n=== summary ===")
    print(f"offers           : {len(rows)}")
    print(f"clusters         : {len(by_cluster)} ({len(multi)} with >=2 offers)")
    print(f"offers/cluster   : {len(rows)/max(len(by_cluster),1):.2f} avg")
    print(f"price coverage   : {with_price}/{len(rows)}")
    print(f"image coverage   : {with_image}/{len(rows)}")
    print("\n=== sample multi-offer clusters (title variance) ===")
    for c, rs in list(multi.items())[:3]:
        print(f"- {c} | {rs[0]['cluster_label']}")
        for r in rs:
            print(f"    {str(r['price_eur']):>8} € [{r['shop_name'][:18]:>18}] {r['title'][:62]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--searchstrings",
        default="smartphone",
        help="comma-separated billiger.de search terms, one category each",
    )
    ap.add_argument("--baseproducts", type=int, default=12)
    ap.add_argument(
        "--skip-baseproducts",
        type=int,
        default=0,
        help="skip the first N baseproducts per category (for topping up beyond a prior run)",
    )
    ap.add_argument("--variants-per-base", type=int, default=3)
    ap.add_argument("--max-requests", type=int, default=55, help="per search term")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    ap.add_argument(
        "--target-offers",
        type=int,
        default=0,
        help="soft floor: stop after the variant/category that reaches at least this "
        "many total offers (0 = no cap). May overshoot by one cluster's offers, since "
        "whole clusters are kept intact rather than truncated mid-cluster.",
    )
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    global DELAY_S
    DELAY_S = args.delay

    queries = [q.strip() for q in args.searchstrings.split(",") if q.strip()]
    target = args.target_offers or None
    seen_variants: set[str] = set()  # shared across categories: fetch each product once
    all_rows: list[dict] = []
    for query in queries:
        url = f"{BASE}/search?searchstring={urllib.parse.quote(query)}"
        print(f"\n##### category: {query!r} ({len(all_rows)} offers so far) #####")
        remaining = (target - len(all_rows)) if target else None
        all_rows.extend(
            scrape(
                url,
                args.baseproducts,
                args.variants_per_base,
                args.max_requests,
                query,
                max_offers=remaining,
                skip_base=args.skip_baseproducts,
                seen_variants=seen_variants,
            )
        )
        if target and len(all_rows) >= target:
            print(f"\nreached global target of {target} offers")
            break
    if not all_rows:
        sys.exit("no rows scraped")

    # Assign globally unique offer ids across all categories (cluster_id is the
    # billiger product_id and is already globally unique, so it needs no remap).
    for seq, row in enumerate(all_rows, 1):
        row["offer_id"] = f"b{seq:05d}"
    fieldnames = ["offer_id"] + [k for k in all_rows[0] if k != "offer_id"]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nwrote {len(all_rows)} offers from {len(queries)} categories -> {args.out}")
    summarise(all_rows)


if __name__ == "__main__":
    main()
