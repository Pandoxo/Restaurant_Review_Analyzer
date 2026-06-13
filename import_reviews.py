import os
import json
import re
from datetime import datetime, timedelta
import hashlib
import sys

from db import get_db, init_db, insert_restaurant, insert_review
from config import DB_PATH

def parse_relative_date(time_str: str) -> int:
    """Convert 'tydzień temu', 'miesiąc temu', '2 dni temu' etc. to Unix timestamp."""
    time_str = time_str.lower()
    nums = re.findall(r'\d+', time_str)
    num = int(nums[0]) if nums else 1

    now = datetime.now()
    delta = timedelta(0)

    if any(w in time_str for w in ["rok", "lata", "lat", "year"]):
        delta = timedelta(days=num * 365)
    elif any(w in time_str for w in ["miesiąc", "miesiące", "miesięcy", "month"]):
        delta = timedelta(days=num * 30)
    elif any(w in time_str for w in ["tydzień", "tygodnie", "tygodni", "week"]):
        delta = timedelta(weeks=num)
    elif any(w in time_str for w in ["dzień", "dni", "day"]):
        delta = timedelta(days=num)
    elif any(w in time_str for w in ["godzina", "godziny", "godzin", "hour"]):
        delta = timedelta(hours=num)
    elif any(w in time_str for w in ["minuta", "minuty", "minut", "minute"]):
        delta = timedelta(minutes=num)
    
    dt = now - delta
    return int(dt.timestamp())

def import_json_files(directory="reviews", clean=False):
    if clean and DB_PATH.exists():
        os.remove(DB_PATH)
        print("🗑️  Old database removed.")
    
    init_db()
    with get_db() as conn:
        for filename in os.listdir(directory):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(directory, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            rest = data.get("restaurant", {})
            reviews = data.get("reviews", [])
            
            name = rest.get("name", "Unknown")
            place_id = hashlib.md5(name.encode()).hexdigest()
            
            insert_restaurant(conn, {
                "place_id": place_id,
                "name": name,
                "type": rest.get("type", ""),
                "address": rest.get("address", ""),
                "rating": rest.get("avg_rating"),
                "total_reviews": rest.get("total_reviews"),
                "lat": None,
                "lng": None,
            })
            
            for rev in reviews:
                ts = parse_relative_date(rev.get("published_at", ""))
                insert_review(conn, {
                    "place_id": place_id,
                    "review_id": rev.get("review_id"),
                    "author_name": rev.get("author_name"),
                    "author_url": "",
                    "author_reviews_count": rev.get("author_reviews_count"),
                    "rating": rev.get("rating"),
                    "text": rev.get("text", ""),
                    "published_at": rev.get("published_at", ""),
                    "published_timestamp": ts,
                    "language": rev.get("language", "pl"),
                })
            
            print(f"✅ Imported {name}: {len(reviews)} reviews")

if __name__ == "__main__":
    clean = "--clean" in sys.argv
    import_json_files(clean=clean)
    print("\n🎉 Import complete! Now run `python analyze.py --all` and then `python detect.py`")
