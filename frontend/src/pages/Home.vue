<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { call, friendlyError } from '../api'
import ThemeToggle from '../components/ThemeToggle.vue'
import LoadingBlock from '../components/LoadingBlock.vue'
import StatCard from '../components/StatCard.vue'
import ErrorState from '../components/ErrorState.vue'

const bootUser = window.user

const loggedUser = ref<string | null>(null)
const userError = ref('')
const checking = ref(true)

async function checkUser() {
  checking.value = true
  userError.value = ''
  try {
    loggedUser.value = await call<string>('frappe.auth.get_logged_user', {}, 'GET')
  } catch (e) {
    userError.value = friendlyError(e)
  } finally {
    checking.value = false
  }
}

onMounted(checkUser)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-ink-gray-8">Lube Station</h1>
        <p class="mt-1 text-sm text-ink-gray-5">Hosting, domains and billing — powered by your Frappe site.</p>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <ThemeToggle />
        <RouterLink to="/store">
          <Button label="Browse store" variant="solid" />
        </RouterLink>
      </div>
    </div>

    <div class="grid gap-3 sm:grid-cols-3">
      <StatCard value="Plans" label="Browse the store" to="/store" />
      <StatCard value="Services" label="Manage my services" to="/services" />
      <StatCard value="Billing" label="Invoices and payments" to="/invoices" />
    </div>

    <div class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-1 bg-surface-white">
      <div class="flex items-center gap-3 px-4 py-3">
        <span class="lucide-file-json size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-ink-gray-8">Boot data</p>
          <p class="mt-0.5 truncate text-sm text-ink-gray-5">
            {{ bootUser ? `Signed in as ${bootUser}` : 'Only a production build has boot data' }}
          </p>
        </div>
        <Badge :theme="bootUser ? 'green' : 'gray'" :label="bootUser ? 'Loaded' : 'Dev server'" />
      </div>

      <div class="flex items-center gap-3 px-4 py-3">
        <span class="lucide-server size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-ink-gray-8">Server call</p>
          <LoadingBlock v-if="checking && !loggedUser && !userError" :lines="1" />
          <p v-else class="mt-0.5 truncate text-sm text-ink-gray-5">
            {{
              loggedUser
                ? `frappe.auth.get_logged_user returned ${loggedUser}`
                : userError || 'Calling frappe.auth.get_logged_user…'
            }}
          </p>
        </div>
        <Badge v-if="loggedUser" theme="green" label="Working" />
        <Badge v-else-if="userError" theme="red" label="Failed" />
        <Button
          icon="lucide-refresh-cw"
          tooltip="Call again"
          aria-label="Call again"
          :loading="checking"
          @click="checkUser"
        />
      </div>
    </div>

    <ErrorState v-if="userError" :message="userError" @retry="checkUser" />
  </div>
</template>
