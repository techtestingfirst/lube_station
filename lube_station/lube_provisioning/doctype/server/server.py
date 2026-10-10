import time

import frappe
from frappe.model.document import Document


PANEL_TO_ADAPTER_PATH = {
    "cPanel / WHM": "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter",
    "Plesk": "lube_station.lube_station.adapters.provisioning.plesk.PleskAdapter",
    "DirectAdmin": "lube_station.lube_station.adapters.provisioning.directadmin.DirectAdminAdapter",
}


def _load_adapter(control_panel: str):
    import importlib

    path = PANEL_TO_ADAPTER_PATH.get((control_panel or "").strip())
    if not path:
        frappe.throw(f"No live adapter for control panel '{control_panel}'. Choose cPanel / WHM, Plesk or DirectAdmin.")
    mod_name, cls_name = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod_name), cls_name)()


class Server(Document):
    @frappe.whitelist()
    def test_connection(self):
        """Test live panel API and store result on the Server record.

        Called from Desk via the "Test Connection" button. Updates
        connection_status / last_checked_on / response_time_ms /
        last_check_message so the form always shows whether the
        server is reachable. Never raises: failure is stored and returned.
        """
        started = time.monotonic()
        try:
            adapter = _load_adapter(self.control_panel)
            adapter.test_connection(self.name)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self.connection_status = "Online"
            self.last_check_message = f"Connected OK in {elapsed_ms} ms via {self.control_panel}."
            self.response_time_ms = elapsed_ms
        except Exception as e:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self.connection_status = "Failed"
            self.last_check_message = str(e)[:500]
            self.response_time_ms = elapsed_ms
        self.last_checked_on = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)
        return {
            "ok": self.connection_status == "Online",
            "status": self.connection_status,
            "message": self.last_check_message,
            "response_time_ms": self.response_time_ms,
            "checked_on": str(self.last_checked_on),
        }


def get_indicator(doc):
    if doc.get("connection_status") == "Online":
        return ("Online", "green", "connection_status,=,Online")
    if doc.get("connection_status") == "Failed":
        return ("Offline", "red", "connection_status,=,Failed")
    return ("Not Checked", "gray", "connection_status,=,Not Checked")
