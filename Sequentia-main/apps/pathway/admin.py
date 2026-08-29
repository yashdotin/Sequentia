from django.contrib import admin

from .models import LearningPath, LearningPathItem, PathChangeEvent

admin.site.register(LearningPath)
admin.site.register(LearningPathItem)
admin.site.register(PathChangeEvent)
