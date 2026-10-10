# Lube Station Seller Setup Manual

Audience: seller or admin who sets up products for sale.
Goal: configure groups, servers, provisioning, plans, pricing, and add-ons.
Conventions used in this manual:

- Screen: Desk location and view to open.
- DocType: exact DocType name in `lube_station`.
- Fields: field labels as shown in Desk.

Desk base URL in development: `http://lubestation.localhost:8000`.
Desk route pattern: `/app/<doctype-slug>`.
Portal base URL in development: `http://localhost:8080`.

## 1. WHMCS to Lube Station concept map

| WHMCS concept | Lube Station equivalent | Notes |
|---|---|---|
| Product Group | Product Group | Same purpose. Lube Station has no per-group gateway list. |
| Product (Shared, Reseller, Server/VPS, Other) | Hosting Plan with Product Type | One DocType covers 11 types. See section 5. |
| Details tab, Require Domain | Product Type Schema | Flags plus custom fields. See section 6. |
| Pricing tab | Plan Pricing (child of Hosting Plan) | One record per billing cycle. See section 7. |
| Module (cPanel, Plesk, SolusVM) | Provisioning Module + Provisioning Adapter + Infrastructure Provider + Provider Product + Reseller Agreement | Lube Station splits one WHMCS module into five records. See section 2. |
| Server | Server | Same purpose. Credentials use Password fields. |
| Server group assignment | Server Group with fill strategy | Round Robin, Least Full, Manual. |
| Configurable Options | Plan Config Field (table on Hosting Plan) | Billed with main plan. No separate DocType. |
| Product Addons | Separate Hosting Plan (SSL, Backup Addon, Migration Service) | Independent billing cycle. |
| MarketConnect | Infrastructure Provider of type Reseller Program + Provider Product + Reseller Agreement | Manual setup. No built-in store. |
| Welcome Email | Hosting Plan field Welcome Email Template (link to Email Template) | Same purpose. |
| Automation (create, suspend, terminate) | Provisioning jobs + Service status + Dunning Rule | See sections 9 and 14. |

## 2. How Lube Station handles modules

WHMCS uses one module. The module holds code and server binding.

Lube Station uses five records. Each record has one job.

1. Provisioning Adapter: code registry. Fields: Adapter Name, Vendor Name, Class Path, Lifecycle Methods, Supports Usage, Supports Resize, Supports SSO, Supports Change Plan, Active.
2. Provisioning Module: seller-facing pointer. Fields: Module Name, Control Panel, Python Class Path.
3. Infrastructure Provider: upstream account. Fields: Provider Name, Provider Type, API Base URL, Credential Reference (Password), Capabilities (Code), Status.
4. Provider Product: upstream catalog entry. Fields: Provider (link), External Product ID, Product Type, Regions JSON, Plans JSON, Available Quantity, Sync Status.
5. Reseller Agreement: commercial terms. Fields: Provider (link), Agreement Name, Billing Model, Markup Type, Markup Value, Terms JSON, Active.

Screen: Desk > Lube Station > Provisioning Adapter List.
Screen: Desk > Lube Station > Provisioning Module List.
Screen: Desk > Lube Station > Infrastructure Provider List.

Use this rule:

- Sell from owned cPanel, Plesk, or DirectAdmin servers: set Provisioning Module and Server Group on the plan. Provider records stay empty or use Manual adapter for audit.
- Sell from VPS, cloud, or dedicated inventory: set Infrastructure Provider, Provider Product, and Reseller Agreement. Link the plan to the correct configuration DocType.
- Resell third-party SSL, SEO, or builder services: create a Provider of type Reseller Program, one Provider Product per upstream item, and one active Reseller Agreement.

## 3. Prerequisites

Complete this section before you create any plan.

### 3.1 Lube Station Settings

DocType: Lube Station Settings (Single).
Screen: Desk > Lube Station > Lube Station Settings.

