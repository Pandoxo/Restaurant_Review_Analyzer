"""
Stealth Google Maps Review Scraper — powered by Camoufox.

Usage:
    # Single place by Place ID
    python scrape_camoufox.py ChIJv20NLjJbBEcR9S9YiX-PfW8 --limit 100

    # Single place by Google Maps URL
    python scrape_camoufox.py "https://www.google.com/maps/place/..." --limit 100

    # Batch mode — pass a .txt file with one URL/place_id per line
    python scrape_camoufox.py --file restaurants.txt --limit 200

    # Headed mode for debugging
    python scrape_camoufox.py --file restaurants.txt --limit 50 --headed
"""

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from camoufox.sync_api import Camoufox


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def slugify(text: str) -> str:
    """Convert a restaurant name into a safe filename slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)


def parse_input_line(line: str) -> str:
    """
    Accept either a raw Place ID or a full Google Maps URL.
    Returns a Google Maps URL suitable for navigation.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # If it looks like a URL, return it directly
    if line.startswith("http://") or line.startswith("https://"):
        return line

    # Otherwise treat it as a Place ID and build the URL
    return f"https://www.google.com/maps/search/?api=1&query=place&query_place_id={line}"


def load_targets_from_file(filepath: str) -> list[str]:
    """Read a .txt file with one URL or Place ID per line."""
    targets = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            url = parse_input_line(line)
            if url:
                targets.append(url)
    return targets


# ═══════════════════════════════════════════════════════════════
# Restaurant Info Extraction
# ═══════════════════════════════════════════════════════════════

def extract_restaurant_info(page, language: str) -> dict:
    """
    Extract basic restaurant metadata from the place panel header.
    Returns dict with name, address, price_range, total_reviews, avg_rating.
    """
    info = {
        "name": None,
        "address": None,
        "price_range": None,
        "total_reviews": None,
        "avg_rating": None,
    }

    # --- Name ---
    try:
        name_elem = page.locator('h1').first
        if name_elem.count() > 0:
            info["name"] = name_elem.inner_text().strip()
    except Exception:
        pass

    # --- Average Rating ---
    try:
        # The rating is typically in a <span> with role=img and aria-label like "4,5 gwiazdki"
        rating_span = page.locator('div.F7nice span[aria-hidden="true"]').first
        if rating_span.count() > 0:
            raw = rating_span.inner_text().strip().replace(",", ".")
            info["avg_rating"] = float(raw)
    except Exception:
        pass

    # --- Total Reviews ---
    try:
        # Usually displayed as "(1 234)" or "(1,234 reviews)"
        review_count_elem = page.locator('div.F7nice span[aria-label]').first
        if review_count_elem.count() > 0:
            label = review_count_elem.get_attribute("aria-label") or ""
            nums = re.findall(r"[\d\s.,]+", label)
            if nums:
                count_str = nums[0].replace(" ", "").replace(".", "").replace(",", "")
                if count_str.isdigit():
                    info["total_reviews"] = int(count_str)
    except Exception:
        pass

    # --- Address ---
    try:
        # Address is typically in a button with data-item-id="address"
        addr_elem = page.locator('button[data-item-id="address"] div.Io6YTe').first
        if addr_elem.count() > 0:
            info["address"] = addr_elem.inner_text().strip()
    except Exception:
        pass

    # --- Price Range ---
    try:
        # Price range is often shown as "$$" or "zł zł" near the category info
        # It appears in an aria-label like "Price: Moderate" or in the text directly
        price_elem = page.locator('[aria-label*="Price"], [aria-label*="Cen"]').first
        if price_elem.count() > 0:
            info["price_range"] = price_elem.inner_text().strip()
        else:
            # Fallback: look for the $ or zł symbols in the category/subtitle area
            subtitle_elems = page.locator('button.DkEaL').all()
            for elem in subtitle_elems:
                txt = elem.inner_text().strip()
                if re.match(r'^[·\s]*[\$€£zł]{1,4}[·\s]*$', txt) or '·' in txt:
                    # Extract just the price symbols
                    price_match = re.search(r'([\$€£]{1,4}|(?:zł\s*){1,4})', txt)
                    if price_match:
                        info["price_range"] = price_match.group(0).strip()
                        break
    except Exception:
        pass

    return info


