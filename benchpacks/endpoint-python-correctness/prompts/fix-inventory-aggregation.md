Fix the small Python repository by editing only the inventory aggregation
module.

Allowed repo-root path to edit:

- `inventory.py`

Current file: `inventory.py`

```python
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
```

Relevant test expectations from `tests/test_inventory.py`:

```python
rows = [
    {"sku": "abc-1", "quantity": 4},
    {"sku": " ABC-1 ", "quantity": 3},
    {"sku": "xyz-9", "quantity": 2},
    {"sku": "", "quantity": 99},
]
original = copy.deepcopy(rows)

self.assertEqual(aggregate_stock(rows), {"ABC-1": 7, "XYZ-9": 2})
self.assertEqual(rows, original)

rows = [
    {"sku": "abc-1", "quantity": 4},
    {"sku": " ABC-1 ", "quantity": 3},
    {"sku": "xyz-9", "quantity": 2},
    {"sku": "mno-2", "quantity": 2},
    {"sku": "rst-7", "quantity": 6},
]

self.assertEqual(reorder_list(rows, minimum=5), ["MNO-2", "XYZ-9"])
```

Observed failures:

```text
$ python -m unittest discover -s tests
FAIL: test_aggregate_stock_normalizes_and_sums_without_mutation (test_inventory.InventoryTests.test_aggregate_stock_normalizes_and_sums_without_mutation)
AssertionError: {'abc-1': 4, ' ABC-1 ': 3, 'xyz-9': 2, '': 99} != {'ABC-1': 7, 'XYZ-9': 2}

FAIL: test_reorder_list_uses_aggregate_stock_and_stable_order (test_inventory.InventoryTests.test_reorder_list_uses_aggregate_stock_and_stable_order)
AssertionError: Lists differ: [' ABC-1 ', 'abc-1', 'mno-2', 'xyz-9'] != ['MNO-2', 'XYZ-9']
```

Expected behavior:

- `aggregate_stock(rows)` returns a dict keyed by normalized SKU.
- Normalized SKU means `str(row["sku"]).strip().upper()`.
- Rows with a blank normalized SKU are ignored.
- Quantities are summed for duplicate normalized SKUs.
- Quantities may be integers or numeric strings.
- `aggregate_stock(rows)` must not mutate the input row dictionaries.
- `reorder_list(rows, minimum)` uses aggregated stock, includes only SKUs with
  total quantity strictly less than `minimum`, and returns those SKUs sorted in
  ascending order by total quantity, then SKU.
- `reorder_list(rows, minimum)` must not mutate the input row dictionaries.

Output contract:

- Your entire response must be one fenced code block with info string exactly
  `diff`.
- The first line of your response must be the literal fence marker `` ```diff ``.
- Do not include `<think>`, hidden reasoning, analysis, explanations, shell
  commands, or markdown outside the fenced block.
- Use only exact repo-root paths listed above.
- Omit `index` lines and do not invent paths.
- Inside the block, return a complete unified diff that applies with
  `git apply` from the repository root.
- Close the fenced block.
