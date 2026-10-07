<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call, friendlyError } from '../api'
import ThemeToggle from '../components/ThemeToggle.vue'

const route = useRoute()
const router = useRouter()
const key = (route.query.key as string) || ''
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await call('frappe.core.doctype.user.user.update_password', { new_password: password.value, key })
    router.push('/login')
  } catch (e) {
    error.value = friendlyError(e)
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
        <h1 class="text-xl font-semibold text-ink-gray-8">Set new password</h1>
        <p class="text-sm text-ink-gray-5">Choose a new password for your account.</p>
      </div>
      <TextInput v-model="password" label="New password" type="password" />
      <ErrorMessage v-if="error" :message="error" />
      <Button label="Update password" variant="solid" class="w-full" :loading="loading" @click="submit" />
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
