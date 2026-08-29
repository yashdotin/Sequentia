from django.urls import path

from . import views

app_name = "recommender"

urlpatterns = [
    path("recommendations/<int:recommendation_id>/feedback/", views.submit_feedback, name="feedback"),
]
