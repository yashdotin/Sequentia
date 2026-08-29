from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.profiles.models import LearnerProfile, LearningHistoryEntry
from apps.profiles.views import _query_text_for
from apps.recommender.ml.metadata import load_course_metadata
from apps.recommender.models import Recommendation, RecommendationFeedback
from .forms import PathFeedbackForm
from .models import LearningPathItem, PathChangeEvent
from .services.domain import determine_primary_domain, relevant_domains
from .services.path_engine import generate_path, get_current_path, next_best_action, readiness_percent
from .services.path_validator import validate_path

_FOCUS_DOMAIN = {
    "focus_ai": "Deep Learning",
    "focus_data_science": "Data Analytics",
    "focus_cloud": "Cloud",
}


def _owned_profile_or_none(request):
    return getattr(request.user, "learner_profile", None)


def _unlocks_map(metadata):
    unlocks = {}
    for course, meta in metadata.items():
        for prereq in meta.prerequisites:
            unlocks.setdefault(prereq, []).append(course)
    return unlocks


@login_required
def path_view(request):
    profile = _owned_profile_or_none(request)
    if not profile:
        return redirect("profiles:onboarding")

    path = get_current_path(profile)
    if not path:
        query_text = _query_text_for(profile)
        path = generate_path(profile, query_text, reason="Initial path generated.")

    items = list(path.items.all())
    seen_stages = []
    for item in items:
        if item.stage not in seen_stages:
            seen_stages.append(item.stage)

    metadata = load_course_metadata()
    unlocks = _unlocks_map(metadata)
    known_skills = set(
        profile.skills.filter(evidence_level="known").values_list("skill", flat=True)
    )

    rec_map = {r.course: r for r in Recommendation.objects.filter(profile=profile)}
    feedback_map = {
        fb.recommendation_id: fb
        for fb in RecommendationFeedback.objects.filter(profile=profile)
    }

    for item in items:
        meta = metadata.get(item.course)
        item.meta = meta
        item.unlocks = unlocks.get(item.course, [])
        item.prereqs_detail = []
        if meta:
            for p in meta.prerequisites:
                p_item = next((i for i in items if i.course == p), None)
                item.prereqs_detail.append({
                    "name": p,
                    "met": bool(p_item and p_item.status == "completed"),
                })
        item.already_known = item.course in known_skills and item.status != "completed"

        rec = rec_map.get(item.course)
        item.recommendation_id = rec.id if rec else None
        item.current_feedback = feedback_map.get(rec.id).feedback if rec and rec.id in feedback_map else None

    stages = [{"name": s, "items": [i for i in items if i.stage == s]} for s in seen_stages]

    action = next_best_action(path)
    feedback_form = PathFeedbackForm()

    context = {
        "profile": profile,
        "path": path,
        "stages": stages,
        "next_action": action,
        "readiness": readiness_percent(path),
        "current_stage": action.stage if action else (items[-1].stage if items else ""),
        "feedback_form": feedback_form,
        "feedback_reason_choices": RecommendationFeedback.REASON_CHOICES,
    }
    return render(request, "pathway/path.html", context)


@login_required
def mark_item(request):
    profile = _owned_profile_or_none(request)
    if not profile:
        return redirect("profiles:onboarding")
    if request.method != "POST":
        return redirect("pathway:path")

    item_id = request.POST.get("item_id")
    action = request.POST.get("action")
    item = get_object_or_404(LearningPathItem, id=item_id, path__profile=profile)

    if action == "complete":
        LearningHistoryEntry.objects.update_or_create(
            profile=profile, course=item.course, defaults={"status": "completed"}
        )
        reason = f"You marked \"{item.course}\" as completed."

        stage_siblings = list(item.path.items.filter(stage=item.stage).exclude(id=item.id))
        stage_now_done = all(s.status == "completed" for s in stage_siblings)
        all_siblings = list(item.path.items.exclude(id=item.id))
        path_now_done = all(s.status == "completed" for s in all_siblings)

        query_text = _query_text_for(profile)
        generate_path(profile, query_text, reason=reason)

        if path_now_done and all_siblings:
            messages.success(request, "🏆 You completed every step in this path!", extra_tags="celebrate")
        elif stage_now_done and stage_siblings:
            messages.success(request, f"🎉 You've unlocked {item.stage}!", extra_tags="celebrate")
        else:
            messages.success(request, "Your path was updated.")
        return redirect("pathway:path")

    elif action == "skip":
        LearningHistoryEntry.objects.update_or_create(
            profile=profile, course=item.course, defaults={"status": "skipped"}
        )
        reason = f"You skipped \"{item.course}\"."
    else:
        messages.error(request, "Unrecognized action.")
        return redirect("pathway:path")

    query_text = _query_text_for(profile)
    generate_path(profile, query_text, reason=reason)
    messages.success(request, "Your path was updated.")
    return redirect("pathway:path")


