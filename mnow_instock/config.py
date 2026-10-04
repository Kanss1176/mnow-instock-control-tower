"""Configuration. Every value marked ASSUMED is an assumption, not an observation."""
from dataclasses import dataclass

# City centres (public geographic coordinates). M-Now city list is from press reports.
CITIES = {
    "Bengaluru": (12.9716, 77.5946), "Mumbai": (19.0760, 72.8777),
    "Pune": (18.5204, 73.8567), "Kolkata": (22.5726, 88.3639),
    "Hyderabad": (17.3850, 78.4867), "Delhi-NCR": (28.6139, 77.2090),
    "Patna": (25.5941, 85.1376), "Jaipur": (26.9124, 75.7873),
    "Lucknow": (26.8467, 80.9462), "Ahmedabad": (23.0225, 72.5714),
}
# ASSUMED: relative city scale, not Myntra data.
CITY_SCALE = {"Bengaluru": 1.0, "Mumbai": 1.0, "Pune": 0.8, "Kolkata": 0.8,
              "Hyderabad": 0.9, "Delhi-NCR": 1.0, "Patna": 0.5, "Jaipur": 0.55,
              "Lucknow": 0.55, "Ahmedabad": 0.65}

CATEGORIES = ["ethnic", "western", "footwear", "beauty", "accessories"]
# ASSUMED: how strongly each category responds to festive events (exponent on uplift).
EVENT_AFFINITY = {"ethnic": 1.0, "western": 0.5, "footwear": 0.6, "beauty": 0.8, "accessories": 0.7}
# ASSUMED: Mon..Sun multipliers. Weekly search data cannot reveal day-of-week shape.
DOW_MULT = [0.90, 0.90, 0.95, 1.00, 1.10, 1.25, 1.20]

CAUSES = {0: "none", 1: "override", 2: "stale_plan_input", 3: "late_inbound",
          4: "supply_shortfall", 5: "forecast_error_or_demand_shock"}


@dataclass
class SimConfig:
    seed: int = 42
    start_date: str = "2025-07-01"
    n_days: int = 180
    stores_per_city: int = 3
    n_skus: int = 120
    service_z: float = 1.28
    lead_mean: float = 2.5          # ASSUMED days
    p_override: float = 0.04        # ASSUMED deviation frequencies per order
    p_stale: float = 0.05
    p_late: float = 0.06
    p_short: float = 0.05
    shock_prob_week: float = 0.01   # ASSUMED unmodelled demand shocks
    regime_day: int = 100           # ASSUMED structural break
    regime_category: str = "western"
    regime_factor: float = 0.6
    min_display_packs: int = 1      # ASSUMED minimum presentation stock, in case packs
    cause_window: int = 10          # days a deviation stays the "true cause" label
