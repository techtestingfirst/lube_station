<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call } from '../api'

const instances = ref<{ name: string }[]>([])
const target = ref('')
const action = ref('reboot')
const out = ref('')
const error = ref('')

async function send() {
  try {
    const r = await call<Record<string, unknown>>('lube_station.lube_station.portal.apis.vps_control', { instance: target.value, action: action.value })
    out.value = JSON.stringify(r)
  } catch (e) {
    error.value = String(e)
  }
}

onMounted(async () => {
  try {
    instances.value = await call('frappe.client.get_list', { doctype: 'VPS Instance', fields: ['name'] })
  } catch {
    instances.value = []
  }
})
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-xl font-semibold">VPS controls</h1>
    <ErrorMessage v-if="error" :message="error" />
    <TextInput v-model="target" label="Instance" placeholder="VPS-0001" />
    <TextInput v-model="action" label="Action" placeholder="reboot | start | stop | snapshot | console | usage" />
    <Button label="Run (audited)" variant="solid" @click="send" />
    <p v-if="out" class="text-xs">{{ out }}</p>
  </div>
</template>
