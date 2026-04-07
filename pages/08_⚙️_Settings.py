"""Settings page - Configure scoring weights and core segments."""

import streamlit as st
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db, seed_core_segments
from database.models import get_core_segments, update_core_segments
import config

init_db()
seed_core_segments()

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
st.title("⚙️ Settings")

# Scoring weights
st.markdown("### Scoring Weights")
st.markdown("""
Adjust how much each factor contributes to the overall lead score.
Higher weight = more influence on the final score. Weights must add up to 100%.
""")

col1, col2, col3, col4 = st.columns(4)

# Load current weights from session state or defaults
if "weights" not in st.session_state:
    st.session_state["weights"] = config.DEFAULT_WEIGHTS.copy()

with col1:
    st.markdown("**📍 Proximity**")
    st.markdown("How close is the lead to an existing delivery stop?")
    prox_w = st.slider("Proximity Weight (%)", 0, 100,
                        int(st.session_state["weights"]["proximity"] * 100),
                        key="prox_slider")

with col2:
    st.markdown("**🏷️ Segment Match**")
    st.markdown("Does the lead match your core customer segments?")
    seg_w = st.slider("Segment Weight (%)", 0, 100,
                       int(st.session_state["weights"]["segment"] * 100),
                       key="seg_slider")

with col3:
    st.markdown("**📊 Route Density**")
    st.markdown("How many existing customers are nearby?")
    dens_w = st.slider("Density Weight (%)", 0, 100,
                        int(st.session_state["weights"]["density"] * 100),
                        key="dens_slider")

with col4:
    st.markdown("**💰 Revenue Potential**")
    st.markdown("How much revenue could this lead generate?")
    rev_w = st.slider("Revenue Weight (%)", 0, 100,
                       int(st.session_state["weights"]["revenue"] * 100),
                       key="rev_slider")

total_weight = prox_w + seg_w + dens_w + rev_w

if total_weight != 100:
    st.warning(f"Weights add up to **{total_weight}%** - they should equal 100%")
else:
    st.success("Weights total 100% ✓")

if st.button("Save Weights", use_container_width=True):
    if total_weight != 100:
        st.error("Weights must add up to 100% before saving.")
    else:
        st.session_state["weights"] = {
            "proximity": prox_w / 100,
            "segment": seg_w / 100,
            "density": dens_w / 100,
            "revenue": rev_w / 100,
        }
        st.success("Weights saved! Click **Score All Leads** in the sidebar to re-score with new weights.")

st.markdown("---")

# Core Segments
st.markdown("### Core Customer Segments")
st.markdown("""
Define which business segments are your **core** customers.
Leads matching these segments will be flagged as core segment opportunities.
The minimum revenue threshold determines the minimum estimated weekly revenue
a lead needs to qualify as a true core segment match.
""")

core_segments = get_core_segments()

if not core_segments.empty:
    edited_df = st.data_editor(
        core_segments[["segment_name", "business_type", "min_estimated_revenue", "priority"]],
        column_config={
            "segment_name": st.column_config.TextColumn("Segment Name", width="medium"),
            "business_type": st.column_config.SelectboxColumn(
                "Business Type", options=config.BUSINESS_TYPES, width="medium"
            ),
            "min_estimated_revenue": st.column_config.NumberColumn(
                "Min Revenue ($/wk)", min_value=0, max_value=10000, step=50
            ),
            "priority": st.column_config.NumberColumn(
                "Priority (1=highest)", min_value=1, max_value=10
            ),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="core_segments_editor",
    )

    if st.button("Save Core Segments", use_container_width=True):
        update_core_segments(edited_df)
        st.success("Core segments updated! Re-score leads to apply changes.")
        st.rerun()

else:
    st.info("No core segments defined. Add some below:")
    new_segments = st.data_editor(
        pd.DataFrame(columns=["segment_name", "business_type", "min_estimated_revenue", "priority"]),
        num_rows="dynamic",
        use_container_width=True,
        key="new_core_segments",
    )
    if not new_segments.empty and st.button("Save New Segments"):
        update_core_segments(new_segments)
        st.success("Core segments saved!")
        st.rerun()

st.markdown("---")

# Scoring explanation
st.markdown("### How Scoring Works")
st.markdown("""
Each lead is scored on four dimensions (0-100 each), then combined using the weights above:

**📍 Proximity Score** - Distance to the nearest delivery stop on any route:
| Distance | Score |
|----------|-------|
| Less than 0.5 miles | 100 |
| 0.5 - 1.0 miles | 85 |
| 1.0 - 2.0 miles | 70 |
| 2.0 - 5.0 miles | 50 |
| 5.0 - 10.0 miles | 30 |
| 10.0 - 20.0 miles | 15 |
| Over 20 miles | 5 |

**🏷️ Segment Score** - How well the lead matches your core customer types:
| Match Type | Score |
|-----------|-------|
| Exact segment match | 100 |
| Same business type | 60 |
| Related business type | 40 |
| No match | 10 |

**📊 Density Score** - Number of existing customers within 1 mile:
| Nearby Customers | Score |
|-----------------|-------|
| 10 or more | 100 |
| 7-9 | 85 |
| 4-6 | 70 |
| 2-3 | 50 |
| 1 | 30 |
| 0 | 10 |

**💰 Revenue Score** - Based on percentile rank of estimated weekly revenue among all leads.

**Letter Grades:**
| Grade | Score Range | Meaning |
|-------|-----------|---------|
| A | 80-100 | Hot lead - prioritize outreach |
| B | 65-79 | Strong lead - good fit |
| C | 50-64 | Moderate - worth considering |
| D | 35-49 | Lower priority |
| F | 0-34 | Poor fit at this time |
""")
