<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { call, friendlyError } from '../api'
import { formatDate } from '../format'
import StatusBadge from '../components/StatusBadge.vue'
import StatCard from '../components/StatCard.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface D { domain_name: string; status: string; expiry_date: string }
const list = ref<D[]>([])
const name = ref('')
const error = ref('')
const loading = ref(true)
const loadError = ref('')
const registering = ref(false)
const router = useRouter()

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.my_domains', {}, 'GET')
  } catch (e) {
    loadError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

async function register() {
  error.value = ''
  registering.value = true
  try {
    const cart = await call<{ cart: string }>('lube_station.lube_station.portal.apis.cart_current', {}, 'GET')
    await call('lube_station.lube_station.portal.apis.cart_add_domain', { cart: cart.cart, domain: name.value })
    name.value = ''
    router.push('/cart')
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    registering.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Domains</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Register new domains and manage DNS for the ones you own.</p>
      </div>
      <Button label="Register" variant="solid" size="sm" :loading="registering" @click="register" />
    </div>

    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <StatCard :value="list.length" label="Domains" to="/domains" />
    </div>

    <div class="rounded-lg border border-outline-gray-1 bg-surface-white p-4">
      <div class="text-sm font-medium text-ink-gray-8">Register a domain</div>
      <p class="mt-1 text-sm text-ink-gray-5">Enter the full domain name. It goes to your cart — checkout completes the registration.</p>
      <div class="mt-3 flex flex-col gap-2 sm:flex-row">
        <TextInput v-model="name" placeholder="example.com" class="sm:grow" />
        <Button label="Register" variant="solid" :loading="registering" @click="register" />
      </div>
      <ErrorMessage v-if="error" :message="error" class="mt-2" />
    </div>

    <LoadingBlock v-if="loading" :lines="3" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="refresh" />
    <EmptyState
      v-else-if="!list.length"
      title="No domains yet"
      hint="Register your first domain with the form above."
    />
    <div v-else class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-white">
      <div
        v-for="d in list"
        :key="d.domain_name"
        class="flex items-center justify-between gap-3 border-t border-outline-gray-1 px-4 py-3 first:border-t-0"
      >
        <div class="min-w-0">
          <div class="truncate text-sm font-medium text-ink-gray-8">{{ d.domain_name }}</div>
          <div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-gray-5">
            <StatusBadge :status="d.status" />
            <span>Expires {{ formatDate(d.expiry_date) }}</span>
          </div>
        </div>
        <Button label="DNS" variant="ghost" size="sm" :route="`/dns/${d.domain_name}`" class="shrink-0" />
      </div>
    </div>
  </div>
</template>
