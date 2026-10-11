<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, ErrorMessage } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
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
      <div v-else-if="tickets.length" class="mt-2 divide-y divide-outline-gray-1">
        <a
          v-for="t in tickets"
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
