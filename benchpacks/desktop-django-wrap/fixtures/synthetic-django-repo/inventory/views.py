from django.http import JsonResponse
from django.shortcuts import render

from .models import StockItem


def dashboard(request):
    items = StockItem.objects.all()[:10]
    return render(request, "inventory/dashboard.html", {"items": items})


def healthz(request):
    return JsonResponse({"ok": True, "service": "inventory"})
