import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

def scrape_playwright_reviews(place_id: str, limit: int = 50, language: str = "pl", headless: bool = True) -> list:
    # URL structure to search by place_id which directly opens the place pane
    url = f"https://www.google.com/maps/search/?api=1&query=place&query_place_id={place_id}&hl={language}"
    
    with sync_playwright() as p:
        # Launching Chromium. We use a somewhat large viewport to load more items at once.
        browser = p.chromium.launch(headless=headless, args=['--disable-blink-features=AutomationControlled'])
        context = browser.new_context(
            locale=language,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        if HAS_STEALTH:
            Stealth().apply_stealth_sync(context)
            
        page = context.new_page()
        
        print(f"🌍 Navigating to Google Maps for place_id: {place_id}")
        page.goto(url)
        
        # 1. Handle Cookie Consent (EU specifically)
        try:
            # Matches English "Accept all" and Polish "Zaakceptuj wszystko"
            consent_btn = page.locator('button:has-text("Zaakceptuj wszystko"), button:has-text("Accept all")').first
            consent_btn.click(timeout=5000)
            print("🍪 Accepted cookies")
        except Exception:
            pass
            
        time.sleep(3) # Wait for potential redirect after place loads
        
        # 2. Wait for and click on the "Reviews" / "Opinie" tab
        try:
            # Add a small delay to let Google's scripts fully populate the tabs
            time.sleep(2)
            
            # Wait for the specific tab to become visible
            tab = page.locator('button[role="tab"]:has-text("opini"), button[role="tab"]:has-text("review")').first
            
            try:
                tab.wait_for(state="visible", timeout=5000)
                tab.click()
                print("📝 Clicked Reviews tab")
            except Exception:
                # Fallback: check all tabs manually in case of different casing or naming
                tabs = page.locator('button[role="tab"]').all()
                clicked = False
                for t in tabs:
                    text = t.inner_text().lower()
                    if 'opini' in text or 'review' in text:
                        t.click()
                        print(f"📝 Clicked Reviews tab via fallback: {t.inner_text()}")
                        clicked = True
                        break
                if not clicked:
                     print("⚠️ Could not find a Reviews tab.")
                     
            time.sleep(2)
        except Exception as e:
            print(f"❌ Error while clicking Reviews tab: {e}")
            browser.close()
            return []
            
        # 3. Wait for reviews to load
        try:
            page.wait_for_selector('div[data-review-id]', timeout=10000)
            print("⏬ Scrolling to load reviews...")
        except Exception:
            print("❌ No reviews found or page structure changed.")
            browser.close()
            return []
        
        # 4. Scroll the reviews pane
        reviews_data = []
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
                print(f"  Loaded {len(review_ids_seen)} reviews...")
                
            if len(review_ids_seen) >= limit:
                break
                
            # Scroll down by targeting the last loaded review and scrolling it into view
            if review_elements:
                try:
                    review_elements[-1].scroll_into_view_if_needed()
                    # A small forced scroll to trigger lazy loading
                    page.mouse.wheel(0, 1000)
                    time.sleep(1.5) # Give it time to fetch and render
                except Exception:
                    pass

        # 5. Expand long reviews by clicking "More" / "Więcej"
        print("🔍 Extracting review text and data...")
        more_buttons = page.locator('button.w8nwRe.kyuRq:has-text("Więcej"), button.w8nwRe.kyuRq:has-text("More")').element_handles()
        for btn in more_buttons:
            try:
                if btn.is_visible():
                    btn.click()
            except Exception:
                continue
                
        time.sleep(1) # wait for text expansion to render
        
        # 6. Parse the data
        review_locators = page.locator('div[data-review-id]').all()
        
        for element in review_locators[:limit]:
            try:
                review_id = element.get_attribute("data-review-id")
                
                # Author Name (.d4r55 usually contains the name)
                author_elem = element.locator('.d4r55')
                author_name = author_elem.first.inner_text() if author_elem.count() > 0 else "Unknown"
                
                # Review Text (.wiI7pd)
                text_elem = element.locator('.wiI7pd')
                text = text_elem.first.inner_text() if text_elem.count() > 0 else ""
                
                # Time / Published At (.rsqaWe)
                time_elem = element.locator('.rsqaWe')
                published_at = time_elem.first.inner_text() if time_elem.count() > 0 else ""
                
                # Rating - Looking for aria-label with stars (e.g. "5 gwiazdek" or "5 stars")
                rating = None
                rating_elem = element.locator('[aria-label*="gwiazd"], [aria-label*="star"]').first
                if rating_elem.count() > 0:
                    rating_str = rating_elem.get_attribute("aria-label") or ""
                    # extract the first number found
                    nums = [int(s) for s in rating_str.split() if s.isdigit()]
                    if nums:
                        rating = nums[0]

                reviews_data.append({
                    "place_id": place_id,
                    "review_id": review_id,
                    "author_name": author_name,
                    "rating": rating,
                    "text": text,
                    "published_at": published_at,
                    "language": language
                })
            except Exception as e:
                print(f"Error parsing a review: {e}")
                
        browser.close()
        return reviews_data

def main():
    parser = argparse.ArgumentParser(description="Scrape Google Maps reviews manually using Playwright")
    parser.add_argument("place_id", type=str, help="Google Maps Place ID to scrape")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of reviews to fetch (default: 50)")
    parser.add_argument("--language", type=str, default="pl", help="Language for reviews (default: pl)")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode (visible) for debugging")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output JSON file path (default: <place_id>_reviews.json)")
    
    args = parser.parse_args()

    reviews = scrape_playwright_reviews(
        place_id=args.place_id, 
        limit=args.limit, 
        language=args.language, 
        headless=not args.headed
    )
    
    if not reviews:
        print("⚠️ No reviews found or an error occurred.")
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
