# Sequentia

AI-powered personalized learning-path recommender — built for the HCLTech
AMPlified Season 1, Round 2 challenge.

**Your goal. Your sequence. Your path.**

## What's built

The full core loop works end-to-end and is tested (93 automated tests):

```
Goal (free text) → Learner profile → Hybrid semantic scoring →
Prerequisite-aware sequencing → Explanation → Feedback → Path recalculation
```

Catalog: 96 canonical skills, 101 courses, 147 projects across 18 target
roles and 16 domains — run `python manage.py validate_catalog` for the
live, measured numbers (never hand-typed into this README).

### ML / NLP layer (`apps/recommender/ml/`, `apps/profiles/services/extraction.py`)

- **All ranking, scoring, and path sequencing is NLP/DL/ML — never an API
  call.** Course ranking is a hybrid of TF-IDF (exact/technical-term
  precision) and Word2Vec (synonym/concept recall) — the Word2Vec model is
  **trained on this project's own 109,776 reviews**, not a generic
  pretrained model. That choice wasn't arbitrary: the first attempt used a
  generic pretrained GloVe model (spaCy's `en_core_web_md`) and it silently
  failed on domain jargon — "kubernetes", "pytorch", "django" aren't well
  represented in general-English vector tables, so queries about them
  returned nothing. Training on the review corpus itself guarantees every
  term a learner's goal might mention is covered, and the model genuinely
  learns domain relationships (kubernetes ↔ docker ↔ orchestration ↔
  deployment) that a generic corpus wouldn't. Artifacts are trained once
  (`python manage.py train_embeddings`, ~30s) and persisted to
  `data/artifacts/` — loaded in ~1s per process after that, not retrained
  per request or per server start.
- **Goal/interest/skill extraction**: spaCy's real dependency parser, not
  regex. Sentence-level intent ("known" vs "interested") is detected from
  verb lemmas anywhere in the sentence (handles conjuncts and copula
  constructions like "I'm interested in X"), with explicit negation
  handling via spaCy's `neg` dependency ("I don't know React" is correctly
  NOT marked known). Exact course mentions under a "known" cue get
  whole-sentence substring matching. Interest phrases get grounded against
  real domain vocabulary via the same Word2Vec model.
- **Skill graph** (`apps/recommender/ml/skills.py`): a hand-curated,
  validated dependency graph (96 skills, cycle-checked, every edge
  reference-checked) — not inferred. Every project's `prerequisite_skill_ids`
  / `demonstrates_skill_ids` are *derived* from this graph, not hand-typed.
- **The AI Mentor coach is grounded ML output, optionally phrased by
  Gemini** — see the dedicated section below. Gemini, when configured,
  never sees raw catalog data and never computes a score, rank, or
  recommendation; it only rewords a fact string the rule-based engine
  already produced. With no `GEMINI_API_KEY` set, the coach is 100%
  rule-based and works identically, just less conversationally worded.

### AI Mentor coach (`apps/coach/`)

Two-layer design, in this order:
1. **Grounding (`services/coach.py`, always runs)** — a deterministic,
   keyword-intent matcher answers strictly from the learner's own computed
   state: their current path, scores, blocked-reason strings, and path-change
   history. It cannot invent a course, score, or reason that scoring.py /
   explainability.py didn't already produce. Off-topic questions get an
   explicit "I can only answer path/recommendation questions" refusal —
   never a guess from general knowledge.
2. **Phrasing (`services/gemini_client.py`, optional)** — if
   `GEMINI_API_KEY` is set, the grounded answer from step 1 is passed to
   Gemini as a FACTS block with a system prompt that forbids stating
   anything not in that block, forbids small talk/opinions/general
   knowledge, and caps the reply at 2-4 sentences. If the key is unset, the
   call fails, or the SDK isn't installed, `phrase_grounded_answer()`
   returns `None` and the original grounded text is returned unchanged —
   the mentor never breaks or goes silent because of Gemini.

This keeps the "no external API required for core intelligence" property
exactly true: turn Gemini off and every recommendation, score, and path
decision is byte-for-byte identical — only the coach's phrasing changes.

### Everything else

- **Auth**: register (auto-login), login, logout, password reset — all via
  `request.user`, no client-supplied IDs anywhere
- **Recommendation engine** (`apps/recommender/services/scoring.py`): combines
  semantic relevance, interest alignment, skill-gap, prerequisite readiness,
  difficulty fit, and past feedback into one configurable score per course
