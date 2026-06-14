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
import concurrent.futures

import config
from db import get_db, init_db, get_unanalyzed_reviews, insert_analysis

SYSTEM_PROMPT = (
    "You are an expert NLP analyst specializing in Polish restaurant reviews. "
    "Your task is to perform Aspect-Based Sentiment Analysis and anomaly detection. "
    "Respond with ONLY a valid JSON array of objects, no markdown blocks or conversational text.\n"
    "For each review, extract and return exactly these fields:\n"
    "- \"review_id\": exact string from the input\n"
    "- \"overall_sentiment\": \"positive\", \"negative\", \"neutral\", or \"mixed\"\n"
    "- \"topic_sentiments\": object mapping mentioned topics to their sentiment (\"positive\", \"negative\", \"neutral\"). "
    "Allowed topics: [\"service\", \"food_quality\", \"ambiance\", \"price\", \"location\", \"cleanliness\", \"speed\", \"portions\"]\n"
    "- \"dishes_mentioned\": array of specific food items (keep original Polish, but always return nominative (base) form , [] if none)\n"
    "- \"staff_names\": array of staff names mentioned (waiters/cooks only, [] if none)\n"
    "- \"review_depth\": \"shallow\", \"moderate\", or \"detailed\"\n"
    "- \"specificity_score\": integer from 0 to 5\n"
    "- \"fake_signals\": array of detected anomalies from [\"only_mentions_staff\", \"no_food_details\", "
    "\"generic_praise\", \"excessive_exclamation\", \"template_like\", \"unnaturally_positive\", "
    "\"mentions_staff_by_name_without_context\"]\n"
    "IMPORTANT RULES:\n"
    "1. Polish names decline — always return the nominative (base) form (e.g., Kacpra->Kacper, Pawłowi->Paweł, Zosię->Zosia).\n"
    "2. Do NOT include names from restaurant names or dish names in staff_names. Be conservative.\n"
    "3. Do not include topics in \"topic_sentiments\" if they are not explicitly or implicitly mentioned.\n"
    "4. Output ONLY the raw JSON array."
)


def _build_user_prompt(text: str, restaurant_name: str, rating: int, review_id: str) -> str:
    return (f'Analyze this review:\nReview ID: {review_id}\nRestaurant: {restaurant_name}\n'
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


def call_gemini(text: str, restaurant_name: str = "", rating: int = 5, review_id: str = "test_review_1"):
    """Send a review to Gemini API. Returns parsed JSON dict or None."""
    from google.genai import types

    client = _get_gemini_client()
    prompt = _build_user_prompt(text, restaurant_name, rating, review_id)

    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )
        content = response.text
        data = json.loads(content)
        # If the LLM returns an array as requested, extract the first item.
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return data
    except json.JSONDecodeError:
        print(f"  ⚠️ Failed to parse Gemini JSON response")
        return None
    except Exception as e:
        err = str(e)
        if any(x in err for x in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"]):
            print(f"  ⏳ API busy (rate limit/503), waiting 15s...")
            time.sleep(15)
            return None
        print(f"  ⚠️ Gemini error: {e}")
        return None




# ═══════════════════════════════════════════════════════════════
# Backend dispatcher
# ═══════════════════════════════════════════════════════════════

def call_llm(text: str, restaurant_name: str = "", rating: int = 5,
             backend: str = None, review_id: str = "test_review_1"):
    """Route to the configured LLM backend."""
    backend = backend or config.LLM_BACKEND

    if backend == "gemini":
        return call_gemini(text, restaurant_name, rating, review_id)
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

    if has_staff :
        score += config.WEIGHT_STAFF_MENTIONED
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
            return 0, 0

        rests = {}
        for r in conn.execute("SELECT place_id, name FROM restaurants").fetchall():
            rests[r["place_id"]] = r["name"]

        print(f"📊 Analyzing {len(reviews)} reviews via {backend} (parallel)...")
        processed = 0

        def process_review(rev):
            text = rev.get("text", "")
            if not text or len(text.strip()) < 5:
                return rev, None

            result = call_llm(
                text, rests.get(rev["place_id"], ""),
                rev.get("rating", 5), backend, rev["review_id"]
            )
            return rev, result

        # Use 10 workers for parallel API calls. This is safe for Pay-As-You-Go limits.
        # If running on Free Tier and hitting 429s, it will still naturally backoff.
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_review, rev) for rev in reviews]
            
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                rev, result = future.result()
                text = rev.get("text", "")
                
                # Check if it was an empty review
                if not text or len(text.strip()) < 5:
                    insert_analysis(conn, {
                        "review_id": rev["review_id"], "place_id": rev["place_id"],
                        "overall_sentiment": "neutral", "staff_names": [],
                        "dishes_mentioned": [], "topic_sentiments": {},
                        "review_depth": "shallow", "specificity_score": 0,
                        "fake_signals": [], "suspicion_score": 0.0, "in_burst": 0,
                    })
                    processed += 1
                elif result is None:
                    # Failed API call (rate limit, 503, error), skip DB insertion
                    pass
                else:
                    # Successful API call
                    suspicion = compute_suspicion_score(
                        result, rev.get("author_reviews_count")
                    )
                    insert_analysis(conn, {
                        "review_id": rev["review_id"], "place_id": rev["place_id"],
                        "overall_sentiment": result.get("overall_sentiment", ""),
                        "staff_names": result.get("staff_names", []),
                        "dishes_mentioned": result.get("dishes_mentioned", []),
                        "topic_sentiments": result.get("topic_sentiments", {}),
                        "review_depth": result.get("review_depth", ""),
                        "specificity_score": result.get("specificity_score", 0),
                        "fake_signals": result.get("fake_signals", []),
                        "suspicion_score": suspicion, "in_burst": 0,
                    })
                    processed += 1

                if i % 10 == 0:
                    print(f"  ⏳ {i}/{len(reviews)} completed...")
                    conn.commit()

            conn.commit()

        print(f"\n✅ Analyzed {processed}/{len(reviews)} reviews.")
        return processed, len(reviews)


def analyze_all(backend: str = None):
    """Process all unanalyzed reviews in batches."""
    total = 0
    while True:
        processed, fetched = analyze_batch(50, backend)
        total += processed
        print(f"  📊 Total so far: {total}")
        if fetched < 50:
            break
    print(f"\n🎉 Total analyzed: {total}")


def test_single(backend: str = None):
    """Test the LLM with a sample Polish review."""
    backend = backend or config.LLM_BACKEND
    sample = (
        "Byliśmy tam w sobotę. Kelner Kacper był miły. "
        "Polecił pierogi z kaczką — wyśmienite!, kupiliśmy wrapy z kurczakiem i wrapa vege. Atmosfera była okropna, sala była bardzo brudna."
    )
    print(f"🧪 Testing with {backend}: '{sample}'\n")
    result = call_llm(sample, "Restauracja Testowa", 4, backend, review_id="test_review_1")
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
