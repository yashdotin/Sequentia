#  SEQUENTIA

### Your Goal. Your Sequence. Your Path.

**Sequentia is an AI-powered personalized learning-path recommender that goes beyond ranking courses — it decides what a learner should learn next, and explains why.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Sequentia-111827?style=for-the-badge)](https://sequentia-igzm.onrender.com/)
[![Django](https://img.shields.io/badge/Django-4%2B-0C4B33?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![ML](https://img.shields.io/badge/ML-TF--IDF%20%2B%20Word2Vec-7C3AED?style=flat-square)](#ml--nlp)

> **Most platforms help you find learning content. Sequentia helps you decide what to learn next.**

---

## Why Sequentia?

Traditional recommendation systems often stop at **relevance**: find content that looks similar to the learner's query.

Sequentia adds the missing context:

| Traditional course recommendation | Sequentia |
|---|---|
| Finds relevant content | Builds a learning sequence |
| Content-centric | Learner-centric |
| Ranking-focused | Next-action focused |
| Similarity is the main signal | Multiple learner-specific signals |
| May ignore prerequisites | Prerequisite-aware |
| Can return many options | Picks one current next-best action |
| Static experience | Recalculates as learner state changes |

The key question is not:

**“Which courses are relevant?”**

It is:

**“Which course is relevant for this learner, right now, and why?”**

---

## The Core Loop

```text
Learner goal / free text
        ↓
NLP extraction
        ↓
Learner profile
(goal + role + interests + known skills)
        ↓
Hybrid semantic retrieval
(TF-IDF + project-trained Word2Vec)
        ↓
Skill-gap analysis
        ↓
Prerequisite + difficulty checks
        ↓
Multi-signal scoring
        ↓
Personalized sequence
        ↓
ONE next-best action
        ↓
Learning + feedback
        ↓
Path recalculation
```

---

## What makes the recommender different?

Sequentia scores candidate learning resources using the learner's actual state:

| Signal | Weight |
|---|---:|
| Semantic relevance | **30%** |
| Interest alignment | **20%** |
| Skill gap | **20%** |
| Prerequisite readiness | **20%** |
| Difficulty fit | **10%** |

Past learner feedback can further adjust the score.

This means a course can be highly relevant **but still not be the next course** when prerequisites are missing or the learner's current state points somewhere else.

---

## ML & NLP

### Hybrid semantic recommendation

Sequentia combines two complementary approaches:

**TF-IDF — precision**
- strong exact / technical-term matching
- preserves important lexical signals

**Word2Vec — semantic recall**
- captures related concepts and domain vocabulary
- learns relationships such as `kubernetes ↔ docker ↔ orchestration ↔ deployment`

The Word2Vec model is trained on this project's own **109,776 course reviews**, rather than relying only on generic pretrained English vectors.

Artifacts are trained once and persisted locally for inference.

### Learner-language extraction

The profile pipeline uses **spaCy dependency parsing**, not just regex, to separate:

- target role / goal
- known skills
- interests
- sentence-level intent
- explicit negation

For example:

```text
“I know Python and I’m interested in DevOps.”
```

becomes different learner-state signals instead of one undifferentiated keyword bag.

The parser also handles explicit negation such as:

```text
“I don't know React.”
```

so React is not incorrectly recorded as a known skill.

---

## Sequence Intelligence

Sequentia uses a curated, validated skill graph to reason about dependencies.

```text
Foundations
    ↓
Web Development
    ↓
Databases
    ↓
API Development
    ↓
Deployment
```

A highly relevant advanced resource can remain **blocked** until the learner has the prerequisite evidence needed to make it actionable.

The path engine then chooses **exactly one current next-best action**.

> **The highest-scoring course is not always the next course.**

**Stack and domain scoping.** A goal is scoped to the domains actually
relevant to it (`apps/pathway/services/domain.py`) — a Security goal shows
Security, not Security+Cloud+DevOps+Systems; a Full Stack goal shows Web
Development, not Web Development+Cloud+DevOps. Within that, a learner's
known skills or goal wording are used to detect a language/framework stack
(`apps/pathway/services/stack.py`) — a JavaScript/React learner gets a
Node/React path with zero Python/Django/Java courses mixed in, and vice
versa. Math Foundations only appears for genuinely quantitative goals
(Data Science/ML/DL/Data Engineering), not for every path by default.

---

## Explainable Recommendations

Every recommendation and blocked item gets a reason generated from the actual scoring components.

For example:

```text
Recommended because:
✓ aligned with the target role
✓ addresses a current skill gap
✓ matches learner interests
✓ has no unmet prerequisites
✓ fits the learner's difficulty level
```

The goal is not merely to produce a recommendation, but to make the recommendation understandable.

---

## Adaptive Learning Paths

The path is not a static list.

Every regeneration creates a new path version and the History view records what changed.

```text
Complete a course
      ↓
learner state changes
      ↓
path recalculates
      ↓
course added / removed / reordered
      ↓
new next-best action
```

This makes the learner journey observable instead of hiding path changes behind a black box.

---

## Product Experience

The prototype includes:

- **Dashboard** — current focus, readiness and journey
- **My Path** — staged personalized learning sequence
- **Skills** — interests, known skills, evidence and gaps
- **Projects** — curated portfolio-oriented project briefs
- **Career Readiness** — domain-wise readiness and largest gaps
- **History** — versioned path changes and diffs
- **AI Mentor** — grounded answers about the learner's current path
- **Profile** — editing goals / experience triggers recalculation
- **Internship Mode** — prioritizes portfolio-relevant learning

---

## AI Mentor: grounded first, conversational second

The AI Mentor is deliberately designed so the core recommendation intelligence does not depend on an external LLM.

### Layer 1 — Grounding

A deterministic service answers from the learner's computed state:

- current path
- recommendation scores
- blocked reasons
- path-change history

It cannot invent courses, scores or recommendation reasons.

### Layer 2 — Optional phrasing

Gemini can optionally rephrase the already-grounded answer into more conversational language.

**Turn Gemini off and the recommendation engine still works.**

---

## Data & Catalog

The current catalog contains measured project data for:

- **96 canonical skills**
- **101 courses**
- **147 projects**
- **18 target roles**
- **16 domains**
- **109,776 course reviews** used for the project-trained Word2Vec corpus

Run:

```bash
python manage.py validate_catalog
```

to print live catalog measurements rather than relying on hard-coded README numbers.

---

## Engineering

```text
                    ┌───────────────────┐
                    │   Learner / UI    │
                    └─────────┬─────────┘
                              ↓
                    ┌───────────────────┐
                    │ Django application│
                    └─────────┬─────────┘
                              ↓
             ┌────────────────────────────────┐
             │ Profile / NLP / Recommendation│
             └───────────────┬────────────────┘
                             ↓
                 ┌────────────────────────┐
                 │ Hybrid ML + Skill Graph│
                 └────────────┬───────────┘
                              ↓
                ┌────────────────────────┐
                │ Path + Explainability  │
                └────────────┬───────────┘
                             ↓
                 ┌────────────────────────┐
                 │ Feedback + Path History│
                 └────────────┬───────────┘
                              ↓
                       PostgreSQL
```

### Stack

- Python
- Django
- spaCy
- scikit-learn
- Gensim / Word2Vec
- NumPy / SciPy
- PostgreSQL
- Tailwind CSS
- Render / Gunicorn / WhiteNoise

---

## Testing & Reliability

The project includes **111 automated tests** covering areas such as:

- catalog validation
- skill-graph integrity
- metadata/data validation
- hybrid relevance ranking
- spaCy extraction and negation
- onboarding
- path generation and versioning
- prerequisite reasoning
- AI Mentor grounding and fallback
- stack-aware course filtering (no Python/JS/Java course mixing)
- goal-relevant domain scoping (no unrelated stages for a narrow goal)
- cross-user security isolation

Core recommendation, scoring and path-generation logic does **not** require an external API.

---

## Honest Limitations

Sequentia is intentionally transparent about what is implemented and what is not.

- **21 of 101 courses currently have no real review data.** They remain eligible for catalog, prerequisite and project logic but are excluded from semantic training rather than being given fabricated review text.
- There is currently **no review-quality / sentiment ranking signal** because the source review data has no suitable ratings or sentiment labels.
- Course and project metadata is manually curated in the data seed files.
- The AI Mentor's core intelligence is rule-based; Gemini is optional phrasing, not the recommendation engine.
- Word2Vec is trained on a modest project corpus and therefore should not be expected to generalize well to domains absent from that corpus.

These limitations are documented because reproducibility and honest evaluation matter more than inflated claims.

---

## Roadmap

The next high-value improvements are:

1. **Data-driven project recommendation**
2. **Real rated-review quality signal**
3. **Larger and more diverse review corpus**
4. **Behavior-based personalization**
5. **Stronger offline ranking evaluation and benchmarks**
6. **More exhaustive responsive-device testing**

---

## Run Locally

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py train_embeddings
python manage.py validate_catalog
python manage.py runserver
```

`GEMINI_API_KEY` is optional. Leave it blank to run the AI Mentor without Gemini.

### Frontend styles

Tailwind CSS is compiled and committed for production use:

```bash
npm install
npm run build-css
```

### Tests

```bash
python manage.py test apps
```

---

## Deployment

The repository includes:

- `render.yaml`
- `Procfile`
- Gunicorn
- WhiteNoise
- PostgreSQL configuration
- production static-file support

The trained ML artifacts in `data/artifacts/` can be committed so deployment does not need to retrain the embeddings on every start.

---

## Built for the HCLTech AMPlified Season 1, Round 2 Challenge

Sequentia was built to demonstrate a practical, explainable approach to personalized learning-path recommendation using NLP, ML, prerequisite reasoning and adaptive sequencing.

---

## The One-Line Idea

> **Sequentia does not just recommend what to learn. It recommends what to learn NEXT — and WHY.**

⭐ If the idea is useful or interesting, consider starring the repository and opening an issue with feedback.
