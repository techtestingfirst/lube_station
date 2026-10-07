"""Live Porkbun adapter (JSON v3, key auth in body or headers).

Sandbox is key-driven (pk1_sb_ key, same base URL) — no host switch. Shapes
from Porkbun's published docs: checkDomain, create/renew/transfer with
dryRun quotes, updateNs, get, DNS CRUD by name/type. Money ops self-quote
via dryRun so the exact-pennies cost never mismatches. Nothing fires without
account creds (manual gate).
"""

import time

import frappe

from .base import RegistrarAdapter, normalize_availability

BASE = "https://api.porkbun.com/api/json/v3"
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class PorkbunAdapter(RegistrarAdapter):
    adapter_name = "Porkbun"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "Porkbun", "active": 1}, "name")
        if not name:
            frappe.throw("No active Porkbun Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        key = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not key:
            key = (doc.get("api_key") or "").strip()
        secret = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not key or not secret:
            frappe.throw("Porkbun account is missing API credentials")
        return key, secret

    # -- transport ------------------------------------------------------
    def _call(self, path, payload=None, transport=None):
        import json

        key, secret = self._account()
        transport = transport or _http_post
        body = {"apikey": key, "secretapikey": secret}
        body.update(payload or {})
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(f"{BASE}{path}", {"Content-Type": "application/json"}, json.dumps(body), TIMEOUT)
                return self._result(path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Porkbun {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Porkbun {path} returned non-JSON response")
        if not isinstance(out, dict) or str(out.get("status", "")).upper() != "SUCCESS":
            detail = out.get("message", out) if isinstance(out, dict) else out
            frappe.throw(f"Porkbun {path} rejected: {detail}", frappe.ValidationError)
        return out

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        out = self._call(f"/domain/checkDomain/{domain}", {}, transport)
        response = out.get("response") or {}
        avail = str(response.get("available", "")).lower()
        premium = bool(response.get("premium", False))
        if avail == "available":
            status = "premium" if premium else "available"
        elif avail in ("unavailable", "taken"):
            status = "taken"
        else:
            status = "unknown"
        result = normalize_availability(domain, status)
        result["premium_price"] = response.get("price", 0) if premium else 0
        return result

    def _quote(self, op, domain, transport):
        out = self._call(f"/domain/{op}/{domain}", {"cost": 0, "dryRun": True}, transport)
        if not out.get("wouldSucceed", True):
            frappe.throw(f"Porkbun {op} would fail for {domain}: {out.get('message')}", frappe.ValidationError)
        return int(out.get("cost", 0))

    def register_domain(self, domain, contacts, nameservers, transport=None):
        cost = self._quote("create", domain, transport)
        out = self._call(f"/domain/create/{domain}",
            {"cost": cost, "agreeToTerms": "yes", "whoisPrivacy": True},
            transport,
        )
        return {"registered": domain, "order_id": out.get("orderId"), "cost": cost}

    def transfer_domain(self, domain, auth_code, transport=None):
        cost = self._quote("transfer", domain, transport)
        out = self._call(f"/domain/transfer/{domain}", {"authCode": auth_code, "cost": cost}, transport
        )
        return {"transferred": domain, "order_id": out.get("orderId"), "cost": cost}

    def renew_domain(self, domain, years=1, transport=None):
        cost = self._quote("renew", domain, transport)
        out = self._call(f"/domain/renew/{domain}", {"cost": cost}, transport)
        return {"renewed": domain, "expiration": out.get("expirationDate"), "cost": cost}

    def get_domain_info(self, domain, transport=None):
        out = self._call(f"/domain/get/{domain}", {}, transport)
        return {"domain": domain, "info": out.get("domain", {})}

    def update_nameservers(self, domain, nameservers, transport=None):
        self._call(f"/domain/updateNs/{domain}", {"ns": list(nameservers or [])}, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        frappe.throw("Porkbun contact update is not mapped yet")

    def toggle_privacy(self, domain, enabled, transport=None):
        frappe.throw("Porkbun privacy toggle is not mapped yet")

    # -- dns ops ------------------------------------------------------------
    def _subdomain(self, domain, record):
        host = str((record or {}).get("host") or (record or {}).get("hostname") or (record or {}).get("name") or "")
        if not host or host == "@" or host == domain:
            return ""
        suffix = f".{domain}"
        return host[: -len(suffix)] if host.endswith(suffix) else host

    def create_dns_record(self, domain, record, transport=None):
        record = record or {}
        out = self._call(f"/dns/create/{domain}",
            {
                "name": self._subdomain(domain, record),
                "type": record.get("type") or "A",
                "content": record.get("value") or record.get("content") or "",
                "ttl": int(record.get("ttl") or 600),
                **({"prio": int(record.get("prio"))} if record.get("prio") else {}),
            },
            transport,
        )
        return {"created": True, "domain": domain, "id": out.get("id")}

    def update_dns_record(self, domain, record, transport=None):
        record = record or {}
        if record.get("id"):
            out = self._call(f"/dns/edit/{domain}/{record['id']}",
                {
                    "content": record.get("value") or record.get("content") or "",
                    "ttl": int(record.get("ttl") or 600),
                },
                transport,
            )
            return {"updated": True, "domain": domain, "id": record["id"]}
        out = self._call(f"/dns/editByNameType/{domain}/{record.get('type') or 'A'}/{self._subdomain(domain, record)}",
            {"content": record.get("value") or record.get("content") or ""},
            transport,
        )
        return {"updated": True, "domain": domain}

    def delete_dns_record(self, domain, record_id, transport=None):
        self._call(f"/dns/delete/{domain}/{record_id}", {}, transport)
        return {"deleted": True, "domain": domain}
