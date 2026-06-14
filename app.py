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
    build_topic_sentiments_chart,
    build_dishes_chart,
    build_trust_scatter_chart,
    build_customer_reviews_histogram,
    build_customer_scatter_chart,
)
from db import (
    get_db, init_db, get_dashboard_summary, get_analysis_for_restaurant,
    get_all_reviews_with_analysis
)
import dash_leaflet as dl
from dash import ALL

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
        {"label": f"{r['name']} ({r['type']}) ⭐{r['rating'] or '?'}  "
                  f"({r['total_reviews'] or 0} reviews)",
         "value": r["place_id"]}
        for r in data
    ]


def make_stat_card(value, label, color="#2563eb", icon=""):
    """Create a stat card HTML element."""
    return html.Div([
        html.Div([
            html.Div(str(value), className="stat-value", style={"color": color}),
            html.Div(icon, style={"fontSize": "1.75rem", "opacity": "0.3"}),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "8px"}),
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

def serve_layout():
    return html.Div([
        # SIDEBAR
        html.Div([
            html.Div([
                html.Div([
                    html.Div("🍔", style={"fontSize": "2rem", "marginRight": "12px", "display": "inline-block", "verticalAlign": "middle"}),
                    html.H2("PRR", style={"fontSize": "1.5rem", "fontWeight": "800", "display": "inline-block", "verticalAlign": "middle", "margin": "0", "color": "var(--text-primary)", "letterSpacing": "1px"}),
                ], style={"marginBottom": "32px"}),
            ]),
            
            html.Div([
                html.Div("📢 Campaign", id="nav-campaign", className="nav-item active", n_clicks=0),
                html.Div("👥 All Customers", id="nav-customers", className="nav-item", n_clicks=0),
            ], className="nav-menu"),
        ], className="sidebar"),

        # MAIN CONTENT
        html.Div([
            html.Div(id="page-content"),
            
            # Store for map selection
            dcc.Store(id="selected-place-id"),
            
        ], className="main-content")
    ], className="app-wrapper")

def serve_campaign_view():
    return html.Div([
        # HEADER
        html.Div([
            html.Div([
                html.Div("Click a restaurant on the map to view detailed analytics",
                         className="subtitle", style={"fontSize": "1.05rem"}),
            ]),
            html.Div([
                html.Div("Status: Active", className="badge badge-clean"),
            ]),
        ], className="app-header"),

        # SEARCH BAR
        html.Div([
            html.Span("🔍", style={"position": "absolute", "left": "16px", "top": "12px", "color": "var(--text-secondary)", "fontSize": "1.2rem", "zIndex": "1"}),
            dcc.Input(id="search-input", type="text", placeholder="Search restaurants...", className="search-bar")
        ], style={"position": "relative", "marginBottom": "24px", "maxWidth": "500px"}),

        # TOP LAYOUT: KPIs + MAP
        html.Div([
            html.Div(id="kpi-cards", className="kpi-grid"),
            html.Div([
                dl.Map(
                    [
                        dl.TileLayer(
                            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
                        ),
                        dl.LayerGroup(id="map-markers")
                    ],
                    id="restaurant-map",
                    center=[52.4064, 16.9252],
                    zoom=12,
                    style={'width': '100%', 'height': '100%', 'flex': '1', 'borderRadius': '8px', 'zIndex': '0'}
                )
            ], className="map-card")
        ], className="top-layout"),

        # Tabs
        dcc.Tabs(id="main-tabs", value="tab-overview", children=[
            dcc.Tab(label="📊 Overview", value="tab-overview",
                    className="custom-tab", selected_className="custom-tab--selected"),
            dcc.Tab(label="🍔 Insights", value="tab-insights",
                    className="custom-tab", selected_className="custom-tab--selected"),
            dcc.Tab(label="📅 Timeline", value="tab-timeline",
                    className="custom-tab", selected_className="custom-tab--selected"),
            dcc.Tab(label="👤 Staff Names", value="tab-names",
                    className="custom-tab", selected_className="custom-tab--selected"),
            dcc.Tab(label="🔍 Review Explorer", value="tab-explorer",
                    className="custom-tab", selected_className="custom-tab--selected"),
            dcc.Tab(label="About / Help", value="tab-help",
                    className="custom-tab", selected_className="custom-tab--selected"),
        ], className="custom-tabs"),

        # Tab Content
        html.Div(id="tab-content"),
    ])

def serve_customers_view():
    with get_db() as conn:
        all_reviews = get_all_reviews_with_analysis(conn)
        
    unique_authors = len(set(r.get("author_name") for r in all_reviews if r.get("author_name")))
    avg_reviews = round(sum(max(int(r.get("author_reviews_count") or 0), 1) for r in all_reviews) / max(len(all_reviews), 1), 1)
    
    return html.Div([
        # HEADER
        html.Div([
            html.Div([
                html.H2("Global Customer Analytics", style={"margin": "0", "fontSize": "1.5rem"}),
                html.Div("Aggregated data across all users in the database",
                         className="subtitle", style={"fontSize": "1.05rem", "marginTop": "4px"}),
            ]),
        ], className="app-header"),
        
        # CONTROL WIDGETS
        html.Div([
            html.Div([
                html.Label("Minimum Suspicion Score", className="stat-label", style={"marginBottom": "8px", "display": "block"}),
                dcc.Slider(
                    id="global-suspicion-slider", min=0, max=1, step=0.1, value=0,
                    marks={0: '0', 0.5: '0.5', 1: '1'}, tooltip={"placement": "bottom", "always_visible": False}
                )
            ], style={"flex": "1", "marginRight": "32px"}),
            html.Div([
                html.Label("Review Depth", className="stat-label", style={"marginBottom": "8px", "display": "block"}),
                dcc.Dropdown(
                    id="global-depth-dropdown",
                    options=[
                        {"label": "All", "value": "all"},
                        {"label": "Detailed", "value": "detailed"},
                        {"label": "Moderate", "value": "moderate"},
                        {"label": "Shallow", "value": "shallow"}
                    ],
                    value="all", clearable=False
                )
            ], style={"flex": "1"})
        ], style={"display": "flex", "marginBottom": "24px", "background": "var(--surface)", "padding": "16px", "borderRadius": "8px", "boxShadow": "var(--shadow-sm)"}),
        
        # STATS
        html.Div(id="global-stats-container"),

        # CHARTS GRID
        html.Div([
            html.Div(dcc.Graph(id="global-histogram", config={"displayModeBar": False}), className="card"),
            html.Div(dcc.Graph(id="global-scatter", config={"displayModeBar": False}), className="card"),
        ], className="charts-grid"),
        
        html.Div([
            html.Div(dcc.Graph(id="global-topics-chart", config={"displayModeBar": False}), className="card"),
        ], className="charts-grid", style={"marginTop": "24px"}),

    ])

app.layout = serve_layout

# ═══════════════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════════════

@app.callback(
    Output("map-markers", "children"),
    Input("search-input", "value"),
    Input("selected-place-id", "data")
)
def update_map(search_query, selected_place_id):
    """Filter map based on search query and return markers."""
    summary = get_summary_data()
    if search_query:
        query = search_query.lower()
        summary = [r for r in summary if query in r["name"].lower() or (r["type"] and query in r["type"].lower())]
    
    markers = []
    for r in summary:
        if not r.get("lat") or not r.get("lng"):
            continue
        is_selected = r["place_id"] == selected_place_id
        icon_size = [48, 56] if is_selected else [24, 28]
        icon_anchor = [24, 56] if is_selected else [12, 28]
        
        icon_url = "/assets/location-pin.png"
        markers.append(
            dl.Marker(
                position=[r["lat"], r["lng"]],
                icon=dict(
                    iconUrl=icon_url,
                    iconSize=icon_size,
                    iconAnchor=icon_anchor,
                    className="active-pin" if is_selected else ""
                ),
                id={"type": "map-marker", "place_id": r["place_id"]},
                children=[
                    dl.Tooltip(r["name"])
                ]
            )
        )
    return markers


@app.callback(
    Output("selected-place-id", "data"),
    Input({"type": "map-marker", "place_id": ALL}, "n_clicks"),
    State({"type": "map-marker", "place_id": ALL}, "id"),
    prevent_initial_call=True
)
def update_selected_place(n_clicks, marker_ids):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
        
    prop_id = ctx.triggered[0]["prop_id"]
    if not prop_id or prop_id == ".":
        return dash.no_update
        
    try:
        id_str = prop_id.split(".")[0]
        id_dict = json.loads(id_str)
        return id_dict.get("place_id")
    except Exception:
        return dash.no_update


@app.callback(
    Output("kpi-cards", "children"),
    Input("selected-place-id", "data"),
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
                make_stat_card(rest["name"], "Selected Restaurant", "#2563eb", "📍"),
                make_stat_card(rest["analyzed_count"] or 0, "Reviews Analyzed", "#10b981", "📊"),
                make_stat_card(f"{pct}%", "Flagged Rate", "#ef4444" if pct > 10 else "#f59e0b" if pct > 5 else "#10b981", "🚩"),
                make_stat_card(f"⭐ {rest['rating'] or '?'}", "Google Rating", "#f59e0b", "⭐"),
            ]

    # Global stats
    total_analyzed = sum(r["analyzed_count"] or 0 for r in summary)
    total_flagged = sum(r["flagged_count"] or 0 for r in summary)
    pct = round(100 * total_flagged / max(total_analyzed, 1), 1)

    return [
        make_stat_card(len(summary), "Total Restaurants", "#2563eb", "📍"),
        make_stat_card(total_analyzed, "Total Reviews Analyzed", "#8b5cf6", "📊"),
        make_stat_card(total_flagged, "Flagged Reviews", "#ef4444" if total_flagged else "#10b981", "🚩"),
        make_stat_card(f"{pct}%", "Overall Flag Rate", "#ef4444" if pct > 10 else "#10b981", "📈"),
    ]


@app.callback(
    Output("tab-content", "children"),
    Input("main-tabs", "value"),
    Input("selected-place-id", "data"),
)
def render_tab(tab, place_id):
    """Render the selected tab content."""

    if tab == "tab-help":
        return html.Div([
            html.H3("About this dashboard"),
            html.P("This tool analyzes restaurant reviews to detect potentially fake or suspicious activity.", style={"marginBottom": "16px"}),
            html.H4("Main features:"),
            html.Ul([
                html.Li([html.B("Overview: "), "Shows general sentiment, suspicion scores, and author trust."]),
                html.Li([html.B("Timeline: "), "Displays review trends over time to identify sudden bursts."]),
                html.Li([html.B("Staff Names: "), "Highlights specific names frequently mentioned in reviews."]),
                html.Li([html.B("Review Explorer: "), "A searchable table to read and filter individual reviews."])
            ], style={"marginBottom": "24px"}),
            html.H4("How to use:"),
            html.P("Select a restaurant from the dropdown at the top to begin exploring its data.")
        ], className="card", style={"padding": "32px", "maxWidth": "800px", "margin": "0 auto"})

    if not place_id:
        return html.Div([
            html.Div("📍", className="icon"),
            html.H3("Select a Restaurant"),
            html.P("Click a marker on the map to view detailed analytics for a specific restaurant.", style={"marginTop": "8px"}),
        ], className="empty-state")

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
            html.Div([
                dcc.Graph(figure=build_trust_scatter_chart(reviews),
                          config={"displayModeBar": False}),
            ], className="card chart-full", style={"marginTop": "24px"}),
        ])

    elif tab == "tab-timeline":
        return html.Div([
            html.Div(dcc.Graph(figure=build_timeline_chart(reviews), config={"displayModeBar": False}), className="card", style={"marginBottom": "24px"}),
            html.Div(dcc.Graph(figure=build_name_timeline(reviews), config={"displayModeBar": False}), className="card")
        ], className="tab-pane")

    elif tab == "tab-insights":
        return html.Div([
            html.Div([
                html.Div(dcc.Graph(figure=build_topic_sentiments_chart(reviews), config={"displayModeBar": False}), className="card"),
                html.Div(dcc.Graph(figure=build_dishes_chart(reviews), config={"displayModeBar": False}), className="card"),
            ], className="charts-grid")
        ], className="tab-pane")

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
        "published_at", "rating", "author_name", "author_reviews_count", "author_photos_count", "text",
        "overall_sentiment", "staff_names", "dishes_mentioned",
        "review_depth", "suspicion_score", "in_burst",
    ]
    available = [c for c in display_cols if c in df.columns]
    display_df = df[available].copy()

    if "suspicion_score" in display_df.columns:
        display_df["suspicion_score"] = pd.to_numeric(display_df["suspicion_score"], errors="coerce").round(2)
    if "text" in display_df.columns:
        display_df["text"] = display_df["text"].str[:200]

    return html.Div([
        html.Div("Select a row in the table below to read the full review.", className="subtitle", style={"marginBottom": "16px"}),
        dash_table.DataTable(
            id="explorer-table",
            data=display_df.to_dict("records"),
            columns=[{"name": c.replace("_", " ").title(), "id": c}
                     for c in available],
            sort_action="native",
            filter_action="native",
            page_size=15,
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
            tooltip_duration=None,
        ),
        html.Div(id="review-details-card", style={"marginTop": "24px"})
    ], className="card")

