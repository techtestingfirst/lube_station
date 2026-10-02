<script setup lang="ts">
import { ref } from 'vue'
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
  </div>
</template>
