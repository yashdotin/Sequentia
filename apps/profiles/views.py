from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

from apps.pathway.services.path_engine import generate_path, readiness_percent
from apps.recommender.ml.feature_builder import build_query_text
from apps.recommender.ml.metadata import load_course_metadata
from apps.recommender.services.scoring import score_all_courses

from .models import LearnerInterest, LearnerProfile, LearnerSkillEvidence
from .forms import OnboardingForm, ProfileEditForm
from .services.extraction import extract_from_text


def _query_text_for(profile: LearnerProfile) -> str:
    interests = ", ".join(i.label for i in profile.interests.all())
    known = ", ".join(
        e.skill for e in profile.skills.filter(evidence_level__in=["known", "inferred"])
    )
    return build_query_text(goal=profile.goal_text, interests=interests, known_areas=known)


def _apply_extraction(profile: LearnerProfile) -> None:
    extraction = extract_from_text(profile.goal_text)
    if extraction.target_role and not profile.target_role:
        profile.target_role = extraction.target_role
        profile.save(update_fields=["target_role"])

    for domain in extraction.inferred_interests:
        LearnerInterest.objects.get_or_create(profile=profile, label=domain)

    for skill in extraction.known_skills:
        LearnerSkillEvidence.objects.update_or_create(
            profile=profile,
            skill=skill,
            defaults={"evidence_level": "known", "source": "onboarding_text"},
        )


def _apply_picked_skills_and_interests(profile: LearnerProfile, known_skills: str, interests: str) -> None:
    metadata = load_course_metadata()
    valid_courses = set(metadata.keys())
    valid_domains = {m.domain for m in metadata.values()}

    for skill in [s.strip() for s in known_skills.split(",") if s.strip()]:
        if skill in valid_courses:
            LearnerSkillEvidence.objects.update_or_create(
                profile=profile,
                skill=skill,
                defaults={"evidence_level": "known", "source": "onboarding_picker"},
            )

    for label in [i.strip() for i in interests.split(",") if i.strip()]:
        if label in valid_domains:
            LearnerInterest.objects.get_or_create(profile=profile, label=label)


@login_required
def onboarding(request):
    if hasattr(request.user, "learner_profile"):
        return redirect("pathway:path")

    if request.method == "POST":
        form = OnboardingForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data["destination_role"].strip()
            extra = form.cleaned_data["extra_context"].strip()

            goal_parts = []
            if role:
                article = "an" if role[:1].lower() in "aeiou" else "a"
                goal_parts.append(f"I want to become {article} {role}.")
            if extra:
                goal_parts.append(extra)
            goal_text = " ".join(goal_parts) or f"Learning path for {request.user.username}."

            with transaction.atomic():
                profile = LearnerProfile.objects.create(
                    user=request.user,
                    goal_text=goal_text,
                    target_role=role,
                    experience_level=form.cleaned_data["experience_level"],
                )
                _apply_picked_skills_and_interests(
                    profile,
                    form.cleaned_data["known_skills"],
                    form.cleaned_data["interests"],
                )
                _apply_extraction(profile)
                query_text = _query_text_for(profile)
                generate_path(profile, query_text, reason="Initial path generated from onboarding.")
            messages.success(request, "Your path is ready.")
            return redirect("pathway:path")
    else:
        form = OnboardingForm()

    metadata = load_course_metadata()
    skill_options = sorted(metadata.keys())
    domain_options = sorted({m.domain for m in metadata.values()})

    return render(
        request,
        "profiles/onboarding.html",
        {"form": form, "skill_options": skill_options, "domain_options": domain_options},
    )


@login_required
def profile_edit(request):
    profile, _ = LearnerProfile.objects.get_or_create(
        user=request.user, defaults={"goal_text": ""}
    )
    old_goal = profile.goal_text
    old_experience = profile.experience_level

    if request.method == "POST":
        form = ProfileEditForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            _apply_extraction(profile)

            changes = []
            if profile.goal_text != old_goal:
                changes.append("your goal changed")
            if profile.experience_level != old_experience:
                changes.append("your experience level changed")
            reason = (
                "Your path was updated because " + " and ".join(changes) + "."
                if changes
                else "Profile updated."
            )

            query_text = _query_text_for(profile)
            generate_path(profile, query_text, reason=reason)
            messages.success(request, "Profile updated — your path was recalculated.")
            return redirect("pathway:path")
    else:
        form = ProfileEditForm(instance=profile)

    known_skills = profile.skills.filter(evidence_level="known").order_by("skill")
    inferred_skills = profile.skills.filter(evidence_level="inferred").order_by("skill")
    completed_count = profile.history.filter(status="completed").count()
    current_path = profile.paths.filter(is_current=True).first()

    context = {
        "form": form,
        "profile": profile,
        "known_skills": known_skills,
        "inferred_skills": inferred_skills,
        "completed_count": completed_count,
        "path_version": current_path.version if current_path else None,
        "readiness": readiness_percent(current_path) if current_path else 0,
    }
    return render(request, "profiles/profile.html", context)


