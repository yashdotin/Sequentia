"""Canonical-skill project recommendation and readiness."""
from __future__ import annotations
from dataclasses import dataclass, field
from apps.pathway.services.domain import FOUNDATION_DOMAINS, determine_primary_domain, relevant_domains
from apps.profiles.models import LearnerProfile
from apps.catalog.models import LearnerProjectState
from apps.catalog.services.projects import ProjectMeta, load_project_seed
from apps.recommender.ml.canonical import resolve_skill_ids, skill_display

WEIGHTS={"role_alignment":0.25,"goal_alignment":0.20,"readiness_margin":0.20,"current_path_relevance":0.10,"difficulty_fit":0.10,"portfolio_value":0.10,"interest_alignment":0.05}
_PORTFOLIO={"high":1.0,"medium":0.6,"low":0.3}
_DIFF={"beginner":0,"intermediate":1,"advanced":2}
_EXP={"beginner":0,"intermediate":1,"advanced":2,"expert":2}

@dataclass
class ProjectRecommendation:
    project:ProjectMeta; status:str; score:float; domain_match:bool; role_match:float; readiness:float; path_relevance:float=0.0; satisfied_skills:list[str]=field(default_factory=list); missing_skills:list[str]=field(default_factory=list); difficulty_fit:float=0.0; reason:str=""

def _canonical_evidence(profile):
    levels={"unknown":0,"inferred":1,"known":2}; evidence={}
    for e in profile.skills.all():
        value=e.skill.strip(); ids=resolve_skill_ids(value)
        if not ids: continue
        for sid in ids:
            prev=evidence.get(sid,"unknown")
            if levels.get(e.evidence_level,0)>levels.get(prev,0): evidence[sid]=e.evidence_level
    for course in profile.history.filter(status="completed").values_list("course",flat=True):
        for sid in resolve_skill_ids(course): evidence[sid]="known"
    return evidence

def _legacy_fallback_evidence(profile):
    return {e.skill:e.evidence_level for e in profile.skills.all()} | {c:"known" for c in profile.history.filter(status="completed").values_list("course",flat=True)}

def compute_readiness(profile: LearnerProfile, project: ProjectMeta):
    prereqs=project.prerequisite_skill_ids or project.required_skill_ids
    if not prereqs: prereqs=tuple(resolve_skill_ids(s)[0] for s in project.skills if resolve_skill_ids(s))
    if not prereqs: return 1.0,[],[]
    canonical=_canonical_evidence(profile); legacy=_legacy_fallback_evidence(profile)
    satisfied=[]; missing=[]
    for sid in prereqs:
        level=canonical.get(sid)
        if not level:
            level=legacy.get(skill_display(sid), legacy.get(sid,"unknown"))
        label=skill_display(sid)
        if level in ("known","inferred"): satisfied.append(label)
        else: missing.append(label)
    return len(satisfied)/len(prereqs),satisfied,missing

def _difficulty_fit(difficulty,experience):
    gap=abs(_DIFF.get(difficulty.lower(),1)-_EXP.get(experience,0)); return {0:1.0,1:0.6,2:0.25}.get(gap,0.1)

def _role_alignment(project,target_role):
    if not project.target_roles or not target_role:return 0.5
    t=target_role.strip().lower()
    return 1.0 if any(t==r.strip().lower() or t in r.strip().lower() or r.strip().lower() in t for r in project.target_roles) else 0.0

def _current_path_relevance(project,path):
    if path is None:return 0.0
    path_courses=set(path.items.filter(status__in=("current","upcoming","completed")).values_list("course",flat=True))
    if not path_courses:return 0.0
    legacy=set(project.skills); return sum(1 for s in legacy if s in path_courses)/len(legacy) if legacy else 0.0

def _interest_alignment(project,primary_domain,interests):
    return 0.0 if project.domain==primary_domain else (1.0 if project.domain in interests else 0.0)

def recommend_projects(profile:LearnerProfile,path=None,limit=None):
    projects=load_project_seed(); states={s.project_slug:s for s in profile.project_states.all()}
    primary=determine_primary_domain(profile); relevant=relevant_domains(primary); interests=set(profile.interests.values_list("label",flat=True))
    def in_scope(domain):
        return True if relevant is None else domain in FOUNDATION_DOMAINS or domain in relevant or domain in interests
    out=[]
    for p in projects:
        readiness,satisfied,missing=compute_readiness(profile,p); role=_role_alignment(p,profile.target_role or ""); domain=in_scope(p.domain); path_rel=_current_path_relevance(p,path); diff=_difficulty_fit(p.difficulty,profile.experience_level); portfolio=_PORTFOLIO.get(p.portfolio_value.lower(),0.5); goal=1.0 if domain and p.domain==primary else (0.6 if domain else 0.0); interest=_interest_alignment(p,primary,interests)
        state=states.get(p.slug); status=state.status if state and state.status in ("completed","published") else ("recommended" if readiness>=1.0 and domain else "locked")
        score=WEIGHTS["role_alignment"]*role+WEIGHTS["goal_alignment"]*goal+WEIGHTS["readiness_margin"]*readiness+WEIGHTS["current_path_relevance"]*path_rel+WEIGHTS["difficulty_fit"]*diff+WEIGHTS["portfolio_value"]*portfolio+WEIGHTS["interest_alignment"]*interest
        if not domain: reason=f"Outside your current target domain ({p.domain})."
        elif readiness<1.0: reason=f"Locked — still missing: {', '.join(missing)}."
        else: reason=f"Unlocked — ready to practice {', '.join(satisfied) if satisfied else 'the required skills'}."
        out.append(ProjectRecommendation(p,status,round(score,4),domain,role,round(readiness,4),round(path_rel,4),satisfied,missing,diff,reason))
    out.sort(key=lambda r:(r.status=="recommended",r.score),reverse=True)
    return out[:limit] if limit else out