1. Open Lube Station Settings.
2. Enter Company Name.
3. Enter Company Address.
4. Enter Support Email.
5. Set Enabled Gateways display order. Default value:
   `Stripe, Razorpay, Bank Transfer`.
6. Set Tax Mode to Exclusive or Inclusive.
7. Set Invoice Due Days. Default is 7.
8. Set Domain Year Price. Default is 15.
9. Accept Terms of Service requirement if needed.
10. Save.

### 3.2 Payment gateway

DocType: Payment Gateway Adapter (registry).
Screen: Desk > Lube Station > Payment Gateway Adapter List.

Class Path is the dotted Python path to the code that talks to the vendor, e.g. `lube_station.lube_station.adapters.payments.stripe.StripeAdapter`.

1. Open the Payment Gateway Adapter list.
2. Confirm the row for Stripe, Razorpay, PayPal, or Bank Transfer exists. Seeded rows already carry the correct Class Path.
3. Open the row.
4. Select Vendor Name. Pick the vendor or Custom.
5. Leave Class Path empty for known vendors. It fills on save. The field shows only when Vendor is Custom or the path is empty.
6. Check Active.
7. Check Supports One Time, Supports Recurring, Supports Tokenization, and Supports Refunds match the vendor.
8. Save. A wrong path on an active record is rejected with the path name.
9. Configure keys through the linked payment implementation. Do not store secret keys in Data fields.

For Vendor Custom, a developer must first add the adapter class. See section 17.1.

WHMCS difference: WHMCS enables gateways per product group. Lube Station enables adapters globally and controls tax and due dates in Lube Station Settings.

### 3.3 Tax Rule

DocType: Tax Rule.
Screen: Desk > Lube Station > Tax Rule > New.

1. Select New.
2. Enter Tax Name.
3. Select Country and State if the tax is regional.
4. Enter Percentage.
5. Select Level 1 or Level 2 for stacked taxes.
6. Add eligible client groups if the tax applies to a subset.
7. Check Active.
8. Save.

### 3.4 Dunning Rule

DocTypes: Dunning Rule, Dunning Step (child table).
Screen: Desk > Lube Station > Dunning Rule > New.

1. Select New.
2. Enter Rule Name.
3. Leave Hosting Plan empty for a global rule. Select a plan for a per-plan rule.
4. Select Product Type if the rule covers one type.
5. Enter Grace Days. Default is 7.
6. Enter Termination Days. Default is 30.
7. Add steps. Use Step Type Pre-due, Due, Overdue, Suspend, or Terminate Queue.
8. Enter Days Offset for each step.
9. Pick Template for each notify step from the seeded Lube Station templates (Due Soon, Due Today, Overdue, Suspended, Termination Notice).
10. Select Action Notify, Suspend, or Queue Termination.
11. Check Active.
12. Save.

Nine Lube Station email templates ship with the app: Due Soon, Due Today, Overdue, Suspended, Termination Notice, Payment Received, Service Restored, Service Welcome, Renewal Reminder. Edits you make to them are kept on update.

Create at least one active global rule before you sell.

### 3.5 Registrar account (only if you sell domains)

DocTypes: Registrar Adapter, Registrar Account.
Screen: Desk > Lube Station > Registrar Adapter List, then Registrar Account > New.

1. Open the Registrar Adapter for OpenSRS, Namecheap, GoDaddy, or LogicBoxes.
2. Check Active.
3. Open Registrar Account > New.
4. Select Registrar.
5. Enter API Key and API Secret. Both fields use Password type.
6. Check Active.
7. Save.

## 4. Product Group

DocType: Product Group.
Screen: Desk > Lube Station > Product Group > New.
Desk route: `/app/product-group`.

Fields:

- Group Name (required, unique). Example: Shared cPanel Hosting.
- Slug. Lowercase with hyphens. Example: `shared-cpanel-hosting`.
- Description (Text Editor). Shows on the portal.
- Icon (Attach Image).
- Sort Order (Int). Lower numbers show first.
- Show On Portal (Check).

