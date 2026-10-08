import frappe
from frappe.tests import IntegrationTestCase


class TestAdapterAutofill(IntegrationTestCase):
    def test_payment_autofill(self):
        doc = frappe.get_doc("Payment Gateway Adapter", "Mollie")
        doc.class_path = ""
        doc.save(ignore_permissions=True)
        self.assertEqual(
            doc.class_path,
            "lube_station.lube_station.adapters.payments.stubs.MollieAdapter",
        )

    def test_payment_bad_path_rejected_when_active(self):
        doc = frappe.get_doc("Payment Gateway Adapter", "Mollie")
        doc.class_path = "nope.Bad"
        doc.active = 1
        self.assertRaises(frappe.ValidationError, doc.save)

    def test_payment_unknown_vendor_path_required_when_active(self):
        doc = frappe.get_doc(
            {
                "doctype": "Payment Gateway Adapter",
                "adapter_name": "Autofill Draft",
                "vendor_name": "Custom",
                "active": 1,
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_payment_unknown_vendor_draft_allowed(self):
        doc = frappe.get_doc(
            {
                "doctype": "Payment Gateway Adapter",
                "adapter_name": "Autofill Draft",
                "vendor_name": "Custom",
                "active": 0,
            }
        )
        doc.insert(ignore_permissions=True)
        self.assertFalse(doc.class_path)

    def test_provisioning_autofill(self):
        doc = frappe.get_doc("Provisioning Adapter", "AWS EC2")
        original = doc.class_path
        doc.class_path = ""
        try:
            doc.save(ignore_permissions=True)
            self.assertEqual(
                doc.class_path,
                "lube_station.lube_station.adapters.provisioning.stubs.AwsEc2Adapter",
            )
        finally:
            doc.class_path = original
            doc.save(ignore_permissions=True)

    def test_provisioning_lifecycle_from_code(self):
        live = frappe.get_doc("Provisioning Adapter", "cPanel / WHM")
        live.save(ignore_permissions=True)
        for method in (
            "create_account",
            "suspend_account",
            "unsuspend_account",
            "terminate_account",
            "change_password",
            "change_package",
            "get_usage",
            "test_connection",
        ):
            self.assertIn(method, live.lifecycle_methods or "")
        stub = frappe.get_doc("Provisioning Adapter", "AWS EC2")
        original_stub = stub.class_path
        stub.class_path = "lube_station.lube_station.adapters.provisioning.stubs.AwsEc2Adapter"
        try:
            stub.save(ignore_permissions=True)
            self.assertFalse(stub.lifecycle_methods)
        finally:
            stub.class_path = original_stub
            stub.save(ignore_permissions=True)

    def test_provisioning_api_mode_select(self):
        field = frappe.get_meta("Provisioning Adapter").get_field("api_mode")
        self.assertEqual(field.fieldtype, "Select")
        self.assertIn("WHM API", field.options or "")
        self.assertEqual(
            frappe.db.get_value("Provisioning Adapter", "cPanel / WHM", "api_mode"),
            "WHM API",
        )

    def test_registrar_autofill(self):
        doc = frappe.get_doc("Registrar Adapter", "Nominet")
        original = doc.class_path
        doc.class_path = ""
        try:
            doc.save(ignore_permissions=True)
            self.assertEqual(
                doc.class_path,
                "lube_station.lube_station.adapters.registrar.nominet.NominetAdapter",
            )
        finally:
            doc.class_path = original
            doc.save(ignore_permissions=True)

    def test_registrar_operations_from_code(self):
        live = frappe.get_doc("Registrar Adapter", "OpenSRS")
        live.save(ignore_permissions=True)
        for operation in (
            "check_availability",
            "register_domain",
            "transfer_domain",
            "renew_domain",
            "get_domain_info",
            "update_nameservers",
            "toggle_privacy",
        ):
            self.assertIn(operation, live.supported_operations or "")
        stub = frappe.get_doc("Registrar Adapter", "HEXONET")
        original_stub = stub.class_path
        stub.class_path = "lube_station.lube_station.adapters.registrar.stubs.HexonetAdapter"
        try:
            stub.save(ignore_permissions=True)
            self.assertFalse(stub.supported_operations)
        finally:
            stub.class_path = original_stub
            stub.save(ignore_permissions=True)

    def test_module_fills_from_adapter(self):
        module = frappe.get_doc(
            {
                "doctype": "Provisioning Module",
                "module_name": "Autofill Module",
                "provisioning_adapter": "cPanel / WHM",
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(module.control_panel, "cPanel / WHM")
        self.assertEqual(
            module.class_path,
            "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter",
        )

    def test_module_keeps_manual_values(self):
        module = frappe.get_doc(
            {
                "doctype": "Provisioning Module",
                "module_name": "Manual Module",
                "provisioning_adapter": "cPanel / WHM",
                "control_panel": "DirectAdmin",
                "class_path": "custom.path.Adapter",
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(module.control_panel, "DirectAdmin")
        self.assertEqual(module.class_path, "custom.path.Adapter")

    def test_module_saves_without_path(self):
        module = frappe.get_doc(
            {"doctype": "Provisioning Module", "module_name": "Bare Module"}
        ).insert(ignore_permissions=True)
        self.assertFalse(module.class_path)

    def test_module_control_panel_is_select(self):
        field = frappe.get_meta("Provisioning Module").get_field("control_panel")
        self.assertEqual(field.fieldtype, "Select")
        for panel in ("cPanel / WHM", "Plesk", "DirectAdmin"):
            self.assertIn(panel, field.options or "")
