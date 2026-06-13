import argparse
import hashlib
import json
import os
from pathlib import Path
from apify_client import ApifyClient

# Make sure to set your API key in your terminal or .env
# export APIFY_TOKEN="your_apify_token_here"
# or we can grab it from config if you add it there.

def scrape_apify_reviews(place_id: str, limit: int = 50, language: str = "pl") -> list:
    """
    Fetch reviews for a single place using Apify's Google Maps Scraper Actor.
    """
    apify_token = os.getenv("APIFY_TOKEN")
    if not apify_token:
        print("❌ APIFY_TOKEN not set. Please export it or add it to your .env file.")
        return []

    client = ApifyClient(apify_token)

    # We format the Place ID into a Google Maps URL because most Apify actors expect URLs
    place_url = f"https://www.google.com/maps/search/?api=1&query=place&query_place_id={place_id}"

    # We use compass/google-maps-reviews-scraper which is highly optimized for this
    # You can also use drobnikj/crawler-google-places
    run_input = {
        "startUrls": [{"url": place_url}],
        "maxReviews": limit,
        "language": language,
        "personalData": True # Required to get reviewer names
    }

    print(f"🌍 Starting Apify actor for Place ID: {place_id} (Limit: {limit})")
    print("⏳ This might take a minute depending on the limit...")
    
    # Run the actor and wait for it to finish
    run = client.actor("compass/google-maps-reviews-scraper").call(run_input=run_input)

    dataset_id = run.default_dataset_id
    raw_reviews = list(client.dataset(dataset_id).iterate_items())
    
    if not raw_reviews:
        print("⚠️ No reviews returned from Apify.")
        return []

    reviews = []
    for r in raw_reviews:
        text = r.get("text", "")
        if not text or not str(text).strip():
            continue

        # Create a stable review_id from author + timestamp
        review_id = hashlib.md5(
            f"{r.get('name', '')}-{r.get('publishedAtDate', '')}".encode()
        ).hexdigest()

        reviews.append({
            "place_id": place_id,
            "review_id": review_id,
            "author_name": r.get("name", ""),
            "author_url": r.get("reviewerUrl", ""),
            "author_reviews_count": r.get("reviewerNumberOfReviews", 0),
            "rating": r.get("stars", None),
            "text": r.get("text", ""),
            "published_at": r.get("publishedAtDate", ""),
            "published_timestamp": None,
            "language": language,
        })

    return reviews

def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps reviews using Apify")
    parser.add_argument("place_id", type=str, help="Google Maps Place ID to scrape")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of reviews to fetch (default: 50)")
    parser.add_argument("--language", type=str, default="pl", help="Language for reviews (default: pl)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON file path")
    
    args = parser.parse_args()

    reviews = scrape_apify_reviews(
        place_id=args.place_id, 
        limit=args.limit, 
        language=args.language
    )
    
    if not reviews:
        return
        
    print(f"✅ Extracted {len(reviews)} reviews.")
    
    output_file = args.output or f"{args.place_id}_reviews.json"
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
        
    print(f"💾 Saved reviews to {output_file}")

if __name__ == "__main__":
    main()
