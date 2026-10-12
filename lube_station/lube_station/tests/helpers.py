"""Shared hermetic fixtures for integration tests.

Every helper mints unique names so tests stay green on dev sites that
already hold committed demo data (e.g. an Administrator-linked customer).
Test-runner rollback cleans up; uniqueness prevents cross-run collisions.
"""

import uuid

import frappe


def make_user(prefix: str = "t") -> str:
    """Create a unique enabled User. Returns email."""
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    frappe.get_doc({"doctype": "User", "email": email, "first_name": "Test", "enabled": 1}).insert(
        ignore_permissions=True
    )
    return email


def make_customer(prefix: str = "t", **kwargs) -> str:
    """Create a unique User + Hosting Customer. Returns customer name."""
    doc = {"doctype": "Hosting Customer", "user": make_user(prefix), "status": "Active", "kyc_status": "Verified"}
    doc.update(kwargs)
    return frappe.get_doc(doc).insert().name
