"""
Database module — SQLite schema creation and helper functions.
"""

import sqlite3
import json
from contextlib import contextmanager
from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS restaurants (
                place_id       TEXT PRIMARY KEY,
                name           TEXT NOT NULL,
                type           TEXT,
                address        TEXT,
                rating         REAL,
                total_reviews  INTEGER,
                lat            REAL,
                lng            REAL,
                fetched_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                place_id            TEXT NOT NULL,
                review_id           TEXT UNIQUE,
                author_name         TEXT,
                author_url          TEXT,
                author_reviews_count INTEGER,
                author_photos_count  INTEGER,
                rating              INTEGER,
                text                TEXT,
                published_at        TEXT,
                published_timestamp INTEGER,
                language            TEXT,
                fetched_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (place_id) REFERENCES restaurants(place_id)
            );

            CREATE TABLE IF NOT EXISTS analysis (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id           TEXT UNIQUE,
                place_id            TEXT NOT NULL,
                overall_sentiment   TEXT,
                staff_names         TEXT,  -- JSON array
                dishes_mentioned    TEXT,  -- JSON array
                topic_sentiments    TEXT,  -- JSON object
                review_depth        TEXT,  -- "shallow", "moderate", "detailed"
                specificity_score   INTEGER,
                fake_signals        TEXT,  -- JSON array
                suspicion_score     REAL DEFAULT 0.0,
                in_burst            INTEGER DEFAULT 0,
                analyzed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (review_id) REFERENCES reviews(review_id),
                FOREIGN KEY (place_id) REFERENCES restaurants(place_id)
            );

            CREATE INDEX IF NOT EXISTS idx_reviews_place
                ON reviews(place_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_timestamp
                ON reviews(published_timestamp);
            CREATE INDEX IF NOT EXISTS idx_analysis_place
                ON analysis(place_id);
            CREATE INDEX IF NOT EXISTS idx_analysis_suspicion
                ON analysis(suspicion_score);
        """)
    print("✅ Database initialized.")


def insert_restaurant(conn, restaurant: dict):
    """Insert or update a restaurant record."""
    conn.execute("""
        INSERT OR REPLACE INTO restaurants
            (place_id, name, type, address, rating, total_reviews, lat, lng)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        restaurant["place_id"],
        restaurant["name"],
        restaurant.get("type", ""),
        restaurant.get("address", ""),
        restaurant.get("rating"),
        restaurant.get("total_reviews"),
        restaurant.get("lat"),
        restaurant.get("lng"),
    ))


def insert_review(conn, review: dict):
    """Insert a review, skipping duplicates."""
    try:
        conn.execute("""
            INSERT OR IGNORE INTO reviews
                (place_id, review_id, author_name, author_url,
                 author_reviews_count, author_photos_count, rating, text, published_at,
                 published_timestamp, language)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            review["place_id"],
            review["review_id"],
            review.get("author_name", ""),
            review.get("author_url", ""),
            review.get("author_reviews_count"),
            review.get("author_photos_count"),
            review.get("rating"),
            review.get("text", ""),
            review.get("published_at", ""),
            review.get("published_timestamp"),
            review.get("language", ""),
        ))
    except sqlite3.IntegrityError:
        pass  # duplicate, skip


def insert_analysis(conn, analysis: dict):
    """Insert or update analysis results for a review."""
    conn.execute("""
        INSERT OR REPLACE INTO analysis
            (review_id, place_id, overall_sentiment, staff_names, dishes_mentioned,
             topic_sentiments, review_depth, specificity_score, fake_signals,
             suspicion_score, in_burst)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        analysis["review_id"],
        analysis["place_id"],
        analysis.get("overall_sentiment", ""),
        json.dumps(analysis.get("staff_names", []), ensure_ascii=False),
        json.dumps(analysis.get("dishes_mentioned", []), ensure_ascii=False),
        json.dumps(analysis.get("topic_sentiments", {}), ensure_ascii=False),
        analysis.get("review_depth", ""),
        analysis.get("specificity_score", 0),
        json.dumps(analysis.get("fake_signals", []), ensure_ascii=False),
        analysis.get("suspicion_score", 0.0),
        analysis.get("in_burst", 0),
    ))


def get_all_restaurants(conn) -> list:
    """Return all restaurants as dicts."""
    rows = conn.execute("SELECT * FROM restaurants ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_reviews_for_restaurant(conn, place_id: str) -> list:
    """Return all reviews for a given restaurant."""
    rows = conn.execute(
        "SELECT * FROM reviews WHERE place_id = ? ORDER BY published_timestamp",
        (place_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_analysis_for_restaurant(conn, place_id: str) -> list:
    """Return analysis results joined with review data for a restaurant."""
    rows = conn.execute("""
        SELECT r.*, a.overall_sentiment, a.staff_names, a.dishes_mentioned,
               a.topic_sentiments, a.review_depth, a.specificity_score,
               a.fake_signals, a.suspicion_score, a.in_burst
        FROM reviews r
        LEFT JOIN analysis a ON r.review_id = a.review_id
        WHERE r.place_id = ?
        ORDER BY r.published_timestamp
    """, (place_id,)).fetchall()
    return [dict(r) for r in rows]


def get_unanalyzed_reviews(conn, limit: int = 100) -> list:
    """Return reviews that haven't been analyzed yet."""
    rows = conn.execute("""
        SELECT r.* FROM reviews r
        LEFT JOIN analysis a ON r.review_id = a.review_id
        WHERE a.review_id IS NULL AND r.text IS NOT NULL AND r.text != ''
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_dashboard_summary(conn) -> list:
    """Return per-restaurant summary stats for the dashboard."""
    rows = conn.execute("""
        SELECT
            rest.place_id,
            rest.name,
            rest.type,
            rest.rating,
            rest.total_reviews,
            rest.lat,
            rest.lng,
            COUNT(a.review_id) AS analyzed_count,
            SUM(CASE WHEN a.suspicion_score >= 0.6 THEN 1 ELSE 0 END) AS flagged_count,
            ROUND(
                100.0 * SUM(CASE WHEN a.suspicion_score >= 0.6 THEN 1 ELSE 0 END)
                / MAX(COUNT(a.review_id), 1), 1
            ) AS flagged_pct,
            SUM(CASE WHEN a.in_burst = 1 THEN 1 ELSE 0 END) AS burst_count
        FROM restaurants rest
        LEFT JOIN analysis a ON rest.place_id = a.place_id
        GROUP BY rest.place_id
        ORDER BY flagged_pct DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_customers_for_restaurant(conn, place_id: str) -> list:
    """Return customer aggregations for a given restaurant."""
    rows = conn.execute("""
        SELECT 
            author_name,
            MAX(author_reviews_count) as author_reviews_count,
            MAX(author_photos_count) as author_photos_count,
            GROUP_CONCAT(review_id, ', ') as review_ids
        FROM reviews
        WHERE place_id = ?
        GROUP BY author_name
        ORDER BY author_reviews_count DESC
    """, (place_id,)).fetchall()
    return [dict(r) for r in rows]


def get_all_reviews_with_analysis(conn) -> list:
    """Return analysis results joined with review data for ALL restaurants globally."""
    rows = conn.execute("""
        SELECT r.*, a.overall_sentiment, a.staff_names, a.dishes_mentioned,
               a.topic_sentiments, a.review_depth, a.specificity_score,
               a.fake_signals, a.suspicion_score, a.in_burst
        FROM reviews r
        LEFT JOIN analysis a ON r.review_id = a.review_id
        ORDER BY r.published_timestamp DESC
    """).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
