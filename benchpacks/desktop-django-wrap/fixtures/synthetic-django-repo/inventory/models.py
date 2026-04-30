from django.db import models


class StockItem(models.Model):
    name = models.CharField(max_length=80)
    sku = models.CharField(max_length=32, unique=True)
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"
