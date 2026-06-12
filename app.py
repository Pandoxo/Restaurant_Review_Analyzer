"""
Dash Dashboard — Main application entry point.

Usage:
    python app.py              # Start dashboard on http://localhost:8050
    python app.py --port 8080  # Custom port
"""

import argparse
import json

import dash
from dash import dcc, html, dash_table, Input, Output, State
import pandas as pd

from db import get_db, init_db, get_dashboard_summary, get_analysis_for_restaurant
from charts import (
    build_timeline_chart,
    build_staff_name_chart,
    build_name_timeline,
    build_sentiment_chart,
    build_suspicion_histogram,
    build_depth_chart,
)

app = dash.Dash(
    __name__,
    title="Poznań Review Analyzer",
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"},
        {"name": "description",
         "content": "Analyze restaurant reviews in Poznań for patterns and anomalies"},
    ],
)


def get_summary_data():
    """Load dashboard summary from DB."""
    with get_db() as conn:
        return get_dashboard_summary(conn)


def get_restaurant_options():
    """Build dropdown options from DB."""
    data = get_summary_data()
    return [
        {"label": f"{r['name']}  ⭐{r['rating'] or '?'}  "
                  f"({r['analyzed_count'] or 0} analyzed)",
         "value": r["place_id"]}
        for r in data
    ]


def make_stat_card(value, label, color="#6366f1"):
    """Create a stat card HTML element."""
    return html.Div([
        html.Div(str(value), className="stat-value",
                 style={"color": color}),
        html.Div(label, className="stat-label"),
    ], className="stat-card")


def badge_class(pct):
    """Return badge class based on flagged percentage."""
    if pct is None or pct < 5:
        return "badge badge-clean"
    elif pct < 15:
        return "badge badge-moderate"
    return "badge badge-suspicious"


def badge_text(pct):
    if pct is None or pct < 5:
        return "🟢 Clean"
    elif pct < 15:
        return "🟡 Moderate"
    return "🔴 Suspicious"


# ═══════════════════════════════════════════════════════════════
# Layout
# ═══════════════════════════════════════════════════════════════

app.layout = html.Div([
    # Header
    html.Div([
        html.Div([
            html.H1("🍽️ Poznań Review Analyzer"),
            html.Div("Detect fake review patterns in restaurant reviews",
                     className="subtitle"),
        ]),
        html.Div([
            html.Div("Proof of Concept", className="badge badge-moderate"),
        ]),
    ], className="app-header"),

    # Stats Row
    html.Div(id="stats-row", className="stats-row"),

    # Restaurant Selector
    html.Div([
        html.Label("Select Restaurant"),
        dcc.Dropdown(
            id="restaurant-selector",
            options=get_restaurant_options(),
            placeholder="Choose a restaurant to analyze...",
            clearable=False,
            className="restaurant-dropdown",
        ),
    ], className="selector-container"),

    # Tabs
    dcc.Tabs(id="main-tabs", value="tab-overview", children=[
        dcc.Tab(label="📊 Overview", value="tab-overview",
                className="custom-tab", selected_className="custom-tab--selected"),
        dcc.Tab(label="📅 Timeline", value="tab-timeline",
                className="custom-tab", selected_className="custom-tab--selected"),
        dcc.Tab(label="👤 Staff Names", value="tab-names",
                className="custom-tab", selected_className="custom-tab--selected"),
        dcc.Tab(label="🔍 Review Explorer", value="tab-explorer",
                className="custom-tab", selected_className="custom-tab--selected"),
    ], className="custom-tabs"),

    # Tab Content
    html.Div(id="tab-content"),

], className="app-container")


# ═══════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════

@app.callback(
    Output("stats-row", "children"),
    Input("restaurant-selector", "value"),
)
def update_stats(place_id):
    """Update the top stats row."""
    summary = get_summary_data()

    if not summary:
        return [make_stat_card("—", "No Data")]

    if place_id:
        # Show stats for selected restaurant
        rest = next((r for r in summary if r["place_id"] == place_id), None)
        if rest:
            pct = rest["flagged_pct"] or 0
            return [
                make_stat_card(rest["analyzed_count"] or 0, "Reviews Analyzed",
                               "#6366f1"),
                make_stat_card(rest["flagged_count"] or 0, "Flagged Reviews",
                               "#ef4444" if rest["flagged_count"] else "#22c55e"),
                make_stat_card(f"{pct}%", "Flagged Rate",
                               "#ef4444" if pct > 10 else "#eab308" if pct > 5
                               else "#22c55e"),
                make_stat_card(rest["burst_count"] or 0, "In Burst Windows",
                               "#f97316" if rest["burst_count"] else "#64748b"),
                make_stat_card(f"⭐ {rest['rating'] or '?'}", "Google Rating",
                               "#eab308"),
            ]

    # Global stats
    total_analyzed = sum(r["analyzed_count"] or 0 for r in summary)
    total_flagged = sum(r["flagged_count"] or 0 for r in summary)
    total_bursts = sum(r["burst_count"] or 0 for r in summary)
    pct = round(100 * total_flagged / max(total_analyzed, 1), 1)

    return [
        make_stat_card(len(summary), "Restaurants", "#6366f1"),
        make_stat_card(total_analyzed, "Reviews Analyzed", "#a855f7"),
        make_stat_card(total_flagged, "Flagged Reviews",
                       "#ef4444" if total_flagged else "#22c55e"),
        make_stat_card(f"{pct}%", "Overall Flag Rate",
                       "#ef4444" if pct > 10 else "#22c55e"),
        make_stat_card(total_bursts, "Burst Reviews", "#f97316"),
    ]


