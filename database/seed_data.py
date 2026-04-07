"""Generate realistic sample data for the Denver, CO metro area."""

import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.connection import init_db, seed_core_segments, get_connection
from database.models import (
    upsert_dc, upsert_route, insert_customer, insert_route_stop, insert_lead,
    rebuild_route_stops,
)

random.seed(42)

# Denver metro area base coordinates
DENVER_CENTER = (39.7392, -104.9903)

BUSINESS_CONFIGS = [
    ("Restaurant", "Full-Service Restaurant", 800, 300),
    ("Restaurant", "Quick-Service Restaurant", 500, 200),
    ("Convenience Store", "C-Store", 600, 250),
    ("Hotel", "Hospitality", 1200, 400),
    ("Hospital/Healthcare", "Healthcare", 1500, 500),
    ("School/University", "Education", 700, 300),
    ("Bar/Tavern", "Entertainment", 400, 150),
    ("Grocery", "Retail", 900, 350),
    ("Catering", "Full-Service Restaurant", 650, 250),
    ("Office Complex", "Corporate", 500, 200),
    ("Fitness Center", "Other", 300, 100),
]

STREET_NAMES = [
    "Main St", "Broadway", "Colfax Ave", "Colorado Blvd", "Federal Blvd",
    "Alameda Ave", "Evans Ave", "Hampden Ave", "Belleview Ave", "Arapahoe Rd",
    "Parker Rd", "Wadsworth Blvd", "Sheridan Blvd", "Kipling St", "Simms St",
    "Peoria St", "Havana St", "Chambers Rd", "Tower Rd", "Quincy Ave",
]

FIRST_NAMES = [
    "Golden", "Silver", "Mountain", "Mile High", "Rocky", "Front Range",
    "Alpine", "Summit", "Pioneer", "Sunset", "Eagle", "Aspen", "Cedar",
    "Maple", "Oak", "River", "Lake", "Valley", "Peak", "Ridge",
    "Blue Sky", "Red Rock", "Pine", "Willow", "Birch", "Elk",
]

BIZ_SUFFIXES = {
    "Restaurant": ["Grill", "Kitchen", "Bistro", "Cafe", "Diner", "Eatery"],
    "Bar/Tavern": ["Pub", "Tavern", "Taphouse", "Lounge", "Bar & Grill"],
    "Hotel": ["Inn", "Suites", "Lodge", "Hotel", "Resort"],
    "Hospital/Healthcare": ["Medical Center", "Health Clinic", "Care Center"],
    "School/University": ["Academy", "School", "Institute", "College"],
    "Convenience Store": ["Quick Stop", "Mart", "Express", "Corner Store"],
    "Grocery": ["Market", "Foods", "Grocery", "Fresh Market"],
    "Catering": ["Catering Co.", "Events & Catering", "Banquets"],
    "Office Complex": ["Business Center", "Office Park", "Corporate Plaza"],
    "Fitness Center": ["Fitness", "Gym", "Health Club", "Athletic Club"],
}


def random_biz_name(biz_type):
    first = random.choice(FIRST_NAMES)
    suffix = random.choice(BIZ_SUFFIXES.get(biz_type, ["Services"]))
    return f"{first} {suffix}"


def random_address():
    num = random.randint(100, 9999)
    street = random.choice(STREET_NAMES)
    return f"{num} {street}"


def jitter(base, spread=0.02):
    return base + random.uniform(-spread, spread)


def generate_route_corridor(center_lat, center_lon, num_stops, spread=0.03):
    """Generate a roughly linear corridor of stops."""
    angle = random.uniform(0, 3.14159)
    import math
    stops = []
    for i in range(num_stops):
        t = (i / max(num_stops - 1, 1)) - 0.5  # -0.5 to 0.5
        lat = center_lat + t * spread * math.cos(angle) + random.uniform(-0.005, 0.005)
        lon = center_lon + t * spread * math.sin(angle) + random.uniform(-0.005, 0.005)
        stops.append((lat, lon))
    return stops


