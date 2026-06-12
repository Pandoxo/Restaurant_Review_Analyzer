import asyncio
import json
import argparse
from playwright.async_api import async_playwright

async def scrape_google_maps_reviews(place_id: str, max_reviews: int = 50, headless: bool = True):
    """
    Scrapes reviews from Google Maps for a given Place ID.
    
    Args:
        place_id (str): The Google Place ID (e.g., ChIJj61dQgK6j4AR4GeTYWZsKWw)
        max_reviews (int): Maximum number of reviews to collect
        headless (bool): Whether to run the browser in background (headless)
    """
    # The standard URL format to search for a specific place ID on Google Maps
    url = f"https://www.google.com/maps/search/?api=1&query=Google&query_place_id={place_id}"
    
    async with async_playwright() as p:
        # Launch browser. Sometimes headless=False helps bypass bot detection.
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='en-US'  # Force English to standardize text like "Reviews", "More"
        )
        page = await context.new_page()
        
        print(f"Navigating to: {url}")
        await page.goto(url)
        
        # 1. Handle cookie consent if prompted (in Europe)
        try:
            consent_button = page.locator("button:has-text('Accept all')").first
            if await consent_button.is_visible(timeout=5000):
                await consent_button.click()
                print("Accepted cookies.")
        except Exception:
            pass
            
        # 2. Wait for the main panel to load (the place name is usually an h1)
        try:
            await page.wait_for_selector('h1', timeout=10000)
        except Exception:
            print("Failed to load the place page. The place ID might be invalid.")
            await browser.close()
            return []
            
        # 3. Click the "Reviews" tab
        try:
            # The tab typically has role="tab" and contains the word "Reviews"
            reviews_tab = page.locator("button[role='tab']:has-text('Reviews')").first
            await reviews_tab.click()
            print("Switched to Reviews tab.")
        except Exception:
            print("Could not find 'Reviews' tab. Make sure the place has reviews.")
            await browser.close()
            return []
            
        # 4. Wait for the reviews container to load
        # .jftiEf is the standard CSS class for a single review block on Google Maps
        try:
            await page.wait_for_selector('.jftiEf', timeout=10000)
        except Exception:
            print("No reviews appeared after clicking the tab.")
            await browser.close()
            return []
            
        reviews = []
        parsed_ids = set()
        consecutive_no_new = 0
        
        print(f"Scraping up to {max_reviews} reviews...")
        
        while len(reviews) < max_reviews and consecutive_no_new < 5:
            # Click all "More" buttons to expand long reviews
            more_buttons = page.locator("button:has-text('More')")
            count = await more_buttons.count()
            for i in range(count):
                try:
                    if await more_buttons.nth(i).is_visible():
                        await more_buttons.nth(i).click()
                except Exception:
                    pass
            
            # Parse currently visible reviews
            review_elements = await page.query_selector_all('.jftiEf')
            new_found = False
            
            for el in review_elements:
                if len(reviews) >= max_reviews:
                    break
                    
                data_id = await el.get_attribute('data-review-id')
                if not data_id or data_id in parsed_ids:
                    continue
                    
                parsed_ids.add(data_id)
                new_found = True
                
                try:
                    # Reviewer Name
                    name_el = await el.query_selector('.d4r55')
                    name = await name_el.inner_text() if name_el else "Unknown"
                    
                    # Rating (e.g. aria-label="5 stars")
                    rating_el = await el.query_selector('span[role="img"]')
                    rating_text = await rating_el.get_attribute('aria-label') if rating_el else ""
                    rating = 0
                    if rating_text:
                        digits = [int(s) for s in rating_text.split() if s.isdigit()]
                        if digits:
                            rating = digits[0]
                            
                    # Review Text
                    text_el = await el.query_selector('.wiI7pd')
                    text = await text_el.inner_text() if text_el else ""
                    
                    # Relative Time (e.g., "2 months ago")
                    time_el = await el.query_selector('.rsqaWe')
                    time_str = await time_el.inner_text() if time_el else ""
                    
                    reviews.append({
                        "review_id": data_id,
                        "author_name": name,
                        "rating": rating,
                        "text": text,
                        "time": time_str
                    })
                except Exception as e:
                    print(f"Error parsing a review: {e}")
            
            if not new_found:
                consecutive_no_new += 1
            else:
                consecutive_no_new = 0
                
            print(f"Collected {len(reviews)} / {max_reviews} reviews so far...")
            
            if len(reviews) >= max_reviews:
                break
                
            # Scroll down to load more reviews
            if review_elements:
                try:
                    # The scrollable div on Maps often has this specific class combination,
                    # but fallback to scrolling the last review element into view.
                    await page.evaluate('''() => {
                        const scrollContainers = document.querySelectorAll('.m6QErb.DxyBCb.kA9KIf.dS8AEf.ecceSd');
                        if (scrollContainers.length > 1) {
                            scrollContainers[1].scrollBy(0, 5000);
                        } else if (scrollContainers.length > 0) {
                            scrollContainers[0].scrollBy(0, 5000);
                        } else {
                            const reviews = document.querySelectorAll('.jftiEf');
                            if (reviews.length > 0) {
                                reviews[reviews.length - 1].scrollIntoView();
                            }
                        }
                    }''')
                except Exception:
                    pass
                
                # Wait for API to return more reviews
                await page.wait_for_timeout(2000) 
                
        await browser.close()
        return reviews

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Google Maps Reviews by Place ID")
    parser.add_argument("--place_id", type=str, required=True, help="Google Maps Place ID")
    parser.add_argument("--max", type=int, default=50, help="Maximum number of reviews to scrape")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    
    args = parser.parse_args()
    
    results = asyncio.run(scrape_google_maps_reviews(args.place_id, max_reviews=args.max, headless=args.headless))
    
    print("\n--- Scraping Complete ---")
    print(json.dumps(results, indent=2, ensure_ascii=False))
