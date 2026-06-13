# Google Maps Review Scraper & Analyzer

A high-performance, stealthy pipeline for extracting, analyzing, and visualizing Google Maps restaurant reviews. This toolkit helps you discover patterns, extract rich metadata (like reviewer history), run NLP analysis via Large Language Models (LLMs), and detect suspicious "fake review" bursts.

## 🚀 How the Scraping Algorithm Works

The core of the scraper (`scrape_camoufox.py`) relies on **Camoufox** (a stealth browser based on Firefox) driven by **Playwright**.

Instead of interacting with volatile HTML DOM structures, the scraper injects custom JavaScript (`page.evaluate`) directly into the browser context. This does three things:
1. **Performance:** Eliminates the IPC (Inter-Process Communication) bottleneck between Python and the browser, allowing high-speed scrolling and data extraction.
2. **Stealth & Resiliency:** Minimizes bot-detection risks and easily bypasses Google's frequent layout changes.
3. **Rich Data Extraction:** Automatically parses deep metadata, including reviewer histories (`author_reviews_count`, `author_photos_count`), restaurant types, exact timestamps, and full review text.

It saves each restaurant's data into intelligent, conflict-free `.json` files in the `reviews/` folder.

---

## 🛠️ How to Use the System

### 1. Scraping the Reviews
1. Create a `restaurants.txt` (or any `.txt` file) and paste Google Maps URLs or Place IDs, one per line.
2. Run the scraper:
   ```bash
   python scrape_camoufox.py restaurants.txt --max-months 12
   ```
   *This extracts reviews up to 12 months old and saves them into the `reviews/` directory.*

### 2. Preparing the Database
Once you have your JSON files, import them into the SQLite database so the dashboard and analysis tools can read them:
```bash
python import_reviews.py --clean
```
*(The `--clean` flag wipes the old database to prevent duplication of previous runs).*

### 3. (Optional) AI Analysis & Burst Detection
To enrich your data with LLM analysis (extracting sentiment, staff names, dishes, and fake review signals):
```bash
python analyze.py --all
python detect.py
```
*(Note: Ensure you have `GEMINI_API_KEY` set in your `.env` file, or configure Ollama for local processing).*

### 4. Running the Dashboard
Start the interactive Plotly Dash application:
```bash
python app.py
```
Open your browser to `http://localhost:8050` to explore the data.

---

## 💡 Ideas for Future Visualizations

Our enriched dataset opens up several advanced data visualization possibilities. Here are some ideas you could build next:

1. **Reviewer Trust vs. Rating Scatter Plot:**
   - **X-axis:** `author_reviews_count` + `author_photos_count`
   - **Y-axis:** Star Rating
   - **Insight:** Do experienced "Local Guides" rate restaurants more harshly than one-off reviewers? Do 5-star ratings disproportionately come from accounts with 0 photos?

2. **NLP-Driven Word Clouds & Topic Clusters:**
   - Create dynamic word clouds based on the `dishes_mentioned` array.
   - Cross-reference topics (e.g., "service", "food_quality", "price") with sentiment to create a **Strengths & Weaknesses Radar Chart** for each restaurant.

3. **Geospatial Heatmaps:**
   - Map restaurants by their coordinates and use a heatmap overlay to show average `suspicion_score`.
   - **Insight:** Are fake review campaigns geographically clustered around specific districts?

4. **Network Graph of Staff Mentions:**
   - Connect reviewers to the `staff_names` they mention.
   - **Insight:** Detect if a specific subset of low-trust reviewers exclusively praises one specific waiter, highlighting a targeted incentive campaign.

5. **Sentiment Trajectory Timeline:**
   - A smoothed moving-average line chart of review sentiment over the last 12 months.
   - Annotate the chart with points where `in_burst` is True to see if a sudden influx of 5-star reviews artificially propped up a declining sentiment trend.
