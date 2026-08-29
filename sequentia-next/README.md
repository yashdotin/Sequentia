# Sequentia

AI-powered personalized learning-path recommender — built for the HCLTech
AMPlified Season 1, Round 2 challenge.

**Your goal. Your sequence. Your path.**

## What's built

The full core loop works end-to-end and is tested (30 automated tests):

```
Goal (free text) → Learner profile → Hybrid semantic scoring →
Prerequisite-aware sequencing → Explanation → Feedback → Path recalculation
```

### ML / NLP layer (`apps/recommender/ml/`, `apps/profiles/services/extraction.py`)

- **Course ranking**: a hybrid of TF-IDF (exact/technical-term precision) and
  Word2Vec (synonym/concept recall) — the Word2Vec model is **trained on this
  project's own 109,776 reviews**, not a generic pretrained model. That choice
  wasn't arbitrary: the first attempt used a generic pretrained GloVe model
  (spaCy's `en_core_web_md`) and it silently failed on domain jargon —
  "kubernetes", "pytorch", "django" aren't well-represented in general-English
  vector tables, so queries about them returned nothing. Training on the
  review corpus itself guarantees every term a learner's goal might mention is
  covered, and the model genuinely learns domain relationships (kubernetes ↔
  docker ↔ orchestration ↔ deployment) that a generic corpus wouldn't.
  Artifacts are trained once (`python manage.py train_embeddings`, ~40s) and
  persisted to `data/artifacts/` (~2MB) — loaded in ~1s per process after
  that, not retrained per request or per server start.
- **Goal/interest/skill extraction**: spaCy's real dependency parser, not
  regex. Sentence-level intent ("known" vs "interested") is detected from verb
  lemmas anywhere in the sentence (handles conjuncts and copula constructions
  like "I'm interested in X"), with explicit negation handling via spaCy's
  `neg` dependency ("I don't know React" is correctly NOT marked known).
  Exact course mentions under a "known" cue get whole-sentence substring
  matching (spaCy's noun-chunker splits multi-word course names like "SQL for
  Beginners" at the preposition, so chunk-level exact matching would miss
  them). Interest phrases get grounded against real domain vocabulary via the
  same Word2Vec model, so "I love container orchestration" correctly infers
  the DevOps domain with no hardcoded keyword for that phrasing.
- **Why not a local LLM**: considered and deliberately not used for core
  intelligence. A real local model (even a small quantized Llama) needs
  meaningful RAM and adds multi-second latency per request — real risk for a
  live hackathon demo and for free-tier hosting RAM limits. The AI coach
  stays rule-based and instant; an LLM could be added later purely to
  rephrase the (already-grounded) rule-based answer more conversationally,
  without it ever generating the substantive content itself.

### Everything else

- **Auth**: register (auto-login), login, logout, password reset — all via
  `request.user`, no client-supplied IDs anywhere
- **Recommendation engine** (`apps/recommender/services/scoring.py`): combines
  semantic relevance, interest alignment, skill-gap, prerequisite readiness,
  difficulty fit, and past feedback into one configurable score per course
- **Path engine** (`apps/pathway/services/path_engine.py`): stages courses
  into Foundations → Core Skills → Machine Learning → Deep Learning →
  Production → Specialization, blocks anything with unmet prerequisites, and
  always picks exactly one "current" next-best-action
- **Explainability**: every recommendation and every blocked item has a
  reason string generated from the actual scoring components
- **Path versioning & history**: every regeneration is a new `LearningPath`
  version; the History page shows an added/removed course diff per version
- **AI coach** (`apps/coach/`): rule-based, grounded only in the learner's own
  backend state — refuses general teaching questions outside path scope
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
- **Security**: 30 automated tests, including cross-user isolation
- **Deployment**: `render.yaml` + `Procfile` for Render (Gunicorn + managed
  PostgreSQL + WhiteNoise + auto-generated `SECRET_KEY`)

## Honest limitations (not fabricated, by design)

- **No project-type resources.** `train.csv` is 100% course reviews — no
  project data exists anywhere in the source material. The schema supports
  `resource_type="project"` but nothing populates it. **This is the single
  highest-value dataset addition** — send a `projects.csv` (title, difficulty,
  skills, prerequisites, estimated hours, portfolio value) and Phase 8 lights
  up for real.
- **No review-quality/sentiment signal** — `train.csv` has no ratings and no
  labeled sentiment. A small ratings-labeled subset of reviews would unlock a
  genuine review-quality ranking component.
- **Course metadata (domain/difficulty/prerequisites) is manually curated**
  in `data/course_metadata_seed.csv`, not derived from the dataset. Edit it
  freely — the whole engine reads from it live (run
  `python manage.py train_embeddings` again after editing, since it affects
  the course documents the model trains on).
- **The AI coach is rule-based**, not an LLM, per the brief's "no external API
  required for core intelligence" rule and the demo-reliability trade-off
  discussed above.
- **Word2Vec is trained on a modest corpus** (~1,500-word vocabulary after
  TF-IDF filtering). It works well for this catalog's actual vocabulary but
  won't generalize to topics genuinely absent from the 80 courses' reviews.
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
python manage.py runserver
```

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

30 tests: metadata/data validation, hybrid relevance ranking, spaCy-based
extraction (including negation), onboarding flow, path generation/versioning,
and cross-user security isolation.

## Deploying to Render

1. Push this repo to GitHub — `data/artifacts/` (the trained ML artifacts,
   ~2MB) should be committed so Render doesn't need to retrain on deploy.
2. In Render, "New +" → "Blueprint" → point at the repo. `render.yaml`
   provisions a free PostgreSQL database and a web service, auto-generates
   `SECRET_KEY`, and runs migrations on release.
3. `EMAIL_BACKEND` defaults to console (password reset emails go to Render's
   logs) — set real SMTP env vars if you need real delivery for the demo.

## Architecture notes

- **No separate Resource/Skill/Project DB tables.** Course metadata is read
  live from `data/course_metadata_seed.csv` + `data/train.csv` through the ML
  layer, not duplicated into the database. Only per-user state (profile,
  path, feedback, history) is persisted.
- **Stage taxonomy** (Foundations/Core Skills/Machine Learning/Deep
  Learning/Production/Specialization) is a manual domain→stage mapping in
  `path_engine.py` — a curated design decision, not derived from data.

## What would most improve accuracy right now

If you can source more data, in priority order:
1. **A projects dataset** — closes the biggest functional gap (zero project
   recommendations currently).
2. **A few hundred rated reviews** (1-5 stars) — unlocks a real review-quality
   ranking signal instead of omitting it.
3. **A larger/more diverse review corpus** — the current Word2Vec vocabulary
   is ~1,500 words after filtering; more review text (even for the same 80
   courses) would let the model learn richer relationships.

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
- [ ] Project recommendations — schema supports it, no project data exists
- [x] Resource recommendations work
- [x] Learning history influences recommendation
- [x] Feedback influences recommendation
- [x] Path versioning works
- [x] Path history works (with real diffs)
- [x] Path explanations work
- [x] Recommendation explanations work
- [x] AI assistant works (rule-based, grounded)
- [x] Dashboard works
- [x] Path page works
- [x] Skills page works
- [x] Resource detail works
- [ ] Project details — no project data
- [x] Landing page works
- [x] No hardcoded recommendation values / path sequence
- [x] No external API required for core intelligence
- [x] User data is secure (30 tests, including cross-user isolation)
- [x] render.yaml + Procfile present
- [x] Static files work in production (WhiteNoise, verified via collectstatic)
- [x] Database migrations work
- [x] Tests pass (30/30)
- [x] README complete
- [ ] Exhaustive mobile/desktop breakpoint testing — responsive classes are
      in place (sidebar → bottom tab bar, carousel, etc.) but not tested at
      every device size
