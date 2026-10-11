"""Customer Knowledge Base proxy (launcher pattern, same as support tickets).

Lists published Helpdesk articles inside the Lube portal; reading happens in
the Helpdesk portal (/helpdesk/kb-public). Published-only filter is hardcoded:
get_all ignores permissions, so Draft/Archived must never leak.
Reference: helpdesk/api/knowledge_base.py get_categories/get_category_articles.
"""

import frappe


@frappe.whitelist(methods=["GET"])
def my_kb_categories() -> list:
    """Categories holding at least one published article, most articles first."""
    cats = frappe.db.get_all(
        "HD Article Category",
        fields=["name", "category_name", "description", "modified"],
    )
    out = []
    for c in cats:
        count = frappe.db.count("HD Article", {"category": c["name"], "status": "Published"})
        if count:
            out.append({**c, "article_count": count})
    out.sort(key=lambda d: d["article_count"], reverse=True)
    return out


@frappe.whitelist(methods=["GET"])
def my_kb_articles(category: str | None = None, q: str | None = None, limit: int = 50) -> list:
    """Published articles, optionally filtered by category and/or title search."""
    filters: dict = {"status": "Published"}
    if category:
        if not frappe.db.exists("HD Article Category", category):
            frappe.throw("Unknown category", frappe.DoesNotExistError)
        filters["category"] = category
    if q and q.strip():
        filters["title"] = ["like", f"%{q.strip()}%"]
    return frappe.db.get_all(
        "HD Article",
        filters,
        ["name", "title", "category", "published_on", "modified"],
        order_by="modified desc",
        limit=max(1, min(int(limit or 50), 100)),
    )
