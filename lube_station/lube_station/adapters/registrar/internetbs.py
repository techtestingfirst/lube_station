"""Live Internet.bs adapter (reseller commands over HTTPS, key auth).

Test host by default. Command shapes mirror the internet.bs reseller API
plus the InternetBS-API-PHP-Class client (Domain/Check/Create/Update/Renew/
Transfer/Initiate/Info, PrivateWhois toggles, NS via Ns_list). Contact field
names follow the per-role convention and must be confirmed on sandbox.
Nothing fires without account creds (manual gate).
"""

import time

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://api.internet.bs"
TEST_URL = "https://testapi.internet.bs"
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class InternetBsAdapter(RegistrarAdapter):
    adapter_name = "Internet.bs"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "Internet.bs", "active": 1}, "name")
        if not name:
            frappe.throw("No active Internet.bs Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        key = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not key:
            key = (doc.get("api_key") or "").strip()
        password = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not key or not password:
            frappe.throw("Internet.bs account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return key, password, url

    # -- transport ------------------------------------------------------
    def _call(self, command, params, transport=None):
        import urllib.parse

        key, password, base = self._account()
        transport = transport or _http_post
        query = {"ApiKey": key, "Password": password, "ResponseFormat": "JSON"}
        query.update(params or {})
        safe = {k: ("***" if k == "Password" else v) for k, v in query.items()}
        body = urllib.parse.urlencode(query)
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(f"{base}/{command}", {"Content-Type": "application/x-www-form-urlencoded"}, body, TIMEOUT)
                return self._result(command, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Internet.bs {command} failed after {RETRIES} attempts: {last_error}")

    def _result(self, command, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Internet.bs {command} returned non-JSON response")
        if str(out.get("status", "")).upper() != "SUCCESS":
            frappe.throw(
                f"Internet.bs {command} rejected: {out.get('message', out)}", frappe.ValidationError
            )
        return out

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        out = self._call("Domain/Check", {"Domain": domain}, transport)
        status = str(out.get("status", "")).upper()
        # Domain/Check answers per-domain availability; treat explicit
        # availability markers as available, anything else as taken.
        avail = str(out.get("availability", out.get("result", ""))).lower()
        if avail in ("available", "yes", "true", "1"):
            return normalize_availability(domain, "available")
        if status == "SUCCESS":
            return normalize_availability(domain, "unknown")
        return normalize_availability(domain, "taken")

    def register_domain(self, domain, contacts, nameservers, transport=None):
        params = {"Domain": domain, "Period": "1Y"}
        params.update(self._contact_params(contacts or {}))
        if nameservers:
            params["Ns_list"] = ",".join(nameservers)
        self._call("Domain/Create", params, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        self._call("Domain/Transfer/Initiate", {"Domain": domain, "transferAuthInfo": auth_code}, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        info = self.get_domain_info(domain, transport)
        exp = (info.get("info") or {}).get("expiration") or ""
        params = {"Domain": domain, "Period": f"{years or 1}Y"}
        if exp:
            params["CurrentExpirationDate"] = exp
        self._call("Domain/Renew", params, transport)
        return {"renewed": domain}

    def get_domain_info(self, domain, transport=None):
        out = self._call("Domain/Info", {"Domain": domain}, transport)
        return {"domain": domain, "info": out}

    def update_nameservers(self, domain, nameservers, transport=None):
        self._call("Domain/Update", {"Domain": domain, "Ns_list": ",".join(nameservers or [])}, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        params = {"Domain": domain}
        params.update(self._contact_params(contacts or {}))
        self._call("Domain/Update", params, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        action = "Enable" if enabled else "Disable"
        self._call(f"Domain/PrivateWhois/{action}", {"Domain": domain}, transport)
        return {"domain": domain, "privacy": bool(enabled)}

    # -- dns ops ------------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        frappe.throw("Internet.bs DNS records are not mapped yet; use nameservers instead")

    def update_dns_record(self, domain, record, transport=None):
        frappe.throw("Internet.bs DNS records are not mapped yet; use nameservers instead")

    def delete_dns_record(self, domain, record_id, transport=None):
        frappe.throw("Internet.bs DNS records are not mapped yet; use nameservers instead")

    # -- helpers ----------------------------------------------------------
    def _contact_params(self, contacts):
        kinds = {"owner": "Registrant", "admin": "Admin", "tech": "Tech", "billing": "Billing"}
        fields = ("FirstName", "LastName", "Organization", "Address", "City", "State",
                  "PostalCode", "Country", "Email", "Phone")
        out = {}
        for key, prefix in kinds.items():
            src = (contacts or {}).get(key) or {}
            if not isinstance(src, dict):
                continue
            for field in fields:
                if src.get(field):
                    out[f"{prefix}{field}"] = src[field]
        return out
