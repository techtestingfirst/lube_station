PRODUCT_SLA_HOURS = {"Dedicated Server": 2, "VPS": 4, "Shared Hosting": 8, "Reseller": 8, "Cloud": 4}

PRODUCT_PRIORITY = {"Dedicated Server": "Urgent", "VPS": "High", "Shared Hosting": "Medium"}


def sla_hours(product_type: str | None) -> int:
    return PRODUCT_SLA_HOURS.get(product_type or "", 24)


def priority_for(product_type: str | None) -> str:
    return PRODUCT_PRIORITY.get(product_type or "", "Low")