# ═══════════════════════════════════════════════════════════════
# Core Scraper
# ═══════════════════════════════════════════════════════════════

def scrape_place(page, url: str, limit: int, language: str) -> dict:
    """
    Scrape a single place. Returns a dict with:
        { "restaurant": {...info...}, "reviews": [...] }
    """
    print(f"\n{'═'*60}")
    print(f"🌍 Navigating to: {url[:80]}...")
    page.goto(url, wait_until="domcontentloaded")

    # 1. Handle Cookie Consent (EU)
    try:
        consent_btn = page.locator(
            'button:has-text("Zaakceptuj wszystko"), '
            'button:has-text("Accept all")'
        ).first
        consent_btn.click(timeout=5000)
        print("🍪 Accepted cookies")
    except Exception:
        pass

    time.sleep(3)

    # 2. Extract restaurant info from the main place panel
    info = extract_restaurant_info(page, language)
    restaurant_name = info["name"] or "unknown_restaurant"
    print(f"🏪 Restaurant: {restaurant_name}")
    if info["avg_rating"]:
        print(f"   ⭐ Rating: {info['avg_rating']}  ({info['total_reviews'] or '?'} reviews)")
    if info["address"]:
        print(f"   📍 {info['address']}")
    if info["price_range"]:
        print(f"   💰 Price: {info['price_range']}")

    # 3. Click the Reviews tab
    try:
        time.sleep(2)
        tab = page.locator(
            'button[role="tab"]:has-text("opini"), '
            'button[role="tab"]:has-text("review")'
        ).first

        try:
            tab.wait_for(state="visible", timeout=5000)
            tab.click()
            print("📝 Clicked Reviews tab")
        except Exception:
            tabs = page.locator('button[role="tab"]').all()
            clicked = False
            for t in tabs:
                txt = t.inner_text().lower()
                if "opini" in txt or "review" in txt:
                    t.click()
                    print(f"📝 Clicked Reviews tab via fallback: {t.inner_text()}")
                    clicked = True
                    break
            if not clicked:
                print("⚠️ Could not find a Reviews tab.")
                return {"restaurant": info, "reviews": []}

        time.sleep(2)
    except Exception as e:
        print(f"❌ Error clicking Reviews tab: {e}")
        return {"restaurant": info, "reviews": []}

    # 4. Sort by Newest
    try:
        sort_btn = page.locator(
            'button[aria-label*="Sortuj"], '
            'button[aria-label*="Sort"], '
            'button[data-value="Sort"]'
        ).first
        if sort_btn.count() > 0:
            sort_btn.click()
            time.sleep(1)
            # Click "Najnowsze" / "Newest"
            newest_opt = page.locator(
                'div[role="menuitemradio"]:has-text("Najnowsze"), '
                'div[role="menuitemradio"]:has-text("Newest")'
            ).first
            if newest_opt.count() > 0:
                newest_opt.click()
                print("🔃 Sorted reviews by Newest")
                time.sleep(2)
            else:
                print("⚠️ Could not find 'Newest' sort option")
        else:
            print("⚠️ Sort button not found")
    except Exception as e:
        print(f"⚠️ Could not sort reviews: {e}")

    # 5. Wait for reviews to load
    try:
        page.wait_for_selector('div[data-review-id]', timeout=10000)
        print("⏬ Scrolling to load reviews...")
    except Exception:
        print("❌ No reviews found or page structure changed.")
        return {"restaurant": info, "reviews": []}

    # 6. Scroll to load reviews
    review_ids_seen = set()
    consecutive_no_new = 0

    while len(review_ids_seen) < limit and consecutive_no_new < 5:
        review_elements = page.locator('div[data-review-id]').element_handles()

        new_found = 0
        for element in review_elements:
            rid = element.get_attribute("data-review-id")
            if rid and rid not in review_ids_seen:
                review_ids_seen.add(rid)
                new_found += 1

        if new_found == 0:
            consecutive_no_new += 1
        else:
            consecutive_no_new = 0
            print(f"  Loaded {len(review_ids_seen)} unique reviews...")

        if len(review_ids_seen) >= limit:
            break

        if review_elements:
            try:
                review_elements[-1].scroll_into_view_if_needed()
                page.mouse.wheel(0, 1000)
                time.sleep(1.5)
            except Exception:
                pass

    # 7. Expand long reviews
    print("🔍 Extracting review text and data...")
    more_buttons = page.locator(
        'button.w8nwRe.kyuRq:has-text("Więcej"), '
        'button.w8nwRe.kyuRq:has-text("More")'
    ).element_handles()
    for btn in more_buttons:
        try:
            if btn.is_visible():
                btn.click()
        except Exception:
            continue

    time.sleep(1)

    # 8. Parse reviews — deduplicate by review_id
    review_locators = page.locator('div[data-review-id]').all()
    reviews_data = []
    seen_ids = set()

    for element in review_locators:
        if len(reviews_data) >= limit:
            break
        try:
            review_id = element.get_attribute("data-review-id")

            # Skip duplicates
            if review_id in seen_ids:
                continue
            seen_ids.add(review_id)

            # Author Name
            author_elem = element.locator('.d4r55')
            author_name = author_elem.first.inner_text() if author_elem.count() > 0 else "Unknown"

            # Review Text
            text_elem = element.locator('.wiI7pd')
            text = text_elem.first.inner_text() if text_elem.count() > 0 else ""

            # Skip reviews without text
            if not text or not str(text).strip():
                continue

            # Published At
            time_elem = element.locator('.rsqaWe')
            published_at = time_elem.first.inner_text() if time_elem.count() > 0 else ""

            # Rating
            rating = None
            rating_elem = element.locator('[aria-label*="gwiazd"], [aria-label*="star"]').first
            if rating_elem.count() > 0:
                rating_str = rating_elem.get_attribute("aria-label") or ""
                nums = [int(s) for s in rating_str.split() if s.isdigit()]
                if nums:
                    rating = nums[0]

            reviews_data.append({
                "review_id": review_id,
                "author_name": author_name,
                "rating": rating,
                "text": text,
                "published_at": published_at,
                "language": language,
            })
        except Exception as e:
            print(f"  Error parsing a review: {e}")

    print(f"✅ Extracted {len(reviews_data)} reviews with text (from {len(seen_ids)} total).")
    return {"restaurant": info, "reviews": reviews_data}


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Google Maps reviews using Camoufox (Stealth Firefox)"
    )
    parser.add_argument(
        "target", nargs="?", default=None,
        help="A Google Maps Place ID or URL to scrape"
    )
    parser.add_argument(
        "--file", "-f", type=str, default=None,
        help="Path to a .txt file with one URL or Place ID per line"
    )
    parser.add_argument("--limit", type=int, default=50,
                        help="Max reviews per restaurant (default: 50)")
    parser.add_argument("--language", type=str, default="pl",
                        help="Language for reviews (default: pl)")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser in headed mode for debugging")
    parser.add_argument("--output-dir", "-d", type=str, default="data",
                        help="Output directory for JSON files (default: data)")

    args = parser.parse_args()

    # Collect all targets
    targets = []
    if args.file:
        targets = load_targets_from_file(args.file)
        print(f"📄 Loaded {len(targets)} targets from {args.file}")
    elif args.target:
        url = parse_input_line(args.target)
        if url:
            targets.append(url)
    else:
        parser.error("Provide either a Place ID / URL or --file with targets.")

    if not targets:
        print("❌ No valid targets found.")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use a single browser session for all targets (more efficient & stealthy)
    with Camoufox(headless=not args.headed) as browser:
        page = browser.new_page()

        for i, url in enumerate(targets, 1):
            print(f"\n🔢 [{i}/{len(targets)}]")

            result = scrape_place(page, url, args.limit, args.language)
            restaurant = result["restaurant"]
            reviews = result["reviews"]

            # Build filename from restaurant name
            name = restaurant.get("name") or "unknown"
            filename = f"{slugify(name)}.json"
            output_path = output_dir / filename

            # Build the output JSON with restaurant info + reviews
            output_data = {
                "restaurant": restaurant,
                "reviews": reviews,
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

            print(f"💾 Saved {len(reviews)} reviews → {output_path}")

            # Small delay between restaurants to appear more human
            if i < len(targets):
                time.sleep(3)

    print(f"\n🎉 Done! Scraped {len(targets)} restaurant(s).")


if __name__ == "__main__":
    main()
