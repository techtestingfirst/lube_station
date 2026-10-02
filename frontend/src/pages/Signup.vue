<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call, login } from '../api'

const name = ref('')
const email = ref('')
const password = ref('')
const company = ref('')
const error = ref('')
const loading = ref(false)
const router = useRouter()

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await call('lube_station.lube_station.portal.apis.signup_customer', {
      full_name: name.value, email: email.value, password: password.value, company: company.value || undefined,
    })
    await login(email.value, password.value)
    router.push('/')
  } catch (e) {
    error.value = String(e).replace('ValidationError: ', '')
    loading.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-sm space-y-4">
    <h1 class="text-xl font-semibold">Create account</h1>
    <TextInput v-model="name" label="Full name" />
    <TextInput v-model="email" label="Email" placeholder="you@example.com" />
    <TextInput v-model="password" label="Password (8+ characters)" type="password" />
    <TextInput v-model="company" label="Company (optional)" />
    <ErrorMessage v-if="error" :message="error" />
    <Button label="Sign up" variant="solid" :loading="loading" @click="submit" />
    <p class="text-sm">Have account? <RouterLink to="/login" class="text-blue-600">Sign in</RouterLink></p>
  </div>
</template>
