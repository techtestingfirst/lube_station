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
