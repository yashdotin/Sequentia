from django.urls import path

from . import views

app_name = "profiles"

urlpatterns = [
    path("onboarding/", views.onboarding, name="onboarding"),
    path("profile/", views.profile_edit, name="profile"),
    path("skills/", views.skills, name="skills"),
]
