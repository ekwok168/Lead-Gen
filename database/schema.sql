-- Lead Generation Tool Database Schema

CREATE TABLE IF NOT EXISTS distribution_centers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dc_id INTEGER NOT NULL,
    route_code TEXT UNIQUE NOT NULL,
    route_name TEXT,
    day_of_week TEXT,
    driver_name TEXT,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (dc_id) REFERENCES distribution_centers(id)
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    business_type TEXT,
    segment TEXT,
    weekly_revenue REAL DEFAULT 0,
    stop_sequence INTEGER,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (route_id) REFERENCES routes(id)
);

CREATE TABLE IF NOT EXISTS route_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL,
    customer_id INTEGER,
    stop_sequence INTEGER NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    stop_type TEXT DEFAULT 'customer',  -- customer, depot, waypoint
    stop_name TEXT,
    FOREIGN KEY (route_id) REFERENCES routes(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    business_type TEXT,
    segment TEXT,
    estimated_weekly_revenue REAL DEFAULT 0,
    phone TEXT,
    website TEXT,
    source TEXT DEFAULT 'Manual Entry',
    status TEXT DEFAULT 'New',
    assigned_salesperson TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    nearest_route_id INTEGER,
    nearest_dc_id INTEGER,
    nearest_stop_id INTEGER,
    proximity_score REAL DEFAULT 0,
    segment_score REAL DEFAULT 0,
    density_score REAL DEFAULT 0,
    revenue_score REAL DEFAULT 0,
    total_score REAL DEFAULT 0,
    score_grade TEXT DEFAULT 'F',
    is_core_segment INTEGER DEFAULT 0,
    nearest_customer_distance_mi REAL,
    nearest_route_stop_distance_mi REAL,
    suggested_insertion_sequence INTEGER,
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (nearest_route_id) REFERENCES routes(id),
    FOREIGN KEY (nearest_dc_id) REFERENCES distribution_centers(id),
    FOREIGN KEY (nearest_stop_id) REFERENCES route_stops(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    customer_id INTEGER,
    first_name TEXT NOT NULL,
    last_name TEXT,
    title TEXT,
    email TEXT,
    phone TEXT,
    mobile_phone TEXT,
    preferred_contact_method TEXT DEFAULT 'Phone',
    is_primary INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    lead_id INTEGER,
    customer_id INTEGER,
    activity_type TEXT NOT NULL,
    subject TEXT,
    description TEXT,
    outcome TEXT,
    activity_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logged_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS core_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_name TEXT NOT NULL,
    business_type TEXT NOT NULL,
    min_estimated_revenue REAL DEFAULT 0,
    priority INTEGER DEFAULT 5
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_customers_route ON customers(route_id);
CREATE INDEX IF NOT EXISTS idx_customers_location ON customers(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_leads_location ON leads(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_lead_scores_lead ON lead_scores(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_scores_route ON lead_scores(nearest_route_id);
CREATE INDEX IF NOT EXISTS idx_route_stops_route ON route_stops(route_id);
CREATE INDEX IF NOT EXISTS idx_routes_dc ON routes(dc_id);
CREATE INDEX IF NOT EXISTS idx_contacts_lead ON contacts(lead_id);
CREATE INDEX IF NOT EXISTS idx_contacts_customer ON contacts(customer_id);
CREATE INDEX IF NOT EXISTS idx_activities_lead ON activities(lead_id);
CREATE INDEX IF NOT EXISTS idx_activities_contact ON activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(activity_date);
