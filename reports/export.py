"""Export reports to CSV and Excel formats."""

import io
import pandas as pd


def export_to_csv(df):
    """Export a DataFrame to CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")


def export_dc_report_excel(report_data):
    """Export a DC report to a multi-sheet Excel workbook.

    Args:
        report_data: dict from generate_dc_report()

    Returns:
        bytes of the Excel file
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Summary sheet
        summary = report_data["summary"]
        summary_df = pd.DataFrame([{
            "DC Name": summary["dc_name"],
            "DC Code": summary["dc_code"],
            "Address": summary["dc_address"],
            "Total Routes": summary["total_routes"],
            "Total Customers": summary["total_customers"],
            "Total Leads": summary["total_leads"],
            "Weekly Revenue": summary["total_revenue"],
            "A Leads": summary["grade_distribution"]["A"],
            "B Leads": summary["grade_distribution"]["B"],
            "C Leads": summary["grade_distribution"]["C"],
            "D Leads": summary["grade_distribution"]["D"],
            "F Leads": summary["grade_distribution"]["F"],
            "Core Segment Leads": summary["core_segment_leads"],
            "Est. Revenue Opportunity (A+B)": summary["estimated_revenue_opportunity"],
        }])
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        # Route Comparison
        if not report_data["route_comparison"].empty:
            rc = report_data["route_comparison"].copy()
            rc.columns = [c.replace("_", " ").title() for c in rc.columns]
            rc.to_excel(writer, sheet_name="Route Comparison", index=False)

        # Top Leads
        if not report_data["top_leads"].empty:
            tl = report_data["top_leads"].copy()
            tl.columns = [c.replace("_", " ").title() for c in tl.columns]
            tl.to_excel(writer, sheet_name="Top 20 Leads", index=False)

        # Segment Analysis
        if not report_data["segment_analysis"].empty:
            sa = report_data["segment_analysis"].copy()
            sa.columns = [c.replace("_", " ").title() for c in sa.columns]
            sa.to_excel(writer, sheet_name="Segment Analysis", index=False)

    return output.getvalue()


def export_route_report_excel(report_data):
    """Export a route report to a multi-sheet Excel workbook.

    Args:
        report_data: dict from generate_route_report()

    Returns:
        bytes of the Excel file
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Summary
        s = report_data["summary"]
        summary_df = pd.DataFrame([{
            "Route Code": s["route_code"],
            "Route Name": s["route_name"],
            "Distribution Center": s["dc_name"],
            "Days": s["day_of_week"],
            "Driver": s.get("driver_name", ""),
            "Customer Count": s["customer_count"],
            "Weekly Revenue": s["total_weekly_revenue"],
            "Total Leads": s["lead_count"],
            "A Leads": s["a_leads"],
            "B Leads": s["b_leads"],
            "Avg Lead Score": s["avg_lead_score"],
            "Lead Revenue Opportunity": s["lead_revenue_opportunity"],
        }])
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        # Customers
        if not report_data["customers"].empty:
            cust = report_data["customers"].copy()
            cust.columns = [c.replace("_", " ").title() for c in cust.columns]
            cust.to_excel(writer, sheet_name="Customers", index=False)

        # Leads
        if not report_data["leads"].empty:
            leads = report_data["leads"][[
                "name", "business_type", "segment", "address", "total_score",
                "score_grade", "is_core_segment", "proximity_score", "segment_score",
                "density_score", "revenue_score", "nearest_route_stop_distance_mi",
                "nearest_stop_name", "suggested_insertion_sequence",
                "estimated_weekly_revenue", "why_this_lead", "nearest_stop_info",
                "phone", "status",
            ]].copy()
            leads.columns = [c.replace("_", " ").title() for c in leads.columns]
            leads.to_excel(writer, sheet_name="Leads", index=False)

    return output.getvalue()


def generate_leads_csv(leads_df):
    """Export all scored leads to CSV with key fields."""
    if leads_df.empty:
        return b""

    export_cols = [
        "name", "address", "city", "state", "zip_code", "business_type", "segment",
        "phone", "estimated_weekly_revenue", "total_score", "score_grade",
        "is_core_segment", "proximity_score", "segment_score", "density_score",
        "revenue_score", "nearest_route_stop_distance_mi", "nearest_route_code",
        "nearest_stop_name", "status", "assigned_salesperson",
    ]
    available = [c for c in export_cols if c in leads_df.columns]
    return leads_df[available].to_csv(index=False).encode("utf-8")
