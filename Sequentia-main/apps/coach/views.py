from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.pathway.services.path_engine import get_current_path, next_best_action

from .services.coach import answer_question


@login_required
def mentor(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")

    path = get_current_path(profile)
    action = next_best_action(path) if path else None

    quick_actions = [
        {"label": "Why am I learning this?", "question": "Why am I learning this?"},
        {"label": "What should I learn next?", "question": "What's next?"},
        {"label": "Can I skip this?", "question": f"Can I skip {action.course}?" if action else "Can I skip this?"},
        {"label": "Explain my career gap", "question": "Explain my career gap"},
        {"label": "Give me a project", "question": "Give me a project"},
    ]

    return render(request, "coach/mentor.html", {"profile": profile, "quick_actions": quick_actions})


@login_required
@require_POST
def ask(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return JsonResponse({"answer": "Build your profile first."}, status=400)

    question = request.POST.get("question", "")
    answer = answer_question(profile, question)
    return JsonResponse({"answer": answer})