- **Path engine** (`apps/pathway/services/path_engine.py`,
  `apps/pathway/services/domain.py`): stages are generated dynamically per
  learner from a curated domain-adjacency table, not a fixed universal
  sequence — a Security-goal path shows Security (+ always-eligible
  Foundations), not Security+Cloud+DevOps+Systems just because those domains
  touch it somewhere. Blocks anything with unmet prerequisites, and always
  picks exactly one "current" next-best-action.
- **Explainability**: every recommendation and every blocked item has a
  reason string generated from the actual scoring components
- **Path versioning & history**: every regeneration is a new `LearningPath`
  version; the History page shows an added/removed course diff per version
- **Pages**: Landing (public marketing page — hero, how-it-works, CTAs),
  Dashboard (with a horizontal resource carousel), Path (stage timeline with
  completed/current/upcoming/blocked cards + Ask Assistant), Skills, Path
  History (expandable version cards with real diffs), Resource detail,
  Profile (skill evidence, quick stats, editing goal/experience triggers path
  recalculation)
- **Navigation**: icon sidebar on desktop, bottom tab bar on mobile
- **Styling**: compiled Tailwind CSS (v3, built via `npm run build-css`), not
  the CDN script — the CDN version isn't recommended for production and adds
  an external dependency at page-load time
- **"Change my path?"** feedback panel and per-recommendation helpful/
  not-helpful feedback, both feeding into the next path generation
- **Security**: 93 automated tests, including cross-user isolation
- **Deployment**: `render.yaml` + `Procfile` for Render (Gunicorn + managed
  PostgreSQL + WhiteNoise + auto-generated `SECRET_KEY`)

## Honest limitations (not fabricated, by design)

- **21 of 101 courses have no real review data.** They were added for
  catalog/skill-graph/project coverage (Security, Blockchain, Systems,
  MLOps, Developer Tools domains) ahead of collecting real usage data — a
  normal state for a growing catalog, not hidden. They don't participate in
  TF-IDF/Word2Vec semantic scoring (`build_course_corpora` deliberately
  excludes them rather than training on fabricated review text); they still
  work fully for skill-graph, prerequisite, and project-readiness logic.
  Run `python manage.py validate_catalog` to see the exact list.
- **No review-quality/sentiment signal** — `train.csv` has no ratings and no
  labeled sentiment. A small ratings-labeled subset of reviews would unlock a
  genuine review-quality ranking component.
- **Course and project metadata is manually curated**
  in `data/course_metadata_seed.csv` / `data/project_seed.csv`, not derived
  from the dataset. Edit it freely — the whole engine reads from it live (run
  `python manage.py train_embeddings` again after editing course metadata,
  since it affects the course documents the model trains on).
- **The AI Mentor's core intelligence is rule-based, not an LLM** — Gemini
  (when configured) only rephrases already-computed grounded facts; see the
  AI Mentor section above. This keeps "no external API required for core
  intelligence" true regardless of whether `GEMINI_API_KEY` is set.
- **Word2Vec is trained on a modest corpus** (~1,500-word vocabulary after
  TF-IDF filtering, over the 80 review-backed courses). It works well for
  this catalog's actual vocabulary but won't generalize to topics genuinely
  absent from those reviews.
- **spaCy's noun-chunk extraction under-segments** multi-clause sentences
  occasionally (e.g. "I completed X and want to move into Y" can have the Y
  clause absorbed into the "known" intent of the earlier clause rather than
  read as a separate interest signal) — a clause-level rather than
  sentence-level intent scope would fix this; not implemented given time.

