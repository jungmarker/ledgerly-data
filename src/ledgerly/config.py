"""Business assumptions for the fictional B2B SaaS company "Ledgerly".

Ledgerly sells a seat-based finance-operations platform. Every number that shapes
the simulation lives here so the assumptions are easy to read and change.
"""
from dataclasses import dataclass
from datetime import date

START = date(2023, 1, 1)
AS_OF = date(2026, 9, 30)  # snapshot date: anything after this is "the future"

# List price per seat per month
PLAN_PRICE = {"Starter": 25.0, "Growth": 45.0, "Enterprise": 75.0}


@dataclass(frozen=True)
class Segment:
    name: str
    employees: tuple[int, int]
    plans: tuple[str, ...]
    plan_weights: tuple[float, ...]
    seats: tuple[int, int]
    cycle_days_median: int  # sales cycle length
    win_rate: float  # base new-business win rate
    annual_billing_share: float
    churn_base: float  # renewal churn probability at average health
    max_discount: float


SEGMENTS = {
    "SMB": Segment("SMB", (10, 99), ("Starter", "Growth"), (0.65, 0.35), (5, 40), 21, 0.27, 0.35, 0.22, 0.10),
    "Mid-Market": Segment("Mid-Market", (100, 999), ("Growth", "Enterprise"), (0.75, 0.25), (20, 180), 52, 0.22, 0.80, 0.12, 0.18),
    "Enterprise": Segment("Enterprise", (1000, 20000), ("Enterprise",), (1.0,), (80, 700), 105, 0.17, 1.00, 0.07, 0.25),
}
SEGMENT_MIX = {"SMB": 0.62, "Mid-Market": 0.30, "Enterprise": 0.08}

# Lead sources: share of leads, MQL rate, multiplier on opportunity win rate
LEAD_SOURCES = {
    "Organic Search": (0.24, 0.30, 1.05),
    "Paid Search": (0.20, 0.22, 0.85),
    "Paid Social": (0.12, 0.15, 0.70),
    "Webinar": (0.10, 0.40, 1.00),
    "Events": (0.07, 0.45, 1.10),
    "Partner Referral": (0.07, 0.55, 1.45),
    "Customer Referral": (0.05, 0.60, 1.60),
    "Outbound": (0.15, 0.18, 0.80),
}

# Month-of-year demand seasonality (Jan..Dec)
SEASONALITY = (0.95, 1.0, 1.08, 1.02, 1.0, 0.92, 0.85, 0.9, 1.1, 1.12, 1.0, 0.78)
MONTHLY_LEAD_GROWTH = 0.018
BASE_MONTHLY_LEADS = 420

STAGES = ("Discovery", "Demo", "Proposal", "Negotiation")
STAGE_PROBABILITY = {"Discovery": 0.10, "Demo": 0.25, "Proposal": 0.50, "Negotiation": 0.75}
LOSS_REASONS = ("No Decision", "Price", "Competitor", "Timing", "Missing Feature", "Champion Left")

INDUSTRIES = ("Software", "Healthcare", "Manufacturing", "Retail", "Financial Services", "Nonprofit",
              "Education", "Professional Services", "Logistics", "Real Estate", "Media", "Construction")

STATES = ("CA", "NY", "TX", "FL", "IL", "MA", "WA", "GA", "CO", "NC", "VA", "MD", "PA", "OH", "MN", "AZ",
          "NJ", "OR", "MI", "TN", "UT", "MO", "WI", "IN")
REGION_BY_STATE = {
    **dict.fromkeys(("NY", "MA", "PA", "NJ", "MD", "VA", "NC", "GA", "FL"), "East"),
    **dict.fromkeys(("IL", "OH", "MI", "MN", "WI", "IN", "MO", "TN", "TX"), "Central"),
    **dict.fromkeys(("CA", "WA", "OR", "CO", "AZ", "UT"), "West"),
}

TICKET_CATEGORIES = {
    # category: (base share, priority weights low/normal/high/urgent, routed team)
    "How-To": (0.30, (0.45, 0.45, 0.08, 0.02), "Support Tier 1"),
    "Bug": (0.20, (0.10, 0.45, 0.33, 0.12), "Support Tier 2"),
    "Billing": (0.14, (0.20, 0.55, 0.20, 0.05), "Billing Ops"),
    "Account Access": (0.12, (0.15, 0.45, 0.30, 0.10), "Support Tier 1"),
    "Integration": (0.12, (0.10, 0.50, 0.30, 0.10), "Solutions Engineering"),
    "Feature Request": (0.08, (0.60, 0.35, 0.05, 0.00), "Product"),
    "Cancellation": (0.04, (0.05, 0.40, 0.40, 0.15), "Customer Success"),
}
FEATURES = ("reports_created", "automations_run", "approvals_processed", "api_calls")
INTEGRATIONS = ("NetSuite", "QuickBooks", "Salesforce", "HubSpot", "Slack", "Snowflake", "Workday", "Expensify")
