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
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #f7eddf;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #a49b8e;
        margin-bottom: 2rem;
    }
    .positive { color: #5cc98a; font-weight: 600; }
    .negative { color: #e8604a; font-weight: 600; }
    .neutral  { color: #928f87; font-weight: 600; }
    .signal-card {
        background: #1e1e1e;
        border-left: 4px solid #3a3835;
        border-top: 1px solid #262523;
        border-right: 1px solid #262523;
        border-bottom: 1px solid #262523;
        border-radius: 8px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .signal-card.positive-border { border-left-color: #5cc98a; }
    .signal-card.negative-border { border-left-color: #e8604a; }
    .signal-card.neutral-border  { border-left-color: #928f87; }
    .methodology-box {
        background: #262523;
        border: 1px solid #3a3835;
        border-radius: 8px;
        padding: 20px;
        margin: 1.5rem 0;
        color: #d5cabb;
        font-size: 0.95rem;
        line-height: 1.6;
    }
    .methodology-box h4 {
        margin-top: 0;
        color: #deaa64;
        font-size: 1.2rem;
        margin-bottom: 12px;
    }
    .methodology-box strong { color: #f7eddf; }
    .methodology-box code {
        background: #1e1e1e;
        color: #deaa64;
        padding: 2px 6px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

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
    st.markdown("### Syndra API Demo")
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
                "🔑 API Key",
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
            "🔑 API Key",
            type="password",
            placeholder="syndra_xxxxxxxxxxxxxxxx",
            help="Your Syndra API key. Request demo access at syndradata@gmail.com",
        )

    ticker = st.text_input(
        "📈 Ticker Symbol",
        value=DEFAULT_TICKER,
        placeholder="e.g. NVDA, AAPL, TSLA",
    ).upper().strip()

    article_limit = st.slider(
        "📰 Article Limit",
        min_value=10,
        max_value=100,
        value=50,
        step=10,
        help="Maximum number of recent articles to analyze",
    )

    days_window = st.selectbox(
        "⏱️ Time Window",
        options=[1, 3, 7, 14, 30],
        format_func=lambda x: f"Last {x} days",
        index=1,
        help="Optional: Filter articles by strict time window",
    )

    st.markdown("---")

    if st.button("🚀 Analyze Sentiment", type="primary", use_container_width=True):
        st.session_state["fetch_triggered"] = True

    st.markdown("---")
    st.markdown("#### 📚 Resources")
    st.link_button("API Documentation", "https://api.syndradata.com/docs", use_container_width=True)
    st.link_button("JSON Schema (Gist)", "https://gist.github.com/FranSMM/7f69e0e54352634f5b977e8c0662b23a", use_container_width=True)
    st.link_button("GitHub Repository", "https://github.com/FranSMM/syndra-docs", use_container_width=True)

    st.markdown("---")
    st.markdown(
        "<div style='text-align:center; font-size:0.8rem; color:#928f87;'>"
        "© 2026 Syndra Data Engine<br>"
        "<a href='mailto:syndradata@gmail.com'>syndradata@gmail.com</a>"
        "</div>",
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# MAIN HEADER
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("<div class='main-header'>Syndra · Financial Sentiment API</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-header'>"
    "Zero-leakage NLP sentiment analysis for financial markets. "
    "Self-hosted. API-first. No OpenAI dependency."
    "</div>",
    unsafe_allow_html=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# API KEY VALIDATION
# ──────────────────────────────────────────────────────────────────────────────
if not api_key:
    st.warning("👈 Please enter your API Key in the sidebar to begin.")
    st.info(
        "Don't have a key? Request demo access at **syndradata@gmail.com** "
        "or connect with us on [LinkedIn](https://www.linkedin.com/in/francisco-montesinos/)."
    )
    
    st.markdown("---")
    st.markdown("### 📊 Dashboard Preview")
    st.markdown("Here is a preview of the Syndra intelligence dashboard in action:")
    
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


tab_sentiment, tab_search = st.tabs(["📊 Sentiment Analysis", "🔎 Semantic Search"])

# ──────────────────────────────────────────────────────────────────────────────
# SEMANTIC SEARCH TAB
# ──────────────────────────────────────────────────────────────────────────────
# Rendered first: the sentiment tab stops the script on missing input or errors.
MAX_QUERY_LENGTH = 200  # same limit as the API's query parameter

with tab_search:
    st.markdown("### 🔎 Semantic Search")
    st.markdown(
        "Search the news by meaning, not by keyword. Every article is embedded "
        "with all-MiniLM-L6-v2 and stored in Qdrant, so a query finds related "
        "news even when it shares no words with it."
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
        submitted = st.form_submit_button("🔎 Search", type="primary")

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
                    st.error(f"❌ {e}")
                except Exception as e:
                    st.error(f"❌ Unexpected error: {e}")

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
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div style="flex:1;">
                            <div style="color:#f7eddf; font-weight:600; font-size:1.1rem; line-height:1.4;">{title}</div>
                            <div style="margin-top:8px; font-size:0.85rem; color:#a49b8e; font-weight:500;">{tickers}</div>
                        </div>
                        <div style="text-align:right; margin-left:16px; min-width:100px;">
                            <div class="{label}" style="font-size:1.15rem; letter-spacing:0.05em;">{label.upper()}</div>
                            <div style="font-size:0.95rem; color:#d5cabb; font-weight:500; margin-top:4px;">similarity {similarity:.4f}</div>
                        </div>
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
        st.warning("👈 Please enter a ticker symbol in the sidebar.")
        st.stop()

    # ──────────────────────────────────────────────────────────────────────────────
    # FETCH DATA
    # ──────────────────────────────────────────────────────────────────────────────
    fetch_triggered = st.session_state.get("fetch_triggered", True)

    if fetch_triggered:
        with st.spinner(f"🔍 Analyzing sentiment for **{ticker}**..."):
            try:
                data = fetch_sentiment_data(ticker, api_key, article_limit, days_window)
            except ValueError as e:
                st.error(f"❌ {e}")
                st.stop()
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
                st.stop()
    else:
        st.info("👈 Click **Analyze Sentiment** in the sidebar to fetch data.")
        st.stop()

    # ──────────────────────────────────────────────────────────────────────────────
    # RENDER RESULTS
    # ──────────────────────────────────────────────────────────────────────────────

    # ── KEY METRICS ──
    st.markdown("---")
    st.markdown("### 📊 Aggregated Sentiment Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    sentiment = data.get("aggregated_sentiment", "neutral")
    score = data.get("average_score", 0.0)
    count = data.get("article_count", 0)
    window = data.get("time_window", "N/A")

    sentiment_class = sentiment.lower()
    sentiment_emoji = {"positive": "🟢", "negative": "🔴", "neutral": "⚪"}.get(sentiment_class, "⚪")

    with col1:
        st.metric("Articles Analyzed", count)
    with col2:
        st.metric("Avg Sentiment Score", f"{score:.4f}")
    with col3:
        st.metric("Sentiment Label", f"{sentiment_emoji} {sentiment.title()}")
    with col4:
        st.metric("Time Window", window)
    with col5:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            number={"font": {"size": 24}},
            gauge={
                "axis": {"range": [-1, 1], "tickwidth": 1},
                "bar": {"color": "#deaa64"},
                "bgcolor": "white",
                "borderwidth": 2,
                "bordercolor": "#3a3835",
                "steps": [
                    {"range": [-1, -0.2], "color": "#3a2320"},
                    {"range": [-0.2, 0.2], "color": "#2b2a27"},
                    {"range": [0.2, 1], "color": "#223a2c"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 4},
                    "thickness": 0.75,
                    "value": score,
                },
            },
        ))
        fig_gauge.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True, config={"displayModeBar": False})

    # ── SCORING METHODOLOGY (MLOps) ──
    with st.expander("📖 Understanding the Scoring Methodology", expanded=False):
        st.markdown("""
        <div class="methodology-box">
            <h4>🔬 FinBERT Softmax Classification</h4>
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
            <strong>💡 For Quants:</strong> Use <code>sentiment_label</code> for discrete event triggers
            and the <strong>moving average of <code>sentiment_score</code></strong> for trend divergence analysis.
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ── SENTIMENT TIMELINE ──
    st.markdown("---")
    st.markdown("### 📈 Sentiment Timeline")

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
            color_discrete_map={"positive": "#5cc98a", "negative": "#e8604a", "neutral": "#928f87"},
            hover_data={"title": True, "source": True, "sentiment_score": ":.4f"},
            title=f"Sentiment Score Evolution: {ticker}",
            labels={"published_at": "Published At", "sentiment_score": "Sentiment Score"},
        )
        fig_timeline.update_traces(marker=dict(size=10, opacity=0.8))
        fig_timeline.update_layout(
            height=400,
            xaxis_title="",
            yaxis_title="Sentiment Score",
            yaxis=dict(range=[-1.1, 1.1]),
            legend_title_text="Label",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
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
                color_discrete_map={"positive": "#5cc98a", "negative": "#e8604a", "neutral": "#928f87"},
                title="Signal Distribution",
            )
            fig_pie.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_b:
            fig_hist = px.histogram(
                df,
                x="sentiment_score",
                nbins=20,
                color="sentiment_label",
                color_discrete_map={"positive": "#5cc98a", "negative": "#e8604a", "neutral": "#928f87"},
                title="Score Distribution",
                labels={"sentiment_score": "Score", "count": "Articles"},
            )
            fig_hist.update_layout(height=300, bargap=0.1)
            st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("No recent signals available for this ticker.")

    # ── RECENT SIGNALS ──
    st.markdown("---")
    st.markdown("### 📰 Recent Signals")

    if signals:
        for sig in signals[:10]:
            label = sig.get("sentiment_label", "neutral").lower()
            score_s = sig.get("sentiment_score", 0.0)
            # Scraped feed content, escaped before going into HTML; only web links are kept.
            title = html.escape(sig.get("title") or "Untitled")
            raw_url = sig.get("url") or ""
            url = html.escape(raw_url) if raw_url.startswith(("http://", "https://")) else "#"
            source = html.escape(sig.get("source") or "Unknown")
            published = html.escape(str(sig.get("published_at") or "N/A"))

            border_class = f"{label}-border"
            label_class = label

            st.markdown(f"""
            <div class="signal-card {border_class}">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div style="flex:1;">
                        <a href="{url}" target="_blank" style="text-decoration:none; color:#f7eddf; font-weight:600; font-size:1.1rem; line-height:1.4;">
                            {title}
                        </a>
                        <div style="margin-top:8px; font-size:0.85rem; color:#a49b8e; font-weight:500;">
                            {source} &nbsp;·&nbsp; {published}
                        </div>
                    </div>
                    <div style="text-align:right; margin-left:16px; min-width:100px;">
                        <div class="{label_class}" style="font-size:1.15rem; letter-spacing:0.05em;">{label.upper()}</div>
                        <div style="font-size:0.95rem; color:#d5cabb; font-weight:500; margin-top:4px;">{score_s:.4f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        if len(signals) > 10:
            st.caption(f"Showing top 10 of {len(signals)} signals. Full data available via API.")
    else:
        st.info("No signals to display.")

    # ── RAW JSON (for developers) ──
    st.markdown("---")
    st.markdown("### 🔧 Raw API Response")

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
st.markdown("---")
st.markdown("""
<div style="text-align:center; padding:2rem 0;">
    <h3>Ready to integrate Syndra into your pipeline?</h3>
    <p style="color:#928f87;">
        Self-hosted · Zero data leakage · FinBERT-powered · REST API
    </p>
</div>
""", unsafe_allow_html=True)

col_cta1, col_cta2, col_cta3 = st.columns(3)
with col_cta1:
    st.link_button("📖 Full API Docs", "https://api.syndradata.com/docs", use_container_width=True)
with col_cta2:
    st.link_button("💬 Contact Sales", "mailto:syndradata@gmail.com", use_container_width=True)
with col_cta3:
    st.link_button("⭐ Star on GitHub", "https://github.com/FranSMM/syndra-docs", use_container_width=True)