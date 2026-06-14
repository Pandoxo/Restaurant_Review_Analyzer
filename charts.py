"""
Dashboard chart builders — all Plotly figure constructors used by app.py.
"""

import json
import random
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ── Color Constants ────────────────────────────────────────
BG = "#f8f9fa"
CARD_BG = "#ffffff"
GRID_COLOR = "#f1f3f5"
TEXT_COLOR = "#64748b"
TEXT_PRIMARY = "#1e293b"
ACCENT = "#6366f1"
RED = "#ef4444"
GREEN = "#22c55e"
YELLOW = "#eab308"
ORANGE = "#f97316"


def _base_layout(title=""):
    """Shared layout settings for all charts."""
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=TEXT_COLOR, size=12),
        title=dict(text=title, font=dict(size=14, color=TEXT_PRIMARY),
                   x=0, xanchor="left", pad=dict(l=8)),
        margin=dict(l=48, r=24, t=48, b=40),
        xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hoverlabel=dict(bgcolor=CARD_BG, font_size=12,
                        font_family="Inter, sans-serif"),
    )

import plotly.express as px

def build_restaurant_map(summary: list) -> go.Figure:
    """Build a Mapbox scatter plot of restaurants."""
    if not summary:
        return go.Figure(layout=_base_layout("No Map Data"))

    df = pd.DataFrame(summary)
    
    # Check if lat/lng are missing
    if "lat" not in df.columns or "lng" not in df.columns or df["lat"].isnull().all():
        return go.Figure(layout=_base_layout("No Coordinates Available"))
        
    df = df.dropna(subset=["lat", "lng"])
    
    def get_color(p):
        if pd.isna(p): return GREEN
        if p > 10: return RED
        if p > 5: return YELLOW
        return GREEN
        
    df["color"] = df["flagged_pct"].apply(get_color)
    df["size"] = 12
    
    fig = px.scatter_mapbox(
        df, lat="lat", lon="lng", hover_name="name",
        hover_data={"place_id": False, "lat": False, "lng": False, "flagged_pct": True, "analyzed_count": True, "color": False, "size": False},
        color="color", color_discrete_map="identity",
        size="size", size_max=12, zoom=11.5,
        center=dict(lat=df["lat"].mean(), lon=df["lng"].mean())
    )
    
    fig.update_layout(
        mapbox_style="carto-positron",
        margin={"r":0,"t":0,"l":0,"b":0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        clickmode="event+select"
    )
    
    # Add customdata to trace so we can grab place_id on click
    fig.update_traces(customdata=df[["place_id"]])
    return fig


def build_timeline_chart(reviews: list) -> go.Figure:
    """
    Timeline chart showing review volume over time with burst windows
    and staff-name mentions highlighted.
    """
    if not reviews:
        return go.Figure(layout=_base_layout("No review data available"))

    df = pd.DataFrame(reviews)
    df["date"] = pd.to_datetime(df["published_timestamp"], unit="s", errors="coerce")
    df = df.dropna(subset=["date"])
    df["month"] = df["date"].dt.to_period("M").dt.start_time

    # Monthly counts
    monthly = df.groupby("month").agg(
        total=("review_id", "count"),
        suspicious=("suspicion_score", lambda x: (pd.to_numeric(x, errors="coerce").fillna(0) >= 0.6).sum()),
        with_staff=("staff_names", lambda x: sum(
            1 for s in x
            if isinstance(s, str) and s.strip() and s != "[]"
        )),
        in_burst=("in_burst", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum()),
    ).reset_index()

    fig = go.Figure()

    # Normal reviews (background)
    fig.add_trace(go.Bar(
        x=monthly["month"], y=monthly["total"],
        name="All Reviews",
        marker_color="rgba(99, 102, 241, 0.25)",
        marker_line=dict(width=0),
        hovertemplate="%{x|%B %Y}<br>%{y} reviews<extra></extra>",
    ))

    # Suspicious reviews overlay
    fig.add_trace(go.Bar(
        x=monthly["month"], y=monthly["suspicious"],
        name="Suspicious",
        marker_color="rgba(239, 68, 68, 0.7)",
        marker_line=dict(width=0),
        hovertemplate="%{x|%B %Y}<br>%{y} suspicious<extra></extra>",
    ))

    # Burst markers
    burst_months = monthly[monthly["in_burst"] > 0]
    if not burst_months.empty:
        fig.add_trace(go.Scatter(
            x=burst_months["month"],
            y=burst_months["total"] + 1,
            mode="markers",
            name="Burst Window",
            marker=dict(size=10, color=ORANGE, symbol="triangle-down",
                        line=dict(width=1, color="#fff")),
            hovertemplate="%{x|%B %Y}<br>Burst detected<extra></extra>",
        ))

    layout = _base_layout("📅 Review Timeline — Volume & Suspicious Activity")
    layout["barmode"] = "overlay"
    layout["xaxis"]["title"] = ""
    layout["yaxis"]["title"] = "Reviews per Month"
    layout["height"] = 380
    fig.update_layout(**layout)

    return fig


def build_staff_name_chart(reviews: list) -> go.Figure:
    """Bar chart of staff name mention frequency."""
    name_counts = Counter()
    for r in reviews:
        names = r.get("staff_names", "[]")
        if isinstance(names, str):
            try:
                names = json.loads(names)
            except json.JSONDecodeError:
                names = []
        for name in names:
            name_counts[name] += 1

    if not name_counts:
        return go.Figure(layout=_base_layout("No staff names detected"))

    # Top 15 names
    top = name_counts.most_common(15)
    names, counts = zip(*top)

    fig = go.Figure(go.Bar(
        x=list(counts), y=list(names),
        orientation="h",
        marker=dict(
            color=list(counts),
            colorscale="Sunset",
            line=dict(width=0)
        ),
        hovertemplate="%{y}: %{x} mentions<extra></extra>",
    ))

    layout = _base_layout("👤 Staff Name Frequency")
    layout["height"] = max(300, len(top) * 32 + 80)
    layout["yaxis"]["autorange"] = "reversed"
    layout["xaxis"]["title"] = "Mentions"
    fig.update_layout(**layout)

    return fig



def build_sentiment_chart(reviews: list) -> go.Figure:
    """Donut chart of sentiment distribution."""
    sentiments = Counter()
    for r in reviews:
        s = r.get("overall_sentiment", "neutral")
        if s:
            sentiments[s] += 1

    if not sentiments:
        return go.Figure(layout=_base_layout("No sentiment data"))

    labels = list(sentiments.keys())
    values = list(sentiments.values())
    color_map = {
        "positive": GREEN, "negative": RED,
        "neutral": "#64748b", "mixed": YELLOW
    }
    colors = [color_map.get(l, ACCENT) for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color=BG, width=2)),
        textinfo="percent",
        textposition="inside",
        textfont=dict(size=12, color="white"),
        hovertemplate="%{label}: %{value} reviews (%{percent})<extra></extra>",
    ))

    layout = _base_layout("💬 Sentiment Distribution")
    layout["height"] = 320
    layout["showlegend"] = True
    layout["legend"] = dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=0.9)
    fig.update_layout(**layout)

    return fig


