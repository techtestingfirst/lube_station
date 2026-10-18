# Copyright (c) 2026, Praveen Kumar and Contributors
# See license.txt

import uuid

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


def _uid():
	return uuid.uuid4().hex[:6]


def _make_provider(name=None):
	return frappe.get_doc(
		{
			"doctype": "Infrastructure Provider",
			"provider_name": name or f"Markup Provider {_uid()}",
			"provider_type": "VPS API",
			"status": "Active",
		}
	).insert(ignore_permissions=True)


def _make_agreement(provider, billing_model="Wholesale Recurring", markup_type="Percentage",
					markup_value=20, active=1, name=None):
	return frappe.get_doc(
		{
			"doctype": "Reseller Agreement",
			"provider": provider.name,
			"agreement_name": name or f"Markup Agreement {_uid()}",
			"billing_model": billing_model,
			"markup_type": markup_type,
			"markup_value": markup_value,
			"active": active,
		}
	).insert(ignore_permissions=True)


def _make_group(name=None):
	return frappe.get_doc(
		{"doctype": "Product Group", "group_name": name or f"Markup Group {_uid()}"}
	).insert(ignore_permissions=True)


def _make_plan(group, agreement_name, plan_name=None):
	return frappe.get_doc(
		{
			"doctype": "Hosting Plan",
			"plan_name": plan_name or f"Markup Plan {_uid()}",
			"product_type": "VPS",
			"product_group": group.name,
			"reseller_agreement": agreement_name,
		}
	).insert(ignore_permissions=True)


def _make_pricing(plan, wholesale_cost=100, cycle="Monthly"):
	return frappe.get_doc(
		{
			"doctype": "Plan Pricing",
			"hosting_plan": plan.name,
			"billing_cycle": cycle,
			"wholesale_cost": wholesale_cost,
		}
	).insert(ignore_permissions=True)


class IntegrationTestPlanPricing(IntegrationTestCase):
	"""
	Integration tests for PlanPricing.
	Use this class for testing interactions between multiple components.
	"""

	def test_percentage_markup_auto_computes_recurring_amount(self):
		provider = _make_provider()
		agreement = _make_agreement(provider, markup_type="Percentage", markup_value=20)
		group = _make_group()
		plan = _make_plan(group, agreement.name)
		pricing = _make_pricing(plan, wholesale_cost=100)

		# 100 cost + 20% markup = 120
		self.assertEqual(pricing.recurring_amount, 120)

	def test_fixed_markup_auto_computes_recurring_amount(self):
		provider = _make_provider()
		agreement = _make_agreement(provider, markup_type="Fixed", markup_value=20)
		group = _make_group(name="Fixed Group")
		plan = _make_plan(group, agreement.name, plan_name="Fixed Plan")
		pricing = _make_pricing(plan, wholesale_cost=100)

		# 100 cost + 20 fixed = 120
		self.assertEqual(pricing.recurring_amount, 120)

	def test_per_usage_billing_skips_markup(self):
		provider = _make_provider()
		agreement = _make_agreement(provider, billing_model="Per Usage", markup_type="Percentage", markup_value=20)
		group = _make_group(name="Per Usage Group")
		plan = _make_plan(group, agreement.name, plan_name="Per Usage Plan")
		pricing = _make_pricing(plan, wholesale_cost=100)

		# Per Usage is metered; recurring_amount stays as wholesale cost (manual)
		self.assertEqual(pricing.recurring_amount, 100)

	def test_inactive_agreement_skips_markup(self):
		provider = _make_provider()
		agreement = _make_agreement(provider, active=0)
		group = _make_group(name="Inactive Group")
		plan = _make_plan(group, agreement.name, plan_name="Inactive Plan")
		pricing = _make_pricing(plan, wholesale_cost=100)

		# Inactive agreement: no markup applied
		self.assertEqual(pricing.recurring_amount, 100)

	def test_no_wholesale_cost_keeps_manual_price(self):
		provider = _make_provider()
		agreement = _make_agreement(provider, markup_type="Percentage", markup_value=20)
		group = _make_group(name="No Cost Group")
		plan = _make_plan(group, agreement.name, plan_name="No Cost Plan")
		pricing = frappe.get_doc(
			{
				"doctype": "Plan Pricing",
				"hosting_plan": plan.name,
				"billing_cycle": "Monthly",
				"recurring_amount": 999,
				"wholesale_cost": 0,
			}
		).insert(ignore_permissions=True)

		# wholesale_cost 0: markup skipped, manual recurring_amount preserved
		self.assertEqual(pricing.recurring_amount, 999)

	def test_no_agreement_linked_keeps_manual_price(self):
		provider = _make_provider()
		agreement = _make_agreement(provider, markup_type="Percentage", markup_value=20)
		group = _make_group(name="No Link Group")
		plan = _make_plan(group, None, plan_name="No Link Plan")

		# Clear the agreement link
		plan.reseller_agreement = None
		plan.save(ignore_permissions=True)

		pricing = _make_pricing(plan, wholesale_cost=100)
		# No agreement linked: no markup applied
		self.assertEqual(pricing.recurring_amount, 100)
