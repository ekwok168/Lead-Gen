"""Lead Generation Tool - Main Streamlit Application."""

import streamlit as st
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from database.connection import init_db, seed_core_segments
from database.models import get_table_counts

# Page configuration
st.set_page_config(
    page_title="Lead Generation Tool",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --- Password Protection ---
def check_password():
    """Return True if the user has entered the correct password."""
    # If no password is configured in secrets, skip auth
    try:
        correct_password = st.secrets["password"]
    except (KeyError, FileNotFoundError):
        return True

    if st.session_state.get("authenticated"):
        return True

    st.markdown("### 🔒 Lead Generation Tool")
    st.markdown("Please enter the password to access this tool.")
    password = st.text_input("Password", type="password", key="password_input")

    if password:
        if password == correct_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")
    return False


if not check_password():
    st.stop()


# Custom CSS for larger fonts and buttons (non-technical user friendly)
st.markdown("""
<style>
    .main .block-container { padding-top: 1rem; }
    .stButton > button {
        font-size: 16px;
        padding: 0.5rem 1.5rem;
        border-radius: 8px;
    }
    .big-button > button {
        font-size: 20px !important;
        padding: 1rem 2rem !important;
        background-color: #2196F3 !important;
        color: white !important;
    }
    h1 { font-size: 2rem !important; }
    h2 { font-size: 1.5rem !important; }
    .metric-card {
        background: #f8f9fa;
        padding: 1.2rem;
        border-radius: 10px;
        text-align: center;
        border: 1px solid #e0e0e0;
    }
    .metric-value { font-size: 2rem; font-weight: bold; color: #1976D2; }
    .metric-label { font-size: 0.9rem; color: #666; }
</style>
""", unsafe_allow_html=True)

# Initialize database on first run
init_db()
seed_core_segments()

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/target.png", width=60)
    st.title("Lead Gen Tool")
    st.markdown("---")

    counts = get_table_counts()
    st.markdown("**Data Summary**")
    st.write(f"📍 Distribution Centers: **{counts.get('distribution_centers', 0)}**")
    st.write(f"🚛 Routes: **{counts.get('routes', 0)}**")
    st.write(f"👥 Customers: **{counts.get('customers', 0)}**")
    st.write(f"🎯 Leads: **{counts.get('leads', 0)}**")
    st.write(f"📊 Scored: **{counts.get('lead_scores', 0)}**")

    st.markdown("---")
    st.markdown("**Quick Actions**")
    if st.button("🔄 Score All Leads", use_container_width=True):
        st.session_state["trigger_scoring"] = True
        st.rerun()

# Main content - Welcome page
st.title("🎯 Lead Generation Tool")
st.markdown("**Find and prioritize new customers near your existing delivery routes**")

counts = get_table_counts()
has_data = counts.get("customers", 0) > 0

if not has_data:
    st.markdown("---")
    st.markdown("## 👋 Welcome! Let's get started")
    st.markdown("""
    This tool helps your sales team find the best new customers by analyzing
    proximity to your existing delivery routes. Here's how to get started:
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">1</div>
            <div class="metric-label">
                <b>Upload Your Data</b><br>
                Go to the <b>Upload Data</b> page to import your
                customers, routes, and prospect lists via Excel or copy-paste.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">2</div>
            <div class="metric-label">
                <b>Score Your Leads</b><br>
                Click <b>"Score All Leads"</b> to analyze every prospect
                based on proximity, segment fit, and route density.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">3</div>
            <div class="metric-label">
                <b>Review & Export</b><br>
                View results on the <b>Dashboard</b>, explore the
                <b>Map View</b>, and export reports to Excel.
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.info("💡 **Tip:** Want to try it with sample data first? Click the button below to load demo data for the Denver metro area.")

    if st.button("📦 Load Sample Data", use_container_width=True):
        with st.spinner("Generating sample data..."):
            from database.seed_data import seed_database
            seed_database()
        st.success("Sample data loaded! Navigate to the Dashboard or Upload Data page to explore.")
        st.rerun()

else:
    # Show overview metrics
    st.markdown("---")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Distribution Centers", counts.get("distribution_centers", 0))
    with col2:
        st.metric("Routes", counts.get("routes", 0))
    with col3:
        st.metric("Customers", counts.get("customers", 0))
    with col4:
        st.metric("Leads", counts.get("leads", 0))
    with col5:
        st.metric("Scored", counts.get("lead_scores", 0))

    # Handle scoring trigger
    if st.session_state.get("trigger_scoring"):
        st.session_state["trigger_scoring"] = False
        st.markdown("---")
        st.markdown("### Scoring leads...")
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(pct, msg):
            progress_bar.progress(pct / 100)
            status_text.text(msg)

        from scoring.engine import score_all_leads
        results = score_all_leads(progress_callback=update_progress)

        if not results.empty:
            st.success(f"Scored {len(results)} leads! Navigate to Dashboard or Lead Explorer to review.")
            grade_counts = results["score_grade"].value_counts().to_dict()
            cols = st.columns(5)
            for i, grade in enumerate(["A", "B", "C", "D", "F"]):
                with cols[i]:
                    st.metric(f"Grade {grade}", grade_counts.get(grade, 0))
        else:
            st.warning("No leads to score. Upload some leads first!")

    st.markdown("---")
    st.markdown("### Navigate to a page using the sidebar to explore your data")
    st.markdown("""
    - **📊 Dashboard** - Overview of all leads, scores, and KPIs
    - **📥 Upload Data** - Import customers, routes, and prospects
    - **🏢 DC View** - Distribution center level analysis
    - **🚛 Route View** - Route level analysis with maps
    - **🔍 Lead Explorer** - Search and filter individual leads
    - **🗺️ Map View** - Interactive map of all routes and leads
    - **📋 Reports** - Generate and export reports
    - **⚙️ Settings** - Configure scoring weights and segments
    """)
