<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { login } from '../api'

const usr = ref('')
const pwd = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await login(usr.value, pwd.value)
  } catch {
    error.value = 'Invalid credentials'
    loading.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-sm space-y-4">
    <h1 class="text-xl font-semibold">Sign in</h1>
    <TextInput v-model="usr" label="Email" placeholder="you@example.com" />
    <TextInput v-model="pwd" label="Password" type="password" @keydown.enter="submit" />
    <ErrorMessage v-if="error" :message="error" />
    <Button label="Sign in" variant="solid" :loading="loading" @click="submit" />
    <p class="flex justify-between text-sm">
      <RouterLink to="/signup" class="text-blue-600">Create account</RouterLink>
      <RouterLink to="/forgot" class="text-blue-600">Forgot password?</RouterLink>
    </p>
  </div>
</template>
