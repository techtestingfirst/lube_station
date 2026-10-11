<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Button, ErrorMessage, TextInput, Textarea } from 'frappe-ui'
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

interface ThreadItem {
  kind: string
  content: string
  creation?: string
  by?: string
}

interface TicketDetail {
  ticket: TicketRow & { description?: string; raised_by?: string }
  reference: { service?: string | null; invoice?: string | null }
  comments: Array<{ content: string; creation?: string; commented_by?: string }>
  communications: Array<{
    content: string
    creation?: string
    communication_date?: string
    sender?: string
    sent_or_received?: string
  }>
}

const route = useRoute()
const subject = ref('')
const description = ref('')
const service = ref('')
const out = ref('')
const ticket = ref('')
const priority = ref('')
const error = ref('')
const opening = ref(false)

const tickets = ref<TicketRow[]>([])
const loadingTickets = ref(false)
const listError = ref('')
const selected = ref<string | null>(null)
const detail = ref<TicketDetail | null>(null)
const loadingDetail = ref(false)
const detailError = ref('')
const reply = ref('')
const replying = ref(false)
const replyError = ref('')

/** Helpdesk SPA lives on backend origin (:8000). Dev Vite runs :8080. */
function backendOrigin(): string {
  const { protocol, hostname, port } = window.location
  if (port === '8080') return `${protocol}//${hostname}:8000`
  return ''
}

const helpdeskUrl = computed(() =>
  selected.value ? `${backendOrigin()}/helpdesk/my-tickets/${selected.value}` : '',
)

const thread = computed<ThreadItem[]>(() => {
  if (!detail.value) return []
  const items: ThreadItem[] = []
  for (const c of detail.value.comments || []) {
    items.push({ kind: 'Note', content: c.content, creation: c.creation, by: c.commented_by })
  }
  for (const m of detail.value.communications || []) {
    items.push({
      kind: m.sent_or_received === 'Sent' ? 'Agent reply' : 'Your reply',
      content: m.content,
      creation: m.communication_date || m.creation,
      by: m.sender || undefined,
    })
  }
  items.sort((a, b) => String(a.creation || '').localeCompare(String(b.creation || '')))
  return items
})

async function loadTickets() {
  listError.value = ''
  loadingTickets.value = true
  try {
    tickets.value = await call<TicketRow[]>(
      'lube_station.lube_station.support.tickets.my_tickets',
      {},
      'GET',
    )
  } catch (e) {
    listError.value = friendlyError(e)
  } finally {
    loadingTickets.value = false
  }
}

async function selectTicket(name: string) {
  selected.value = name
  detail.value = null
  detailError.value = ''
  reply.value = ''
  replyError.value = ''
  loadingDetail.value = true
  try {
    detail.value = await call<TicketDetail>(
      'lube_station.lube_station.support.tickets.my_ticket_detail',
      { ticket: name },
      'GET',
    )
  } catch (e) {
    detailError.value = friendlyError(e)
  } finally {
    loadingDetail.value = false
  }
}

function closeDetail() {
  selected.value = null
  detail.value = null
  reply.value = ''
}

async function sendReply() {
  if (!selected.value) return
  replyError.value = ''
  replying.value = true
  try {
    await call('lube_station.lube_station.support.tickets.add_ticket_reply', {
      ticket: selected.value,
      content: reply.value,
    })
    reply.value = ''
    await selectTicket(selected.value)
  } catch (e) {
    replyError.value = friendlyError(e)
  } finally {
    replying.value = false
  }
}

onMounted(() => {
  const q = route.query.service
  if (typeof q === 'string' && q.trim()) service.value = q.trim()
  loadTickets()
})

