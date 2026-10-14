"""
Syndra Demo Dashboard
=====================
B2B sales tool for the Syndra Financial Sentiment API.

Self-hosted on the project VPS behind Caddy at demo.syndradata.com, in its own
container capped at 384MB so a runaway demo cannot disturb the API it is
demonstrating. It previously ran on Streamlit Community Cloud; that deployment
is kept as a fallback until the self-hosted one has proven itself, and the free
tier's cold start (30-60s of "your app is waking up") is the main reason for
the move.

Stack: Streamlit + Plotly + Requests
"""

import html

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit.errors import StreamlitSecretNotFoundError

# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Syndra · Financial Sentiment API",
    page_icon="assets/favicon.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ──────────────────────────────────────────────────────────────────────────────
# Dark-mode steps of frontend/tokens.css; keep in sync with that file, not by eye.
st.markdown("""
<style>
    :root {
        --bg: #1e1e1e;
        --surface: #262523;
        --border: #3a3835;
        --border-strong: #4a4844;
        --fg: #f7eddf;
        --fg-muted: #d5cabb;
        --fg-faint: #a49b8e;
        --warm-text: #deaa64;
        --warm-text-hover: #ecc188;
        --pos: #5cc98a;
        --neu: #928f87;
        --neg: #e8604a;
        --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
    }
    .block-container, [data-testid="stMainBlockContainer"] {
        padding-top: 2.5rem;
        max-width: 1280px;
    }
    /* Links take the warm text step and never an underline, as on the landing. */
    .signal-card a, .sidebar-footer a {
        color: var(--warm-text);
        text-decoration: none;
    }
    .sidebar-footer a:hover {
        color: var(--warm-text-hover);
    }

    /* Header */
    .brand-header { margin-bottom: 1rem; }
    .brand-row {
        display: flex;
        align-items: center;
        gap: 10px;
        color: var(--fg-faint);
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.14em;
        text-transform: uppercase;
    }
    .brand-mark { width: 22px; height: 22px; flex: none; }
    .brand-title {
        color: var(--fg);
        font-size: 2rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        line-height: 1.2;
        margin: 0.6rem 0 0.35rem;
    }
    .brand-lede {
        color: var(--fg-muted);
        font-size: 1rem;
        max-width: 90ch;
    }
    .brand-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 22px;
        margin-top: 0.9rem;
        color: var(--fg-faint);
        font-size: 0.8rem;
    }
    .brand-meta span b { color: var(--fg-muted); font-weight: 600; }

    /* Section headings replace the emoji h3 plus horizontal rule pairs. */
    .section-head {
        border-top: 1px solid var(--border);
        margin: 2rem 0 1rem;
        padding-top: 1.25rem;
    }
    .section-head.first { border-top: 0; margin-top: 0.75rem; padding-top: 0; }
    .section-title {
        color: var(--fg);
        font-size: 1.2rem;
        font-weight: 600;
        letter-spacing: -0.01em;
    }
    .section-caption {
        color: var(--fg-faint);
        font-size: 0.82rem;
        margin-top: 0.2rem;
    }
    .section-caption code, .brand-meta code {
        font-family: var(--mono);
        font-size: 0.78rem;
        color: var(--fg-faint);
        background: transparent;
        padding: 0;
    }

    /* Sentiment colours: data only, always next to their text label. */
    .positive { color: var(--pos); }
    .negative { color: var(--neg); }
    .neutral  { color: var(--neu); }

    /* Signal cards */
    .signal-card {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 24px;
        background: var(--surface);
        border: 1px solid var(--border);
        border-left: 3px solid var(--border-strong);
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 10px;
    }
    .signal-card.positive-border { border-left-color: var(--pos); }
    .signal-card.negative-border { border-left-color: var(--neg); }
    .signal-card.neutral-border  { border-left-color: var(--neu); }
    .signal-main { flex: 1; min-width: 0; }
    .signal-card .signal-title {
        display: block;
        color: var(--fg);
        font-weight: 600;
        font-size: 1rem;
        line-height: 1.4;
    }
    .signal-card a.signal-title:hover { color: var(--warm-text); }
    .signal-meta {
        margin-top: 6px;
        color: var(--fg-faint);
        font-size: 0.8rem;
    }
    .signal-side { text-align: right; min-width: 110px; }
    .signal-label {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.1em;
    }
    .signal-score {
        margin-top: 4px;
        color: var(--fg-muted);
        font-family: var(--mono);
        font-size: 0.85rem;
    }

    /* Metric tiles */
    [data-testid="stMetric"] { background: var(--surface); }
    [data-testid="stMetricLabel"] p { color: var(--fg-faint); font-size: 0.85rem; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 500; }
    /* Faint tint only: the label text carries the meaning, the colour just echoes it. */
    .st-key-label-tile-positive [data-testid="stMetric"] {
        background: color-mix(in srgb, var(--pos) 9%, var(--surface));
        border-color: color-mix(in srgb, var(--pos) 40%, transparent);
    }
    .st-key-label-tile-negative [data-testid="stMetric"] {
        background: color-mix(in srgb, var(--neg) 9%, var(--surface));
        border-color: color-mix(in srgb, var(--neg) 40%, transparent);
    }
    .st-key-label-tile-neutral [data-testid="stMetric"] {
        background: color-mix(in srgb, var(--neu) 9%, var(--surface));
        border-color: color-mix(in srgb, var(--neu) 40%, transparent);
    }

    /* Methodology */
    .methodology-box {
        color: var(--fg-muted);
        font-size: 0.92rem;
        line-height: 1.6;
        padding: 4px 2px;
    }
    .methodology-box .box-title {
        color: var(--fg);
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .methodology-box strong { color: var(--fg); }
    .methodology-box code {
        background: var(--bg);
        color: var(--warm-text);
        font-family: var(--mono);
        padding: 1px 6px;
        border-radius: 4px;
    }

    /* Sidebar */
    .sidebar-title {
        color: var(--fg);
        font-size: 1rem;
        font-weight: 600;
    }
    .sidebar-subtitle, .sidebar-label {
        color: var(--fg-faint);
        font-size: 0.75rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
    .sidebar-label { margin: 0.25rem 0 0.5rem; font-weight: 600; }
    .sidebar-footer {
        text-align: center;
        color: var(--fg-faint);
        font-size: 0.78rem;
        line-height: 1.6;
    }

    /* Footer */
    .app-footer {
        border-top: 1px solid var(--border);
        margin-top: 2.5rem;
        padding-top: 1.5rem;
        color: var(--fg-faint);
        font-size: 0.85rem;
    }
    .app-footer .footer-title { color: var(--fg); font-weight: 600; font-size: 1rem; }
</style>
""", unsafe_allow_html=True)


