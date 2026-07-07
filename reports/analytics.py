"""Cross-cutting CRM analytics: forecasting, territory, leaderboard, trends."""

import pandas as pd

from database.connection import get_connection
from database.models import get_all_deals

CLOSED_STAGES = ("Closed Won", "Closed Lost")

# Latest score row per lead (mirrors get_leads_with_scores)
_LATEST_SCORE_FILTER = (
    "s.id = (SELECT MAX(s2.id) FROM lead_scores s2 WHERE s2.lead_id = s.lead_id)"
)

_FORECAST_STAGE_COLUMNS = ["stage_name", "deal_count", "total_revenue", "weighted_revenue"]
_LEADERBOARD_COLUMNS = ["salesperson", "won_count", "won_revenue", "open_count",
                        "open_pipeline", "activities_logged", "win_rate"]


def compute_pipeline_forecast():
    """Forecast revenue from open deals weighted by stage probability.

    Returns:
        dict with:
        - weighted_total: sum of expected_weekly_revenue * probability_pct / 100
        - best_case: sum of expected_weekly_revenue (all open deals)
        - by_stage: DataFrame(stage_name, deal_count, total_revenue, weighted_revenue)
    """
    empty = {
        "weighted_total": 0.0,
        "best_case": 0.0,
        "by_stage": pd.DataFrame(columns=_FORECAST_STAGE_COLUMNS),
    }

    deals = get_all_deals()
    if deals.empty:
        return empty

    open_deals = deals[~deals["stage_name"].isin(CLOSED_STAGES)].copy()
    if open_deals.empty:
        return empty

    open_deals["expected_weekly_revenue"] = open_deals["expected_weekly_revenue"].fillna(0)
    open_deals["weighted_revenue"] = (
        open_deals["expected_weekly_revenue"] * open_deals["probability_pct"] / 100.0
    )

    by_stage = (
        open_deals.groupby(["display_order", "stage_name"], as_index=False)
        .agg(
            deal_count=("id", "count"),
            total_revenue=("expected_weekly_revenue", "sum"),
            weighted_revenue=("weighted_revenue", "sum"),
        )
        .sort_values("display_order")[_FORECAST_STAGE_COLUMNS]
        .reset_index(drop=True)
    )

    return {
        "weighted_total": float(open_deals["weighted_revenue"].sum()),
        "best_case": float(open_deals["expected_weekly_revenue"].sum()),
        "by_stage": by_stage,
    }


def compute_territory_performance():
    """Per-route territory rollup of customers, scored leads and open pipeline.

    Leads and deals attach to a route via the latest lead score's
    nearest_route_id; customers attach via customers.route_id.

    Returns:
        DataFrame(route_code, route_name, customer_count, total_weekly_revenue,
                  lead_count, a_b_lead_count, open_deal_count, pipeline_revenue)
    """
    conn = get_connection()
    df = pd.read_sql_query(
        f"""SELECT r.route_code, r.route_name,
               COALESCE(c.customer_count, 0) as customer_count,
               COALESCE(c.total_weekly_revenue, 0) as total_weekly_revenue,
               COALESCE(ls.lead_count, 0) as lead_count,
               COALESCE(ls.a_b_lead_count, 0) as a_b_lead_count,
               COALESCE(dl.open_deal_count, 0) as open_deal_count,
               COALESCE(dl.pipeline_revenue, 0) as pipeline_revenue
           FROM routes r
           LEFT JOIN (
               SELECT route_id, COUNT(*) as customer_count,
                      COALESCE(SUM(weekly_revenue), 0) as total_weekly_revenue
               FROM customers
               WHERE is_active = 1
               GROUP BY route_id
           ) c ON c.route_id = r.id
           LEFT JOIN (
               SELECT s.nearest_route_id as route_id, COUNT(*) as lead_count,
                      SUM(CASE WHEN s.score_grade IN ('A', 'B') THEN 1 ELSE 0 END)
                          as a_b_lead_count
               FROM lead_scores s
               WHERE {_LATEST_SCORE_FILTER}
               GROUP BY s.nearest_route_id
           ) ls ON ls.route_id = r.id
           LEFT JOIN (
               SELECT s.nearest_route_id as route_id,
                      COUNT(*) as open_deal_count,
                      COALESCE(SUM(d.expected_weekly_revenue), 0) as pipeline_revenue
               FROM deals d
               JOIN pipeline_stages ps ON d.stage_id = ps.id
               JOIN lead_scores s ON s.lead_id = d.lead_id
                   AND {_LATEST_SCORE_FILTER}
               WHERE ps.name NOT IN ('Closed Won', 'Closed Lost')
               GROUP BY s.nearest_route_id
           ) dl ON dl.route_id = r.id
           WHERE r.is_active = 1
           ORDER BY r.route_code""",
        conn,
    )
    conn.close()
    return df