Steps:

1. Open Product Group > New.
2. Enter Group Name.
3. Enter Slug.
4. Enter Description.
5. Upload Icon.
6. Enter Sort Order.
7. Check Show On Portal.
8. Save.

Create one group per storefront section. Examples: Shared Hosting, VPS Plans, Cloud Servers, Email, SSL and Add-ons, Downloadable Software.

## 5. Hosting Plan (the product)

DocType: Hosting Plan.
Screen: Desk > Lube Station > Hosting Plan > New.
Desk route: `/app/hosting-plan`.

Fields:

- Plan Name (required, unique).
- Product Group (Link to Product Group, required).
- Product Type (Select, required): Shared Hosting, Reseller, VPS, Dedicated Server, Cloud, Email Hosting, Website Builder, SSL, Backup Addon, Migration Service, Downloadable Product.
- Provisioning Module (Link to Provisioning Module).
- Server Group (Link to Server Group).
- Welcome Email Template (Link to Email Template).
- Product Type Schema (Link to Product Type Schema).
- Config Fields (Table to Plan Config Field with Field Key and Field Value).
- Is Active (Check).
- Apply Tax (Check).
- Stock Control (Check) and Qty Available (Int).

Steps for every plan:

1. Open Hosting Plan > New.
2. Enter Plan Name.
3. Select Product Group.
4. Select Product Type.
5. Select Provisioning Module if auto-provisioning applies.
6. Select Server Group if placement from owned servers applies.
7. Select Welcome Email Template.
8. Select Product Type Schema.
9. Add Config Fields rows for fixed package mapping.
10. Check Is Active.
11. Check Apply Tax if taxable.
12. Save.

WHMCS difference: WHMCS selects product type once and shows type-specific tabs. Lube Station keeps one form and drives checkout requirements from Product Type Schema plus type-specific configuration DocTypes in sections 8 to 18.

## 6. Product Type Schema (checkout requirements)

DocTypes: Product Type Schema, Product Requirement Field (child table).
Screen: Desk > Lube Station > Product Type Schema > New.
Desk route: `/app/product-type-schema`.

Fields on schema:

- Schema Name (required, unique).
- Product Type (Select, required, same 11 options).
- Requires Domain (Check).
- Requires Hostname (Check).
- Requires Root Password (Check).
- Requires OS (Check).
- Requires Location (Check).
- Requires Nameservers (Check).
- Fields (Table).

Fields on each requirement row:

- Field Key (required).
- Label (required).
- Field Type: Text, Password, Integer, Decimal, Select, Multi Select, Checkbox, JSON.
- Options Source: Static, OS Image Catalog, Location Catalog, Server Inventory, Provider API.
- Options JSON (Code).
- Required (Check).
- Validation Rule (Data).
- Maps To (Data).

Steps:

1. Open Product Type Schema > New.
2. Enter Schema Name. Example: `Shared Hosting Default`.
3. Select Product Type.
4. Check the flags the checkout must collect.
5. Add one row per extra field.
6. Save.
7. Open the Hosting Plan.
8. Select this schema in Product Type Schema.
9. Save the plan.

Resolution order used by `get_product_requirements`: explicit schema first, then plan link, then lookup by product type. The API rejects missing required input with `Missing required field: {key}`.

## 7. Plan Pricing

DocType: Plan Pricing.
Screen: Desk > Lube Station > Plan Pricing > New, or add from Hosting Plan.
Desk route: `/app/plan-pricing`.

Fields:

- Hosting Plan (Link, required).
- Billing Cycle (Select, required): Monthly, Quarterly, Semi-Annually, Annually, Biennially, Triennially, One Time.
- Setup Fee (Currency).
- Recurring Amount (Currency, required).
- Currency (Link to Currency).

Steps:

