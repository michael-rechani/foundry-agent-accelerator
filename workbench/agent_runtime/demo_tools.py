import json
import re
from copy import deepcopy


TEMPLATE_IDS = frozenset({
    "document-analyst", "criteria-checker", "document-intake", "casework-assistant", "workflow-coordinator",
    "medical-bill-reviewer", "insurance-preapproval-helper", "benefits-renewal-helper", "supplier-invoice-reviewer",
    "public-records-intake", "grant-reporting-checker", "community-program-brief", "customer-support-brief",
    "cash-application-reviewer", "maintenance-work-order-planner", "contract-playbook-checker", "rfp-answer-drafter",
    "expense-report-checker", "incident-timeline-writer", "customer-feedback-themes", "order-delay-helper",
})
_EXAMPLE = "Example only; not a real record"

_REQUESTS = {
    "REQ-101": {
        "request_id": "REQ-101", "service_id": "SVC-DEMO-ACCESS",
        "summary": "The analytics team wants read-only access to a reporting workspace.",
        "supplied_information": ["Purpose: review monthly counts."],
        "missing_information": ["Requested access duration", "Named team owner"],
        "status": "Example only; no real request exists",
    },
    "REQ-102": {
        "request_id": "REQ-102", "service_id": "SVC-DEMO-EXPORT",
        "summary": "The operations team wants to plan a data export.",
        "supplied_information": ["Format: CSV.", "Contents: equipment inventory."],
        "missing_information": ["Required fields"],
        "status": "Example only; no real request exists",
    },
}
_SERVICES = {
    "SVC-DEMO-ACCESS": {
        "service_id": "SVC-DEMO-ACCESS", "name": "Reporting access",
        "suggested_review_steps": ["Clarify the duration and team owner.", "Have a person review the request."],
        "actions_available": "None. This fixture does not provision accounts or enforce approval.",
        "status": "Example only; no real service exists",
    },
    "SVC-DEMO-EXPORT": {
        "service_id": "SVC-DEMO-EXPORT", "name": "Data export planning",
        "suggested_review_steps": ["Clarify the fields.", "Have a person review the intended use."],
        "actions_available": "None. This fixture cannot export data or contact a system.",
        "status": "Example only; no real service exists",
    },
}
_PLANS = {
    "PLAN-DEMO-SILVER": {
        "plan_id": "PLAN-DEMO-SILVER", "plan_name": "Silver Demo Plan", "plan_year": 2027,
        "in_network_providers": ["Lakeside Demo Hospital", "Riverbend Demo Clinic", "Lakeside Demo Imaging Center"],
        "deductible_remaining": "$0.00 (met earlier in 2027)",
        "patient_share_after_deductible": "20% of the allowed amount for in-network care",
        "in_network_billing_rule": (
            "In-network providers have agreed to accept the allowed amount. Members owe only the 'your share' "
            "amount on the insurer statement."
        ),
        "duplicate_rule": "The same service on the same date is paid once unless the provider explains why it was repeated.",
        "dispute_steps": [
            "Ask the hospital billing office for a corrected itemized bill.",
            "Call member services at the number on the member card.",
            "Send a written dispute within 180 days of the insurer statement date.",
        ],
        "status": "Example only; not a real health plan",
    },
}
_USUAL_PRICES = {
    code: {"service_code": code, "plan_id": "PLAN-DEMO-SILVER", "description": description,
           "usual_allowed_amount": amount, "billing_unit": unit, "status": _EXAMPLE}
    for code, description, amount, unit in (
        ("DEMO-ER-3", "Emergency room visit, level 3", "$600.00", "One per visit"),
        ("DEMO-XR-2", "Chest X-ray, two views", "$150.00", "One per imaging session; a repeat needs a documented reason"),
        ("DEMO-LAB-7", "Basic blood panel", "$40.00", "One per blood draw"),
        ("DEMO-SUP-1", "Wrist splint", "$80.00", "One per item supplied"),
    )
}
_PREAPPROVAL_RULES = {
    "PLAN-DEMO-SILVER/DEMO-MRI-LS": {
        "plan_id": "PLAN-DEMO-SILVER", "service_code": "DEMO-MRI-LS", "service": "MRI of the lower back",
        "required_documents": [
            {"id": "RULE-1", "item": "Order signed and dated by the treating clinician"},
            {"id": "RULE-2", "item": "Visit notes dated within 60 days before the request date"},
            {"id": "RULE-3", "item": "Record of treatments already tried for this problem, with dates"},
            {"id": "RULE-4", "item": "Member ID that matches the plan"},
            {"id": "RULE-5", "item": "Facility in the plan's network, or an out-of-network exception form"},
        ],
        "note": "Paperwork list only. The insurer's own reviewers decide medical need.",
        "status": "Example only; not a real insurer rule",
    },
}
_FACILITIES = {
    "FAC-DEMO-22": {
        "facility_id": "FAC-DEMO-22", "name": "Northside Demo Imaging",
        "network_status": {"PLAN-DEMO-SILVER": "Out of network"},
        "in_network_alternative": "FAC-DEMO-31 Lakeside Demo Imaging Center",
        "status": _EXAMPLE,
    },
    "FAC-DEMO-31": {
        "facility_id": "FAC-DEMO-31", "name": "Lakeside Demo Imaging Center",
        "network_status": {"PLAN-DEMO-SILVER": "In network"},
        "status": _EXAMPLE,
    },
}
_RENEWAL_RULES = {
    "PROG-DEMO-FOOD": {
        "program_id": "PROG-DEMO-FOOD", "program_name": "Family Food Help",
        "required_proofs": [
            {"id": "PROOF-1", "proof": "Identity of the head of household", "rule": "Not needed again if still valid on file"},
            {"id": "PROOF-2", "proof": "Income", "rule": "Every pay stub dated in the 30 days before the form was signed"},
            {"id": "PROOF-3", "proof": "Housing cost", "rule": "Lease or landlord letter dated within 12 months before the form was signed"},
            {"id": "PROOF-4", "proof": "Household members",
             "rule": "Household size must match across the form and documents, or the difference must be explained"},
            {"id": "PROOF-5", "proof": "Child care cost",
             "rule": "Only if child care is listed: a provider letter or receipts dated in the last 30 days"},
        ],
        "note": "Checklist only. The caseworker decides eligibility and benefit amounts.",
        "status": "Example only; not a real program rule",
    },
}
_ON_FILE = {
    "HH-DEMO-5150": {
        "household_id": "HH-DEMO-5150", "last_renewal": "2026-04-01",
        "on_file": [
            {"proof": "Identity of the head of household", "document": "Photo ID checked 2026-03-18", "still_valid": True},
        ],
        "previous_household_size": "3 at the 2026 renewal",
        "status": "Example only; no real case record",
    },
}
_PURCHASE_ORDERS = {
    "PO-DEMO-2210": {
        "po_number": "PO-DEMO-2210", "supplier": "Example Furniture Supply",
        "buyer": "Example Conference Center", "ordered_on": "2027-03-01",
        "lines": [
            {"item": "CH-100 Stacking chair", "quantity": 100, "agreed_unit_price": "$50.00"},
            {"item": "TB-300 Folding table", "quantity": 10, "agreed_unit_price": "$300.00"},
        ],
        "terms": "Delivery included at no charge for orders over $2,000. Prices fixed until 2027-12-31.",
        "po_total": "$8,000.00",
        "status": "Example only; not a real purchase order",
    },
}
_DELIVERIES = {
    "PO-DEMO-2210": {
        "po_number": "PO-DEMO-2210", "delivered_on": "2027-03-28", "received_by": "Receiving dock",
        "lines": [
            {"item": "CH-100 Stacking chair", "quantity_received": 100,
             "note": "2 chairs arrived with cracked seats; photos on file"},
            {"item": "TB-300 Folding table", "quantity_received": 10, "note": "No issues noted"},
        ],
        "status": "Example only; not a real delivery record",
    },
}
_EXPENSE_POLICIES = {
    "POL-DEMO-TRAVEL": {
        "policy_id": "POL-DEMO-TRAVEL", "policy_name": "Travel and Expense Rules",
        "rules": [
            {"id": "RULE-1", "rule": "Hotel: up to $220.00 per night"},
            {"id": "RULE-2", "rule": "Meals: up to $75.00 per person per day, excluding non-reimbursable items"},
            {"id": "RULE-3", "rule": "Receipts: required for any line over $25.00"},
            {"id": "RULE-4", "rule": "Not reimbursable: alcohol and personal entertainment"},
            {"id": "RULE-5", "rule": "Dates: expenses must fall within the approved trip dates, including travel days"},
        ],
        "note": "Checklist only. A finance approver decides reimbursement and any exception.",
        "status": "Example only; not a real expense policy",
    },
}
_TRIPS = {
    "TRIP-DEMO-4410": {
        "trip_id": "TRIP-DEMO-4410", "traveler": "Jordan Lee",
        "purpose": "Customer workshop in Example City", "approved_dates": "2027-05-10 to 2027-05-12",
        "approved_budget": {"hotel": "$440.00 for 2 nights", "meals": "$225.00 for 3 days", "local_transport": "$60.00"},
        "approved_by": "Finance lead",
        "status": "Example only; not a real trip request",
    },
}
_ORDERS = {
    "ORD-DEMO-3307": {
        "order_id": "ORD-DEMO-3307", "customer": "A. Chen", "placed_on": "2027-06-01",
        "promised_delivery": "2027-06-06", "shipping": "Standard",
        "lines": [
            {"item": "DL-20 Desk lamp", "quantity": 1, "price": "$45.00"},
            {"item": "MS-5 Monitor stand", "quantity": 1, "price": "$80.00"},
        ],
        "order_total": "$125.00",
        "note": "Refunds, credits, cancellations and reshipments are decided by customer service staff.",
        "status": "Example only; not a real order",
    },
}
_SHIPMENTS = {
    "ORD-DEMO-3307": {
        "order_id": "ORD-DEMO-3307",
        "shipments": [
            {"shipment_id": "SHP-DEMO-881", "carrier": "Example Parcel", "items": ["DL-20 Desk lamp"],
             "events": ["2027-06-02 Label created", "2027-06-03 Picked up",
                        "2027-06-05 Delayed: weather at regional hub"],
             "carrier_estimate": "2027-06-09"},
        ],
        "not_shipped": [{"item": "MS-5 Monitor stand", "state": "Backordered; restock date not confirmed"}],
        "status": "Example only; not a real tracking record",
    },
}


