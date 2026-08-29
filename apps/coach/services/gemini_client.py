from __future__ import annotations

from django.conf import settings

SYSTEM_PROMPT = (
    "You are Sequentia's learning coach. You rephrase a FACTS block into a "
    "short, warm, natural-sounding reply for the learner. Rules, no exceptions:\n"
    "1. Use ONLY the information inside FACTS. Never state a course name, "
    "score, percentage, or reason that is not present in FACTS.\n"
    "2. Never invent, guess, or estimate anything FACTS does not state.\n"
    "3. Never answer general knowledge, small talk, opinions, or anything "
    "outside the learner's own path/recommendations — if FACTS says the "
    "question is out of scope, say so plainly and redirect to what you can "
    "help with. Do not apologize at length or chat.\n"
    "4. Keep the reply to 2-4 sentences. No filler, no disclaimers about "
    "being an AI.\n"
    "5. All ranking, scoring, and recommendation decisions were already made "
    "by the platform's own ML pipeline before you saw this — you are only "
    "phrasing the result, never producing or altering it."
)


def _client():
    if not settings.GEMINI_API_KEY:
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        return None
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)


def phrase_grounded_answer(question: str, facts: str) -> str | None:
    model = _client()
    if model is None:
        return None
    prompt = f"FACTS:\n{facts}\n\nLearner's question: {question}\n\nReply:"
    try:
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.3, "max_output_tokens": 200},
        )
        text = (response.text or "").strip()
        return text or None
    except Exception:
        return None
