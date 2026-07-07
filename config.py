"""Application configuration for Lead Generation Tool."""

import os

# Database - can override with LEAD_GEN_DB_PATH environment variable
DB_PATH = os.environ.get("LEAD_GEN_DB_PATH", os.path.join(os.path.dirname(__file__), "lead_gen.db"))

# Scoring weights (must sum to 1.0)
DEFAULT_WEIGHTS = {
    "proximity": 0.35,
    "segment": 0.25,
    "density": 0.25,
    "revenue": 0.15,
}

# Proximity scoring thresholds (miles -> score)
PROXIMITY_TIERS = [
    (0.5, 100),
    (1.0, 85),
    (2.0, 70),
    (5.0, 50),
    (10.0, 30),
    (20.0, 15),
]
PROXIMITY_DEFAULT_SCORE = 5  # Beyond max tier

# Density scoring thresholds (customer count within radius -> score)
DENSITY_RADIUS_MILES = 1.0
DENSITY_TIERS = [
    (10, 100),
    (7, 85),
    (4, 70),
    (2, 50),
    (1, 30),
]
DENSITY_DEFAULT_SCORE = 10  # Zero nearby customers

# Segment scoring
SEGMENT_EXACT_MATCH = 100
SEGMENT_TYPE_MATCH = 60
SEGMENT_ADJACENT_MATCH = 40
SEGMENT_NO_MATCH = 10

# Adjacent business type mappings
ADJACENT_TYPES = {
    "Restaurant": ["Bar/Tavern", "Catering"],
    "Bar/Tavern": ["Restaurant"],
    "Hotel": ["Resort", "Convention Center"],
    "Catering": ["Restaurant", "Bar/Tavern"],
    "Convenience Store": ["Grocery"],
    "Grocery": ["Convenience Store"],
}

# Grade thresholds
GRADE_THRESHOLDS = {
    "A": 80,
    "B": 65,
    "C": 50,
    "D": 35,
}
# Below D threshold = F

# Lead statuses
LEAD_STATUSES = ["New", "Contacted", "Qualified", "Converted", "Rejected"]

# Business types
BUSINESS_TYPES = [
    "Restaurant",
    "Bar/Tavern",
    "Hotel",
    "Hospital/Healthcare",
    "School/University",
    "Convenience Store",
    "Grocery",
    "Catering",
    "Office Complex",
    "Fitness Center",
]

# Segments
SEGMENTS = [
    "Full-Service Restaurant",
    "Quick-Service Restaurant",
    "C-Store",
    "Hospitality",
    "Healthcare",
    "Education",
    "Corporate",
    "Retail",
    "Entertainment",
    "Other",
]

# Geocoding
GEOCODING_TIMEOUT = 10
GEOCODING_RATE_LIMIT_DELAY = 1.1  # seconds between requests

# Duplicate detection
DUPLICATE_DISTANCE_THRESHOLD_MI = 0.05  # ~264 feet
DUPLICATE_NAME_SIMILARITY_THRESHOLD = 85  # fuzzy match score 0-100

# Map defaults
MAP_DEFAULT_ZOOM = 11
MAP_TILE_STYLE = "OpenStreetMap"

# Restaurant discovery (OpenStreetMap Overpass API)
OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60  # seconds per request
OVERPASS_RATE_LIMIT_DELAY = 1.1  # seconds between requests
OVERPASS_MAX_RETRIES = 3
OVERPASS_DEFAULT_RADIUS_MI = 1.0
DISCOVERY_AMENITY_TYPES = {
    "restaurant": "Restaurant",
    "fast_food": "Fast Food",
    "cafe": "Cafe",
    "bar": "Bar",
    "pub": "Pub",
}
AMENITY_BUSINESS_TYPE_MAP = {
    "restaurant": ("Restaurant", "Full-Service Restaurant"),
    "fast_food": ("Restaurant", "Quick-Service Restaurant"),
    "cafe": ("Restaurant", "Quick-Service Restaurant"),
    "bar": ("Bar", "Entertainment"),
    "pub": ("Bar", "Entertainment"),
}

# CRM: contacts & activities
ACTIVITY_TYPES = ["Call", "Email", "Meeting", "Note", "Status Change"]
CONTACT_METHODS = ["Phone", "Email", "In Person", "Text"]

# CRM: sales pipeline
DEFAULT_PIPELINE_STAGES = [
    # (name, display_order, probability_pct)
    ("Prospect", 1, 10),
    ("Qualified", 2, 25),
    ("Proposal", 3, 50),
    ("Negotiation", 4, 75),
    ("Closed Won", 5, 100),
    ("Closed Lost", 6, 0),
]