@login_required
def skills(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")

    query_text = _query_text_for(profile)
    scores = score_all_courses(profile, query_text)

    def gap_label(skill_gap_score: float) -> str:
        if skill_gap_score > 0.8:
            return "Significant"
        if skill_gap_score > 0.3:
            return "Moderate"
        return "Small"

    def relevance_label(semantic_score: float) -> str:
        if semantic_score > 0.5:
            return "High"
        if semantic_score > 0.15:
            return "Moderate"
        return "Low"

    def evidence_label(course: str) -> str:
        entry = profile.skills.filter(skill=course).first()
        if entry:
            return entry.get_evidence_level_display()
        if profile.history.filter(course=course, status="completed").exists():
            return "Known — completed"
        return "Unknown — no evidence"

    rows = [
        {
            "course": s.course,
            "domain": s.meta.domain,
            "evidence": evidence_label(s.course),
            "target_relevance": relevance_label(s.components["semantic_relevance"]),
            "gap": gap_label(s.components["skill_gap"]),
        }
        for s in scores[:30]
    ]

    known_skills = list(
        profile.skills.filter(evidence_level="known").order_by("skill").values_list("skill", flat=True)
    )
    metadata = load_course_metadata()
    skill_options = sorted(metadata.keys())
    current_interests = list(profile.interests.order_by("label").values_list("label", flat=True))
    domain_options = sorted({m.domain for m in metadata.values()})

    return render(request, "profiles/skills.html", {
        "rows": rows, "profile": profile,
        "known_skills": known_skills, "skill_options": skill_options,
        "current_interests": current_interests, "domain_options": domain_options,
    })


@login_required
def update_known_skills(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")
    if request.method != "POST":
        return redirect("profiles:skills")

    action = request.POST.get("action")
    skill = request.POST.get("skill", "").strip()
    metadata = load_course_metadata()

    if skill not in metadata:
        messages.error(request, "That's not a recognized skill in the catalog.")
        return redirect("profiles:skills")

    if action == "add":
        LearnerSkillEvidence.objects.update_or_create(
            profile=profile, skill=skill,
            defaults={"evidence_level": "known", "source": "manual_skill_update"},
        )
        reason = f'You added "{skill}" as a known skill.'
    elif action == "remove":
        existing = LearnerSkillEvidence.objects.filter(profile=profile, skill=skill).first()
        if existing and existing.source in ("manual_skill_update", "onboarding_picker", "onboarding_text"):
            existing.delete()
        elif existing:
            messages.error(
                request,
                f'"{skill}" has evidence from {existing.get_source_display() if hasattr(existing, "get_source_display") else existing.source} '
                "and can't be removed here.",
            )
            return redirect("profiles:skills")
        reason = f'You removed "{skill}" from known skills.'
    else:
        messages.error(request, "Unrecognized skill action.")
        return redirect("profiles:skills")

    query_text = _query_text_for(profile)
    generate_path(profile, query_text, reason=reason)
    messages.success(request, "Your skills were updated — path recalculated.")
    return redirect("profiles:skills")


@login_required
def update_interests(request):
    profile = getattr(request.user, "learner_profile", None)
    if not profile:
        return redirect("profiles:onboarding")
    if request.method != "POST":
        return redirect("profiles:skills")

    action = request.POST.get("action")
    label = request.POST.get("interest", "").strip()
    metadata = load_course_metadata()
    valid_domains = {m.domain for m in metadata.values()}

    if label not in valid_domains:
        messages.error(request, "That's not a recognized interest category.")
        return redirect("profiles:skills")

    already_exists = LearnerInterest.objects.filter(profile=profile, label=label).exists()

    if action == "add":
        if already_exists:
            messages.success(request, f'"{label}" is already one of your interests.')
            return redirect("profiles:skills")
        LearnerInterest.objects.create(profile=profile, label=label)
        reason = f'Interest added: {label}.'
    elif action == "remove":
        if not already_exists:
            return redirect("profiles:skills")
        LearnerInterest.objects.filter(profile=profile, label=label).delete()
        reason = f'Interest removed: {label}.'
    else:
        messages.error(request, "Unrecognized interest action.")
        return redirect("profiles:skills")

    query_text = _query_text_for(profile)
    generate_path(profile, query_text, reason=reason)
    messages.success(request, "Your interests were updated — recommendations recalculated.")
    return redirect("profiles:skills")
