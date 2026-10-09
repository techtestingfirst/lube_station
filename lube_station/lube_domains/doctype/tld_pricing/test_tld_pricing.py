import uuid
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_domains.doctype.tld_pricing.tld_pricing import domain_price, tld_of


def _ensure_tld(tld: str, register: float, renew: float, transfer: float):
    tld = tld.strip().lower()
    if not tld.startswith("."):
        tld = f".{tld}"
    if frappe.db.exists("TLD Pricing", tld):
        doc = frappe.get_doc("TLD Pricing", tld)
    else:
        doc = frappe.get_doc({"doctype": "TLD Pricing", "tld": tld})
    doc.register_price = register
    doc.renew_price = renew
    doc.transfer_price = transfer
    doc.save(ignore_permissions=True)
    return doc


class TestTLDPricing(IntegrationTestCase):
    def test_tld_matching(self):
        _ensure_tld(".in", 8, 9, 8)
        _ensure_tld(".co.in", 6, 7, 6)
        _ensure_tld(".com", 12, 13, 11)
        # Longest suffix wins over .in.
        self.assertEqual(tld_of("shop.co.in"), ".co.in")
        self.assertEqual(tld_of("shop.in"), ".in")
        self.assertEqual(tld_of("SHOP.COM"), ".com")
        self.assertIsNone(tld_of(f"shop-{uuid.uuid4().hex[:6]}.xyz"))

    def test_tld_normalized(self):
        doc = _ensure_tld("COM", 12, 13, 11)
        self.assertEqual(doc.tld, ".com")
        self.assertRaises(frappe.ValidationError, frappe.get_doc({"doctype": "TLD Pricing", "tld": "not a tld"}).insert)

    def test_domain_price_actions(self):
        _ensure_tld(".com", 12, 13, 11)
        _ensure_tld(".io", 35, 39, 35)
        self.assertEqual(domain_price("example.com", "register"), 12)
        self.assertEqual(domain_price("example.com", "renew"), 13)
        self.assertEqual(domain_price("example.com", "transfer"), 11)
        self.assertEqual(domain_price("example.io", "register"), 35)
        # Blank transfer falls back to register rate.
        _ensure_tld(".net", 10, 11, 0)
        self.assertEqual(domain_price("example.net", "transfer"), 10)
        # Unknown TLD falls back to the flat setting rate.
        from lube_station.lube_station.settings import get_setting

        self.assertEqual(domain_price(f"example-{uuid.uuid4().hex[:6]}.xyz", "register"), get_setting("domain_year_price"))

    def test_cart_domain_tld_price(self):
        import json

        _ensure_tld(".com", 12, 13, 11)
        cart = frappe.get_doc({"doctype": "Cart", "session_id": f"tld-{uuid.uuid4().hex[:8]}"}).insert()
        cart.append(
            "items",
            {
                "item_type": "Domain",
                "domain": f"buy-{uuid.uuid4().hex[:6]}.com",
                "billing_cycle": "One Time",
                "quantity": 2,
                "configuration_json": json.dumps({"domain_action": "register", "domain_years": 2}),
            },
        )
        cart.save()
        self.assertEqual(cart.items[0].unit_price, 12)
        self.assertEqual(cart.subtotal, 24)

    def test_renew_uses_renew_price(self):
        from lube_station.lube_station.adapters.seed import seed
        from lube_station.lube_domains.doctype.domain.domain import renew_domain

        seed()
        _ensure_tld(".com", 12, 13, 11)
        email = f"tld-{uuid.uuid4().hex[:8]}@test.com"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Tld", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        name = f"renew-{uuid.uuid4().hex[:6]}.com"
        frappe.get_doc({"doctype": "Domain", "domain_name": name, "customer": cust.name, "status": "Registered"}).insert(ignore_permissions=True)
        mock = MagicMock()
        mock.renew_domain.return_value = {"renewed": name}
        with patch("lube_station.lube_station.adapters.registry.get_registrar_adapter", return_value=mock):
            renew_domain(name, years=2)
        inv = frappe.get_doc("Hosting Invoice", {"customer": cust.name})
        self.assertEqual(sum(i.amount for i in inv.invoice_items), 26)


def _premium_availability(premium_price: float = 999):
    mock = MagicMock()
    mock.return_value = {"domain": "vip.test", "status": "Premium", "premium_price": premium_price}
    return patch("lube_station.lube_domains.doctype.domain.domain.check_availability", mock)


def _portal_customer():
    from lube_station.lube_station.portal import apis

    email = f"premium-{uuid.uuid4().hex[:8]}@test.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Premium", "enabled": 1}).insert(ignore_permissions=True)
    cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
    frappe.set_user(user.name)
    return apis, cust


class TestPremiumDomain(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_premium_bills_registrar_price(self):
        import json

        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        with _premium_availability(999):
            view = apis.cart_add_domain(cart.name, "vip.test", "register", years=1)
        line = [i for i in view["items"] if i["domain"] == "vip.test"][0]
        self.assertEqual(line["unit_price"], 999)
        self.assertEqual(json.loads(line["configuration_json"])["premium_price"], 999)
        self.assertEqual(view["grand_total"], 999)

    def test_premium_multiyear_rejected(self):
        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        with _premium_availability(999):
            self.assertRaises(frappe.ValidationError, apis.cart_add_domain, cart.name, "vip.test", "register", 2)

    def test_premium_no_price_rejected(self):
        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        with _premium_availability(0):
            self.assertRaises(frappe.ValidationError, apis.cart_add_domain, cart.name, "vip.test", "register", 1)

    def test_premium_blocked_on_hosting_row(self):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Premium Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Premium Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 10}).insert()
        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save(ignore_permissions=True)
        row = frappe.get_doc("Cart", cart.name).items[0].name
        with _premium_availability(999):
            self.assertRaises(frappe.ValidationError, apis.cart_set_domain, cart.name, row, "vip.test", "register", 1)
