# Sequentia — Ready-to-Drop Catalog Upgrade

This checkpoint upgrades the catalog without redesigning the UI or replacing the existing recommendation architecture.

## What changed

- Added a canonical skill vocabulary in `data/skill_seed.csv`.
- Added explicit role requirements in `data/role_seed.csv`.
- Upgraded `data/course_metadata_seed.csv` to the canonical resource schema.
- Upgraded `data/project_seed.csv` to separate prerequisites from demonstrated skills.
- Added `python manage.py validate_catalog`.
- Recommendation scoring now consumes canonical skill IDs.
- Project readiness now gates on canonical prerequisite skill IDs.
- Existing learner evidence written as old course names remains compatible.
- Catalog-only resources are allowed without fake URLs/providers and without a matching row in `train.csv`.
- Semantic embeddings automatically rebuild if the catalog size/order changes.
- Existing UI templates and database models are intentionally left intact.

## Measured catalog

- Canonical skills: 112
- Resources: 142
- Projects: 112
- Supported roles: 24
- Domains: 16
- Dependency cycles: 0

## Replace

You can replace the repository contents with this checkpoint. The generated `data/artifacts/` directory is intentionally empty so stale embeddings are not reused.

## First run

```bash
python manage.py check
python manage.py migrate
python manage.py validate_catalog
python manage.py test
```

On the first recommendation request (or when you run the embedding command), Sequentia will rebuild embeddings for the complete catalog because new internal resources do not have review rows in `train.csv`.

To rebuild them explicitly:

```bash
python manage.py train_embeddings
```

## What to verify manually

1. Frontend Developer path stays in Web Development plus legitimate foundations/supporting domains.
2. Python Developer path uses the Python ecosystem rather than jumping into unrelated ML content.
3. Data Engineer path progresses through SQL → modeling → ETL → warehouse → Spark/Kafka.
4. AI/LLM Engineer path progresses through ML/NLP/deep learning → embeddings → LLMs → RAG/evaluation/agents.
5. DevOps/SRE paths use Linux → networking → Docker → CI/CD → Kubernetes → observability.
6. Completing a project adds inferred evidence for its demonstrated canonical skills and regenerates the learning path.

## Important

The new resources are internal Sequentia catalog items. Provider URLs and external course claims are intentionally left blank unless supplied by verified source data.