def build_suspicion_histogram(reviews: list) -> go.Figure:
    """Histogram of suspicion scores across all reviews."""
    scores = [r.get("suspicion_score", 0) for r in reviews if r.get("suspicion_score") is not None]

    if not scores:
        return go.Figure(layout=_base_layout("No suspicion scores"))

    fig = go.Figure(go.Histogram(
        x=scores,
        nbinsx=20,
        marker_color=ACCENT,
        marker_line=dict(width=1, color="rgba(255,255,255,0.1)"),
        hovertemplate="Score: %{x:.2f}<br>Count: %{y}<extra></extra>",
    ))

    # Threshold line
    fig.add_vline(x=0.6, line_dash="dash", line_color=RED, line_width=2,
                  annotation_text="Threshold", annotation_font_color=RED)

    layout = _base_layout("🎯 Suspicion Score Distribution")
    layout["xaxis"]["title"] = "Suspicion Score"
    layout["yaxis"]["title"] = "Number of Reviews"
    layout["height"] = 320
    fig.update_layout(**layout)

    return fig


def build_depth_chart(reviews: list) -> go.Figure:
    """Bar chart comparing review depth for suspicious vs clean reviews."""
    depths = {"shallow": 0, "moderate": 0, "detailed": 0}
    depths_sus = {"shallow": 0, "moderate": 0, "detailed": 0}

    for r in reviews:
        d = r.get("review_depth", "")
        if d in depths:
            depths[d] += 1
            if r.get("suspicion_score", 0) >= 0.6:
                depths_sus[d] += 1

    cats = list(depths.keys())
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=cats, y=[depths[c] for c in cats],
        name="All Reviews", marker_color="rgba(99,102,241,0.4)",
    ))
    fig.add_trace(go.Bar(
        x=cats, y=[depths_sus[c] for c in cats],
        name="Suspicious", marker_color="rgba(239,68,68,0.7)",
    ))

    layout = _base_layout("📝 Review Depth: All vs Suspicious")
    layout["barmode"] = "group"
    layout["height"] = 320
    fig.update_layout(**layout)

    return fig

