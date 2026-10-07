import frappe
from frappe.model.document import Document

PANEL_BY_VENDOR = {"cPanel": "cPanel / WHM", "Plesk": "Plesk", "DirectAdmin": "DirectAdmin"}


class ProvisioningModule(Document):
    def validate(self):
        if self.provisioning_adapter:
            adapter = frappe.get_doc("Provisioning Adapter", self.provisioning_adapter)
            if not self.class_path:
                self.class_path = adapter.class_path
            if not self.control_panel and adapter.vendor_name in PANEL_BY_VENDOR:
                self.control_panel = PANEL_BY_VENDOR[adapter.vendor_name]

    def create_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_create", service=service)

    def suspend_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_suspend", service=service)

    def unsuspend_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_unsuspend", service=service)

    def terminate_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_terminate", service=service)
