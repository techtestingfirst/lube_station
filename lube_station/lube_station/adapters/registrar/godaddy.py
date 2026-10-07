"""Live GoDaddy adapter (Domains v1 REST, sso-key auth).

OTE sandbox by default (live_mode on the account row opts into production).
Endpoint shapes come from GoDaddy's published OpenAPI (domains-v1.json):
availability, purchase with agreement consent, transfer, renew, contacts,
nameservers, privacy flag, and full-set DNS replace. Nothing is contacted
without account creds (manual gate).
"""

import time

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://api.godaddy.com"
TEST_URL = "https://api.ote-godaddy.com"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class GodaddyAdapter(RegistrarAdapter):
    adapter_name = "GoDaddy"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value(
            "Registrar Account", {"registrar": "GoDaddy", "active": 1}, "name"
        )
        if not name:
            frappe.throw("No active GoDaddy Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        key = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not key:
            key = (doc.get("api_key") or "").strip()
        secret = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not key or not secret:
            frappe.throw("GoDaddy account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return key, secret, url

    # -- transport ------------------------------------------------------
    def _headers(self):
        key, secret, _ = self._account()
        return {"Authorization": f"sso-key {key}:{secret}", "Content-Type": "application/json"}

    def _call(self, method, path, payload=None, transport=None):
        import json

        key, secret, base = self._account()
        transport = transport or _http
        headers = {"Authorization": f"sso-key {key}:{secret}", "Content-Type": "application/json"}
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(method, f"{base}{path}", headers, json.dumps(payload or {}), TIMEOUT)
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"GoDaddy {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        if getattr(resp, "status_code", 200) == 204 or not (resp.text if hasattr(resp, "text") else ""):
            return {}
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"GoDaddy {method} {path} returned non-JSON response")
        if isinstance(out, dict) and out.get("code"):
            frappe.throw(f"GoDaddy {path} rejected: {out.get('message', out.get('code'))}", frappe.ValidationError)
        return out if isinstance(out, (dict, list)) else {}

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        import urllib.parse

        out = self._call(
            "GET", f"/v1/domains/available?{urllib.parse.urlencode({'domain': domain, 'checkType': 'FULL'})}", transport=transport
        )
        status = "available" if out.get("available") else "taken"
        price = out.get("price") or 0
        result = normalize_availability(domain, status)
        result["premium_price"] = price / 1_000_000 if isinstance(price, (int, float)) else 0
        return result

    def _consent(self, transport, tlds, privacy=False, for_transfer=False):
        import urllib.parse

        from frappe.utils import now_datetime

        keys = []
        try:
            out = self._call(
                "GET",
                "/v1/domains/agreements?" + urllib.parse.urlencode({"tlds": tlds, "privacy": str(bool(privacy)).lower(), "forTransfer": str(bool(for_transfer)).lower()}),
                transport=transport,
            )
            keys = out if isinstance(out, list) else []
        except Exception:
            keys = []
        return {"agreedAt": now_datetime().isoformat(), "agreedBy": "reseller", "agreementKeys": keys}

    def _tld(self, domain):
        return domain.rsplit(".", 1)[-1] if "." in domain else domain

    def register_domain(self, domain, contacts, nameservers, transport=None):
        payload = {
            "domain": domain,
            "consent": self._consent(transport, self._tld(domain)),
            "period": 1,
            "privacy": False,
            "renewAuto": True,
        }
        mapped = self._contacts(contacts or {})
        if mapped:
            payload.update(mapped)
        if nameservers:
            payload["nameServers"] = list(nameservers)
        self._call("POST", "/v1/domains/purchase", payload, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        payload = {
            "authCode": auth_code,
            "consent": self._consent(transport, self._tld(domain), for_transfer=True),
            "period": 1,
            "privacy": False,
            "renewAuto": True,
        }
        self._call("POST", f"/v1/domains/{domain}/transfer", payload, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        self._call("POST", f"/v1/domains/{domain}/renew", {"period": years or 1}, transport)
        return {"renewed": domain}

    def get_domain_info(self, domain, transport=None):
        out = self._call("GET", f"/v1/domains/{domain}", transport=transport)
        return {"domain": domain, "info": out}

    def update_nameservers(self, domain, nameservers, transport=None):
        self._call("PATCH", f"/v1/domains/{domain}", {"nameServers": list(nameservers or [])}, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        mapped = self._contacts(contacts or {})
        if not mapped:
            frappe.throw("No contact fields to update", frappe.ValidationError)
        self._call("PATCH", f"/v1/domains/{domain}/contacts", mapped, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        # exposeWhois=false hides details (privacy on). Confirm on sandbox.
        self._call("PATCH", f"/v1/domains/{domain}", {"exposeWhois": not bool(enabled)}, transport)
        return {"domain": domain, "privacy": bool(enabled)}

    # -- dns ops (PUT replaces all: read-modify-write) --------------------
    def _records(self, domain, transport):
        out = self._call("GET", f"/v1/domains/{domain}/records", transport=transport)
        return out if isinstance(out, list) else []

    def create_dns_record(self, domain, record, transport=None):
        records = self._records(domain, transport)
        records.append(self._to_record(record))
        self._call("PUT", f"/v1/domains/{domain}/records", records, transport)
        return {"created": True, "domain": domain}

    def update_dns_record(self, domain, record, transport=None):
        record = dict(record or {})
        needle = str(record.get("name") or record.get("host") or record.get("hostname") or "")
        rtype = str(record.get("type") or record.get("RecordType") or "")
        records = [
            r for r in self._records(domain, transport)
            if not (str(r.get("name", "")) == needle and (not rtype or str(r.get("type", "")) == rtype))
        ]
        records.append(self._to_record(record))
        self._call("PUT", f"/v1/domains/{domain}/records", records, transport)
        return {"updated": True, "domain": domain}

    def delete_dns_record(self, domain, record_id, transport=None):
        records = self._records(domain, transport)
        kept = [r for r in records if str(r.get("name", "")) != str(record_id)]
        self._call("PUT", f"/v1/domains/{domain}/records", kept, transport)
        return {"deleted": True, "domain": domain}

    # -- helpers ----------------------------------------------------------
    def _to_record(self, record):
        record = record or {}
        return {
            "type": str(record.get("type") or record.get("RecordType") or "A"),
            "name": str(record.get("host") or record.get("hostname") or record.get("name") or "@"),
            "data": str(record.get("value") or record.get("data") or ""),
            "ttl": int(record.get("ttl") or record.get("TTL") or 3600),
        }

    def _contacts(self, contacts):
        kinds = {"owner": "contactRegistrant", "admin": "contactAdmin", "billing": "contactBilling", "tech": "contactTech"}
        out = {}
        for key, role in kinds.items():
            src = contacts.get(key) or {}
            if not isinstance(src, dict) or not src:
                continue
            contact = {
                "nameFirst": src.get("FirstName", ""),
                "nameLast": src.get("LastName", ""),
                "email": src.get("EmailAddress", ""),
                "phone": src.get("Phone", ""),
                "organization": src.get("OrganizationName", ""),
                "addressMailing": {
                    "address1": src.get("Address1", ""),
                    "city": src.get("City", ""),
                    "state": src.get("StateProvince", ""),
                    "postalCode": src.get("PostalCode", ""),
                    "country": src.get("Country", ""),
                },
            }
            if any([contact["nameFirst"], contact["email"]]):
                out[role] = contact
        return out
