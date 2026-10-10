import frappe


def sync_record(record: str) -> dict:
    rec = frappe.get_doc("DNS Record", record)
    dom = frappe.get_doc("Registered Domain", rec.domain)
    if not dom.registrar:
        return {"synced": False, "reason": "no registrar"}
    from lube_station.lube_station.adapters.registry import get_registrar_adapter

    try:
        adapter = get_registrar_adapter(dom.registrar)
        return adapter.create_dns_record(dom.domain_name, {"type": rec.record_type, "host": rec.hostname, "value": rec.record_value, "ttl": rec.ttl})
    except Exception as e:
        return {"synced": False, "reason": str(e)}
