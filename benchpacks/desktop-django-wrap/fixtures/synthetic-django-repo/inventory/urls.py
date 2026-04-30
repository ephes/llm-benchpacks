from django.urls import path

from . import views


app_name = "inventory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("healthz/", views.healthz, name="healthz"),
]
