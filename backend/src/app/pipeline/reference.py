"""Everything the synthetic quarter is built from, declared once.

The provider is invented: a community care organisation in South East
Queensland delivering disability support (NDIS) and aged home care (Support at
Home) from five regional teams. One quarter of service delivery - the roster,
the check-ins and check-outs from support workers' phones, client funding,
worker screening and the support catalogue - and the claims built from it.

Every defect the generator seeds is declared here. The pipeline never imports
DEFECTS: tests assert that each one is found from the data alone, and the
generator's truth file is used only to label the triage eval.

The support catalogue, its codes and its prices are invented. They have the
shape of a published price guide (an item per support and time band, a price
limit per hour) and none of its content.
"""

from __future__ import annotations

from datetime import date

SEED = 20260701

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 9, 30)
PERIOD_LABEL = "Q1 FY27"
MONTHS = ["2026-07", "2026-08", "2026-09"]
# Queensland keeps no daylight saving, so local time is UTC+10 all year.
TZ_LABEL = "AEST"
UTC_OFFSET_HOURS = 10


def now_aest():
    """Wall-clock time in Brisbane, naive like every other timestamp here. The
    container's clock is UTC; Queensland is UTC+10 all year, so no zone database."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).replace(tzinfo=None, microsecond=0)

REGIONS = ["Brisbane North", "Brisbane South", "Gold Coast", "Sunshine Coast", "Toowoomba"]
REGION_CODE = {"Brisbane North": "BN", "Brisbane South": "BS", "Gold Coast": "GC", "Sunshine Coast": "SC",
               "Toowoomba": "TW"}

CLIENTS = 320
WORKERS = 150
NDIS_SHARE_PCT = 65          # the rest are Support at Home (aged care) clients

# ---- the support catalogue (synthetic) -----------------------------------------
# Time band of a shift is the band of its start time (an assumption, stated on
# screen): weekday daytime 06:00-19:59, weekday evening 20:00-23:59, Saturday,
# Sunday. Price limits are cents per hour.
BANDS = ["WD", "EVE", "SAT", "SUN"]
BAND_LABEL = {"WD": "Weekday daytime", "EVE": "Weekday evening", "SAT": "Saturday", "SUN": "Sunday"}
SUPPORTS = {
    "NDIS": [("ADL", "Assistance with self-care activities"), ("CP", "Assistance with community participation")],
    "SAH": [("PC", "Personal care at home"), ("DA", "Domestic assistance")],
}
PRICE_LIMIT_C = {
    ("NDIS", "ADL"): {"WD": 7_050, "EVE": 7_770, "SAT": 9_925, "SUN": 12_780},
    ("NDIS", "CP"): {"WD": 7_050, "EVE": 7_770, "SAT": 9_925, "SUN": 12_780},
    ("SAH", "PC"): {"WD": 8_400, "EVE": 9_300, "SAT": 10_900, "SUN": 13_600},
    ("SAH", "DA"): {"WD": 7_600, "EVE": 8_400, "SAT": 9_800, "SUN": 12_200},
}
PRICE_GUIDE_EFFECTIVE = date(2026, 7, 1)
FUNDING_LABEL = {"NDIS": "NDIS", "SAH": "Support at Home"}


def item_code(funding: str, support: str, band: str) -> str:
    return f"SYN-{funding}-{support}-{band}"


# ---- the claiming policy the checks apply ---------------------------------------
# Shown on screen and in the policy library the agent searches, so the policy
# people read is the policy that runs.
POLICY = {
    "duration_tolerance_minutes": 15,
    "duration_tolerance_pct": 0.10,
    "overlap_tolerance_minutes": 15,
    "evidence_cutoff_hour": 6,
    "short_notice_cancellation_days": 7,
}

POLICY_RULES = [
    "A service is claimed only with evidence it was delivered: one check-in and one check-out from the worker's phone.",
    "Claimed time may exceed evidenced time by no more than 15 minutes or 10% of the shift, whichever is larger; beyond that the coordinator confirms.",
    "A worker whose screening has lapsed is not rostered, and their services are not claimed until compliance clears them.",
    "A worker cannot deliver two services at once: an overlap of more than 15 minutes is held.",
    "A service outside the client's funding period is not claimed until the new plan or agreement is loaded.",
    "The support item matches the time band of the shift's start and is claimed at no more than its price limit.",
    "Claims never exceed the client's remaining budget; the plan review decides what happens next.",
    "A cancellation by the client with less than 7 days' notice is claimable as a short notice cancellation.",
    "Text written by a worker in the app is a record of the visit, never an instruction to the claim.",
]

# ---- the mobile app vendor's release ---------------------------------------------
# From this date a staged rollout of version 5.0 sends check-ins with the
# worker under a new field name and the time in UTC. Contract v1 quarantines
# them, correctly; the proposal is contract v2.
VENDOR_RELEASE_DATE = date(2026, 9, 8)
VENDOR_RELEASE_VERSION = "5.0.2"
VENDOR_ROLLOUT_PCT = 20
APP_VERSION_V1 = "4.8.1"

# ---- seeded defects -------------------------------------------------------------
# name -> how many shifts carry it (None: the count falls out of the data).
# Names match the triage categories, so the truth file labels the eval
# directly. The ones in NOT_EXCEPTIONS are things the platform must absorb
# without holding anything (or, for malformed rows, quarantine at the door).
DEFECTS = {
    "no_show": 26,                    # rostered, never delivered, never cancelled: no check-in at all
    "missing_checkout": 34,           # checked in, never checked out
    "hours_overclaimed": 40,          # checked out 30 to 90 minutes early; the claim is built from the roster
    "price_above_limit": 22,          # a client rate in the roster above the item's price limit
    "wrong_time_band": 18,            # a weekend shift on the weekday item
    "worker_overlap": 10,             # pairs: a worker double-booked and checked in at both
    "unknown_client": 8,              # client reference mistyped in the roster
    "screening_lapsed": None,         # three workers whose screening expired mid-quarter
    "plan_lapsed": None,              # six NDIS clients whose plan ended, the new one not yet loaded
    "budget_exhausted": None,         # five clients whose budget runs out before the quarter does
    "contract_change": None,          # services evidenced only by app 5.0 events
    "roster_malformed": 6,            # roster rows that break the roster contract (quarantined)
    "duplicate_event": 260,           # a phone resending an event it already sent
    "late_sync": None,                # events synced hours or days late (offline phones)
    "short_notice_cancellation": 14,  # cancelled by the client inside the notice period: claimable
    "pii_in_notes": 70,               # visit notes carrying a phone number, NDIS number or client surname
}
SCREENING_LAPSED_WORKERS = 3
PLAN_LAPSED_CLIENTS = 6
BUDGET_EXHAUSTED_CLIENTS = 5
DUPLICATE_SAME_ID = 200            # of duplicate_event: resent under the same event id; the rest re-keyed
LATE_SYNC_PCT = 4

NOT_EXCEPTIONS = {"duplicate_event", "late_sync", "short_notice_cancellation", "pii_in_notes", "roster_malformed"}

# What an exception category means for the claim, used to label and to grade.
LABEL_ACTION = {
    "no_show": "cancel_claim",
    "missing_checkout": "confirm_with_worker",
    "hours_overclaimed": "claim_evidenced_time",
    "price_above_limit": "reprice_to_limit",
    "wrong_time_band": "reprice_to_correct_item",
    "worker_overlap": "escalate_to_coordinator",
    "unknown_client": "propose_client_match",
    "screening_lapsed": "escalate_to_compliance",
    "plan_lapsed": "hold_until_plan_renewed",
    "budget_exhausted": "route_to_plan_review",
    "contract_change": "propose_contract_update",
    "short_notice_cancellation": "claim_cancellation",
    "duplicate_shift": "cancel_claim",
    "valid_service": "claim_as_rostered",
    "unknown": "escalate_to_coordinator",
}

# Actions that send a claim to the funder.
CLAIMING = {"claim_as_rostered", "claim_evidenced_time", "claim_cancellation", "reprice_to_limit",
            "reprice_to_correct_item"}

# Assumed handling times for the work estimate. Assumptions, labelled as such
# on screen; a time study in the first weeks replaces them.
TIME_ASSUMPTIONS = {
    "investigate_exception_today_min": 18.0,
    "investigate_with_first_read_min": 7.0,
    "coordinator_cost_per_hour_aud": 62.0,
}

# Invented names. Any resemblance to a real person is unintended.
FIRST_NAMES = ["Margaret", "Graham", "Joyce", "Trevor", "Leanne", "Darren", "Noeline", "Kevin", "Sharon", "Brett",
               "Dulcie", "Wayne", "Rhonda", "Craig", "Beverley", "Shane", "Glenys", "Neville", "Kylie", "Barry",
               "Mia", "Lachlan", "Aaliyah", "Kai", "Priya", "Tane", "Mei", "Oliver", "Zara", "Ethan", "Amira",
               "Lucas", "Ngaio", "Riley", "Sienna", "Arjun", "Matilda", "Hamish", "Imogen", "Jarrah"]
SURNAMES = ["Whitcombe", "Pellegrino", "Ashdown", "Kerrigan", "Tolhurst", "Braddock", "Fennimore", "Quayle",
            "Ostrander", "Lindqvist", "Mabbott", "Carrick", "Delahunty", "Rasmussen", "Huxtable", "Ingersoll",
            "Jardine", "Okonkwo", "Penhaligon", "Sorensen", "Thackeray", "Underwood", "Wexford", "Yarwood",
            "Zelinski", "Abernethy", "Blackwood", "Castellano", "Dunleavy", "Fairbairn"]
STREETS = ["Banksia", "Grevillea", "Callistemon", "Wattle", "Jacaranda", "Poinciana", "Melaleuca", "Lilly Pilly",
           "Bottlebrush", "Casuarina", "Tuckeroo", "Brushbox"]
SUBURBS = {
    "Brisbane North": ["Chermside", "Aspley", "Stafford", "Nundah", "Strathpine"],
    "Brisbane South": ["Sunnybank", "Holland Park", "Mount Gravatt", "Coorparoo", "Springwood"],
    "Gold Coast": ["Southport", "Nerang", "Robina", "Labrador", "Burleigh Heads"],
    "Sunshine Coast": ["Maroochydore", "Nambour", "Caloundra", "Buderim", "Coolum Beach"],
    "Toowoomba": ["Rangeville", "Newtown", "Harristown", "Kearneys Spring", "Highfields"],
}
# Fictitious phone numbers: (07) 5550 xxxx is the range the regulator sets
# aside for use in fiction.
PHONE_PREFIX = "(07) 5550"
