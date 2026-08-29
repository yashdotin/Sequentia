
from __future__ import annotations

import re

from apps.dashboard.views import _domain_breakdown
from apps.pathway.models import PathChangeEvent
from apps.pathway.services.path_engine import get_current_path, next_best_action
from apps.profiles.models import LearnerProfile
from apps.profiles.views import _query_text_for
from apps.recommender.ml.inference import get_engine
from apps.recommender.services.explainability import explain_blocked, explain_recommendation
from apps.recommender.services.scoring import score_all_courses

from .gemini_client import phrase_grounded_answer


def _find_mentioned_course(question: str) -> str | None:
    engine = get_engine()
    lower = question.lower()
    best_match = None
    best_len = 0
    for course in engine.all_courses:
        simplified = re.sub(r"[^a-z0-9 ]", "", course.lower())
        if simplified in re.sub(r"[^a-z0-9 ]", "", lower) and len(simplified) > best_len:
            best_match = course
            best_len = len(simplified)
    return best_match


def answer_question(profile: LearnerProfile, question: str) -> str:
    facts = _grounded_answer(profile, question)
    phrased = phrase_grounded_answer(question, facts)
    return phrased or facts


def _grounded_answer(profile: LearnerProfile, question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "Ask me something about your path or recommendations — e.g. \"why is this first?\""

    lower = question.lower()
    path = get_current_path(profile)
    if not path:
        return "You don't have a path yet — build one from onboarding first."

    query_text = _query_text_for(profile)
    scores = {s.course: s for s in score_all_courses(profile, query_text)}
    mentioned_course = _find_mentioned_course(question)

    if any(kw in lower for kw in ["what changed", "why did my path change", "path change"]):
        event = PathChangeEvent.objects.filter(profile=profile).first()
        if event:
            return f"Your path changed from v{event.previous_version or '—'} to v{event.new_version}: {event.reason}"
        return "Your path hasn't changed since it was first generated."

    if any(kw in lower for kw in ["next step", "what should i do", "what's next", "what next"]):
        action = next_best_action(path)
        if action:
            return f"Your next best action is: {action.course}. {action.reason}"
        return "Everything currently eligible in your path is already in progress or completed."

    if any(kw in lower for kw in ["what can i skip", "can i skip"]):
        completed = list(path.items.filter(status="completed").values_list("course", flat=True))
        if completed:
            return "You've already covered: " + ", ".join(completed) + " — these won't be repeated."
        return "You haven't marked anything as completed yet, so nothing is being skipped."

    if any(kw in lower for kw in ["which project", "project should i pick", "recommend a project", "give me a project"]):
        stage_items = list(path.items.filter(status__in=["current", "completed"]))
        reachable_stages = {i.stage for i in stage_items}
        if reachable_stages:
            return (
                "Check your Projects page — briefs unlock as you reach their stage. "
                f"Right now you've reached: {', '.join(sorted(reachable_stages))}."
            )
        return "Complete or reach a stage in your path first, then check your Projects page — briefs unlock as you go."

    if any(kw in lower for kw in ["career gap", "biggest gap", "weakest area", "what am i missing"]):
        items = list(path.items.all())
        domains = _domain_breakdown(items)
        real_domains = [d for d in domains if d["total"] >= 2]
        if not real_domains:
            return "Your path doesn't have enough items in any single domain yet to call out a clear gap."
        gap = real_domains[-1]
        strongest = real_domains[0]
        return (
            f"Your largest gap right now is {gap['domain']} ({gap['pct']}% of that domain's items done). "
            f"Your strongest area is {strongest['domain']} ({strongest['pct']}%)."
        )

    if any(kw in lower for kw in ["why am i learning this", "why is this next", "why this"]) and not mentioned_course:
        action = next_best_action(path)
        if action:
            return f"{action.course}: {action.reason}"
        return "Nothing is currently marked as your next step."

    if mentioned_course and mentioned_course in scores:
        score = scores[mentioned_course]
        if any(kw in lower for kw in ["why not", "why isn't", "why isnt", "not next", "later", "blocked"]):
            blocked_reason = explain_blocked(score)
            if blocked_reason:
                return f"{mentioned_course} is later in your path because {blocked_reason}"
            return f"{mentioned_course} has no unmet prerequisites — it may just be scoring lower than your current next action right now."
        return explain_recommendation(score)

    return (
        "I can answer questions about your recommendations and path — like \"why is this "
        "first?\", \"what's next?\", or \"why did my path change?\". I can't help with general "
        "teaching questions outside your path."
    )
