"""
LLM Analysis Pipeline — Supports Gemini API (free, no GPU) and Ollama (local).

Usage:
    python analyze.py              # Analyze all unanalyzed reviews
    python analyze.py --batch 50   # Process 50 reviews at a time
    python analyze.py --test       # Test with a single sample review
    python analyze.py --backend gemini  # Force specific backend
"""

import argparse
import json
import time
import requests

import config
from db import get_db, init_db, get_unanalyzed_reviews, insert_analysis

SYSTEM_PROMPT = (
    "You are an expert NLP analyst for Polish restaurant reviews. "
    "Respond with ONLY valid JSON, no markdown.\n"
    "Extract: sentiment (positive/negative/neutral/mixed), "
    "staff_names (base nominative form, ONLY staff like waiters/cooks), "
    "dishes_mentioned (Polish), "
    "topics (from: service, food_quality, ambiance, price, location, "
    "cleanliness, speed, portions), "
    "review_depth (shallow/moderate/detailed), "
    "specificity_score (0-5), "
    "fake_signals (from: only_mentions_staff, no_food_details, generic_praise, "
    "excessive_exclamation, template_like, unnaturally_positive, "
    "mentions_staff_by_name_without_context).\n"
    "Rules: Polish names decline — always return nominative: Kacpra→Kacper. "
    "Do NOT include names from restaurant/dish names. Be conservative."
)


def _build_user_prompt(text: str, restaurant_name: str, rating: int) -> str:
    return (f'Analyze this review:\nRestaurant: {restaurant_name}\n'
            f'Rating: {rating}/5\nText: "{text[:2000]}"\nRespond JSON only.')


# ═══════════════════════════════════════════════════════════════
# Backend: Google Gemini API (free tier, no GPU required)
# ═══════════════════════════════════════════════════════════════

_gemini_client = None