def _lookup(records, identifier):
    key = identifier.strip().upper() if isinstance(identifier, str) else None
    if key not in records:
        raise ValueError("Unknown fictional demo identifier; use an identifier from the supplied example")
    return deepcopy(records[key])


def create_demo_tools(template_id, agent_name):
    if template_id not in TEMPLATE_IDS:
        raise ValueError("Unsupported demo template")
    if not isinstance(agent_name, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", agent_name):
        raise ValueError("Invalid hosted agent name")

    def receipt(record):
        return json.dumps({
            "status": "succeeded", "agent": agent_name, "simulation": True,
            "output": "SIMULATED read-only fixture lookup. No external system was contacted or changed.\n"
                      + json.dumps(record, sort_keys=True),
        })

    def lookup_demo_request(request_id: str) -> str:
        """Read a fixed fictional request by ID. SIMULATED, read-only; never opens or updates a ticket."""
        return receipt(_lookup(_REQUESTS, request_id))

    def lookup_demo_service(service_id: str) -> str:
        """Read a fixed fictional service by ID. SIMULATED, read-only; no connected systems or approval actions."""
        return receipt(_lookup(_SERVICES, service_id))

    def lookup_plan_benefits(plan_id: str) -> str:
        """Read a fixed fictional health plan's benefits and billing rules by plan ID. SIMULATED, read-only; never contacts an insurer."""
        return receipt(_lookup(_PLANS, plan_id))

    def lookup_usual_price(service_code: str) -> str:
        """Read the fictional plan's usual allowed price for one service code. SIMULATED, read-only; not a real price list."""
        return receipt(_lookup(_USUAL_PRICES, service_code))

    def lookup_preapproval_rules(plan_id: str, service_code: str) -> str:
        """Read a fixed fictional insurer's pre-approval document list for a plan ID and service code. SIMULATED, read-only; never submits a request."""
        if not isinstance(plan_id, str) or not isinstance(service_code, str):
            raise ValueError("Unknown fictional demo identifier; use an identifier from the supplied example")
        return receipt(_lookup(_PREAPPROVAL_RULES, plan_id.strip() + "/" + service_code.strip()))

    def lookup_facility(facility_id: str) -> str:
        """Read a fixed fictional facility's network status by facility ID. SIMULATED, read-only; no external directory."""
        return receipt(_lookup(_FACILITIES, facility_id))

    def lookup_renewal_rules(program_id: str) -> str:
        """Read a fixed fictional benefits program's renewal proof rules by program ID. SIMULATED, read-only; never decides eligibility."""
        return receipt(_lookup(_RENEWAL_RULES, program_id))

    def lookup_documents_on_file(household_id: str) -> str:
        """Read which fictional proofs a household already has on file by household ID. SIMULATED, read-only; never changes a record."""
        return receipt(_lookup(_ON_FILE, household_id))

    def lookup_purchase_order(po_number: str) -> str:
        """Read a fixed fictional purchase order by PO number. SIMULATED, read-only; never changes an order."""
        return receipt(_lookup(_PURCHASE_ORDERS, po_number))

    def lookup_delivery_record(po_number: str) -> str:
        """Read what the fictional buyer recorded as delivered for a PO number. SIMULATED, read-only; never changes a record."""
        return receipt(_lookup(_DELIVERIES, po_number))

    def lookup_expense_policy(policy_id: str) -> str:
        """Read fixed fictional travel and expense rules by policy ID. SIMULATED, read-only; never approves a claim."""
        return receipt(_lookup(_EXPENSE_POLICIES, policy_id))

    def lookup_trip_request(trip_id: str) -> str:
        """Read a fixed fictional approved trip request by trip ID. SIMULATED, read-only; never changes a record."""
        return receipt(_lookup(_TRIPS, trip_id))

    def lookup_order(order_id: str) -> str:
        """Read a fixed fictional customer order by order ID. SIMULATED, read-only; never refunds or changes an order."""
        return receipt(_lookup(_ORDERS, order_id))

    def lookup_shipment(order_id: str) -> str:
        """Read fixed fictional shipment tracking for an order ID. SIMULATED, read-only; never contacts a carrier."""
        return receipt(_lookup(_SHIPMENTS, order_id))

    return {
        "workflow-coordinator": [lookup_demo_request, lookup_demo_service],
        "medical-bill-reviewer": [lookup_plan_benefits, lookup_usual_price],
        "insurance-preapproval-helper": [lookup_preapproval_rules, lookup_facility],
        "benefits-renewal-helper": [lookup_renewal_rules, lookup_documents_on_file],
        "supplier-invoice-reviewer": [lookup_purchase_order, lookup_delivery_record],
        "expense-report-checker": [lookup_expense_policy, lookup_trip_request],
        "order-delay-helper": [lookup_order, lookup_shipment],
    }.get(template_id, [])