1. Open Plan Pricing > New.
2. Select Hosting Plan.
3. Select Billing Cycle.
4. Enter Recurring Amount.
5. Enter Setup Fee if any.
6. Select Currency.
7. Save.
8. Repeat for each cycle you sell. Example: Monthly and Annually.

WHMCS difference: WHMCS pricing lives on tabs inside the product. Lube Station stores one Plan Pricing record per cycle.

## 8. Shared Hosting (separate setup)

WHMCS path: New Product, type Shared Hosting, module cPanel, Require Domain checked.
Lube Station path: Hosting Plan with Product Type Shared Hosting.

DocTypes used: Product Group, Product Type Schema, Server, Server Group, Provisioning Module, Hosting Plan, Plan Pricing.

Screen sequence:

- Screen 1: Desk > Product Group. Confirm group `Shared Hosting`.
- Screen 2: Desk > Server List. Confirm at least one Active cPanel, Plesk, or DirectAdmin server.
- Screen 3: Desk > Server Group. Confirm group and fill strategy.
- Screen 4: Desk > Product Type Schema. Confirm Requires Domain checked.
- Screen 5: Desk > Hosting Plan > New. Create the plan.
- Screen 6: Desk > Plan Pricing. Add cycles.

Steps:

1. Create Product Group `Shared Hosting` per section 4.
2. Create Server records per section 9. Set Control Panel to `cPanel / WHM`, `Plesk`, or `DirectAdmin`.
3. Create Server Group per section 9. Add servers. Select Round Robin or Least Full.
4. Create schema `Shared Hosting Default`. Check Requires Domain. Clear Requires Root Password.
5. Create Hosting Plan. Set Product Type to Shared Hosting. Link Product Group, Provisioning Module, Server Group, Schema, and Welcome Email Template.
6. Add Config Fields rows for package mapping. Example: `package = shared_basic`, `disk_quota_mb = 10240`.
7. Create Plan Pricing rows. Use Recurring cycles. Example: Monthly 5.00, Annually 50.00.
8. Check Is Active.
9. Place a test order and confirm Service creation and welcome email.

## 9. Server and Server Group (owned infrastructure)

DocTypes: Server, Server Group, Server Group Entry (child).
Screens: Desk > Lube Station > Server > New; Desk > Server Group > New.

Server fields:

- Hostname (required, unique).
- IP Address.
- Control Panel (Select). Example: `cPanel / WHM`.
- API Username (Data).
- API Secret (Password).
- Max Accounts (Int).
- Active Accounts (Int).
- Status: Active, Maintenance, Disabled.
- Server Group (Link).

Server Group fields:

- Group Name (required, unique).
- Servers (Table of Server links).
- Fill Strategy: Round Robin, Least Full, Manual.

Steps:

1. Open Server > New.
2. Enter Hostname.
3. Enter IP Address.
4. Enter Control Panel.
5. Enter API Username.
6. Enter API Secret.
7. Enter Max Accounts.
8. Set Status to Active.
9. Save.
10. Open Server Group > New.
11. Enter Group Name.
12. Add each Server row.
13. Select Fill Strategy.
14. Save.
15. Link this group on each Hosting Plan that uses owned servers.

## 10. Reseller Hosting (separate setup)

WHMCS path: same as Shared, type Reseller Hosting, reseller package mapping.
Lube Station path: Hosting Plan with Product Type Reseller.

DocTypes used: same as section 8. Package mapping points to a reseller package.

Steps:

1. Create Product Group `Reseller Hosting`.
2. Create Server records for reseller-capable WHM, Plesk, or DirectAdmin hosts.
3. Create Server Group for reseller nodes.
4. Create schema `Reseller Default`. Check Requires Domain.
5. Create Hosting Plan with Product Type Reseller.
6. Link Product Group, Provisioning Module for the panel, Server Group, Schema, and Welcome Email Template.
7. Add Config Fields for reseller limits. Example: `package = reseller_50`, `max_subaccounts = 50`.
8. Create Plan Pricing rows with Recurring cycles and setup fee if needed.
9. Activate and test order, suspension, and termination.

