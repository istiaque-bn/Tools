from django.urls import path

from . import views

app_name = "jssdm"

urlpatterns = [path("", views.checker, name="checker")]
