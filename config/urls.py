from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.profiles.urls")),
    path("", include("apps.pathway.urls")),
    path("", include("apps.recommender.urls")),
    path("", include("apps.catalog.urls")),
    path("coach/", include("apps.coach.urls")),
    path("", include("apps.dashboard.urls")),
]
