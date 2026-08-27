from django.urls import path

from . import views

app_name = "pathway"

urlpatterns = [
    path("path/", views.path_view, name="path"),
    path("path/change/", views.change_path, name="change"),
    path("path/mark/", views.mark_item, name="mark_item"),
    path("path/history/", views.history, name="history"),
]