Difference from Shared Hosting: Config Fields map to a reseller package, not an end-user package. Do not reuse shared package names.

## 11. VPS (separate setup)

WHMCS path: type Server/VPS, module SolusVM or Virtualizor, hostname and password prompts.
Lube Station path: Hosting Plan with Product Type VPS plus VPS Configuration.

Extra DocTypes: VPS Configuration, VPS Instance, Infrastructure Provider, Provider Product.

VPS Configuration fields (one per Hosting Plan, Hosting Plan link is unique):

- Hosting Plan (Link, required, unique).
- CPU Cores.
- RAM MB.
- Storage GB.
- Bandwidth GB.
- OS Images JSON (Code).
- Locations JSON (Code).
- IPv4 Count.
- Backup Enabled (Check).

Screens:

- Screen 1: Desk > Infrastructure Provider. Confirm Active VPS API provider.
- Screen 2: Desk > Provider Product. Confirm regions and plans JSON.
- Screen 3: Desk > Product Type Schema. Confirm Requires Hostname, Requires Root Password, Requires OS, Requires Location.
- Screen 4: Desk > Hosting Plan. Create VPS plan.
- Screen 5: Desk > VPS Configuration. Create fixed specs.
- Screen 6: Desk > Plan Pricing. Add cycles.

Steps:

1. Create Product Group `VPS Plans`.
2. Create Infrastructure Provider with Provider Type VPS API. Set Status to Active.
3. Create Provider Product. Select Product Type VPS. Fill Regions JSON and Plans JSON.
4. Create Reseller Agreement if you resell upstream capacity.
5. Create schema `VPS Default`. Check Requires Hostname, Requires Root Password, Requires OS, and Requires Location. Leave Requires Domain cleared unless you bundle a domain.
6. Create Hosting Plan with Product Type VPS.
7. Create VPS Configuration for that plan. Enter CPU, RAM, storage, bandwidth, IPv4 count, OS images, and locations.
8. Lock fixed plans by keeping specs only in VPS Configuration. Expose choices through schema fields only for customizable plans.
9. Create Plan Pricing rows with Recurring cycles.
10. Test boot, reboot, shutdown, snapshot, and usage display if the adapter supports them.

## 12. Dedicated Server (separate setup)

WHMCS path: type Server/VPS with dedicated module.
Lube Station path: Hosting Plan with Product Type Dedicated Server plus Dedicated Server Configuration and Dedicated Server Inventory.

Extra DocTypes: Dedicated Server Configuration, Dedicated Server Inventory.

Configuration fields (one per Hosting Plan):

- Hosting Plan (Link, required, unique).
- Server Class.
- Location.
- OS Image.
- Control Panel.
- Managed Service (Check).
- IP Count.
- Bandwidth Commitment.

Inventory fields:

- Provider (Link).
- Asset ID (unique).
- CPU, RAM GB, Storage JSON, Location, IP Pool, Bandwidth Mbps.
- Status: Available, Reserved, Assigned, Wipe Pending, Terminated.
- Assigned Service, Lease Key, Lease Expiry.

Steps:

1. Create Product Group `Dedicated Servers`.
2. Create Infrastructure Provider with Provider Type Dedicated Server Provider, Bare Metal API, or Local Infrastructure.
3. Create Dedicated Server Inventory rows. Keep Status as Available until sold.
4. Create schema `Dedicated Default`. Check Requires Hostname and Requires OS. Add data-center or network fields as needed.
5. Create Hosting Plan with Product Type Dedicated Server.
6. Create Dedicated Server Configuration for that plan.
7. Enable Stock Control on the plan if quantity is limited. Set Qty Available.
8. Create Plan Pricing rows with Recurring cycles and setup fee for provisioning.
9. Test reserve, assign, release, and wipe approval. A server returns to Available only after wipe confirmation.

## 13. Cloud (separate setup)

