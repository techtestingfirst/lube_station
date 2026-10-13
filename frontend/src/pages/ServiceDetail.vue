<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { Button, Dialog, FormControl } from 'frappe-ui'
import { call, friendlyError } from '../api'
import { formatDate, formatMoney } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface Svc {
  name: string
  hosting_plan: string
  plan_name?: string | null
  product_type?: string | null
  product_group?: string | null
  order_ref: string | null
  billing_cycle: string
  server: string | null
  server_hostname?: string | null
  server_panel?: string | null
  primary_domain: string | null
  svc_username: string | null
  vendor_ref?: string | null
  node?: string | null
  status: string
  next_due_date: string | null
  registration_date?: string | null
  recurring_amount: number
  payment_method?: string | null
  cancellation_requested?: boolean
  cancellation_mode?: string | null
}
interface Inv { name: string; status: string; total_due: number; due_date: string; gateway?: string | null }
interface Row { key: string; label: string; value: unknown }
interface Dedicated { name: string; asset_id: string; location: string; status: string; cpu?: string | null; ram_gb?: number | null; ip_pool?: string | null; bandwidth_mbps?: number | null }
interface Vps { name: string; status: string; ipv4: string | null; location: string; image?: string | null }
interface Capabilities { can_vps_control: boolean; can_vps_rebuild: boolean; can_vps_rescue: boolean; can_vps_snapshot: boolean; can_dedicated_control: boolean; can_change_password: boolean; can_sso: boolean; can_panel: boolean; can_upgrade: boolean; can_cancel: boolean }
interface MgmtButton { key: string; label: string; kind: string; url?: string; action?: string }
interface UpgradeOption { plan: string; plan_name: string; recurring_amount: number; setup_fee: number }
interface UsageSnap { name: string; snap_date: string; disk_used: number; bandwidth_used: number }
interface VpsSnap { name: string; instance: string; label: string | null; status: string; creation: string }
interface Detail {
  service: Svc
  kyc: { status: string; verified: boolean } | null
  plan: { name: string; plan_name: string; product_type: string; product_group: string } | null
  server: { hostname: string; ip_address: string | null; control_panel: string | null; status: string } | null
  billing: { billing_cycle: string; recurring_amount: number; next_due_date: string | null; registration_date: string | null; payment_method: string | null; order_ref: string | null }
  configuration: Row[]
  custom_fields: Row[]
  hidden_count: number
  invoices: Inv[]
  dedicated: Dedicated[]
  dedicated_spec: Record<string, unknown> | null
  vps: Vps[]
  vps_spec: Record<string, unknown> | null
  capabilities: Capabilities
  management: { panels: unknown[]; buttons: MgmtButton[] }
  management_note: string
  panel_url: string | null
  upgrade_options: UpgradeOption[]
  usage: { snapshots: UsageSnap[]; limits: { disk: number; bandwidth: number } }
  vps_snapshots: VpsSnap[]
}

const route = useRoute()
const router = useRouter()
const id = route.params.service as string
const detail = ref<Detail | null>(null)
const loading = ref(true)
const error = ref('')
const actionMsg = ref('')
const actionBusy = ref('')

const showPw = ref(false)
const pw1 = ref('')
const pw2 = ref('')
const showCancel = ref(false)
const cancelReason = ref('')
const cancelMode = ref('End of Billing Cycle')
const cancelConfirm = ref('')
const cancelAck = ref(false)
const showUpgrade = ref(false)
const upgradePlan = ref('')
const upgradeQuote = ref<{ old_plan: string; new_plan: string; billing_cycle: string; old_recurring: number; new_recurring: number; remaining_days: number; cycle_days: number; prorated_diff: number; setup_diff: number; total_due: number; payment_required: boolean } | null>(null)
const quoting = ref(false)
const showRdns = ref(false)
const rdnsTarget = ref('')
const rdnsHost = ref('')
const showRebuild = ref(false)
const rebuildTarget = ref('')
const showRescue = ref(false)
const rescueTarget = ref('')
const rescueKind = ref<'vps' | 'dedicated'>('vps')
const showRestore = ref(false)
const restoreInstance = ref('')
const restoreSnap = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await call('lube_station.lube_station.portal.apis.my_service_detail', { service: id }, 'GET')
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

