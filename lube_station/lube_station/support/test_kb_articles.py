import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.support import articles


def _make_category(name: str) -> str:
    return frappe.get_doc({"doctype": "HD Article Category", "category_name": name}).insert().name


def _make_article(title: str, category: str, status: str = "Published") -> str:
    return frappe.get_doc(
        {"doctype": "HD Article", "title": title, "category": category, "status": status, "content": f"<p>{title} body</p>"}
    ).insert(ignore_permissions=True).name


class TestKbArticles(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if not frappe.db.exists("DocType", "HD Article"):
            self.skipTest("HD Article (helpdesk app) not installed")

    def test_published_only(self):
        cat = _make_category("Billing")
        _make_article("How to pay", cat, "Published")
        _make_article("Draft secret", cat, "Draft")
        _make_article("Old news", cat, "Archived")
        rows = articles.my_kb_articles()
        titles = [r["title"] for r in rows if r["category"] == cat]
        self.assertIn("How to pay", titles)
        self.assertNotIn("Draft secret", titles)
        self.assertNotIn("Old news", titles)

    def test_category_filter_and_counts(self):
        cat_a = _make_category("Cat A")
        cat_b = _make_category("Cat B")
        _make_article("A1", cat_a)
        _make_article("A2", cat_a)
        _make_article("B1", cat_b)
        cats = {c["name"]: c["article_count"] for c in articles.my_kb_categories()}
        self.assertGreaterEqual(cats.get(cat_a, 0), 2)
        self.assertGreaterEqual(cats.get(cat_b, 0), 1)
        only_a = articles.my_kb_articles(category=cat_a)
        self.assertTrue(only_a)
        self.assertTrue(all(r["category"] == cat_a for r in only_a))
        self.assertRaises(frappe.DoesNotExistError, articles.my_kb_articles, category="NOPE")

    def test_search(self):
        cat = _make_category("Search Cat")
        _make_article("Reset your password steps", cat)
        rows = articles.my_kb_articles(q="password")
        self.assertTrue(any(r["title"] == "Reset your password steps" for r in rows))
        rows_none = articles.my_kb_articles(q="zzz-no-such-title")
        self.assertFalse(any(r["title"] == "Reset your password steps" for r in rows_none))