WHMCS mapping: no distinct Cloud type. WHMCS uses Server/VPS type with a cloud module.
Lube Station mapping: Hosting Plan with Product Type Cloud. Same pattern.

Steps:

1. Create Product Group `Cloud Servers`.
2. Create Infrastructure Provider with Provider Type Cloud API. Examples: AWS, Hetzner, Proxmox.
3. Create Provider Product with Product Type Cloud. Fill Regions JSON and Plans JSON.
4. Create Reseller Agreement with Billing Model Wholesale Recurring, Prepaid Credit, Per Usage, or Commission.
5. Create schema `Cloud Default`. Check Requires Hostname, Requires OS, and Requires Location.
6. Create Hosting Plan with Product Type Cloud.
7. Reuse VPS Configuration fields where the adapter expects them, or map through Plan Config Field rows.
8. Create Plan Pricing rows. Use Per Usage billing model on the agreement if the plan bills by usage.
9. Test provision, resize, snapshot, and usage pull through Usage Snapshot.

## 14. Email Hosting, Website Builder, SSL, Backup Addon, Migration Service (separate setups)

Lube Station gives each add-on style product its own Product Type. Use this section when the item has its own price and cycle.

### 14.1 Email Hosting

1. Create Product Group `Email Hosting`.
2. Create schema `Email Default`. Check Requires Domain.
3. Create Hosting Plan with Product Type Email Hosting.
4. Link Provisioning Module for the mail platform and Server Group if hosted locally.
5. Add Config Fields for mailbox quota and mailbox count. Example: `quota_gb = 25`, `mailboxes = 10`.
6. Create Plan Pricing rows with Recurring cycles.

### 14.2 Website Builder

1. Create Product Group `Website Builder`.
2. Create schema `Builder Default`. Check Requires Domain if sites bind to a domain.
3. Create Hosting Plan with Product Type Website Builder.
4. Link the builder Provisioning Module or upstream Provider Product.
5. Add Config Fields for site tier and template set.
6. Create Plan Pricing rows with Recurring cycles.

### 14.3 SSL Certificate

1. Create Product Group `SSL and Add-ons`.
2. Create Infrastructure Provider with Provider Type Reseller Program if you resell certificates.
3. Create Provider Product with Product Type SSL and External Product ID from the vendor.
4. Create schema `SSL Default`. Clear Requires Domain only if you collect the common name as a custom field instead.
5. Add a requirement field `common_name` with Required checked if you cleared Requires Domain.
6. Create Hosting Plan with Product Type SSL.
7. Create Plan Pricing rows. Use Annually for most certificates. Add setup fee for installation if you charge it.

### 14.4 Backup Addon

1. Create Product Group `SSL and Add-ons`.
2. Create schema `Backup Default`. No domain flags in most cases.
3. Create Hosting Plan with Product Type Backup Addon.
4. Add Config Fields for retention and quota. Example: `retention_days = 30`, `quota_gb = 100`.
5. Create Plan Pricing rows. The cycle can differ from the parent hosting plan.

### 14.5 Migration Service

1. Create Product Group `Services`.
2. Create schema `Migration Default`. Add fields for source panel, source host, and site size.
3. Create Hosting Plan with Product Type Migration Service.
4. Leave Provisioning Module empty if staff perform the work manually.
5. Create Plan Pricing rows. Use One Time for fixed migrations.

## 15. Downloadable and software license product (separate setup)

WHMCS path: type Other, Auto Release module, no domain.
Lube Station path: Hosting Plan with Product Type Downloadable Product plus Download Category and Downloadable Asset.

DocTypes: Download Category, Downloadable Asset, Download Allowed Product (child table).

Download Category fields:

- Category Name (required, unique).
- Parent Category (Link to Download Category).
- Is Public (Check).

Downloadable Asset fields:

- Title (required).
- Category (Link).
- Storage Type (required): Frappe File, Private Object Storage, Remote URL.
- File (Attach).
- Remote URL (Data).
- Access Policy (required): Public, Logged-in Customers, Purchased Product, Active Service.
- Allowed Products (Table to Download Allowed Product).
- Version, Download Count, Active.