async function open() {
  error.value = ''
  opening.value = true
  try {
    const r = await call<{ ticket: string; priority: string }>(
      'lube_station.lube_station.support.tickets.create_ticket',
      {
        subject: subject.value,
        description: description.value,
        service: service.value || undefined,
      },
    )
    out.value = `Ticket ${r.ticket} (${r.priority})`
    ticket.value = r.ticket
    priority.value = r.priority
    subject.value = ''
    description.value = ''
    await loadTickets()
    await selectTicket(r.ticket)
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    opening.value = false
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Support</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Open a ticket and track it below.</p>
      </div>
      <Button label="Open ticket" variant="solid" size="sm" :loading="opening" @click="open" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">New ticket</div>
      <div class="mt-2 space-y-3">
        <TextInput v-model="subject" label="Subject" placeholder="Brief summary of the issue" />
        <Textarea
          v-model="description"
          label="Description"
          placeholder="Steps to reproduce, error messages, affected service…"
          :rows="4"
        />
        <TextInput v-model="service" label="Service (optional)" placeholder="SVC-0001" />
        <ErrorMessage v-if="error" :message="error" />
      </div>
    </div>

    <div
      v-if="out"
      class="flex items-center justify-between gap-3 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3"
    >
      <div class="min-w-0">
        <div class="truncate text-sm font-medium text-ink-gray-8">{{ ticket }}</div>
        <div class="mt-1 text-sm text-ink-gray-5">{{ out }}</div>
      </div>
      <StatusBadge :status="priority || 'Open'" class="shrink-0" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">My tickets</div>
      <div v-if="loadingTickets" class="mt-2 text-sm text-ink-gray-5">Loading tickets…</div>
      <ErrorMessage v-else-if="listError" class="mt-2" :message="listError" />
      <div v-else-if="tickets.length" class="mt-2 divide-y divide-outline-gray-1">
        <button
          v-for="t in tickets"
          :key="t.name"
          class="flex w-full items-center justify-between gap-3 px-1 py-2 text-left hover:bg-surface-gray-1"
          @click="selectTicket(t.name)"
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
        </button>
      </div>
      <EmptyState
        v-else
        title="No tickets yet"
        hint="Fill in the form above and open your first ticket."
      />
    </div>

    <div
      v-if="selected"
      class="space-y-3 rounded-lg border border-outline-gray-1 bg-surface-white p-4"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <Button label="← Back to list" variant="ghost" size="sm" @click="closeDetail" />
        <a :href="helpdeskUrl" target="_blank" rel="noopener">
          <Button label="Open in Helpdesk" variant="subtle" size="sm" />
        </a>
      </div>
      <div v-if="loadingDetail" class="text-sm text-ink-gray-5">Loading ticket…</div>
      <ErrorMessage v-else-if="detailError" :message="detailError" />
      <div v-else-if="detail" class="space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <div class="text-sm font-medium text-ink-gray-8">{{ detail.ticket.name }}</div>
          <StatusBadge :status="detail.ticket.status" />
          <StatusBadge :status="detail.ticket.priority" />
        </div>
        <div class="text-sm font-medium text-ink-gray-8">{{ detail.ticket.subject }}</div>
        <div class="text-xs text-ink-gray-5">
          Service {{ detail.reference.service || '—' }} · Invoice
          {{ detail.reference.invoice || '—' }}
        </div>
        <div
          v-if="detail.ticket.description"
          class="rounded border border-outline-gray-1 bg-surface-gray-1 p-3 text-sm"
          v-html="detail.ticket.description"
        />
        <div class="space-y-2">
          <div class="text-sm font-medium text-ink-gray-8">Conversation</div>
          <div v-if="!thread.length" class="text-sm text-ink-gray-5">No replies yet.</div>
          <div
            v-for="(m, i) in thread"
            :key="i"
            class="rounded border border-outline-gray-1 p-3"
          >
            <div class="text-xs font-medium text-ink-gray-5">
              {{ m.kind }}{{ m.by ? ` · ${m.by}` : '' }}{{ m.creation ? ` · ${m.creation}` : '' }}
            </div>
            <div class="mt-1 text-sm" v-html="m.content" />
          </div>
        </div>
        <div class="space-y-2">
          <Textarea v-model="reply" label="Your reply" placeholder="Type your update…" :rows="3" />
          <ErrorMessage v-if="replyError" :message="replyError" />
          <Button label="Send reply" variant="solid" size="sm" :loading="replying" @click="sendReply" />
        </div>
      </div>
    </div>
  </div>
</template>
