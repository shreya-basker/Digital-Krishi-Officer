"""OpenAI calls, kept server-side so the API key never reaches the browser."""

import json
import logging

from openai import OpenAI, OpenAIError

from app.config import settings

log = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "simple English", "ml": "Malayalam", "hi": "Hindi"}

CHAT_SYSTEM_PROMPT = """
You are Agrisathi, a digital Krishi officer assistant for Indian farmers. Give quick, clear, practical advice.

Rules:
1. Answer only farming-related queries: crops, soil, irrigation, fertilisers, pests, seeds, government schemes,
   mandi prices, weather, pesticides, organic practices and sustainable methods.
2. Keep answers short, clear and easy to understand. Use bullet points or numbered lists where possible.
3. Reply in the language of the farmer's query. If unclear, reply in {language}.
4. When farm context is provided below, use it (location, crop, stage, soil, weather, prices, current
   recommendations) instead of guessing. Do not contradict the listed recommendations without saying why.
5. Never invent exact pesticide or fertiliser doses. Say they should follow the label, their Soil Health Card
   or their local KVK / Krishi officer.
6. If unsure, say: "Please consult your local Krishi Officer for exact guidance."
7. If the query is unrelated to farming, politely decline: "I can only help with farming-related questions."
8. If an image is provided, analyse it for crop health, soil, pest attack or irrigation issues and give advice
   relevant to what is seen. If the query is empty, just analyse the image.
9. Encourage sustainable, eco-friendly and cost-effective practices. Be respectful and supportive.
""".strip()

EXPLAIN_SYSTEM_PROMPT = """
You rewrite farm recommendations for a farmer in {language}. Keep the meaning exactly the same.
Do not add new advice, doses, products or numbers that are not in the input. Keep titles under 12 words
and rationales under 40 words. Return JSON: {{"items": [{{"id": <id>, "title": "...", "rationale": "..."}}]}}
""".strip()

FALLBACK_ANSWER = (
    "The AI assistant is not configured yet (no OpenAI API key). "
    "Your question has been saved. Please check today's recommendations on the dashboard, "
    "or consult your local Krishi Officer."
)


def enabled() -> bool:
    return bool(settings.openai_api_key)


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key, timeout=30)


def chat(text: str, image_base64: str | None, image_mime: str, farm_context: str | None, language: str) -> str:
    if not enabled():
        return FALLBACK_ANSWER
    system = CHAT_SYSTEM_PROMPT.format(language=LANGUAGE_NAMES.get(language, "simple English"))
    if farm_context:
        system += "\n\nFarm context:\n" + farm_context
    content: list[dict] = [{"type": "text", "text": text or "Please analyse this image of my crop."}]
    if image_base64:
        content.append({"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_base64}"}})
    try:
        resp = _client().chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            temperature=0.3,
        )
        return resp.choices[0].message.content or "No response received."
    except OpenAIError as exc:
        log.warning("OpenAI chat failed: %s", exc)
        return "Sorry, the AI assistant is unavailable right now. Please try again in a few minutes."


def rewrite_actions(items: list[dict], language: str) -> dict[int, dict] | None:
    """Returns {id: {title, rationale}} in the farmer's language, or None to keep the templates."""
    if not enabled() or not items:
        return None
    system = EXPLAIN_SYSTEM_PROMPT.format(language=LANGUAGE_NAMES.get(language, "simple English"))
    try:
        resp = _client().chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(items)}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return {int(i["id"]): {"title": i["title"], "rationale": i["rationale"]} for i in data.get("items", [])}
    except (OpenAIError, ValueError, KeyError, TypeError) as exc:
        log.warning("OpenAI explanation failed, using templates: %s", exc)
        return None