def _get_gemini_client():
    """Lazy-init the Gemini client."""
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        api_key = config.GEMINI_API_KEY
        if not api_key or "your_" in api_key:
            raise ValueError(
                "❌ GEMINI_API_KEY not set. Get one free at: "
                "https://aistudio.google.com/apikey"
            )
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def call_gemini(text: str, restaurant_name: str = "", rating: int = 5):
    """Send a review to Gemini API. Returns parsed JSON dict or None."""
    from google.genai import types

    client = _get_gemini_client()
    prompt = _build_user_prompt(text, restaurant_name, rating)

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                max_output_tokens=512,
                response_mime_type="application/json",
            ),
        )
        content = response.text
        return json.loads(content)
    except json.JSONDecodeError:
        print(f"  ⚠️ Failed to parse Gemini JSON response")
        return None
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            print(f"  ⏳ Rate limited, waiting 15s...")
            time.sleep(15)
            return None
        print(f"  ⚠️ Gemini error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# Backend: Ollama (local GPU)
# ═══════════════════════════════════════════════════════════════

def call_ollama(text: str, restaurant_name: str = "", rating: int = 5):
    """Send a review to Ollama. Returns parsed JSON dict or None."""
    prompt = _build_user_prompt(text, restaurant_name, rating)

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
        "format": "json",
    }

    try:
        resp = requests.post(
            f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=120
        )
        if resp.status_code != 200:
            return None
        content = resp.json().get("message", {}).get("content", "")
        return json.loads(content)
    except (json.JSONDecodeError, requests.exceptions.ConnectionError):
        return None
    except Exception as e:
        print(f"  ⚠️ Ollama error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# Backend dispatcher
# ═══════════════════════════════════════════════════════════════

def call_llm(text: str, restaurant_name: str = "", rating: int = 5,
             backend: str = None):
    """Route to the configured LLM backend."""
    backend = backend or config.LLM_BACKEND

    if backend == "gemini":
        return call_gemini(text, restaurant_name, rating)
    elif backend == "ollama":
        return call_ollama(text, restaurant_name, rating)
    else:
        raise ValueError(f"Unknown LLM_BACKEND: {backend}. Use 'gemini' or 'ollama'.")


# ═══════════════════════════════════════════════════════════════
# Suspicion Scoring
# ═══════════════════════════════════════════════════════════════

def compute_suspicion_score(analysis: dict, author_reviews_count=None):
    """Compute composite suspicion score 0.0–1.0."""
    score = 0.0
    has_staff = len(analysis.get("staff_names", [])) > 0
    has_food = len(analysis.get("dishes_mentioned", [])) > 0

    if has_staff and not has_food:
        score += config.WEIGHT_STAFF_NAME_ONLY
    if analysis.get("review_depth") == "shallow":
        score += config.WEIGHT_SHALLOW_REVIEW
    if author_reviews_count is not None and author_reviews_count < 5:
        score += config.WEIGHT_LOW_REVIEWER_HISTORY
    fake_signals = analysis.get("fake_signals", [])
    if len(fake_signals) >= 2:
        score += config.WEIGHT_GENERIC_LANGUAGE
    elif len(fake_signals) == 1:
        score += config.WEIGHT_GENERIC_LANGUAGE * 0.5
    if analysis.get("specificity_score", 3) <= 1:
        score += 0.05

    return min(score, 1.0)


# ═══════════════════════════════════════════════════════════════
# Batch Processing
# ═══════════════════════════════════════════════════════════════

def analyze_batch(batch_size: int = 50, backend: str = None):
    """Process a batch of unanalyzed reviews through the LLM."""
    backend = backend or config.LLM_BACKEND

    with get_db() as conn:
        reviews = get_unanalyzed_reviews(conn, limit=batch_size)
        if not reviews:
            print("✅ No unanalyzed reviews remaining.")
            return 0

        rests = {}
        for r in conn.execute("SELECT place_id, name FROM restaurants").fetchall():
            rests[r["place_id"]] = r["name"]

        print(f"📊 Analyzing {len(reviews)} reviews via {backend}...")
        processed = 0

        for i, rev in enumerate(reviews, 1):
            text = rev.get("text", "")
            if not text or len(text.strip()) < 5:
                insert_analysis(conn, {
                    "review_id": rev["review_id"], "place_id": rev["place_id"],
                    "sentiment": "neutral", "staff_names": [],
                    "dishes_mentioned": [], "topics": [],
                    "review_depth": "shallow", "specificity_score": 0,
                    "fake_signals": [], "suspicion_score": 0.0, "in_burst": 0,
                })
                processed += 1
                continue

            result = call_llm(
                text, rests.get(rev["place_id"], ""),
                rev.get("rating", 5), backend
            )
            if result is None:
                continue

            suspicion = compute_suspicion_score(
                result, rev.get("author_reviews_count")
            )
            insert_analysis(conn, {
                "review_id": rev["review_id"], "place_id": rev["place_id"],
                "sentiment": result.get("sentiment", ""),
                "staff_names": result.get("staff_names", []),
                "dishes_mentioned": result.get("dishes_mentioned", []),
                "topics": result.get("topics", []),
                "review_depth": result.get("review_depth", ""),
                "specificity_score": result.get("specificity_score", 0),
                "fake_signals": result.get("fake_signals", []),
                "suspicion_score": suspicion, "in_burst": 0,
            })
            processed += 1
            if i % 10 == 0:
                print(f"  ⏳ {i}/{len(reviews)} processed...")
                conn.commit()

            # Respect rate limits for Gemini
            if backend == "gemini":
                time.sleep(config.GEMINI_DELAY_SECONDS)

        print(f"\n✅ Analyzed {processed}/{len(reviews)} reviews.")
        return processed


def analyze_all(backend: str = None):
    """Process all unanalyzed reviews in batches."""
    total = 0
    while True:
        batch = analyze_batch(50, backend)
        total += batch
        if batch < 50:
            break
        print(f"  📊 Total so far: {total}")
    print(f"\n🎉 Total analyzed: {total}")


def test_single(backend: str = None):
    """Test the LLM with a sample Polish review."""
    backend = backend or config.LLM_BACKEND
    sample = (
        "Byliśmy tam w sobotę. Kelner Kacper był miły. "
        "Polecił pierogi z kaczką — wyśmienite! Atmosfera przytulna."
    )
    print(f"🧪 Testing with {backend}: '{sample}'\n")
    result = call_llm(sample, "Restauracja Testowa", 4, backend)
    if result:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"\n📊 Suspicion: {compute_suspicion_score(result, 15):.2f}")
    else:
        if backend == "gemini":
            print("❌ Failed. Check GEMINI_API_KEY in .env")
        else:
            print("❌ Failed. Is Ollama running? (ollama serve)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze reviews with LLM (Gemini or Ollama)"
    )
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--backend", choices=["gemini", "ollama"],
                        default=None, help="Override LLM_BACKEND from .env")
    args = parser.parse_args()

    backend = args.backend

    if args.test:
        test_single(backend)
        return
    init_db()
    if args.all:
        analyze_all(backend)
    else:
        analyze_batch(args.batch, backend)


if __name__ == "__main__":
    main()
