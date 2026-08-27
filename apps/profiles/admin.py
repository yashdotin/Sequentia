from django.contrib import admin

from .models import LearnerProfile, LearnerInterest, LearnerSkillEvidence, LearningHistoryEntry

admin.site.register(LearnerProfile)
admin.site.register(LearnerInterest)
admin.site.register(LearnerSkillEvidence)
admin.site.register(LearningHistoryEntry)