Steps:

1. Open Download Category > New.
2. Enter Category Name.
3. Select Parent Category if nested.
4. Save.
5. Open Downloadable Asset > New.
6. Enter Title.
7. Select Category.
8. Select Storage Type.
9. Attach File or enter Remote URL.
10. Select Access Policy.
11. If policy is Purchased Product or Active Service, add Allowed Products rows with Hosting Plan links.
12. Check Active.
13. Save.
14. Create Hosting Plan with Product Type Downloadable Product.
15. Link Product Group for software.
16. Leave Product Type Schema domain flags cleared.
17. Create Plan Pricing rows. Use One Time for lifetime licenses or Recurring for subscriptions.
18. Test purchase, download link release, and license key delivery.

## 16. Add-on services: configurable options versus separate addons

Use this decision table for every add-on.

| Situation | Lube Station method | Billing |
|---|---|---|
| Choice changes the same service price (extra RAM, disk, OS) | Plan Config Field rows plus requirement fields on schema | Same invoice and cycle as main plan |
| Standalone item with its own cycle (SSL yearly on monthly hosting) | Separate Hosting Plan with Product Type SSL, Backup Addon, or Migration Service | Own Plan Pricing and cycle |
| File or license tied to purchase | Downloadable Asset with Allowed Products | Follows linked plan |
| Third-party service without custom code | Infrastructure Provider plus Provider Product plus Reseller Agreement | Per agreement billing model |

Steps for a same-plan option (example: extra RAM):

1. Open the Hosting Plan.
2. Add a Product Requirement Field row for `ram_upgrade` on the linked schema.
3. Set Field Type to Select.
4. Set Options Source to Static.
5. Enter Options JSON with choices and price deltas.
6. Save.

Steps for a separate addon (example: yearly SSL on monthly hosting):

1. Create Hosting Plan with Product Type SSL per section 14.3.
2. Create Plan Pricing with Billing Cycle Annually.
3. Sell it as a separate order item linked to the same customer.
4. Confirm separate Next Due Date on each Service.

## 17. Provisioning Module and adapter setup (replaces WHMCS module install)

DocTypes: Provisioning Module, Provisioning Adapter.
Screens: Desk > Provisioning Module > New; Desk > Provisioning Adapter List.

Provisioning Module fields:

- Module Name (required, unique). Example: `cPanel Shared`.
- Control Panel (Select). Example: `cPanel / WHM`.
- Python Class Path (Data, optional). Auto-filled from the linked adapter.

Provisioning Adapter fields:

- Adapter Name (required, unique).
- Vendor Name (required, Select: cPanel, Plesk, DirectAdmin, Virtualizor, Proxmox, Hetzner, AWS, Cloudflare, Custom).
- Class Path (auto-filled on save for known vendors; shown only when Vendor is Custom or the path is empty).
- API Mode (Data).
- Lifecycle Methods (Small Text).
- Supports Usage, Supports Resize, Supports SSO, Supports Change Plan (Checks).
- Active (Check).

Steps:

1. Open Provisioning Adapter List.
2. Confirm the adapter for cPanel, Plesk, DirectAdmin, Virtualizor, Proxmox, Hetzner, AWS, or Cloudflare exists.
3. Select Vendor Name and leave Class Path empty for known vendors. It fills on save.
4. Check Active for adapters you sell.
5. Open Provisioning Module > New.
6. Enter Module Name.
7. Enter Control Panel.
8. Copy Python Class Path from the matching Provisioning Adapter record.
9. Save.
10. Select this module on each Hosting Plan it provisions.
11. Confirm Provider API Log records Success for create, suspend, unsuspend, and terminate tests.

WHMCS difference: WHMCS bundles code, package mapping, and automation buttons in one module screen. Lube Station keeps code in the adapter, seller selection in the module, capacity in servers or providers, and automation in background jobs plus Service status.