def build_trust_scatter_chart(reviews: list) -> go.Figure:
    """Scatter plot of reviewer experience vs star rating."""
    if not reviews:
        return go.Figure(layout=_base_layout("No trust data"))

    # Extract x and y
    data = []
    for r in reviews:
        try:
            rev_count = int(r.get("author_reviews_count") or 0)
        except ValueError:
            rev_count = 0
            
        try:
            photo_count = int(r.get("author_photos_count") or 0)
        except ValueError:
            photo_count = 0
            
        try:
            rating = float(r.get("rating") or 0)
        except ValueError:
            rating = 0
            
        if rating == 0:
            continue

        try:
            suspicion = float(r.get("suspicion_score") or 0)
        except ValueError:
            suspicion = 0
        
        is_suspicious = suspicion >= 0.6
        
        # We add 1 to trust score for log scale so 0 becomes 1 (log(1) = 0)
        data.append({
            "trust_score": rev_count + photo_count,
            "log_trust_score": max(rev_count + photo_count, 0.5), # avoid 0 for log axis
            "rating": rating,
            "jittered_rating": rating + random.uniform(-0.2, 0.2),
            "is_suspicious": is_suspicious
        })

    if not data:
        return go.Figure(layout=_base_layout("No trust data"))
        
    df = pd.DataFrame(data)

    fig = go.Figure()
    
    clean_df = df[~df["is_suspicious"]]
    fig.add_trace(go.Scatter(
        x=clean_df["log_trust_score"],
        y=clean_df["jittered_rating"],
        mode="markers",
        name="Clean",
        marker=dict(color=ACCENT, size=6, opacity=0.5, line=dict(width=0)),
        hovertemplate="Trust (Reviews+Photos): %{customdata[0]}<br>Rating: %{customdata[1]}<extra></extra>",
        customdata=clean_df[["trust_score", "rating"]]
    ))

    sus_df = df[df["is_suspicious"]]
    if not sus_df.empty:
        fig.add_trace(go.Scatter(
            x=sus_df["log_trust_score"],
            y=sus_df["jittered_rating"],
            mode="markers",
            name="Suspicious",
            marker=dict(color=RED, size=8, opacity=0.8, line=dict(width=1, color=CARD_BG)),
            hovertemplate="Trust (Reviews+Photos): %{customdata[0]}<br>Rating: %{customdata[1]}<extra></extra>",
            customdata=sus_df[["trust_score", "rating"]]
        ))
        
    layout = _base_layout("⚖️ Reviewer Trust vs. Rating")
    layout["xaxis"]["title"] = "Reviewer Experience (Reviews + Photos) [Log Scale]"
    layout["xaxis"]["type"] = "log"
    layout["yaxis"]["title"] = "Star Rating"
    layout["yaxis"]["tickvals"] = [1, 2, 3, 4, 5]
    layout["yaxis"]["range"] = [0.5, 5.5]
    layout["height"] = 320
    fig.update_layout(**layout)

    return fig


