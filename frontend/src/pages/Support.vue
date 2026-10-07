<script setup lang="ts">
import { ref } from 'vue'
import { Button, ErrorMessage, TextInput, Textarea } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'

const subject = ref('')
const description = ref('')
const service = ref('')
const out = ref('')
const ticket = ref('')
const priority = ref('')
const error = ref('')
const opening = ref(false)

async function open() {
  error.value = ''
  opening.value = true
  try {
    const r = await call<{ ticket: string; priority: string }>('lube_station.lube_station.support.tickets.create_ticket', {
      subject: subject.value, description: description.value, service: service.value || undefined,
    })
    out.value = `Ticket ${r.ticket} (${r.priority})`
    ticket.value = r.ticket
    priority.value = r.priority
    subject.value = ''
    description.value = ''
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
        <p class="mt-1 text-sm text-ink-gray-5">Open a ticket and track the confirmation below.</p>
      </div>
      <Button label="Open ticket" variant="solid" size="sm" :loading="opening" @click="open" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">New ticket</div>
      <div class="mt-2 space-y-3">
        <TextInput v-model="subject" label="Subject" placeholder="Brief summary of the issue" />
        <Textarea v-model="description" label="Description" placeholder="Steps to reproduce, error messages, affected service…" :rows="4" />
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
    <EmptyState
      v-else
      title="No ticket opened yet"
      hint="Fill in the form above and open your first ticket."
    />
  </div>
</template>
