import argparse
import hashlib
import json
from pathlib import Path

from outscraper import ApiClient

import config

def scrape_place_reviews(place_id: str, limit: int = None, language: str = "pl", sort: str = "newest") -> list:
    """
    Fetch all reviews for a single place using Outscraper.
    Returns a list of normalized review dicts.
    """
    api_key = config.OUTSCRAPER_API_KEY
    if not api_key or api_key == "your_outscraper_api_key_here":
        print("❌ OUTSCRAPER_API_KEY not set in .env")
        return []

    client = ApiClient(api_key=api_key)
    limit = limit or config.MAX_REVIEWS_PER_RESTAURANT

    try:
        results = client.google_maps_reviews(
            [place_id],
            limit=limit,
            language=language,
            sort=sort,
        )
    except Exception as e:
        print(f"❌ Outscraper error for {place_id}: {e}")
        return []

    if not results or not results[0]:
        return []

    place_data = results[0]
    raw_reviews = place_data.get("reviews_data", [])

    reviews = []
    for r in raw_reviews:
        # Create a stable review_id from author + timestamp
        review_id = hashlib.md5(
            f"{r.get('author_id', '')}-{r.get('review_datetime_utc', '')}".encode()
        ).hexdigest()

        reviews.append({
            "place_id": place_id,
            "review_id": review_id,
            "author_name": r.get("author_title", ""),
            "author_url": r.get("author_link", ""),
            "author_reviews_count": r.get("author_reviews_count"),
            "rating": r.get("review_rating"),
            "text": r.get("review_text", ""),
            "published_at": r.get("review_datetime_utc", ""),
            "published_timestamp": r.get("review_timestamp"),
            "language": language,
        })

    return reviews

def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps reviews for a specific place ID and output to JSON")
    parser.add_argument("place_id", type=str, help="Google Maps Place ID to scrape")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of reviews to fetch (default: from config)")
    parser.add_argument("--language", type=str, default="pl", help="Language for reviews (default: pl)")
    parser.add_argument("--sort", type=str, default="newest", help="Sort order: newest, most_relevant, highest_rating, lowest_rating (default: newest)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON file path (default: <place_id>_reviews.json)")
    
    args = parser.parse_args()

    print(f"📥 Fetching reviews for place ID: {args.place_id}")
    
    reviews = scrape_place_reviews(
        place_id=args.place_id, 
        limit=args.limit, 
        language=args.language, 
        sort=args.sort
    )
    
    if not reviews:
        print("⚠️ No reviews found or an error occurred.")
        return
        
    print(f"✅ Fetched {len(reviews)} reviews.")
    
    output_file = args.output or f"{args.place_id}_reviews.json"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
        
    print(f"💾 Saved reviews to {output_file}")

if __name__ == "__main__":
    main()