# ═══════════════════════════════════════════════════════════════
# Cross-Filtering Callback
# ═══════════════════════════════════════════════════════════════
@app.callback(
    Output("review-details-card", "children"),
    Input("explorer-table", "active_cell"),
    State("explorer-table", "data"),
    prevent_initial_call=True
)
def display_review_details(active_cell, table_data):
    if not active_cell or not table_data:
        return dash.no_update
    
    row = table_data[active_cell["row"]]
    
    # We query the DB for the full text since the table might truncate it
    with get_db() as conn:
        all_revs = get_all_reviews_with_analysis(conn)
    
    # Find the matching review by author and date
    author = row.get("author_name")
    date = row.get("published_at")
    
    full_text = row.get("text", "")
    for r in all_revs:
        if r.get("author_name") == author and r.get("published_at") == date:
            full_text = r.get("text", full_text)
            break
            
    return html.Div([
        html.H4(f"Review by {author}", style={"marginTop": "0", "color": "var(--text-primary)"}),
        html.Div(f"Published: {date} | Rating: {row.get('rating', '?')} ⭐", style={"color": "var(--text-secondary)", "marginBottom": "12px", "fontSize": "0.9rem"}),
        html.Div(full_text, style={"padding": "16px", "background": "var(--bg)", "borderRadius": "8px", "borderLeft": "4px solid var(--accent)", "lineHeight": "1.6"}),
        html.Div(f"Topics: {row.get('overall_sentiment', 'None')}", style={"marginTop": "12px", "fontSize": "0.9rem", "color": "var(--text-secondary)"}),
    ], style={"padding": "24px", "background": "var(--surface)", "borderRadius": "8px", "boxShadow": "var(--shadow-sm)", "border": "1px solid rgba(255,255,255,0.05)"})


