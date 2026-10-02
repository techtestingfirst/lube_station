<script setup lang="ts">
import { ref } from 'vue'
import { Button, ErrorMessage, TextInput, Textarea } from 'frappe-ui'
import { call } from '../api'

const subject = ref('')
const description = ref('')
const service = ref('')
const out = ref('')
const error = ref('')

async function open() {
  try {
    const r = await call<{ ticket: string; priority: string }>('lube_station.lube_station.support.tickets.create_ticket', {
      subject: subject.value, description: description.value, service: service.value || undefined,
    })
    out.value = `Ticket ${r.ticket} (${r.priority})`
    subject.value = ''
    description.value = ''
  } catch (e) {
    error.value = String(e)
  }
}
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Support</h1>
    <ErrorMessage v-if="error" :message="error" />
    <TextInput v-model="subject" label="Subject" />
    <Textarea v-model="description" label="Description" />
    <TextInput v-model="service" label="Service (optional)" placeholder="SVC-0001" />
    <Button label="Open ticket" variant="solid" @click="open" />
    <p v-if="out" class="text-sm">{{ out }}</p>
  </div>
</template>
