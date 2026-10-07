import json

import frappe
from frappe.model.document import Document


def _as_strings(value) -> list:
    """Best-effort region names from free-form regions JSON."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, dict):
        return [str(k).strip() for k in value if str(k).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def derive_capabilities(provider_name: str) -> dict | None:
    """Summary of the provider's own Provider Product records.

    Returns None when nothing structured exists, so free text is kept.
    """
    products = frappe.get_all(
        "Provider Product",
        filters={"provider": provider_name},
        fields=["product_type", "regions_json", "available_quantity"],
    )
    if not products:
        return None
    regions = set()
    for p in products:
        if not p.regions_json:
            continue
        try:
            regions.update(_as_strings(json.loads(p.regions_json)))
        except (ValueError, TypeError):
            continue
    summary = {
        "products": len(products),
        "product_types": sorted({p.product_type for p in products if p.product_type}),
        "total_available": sum(p.available_quantity or 0 for p in products),
    }
    if regions:
        summary["regions"] = sorted(regions)
    return summary


class InfrastructureProvider(Document):
    def validate(self):
        if self.capabilities and str(self.capabilities).strip():
            try:
                json.loads(self.capabilities)
            except (ValueError, TypeError):
                frappe.throw("Capabilities must be valid JSON")
            return
        derived = derive_capabilities(self.name) if self.name else None
        if derived:
            self.capabilities = json.dumps(derived, indent=2)
