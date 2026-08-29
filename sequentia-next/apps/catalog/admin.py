from django.contrib import admin

from .models import LearnerProjectState, LearnerSavedResource

admin.site.register(LearnerProjectState)
admin.site.register(LearnerSavedResource)
