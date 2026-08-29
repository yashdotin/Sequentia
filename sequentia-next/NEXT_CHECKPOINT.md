# Sequentia — Canonical Catalog Checkpoint

This checkpoint adds a canonical skill/role layer without replacing the existing 80-course review corpus or 46-project catalog.

## New data

- `data/skill_seed.csv` — stable skill IDs, aliases, prerequisites, related skills, applicable roles.
- `data/role_seed.csv` — 24 supported target roles and required skill IDs.
- `data/course_skill_map.csv` — maps each existing course/resource to canonical skill IDs.

## Runtime changes

- `apps/recommender/ml/canonical.py` loads canonical skills, roles, and course mappings.
- `apps/recommender/ml/metadata.py` enriches each existing `CourseMeta` with canonical skills, prerequisite skill IDs, and target roles while keeping the old 5-column CSV contract valid.
- `apps/recommender/services/scoring.py` now scores against canonical skill evidence and gives an explicit target-role alignment signal.
- `apps/recommender/services/explainability.py` explains direct role alignment when present.
- `apps/catalog/services/catalog_validation.py` validates the data layer without depending on a nonexistent ML module.
- `apps/catalog/management/commands/validate_catalog.py` provides the management command.
- `config/settings.py` exposes optional paths for the new catalog files.

## Run

```powershell
python manage.py check
python manage.py migrate
python manage.py validate_catalog
python manage.py test
```

Do **not** retrain embeddings yet if `validate_catalog` reports data warnings only. Warnings are coverage gaps; critical errors are invalid references/cycles.

## What is intentionally preserved

- Existing UI/templates.
- Existing 80-course review corpus.
- Existing 46-project seed.
- Existing course-name history fields for backward compatibility.
- Existing goal/domain gating in the path engine.
- Existing project completion -> skill evidence -> path regeneration flow.

## Next checkpoint after this one

1. Split project skills into canonical `prerequisite_skill_ids` and `demonstrates_skill_ids` using a project-specific mapping.
2. Add explicit per-role course/project coverage reporting.
3. Add path coverage tests for zero/basic/intermediate/advanced learner evidence.
4. Only then retrain embeddings and tune ranking weights from real behavior.
