"""
Burst Detection — Identifies temporal clusters of suspicious reviews.

Usage:
    python detect.py          # Run burst detection on all analyzed data
    python detect.py --plot   # Show a quick matplotlib plot (debug)
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

import config
from db import get_db, init_db


def detect_bursts(conn, place_id: str, window_days: int = None,
                  min_reviews: int = None) -> list:
    """
    Sliding-window burst detection for a single restaurant.
    Returns a list of burst dicts: {start, end, count, staff_names, review_ids}.
    """
    window_days = window_days or config.BURST_WINDOW_DAYS
    min_reviews = min_reviews or config.BURST_MIN_REVIEWS

    rows = conn.execute("""
        SELECT r.review_id, r.published_timestamp, r.author_reviews_count,
               a.staff_names, a.suspicion_score
        FROM reviews r
        JOIN analysis a ON r.review_id = a.review_id
        WHERE r.place_id = ? AND r.published_timestamp IS NOT NULL
        ORDER BY r.published_timestamp
    """, (place_id,)).fetchall()

    if len(rows) < min_reviews:
        return []

    # Build list of (timestamp, review_id, staff_names, suspicion)
    entries = []
    for r in rows:
        ts = r["published_timestamp"]
        if ts is None:
            continue
        names = json.loads(r["staff_names"]) if r["staff_names"] else []
        entries.append({
            "ts": int(ts),
            "review_id": r["review_id"],
            "staff_names": names,
            "suspicion": r["suspicion_score"] or 0.0,
            "author_reviews": r["author_reviews_count"],
        })

    if not entries:
        return []

    entries.sort(key=lambda x: x["ts"])
    window_seconds = window_days * 86400

    bursts = []
    i = 0
    while i < len(entries):
        window_start = entries[i]["ts"]
        window_end = window_start + window_seconds

        # Collect all reviews in this window
        window_reviews = []
        j = i
        while j < len(entries) and entries[j]["ts"] <= window_end:
            window_reviews.append(entries[j])
            j += 1

        # Check if this window qualifies as a burst
        # A burst needs: enough reviews + elevated suspicion OR staff name clustering
        staff_name_reviews = [r for r in window_reviews if r["staff_names"]]
        avg_suspicion = (
            sum(r["suspicion"] for r in window_reviews) / len(window_reviews)
            if window_reviews else 0
        )

        is_burst = False
        # Condition 1: Many reviews mentioning staff names in short window
        if len(staff_name_reviews) >= min_reviews:
            is_burst = True
        # Condition 2: High density of suspicious reviews
        elif (len(window_reviews) >= min_reviews * 2
              and avg_suspicion >= config.SUSPICION_THRESHOLD):
            is_burst = True

        if is_burst:
            # Collect all staff names mentioned in this burst
            all_names = defaultdict(int)
            for r in window_reviews:
                for name in r["staff_names"]:
                    all_names[name] += 1

            burst = {
                "start": window_start,
                "end": window_end,
                "start_date": datetime.fromtimestamp(window_start).isoformat(),
                "end_date": datetime.fromtimestamp(window_end).isoformat(),
                "count": len(window_reviews),
                "staff_name_count": len(staff_name_reviews),
                "staff_names": dict(all_names),
                "avg_suspicion": round(avg_suspicion, 3),
                "review_ids": [r["review_id"] for r in window_reviews],
            }
            bursts.append(burst)

            # Skip past this window to avoid overlapping bursts
            i = j
        else:
            i += 1

    return bursts


def mark_burst_reviews(conn, bursts: list):
    """Mark reviews that fall within detected burst windows."""
    for burst in bursts:
        for rid in burst["review_ids"]:
            conn.execute(
                "UPDATE analysis SET in_burst = 1 WHERE review_id = ?",
                (rid,)
            )


def run_detection():
    """Run burst detection for all restaurants."""
    with get_db() as conn:
        restaurants = conn.execute(
            "SELECT place_id, name FROM restaurants"
        ).fetchall()

        # Reset all burst flags first
        conn.execute("UPDATE analysis SET in_burst = 0")

        total_bursts = 0
        for rest in restaurants:
            pid = rest["place_id"]
            name = rest["name"]

            bursts = detect_bursts(conn, pid)
            if bursts:
                mark_burst_reviews(conn, bursts)
                total_bursts += len(bursts)
                print(f"\n🔴 {name}: {len(bursts)} burst(s) detected")
                for b in bursts:
                    print(f"   📅 {b['start_date'][:10]} → {b['end_date'][:10]}"
                          f" | {b['count']} reviews"
                          f" | {b['staff_name_count']} mention staff"
                          f" | names: {b['staff_names']}")
            else:
                print(f"🟢 {name}: no bursts detected")

        print(f"\n🎉 Detection complete. {total_bursts} total burst(s) found.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot", action="store_true",
                        help="Show debug plot")
    args = parser.parse_args()

    init_db()
    run_detection()


if __name__ == "__main__":
    main()
