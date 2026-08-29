from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import slugify

from apps.pathway.services.path_engine import get_current_path
from apps.recommender.ml.inference import get_engine
from apps.recommender.models import Recommendation, RecommendationFeedback
from apps.recommender.services.explainability import explain_recommendation
from apps.recommender.services.scoring import score_all_courses

from .models import LearnerProjectState, LearnerSavedResource
from .services.project_recommender import recommend_projects
from .services.projects import load_project_seed


def _find_course_by_slug(slug):
    engine = get_engine()
    for course in engine.all_courses:
        if slugify(course) == slug:
            return course
    return None


@login_required
def resource_detail(request, slug):
    course = _find_course_by_slug(slug)
    if not course:
        raise Http404()

    engine = get_engine()
    corpus = engine.get_course(course)
    meta = corpus.meta

    depends_on = meta.prerequisites
    required_by = [c for c, cc in engine.corpora.items() if course in cc.meta.prerequisites]

    context = {
        "course": course,
        "meta": meta,
        "review_count": corpus.review_count,
        "depends_on": depends_on,
        "required_by": required_by,
    }

    profile = getattr(request.user, "learner_profile", None)
    if profile:
        from apps.profiles.views import _query_text_for

        query_text = _query_text_for(profile)
        scores = {s.course: s for s in score_all_courses(profile, query_text)}
        score = scores.get(course)
        if score:
            context["why_recommended"] = explain_recommendation(score)
            context["match_score"] = round(score.total * 100)
            path = profile.paths.filter(is_current=True).first()
            if path:
                item = path.items.filter(course=course).first()
                context["path_status"] = item.status if item else None
                context["path_stage"] = item.stage if item else None
                context["item_id"] = item.id if item else None

        context["is_saved"] = LearnerSavedResource.objects.filter(profile=profile, course=course).exists()

        rec = Recommendation.objects.filter(profile=profile, course=course).first()
        context["recommendation_id"] = rec.id if rec else None
        if rec:
            fb = RecommendationFeedback.objects.filter(profile=profile, recommendation=rec).first()
            context["current_feedback"] = fb.feedback if fb else None
        context["feedback_reason_choices"] = RecommendationFeedback.REASON_CHOICES

    return render(request, "catalog/resource_detail.html", context)


@login_required
def toggle_save(request, slug):
    course = _find_course_by_slug(slug)
    if not course:
        raise Http404()
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")
    if request.method != "POST":
        return redirect("catalog:resource_detail", slug=slug)

    obj, created = LearnerSavedResource.objects.get_or_create(profile=profile, course=course)
    if not created:
        obj.delete()
        messages.success(request, f'Removed "{course}" from saved resources.')
    else:
        messages.success(request, f'Saved "{course}".')
    return redirect("catalog:resource_detail", slug=slug)


@login_required
def saved_resources(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")

    metadata_engine = get_engine()
    saved = list(profile.saved_resources.all())
    rows = []
    for s in saved:
        try:
            meta = metadata_engine.get_course(s.course).meta
        except Exception:
            meta = None
        rows.append({"course": s.course, "meta": meta, "saved_at": s.saved_at})

    return render(request, "catalog/saved_resources.html", {"rows": rows})


@login_required
def search(request):
    q = request.GET.get("q", "").strip()
    course_results = []
    project_results = []
    domain_results = []

    if q:
        q_lower = q.lower()
        engine = get_engine()
        for course in engine.all_courses:
            meta = engine.get_course(course).meta
            if q_lower in course.lower() or q_lower in meta.domain.lower():
                course_results.append({"course": course, "meta": meta})

        for p in load_project_seed():
            haystack = (p.title + " " + " ".join(p.skills) + " " + p.stage).lower()
            if q_lower in haystack:
                project_results.append(p)

        seen_domains = {c["meta"].domain for c in course_results}
        domain_results = sorted(seen_domains)

    return render(request, "catalog/search.html", {
        "q": q,
        "course_results": course_results[:20],
        "project_results": project_results[:10],
        "domain_results": domain_results,
    })


@login_required
def projects_list(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")

    path = get_current_path(profile)
    recommendations = recommend_projects(profile, path=path)
    states = {s.project_slug: s for s in profile.project_states.all()}


    by_stage = {}
    for rec in recommendations:
        by_stage.setdefault(rec.project.domain, []).append({
            "meta": rec.project,
            "locked": rec.status == "locked",
            "state": states.get(rec.project.slug),
            "reason": rec.reason,
            "readiness": rec.readiness,
            "missing_skills": rec.missing_skills,
        })

    completed_count = sum(1 for s in states.values() if s.status in ("completed", "published"))
    github_count = sum(1 for s in states.values() if s.github_url)
    unlocked_count = sum(1 for rec in recommendations if rec.status != "locked")

    return render(request, "catalog/projects.html", {
        "by_stage": by_stage,
        "completed_count": completed_count,
        "github_count": github_count,
        "total_count": len(recommendations),
        "unlocked_count": unlocked_count,
    })


@login_required
def project_action(request, slug):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")
    if request.method != "POST":
        return redirect("catalog:projects")

    projects = {p.slug: p for p in load_project_seed()}
    if slug not in projects:
        raise Http404()

    action = request.POST.get("action")
    state, _ = LearnerProjectState.objects.get_or_create(profile=profile, project_slug=slug)
    was_completed_before = state.status in ("completed", "published")

    if action == "start":
        state.status = "in_progress"
    elif action == "complete":
        state.status = "completed"
    elif action == "publish":
        state.status = "published"
        state.github_url = request.POST.get("github_url", "").strip()
        state.demo_url = request.POST.get("demo_url", "").strip()
    else:
        messages.error(request, "Unrecognized project action.")
        return redirect("catalog:projects")

    state.save()


    if action in ("complete", "publish") and not was_completed_before:
        from apps.profiles.models import LearnerSkillEvidence
        for skill in projects[slug].skills:
            existing = LearnerSkillEvidence.objects.filter(profile=profile, skill=skill).first()
            if existing and existing.evidence_level == "known":
                continue
            LearnerSkillEvidence.objects.update_or_create(
                profile=profile, skill=skill,
                defaults={"evidence_level": "inferred", "source": "project_completion"},
            )

        from apps.pathway.services.path_engine import generate_path
        from apps.profiles.views import _query_text_for
        query_text = _query_text_for(profile)
        generate_path(profile, query_text, reason=f'Completed project "{projects[slug].title}".')

    if action in ("complete", "publish"):
        emoji = "🏆" if action == "publish" else "🎉"
        messages.success(request, f'{emoji} "{projects[slug].title}" {state.get_status_display().lower()}.', extra_tags="celebrate")
    else:
        messages.success(request, f'"{projects[slug].title}" updated.')
    return redirect("catalog:projects")
