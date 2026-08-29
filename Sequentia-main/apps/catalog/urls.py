from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("resources/<slug:slug>/", views.resource_detail, name="resource_detail"),
    path("resources/<slug:slug>/save/", views.toggle_save, name="toggle_save"),
    path("saved/", views.saved_resources, name="saved_resources"),
    path("search/", views.search, name="search"),
    path("projects/", views.projects_list, name="projects"),
    path("projects/<slug:slug>/action/", views.project_action, name="project_action"),
]
