<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { call } from '../api'

const data = ref<Record<string, number> | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    data.value = await call('lube_station.lube_station.portal.apis.dashboard', {}, 'GET')
  } catch (e) {
    error.value = String(e)
  }
})
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-xl font-semibold">Dashboard</h1>
    <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
    <div v-if="data" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded border p-3"><div class="text-2xl">{{ data.services }}</div><div class="text-xs">Services</div></div>
      <div class="rounded border p-3"><div class="text-2xl">{{ data.unpaid }}</div><div class="text-xs">Unpaid invoices</div></div>
      <div class="rounded border p-3"><div class="text-2xl">{{ data.domains }}</div><div class="text-xs">Domains</div></div>
      <div class="rounded border p-3"><div class="text-2xl">{{ data.tickets }}</div><div class="text-xs">Tickets</div></div>
    </div>
    <RouterLink to="/store" class="text-sm text-blue-600">Browse storefront →</RouterLink>
  </div>
</template>
