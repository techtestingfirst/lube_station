import frappe
from frappe.model.document import Document


class ServerGroup(Document):
    @frappe.whitelist()
    def pick_server(self) -> str | None:
        servers = [r.server for r in self.servers if r.server]
        if not servers:
            return None
        if self.fill_strategy == "Least Full":
            rows = frappe.get_all("Server", filters={"name": ["in", servers]}, fields=["name", "max_accounts", "active_accounts"])
            rows.sort(key=lambda r: (r.active_accounts or 0) / max(r.max_accounts or 1, 1))
            return rows[0].name if rows else servers[0]
        if self.fill_strategy == "Manual":
            return servers[0]
        idx = (frappe.cache().get_value(f"sg-rr:{self.name}") or 0) % len(servers)
        frappe.cache().set_value(f"sg-rr:{self.name}", idx + 1)
        return servers[idx]
