<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Badge, Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import LoadingBlock from '../components/LoadingBlock.vue'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'

interface A { name: string; title: string; access_policy: string }
const list = ref<A[]>([])
const loading = ref(true)
const loadError = ref('')

async function refresh() {
  loading.value = true
  loadError.value = ''
  try {
    list.value = await call('lube_station.lube_station.portal.apis.downloads', {}, 'GET')
  } catch (e) {
    loadError.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Downloads</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Only entitled assets listed. Every fetch checked server-side.</p>
      </div>
      <Button label="Refresh" variant="solid" size="sm" :loading="loading" @click="refresh" />
    </div>

    <LoadingBlock v-if="loading" :lines="3" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="refresh" />
    <EmptyState
      v-else-if="!list.length"
      title="No downloads available"
      hint="Entitled files will appear here once they are assigned to your account."
      actionLabel="Refresh"
      @action="refresh"
    />
    <div v-else class="overflow-hidden rounded-lg border border-outline-gray-1 bg-surface-white">
      <div
        v-for="a in list"
        :key="a.name"
        class="flex items-center justify-between gap-3 border-t border-outline-gray-1 px-4 py-3 first:border-t-0"
      >
        <div class="min-w-0">
          <div class="truncate text-sm font-medium text-ink-gray-8">{{ a.title }}</div>
          <div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-gray-5">
            <Badge :theme="a.access_policy === 'Public' ? 'green' : 'blue'" size="md">{{ a.access_policy }}</Badge>
            <span class="truncate">{{ a.name }}</span>
          </div>
        </div>
        <Button label="Download" variant="outline" size="sm" class="shrink-0" @click="refresh" />
      </div>
    </div>
  </div>
</template>
