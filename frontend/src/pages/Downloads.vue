<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { call } from '../api'

interface A { name: string; title: string; access_policy: string }
const list = ref<A[]>([])
onMounted(async () => {
  list.value = await call('lube_station.lube_station.portal.apis.downloads', {}, 'GET')
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">Downloads</h1>
    <p class="text-xs">Only entitled assets listed. Every fetch checked server-side.</p>
    <div v-for="a in list" :key="a.name" class="rounded border p-3 text-sm">
      <div class="font-medium">{{ a.title }}</div>
      <div>{{ a.access_policy }}</div>
    </div>
  </div>
</template>
