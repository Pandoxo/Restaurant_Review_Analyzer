"""
Data Collection — Uses Google Places API for discovery and Outscraper for reviews.

Usage:
    python collect.py                  # Run full pipeline
    python collect.py --find-only      # Only find restaurants (no reviews)
    python collect.py --reviews-only   # Only fetch reviews for existing restaurants
"""

import argparse
import hashlib
import time
import requests
from outscraper import ApiClient

import config
from db import get_db, init_db, insert_restaurant, insert_review


# ═══════════════════════════════════════════════════════════════
# Step 1: Find restaurants via Google Places API (Text Search)
# ═══════════════════════════════════════════════════════════════

def find_restaurants(query: str = None, max_results: int = None) -> list:
    """
    Use Google Places API (New) Text Search to find restaurants in Poznań.
    Returns a list of restaurant dicts with place_id, name, etc.
    """
    query = query or config.SEARCH_QUERY
    max_results = max_results or config.MAX_RESTAURANTS

    api_key = config.GOOGLE_PLACES_API_KEY
    if not api_key or api_key == "your_google_places_api_key_here":
        print("❌ GOOGLE_PLACES_API_KEY not set in .env")
        return []

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        # Only request fields we need to minimize cost
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.location"
        ),
    }
    body = {
        "textQuery": query,
        "languageCode": "pl",
        "maxResultCount": min(max_results, 20),  # API max is 20 per request
    }

    print(f"🔍 Searching: '{query}'...")
    resp = requests.post(url, json=body, headers=headers)

    if resp.status_code != 200:
        print(f"❌ Google Places API error {resp.status_code}: {resp.text[:300]}")
        return []

    data = resp.json()
    places = data.get("places", [])

    restaurants = []
    for p in places[:max_results]:
        loc = p.get("location", {})
        restaurant = {
            "place_id": p.get("id", ""),
            "name": p.get("displayName", {}).get("text", "Unknown"),
            "address": p.get("formattedAddress", ""),
            "rating": p.get("rating"),
            "total_reviews": p.get("userRatingCount"),
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
        }
        restaurants.append(restaurant)
        print(f"  📍 {restaurant['name']} — ⭐ {restaurant['rating']} "
              f"({restaurant['total_reviews']} reviews)")

    print(f"\n✅ Found {len(restaurants)} restaurants.")
    return restaurants


# ═══════════════════════════════════════════════════════════════
# Step 2: Fetch reviews via Outscraper API
# ═══════════════════════════════════════════════════════════════

def fetch_reviews_for_restaurant(client: ApiClient, place_id: str,
                                  limit: int = None) -> list:
    """
    Fetch all reviews for a single restaurant using Outscraper.
    Returns a list of normalized review dicts.
    """
    limit = limit or config.MAX_REVIEWS_PER_RESTAURANT

    try:
        results = client.google_maps_reviews(
            [place_id],
            limit=limit,
            language="pl",
            sort="newest",
            ignore_empty=True,
        )
    except Exception as e:
        print(f"  ❌ Outscraper error for {place_id}: {e}")
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
            "language": "pl",
        })

    return reviews


def fetch_all_reviews(restaurants: list = None):
    """
    Fetch reviews for all restaurants in the database (or a provided list).
    """
    api_key = config.OUTSCRAPER_API_KEY
    if not api_key or api_key == "your_outscraper_api_key_here":
        print("❌ OUTSCRAPER_API_KEY not set in .env")
        return

    client = ApiClient(api_key=api_key)

    with get_db() as conn:
        if restaurants is None:
            rows = conn.execute("SELECT place_id, name FROM restaurants").fetchall()
            restaurants = [{"place_id": r["place_id"], "name": r["name"]} for r in rows]

        for i, rest in enumerate(restaurants, 1):
            pid = rest["place_id"]
            name = rest["name"]
            print(f"\n📥 [{i}/{len(restaurants)}] Fetching reviews for: {name}")

            reviews = fetch_reviews_for_restaurant(client, pid)
            for rev in reviews:
                insert_review(conn, rev)

            print(f"  ✅ Stored {len(reviews)} reviews.")

            # Be polite to the API
            if i < len(restaurants):
                time.sleep(2)

    print(f"\n🎉 Done fetching reviews for {len(restaurants)} restaurants.")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Collect restaurant data and reviews")
    parser.add_argument("--find-only", action="store_true",
                        help="Only find restaurants, don't fetch reviews")
    parser.add_argument("--reviews-only", action="store_true",
                        help="Only fetch reviews for existing restaurants")
    parser.add_argument("--query", type=str, default=None,
                        help="Custom search query")
    parser.add_argument("--max", type=int, default=None,
                        help="Max number of restaurants to find")
    args = parser.parse_args()

    init_db()

    if not args.reviews_only:
        restaurants = find_restaurants(query=args.query, max_results=args.max)
        if restaurants:
            with get_db() as conn:
                for r in restaurants:
                    insert_restaurant(conn, r)
            print(f"💾 Saved {len(restaurants)} restaurants to database.")

    if not args.find_only:
        fetch_all_reviews()


if __name__ == "__main__":
    main()
