<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { Button, ErrorMessage, TextInput } from 'frappe-ui'
import { call } from '../api'

const route = useRoute()
const router = useRouter()
const key = (route.query.key as string) || ''
const password = ref('')
const error = ref('')

async function submit() {
  try {
    await call('frappe.core.doctype.user.user.update_password', { new_password: password.value, key })
    router.push('/login')
  } catch (e) {
    error.value = String(e)
  }
}
</script>

<template>
  <div class="mx-auto max-w-sm space-y-4">
    <h1 class="text-xl font-semibold">Set new password</h1>
    <ErrorMessage v-if="error" :message="error" />
    <TextInput v-model="password" label="New password" type="password" />
    <Button label="Update password" variant="solid" @click="submit" />
    <p class="text-sm"><RouterLink to="/login" class="text-blue-600">Back to sign in</RouterLink></p>
  </div>
</template>
