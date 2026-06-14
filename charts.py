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
BG = "#0a0e17"
CARD_BG = "#1a1f2e"
GRID_COLOR = "#1e2538"
TEXT_COLOR = "#8892a8"
TEXT_PRIMARY = "#e8ecf4"
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
    df["week"] = df["date"].dt.to_period("W").dt.start_time

    # Weekly counts
    weekly = df.groupby("week").agg(
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
        x=weekly["week"], y=weekly["total"],
        name="All Reviews",
        marker_color="rgba(99, 102, 241, 0.25)",
        marker_line=dict(width=0),
        hovertemplate="%{x|%b %d, %Y}<br>%{y} reviews<extra></extra>",
    ))

    # Suspicious reviews overlay
    fig.add_trace(go.Bar(
        x=weekly["week"], y=weekly["suspicious"],
        name="Suspicious",
        marker_color="rgba(239, 68, 68, 0.7)",
        marker_line=dict(width=0),
        hovertemplate="%{x|%b %d, %Y}<br>%{y} suspicious<extra></extra>",
    ))

    # Burst markers
    burst_weeks = weekly[weekly["in_burst"] > 0]
    if not burst_weeks.empty:
        fig.add_trace(go.Scatter(
            x=burst_weeks["week"],
            y=burst_weeks["total"] + 1,
            mode="markers",
            name="Burst Window",
            marker=dict(size=10, color=ORANGE, symbol="triangle-down",
                        line=dict(width=1, color="#fff")),
            hovertemplate="%{x|%b %d, %Y}<br>Burst detected<extra></extra>",
        ))

    layout = _base_layout("📅 Review Timeline — Volume & Suspicious Activity")
    layout["barmode"] = "overlay"
    layout["xaxis"]["title"] = ""
    layout["yaxis"]["title"] = "Reviews per Week"
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

    colors = [RED if c >= 5 else YELLOW if c >= 3 else ACCENT for c in counts]

    fig = go.Figure(go.Bar(
        x=list(counts), y=list(names),
        orientation="h",
        marker_color=colors,
        marker_line=dict(width=0),
        hovertemplate="%{y}: %{x} mentions<extra></extra>",
    ))

    layout = _base_layout("👤 Staff Name Frequency")
    layout["height"] = max(300, len(top) * 32 + 80)
    layout["yaxis"]["autorange"] = "reversed"
    layout["xaxis"]["title"] = "Mentions"
    fig.update_layout(**layout)

    return fig


def build_name_timeline(reviews: list) -> go.Figure:
    """Per-name timeline showing when each staff name was mentioned."""
    name_dates = defaultdict(list)
    for r in reviews:
        names = r.get("staff_names", "[]")
        if isinstance(names, str):
            try:
                names = json.loads(names)
            except json.JSONDecodeError:
                names = []
        ts = r.get("published_timestamp")
        if not ts or not names:
            continue
        dt = datetime.fromtimestamp(int(ts))
        for name in names:
            name_dates[name].append(dt)

    if not name_dates:
        return go.Figure(layout=_base_layout("No staff name timeline data"))

    # Sort by total count
    sorted_names = sorted(name_dates.keys(),
                          key=lambda n: len(name_dates[n]), reverse=True)[:10]

    fig = go.Figure()
    palette = ["#6366f1", "#a855f7", "#ec4899", "#f97316", "#eab308",
               "#22c55e", "#06b6d4", "#8b5cf6", "#f43f5e", "#14b8a6"]

    for i, name in enumerate(sorted_names):
        dates = name_dates[name]
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=dates,
            y=[name] * len(dates),
            mode="markers",
            name=f"{name} ({len(dates)})",
            marker=dict(size=8, color=color, opacity=0.8,
                        line=dict(width=1, color="rgba(255,255,255,0.3)")),
            hovertemplate=f"{name}<br>%{{x|%b %d, %Y}}<extra></extra>",
        ))

    layout = _base_layout("📊 Staff Name Mentions Over Time")
    layout["height"] = max(300, len(sorted_names) * 40 + 100)
    layout["showlegend"] = True
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
        textinfo="label+percent",
        textfont=dict(size=12, color=TEXT_PRIMARY),
        hovertemplate="%{label}: %{value} reviews (%{percent})<extra></extra>",
    ))

    layout = _base_layout("💬 Sentiment Distribution")
    layout["height"] = 320
    layout["showlegend"] = False
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
