<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, ErrorMessage } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import StatusTabs from '../components/StatusTabs.vue'
import EmptyState from '../components/EmptyState.vue'

interface TicketRow {
  name: string
  subject: string
  status: string
  priority: string
  modified?: string
  response_by?: string
  service?: string | null
  invoice?: string | null
}

const route = useRoute()
const service = ref('')

const tickets = ref<TicketRow[]>([])
const loading = ref(false)
const listError = ref('')
const tab = ref('All')

const ORDER = ['Open', 'Replied', 'Resolved', 'Closed']

const tabs = computed(() => {
  const counts = new Map<string, number>()
  for (const t of tickets.value) counts.set(t.status, (counts.get(t.status) || 0) + 1)
  const present = ORDER.filter((s) => counts.has(s))
  for (const s of counts.keys()) if (!present.includes(s)) present.push(s)
  return [{ label: 'All', count: tickets.value.length }, ...present.map((s) => ({ label: s, count: counts.get(s) || 0 }))]
})

const filtered = computed(() => tab.value === 'All' ? tickets.value : tickets.value.filter((t) => t.status === tab.value))

/** Helpdesk SPA lives on backend origin (:8000). Dev Vite runs :8080. */
function backendOrigin(): string {
  const { protocol, hostname, port } = window.location
  if (port === '8080') return `${protocol}//${hostname}:8000`
  return ''
}

const newTicketUrl = computed(() => `${backendOrigin()}/helpdesk/my-tickets/new`)

function ticketUrl(name: string): string {
  return `${backendOrigin()}/helpdesk/my-tickets/${name}`
}

function openNew() {
  window.open(newTicketUrl.value, '_blank')
}

onMounted(() => {
  const q = route.query.service
  if (typeof q === 'string' && q.trim()) service.value = q.trim()
  load()
})

async function load() {
  listError.value = ''
  loading.value = true
  try {
    tickets.value = await call<TicketRow[]>(
      'lube_station.lube_station.support.tickets.my_tickets',
      {},
      'GET',
    )
    if (!tabs.value.some((t) => t.label === tab.value)) tab.value = 'All'
  } catch (e) {
    listError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Support</h1>
        <p class="mt-1 text-sm text-ink-gray-5">
          Tickets live in Helpdesk — full thread, replies and knowledge base.
        </p>
      </div>
      <a :href="newTicketUrl" target="_blank" rel="noopener">
        <Button label="Open new ticket" variant="solid" size="sm" />
      </a>
    </div>

    <div
      v-if="service"
      class="rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-sm text-ink-gray-8"
    >
      Opening a ticket for service <span class="font-medium">{{ service }}</span> — mention it
      in the Helpdesk form so staff can link it.
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">My tickets</div>
      <div v-if="loading" class="mt-2 text-sm text-ink-gray-5">Loading tickets…</div>
      <ErrorMessage v-else-if="listError" class="mt-2" :message="listError" />
      <StatusTabs v-else-if="tickets.length" v-model="tab" :tabs="tabs" class="mt-2" />
      <div v-if="!loading && !listError && filtered.length" class="mt-2 divide-y divide-outline-gray-1">
        <a
          v-for="t in filtered"
          :key="t.name"
          :href="ticketUrl(t.name)"
          target="_blank"
          rel="noopener"
          class="flex items-center justify-between gap-3 px-1 py-2 hover:bg-surface-gray-1"
        >
          <div class="min-w-0">
            <div class="truncate text-sm font-medium text-ink-gray-8">
              {{ t.name }} — {{ t.subject }}
            </div>
            <div class="mt-0.5 truncate text-xs text-ink-gray-5">
              {{ t.service || 'No service' }} · Updated {{ t.modified || '—' }}
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <StatusBadge :status="t.priority" />
            <StatusBadge :status="t.status" />
          </div>
        </a>
      </div>
      <EmptyState
        v-else
        title="No tickets yet"
        hint="Open your first ticket in Helpdesk."
        action-label="Open new ticket"
        @action="openNew"
      />
    </div>
  </div>
</template>
