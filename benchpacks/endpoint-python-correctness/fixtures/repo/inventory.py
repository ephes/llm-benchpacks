from __future__ import annotations

from typing import Any


def aggregate_stock(rows: list[dict[str, Any]]) -> dict[str, int]:
    stock: dict[str, int] = {}

    for row in rows:
        sku = str(row.get("sku", ""))
        quantity = int(row.get("quantity", 0))
        stock[sku] = quantity

    return stock


def reorder_list(rows: list[dict[str, Any]], minimum: int) -> list[str]:
    return sorted(
        sku
        for sku, quantity in aggregate_stock(rows).items()
        if quantity <= minimum
    )
