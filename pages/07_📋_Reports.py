"""Reports page - Generate and export reports."""

import streamlit as st
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db
from database.models import (
    get_all_dcs, get_all_routes, get_routes_by_dc, get_leads_with_scores,
)
from reports.dc_report import generate_dc_report
from reports.route_report import generate_route_report
from reports.export import (
    export_dc_report_excel, export_route_report_excel,
    generate_leads_csv, export_to_csv,
)
from utils.auth import require_auth

init_db()

st.set_page_config(page_title="Reports", page_icon="📋", layout="wide")
require_auth()
st.title("📋 Reports")
st.markdown("Generate and download reports for distribution centers and routes")

dcs = get_all_dcs()
if dcs.empty:
    st.info("No data found. Go to **Upload Data** to import your data.")
    st.stop()

# Report type selection
report_type = st.radio(
    "Select Report Type",
    ["DC-Level Report", "Route-Level Report", "All Leads Export"],
    horizontal=True,
)

st.markdown("---")

if report_type == "DC-Level Report":
    dc_options = {row["id"]: f"{row['code']} - {row['name']}" for _, row in dcs.iterrows()}
    selected_dc = st.selectbox("Select Distribution Center", list(dc_options.keys()),
                                format_func=lambda x: dc_options[x])

    if st.button("📊 Generate DC Report", use_container_width=True):
        with st.spinner("Generating report..."):
            report = generate_dc_report(selected_dc)

        if report:
            summary = report["summary"]

            st.markdown(f"### {summary['dc_name']} Report")

            # Summary section
            st.markdown("#### Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Routes", summary["total_routes"])
            with col2:
                st.metric("Customers", summary["total_customers"])
            with col3:
                st.metric("Total Leads", summary["total_leads"])
            with col4:
                st.metric("Est. Opportunity", f"${summary['estimated_revenue_opportunity']:,.0f}/wk")

            # Route comparison
            if not report["route_comparison"].empty:
                st.markdown("#### Route Comparison")
                st.dataframe(report["route_comparison"], use_container_width=True, hide_index=True)

            # Top leads
            if not report["top_leads"].empty:
                st.markdown("#### Top 20 Leads")
                st.dataframe(report["top_leads"], use_container_width=True, hide_index=True)

            # Download
            st.markdown("---")
            excel_data = export_dc_report_excel(report)
            st.download_button(
                "⬇️ Download DC Report (Excel)",
                excel_data,
                f"dc_report_{summary['dc_code']}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.error("Could not generate report.")

elif report_type == "Route-Level Report":
    col1, col2 = st.columns(2)
    with col1:
        dc_options = {"all": "All DCs"}
        dc_options.update({row["id"]: f"{row['code']} - {row['name']}" for _, row in dcs.iterrows()})
        selected_dc = st.selectbox("Filter by DC", list(dc_options.keys()),
                                    format_func=lambda x: dc_options[x], key="rpt_dc")

    with col2:
        if selected_dc == "all":
            routes = get_all_routes()
        else:
            routes = get_routes_by_dc(selected_dc)

        if routes.empty:
            st.warning("No routes found.")
            st.stop()

        route_options = {row["id"]: f"{row['route_code']} - {row.get('route_name', '')}" for _, row in routes.iterrows()}
        selected_route = st.selectbox("Select Route", list(route_options.keys()),
                                       format_func=lambda x: route_options[x], key="rpt_route")

    if st.button("📊 Generate Route Report", use_container_width=True):
        with st.spinner("Generating report..."):
            report = generate_route_report(selected_route)

        if report:
            summary = report["summary"]
            st.markdown(f"### Route {summary['route_code']} Report")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Customers", summary["customer_count"])
            with col2:
                st.metric("Revenue", f"${summary['total_weekly_revenue']:,.0f}/wk")
            with col3:
                st.metric("Leads", summary["lead_count"])
            with col4:
                st.metric("Hot Leads", summary["a_leads"])

            # Customers
            if not report["customers"].empty:
                st.markdown("#### Delivery Stops")
                st.dataframe(report["customers"], use_container_width=True, hide_index=True)

            # Leads
            if not report["leads"].empty:
                st.markdown("#### Prospects")
                lead_display = report["leads"][[
                    c for c in ["name", "business_type", "segment", "total_score", "score_grade",
                                "is_core_segment", "nearest_route_stop_distance_mi",
                                "nearest_stop_name", "estimated_weekly_revenue",
                                "why_this_lead", "phone", "status"]
                    if c in report["leads"].columns
                ]].copy()
                st.dataframe(lead_display, use_container_width=True, hide_index=True)

            # Download
            st.markdown("---")
            excel_data = export_route_report_excel(report)
            st.download_button(
                "⬇️ Download Route Report (Excel)",
                excel_data,
                f"route_report_{summary['route_code']}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        else:
            st.error("Could not generate report.")

elif report_type == "All Leads Export":
    st.markdown("### Export All Scored Leads")
    st.markdown("Download a CSV or Excel file of all leads with their scores and nearest stop information.")

    scored = get_leads_with_scores()
    if scored.empty:
        st.warning("No scored leads to export. Run **Score All Leads** first.")
    else:
        st.write(f"**{len(scored)} leads** available for export")

        # Preview
        st.dataframe(scored.head(20), use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            csv_data = generate_leads_csv(scored)
            st.download_button(
                "⬇️ Download All Leads (CSV)",
                csv_data,
                "all_leads.csv",
                "text/csv",
                use_container_width=True,
            )
        with col2:
            csv_full = scored.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download Full Data (CSV)",
                csv_full,
                "all_leads_full.csv",
                "text/csv",
                use_container_width=True,
            )