def build_topic_sentiments_chart(reviews: list) -> go.Figure:
    """Grouped bar chart for topic sentiments (positive vs negative)."""
    topic_counts = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0})
    for r in reviews:
        ts = r.get("topic_sentiments", "{}")
        if not ts:
            continue
        if isinstance(ts, str):
            try:
                ts = json.loads(ts)
            except json.JSONDecodeError:
                ts = {}
        for topic, sentiment in ts.items():
            if isinstance(sentiment, str):
                s = sentiment.lower()
                if s in ["positive", "negative", "neutral", "mixed"]:
                    topic_counts[topic][s] += 1
                else:
                    topic_counts[topic]["neutral"] += 1

    if not topic_counts:
        return go.Figure(layout=_base_layout("No topic sentiments detected"))

    # Sort topics by total mentions
    sorted_topics = sorted(topic_counts.keys(), key=lambda t: sum(topic_counts[t].values()), reverse=True)[:15]
    
    positives = [topic_counts[t].get("positive", 0) for t in sorted_topics]
    neutrals = [topic_counts[t].get("neutral", 0) for t in sorted_topics]
    negatives = [topic_counts[t].get("negative", 0) for t in sorted_topics]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=sorted_topics, x=positives,
        orientation="h",
        name="Positive", marker_color=GREEN,
    ))
    fig.add_trace(go.Bar(
        y=sorted_topics, x=neutrals,
        orientation="h",
        name="Neutral", marker_color="#94a3b8",
    ))
    fig.add_trace(go.Bar(
        y=sorted_topics, x=negatives,
        orientation="h",
        name="Negative", marker_color=RED,
    ))
    
    layout = _base_layout("🗣️ Topic Sentiments (100% Stacked)")
    layout["barmode"] = "stack"
    layout["barnorm"] = "percent"
    layout["xaxis"]["title"] = "Percentage (%)"
    layout["yaxis"]["title"] = "Topic"
    layout["yaxis"]["autorange"] = "reversed"
    fig.update_layout(**layout)
    return fig


def build_dishes_chart(reviews: list) -> go.Figure:
    """Horizontal bar chart for most mentioned dishes with sentiment."""
    dish_counts = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0})
    for r in reviews:
        dishes = r.get("dishes_mentioned", "[]")
        if not dishes:
            continue
        sentiment = r.get("overall_sentiment", "neutral")
        if sentiment not in ["positive", "negative", "neutral"]:
            sentiment = "neutral"
            
        if isinstance(dishes, str):
            try:
                dishes = json.loads(dishes)
            except json.JSONDecodeError:
                dishes = []
        if isinstance(dishes, list):
            for dish in dishes:
                if isinstance(dish, str) and dish.strip():
                    dish_counts[dish.strip().capitalize()][sentiment] += 1

    if not dish_counts:
        return go.Figure(layout=_base_layout("No dishes mentioned"))

    # Top 10 dishes
    sorted_dishes = sorted(dish_counts.keys(), key=lambda d: sum(dish_counts[d].values()), reverse=True)[:10]
    
    positives = [dish_counts[d]["positive"] for d in sorted_dishes]
    neutrals = [dish_counts[d]["neutral"] for d in sorted_dishes]
    negatives = [dish_counts[d]["negative"] for d in sorted_dishes]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=sorted_dishes, x=positives,
        orientation="h",
        name="Positive", marker_color=GREEN,
    ))
    fig.add_trace(go.Bar(
        y=sorted_dishes, x=neutrals,
        orientation="h",
        name="Neutral", marker_color="#94a3b8",
    ))
    fig.add_trace(go.Bar(
        y=sorted_dishes, x=negatives,
        orientation="h",
        name="Negative", marker_color=RED,
    ))

    layout = _base_layout("🍔 Most Mentioned Dishes by Sentiment (100% Stacked)")
    layout["barmode"] = "stack"
    layout["barnorm"] = "percent"
    layout["yaxis"]["autorange"] = "reversed"
    layout["xaxis"]["title"] = "Percentage (%)"
    layout["yaxis"]["title"] = "Dish"
    fig.update_layout(**layout)

    return fig


def build_customer_reviews_histogram(reviews: list) -> go.Figure:
    """Histogram of author_reviews_count for all customers."""
    if not reviews:
        return go.Figure(layout=_base_layout("No customer data"))

    data = []
    seen_authors = set()
    for r in reviews:
        name = r.get("author_name")
        if not name or name in seen_authors:
            continue
        seen_authors.add(name)
        
        try:
            val = int(r.get("author_reviews_count") or 0)
            rev_count = max(val, 1) # Prevent log(0)
        except ValueError:
            rev_count = 1
            
        data.append(rev_count)

    if not data:
        return go.Figure(layout=_base_layout("No customer data"))

    fig = go.Figure(go.Histogram(
        x=data,
        nbinsx=50,
        marker_color=ACCENT,
        opacity=0.75,
        hovertemplate="Review Count: %{x}<br>Users: %{y}<extra></extra>"
    ))

    layout = _base_layout("📊 Distribution of User Review Counts")
    layout["xaxis"]["title"] = "Number of Reviews Written by User (Log Scale)"
    layout["yaxis"]["title"] = "Number of Users (Log Scale)"
    layout["xaxis"]["type"] = "log"
    layout["yaxis"]["type"] = "log"
    fig.update_layout(**layout)
    return fig


