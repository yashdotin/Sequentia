from django.contrib import admin

from .models import Recommendation, RecommendationFeedback

admin.site.register(Recommendation)
admin.site.register(RecommendationFeedback)
