import frappe
from frappe.model.document import Document


class ProvisioningModule(Document):
    def create_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_create", service=service)

    def suspend_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_suspend", service=service)

    def unsuspend_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_unsuspend", service=service)

    def terminate_account(self, service: str):
        frappe.enqueue("lube_station.lube_station.provisioning.jobs.run_terminate", service=service)
