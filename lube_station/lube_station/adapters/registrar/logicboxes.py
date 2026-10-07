"""Live LogicBoxes/ResellerClub adapter (httpapi.com JSON API, reseller auth).

Sandbox by default (test.httpapi.com). Credentials from the Registrar Account
row (api_key = reseller ID, api_secret Password = API key). Endpoint shapes
mirror the httpapi.com API plus the netinternet/logicboxes-api client
(order-id resolution, register/transfer/renew/modify-ns shapes).

Contacts: LogicBoxes wants numeric contact IDs. Pass explicit IDs in
``contacts`` (customer_id, reg_contact_id, ...); otherwise a reseller
customer is auto-created from our customer record and its id is used as
customer-id, but contact IDs must still be supplied. DNS record ops are
explicitly unmapped (point nameservers at a DNS host instead).
"""

import time
import urllib.parse

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://httpapi.com/api"
TEST_URL = "https://test.httpapi.com/api"
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class LogicBoxesAdapter(RegistrarAdapter):
    adapter_name = "ResellerClub / LogicBoxes"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value(
            "Registrar Account", {"registrar": "ResellerClub / LogicBoxes", "active": 1}, "name"
        )
        if not name:
            frappe.throw("No active LogicBoxes Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        userid = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not userid:
            userid = (doc.get("api_key") or "").strip()
        key = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not userid or not key:
            frappe.throw("LogicBoxes account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return userid, key, url

    # -- transport ------------------------------------------------------
    def _call(self, path, params, transport=None):
        userid, key, base = self._account()
        transport = transport or _http_post
        query = {"auth-userid": userid, "api-key": key}
        query.update(params or {})
        safe = {k: ("***" if k == "api-key" else v) for k, v in query.items()}
        body = urllib.parse.urlencode(query, doseq=True)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(f"{base}/{path}", headers, body, TIMEOUT)
                return self._result(path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"LogicBoxes {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"LogicBoxes {path} returned non-JSON response")
        if str(out.get("status", "")).lower() not in ("success", "ok", "available"):
            if isinstance(out.get("status"), str) and out.get("status").lower() == "error":
                frappe.throw(
                    f"LogicBoxes {path} rejected: {out.get('message', out.get('error', 'unknown'))}",
                    frappe.ValidationError,
                )
        return out

    # -- helpers ----------------------------------------------------------
    def _order_id(self, domain, transport):
        out = self._call("domains/orderid.json", {"domain-name": domain}, transport)
        order_id = out.get("response") or out.get("orderid") or out.get("order-id")
        if not order_id:
            frappe.throw(f"LogicBoxes has no order for {domain}", frappe.ValidationError)
        return order_id

    def _customer_id(self, customer, contacts, transport):
        explicit = (contacts or {}).get("customer_id")
        if explicit:
            return explicit, dict(contacts)
        if not customer:
            frappe.throw("LogicBoxes needs customer_id in contacts", frappe.ValidationError)
        cust = frappe.get_doc("Hosting Customer", customer)
        user_email = frappe.db.get_value("User", cust.user, "email") or cust.user
        import secrets

        out = self._call(
            "customers/signup.json",
            {
                "username": user_email,
                "passwd": secrets.token_urlsafe(16),
                "name": frappe.db.get_value("User", cust.user, "full_name") or user_email,
                "company": "",
                "address-line-1": "-",
                "city": "-",
                "state": "-",
                "zip": "000000",
                "country": "IN",
                "phone-cc": "91",
                "phone": "0000000000",
                "lang-pref": "en",
            },
            transport,
        )
        customer_id = out.get("response") or out.get("customerid") or out.get("customer-id")
        if not customer_id:
            frappe.throw("LogicBoxes customer signup failed", frappe.ValidationError)
        return customer_id, dict(contacts)

    def _contact_ids(self, contacts):
        ids = {}
        for key in ("reg_contact_id", "admin_contact_id", "tech_contact_id", "billing_contact_id"):
            if (contacts or {}).get(key):
                ids[key.replace("_", "-")] = contacts[key]
        missing = [k for k in ("reg-contact-id", "admin-contact-id", "tech-contact-id", "billing-contact-id") if k not in ids]
        if missing:
            frappe.throw(
                f"LogicBoxes needs contact IDs ({', '.join(missing)}); create them in the reseller panel",
                frappe.ValidationError,
            )
        return ids

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        tld = domain.rsplit(".", 1)[-1] if "." in domain else domain
        out = self._call(
            "domains/available.json",
            {"domain-name": domain, "tlds": tld, "suggest-alternative": "false"},
            transport,
        )
        entry = out.get(domain) or {}
        status = str(entry.get("status", "")).lower()
        if status == "available":
            premium = self._premium(domain, transport)
            result = normalize_availability(domain, "premium" if premium[0] else "available")
            result["premium_price"] = premium[1]
            return result
        if status in ("regthroughothers", "regthroughus", "taken", "unavailable"):
            return normalize_availability(domain, "taken")
        return normalize_availability(domain, "unknown")

    def _premium(self, domain, transport):
        try:
            out = self._call("domains/premium-check.json", {"domain-name": domain}, transport)
            price = float(out.get("price") or 0)
            return price > 0, price
        except Exception:
            return False, 0

    def register_domain(self, domain, contacts, nameservers, transport=None, customer=None):
        customer_id, contacts = self._customer_id(customer, contacts, transport)
        ids = self._contact_ids(contacts)
        params = {
            "domain-name": domain,
            "years": 1,
            "ns": list(nameservers or []),
            "customer-id": customer_id,
            "invoice-option": "NoInvoice",
            "protect-privacy": False,
            **ids,
        }
        self._call("domains/register.json", params, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None, contacts=None, customer=None):
        customer_id, contacts = self._customer_id(customer, contacts or {}, transport)
        ids = self._contact_ids(contacts)
        params = {
            "domain-name": domain,
            "auth-code": auth_code,
            "years": 1,
            "ns": [],
            "customer-id": customer_id,
            "invoice-option": "NoInvoice",
            **ids,
        }
        self._call("domains/transfer.json", params, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        order_id = self._order_id(domain, transport)
        details = self._call("domains/details-by-name.json", {"domain-name": domain, "options": "OrderDetails"}, transport)
        exp = self._exp(details)
        self._call(
            "domains/renew.json",
            {"order-id": order_id, "years": years or 1, "exp-date": exp, "invoice-option": "NoInvoice"},
            transport,
        )
        return {"renewed": domain}

    def _exp(self, details):
        import datetime

        blob = details if isinstance(details, dict) else {}
        for key in ("endtime", "end_time", "expiry", "expirydate", "exp-date"):
            val = blob.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return int(val)
            if isinstance(val, str) and val[:4].isdigit():
                try:
                    return int(datetime.datetime.fromisoformat(val).timestamp())
                except Exception:
                    continue
        frappe.throw("LogicBoxes renewal needs the current expiry date", frappe.ValidationError)

    def get_domain_info(self, domain, transport=None):
        out = self._call("domains/details-by-name.json", {"domain-name": domain, "options": "All"}, transport)
        return {"domain": domain, "info": out}

    def update_nameservers(self, domain, nameservers, transport=None):
        order_id = self._order_id(domain, transport)
        self._call("domains/modify-ns.json", {"order-id": order_id, "ns": list(nameservers or [])}, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        order_id = self._order_id(domain, transport)
        ids = self._contact_ids(contacts or {})
        params = {"order-id": order_id, **ids}
        self._call("domains/modify-contact.json", params, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        order_id = self._order_id(domain, transport)
        self._call(
            "domains/modify-privacy-protection.json",
            {"order-id": order_id, "protect-privacy": bool(enabled)},
            transport,
        )
        return {"domain": domain, "privacy": bool(enabled)}

    # -- dns ops ------------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        frappe.throw("LogicBoxes DNS records are not mapped yet; point nameservers at a DNS host")

    def update_dns_record(self, domain, record, transport=None):
        frappe.throw("LogicBoxes DNS records are not mapped yet; point nameservers at a DNS host")

    def delete_dns_record(self, domain, record_id, transport=None):
        frappe.throw("LogicBoxes DNS records are not mapped yet; point nameservers at a DNS host")