def section(title: str, caption: str = "", first: bool = False) -> None:
    """Sober section heading; callers escape anything user-supplied in the caption."""
    caption_html = f'<div class="section-caption">{caption}</div>' if caption else ""
    st.markdown(
        f'<div class="section-head{" first" if first else ""}">'
        f'<div class="section-title">{title}</div>{caption_html}</div>',
        unsafe_allow_html=True,
    )


def format_published(value) -> str:
    """Readable timestamp for the cards; falls back to the raw value if it does not parse."""
    try:
        return pd.to_datetime(value).strftime("%d %b %Y, %H:%M")
    except (ValueError, TypeError, AttributeError):
        return str(value or "N/A")


# Shared by every chart so they read as one set; sentiment colours are unchanged.
SENTIMENT_COLORS = {"positive": "#5cc98a", "negative": "#e8604a", "neutral": "#928f87"}


def style_chart(fig, height: int):
    fig.update_layout(
        height=height,
        font=dict(color="#d5cabb", size=12),
        title_font=dict(color="#f7eddf", size=14),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=48, b=10),
    )
    fig.update_xaxes(gridcolor="#3a3835", zerolinecolor="#3a3835", linecolor="#3a3835")
    fig.update_yaxes(gridcolor="#3a3835", zerolinecolor="#3a3835", linecolor="#3a3835")
    return fig

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
def secret(name: str, default: str = "") -> str:
    """
    Read a Streamlit secret, actually honouring the default.

    `st.secrets.get(name, default)` does not: with no secrets.toml on disk the
    lookup raises StreamlitSecretNotFoundError from inside __getitem__, before
    the default is ever considered, and the script dies at import time. That
    contradicts the fallback this app documents below: a fork or a local run
    is meant to degrade into asking the visitor for a key, not into a
    traceback. Worse, the container's healthcheck only probes /_stcore/health,
    which stays green while every page load is a stack trace, so a failed
    secrets mount would look healthy from the outside.
    """
    try:
        return st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default