### 17.1 Custom vendor adapter (developer task)

Use this when Vendor is Custom for a payment, provisioning, or registrar adapter. A seller cannot do this from Desk. A developer writes one class.

1. Create a file under `adapters/payments/`, `adapters/provisioning/`, or `adapters/registrar/`.
2. Subclass the matching base: `PaymentGatewayAdapter`, `ProvisioningAdapter`, or `RegistrarAdapter`.
3. Implement each method the vendor supports. Throw for the rest. Copy `bank_transfer.py` as the template.
4. Take no constructor arguments. The loader instantiates the class with zero arguments.
5. Reload the bench so the module is importable.
6. Open the adapter record in Desk.
7. Select Vendor Custom.
8. Enter the dotted path, e.g. `lube_station.lube_station.adapters.payments.mygateway.MyGatewayAdapter`.
9. Set the capability flags to match the implemented methods.
10. Check Active and save. A bad path is rejected on save.
11. Point webhooks at the generic endpoint with `gateway=<Adapter Name>`. Put the signing secret in `webhook_secrets` in site config if the vendor signs callbacks.

No controller changes are needed. Payment, provisioning, domain, and dunning flows resolve the adapter through the registry, which falls back to the record Class Path for unknown names.

## 18. Service lifecycle and automation

DocType: Service.
Screen: Desk > Lube Station > Service List.

Fields of interest: Customer, Hosting Plan, Order, Billing Cycle, Server, Primary Domain, Username, Status (Pending, Active, Suspended, Terminated, Cancelled), Next Due Date, Recurring Amount, Provisioning Log.

1. Confirm Order acceptance creates Service in Pending.
2. Confirm successful invoice payment moves Service to Active and triggers provisioning.
3. Confirm overdue invoice plus Dunning Rule moves Service to Suspended.
4. Confirm termination approval moves Service to Terminated.
5. Use Provisioning Log and Provider API Log to trace failures.

## 19. Seller go-live checklist

1. Confirm Lube Station Settings has company, support email, gateways, tax mode, and due days.
2. Confirm at least one Tax Rule is active where tax applies.
3. Confirm at least one Dunning Rule is active.
4. Confirm Product Groups show on the portal in the correct sort order.
5. Confirm every Hosting Plan has schema, pricing for each sold cycle, and Is Active checked.
6. Confirm VPS plans have VPS Configuration.
7. Confirm dedicated plans have Dedicated Server Configuration and Available inventory.
8. Confirm download assets are Active and linked to the correct plans.
9. Confirm registrar account is Active if domains are sold.
10. Place test orders for Shared, VPS or Cloud, and one addon. Confirm invoice, payment, Service status, and welcome email.
11. Confirm suspension and unsuspension on an overdue test invoice.

## Appendix A. Desk route reference

- Product Group: `/app/product-group`
- Hosting Plan: `/app/hosting-plan`
- Plan Pricing: `/app/plan-pricing`
- Product Type Schema: `/app/product-type-schema`
- Server: `/app/server`
- Server Group: `/app/server-group`
- Provisioning Module: `/app/provisioning-module`
- Provisioning Adapter: `/app/provisioning-adapter`
- Infrastructure Provider: `/app/infrastructure-provider`
- Provider Product: `/app/provider-product`
- Reseller Agreement: `/app/reseller-agreement`
- VPS Configuration: `/app/vps-configuration`
- Dedicated Server Configuration: `/app/dedicated-server-configuration`
- Dedicated Server Inventory: `/app/dedicated-server-inventory`
- Service: `/app/service`
- Payment Gateway Adapter: `/app/payment-gateway-adapter`
- Download Category: `/app/download-category`
- Downloadable Asset: `/app/downloadable-asset`
- Tax Rule: `/app/tax-rule`
- Dunning Rule: `/app/dunning-rule`
- Registrar Account: `/app/registrar-account`