## Local setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then edit SECRET_KEY etc.
python manage.py migrate
python manage.py train_embeddings   # first-time only — trains + saves ML artifacts
python manage.py validate_catalog   # optional — prints measured catalog stats
python manage.py runserver
```

`GEMINI_API_KEY` in `.env` is optional — leave it blank to run the AI Mentor
fully rule-based/offline (see the AI Mentor section above).

Styling is a compiled Tailwind CSS build (`static/css/tailwind.css`), not the
CDN `<script>` tag — the CDN script isn't meant for production use and adds
an external network dependency. `static/css/tailwind.css` is already built
and committed, so nothing extra is needed to run the app. If you edit any
template's classes, rebuild it:

```bash
npm install          # first time only — needs Node.js
npm run build-css
```

(`train_embeddings` runs automatically on first access if you skip that step,
but running it explicitly avoids a ~40s delay on your first request.)

## Running tests

```bash
python manage.py test apps
```

93 tests: catalog/skill-graph validation (cycles, orphans, dangling
references), metadata/data validation, hybrid relevance ranking, spaCy-based
extraction (including negation), onboarding flow, path generation/versioning,
prerequisite/demonstrates skill derivation, AI Mentor grounding+fallback, and
cross-user security isolation.

## Deploying to Render

1. Push this repo to GitHub — `data/artifacts/` (the trained ML artifacts,
   ~2MB) should be committed so Render doesn't need to retrain on deploy.
2. In Render, "New +" → "Blueprint" → point at the repo. `render.yaml`
   provisions a free PostgreSQL database and a web service, auto-generates
   `SECRET_KEY`, and runs migrations on release.
3. `EMAIL_BACKEND` defaults to console (password reset emails go to Render's
   logs) — set real SMTP env vars if you need real delivery for the demo.

## Architecture notes

- **No separate Resource/Skill/Project DB tables.** Course/skill/project
  metadata is read live from `data/course_metadata_seed.csv` +
  `data/skill_vocabulary_seed.csv` + `data/project_seed.csv` +
  `data/train.csv` through the ML layer, not duplicated into the database.
  Only per-user state (profile, path, feedback, history) is persisted.
- **Stage taxonomy is dynamic, not fixed.** `apps/pathway/services/domain.py`
  determines each learner's relevant domains from their goal text via a
  curated keyword table + a hand-audited domain-adjacency map, and
  `path_engine.py` generates stage names from whatever domains are actually
  relevant to *that* learner — a Web Development path never shows Machine
  Learning stages, a Security path never shows Cloud/DevOps stages.
- **Skill graph vs. course/project schema.** `apps/recommender/ml/skills.py`
  is the canonical skill vocabulary (parent/prerequisite edges, cycle-
  checked). Courses and projects still key off course *names* internally
  (not skill ids) for backward compatibility with existing learner data —
  `ProjectMeta.demonstrates_skill_ids` / `prerequisite_skill_ids` are derived
  read-only fields computed from that graph, not a live schema migration.

## What would most improve accuracy right now

If you can source more data, in priority order:
1. **Real review data for the 21 courses without any** — unlocks semantic
   scoring for those courses (currently catalog/path-eligible but excluded
   from ranking; see Honest limitations above).
2. **A few hundred rated reviews** (1-5 stars) — unlocks a real review-quality
   ranking signal instead of omitting it.
3. **A larger/more diverse review corpus** — the current Word2Vec vocabulary
   is ~1,500 words after filtering; more review text would let the model
   learn richer relationships.

## Acceptance checklist (from the original brief)

- [x] Django app starts locally
- [x] PostgreSQL supported (SQLite for local dev)
- [x] Registration / login / logout work
- [x] Password reset architecture works
- [x] Authenticated learner data is private (tested)
- [x] Conversational onboarding works
- [x] Goal/interest/known-skill extraction works (spaCy dependency parsing + Word2Vec)
- [x] Learner profile persists
- [x] train.csv integrated correctly
- [x] HclAmd.ipynb logic integrated correctly (TF-IDF reused, dedup trick dropped)
- [x] ML inference works (hybrid TF-IDF + domain-trained Word2Vec)
- [x] Recommendation engine works
- [x] Path generator works
- [x] Prerequisite reasoning works
- [x] Next best action works
- [x] Project recommendations — 147 real projects across 18 roles
- [x] Resource recommendations work
- [x] Learning history influences recommendation
- [x] Feedback influences recommendation
- [x] Path versioning works
- [x] Path history works (with real diffs)
- [x] Path explanations work
- [x] Recommendation explanations work
- [x] AI assistant works (rule-based grounding, optional Gemini phrasing)
- [x] Dashboard works
- [x] Path page works
- [x] Skills page works
- [x] Resource detail works
- [x] Project details work
- [x] Landing page works
- [x] No hardcoded recommendation values / path sequence
- [x] No external API required for core intelligence (recommendations/
      scoring/path generation are 100% NLP/DL/ML; Gemini, if configured, only
      rephrases already-computed facts for the coach)
- [x] User data is secure (93 tests, including cross-user isolation)
- [x] render.yaml + Procfile present
- [x] Static files work in production (WhiteNoise, verified via collectstatic)
- [x] Database migrations work
- [x] Tests pass (93/93)
- [x] README complete
- [ ] Exhaustive mobile/desktop breakpoint testing — responsive classes are
      in place (sidebar → bottom tab bar, carousel, etc.) but not tested at
      every device size