@login_required
def change_path(request):
    profile = _owned_profile_or_none(request)
    if not profile:
        return redirect("profiles:onboarding")

    if request.method != "POST":
        return redirect("pathway:path")

    form = PathFeedbackForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Pick at least one thing you'd like to change.")
        return redirect("pathway:path")

    selected = form.cleaned_data["changes"]
    labels = dict(form.fields["changes"].choices)

    levels = ["beginner", "intermediate", "advanced"]
    if "faster_path" in selected and profile.experience_level != "advanced":
        profile.experience_level = levels[min(levels.index(profile.experience_level) + 1, 2)]
        profile.save(update_fields=["experience_level"])
    if "slower_path" in selected and profile.experience_level != "beginner":
        profile.experience_level = levels[max(levels.index(profile.experience_level) - 1, 0)]
        profile.save(update_fields=["experience_level"])

    for key, domain in _FOCUS_DOMAIN.items():
        if key in selected:
            from apps.profiles.models import LearnerInterest

            LearnerInterest.objects.get_or_create(profile=profile, label=domain)

    reason_text = "You asked to change your path: " + ", ".join(labels[c] for c in selected) + "."
    if "more_projects" in selected or "less_theory" in selected:
        reason_text += (
            " Note: the current dataset has no project-type resources, so this "
            "preference is recorded but can't change the resource mix yet."
        )

    query_text = _query_text_for(profile)
    generate_path(profile, query_text, reason=reason_text)
    messages.success(request, "Your path was updated.")
    return redirect("pathway:path")


@login_required
def history(request):
    profile = _owned_profile_or_none(request)
    if not profile:
        return redirect("profiles:onboarding")

    paths = list(profile.paths.prefetch_related("items").order_by("-version"))
    events = list(PathChangeEvent.objects.filter(profile=profile))


    enriched = []
    for i, path in enumerate(paths):
        courses_now = {item.course for item in path.items.all()}
        older = paths[i + 1] if i + 1 < len(paths) else None
        courses_before = {item.course for item in older.items.all()} if older else set()
        added = sorted(courses_now - courses_before)
        removed = sorted(courses_before - courses_now)
        enriched.append({"path": path, "added": added, "removed": removed})

    comparison = None
    from_v = request.GET.get("from")
    to_v = request.GET.get("to")
    if from_v and to_v:
        from_path = next((p for p in paths if str(p.version) == from_v), None)
        to_path = next((p for p in paths if str(p.version) == to_v), None)
        if from_path and to_path and from_path.id != to_path.id:
            from_courses = {item.course: item for item in from_path.items.all()}
            to_courses = {item.course: item for item in to_path.items.all()}
            added = sorted(set(to_courses) - set(from_courses))
            removed = sorted(set(from_courses) - set(to_courses))
            common = set(from_courses) & set(to_courses)
            changed_stage = sorted(
                c for c in common if from_courses[c].stage != to_courses[c].stage
            )
            comparison = {
                "from_path": from_path,
                "to_path": to_path,
                "added": added,
                "removed": removed,
                "changed_stage": [
                    {"course": c, "from_stage": from_courses[c].stage, "to_stage": to_courses[c].stage}
                    for c in changed_stage
                ],
            }

    return render(request, "pathway/history.html", {
        "paths": enriched,
        "events": events,
        "all_versions": [p.version for p in paths],
        "comparison": comparison,
        "from_v": from_v,
        "to_v": to_v,
    })


@login_required
def diagnostics(request):
    profile = _owned_profile_or_none(request)
    if not profile:
        return JsonResponse({"error": "No profile yet."}, status=400)

    path = get_current_path(profile)
    if not path:
        return JsonResponse({"error": "No path yet."}, status=400)

    metadata = load_course_metadata()
    primary_domain = determine_primary_domain(profile)
    relevant = relevant_domains(primary_domain)

    known_skills = list(profile.skills.filter(evidence_level="known").values_list("skill", flat=True))
    covered = set(profile.history.filter(status="completed").values_list("course", flat=True))

    items = list(path.items.all())
    selected = []
    for item in items:
        meta = metadata.get(item.course)
        selected.append({
            "course": item.course,
            "domain": meta.domain if meta else None,
            "stage": item.stage,
            "status": item.status,
            "match_score": round(item.match_score, 4),
            "reason": item.reason,
        })


    included_courses = {i.course for i in items}
    rejected = []
    for course, meta in metadata.items():
        if course in included_courses:
            continue
        if course in covered:
            continue
        in_scope = (
            relevant is None
            or meta.domain in {"Programming Foundations", "Math Foundations", "Developer Tools", "Databases"}
            or meta.domain in (relevant or set())
            or meta.domain in set(profile.interests.values_list("label", flat=True))
        )
        rejected.append({
            "course": course,
            "domain": meta.domain,
            "reason": "OUT_OF_DOMAIN" if not in_scope else "NOT_TOP_RANKED_FOR_STAGE",
        })

    validation = validate_path(path)

    return JsonResponse({
        "goal_text": profile.goal_text,
        "target_role": profile.target_role,
        "detected_primary_domain": primary_domain,
        "relevant_domains": sorted(relevant) if relevant else None,
        "known_skills": known_skills,
        "completed_history": sorted(covered),
        "path_version": path.version,
        "selected_items": selected,
        "rejected_sample": rejected[:30],
        "rejected_total": len(rejected),
        "validation": {
            "ok": validation.ok,
            "errors": validation.errors,
            "warnings": validation.warnings,
        },
    }, json_dumps_params={"indent": 2})