function pdfUrl(name: string): string {
  const q = new URLSearchParams({ doctype: 'Hosting Invoice', name, format: 'Hosting Invoice' })
  return `/api/method/frappe.utils.print_format.download_pdf?${q.toString()}`
}

function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  return String(v)
}

async function vpsAction(instance: string, action: string) {
  actionMsg.value = ''
  actionBusy.value = `${instance}:${action}`
  try {
    const out = await call('lube_station.lube_station.portal.apis.vps_control', { instance, action }, 'POST')
    if (out && typeof out === 'object' && 'url' in (out as Record<string, unknown>)) {
      window.open(String((out as Record<string, unknown>).url), '_blank', 'noopener')
      actionMsg.value = 'Console opened in a new tab.'
    } else {
      actionMsg.value = `${action} accepted for ${instance}.`
    }
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

async function panelLogin() {
  actionMsg.value = ''
  actionBusy.value = 'sso'
  try {
    const out = await call<{ url?: string }>('lube_station.lube_station.portal.apis.get_panel_login', { service: id }, 'POST')
    if (!out?.url) throw new Error('Panel login failed, please try again later')
    window.open(out.url, '_blank', 'noopener')
    actionMsg.value = 'Hosting panel opened in a new tab. Link expires soon.'
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

async function submitPassword() {
  actionMsg.value = ''
  if (pw1.value !== pw2.value) {
    actionMsg.value = 'Passwords do not match.'
    return
  }
  actionBusy.value = 'password'
  try {
    await call('lube_station.lube_station.portal.apis.change_service_password', { service: id, new_password: pw1.value }, 'POST')
    actionMsg.value = 'Password changed.'
    showPw.value = false
    pw1.value = ''
    pw2.value = ''
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

async function submitCancellation() {
  actionMsg.value = ''
  if (cancelReason.value.trim().length < 10) {
    actionMsg.value = 'Please tell us why (10+ characters).'
    return
  }
  if (cancelConfirm.value.trim() !== id) {
    actionMsg.value = `Type ${id} to confirm cancellation.`
    return
  }
  if (!cancelAck.value) {
    actionMsg.value = 'Please acknowledge you understand the cancellation.'
    return
  }
  actionBusy.value = 'cancel'
  try {
    const out = await call<{ mode?: string; terminated?: boolean }>('lube_station.lube_station.portal.apis.request_cancellation', { service: id, reason: cancelReason.value, mode: cancelMode.value, confirm_text: cancelConfirm.value.trim(), acknowledged: cancelAck.value }, 'POST')
    actionMsg.value = out.terminated
      ? 'Service cancelled immediately as requested.'
      : `Cancellation scheduled (${out.mode || cancelMode.value}). Service stays active until end of cycle. You can withdraw it below.`
    showCancel.value = false
    cancelReason.value = ''
    cancelConfirm.value = ''
    cancelAck.value = false
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

async function withdrawCancellation() {
  actionMsg.value = ''
  actionBusy.value = 'withdraw'
  try {
    await call('lube_station.lube_station.portal.apis.withdraw_cancellation', { service: id }, 'POST')
    actionMsg.value = 'Scheduled cancellation withdrawn. Service continues.'
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

async function fetchQuote(plan: string) {
  upgradeQuote.value = null
  if (!plan) return
  quoting.value = true
  try {
    upgradeQuote.value = await call('lube_station.lube_station.portal.apis.upgrade_quote', { service: id, new_plan: plan }, 'GET')
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    quoting.value = false
  }
}

function pickUpgrade(plan: string) {
  upgradePlan.value = plan
  fetchQuote(plan)
}

async function submitUpgrade() {
  actionMsg.value = ''
  if (!upgradePlan.value) {
    actionMsg.value = 'Pick a plan first.'
    return
  }
  actionBusy.value = 'upgrade'
  try {
    const out = await call<{ order?: string; invoice?: string; total_due?: number; payment_required?: boolean; applied?: boolean; payment?: { url?: string } }>('lube_station.lube_station.portal.apis.request_upgrade', { service: id, new_plan: upgradePlan.value }, 'POST')
    if (out.payment_required && out.invoice) {
      actionMsg.value = `Balance of ${formatMoney(out.total_due || 0)} due. Redirecting to payment...`
      showUpgrade.value = false
      router.push(`/pay/${out.invoice}`)
      return
    }
    actionMsg.value = 'Plan changed. No balance was due.'
    showUpgrade.value = false
    upgradePlan.value = ''
    upgradeQuote.value = null
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

async function dedicatedStep(inventory: string, step: string, arg?: string) {
  actionMsg.value = ''
  actionBusy.value = `${inventory}:${step}`
  try {
    const out = await call('lube_station.lube_station.portal.apis.dedicated_control', { inventory, step, arg }, 'POST')
    actionMsg.value = step === 'rdns'
      ? `rDNS requested for ${(out as { hostname?: string }).hostname}. Staff will confirm.`
      : `${step} queued for ${inventory}.`
    showRdns.value = false
    rdnsHost.value = ''
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

function askRdns(inventory: string) {
  rdnsTarget.value = inventory
  rdnsHost.value = ''
  showRdns.value = true
}

function askRebuild(instance: string) {
  rebuildTarget.value = instance
  showRebuild.value = true
}

async function confirmRebuild() {
  showRebuild.value = false
  if (rebuildTarget.value) await vpsAction(rebuildTarget.value, 'rebuild')
}

function askRescue(target: string, kind: 'vps' | 'dedicated') {
  rescueTarget.value = target
  rescueKind.value = kind
  showRescue.value = true
}

async function confirmRescue() {
  showRescue.value = false
  if (!rescueTarget.value) return
  if (rescueKind.value === 'vps') await vpsAction(rescueTarget.value, 'rescue')
  else await dedicatedStep(rescueTarget.value, 'rescue')
}

function ssoDisabledReason(): string {
  const d = detail.value
  if (!d) return 'Panel login unavailable'
  if (d.service.status !== 'Active') return 'Panel login is available for Active services only'
  if (!d.service.server) return 'Server not assigned yet — provisioning will enable login'
  if (!d.service.svc_username) return 'Panel account not ready yet — provisioning will enable login'
  if (!d.panel_url && !d.management.buttons.length) return 'Panel login is not supported for this product'
  return 'Single sign-on not ready — use the panel link above'
}

function usagePct(used: number, limit: number): number {
  if (!limit || limit <= 0) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

function snapsFor(instance: string): VpsSnap[] {
  return (detail.value?.vps_snapshots || []).filter((s) => s.instance === instance)
}

function askRestore(instance: string) {
  restoreInstance.value = instance
  const list = snapsFor(instance)
  restoreSnap.value = list.length ? list[0].name : ''
  showRestore.value = true
}

async function submitRestore() {
  actionMsg.value = ''
  if (!restoreSnap.value) {
    actionMsg.value = 'Pick a snapshot first.'
    return
  }
  actionBusy.value = 'restore'
  try {
    await call('lube_station.lube_station.portal.apis.vps_restore', { instance: restoreInstance.value, snapshot: restoreSnap.value }, 'POST')
    actionMsg.value = 'Restore started. The instance will come back on the selected snapshot.'
    showRestore.value = false
    restoreSnap.value = ''
    await load()
  } catch (e) {
    actionMsg.value = friendlyError(e)
  } finally {
    actionBusy.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <RouterLink to="/services" class="text-sm text-ink-gray-5 hover:underline">← Services</RouterLink>
        <h1 class="mt-1 text-xl font-semibold tracking-tight text-ink-gray-8">{{ id }}</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Service details, billing and linked resources.</p>
      </div>
      <RouterLink :to="`/support?service=${encodeURIComponent(id)}`"><Button label="Get support" variant="subtle" size="sm" /></RouterLink>
    </div>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <EmptyState
      v-else-if="!detail"
      title="Service not found"
      hint="It may belong to a different account."
      action-label="Back to services"
      @action="router.push('/services')"
    />
    <template v-else>
      <div class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm font-medium text-ink-gray-8">{{ detail.service.plan_name || detail.service.hosting_plan }}</span>
          <StatusBadge :status="detail.service.status" />
          <span v-if="detail.service.product_type" class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs text-ink-gray-6">{{ detail.service.product_type }}</span>
          <span v-if="detail.service.cancellation_requested" class="rounded bg-surface-yellow-2 px-2 py-0.5 text-xs text-ink-yellow-4">Cancellation requested</span>
        </div>
        <dl class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Billing cycle</dt><dd class="text-ink-gray-8">{{ detail.billing.billing_cycle || '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Recurring</dt><dd class="text-ink-gray-8">{{ formatMoney(detail.billing.recurring_amount) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Next due</dt><dd class="text-ink-gray-8">{{ formatDate(detail.billing.next_due_date) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Registered</dt><dd class="text-ink-gray-8">{{ formatDate(detail.billing.registration_date) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Payment method</dt><dd class="text-ink-gray-8">{{ detail.billing.payment_method || '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Order</dt><dd class="text-ink-gray-8">{{ detail.billing.order_ref || '—' }}</dd></div>
        </dl>
      </div>

      <div v-if="detail.kyc && !detail.kyc.verified" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-yellow-2 px-4 py-3">
        <span class="text-sm font-medium text-ink-gray-8">Activation blocked: identity verification is {{ detail.kyc.status }}.</span>
        <span class="text-sm text-ink-gray-6">Payment is received — complete verification and this service activates automatically.</span>
        <RouterLink to="/kyc"><Button label="Complete verification" size="sm" variant="solid" /></RouterLink>
      </div>

      <div class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <h2 class="text-sm font-medium text-ink-gray-8">Service information</h2>
        <dl class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Primary domain</dt><dd class="truncate text-ink-gray-8">{{ detail.service.primary_domain || '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Username</dt><dd class="text-ink-gray-8">{{ detail.service.svc_username || '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Server</dt><dd class="text-ink-gray-8">{{ detail.service.server_hostname || detail.service.server || '—' }}</dd></div>
          <div v-if="detail.service.server_panel" class="flex justify-between gap-3"><dt class="text-ink-gray-5">Control panel</dt><dd class="text-ink-gray-8">{{ detail.service.server_panel }}</dd></div>
          <div v-if="detail.server?.ip_address" class="flex justify-between gap-3"><dt class="text-ink-gray-5">Server IP</dt><dd class="text-ink-gray-8">{{ detail.server.ip_address }}</dd></div>
          <div v-if="detail.service.vendor_ref" class="flex justify-between gap-3"><dt class="text-ink-gray-5">Vendor reference</dt><dd class="text-ink-gray-8">{{ detail.service.vendor_ref }}</dd></div>
          <div v-if="detail.service.node" class="flex justify-between gap-3"><dt class="text-ink-gray-5">Node</dt><dd class="text-ink-gray-8">{{ detail.service.node }}</dd></div>
        </dl>
        <div v-if="detail.management.buttons.length" class="mt-3 flex flex-wrap gap-2">
          <a
            v-for="b in detail.management.buttons"
            :key="b.key"
            :href="b.url"
            target="_blank"
            rel="noopener"
          ><Button :label="b.label" size="sm" /></a>
        </div>
      </div>

      <div v-if="detail.vps_spec || detail.dedicated_spec" class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <h2 class="text-sm font-medium text-ink-gray-8">Plan resources</h2>
        <dl v-if="detail.vps_spec" class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">CPU cores</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.vps_spec.cpu_cores) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">RAM</dt><dd class="text-ink-gray-8">{{ detail.vps_spec.ram_mb ? `${detail.vps_spec.ram_mb} MB` : '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Storage</dt><dd class="text-ink-gray-8">{{ detail.vps_spec.storage_gb ? `${detail.vps_spec.storage_gb} GB` : '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Bandwidth</dt><dd class="text-ink-gray-8">{{ detail.vps_spec.bandwidth_gb ? `${detail.vps_spec.bandwidth_gb} GB` : '—' }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Backups</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.vps_spec.backup_enabled) }}</dd></div>
        </dl>
        <dl v-if="detail.dedicated_spec" class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Server class</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.dedicated_spec.server_class) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Location</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.dedicated_spec.location) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">OS image</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.dedicated_spec.os_image) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">Managed</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.dedicated_spec.managed_service) }}</dd></div>
          <div class="flex justify-between gap-3"><dt class="text-ink-gray-5">IP count</dt><dd class="text-ink-gray-8">{{ fmtVal(detail.dedicated_spec.ip_count) }}</dd></div>
        </dl>
      </div>

      <div v-if="detail.usage.snapshots.length || detail.usage.limits.disk || detail.usage.limits.bandwidth" class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <h2 class="text-sm font-medium text-ink-gray-8">Resource usage</h2>
        <div v-if="detail.usage.snapshots.length" class="mt-3 space-y-2">
          <div v-for="s in detail.usage.snapshots.slice(-7)" :key="s.name" class="text-xs">
            <div class="flex justify-between gap-3 text-ink-gray-6"><span>{{ formatDate(s.snap_date) }}</span><span>Disk {{ s.disk_used }} / {{ detail.usage.limits.disk || '—' }} GB · BW {{ s.bandwidth_used }} / {{ detail.usage.limits.bandwidth || '—' }} GB</span></div>
            <div class="mt-1 h-1.5 overflow-hidden rounded bg-surface-gray-2">
              <div class="h-full rounded bg-ink-blue-5" :style="{ width: `${usagePct(s.bandwidth_used, detail.usage.limits.bandwidth)}%` }"></div>
            </div>
          </div>
        </div>
        <p v-else class="mt-2 text-xs text-ink-gray-5">No usage snapshots yet — daily collection fills this in.</p>
      </div>

      <div v-if="detail.configuration.length || detail.custom_fields.length" class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <h2 class="text-sm font-medium text-ink-gray-8">Options & fields</h2>
        <dl class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div v-for="r in detail.configuration" :key="`c-${r.key}`" class="flex justify-between gap-3"><dt class="text-ink-gray-5">{{ r.label }}</dt><dd class="truncate text-ink-gray-8">{{ fmtVal(r.value) }}</dd></div>
          <div v-for="r in detail.custom_fields" :key="`f-${r.key}`" class="flex justify-between gap-3"><dt class="text-ink-gray-5">{{ r.label }}</dt><dd class="truncate text-ink-gray-8">{{ fmtVal(r.value) }}</dd></div>
        </dl>
        <p v-if="detail.hidden_count" class="mt-2 text-xs text-ink-gray-5">{{ detail.hidden_count }} sensitive field{{ detail.hidden_count === 1 ? '' : 's' }} hidden (Admin Only).</p>
      </div>

      <div class="space-y-2">
        <h2 class="text-sm font-medium text-ink-gray-8">Invoices</h2>
        <div v-if="detail.invoices.length" class="space-y-2">
          <div
            v-for="i in detail.invoices"
            :key="i.name"
            class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 sm:flex-nowrap"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm font-medium text-ink-gray-8">{{ i.name }}</div>
              <div class="mt-0.5 text-sm text-ink-gray-5">Due {{ formatDate(i.due_date) }} · {{ formatMoney(i.total_due) }}<span v-if="i.gateway"> · {{ i.gateway }}</span></div>
            </div>
            <div class="w-28 shrink-0"><StatusBadge :status="i.status" /></div>
            <div class="flex shrink-0 gap-2">
              <a :href="pdfUrl(i.name)" target="_blank" rel="noopener"><Button label="PDF" size="sm" /></a>
              <RouterLink v-if="i.status !== 'Paid'" :to="`/pay/${i.name}`"><Button label="Pay" variant="solid" size="sm" /></RouterLink>
            </div>
          </div>
        </div>
        <p v-else class="text-sm text-ink-gray-5">No invoices for this service yet.</p>
      </div>

      <div v-if="detail.dedicated.length || detail.vps.length" class="space-y-2">
        <h2 class="text-sm font-medium text-ink-gray-8">Linked resources</h2>
        <div
          v-for="d in detail.dedicated"
          :key="d.name"
          class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-sm"
        >
          <div class="flex items-center justify-between gap-3">
            <span class="font-medium text-ink-gray-8">{{ d.asset_id || d.name }}</span>
            <StatusBadge :status="d.status" />
          </div>
          <div class="mt-1 text-xs text-ink-gray-5">{{ d.location || '—' }}<span v-if="d.cpu"> · {{ d.cpu }}</span><span v-if="d.ram_gb"> · {{ d.ram_gb }} GB</span><span v-if="d.ip_pool"> · {{ d.ip_pool }}</span></div>
          <div v-if="detail.capabilities.can_dedicated_control" class="mt-2 flex flex-wrap gap-2">
            <Button label="Reinstall OS" size="sm" :loading="actionBusy === `${d.name}:install_os`" @click="dedicatedStep(d.name, 'install_os')" />
            <Button label="Rescue" size="sm" variant="subtle" @click="askRescue(d.name, 'dedicated')" />
            <Button label="Network" size="sm" variant="subtle" :loading="actionBusy === `${d.name}:network`" @click="dedicatedStep(d.name, 'network')" />
            <Button label="rDNS" size="sm" variant="subtle" :loading="actionBusy === `${d.name}:rdns`" @click="askRdns(d.name)" />
            <Button label="Panel" size="sm" variant="subtle" :loading="actionBusy === `${d.name}:panel`" @click="dedicatedStep(d.name, 'panel')" />
          </div>
        </div>
        <div
          v-for="v in detail.vps"
          :key="v.name"
          class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-sm"
        >
          <div class="flex items-center justify-between gap-3">
            <span class="font-medium text-ink-gray-8">{{ v.name }} · {{ v.ipv4 || 'no IP yet' }}</span>
            <StatusBadge :status="v.status" />
          </div>
          <div class="mt-1 text-xs text-ink-gray-5">{{ v.location }}<span v-if="v.image"> · {{ v.image }}</span></div>
          <div v-if="detail.capabilities.can_vps_control" class="mt-2 flex flex-wrap gap-2">
            <Button label="Start" size="sm" :loading="actionBusy === `${v.name}:start`" @click="vpsAction(v.name, 'start')" />
            <Button label="Stop" size="sm" :loading="actionBusy === `${v.name}:stop`" @click="vpsAction(v.name, 'stop')" />
            <Button label="Reboot" size="sm" :loading="actionBusy === `${v.name}:reboot`" @click="vpsAction(v.name, 'reboot')" />
            <Button label="Console" size="sm" variant="subtle" :loading="actionBusy === `${v.name}:console`" @click="vpsAction(v.name, 'console')" />
            <Button v-if="detail.capabilities.can_vps_snapshot" label="Snapshot" size="sm" variant="subtle" :loading="actionBusy === `${v.name}:snapshot`" @click="vpsAction(v.name, 'snapshot')" />
            <Button v-if="detail.capabilities.can_vps_snapshot && snapsFor(v.name).length" label="Restore" size="sm" variant="subtle" @click="askRestore(v.name)" />
            <Button v-if="detail.capabilities.can_vps_rescue" label="Rescue" size="sm" variant="subtle" @click="askRescue(v.name, 'vps')" />
            <Button v-if="detail.capabilities.can_vps_rebuild" label="Reinstall" size="sm" variant="subtle" @click="askRebuild(v.name)" />
          </div>
        </div>
      </div>

      <div class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3">
        <h2 class="text-sm font-medium text-ink-gray-8">Management</h2>
        <p class="mt-1 text-xs text-ink-gray-5">{{ detail.management_note }}</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <Button v-if="detail.capabilities.can_sso" label="Login to hosting panel" size="sm" variant="solid" :loading="actionBusy === 'sso'" @click="panelLogin" />
          <Button v-else label="Login to hosting panel" size="sm" variant="subtle" disabled :title="ssoDisabledReason()" />
          <Button v-if="detail.capabilities.can_change_password" label="Change password" size="sm" @click="showPw = true" />
          <Button v-if="detail.capabilities.can_upgrade" label="Upgrade / Downgrade" size="sm" variant="subtle" @click="showUpgrade = true" />
          <Button v-if="detail.capabilities.can_cancel" label="Request cancellation" size="sm" variant="subtle" @click="showCancel = true" />
          <Button v-if="detail.service.cancellation_requested && detail.service.status === 'Active'" label="Withdraw cancellation" size="sm" variant="subtle" :loading="actionBusy === 'withdraw'" @click="withdrawCancellation" />
        </div>
        <p v-if="detail.service.cancellation_requested" class="mt-2 text-xs text-ink-gray-5">Cancellation {{ detail.service.cancellation_mode || 'requested' }} — {{ detail.service.status === 'Active' ? 'service stays active until it executes. Withdraw above to keep it.' : 'executed.' }}</p>
        <p v-if="!detail.capabilities.can_sso" class="mt-2 text-xs text-ink-gray-5">{{ ssoDisabledReason() }}.</p>
        <p v-if="actionMsg" class="mt-2 text-xs text-ink-gray-6">{{ actionMsg }}</p>
      </div>

      <Dialog v-model="showPw" title="Change password">
        <template #default>
          <div class="space-y-3">
            <FormControl v-model="pw1" type="password" label="New password" placeholder="10+ characters, letters and numbers" />
            <FormControl v-model="pw2" type="password" label="Confirm password" placeholder="Repeat the new password" />
          </div>
        </template>
        <template #actions>
          <Button label="Cancel" variant="subtle" @click="showPw = false" />
          <Button label="Change" variant="solid" :loading="actionBusy === 'password'" @click="submitPassword" />
        </template>
      </Dialog>

      <Dialog v-model="showCancel" title="Request cancellation">
        <template #default>
          <div class="space-y-3">
            <p class="text-xs text-ink-gray-5">Immediate stops the service now. End of billing cycle keeps it active until {{ formatDate(detail.billing.next_due_date) }} and cancels automatically.</p>
            <FormControl v-model="cancelReason" type="textarea" label="Reason for cancellation (required, 10+ characters)" placeholder="Why are you cancelling? This helps us improve." />
            <div class="flex gap-4 text-sm text-ink-gray-8">
              <label class="flex items-center gap-1.5 text-ink-gray-8"><input v-model="cancelMode" type="radio" value="End of Billing Cycle" class="h-4 w-4" /> End of billing cycle</label>
              <label class="flex items-center gap-1.5 text-ink-gray-8"><input v-model="cancelMode" type="radio" value="Immediate" class="h-4 w-4" /> Immediate</label>
            </div>
            <FormControl v-model="cancelConfirm" :label="`Type ${id} to confirm`" :placeholder="id" />
            <label class="flex items-start gap-2 text-sm text-ink-gray-8"><input v-model="cancelAck" type="checkbox" class="mt-1 h-4 w-4" /> I understand this will {{ cancelMode === 'Immediate' ? 'stop the service now' : 'schedule automatic cancellation' }} and data may be deleted.</label>
            <p v-if="actionMsg && showCancel" class="text-xs text-ink-gray-6">{{ actionMsg }}</p>
          </div>
        </template>
        <template #actions>
          <Button label="Back" variant="subtle" @click="showCancel = false" />
          <Button :label="cancelMode === 'Immediate' ? 'Confirm cancellation' : 'Schedule cancellation'" variant="solid" :loading="actionBusy === 'cancel'" @click="submitCancellation" />
        </template>
      </Dialog>

      <Dialog v-model="showUpgrade" title="Upgrade / Downgrade">
        <template #default>
          <div v-if="detail.upgrade_options.length" class="space-y-2">
            <label
              v-for="o in detail.upgrade_options"
              :key="o.plan"
              class="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8"
            >
              <span class="flex items-center gap-2 font-medium text-ink-gray-9"><input v-model="upgradePlan" type="radio" :value="o.plan" class="h-4 w-4" @change="pickUpgrade(o.plan)" />{{ o.plan_name }}</span>
              <span class="font-medium text-ink-gray-8">{{ formatMoney(o.recurring_amount) }}/{{ detail.billing.billing_cycle }}</span>
            </label>
            <div v-if="quoting" class="text-xs text-ink-gray-6">Calculating prorated balance...</div>
            <div v-if="upgradeQuote" class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-xs">
              <div class="flex justify-between"><span class="text-ink-gray-6">Current</span><span class="font-medium text-ink-gray-9">{{ formatMoney(upgradeQuote.old_recurring) }}</span></div>
              <div class="flex justify-between"><span class="text-ink-gray-6">New</span><span class="font-medium text-ink-gray-9">{{ formatMoney(upgradeQuote.new_recurring) }}</span></div>
              <div class="flex justify-between"><span class="text-ink-gray-6">Remaining {{ upgradeQuote.remaining_days }}/{{ upgradeQuote.cycle_days }} days</span><span class="font-medium text-ink-gray-9">{{ formatMoney(upgradeQuote.prorated_diff) }}</span></div>
              <div class="flex justify-between"><span class="text-ink-gray-6">Setup difference</span><span class="font-medium text-ink-gray-9">{{ formatMoney(upgradeQuote.setup_diff) }}</span></div>
              <div class="flex justify-between font-medium"><span class="text-ink-gray-9">Balance due now</span><span class="text-ink-gray-9">{{ formatMoney(upgradeQuote.total_due) }}</span></div>
              <p class="mt-1 text-ink-gray-7">{{ upgradeQuote.payment_required ? 'Plan swaps automatically once this balance is paid.' : 'No payment needed — plan swaps immediately on confirm.' }}</p>
            </div>
            <p v-if="actionMsg && showUpgrade" class="text-xs text-ink-gray-6">{{ actionMsg }}</p>
          </div>
          <p v-else class="text-sm text-ink-gray-5">No upgrade options for this plan.</p>
        </template>
        <template #actions>
          <Button label="Back" variant="subtle" @click="showUpgrade = false" />
          <Button :label="upgradeQuote && !upgradeQuote.payment_required ? 'Confirm change' : 'Continue to payment'" variant="solid" :loading="actionBusy === 'upgrade'" @click="submitUpgrade" />
        </template>
      </Dialog>

      <Dialog v-model="showRescue" title="Boot into rescue mode?">
        <template #default>
          <p class="text-sm text-ink-gray-6">Rescue mode reboots <span class="font-medium">{{ rescueTarget }}</span> into a recovery environment for repair. Running services will go down until you exit rescue mode.</p>
        </template>
        <template #actions>
          <Button label="Back" variant="subtle" @click="showRescue = false" />
          <Button label="Enter rescue" variant="solid" @click="confirmRescue" />
        </template>
      </Dialog>

      <Dialog v-model="showRdns" title="Set reverse DNS">
        <template #default>
          <div class="space-y-3">
            <FormControl v-model="rdnsHost" label="Hostname" placeholder="host.example.com" />
            <p class="text-xs text-ink-gray-5">Staff reviews the request before the PTR record changes.</p>
          </div>
        </template>
        <template #actions>
          <Button label="Back" variant="subtle" @click="showRdns = false" />
          <Button label="Request" variant="solid" :loading="actionBusy === `${rdnsTarget}:rdns`" @click="dedicatedStep(rdnsTarget, 'rdns', rdnsHost)" />
        </template>
      </Dialog>

      <Dialog v-model="showRebuild" title="Reinstall server?">
        <template #default>
          <p class="text-sm text-ink-gray-6">Reinstall wipes <span class="font-medium">{{ rebuildTarget }}</span> and rebuilds it from the plan image. Back up data first.</p>
        </template>
        <template #actions>
          <Button label="Back" variant="subtle" @click="showRebuild = false" />
          <Button label="Reinstall" variant="solid" @click="confirmRebuild" />
        </template>
      </Dialog>

      <Dialog v-model="showRestore" title="Restore snapshot">
        <template #default>
          <div v-if="snapsFor(restoreInstance).length" class="space-y-2">
            <label
              v-for="s in snapsFor(restoreInstance)"
              :key="s.name"
              class="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-outline-gray-1 px-3 py-2 text-sm"
            >
              <span class="flex items-center gap-2"><input v-model="restoreSnap" type="radio" :value="s.name" />{{ s.label || s.name }}</span>
              <span class="text-ink-gray-6">{{ formatDate(s.creation) }} · {{ s.status }}</span>
            </label>
            <p class="text-xs text-ink-gray-5">Restoring replaces the current disk state. Back up first.</p>
          </div>
          <p v-else class="text-sm text-ink-gray-5">No snapshots for this instance yet.</p>
        </template>
        <template #actions>
          <Button label="Back" variant="subtle" @click="showRestore = false" />
          <Button label="Restore" variant="solid" :loading="actionBusy === 'restore'" @click="submitRestore" />
        </template>
      </Dialog>
    </template>
  </div>
</template>
