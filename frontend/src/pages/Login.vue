<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { friendlyError, login } from '../api'
import ThemeToggle from '../components/ThemeToggle.vue'

const route = useRoute()
const usr = ref((route.query.email as string) || '')
const notice = ref(route.query.created ? 'Account created. Sign in below.' : '')
const pwd = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await login(usr.value, pwd.value)
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
        <h1 class="text-xl font-semibold text-ink-gray-8">Sign in</h1>
        <p class="text-sm text-ink-gray-5">Welcome back. Sign in to continue.</p>
      </div>
      <p
        v-if="notice"
        class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-8"
      >
        {{ notice }}
      </p>
      <div class="space-y-3">
        <TextInput v-model="usr" label="Email" placeholder="you@example.com" />
        <TextInput v-model="pwd" label="Password" type="password" @keydown.enter="submit" />
      </div>
      <ErrorMessage v-if="error" :message="error" />
      <Button label="Sign in" variant="solid" class="w-full" :loading="loading" @click="submit" />
      <div class="flex items-center justify-between border-t border-outline-gray-1 pt-4 text-sm">
        <RouterLink
          to="/signup"
          class="font-medium text-ink-gray-8 underline underline-offset-2 hover:text-ink-gray-5"
        >
          Create account
        </RouterLink>
        <RouterLink
          to="/forgot"
          class="font-medium text-ink-gray-8 underline underline-offset-2 hover:text-ink-gray-5"
        >
          Forgot password?
        </RouterLink>
      </div>
    </div>
  </div>
</template>
