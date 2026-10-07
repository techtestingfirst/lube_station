<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import StatCard from '../components/StatCard.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import ErrorState from '../components/ErrorState.vue'

const data = ref<Record<string, number> | null>(null)
const error = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await call('lube_station.lube_station.portal.apis.dashboard', {}, 'GET')
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Dashboard</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Services, billing and support at a glance.</p>
      </div>
      <RouterLink to="/store"><Button label="Browse store" variant="solid" size="sm" /></RouterLink>
    </div>
    <ErrorState v-if="error && !loading" :message="error" @retry="load" />
    <LoadingBlock v-if="loading" :lines="4" />
    <template v-if="data && !loading">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard :value="data.services ?? 0" label="Services" to="/services" />
        <StatCard :value="data.unpaid ?? 0" label="Unpaid invoices" to="/invoices" />
        <StatCard :value="data.domains ?? 0" label="Domains" to="/domains" />
        <StatCard :value="data.tickets ?? 0" label="Tickets" to="/support" />
      </div>
      <div
        class="flex flex-wrap gap-x-5 gap-y-2 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3 text-sm"
      >
        <RouterLink to="/store" class="text-ink-gray-8 hover:underline">Browse storefront →</RouterLink>
        <RouterLink to="/services" class="text-ink-gray-5 hover:underline">My services →</RouterLink>
        <RouterLink to="/invoices" class="text-ink-gray-5 hover:underline">Pay invoices →</RouterLink>
        <RouterLink to="/support" class="text-ink-gray-5 hover:underline">Get support →</RouterLink>
      </div>
    </template>
  </div>
</template>