API_BASE = secret("API_BASE", "https://api.syndradata.com/api/v1")
DEFAULT_TICKER = "NVDA"

# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div class='sidebar-subtitle'>Syndra Data Engine</div>"
        "<div class='sidebar-title'>API Demo</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # A public read-only key is preloaded from secrets so a first-time visitor
    # sees live data immediately. Asking for a credential up front lost people
    # at the exact moment they were most interested: they arrive from the
    # landing page, are asked for something they do not have, and are handed an
    # email address to write to.
    #
    # The key lives in Streamlit's server-side secrets and never reaches the
    # browser. If it is absent: a fork, a local run, the app falls back to
    # asking, exactly as before.
    DEMO_KEY = secret("DEMO_API_KEY", "")

    if DEMO_KEY:
        use_own = st.toggle(
            "Use my own API key",
            value=False,
            help="Off: browse live data with the shared public demo key. "
                 "On: use your own key, with your own rate limit.",
        )
        if use_own:
            api_key = st.text_input(
                "API Key",
                type="password",
                placeholder="syndra_xxxxxxxxxxxxxxxx",
                help="Your Syndra API key. Request one at syndradata@gmail.com",
            ) or ""
        else:
            api_key = DEMO_KEY
            st.caption(
                "Live data via the shared demo key: rate limited across all "
                "visitors, so it may pause briefly under load."
            )
    else:
        api_key = st.text_input(
            "API Key",
            type="password",
            placeholder="syndra_xxxxxxxxxxxxxxxx",
            help="Your Syndra API key. Request demo access at syndradata@gmail.com",
        )

    ticker = st.text_input(
        "Ticker Symbol",
        value=DEFAULT_TICKER,
        placeholder="e.g. NVDA, AAPL, TSLA",
    ).upper().strip()

    article_limit = st.slider(
        "Article Limit",
        min_value=10,
        max_value=100,
        value=50,
        step=10,
        help="Maximum number of recent articles to analyze",
    )

    days_window = st.selectbox(
        "Time Window",
        options=[1, 3, 7, 14, 30],
        format_func=lambda x: f"Last {x} days",
        index=1,
        help="Optional: Filter articles by strict time window",
    )

    st.markdown("---")

    if st.button("Analyze Sentiment", type="primary", use_container_width=True):
        st.session_state["fetch_triggered"] = True

    st.markdown("---")
    st.markdown("<div class='sidebar-label'>Resources</div>", unsafe_allow_html=True)
    st.link_button("API Documentation", "https://api.syndradata.com/docs", use_container_width=True)
    st.link_button("JSON Schema (Gist)", "https://gist.github.com/FranSMM/7f69e0e54352634f5b977e8c0662b23a", use_container_width=True)
    st.link_button("GitHub Repository", "https://github.com/FranSMM/syndra-docs", use_container_width=True)

    st.markdown("---")
    st.markdown(
        "<div class='sidebar-footer'>"
        "© 2026 Syndra Data Engine<br>"
        "<a href='mailto:syndradata@gmail.com'>syndradata@gmail.com</a>"
        "</div>",
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# MAIN HEADER
# ──────────────────────────────────────────────────────────────────────────────
# The landing's mark (frontend/favicon.svg), dark-mode colours, so both surfaces read as one product.
st.markdown(
    """
    <div class="brand-header">
        <div class="brand-row">
            <svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
                <path d="M25.99 15.48 A10 10 0 1 1 16.52 6.01" fill="none" stroke="#f7eddf" stroke-width="3.2" stroke-linecap="round"/>
                <circle cx="23.07" cy="8.93" r="3.5" fill="#deaa64"/>
            </svg>
            <span>Syndra Data Engine</span>
        </div>
        <div class="brand-title">Financial Sentiment API</div>
        <div class="brand-lede">
            Zero-leakage NLP sentiment analysis for financial markets.
            Self-hosted. API-first. No OpenAI dependency.
        </div>
        <div class="brand-meta">
            <span><b>Source</b> Public financial news feeds</span>
            <span><b>Sentiment</b> <code>ProsusAI/finBERT</code></span>
            <span><b>Search</b> <code>all-MiniLM-L6-v2</code> on Qdrant</span>
            <span><b>Freshness</b> Responses cached for 5 minutes</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# API KEY VALIDATION
# ──────────────────────────────────────────────────────────────────────────────
if not api_key:
    st.warning("Please enter your API Key in the sidebar to begin.")
    st.info(
        "Don't have a key? Request demo access at **syndradata@gmail.com** "
        "or connect with us on [LinkedIn](https://www.linkedin.com/in/francisco-montesinos/)."
    )
    
    section("Dashboard Preview", "A preview of the Syndra intelligence dashboard in action.")
    
    try:
        col_img1, col_img2 = st.columns(2)
        with col_img1:
            st.image("assets/syndra_demo_dashboard_1.png", use_container_width=True, caption="Aggregated Sentiment & Trends")
        with col_img2:
            st.image("assets/syndra_demo_dashboard_2.png", use_container_width=True, caption="Recent Signals & Distribution")
    except FileNotFoundError:
        st.caption("*(Preview images will appear here once added to the assets folder)*")
        
    st.stop()

# ──────────────────────────────────────────────────────────────────────────────
# FETCH FUNCTIONS WITH CACHE
# ──────────────────────────────────────────────────────────────────────────────
def api_get(path: str, api_key: str, params: dict, not_found: str):
    """GET against the Syndra API, turning HTTP failures into messages for the visitor."""
    try:
        resp = requests.get(
            f"{API_BASE}{path}",
            headers={"X-API-Key": api_key},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError:
        if resp.status_code in (401, 403):
            raise ValueError("Invalid API Key. Please check your credentials.")
        elif resp.status_code == 429:
            # On the shared demo key this is nobody's fault in particular: the
            # budget is pooled across everyone browsing at that moment. Say so,
            # or it reads as "you did something wrong" and the visitor leaves.
            raise ValueError(
                "The shared demo key has hit its limit: 100 requests a minute "
                "across all visitors. Wait about a minute and try again, or "
                "switch on 'Use my own API key' in the sidebar."
            )
        elif resp.status_code == 404:
            raise ValueError(not_found)
        else:
            raise ValueError(f"API Error {resp.status_code}: {resp.text}")
    except requests.exceptions.ConnectionError:
        raise ValueError("Unable to connect to Syndra API. Please try again later.")
    except requests.exceptions.Timeout:
        raise ValueError("Request timed out. The API may be under high load.")


# Both cached for 5 minutes to protect the VPS from traffic spikes.
@st.cache_data(ttl=300, show_spinner=False)
def fetch_sentiment_data(ticker_symbol: str, api_key: str, limit: int, d_window: int):
    return api_get(
        f"/sentiment/{ticker_symbol}", api_key,
        {"limit": limit, "days_window": d_window},
        f"No data found for ticker '{ticker_symbol}'.",
    )


@st.cache_data(ttl=300, show_spinner=False)
def fetch_semantic_search(query: str, api_key: str, limit: int, ticker_filter: str):
    params = {"query": query, "limit": limit}
    if ticker_filter:
        params["ticker"] = ticker_filter
    return api_get("/search/semantic", api_key, params, "Semantic search is not available right now.")


tab_sentiment, tab_search = st.tabs(["Sentiment Analysis", "Semantic Search"])

# ──────────────────────────────────────────────────────────────────────────────
# SEMANTIC SEARCH TAB
# ──────────────────────────────────────────────────────────────────────────────
# Rendered first: the sentiment tab stops the script on missing input or errors.
MAX_QUERY_LENGTH = 200  # same limit as the API's query parameter

with tab_search:
    section(
        "Semantic Search",
        "Search the news by meaning, not by keyword. Every article is embedded "
        "with all-MiniLM-L6-v2 and stored in Qdrant, so a query finds related "
        "news even when it shares no words with it. "
        "Endpoint: <code>GET /search/semantic</code>",
        first=True,
    )

    with st.form("semantic_search"):
        query = st.text_input(
            "Query",
            max_chars=MAX_QUERY_LENGTH,
            placeholder="e.g. chip export restrictions",
        )
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            search_ticker = st.text_input(
                "Ticker filter (optional)",
                placeholder="e.g. NVDA",
            ).upper().strip()
        with col_q2:
            search_limit = st.selectbox("Results", options=[5, 10, 20], index=0)
        submitted = st.form_submit_button("Search", type="primary")

    if submitted:
        query = query.strip()
        results = None
        if len(query) < 3:
            st.warning("Type at least 3 characters.")
        else:
            with st.spinner("Searching..."):
                try:
                    results = fetch_semantic_search(query, api_key, search_limit, search_ticker)
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

        if results == []:
            st.info("No matching articles.")
        elif results:
            for hit in results:
                label = hit.get("sentiment_label", "neutral").lower()
                # Titles come from scraped feeds: escaped before going into HTML.
                title = html.escape(hit.get("title", "Untitled"))
                tickers = html.escape(", ".join(hit.get("tickers", [])) or "No tickers")
                similarity = hit.get("similarity_score", 0.0)

                st.markdown(f"""
                <div class="signal-card {label}-border">
                    <div class="signal-main">
                        <div class="signal-title">{title}</div>
                        <div class="signal-meta">{tickers}</div>
                    </div>
                    <div class="signal-side">
                        <div class="signal-label {label}">{label.upper()}</div>
                        <div class="signal-score">similarity {similarity:.4f}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with st.expander("View JSON (for integration debugging)", expanded=False):
                st.json(results)

# ──────────────────────────────────────────────────────────────────────────────
# SENTIMENT TAB
# ──────────────────────────────────────────────────────────────────────────────
with tab_sentiment:
    if not ticker:
        st.warning("Please enter a ticker symbol in the sidebar.")
        st.stop()

    # ──────────────────────────────────────────────────────────────────────────────
    # FETCH DATA
    # ──────────────────────────────────────────────────────────────────────────────
    fetch_triggered = st.session_state.get("fetch_triggered", True)

    if fetch_triggered:
        with st.spinner(f"Analyzing sentiment for **{ticker}**..."):
            try:
                data = fetch_sentiment_data(ticker, api_key, article_limit, days_window)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            except Exception as e:
                st.error(f"Unexpected error: {e}")
                st.stop()
    else:
        st.info("Click **Analyze Sentiment** in the sidebar to fetch data.")
        st.stop()

    # ──────────────────────────────────────────────────────────────────────────────
    # RENDER RESULTS
    # ──────────────────────────────────────────────────────────────────────────────

    # ── KEY METRICS ──
    # Ticker is visitor input, so it is escaped before going into the caption HTML.
    section(
        "Aggregated Sentiment Overview",
        f"<code>GET /sentiment/{html.escape(ticker)}</code> · last {days_window} days · "
        f"up to {article_limit} articles",
        first=True,
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    sentiment = data.get("aggregated_sentiment", "neutral")
    score = data.get("average_score", 0.0)
    count = data.get("article_count", 0)
    window = data.get("time_window", "N/A")

    with col1:
        st.metric("Articles Analyzed", count, border=True)
    with col2:
        st.metric("Avg Sentiment Score", f"{score:.4f}", border=True)
    # The key becomes a CSS class, so it only takes the three known labels.
    tile_label = sentiment.lower() if sentiment.lower() in SENTIMENT_COLORS else "neutral"
    with col3, st.container(key=f"label-tile-{tile_label}"):
        st.metric("Sentiment Label", sentiment.title(), border=True)
    with col4:
        st.metric("Time Window", window, border=True)
    with col5:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            number={"font": {"size": 22, "color": "#f7eddf"}, "valueformat": ".3f"},
            gauge={
                "axis": {"range": [-1, 1], "tickwidth": 1, "tickcolor": "#4a4844",
                         "tickfont": {"color": "#a49b8e", "size": 10}},
                "bar": {"color": "#deaa64", "thickness": 0.3},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 1,
                "bordercolor": "#3a3835",
                "steps": [
                    {"range": [-1, -0.2], "color": "#3a2320"},
                    {"range": [-0.2, 0.2], "color": "#2b2a27"},
                    {"range": [0.2, 1], "color": "#223a2c"},
                ],
                "threshold": {
                    "line": {"color": "#f7eddf", "width": 3},
                    "thickness": 0.75,
                    "value": score,
                },
            },
        ))
        fig_gauge.update_layout(height=150, margin=dict(l=18, r=18, t=18, b=6), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_gauge, use_container_width=True, config={"displayModeBar": False})

    # ── SCORING METHODOLOGY (MLOps) ──
    with st.expander("Understanding the Scoring Methodology", expanded=False):
        st.markdown("""
        <div class="methodology-box">
            <div class="box-title">FinBERT Softmax Classification</div>
            <p>
            Syndra uses <strong>ProsusAI/finBERT</strong>, a domain-specific BERT model fine-tuned on financial text.
            Unlike regression models, FinBERT outputs <strong>classification probabilities via Softmax</strong>:
            </p>
            <ul>
                <li><code>sentiment_score</code> = <code>(P(positive) − P(negative)) * (1 − P(neutral))</code>, ranging from <strong>−1.0 to +1.0</strong></li>
                <li><code>sentiment_label</code> = argmax of [positive, negative, neutral] probabilities</li>
            </ul>
            <p>
            <strong>Why can average_score be low while label is "neutral"?</strong><br>
            When the model detects <em>conflicting vocabulary</em> or <em>low confidence across all classes</em>,
            the score clusters near 0.0 and the label defaults to "neutral". This is <strong>not a bug</strong>:
            it indicates market uncertainty or mixed signals in the news corpus.
            </p>
            <p>
            <strong>For Quants:</strong> Use <code>sentiment_label</code> for discrete event triggers
            and the <strong>moving average of <code>sentiment_score</code></strong> for trend divergence analysis.
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ── SENTIMENT TIMELINE ──
    section("Sentiment Timeline", "Each point is one article, scored individually by FinBERT.")

    signals = data.get("recent_signals", [])
    if signals:
        df = pd.DataFrame(signals)
        df["published_at"] = pd.to_datetime(df["published_at"])
        df = df.sort_values("published_at")

        fig_timeline = px.scatter(
            df,
            x="published_at",
            y="sentiment_score",
            color="sentiment_label",
            color_discrete_map=SENTIMENT_COLORS,
            hover_data={"title": True, "source": True, "sentiment_score": ":.4f"},
            title=f"Sentiment Score Evolution: {ticker}",
            labels={"published_at": "Published At", "sentiment_score": "Sentiment Score"},
        )
        fig_timeline.update_traces(marker=dict(size=9, opacity=0.85, line=dict(width=0)))
        style_chart(fig_timeline, 400)
        fig_timeline.update_layout(
            xaxis_title="",
            yaxis_title="Sentiment Score",
            yaxis=dict(range=[-1.1, 1.1]),
            legend_title_text="Label",
        )
        fig_timeline.add_hline(y=0, line_dash="dash", line_color="#928f87", opacity=0.5)
        st.plotly_chart(fig_timeline, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            dist = df["sentiment_label"].value_counts().to_dict()
            fig_pie = px.pie(
                names=list(dist.keys()),
                values=list(dist.values()),
                color=list(dist.keys()),
                color_discrete_map=SENTIMENT_COLORS,
                title="Signal Distribution",
                hole=0.55,
            )
            # Label next to the share: the light green is only safe for CVD with its text beside it.
            fig_pie.update_traces(textinfo="label+percent", marker=dict(line=dict(color="#1e1e1e", width=2)))
            style_chart(fig_pie, 300)
            fig_pie.update_layout(showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_b:
            # Bucketed by score rounded to one decimal, so each bar names a single value; + 0.0 turns -0.0 into 0.0.
            df_bins = (
                df.assign(score_bin=df["sentiment_score"].round(1) + 0.0)
                .groupby(["score_bin", "sentiment_label"]).size().reset_index(name="articles")
            )
            fig_hist = px.bar(
                df_bins,
                x="score_bin",
                y="articles",
                color="sentiment_label",
                color_discrete_map=SENTIMENT_COLORS,
                category_orders={"sentiment_label": ["positive", "neutral", "negative"]},
                title="Score Distribution",
                labels={"score_bin": "Score", "articles": "Articles", "sentiment_label": "Label"},
            )
            fig_hist.update_traces(
                width=0.08,
                hovertemplate="%{fullData.name}<br>Score %{x:.1f}<br>Articles %{y}<extra></extra>",
            )
            style_chart(fig_hist, 300)
            # Full score range: autorange ignores the manual bar width and clips the edge bars.
            fig_hist.update_xaxes(range=[-1.05, 1.05], dtick=0.5)
            # Whole-article ticks when counts are small, where plotly would otherwise show 0.5 steps.
            if df_bins["articles"].max() <= 8:
                fig_hist.update_yaxes(dtick=1)
            st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("No recent signals available for this ticker.")

    # ── RECENT SIGNALS ──
    section("Recent Signals", "Per-article scores behind the aggregate above.")

    if signals:
        for sig in signals[:10]:
            label = sig.get("sentiment_label", "neutral").lower()
            score_s = sig.get("sentiment_score", 0.0)
            # Scraped feed content, escaped before going into HTML; only web links are kept.
            title = html.escape(sig.get("title") or "Untitled")
            raw_url = sig.get("url") or ""
            url = html.escape(raw_url) if raw_url.startswith(("http://", "https://")) else "#"
            source = html.escape(sig.get("source") or "Unknown")
            published = html.escape(format_published(sig.get("published_at")))

            border_class = f"{label}-border"
            label_class = label

            st.markdown(f"""
            <div class="signal-card {border_class}">
                <div class="signal-main">
                    <a class="signal-title" href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>
                    <div class="signal-meta">{source} &nbsp;·&nbsp; {published}</div>
                </div>
                <div class="signal-side">
                    <div class="signal-label {label_class}">{label.upper()}</div>
                    <div class="signal-score">{score_s:+.4f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        if len(signals) > 10:
            st.caption(f"Showing top 10 of {len(signals)} signals. Full data available via API.")
    else:
        st.info("No signals to display.")

    # ── RAW JSON (for developers) ──
    section("Raw API Response", "The unmodified JSON payload and a Python quick-start.")

    with st.expander("View JSON (for integration debugging)", expanded=False):
        st.json(data)
        code_snippet = (
            f'# Python quick-start\n'
            f'data = requests.get(\n'
            f'    "{API_BASE}/sentiment/{ticker}",\n'
            f'    headers={{"X-API-Key": "{api_key[:8]}..."}},\n'
            f'    params={{"limit": {article_limit}, "days_window": {days_window}}}\n'
            f').json()'
        )
        st.code(code_snippet, language="python")

# ── FOOTER CTA ──
st.markdown("""
<div class="app-footer">
    <div class="footer-title">Integrate Syndra into your pipeline</div>
    <div>Self-hosted · Zero data leakage · FinBERT-powered · REST API</div>
</div>
""", unsafe_allow_html=True)

col_cta1, col_cta2, col_cta3 = st.columns(3)
with col_cta1:
    st.link_button("Full API Docs", "https://api.syndradata.com/docs", use_container_width=True)
with col_cta2:
    st.link_button("Contact Sales", "mailto:syndradata@gmail.com", use_container_width=True)
with col_cta3:
    st.link_button("View on GitHub", "https://github.com/FranSMM/syndra-docs", use_container_width=True)