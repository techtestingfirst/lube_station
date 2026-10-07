<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import ThemeToggle from '../components/ThemeToggle.vue'

const email = ref('')
const error = ref('')
const done = ref(false)
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await call('lube_station.lube_station.portal.apis.forgot_password', { email: email.value })
    done.value = true
  } catch (e) {
    error.value = friendlyError(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-[70vh] bg-surface-gray-1 px-4 py-10">
    <div class="mx-auto flex w-full max-w-sm justify-end pb-3">
      <ThemeToggle />
    </div>
    <div class="mx-auto w-full max-w-sm space-y-4 rounded-xl border border-outline-gray-1 bg-surface-white p-6">
      <div class="space-y-1">
        <h1 class="text-xl font-semibold text-ink-gray-8">Reset password</h1>
        <p class="text-sm text-ink-gray-5">Enter your account email to get a reset link.</p>
      </div>
      <p
        v-if="done"
        class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-8"
      >
        If account exists, reset link sent. Check inbox.
      </p>
      <template v-else>
        <TextInput v-model="email" label="Account email" placeholder="you@example.com" />
        <ErrorMessage v-if="error" :message="error" />
        <Button label="Send reset link" variant="solid" class="w-full" :loading="loading" @click="submit" />
      </template>
      <p class="border-t border-outline-gray-1 pt-4 text-sm text-ink-gray-5">
        <RouterLink
          to="/login"
          class="font-medium text-ink-gray-8 underline underline-offset-2 hover:text-ink-gray-5"
        >
          Back to sign in
        </RouterLink>
      </p>
    </div>
  </div>
</template>
