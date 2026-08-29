from django.urls import path

from . import views

app_name = "coach"

urlpatterns = [
    path("mentor/", views.mentor, name="mentor"),
    path("ask/", views.ask, name="ask"),
]
