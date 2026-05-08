from __future__ import annotations

import copy
import unittest

from inventory import aggregate_stock, reorder_list


class InventoryTests(unittest.TestCase):
    def test_aggregate_stock_normalizes_and_sums_without_mutation(self) -> None:
        rows = [
            {"sku": "abc-1", "quantity": 4},
            {"sku": " ABC-1 ", "quantity": 3},
            {"sku": "xyz-9", "quantity": 2},
            {"sku": "", "quantity": 99},
        ]
        original = copy.deepcopy(rows)

        self.assertEqual(aggregate_stock(rows), {"ABC-1": 7, "XYZ-9": 2})
        self.assertEqual(rows, original)

    def test_reorder_list_uses_aggregate_stock_and_stable_order(self) -> None:
        rows = [
            {"sku": "abc-1", "quantity": 4},
            {"sku": " ABC-1 ", "quantity": 3},
            {"sku": "xyz-9", "quantity": 2},
            {"sku": "mno-2", "quantity": 2},
            {"sku": "rst-7", "quantity": 6},
        ]

        self.assertEqual(reorder_list(rows, minimum=5), ["MNO-2", "XYZ-9"])


if __name__ == "__main__":
    unittest.main()