def seed_database():
    """Generate all sample data."""
    print("Initializing database...")
    init_db()
    seed_core_segments()

    conn = get_connection()
    # Check if data already exists
    count = conn.execute("SELECT COUNT(*) FROM distribution_centers").fetchone()[0]
    conn.close()
    if count > 0:
        print("Data already exists. Skipping seed.")
        return

    print("Creating distribution centers...")
    dcs = [
        ("North Metro DC", "DC-001", "8500 N Washington St", "Thornton", "CO", "80229",
         39.8680, -104.9870),
        ("South Metro DC", "DC-002", "5200 S Santa Fe Dr", "Littleton", "CO", "80120",
         39.6130, -104.9890),
        ("West Side DC", "DC-003", "12000 W Colfax Ave", "Lakewood", "CO", "80215",
         39.7400, -105.1300),
    ]

    dc_ids = []
    for name, code, addr, city, state, zipcode, lat, lon in dcs:
        dc_id = upsert_dc(name, code, addr, city, state, zipcode, lat, lon)
        dc_ids.append(dc_id)
        print(f"  Created DC: {name} (id={dc_id})")

    # Route definitions per DC
    route_defs = {
        0: [  # North Metro DC
            ("R-101", "North Downtown", "MON,WED,FRI", 39.76, -104.98),
            ("R-102", "Thornton/Northglenn", "MON,THU", 39.87, -104.97),
            ("R-103", "Westminster", "TUE,FRI", 39.84, -105.04),
            ("R-104", "Commerce City", "WED,SAT", 39.81, -104.93),
            ("R-105", "Brighton Corridor", "TUE,THU", 39.90, -104.82),
        ],
        1: [  # South Metro DC
            ("R-201", "South Broadway", "MON,WED,FRI", 39.65, -104.99),
            ("R-202", "Englewood/Cherry Hills", "TUE,THU", 39.64, -104.95),
            ("R-203", "Centennial", "MON,WED", 39.58, -104.87),
            ("R-204", "Highlands Ranch", "TUE,FRI", 39.55, -104.97),
            ("R-205", "Lone Tree/Parker", "WED,SAT", 39.53, -104.85),
        ],
        2: [  # West Side DC
            ("R-301", "Lakewood Central", "MON,WED,FRI", 39.73, -105.10),
            ("R-302", "Golden/Arvada", "TUE,THU", 39.77, -105.15),
            ("R-303", "Wheat Ridge", "MON,THU", 39.77, -105.08),
            ("R-304", "Morrison/Ken Caryl", "WED,FRI", 39.65, -105.15),
            ("R-305", "Edgewater/Sloan Lake", "TUE,SAT", 39.75, -105.05),
        ],
    }

    print("Creating routes and customers...")
    all_customer_locations = []

    for dc_idx, dc_id in enumerate(dc_ids):
        for route_code, route_name, days, center_lat, center_lon in route_defs[dc_idx]:
            route_id = upsert_route(dc_id, route_code, route_name, days)
            num_customers = random.randint(12, 25)
            corridor = generate_route_corridor(center_lat, center_lon, num_customers)

            for seq, (lat, lon) in enumerate(corridor, 1):
                biz_type, segment, rev_mean, rev_std = random.choice(BUSINESS_CONFIGS)
                name = random_biz_name(biz_type)
                revenue = max(100, random.gauss(rev_mean, rev_std))

                cust_id = insert_customer(
                    name=name,
                    address=random_address(),
                    city=route_name.split("/")[0].split(" ")[0],
                    state="CO",
                    zip_code=f"80{random.randint(100, 299)}",
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    business_type=biz_type,
                    segment=segment,
                    weekly_revenue=round(revenue, 2),
                    route_id=route_id,
                    stop_sequence=seq,
                )
                all_customer_locations.append((lat, lon))

            rebuild_route_stops(route_id)
            print(f"  Route {route_code}: {num_customers} customers")

    # Generate leads
    print("Creating leads...")
    num_leads = 500
    leads_near = int(num_leads * 0.6)     # 60% within 2 miles of customers
    leads_mid = int(num_leads * 0.25)     # 25% within 2-10 miles
    leads_far = num_leads - leads_near - leads_mid  # 15% far away

    lead_count = 0

    # Near leads (within ~2 miles = ~0.03 degrees)
    for _ in range(leads_near):
        base_lat, base_lon = random.choice(all_customer_locations)
        lat = jitter(base_lat, 0.025)
        lon = jitter(base_lon, 0.025)
        biz_type, segment, rev_mean, rev_std = random.choice(BUSINESS_CONFIGS)
        insert_lead(
            name=random_biz_name(biz_type),
            address=random_address(),
            city="Denver Metro",
            state="CO",
            zip_code=f"80{random.randint(100, 299)}",
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            business_type=biz_type,
            segment=segment,
            estimated_weekly_revenue=round(max(50, random.gauss(rev_mean, rev_std)), 2),
            phone=f"303-{random.randint(200,999)}-{random.randint(1000,9999)}",
            source="Data Import",
        )
        lead_count += 1

    # Mid-distance leads (2-10 miles = ~0.03-0.15 degrees)
    for _ in range(leads_mid):
        base_lat, base_lon = random.choice(all_customer_locations)
        lat = jitter(base_lat, 0.10)
        lon = jitter(base_lon, 0.10)
        biz_type, segment, rev_mean, rev_std = random.choice(BUSINESS_CONFIGS)
        insert_lead(
            name=random_biz_name(biz_type),
            address=random_address(),
            city="Denver Metro",
            state="CO",
            zip_code=f"80{random.randint(100, 399)}",
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            business_type=biz_type,
            segment=segment,
            estimated_weekly_revenue=round(max(50, random.gauss(rev_mean, rev_std)), 2),
            phone=f"720-{random.randint(200,999)}-{random.randint(1000,9999)}",
            source="Data Import",
        )
        lead_count += 1

    # Far leads (10+ miles = ~0.15+ degrees)
    for _ in range(leads_far):
        lat = jitter(DENVER_CENTER[0], 0.25)
        lon = jitter(DENVER_CENTER[1], 0.25)
        biz_type, segment, rev_mean, rev_std = random.choice(BUSINESS_CONFIGS)
        insert_lead(
            name=random_biz_name(biz_type),
            address=random_address(),
            city="Denver Metro",
            state="CO",
            zip_code=f"80{random.randint(100, 499)}",
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            business_type=biz_type,
            segment=segment,
            estimated_weekly_revenue=round(max(50, random.gauss(rev_mean, rev_std)), 2),
            phone=f"303-{random.randint(200,999)}-{random.randint(1000,9999)}",
            source="Data Import",
        )
        lead_count += 1

    print(f"  Created {lead_count} leads")
    print("Seed data generation complete!")


if __name__ == "__main__":
    seed_database()
