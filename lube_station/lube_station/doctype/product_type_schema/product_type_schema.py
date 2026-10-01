import json

import frappe
from frappe.model.document import Document


class ProductTypeSchema(Document):
    def validate(self):
        keys = [f.field_key for f in self.fields]
        if len(keys) != len(set(keys)):
            frappe.throw("Duplicate field_key in schema")


def _schema_doc(name: str):
    doc = frappe.get_doc("Product Type Schema", name)
    return doc


def validate_config(schema_name: str, config: dict):
    doc = _schema_doc(schema_name)
    for f in doc.fields:
        if f.required and (f.field_key not in config or config[f.field_key] in (None, "")):
            frappe.throw(f"Missing required field: {f.field_key}")
    return True


@frappe.whitelist(methods=["GET", "POST"])
def get_product_requirements(plan: str | None = None, schema: str | None = None, product_type: str | None = None):
    """Return requirement fields for checkout renderer.

    Prefers explicit schema, else resolves via Hosting Plan -> product_type_schema,
    else via product_type lookup. Validates nothing, only returns definition.
    """
    schema_name = schema
    if not schema_name and plan and frappe.db.exists("Hosting Plan", plan):
        schema_name = frappe.db.get_value("Hosting Plan", plan, "product_type_schema")
    if not schema_name and product_type:
        schema_name = frappe.db.get_value("Product Type Schema", {"product_type": product_type}, "name")
    if not schema_name:
        frappe.throw("Provide schema, plan with linked schema, or product_type")
    doc = _schema_doc(schema_name)
    return {
        "schema": doc.name,
        "product_type": doc.product_type,
        "flags": {
            "requires_domain": doc.requires_domain,
            "requires_hostname": doc.requires_hostname,
            "requires_root_password": doc.requires_root_password,
            "requires_os": doc.requires_os,
            "requires_location": doc.requires_location,
            "requires_nameservers": doc.requires_nameservers,
        },
        "fields": [
            {
                "field_key": f.field_key,
                "label": f.label,
                "field_type": f.field_type,
                "options_source": f.options_source,
                "options_json": json.loads(f.options_json) if f.options_json else None,
                "required": f.required,
                "validation_rule": f.validation_rule,
                "maps_to": f.maps_to,
            }
            for f in doc.fields
        ],
    }
