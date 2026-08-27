from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.pathway.services.path_engine import (
    DOMAIN_TO_STAGE,
    STAGE_ORDER,
    get_current_path,
    next_best_action,
    readiness_percent,
)
from apps.recommender.ml.metadata import load_course_metadata


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard:home")
    return render(request, "dashboard/landing.html")


def _greeting() -> str:
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _stage_summary(items):
    """Real per-stage rollup from actual path items — no fabricated percentages."""
    summary = []
    by_stage = {}
    for item in items:
        by_stage.setdefault(item.stage, []).append(item)

    for stage in STAGE_ORDER:
        stage_items = by_stage.get(stage)
        if not stage_items:
            continue
        completed = [i for i in stage_items if i.status == "completed"]
        current = [i for i in stage_items if i.status == "current"]
        if len(completed) == len(stage_items):
            state = "done"
        elif current:
            state = "current"
        elif any(i.status == "upcoming" for i in stage_items):
            state = "available"
        else:
            state = "locked"
        summary.append({
            "name": stage,
            "state": state,
            "completed": len(completed),
            "total": len(stage_items),
            "items": stage_items,
        })
    return summary


@login_required
def home(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")

    path = get_current_path(profile)
    if not path:
        return redirect("pathway:path")

    action = next_best_action(path)
    items = list(path.items.all())
    upcoming = [i for i in items if i.status == "upcoming"][:8]
    completed_count = sum(1 for i in items if i.status == "completed")

    action_meta = None
    if action:
        metadata = load_course_metadata()
        action_meta = metadata.get(action.course)

    context = {
        "profile": profile,
        "path": path,
        "greeting": _greeting(),
        "readiness": readiness_percent(path),
        "current_stage": action.stage if action else "",
        "next_action": action,
        "next_action_meta": action_meta,
        "upcoming": upcoming,
        "total_items": len(items),
        "completed_count": completed_count,
        "stage_summary": _stage_summary(items),
    }
    return render(request, "dashboard/home.html", context)


def _domain_breakdown(items):
    """
    Real per-domain readiness: completed / total path items in that domain.
    Grounded in apps.recommender.ml.metadata (the real course->domain map),
    not a fabricated competency score.
    """
    metadata = load_course_metadata()
    by_domain = {}
    for item in items:
        meta = metadata.get(item.course)
        domain = meta.domain if meta else "Other"
        by_domain.setdefault(domain, []).append(item)

    rows = []
    for domain, domain_items in by_domain.items():
        completed = sum(1 for i in domain_items if i.status == "completed")
        total = len(domain_items)
        pct = round(100 * completed / total) if total else 0
        rows.append({"domain": domain, "completed": completed, "total": total, "pct": pct})
    rows.sort(key=lambda r: r["pct"], reverse=True)
    return rows


@login_required
def readiness(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")

    path = get_current_path(profile)
    if not path:
        return redirect("pathway:path")

    items = list(path.items.all())
    domains = _domain_breakdown(items)
    action = next_best_action(path)

    strongest = next((d for d in domains if d["total"] >= 2), None)
    gap = next((d for d in reversed(domains) if d["total"] >= 2), None)

    context = {
        "profile": profile,
        "readiness": readiness_percent(path),
        "domains": domains,
        "strongest": strongest,
        "gap": gap,
        "next_action": action,
    }
    return render(request, "dashboard/readiness.html", context)


@login_required
def toggle_internship_mode(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile or request.method != "POST":
        return redirect("dashboard:readiness")

    profile.internship_mode = not profile.internship_mode
    profile.save(update_fields=["internship_mode"])

    from apps.profiles.views import _query_text_for
    from apps.pathway.services.path_engine import generate_path

    query_text = _query_text_for(profile)
    reason = (
        "Internship Mode turned on — prioritizing portfolio-relevant courses."
        if profile.internship_mode
        else "Internship Mode turned off."
    )
    generate_path(profile, query_text, reason=reason)
    return redirect("dashboard:readiness")
