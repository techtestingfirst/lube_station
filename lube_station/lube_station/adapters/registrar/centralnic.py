"""Live CentralNic Reseller adapter (REST v1 JSON, Basic auth).

OTE sandbox by default (live host when the account row opts into live_mode).
Shapes follow the official REST guide + OpenAPI: availability, contact
create, domain register, NS replace, info, renew (needs current expiry year),
transfer request. Contact update, privacy and DNS record ops are explicitly
unmapped (no callers; DNS sync degrades gracefully). Nothing fires without
account creds (manual gate).
"""

import time

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://rest.rrpproxy.net/v1"
TEST_URL = "https://rest-ote.rrpproxy.net/v1"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class CentralNicAdapter(RegistrarAdapter):
    adapter_name = "CentralNic Reseller"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value(
            "Registrar Account", {"registrar": "CentralNic Reseller", "active": 1}, "name"
        )
        if not name:
            frappe.throw("No active CentralNic Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        login = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not login:
            login = (doc.get("api_key") or "").strip()
        password = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not login or not password:
            frappe.throw("CentralNic account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return login, password, url

    # -- transport ------------------------------------------------------
    def _call(self, method, path, payload=None, transport=None):
        import base64
        import json

        login, password, base = self._account()
        transport = transport or _http
        creds = base64.b64encode(f"{login}:{password}".encode()).decode()
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    method,
                    f"{base}{path}",
                    {"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
                    json.dumps(payload or {}),
                    TIMEOUT,
                )
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"CentralNic {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"CentralNic {method} {path} returned non-JSON response")
        if not isinstance(out, dict) or int(out.get("code", 0)) != 200:
            desc = out.get("description", out) if isinstance(out, dict) else out
            frappe.throw(f"CentralNic {path} rejected: {desc}", frappe.ValidationError)
        return out.get("property") or {}

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        prop = self._call("GET", f"/domain/{domain}/availability", transport=transport)
        raw = prop.get("available", prop.get("status", ""))
        if isinstance(raw, bool):
            status = "available" if raw else "taken"
        else:
            status = str(raw).lower()
            status = "available" if status in ("available", "free", "1", "true", "yes") else ("taken" if status else "unknown")
        return normalize_availability(domain, status)

    def _contact_handle(self, detail, transport):
        if isinstance(detail, str) and detail:
            return detail
        detail = detail or {}
        payload = {
            "firstname": detail.get("FirstName", "-"),
            "lastname": detail.get("LastName", "-"),
            "street": [detail.get("Address1", "-")],
            "city": detail.get("City", "-"),
            "country": detail.get("Country", "DE"),
            "phone": detail.get("Phone", "+49.000000"),
            "email": detail.get("EmailAddress", "admin@example.invalid"),
        }
        if detail.get("OrganizationName"):
            payload["organization"] = detail["OrganizationName"]
        prop = self._call("POST", "/contact", payload, transport)
        handle = prop.get("handle") or prop.get("id") or prop.get("contact")
        if not handle:
            frappe.throw("CentralNic contact create returned no handle", frappe.ValidationError)
        return handle

    def _handles(self, contacts, transport):
        contacts = contacts or {}
        if contacts.get("ownercontact0"):
            return {
                "ownercontact0": contacts["ownercontact0"],
                "admincontact": contacts.get("admincontact", []),
                "techcontact": contacts.get("techcontact", []),
                "billingcontact": contacts.get("billingcontact", []),
            }
        owner = self._contact_handle((contacts or {}).get("owner"), transport)
        other = self._contact_handle((contacts or {}).get("admin") or (contacts or {}).get("owner"), transport)
        return {
            "ownercontact0": owner,
            "admincontact": [other],
            "techcontact": [other],
            "billingcontact": [other],
        }

    def register_domain(self, domain, contacts, nameservers, transport=None):
        payload = {
            "domain": domain,
            "period": 1,
            "nameserver": list(nameservers or []),
            **self._handles(contacts, transport),
        }
        self._call("POST", "/domain", payload, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        payload = {"action": "REQUEST", "auth": auth_code}
        self._call("POST", f"/domain/{domain}/transfer", payload, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        info = self.get_domain_info(domain, transport)
        year = self._expiry_year(info.get("raw") or {})
        self._call("PATCH", f"/domain/{domain}/renew", {"expiration": year, "period": years or 1}, transport)
        return {"renewed": domain}

    def _expiry_year(self, info):
        import datetime
        import re

        candidates = []
        def walk(node):
            if isinstance(node, dict):
                for key, val in node.items():
                    if "expir" in str(key).lower():
                        candidates.append(val)
                    walk(val)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(info)
        for val in candidates:
            match = re.search(r"(19|20)\d{2}", str(val))
            if match:
                return int(match.group(0))
        return datetime.datetime.now().year

    def get_domain_info(self, domain, transport=None):
        prop = self._call("GET", f"/domain/{domain}", transport=transport)
        return {"domain": domain, "info": prop, "raw": prop}

    def update_nameservers(self, domain, nameservers, transport=None):
        self._call("PATCH", f"/domain/{domain}", {"nameserver": list(nameservers or [])}, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        frappe.throw("CentralNic contact update is not mapped yet")

    def toggle_privacy(self, domain, enabled, transport=None):
        frappe.throw("CentralNic privacy toggle is not mapped yet")

    # -- dns ops ------------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        frappe.throw("CentralNic DNS records are not mapped yet; use nameservers instead")

    def update_dns_record(self, domain, record, transport=None):
        frappe.throw("CentralNic DNS records are not mapped yet; use nameservers instead")

    def delete_dns_record(self, domain, record_id, transport=None):
        frappe.throw("CentralNic DNS records are not mapped yet; use nameservers instead")