# ═══════════════════════════════════════════════════════════════
# Page Navigation
# ═══════════════════════════════════════════════════════════════

@app.callback(
    Output("page-content", "children"),
    Output("nav-campaign", "className"),
    Output("nav-customers", "className"),
    Input("nav-campaign", "n_clicks"),
    Input("nav-customers", "n_clicks")
)
def update_page_view(n_campaign, n_customers):
    ctx = dash.callback_context
    if not ctx.triggered:
        return serve_campaign_view(), "nav-item active", "nav-item"

    prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if prop_id == "nav-customers":
        return serve_customers_view(), "nav-item", "nav-item active"
    else:
        return serve_campaign_view(), "nav-item active", "nav-item"

# ═══════════════════════════════════════════════════════════════
# Global Analytics Callbacks
# ═══════════════════════════════════════════════════════════════

@app.callback(
    Output("global-stats-container", "children"),
    Output("global-histogram", "figure"),
    Output("global-scatter", "figure"),
    Output("global-topics-chart", "figure"),
    Input("global-suspicion-slider", "value"),
    Input("global-depth-dropdown", "value")
)
def update_global_charts(min_suspicion, depth):
    with get_db() as conn:
        all_reviews = get_all_reviews_with_analysis(conn)
        
    filtered = []
    for r in all_reviews:
        suspicion = r.get("suspicion_score")
        if suspicion is None: suspicion = 0
        if suspicion < min_suspicion:
            continue
            
        txt_len = len(r.get("text") or "")
        if depth == "detailed" and txt_len < 200: continue
        if depth == "moderate" and (txt_len < 50 or txt_len >= 200): continue
        if depth == "shallow" and txt_len >= 50: continue
            
        filtered.append(r)
        
    unique_authors = len(set(r.get("author_name") for r in filtered if r.get("author_name")))
    avg_reviews = round(sum(max(int(r.get("author_reviews_count") or 0), 1) for r in filtered) / max(len(filtered), 1), 1)
    
    stats = html.Div([
        html.Div([
            html.Div([
                html.Div(f"{unique_authors:,}", className="stat-value", style={"color": "#8b5cf6"}),
                html.Div("👥", style={"fontSize": "1.75rem", "opacity": "0.3"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "8px"}),
            html.Div("Unique Customers", className="stat-label"),
        ], className="stat-card", style={"width": "30%", "display": "inline-block", "marginRight": "16px", "marginBottom": "24px"}),
        
        html.Div([
            html.Div([
                html.Div(f"{avg_reviews}", className="stat-value", style={"color": "#10b981"}),
                html.Div("📊", style={"fontSize": "1.75rem", "opacity": "0.3"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "8px"}),
            html.Div("Avg Total Reviews / User", className="stat-label"),
        ], className="stat-card", style={"width": "30%", "display": "inline-block", "marginBottom": "24px"})
    ])
    
    return (
        stats,
        build_customer_reviews_histogram(filtered),
        build_customer_scatter_chart(filtered),
        build_topic_sentiments_chart(filtered)
    )

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