@app.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "value"),
    Input("restaurant-selector", "value"),
)
def render_tab(tab, place_id):
    """Render the selected tab content."""

    if not place_id:
        # Show restaurant grid for selection
        summary = get_summary_data()
        if not summary:
            return html.Div([
                html.Div("📭", className="icon"),
                html.P("No data yet. Run the pipeline first:"),
                html.Pre("python collect.py\npython analyze.py --all\npython detect.py",
                         style={"color": "#6366f1", "marginTop": "12px"}),
            ], className="empty-state")

        cards = []
        for r in summary:
            pct = r["flagged_pct"] or 0
            cards.append(html.Div([
                html.Div(r["name"], className="restaurant-name"),
                html.Div([
                    html.Span(f"⭐ {r['rating'] or '?'}  |  "
                              f"{r['analyzed_count'] or 0} reviews"),
                    html.Span(badge_text(pct), className=badge_class(pct)),
                ], className="restaurant-meta"),
            ], className="restaurant-card"))

        return html.Div([
            html.Div("Select a restaurant above to see detailed analysis",
                     style={"color": "#8892a8", "marginBottom": "16px",
                            "fontSize": "0.9rem"}),
            html.Div(cards, className="restaurant-grid"),
        ])

    # Load data for selected restaurant
    with get_db() as conn:
        reviews = get_analysis_for_restaurant(conn, place_id)

    if not reviews:
        return html.Div([
            html.Div("📭", className="icon"),
            html.P("No analyzed reviews for this restaurant yet."),
        ], className="empty-state")

    if tab == "tab-overview":
        return html.Div([
            html.Div([
                html.Div([
                    dcc.Graph(figure=build_sentiment_chart(reviews),
                              config={"displayModeBar": False}),
                ], className="card"),
                html.Div([
                    dcc.Graph(figure=build_suspicion_histogram(reviews),
                              config={"displayModeBar": False}),
                ], className="card"),
            ], className="charts-grid"),
            html.Div([
                html.Div([
                    dcc.Graph(figure=build_depth_chart(reviews),
                              config={"displayModeBar": False}),
                ], className="card"),
                html.Div([
                    dcc.Graph(figure=build_staff_name_chart(reviews),
                              config={"displayModeBar": False}),
                ], className="card"),
            ], className="charts-grid"),
        ])

    elif tab == "tab-timeline":
        return html.Div([
            html.Div([
                dcc.Graph(figure=build_timeline_chart(reviews),
                          config={"displayModeBar": False}),
            ], className="card chart-full"),
            html.Div([
                dcc.Graph(figure=build_name_timeline(reviews),
                          config={"displayModeBar": False}),
            ], className="card chart-full"),
        ])

    elif tab == "tab-names":
        return html.Div([
            html.Div([
                html.Div([
                    dcc.Graph(figure=build_staff_name_chart(reviews),
                              config={"displayModeBar": False}),
                ], className="card"),
                html.Div([
                    dcc.Graph(figure=build_name_timeline(reviews),
                              config={"displayModeBar": False}),
                ], className="card"),
            ], className="charts-grid"),
        ])

    elif tab == "tab-explorer":
        return build_review_table(reviews)

    return html.Div("Select a tab")


def build_review_table(reviews: list):
    """Build the review explorer DataTable."""
    df = pd.DataFrame(reviews)

    if df.empty:
        return html.Div("No reviews", className="empty-state")

    # Format columns for display
    display_cols = [
        "published_at", "rating", "author_name", "text",
        "sentiment", "staff_names", "dishes_mentioned",
        "review_depth", "suspicion_score", "in_burst",
    ]
    available = [c for c in display_cols if c in df.columns]
    display_df = df[available].copy()

    if "suspicion_score" in display_df.columns:
        display_df["suspicion_score"] = display_df["suspicion_score"].round(2)
    if "text" in display_df.columns:
        display_df["text"] = display_df["text"].str[:200]

    return html.Div([
        dash_table.DataTable(
            data=display_df.to_dict("records"),
            columns=[{"name": c.replace("_", " ").title(), "id": c}
                     for c in available],
            sort_action="native",
            filter_action="native",
            page_size=25,
            style_table={"overflowX": "auto"},
            style_cell={
                "textAlign": "left",
                "maxWidth": "300px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
                "whiteSpace": "nowrap",
            },
            style_data_conditional=[
                {
                    "if": {"filter_query": "{suspicion_score} >= 0.6"},
                    "backgroundColor": "rgba(239,68,68,0.1)",
                    "color": "#fca5a5",
                },
                {
                    "if": {"filter_query": "{in_burst} = 1"},
                    "borderLeft": "3px solid #f97316",
                },
            ],
            tooltip_data=[
                {
                    "text": {"value": str(row.get("text", "")), "type": "markdown"}
                }
                for row in display_df.to_dict("records")
            ] if "text" in available else None,
            tooltip_duration=None,
        ),
    ], className="card")


# ═══════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    init_db()
    print(f"\n🚀 Dashboard running at http://localhost:{args.port}\n")
    app.run(debug=args.debug, port=args.port)