def build_customer_scatter_chart(reviews: list) -> go.Figure:
    """Scatter plot of author_reviews_count vs author_photos_count."""
    if not reviews:
        return go.Figure(layout=_base_layout("No customer data"))

    import random
    data = []
    seen_authors = set()
    for r in reviews:
        name = r.get("author_name")
        if not name or name in seen_authors:
            continue
        seen_authors.add(name)
        
        try:
            # Jitter the integers slightly so points don't perfectly overlap
            base_rev = max(int(r.get("author_reviews_count") or 0), 1)
            rev_count = base_rev * random.uniform(0.95, 1.05)
        except ValueError:
            rev_count = 1
            
        try:
            base_photo = max(int(r.get("author_photos_count") or 0), 1)
            photo_count = base_photo * random.uniform(0.95, 1.05)
        except ValueError:
            photo_count = 1
            
        try:
            suspicion = float(r.get("suspicion_score") or 0)
        except ValueError:
            suspicion = 0
            
        data.append({
            "name": name,
            "rev_count": rev_count,
            "photo_count": photo_count,
            "is_suspicious": suspicion >= 0.6
        })

    if not data:
        return go.Figure(layout=_base_layout("No customer data"))

    df = pd.DataFrame(data)
    fig = go.Figure()

    clean_df = df[~df["is_suspicious"]]
    fig.add_trace(go.Scatter(
        x=clean_df["rev_count"],
        y=clean_df["photo_count"],
        mode="markers",
        name="Clean",
        text=clean_df["name"],
        marker=dict(color=ACCENT, size=6, opacity=0.3, line=dict(width=0)),
        hovertemplate="%{text}<br>Reviews: %{x:.0f}<br>Photos: %{y:.0f}<extra></extra>"
    ))

    sus_df = df[df["is_suspicious"]]
    if not sus_df.empty:
        fig.add_trace(go.Scatter(
            x=sus_df["rev_count"],
            y=sus_df["photo_count"],
            mode="markers",
            name="Suspicious Reviewer",
            text=sus_df["name"],
            marker=dict(color=RED, size=8, opacity=0.8, line=dict(width=1, color=CARD_BG)),
            hovertemplate="%{text}<br>Reviews: %{x:.0f}<br>Photos: %{y:.0f}<extra></extra>"
        ))

    layout = _base_layout("📸 Review Count vs Photo Count")
    layout["xaxis"]["title"] = "Total Reviews (Log Scale)"
    layout["xaxis"]["type"] = "log"
    layout["yaxis"]["title"] = "Total Photos (Log Scale)"
    layout["yaxis"]["type"] = "log"
    layout["height"] = 400
    fig.update_layout(**layout)
    return fig

def build_rating_distribution_chart(reviews: list) -> go.Figure:
    """Show the distribution of 1 to 5 star ratings."""
    if not reviews:
        return go.Figure(layout=_base_layout("⭐ Rating Distribution"))
        
    ratings = [r.get("rating") for r in reviews if r.get("rating")]
    if not ratings:
        return go.Figure(layout=_base_layout("⭐ Rating Distribution"))
        
    counts = pd.Series(ratings).value_counts().reindex([1, 2, 3, 4, 5], fill_value=0)
    
    fig = go.Figure(data=[
        go.Bar(
            x=[f"{i}" for i in range(1, 6)],
            y=counts.values,
            marker_color=[RED, ORANGE, YELLOW, GREEN, GREEN]
        )
    ])
    
    layout = _base_layout("⭐ Rating Distribution")
    layout["yaxis"]["title"] = "Count"
    layout["height"] = 300
    fig.update_layout(**layout)
    
    return fig
