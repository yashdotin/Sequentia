from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("home/", views.home, name="home"),
    path("readiness/", views.readiness, name="readiness"),
    path("readiness/internship-mode/", views.toggle_internship_mode, name="toggle_internship_mode"),
]