def compute_salesperson_leaderboard(days=90):
    """Per-salesperson performance across deals and logged activities.

    Won stats count deals closed as 'Closed Won' within the last `days` days;
    win_rate is won / (won + lost) among deals closed in the window.

    Returns:
        DataFrame(salesperson, won_count, won_revenue, open_count,
                  open_pipeline, activities_logged, win_rate)
    """
    conn = get_connection()
    deal_agg = pd.read_sql_query(
        """SELECT d.assigned_salesperson as salesperson,
               SUM(CASE WHEN ps.name = 'Closed Won' AND d.closed_at IS NOT NULL
                        AND julianday('now') - julianday(d.closed_at) <= :days
                   THEN 1 ELSE 0 END) as won_count,
               SUM(CASE WHEN ps.name = 'Closed Won' AND d.closed_at IS NOT NULL
                        AND julianday('now') - julianday(d.closed_at) <= :days
                   THEN d.expected_weekly_revenue ELSE 0 END) as won_revenue,
               SUM(CASE WHEN ps.name = 'Closed Lost' AND d.closed_at IS NOT NULL
                        AND julianday('now') - julianday(d.closed_at) <= :days
                   THEN 1 ELSE 0 END) as lost_count,
               SUM(CASE WHEN ps.name NOT IN ('Closed Won', 'Closed Lost')
                   THEN 1 ELSE 0 END) as open_count,
               SUM(CASE WHEN ps.name NOT IN ('Closed Won', 'Closed Lost')
                   THEN d.expected_weekly_revenue ELSE 0 END) as open_pipeline
           FROM deals d
           JOIN pipeline_stages ps ON d.stage_id = ps.id
           GROUP BY d.assigned_salesperson""",
        conn,
        params={"days": days},
    )
    activity_agg = pd.read_sql_query(
        """SELECT logged_by as salesperson, COUNT(*) as activities_logged
           FROM activities
           WHERE julianday('now') - julianday(activity_date) <= ?
           GROUP BY logged_by""",
        conn,
        params=(days,),
    )
    conn.close()

    merged = pd.merge(deal_agg, activity_agg, on="salesperson", how="outer")

    # Drop rows without an attributable person
    merged = merged[merged["salesperson"].notna()]
    merged = merged[merged["salesperson"].astype(str).str.strip() != ""]

    if merged.empty:
        return pd.DataFrame(columns=_LEADERBOARD_COLUMNS)

    count_cols = ["won_count", "won_revenue", "lost_count", "open_count",
                  "open_pipeline", "activities_logged"]
    merged[count_cols] = merged[count_cols].fillna(0)
    for col in ["won_count", "lost_count", "open_count", "activities_logged"]:
        merged[col] = merged[col].astype(int)

    closed = merged["won_count"] + merged["lost_count"]
    merged["win_rate"] = (merged["won_count"] / closed.where(closed > 0)).fillna(0.0)

    return (
        merged.sort_values(["won_revenue", "open_pipeline"], ascending=False)
        [_LEADERBOARD_COLUMNS]
        .reset_index(drop=True)
    )


def compute_revenue_trending(months=6):
    """Monthly trend of new leads and won deals over the last `months` months.

    Buckets are 'YYYY-MM' strings; months with no data are included as zeros.

    Returns:
        DataFrame(month, new_leads, deals_won, revenue_won)
    """
    conn = get_connection()
    current_month = conn.execute("SELECT strftime('%Y-%m', 'now')").fetchone()[0]
    leads_by_month = pd.read_sql_query(
        """SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as new_leads
           FROM leads
           WHERE created_at IS NOT NULL
           GROUP BY month""",
        conn,
    )
    won_by_month = pd.read_sql_query(
        """SELECT strftime('%Y-%m', d.closed_at) as month,
               COUNT(*) as deals_won,
               COALESCE(SUM(d.expected_weekly_revenue), 0) as revenue_won
           FROM deals d
           JOIN pipeline_stages ps ON d.stage_id = ps.id
           WHERE ps.name = 'Closed Won' AND d.closed_at IS NOT NULL
           GROUP BY month""",
        conn,
    )
    conn.close()

    month_labels = [
        str(p) for p in pd.period_range(end=current_month, periods=months, freq="M")
    ]
    trend = pd.DataFrame({"month": month_labels})
    trend = trend.merge(leads_by_month, on="month", how="left")
    trend = trend.merge(won_by_month, on="month", how="left")
    trend[["new_leads", "deals_won"]] = trend[["new_leads", "deals_won"]].fillna(0).astype(int)
    trend["revenue_won"] = trend["revenue_won"].fillna(0.0)
    return trend


def compute_activity_metrics(days=30):
    """Activity volume within the last `days` days.

    Returns:
        dict with:
        - by_type: DataFrame(activity_type, count), busiest first
        - total: int, all activities in the window
        - by_person: DataFrame(logged_by, count), null/blank loggers excluded
    """
    conn = get_connection()
    by_type = pd.read_sql_query(
        """SELECT activity_type, COUNT(*) as count
           FROM activities
           WHERE julianday('now') - julianday(activity_date) <= ?
           GROUP BY activity_type
           ORDER BY count DESC, activity_type""",
        conn,
        params=(days,),
    )
    by_person = pd.read_sql_query(
        """SELECT logged_by, COUNT(*) as count
           FROM activities
           WHERE julianday('now') - julianday(activity_date) <= ?
             AND logged_by IS NOT NULL AND TRIM(logged_by) != ''
           GROUP BY logged_by
           ORDER BY count DESC, logged_by""",
        conn,
        params=(days,),
    )
    total = conn.execute(
        """SELECT COUNT(*) FROM activities
           WHERE julianday('now') - julianday(activity_date) <= ?""",
        (days,),
    ).fetchone()[0]
    conn.close()

    return {"by_type": by_type, "total": int(total), "by_person": by_person}
