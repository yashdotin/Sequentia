from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect

from apps.profiles.views import _query_text_for
from apps.pathway.services.path_engine import generate_path

from .models import Recommendation, RecommendationFeedback


@login_required
def submit_feedback(request, recommendation_id):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        raise Http404()


    try:
        recommendation = Recommendation.objects.get(id=recommendation_id, profile=profile)
    except Recommendation.DoesNotExist:
        raise Http404()

    if request.method != "POST":
        return redirect("pathway:path")

    feedback_value = request.POST.get("feedback")
    reason = request.POST.get("reason", "")
    if feedback_value not in {"helpful", "not_helpful"}:
        messages.error(request, "Invalid feedback.")
        return redirect("pathway:path")

    RecommendationFeedback.objects.update_or_create(
        profile=profile,
        recommendation=recommendation,
        defaults={"feedback": feedback_value, "reason": reason},
    )

    query_text = _query_text_for(profile)
    generate_path(
        profile,
        query_text,
        reason=f"Feedback recorded on {recommendation.course} — recommendations updated.",
    )
    messages.success(request, "Thanks — that'll shape your next recommendations.")
    return redirect("pathway:path")
