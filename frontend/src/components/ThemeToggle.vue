<script setup lang="ts">
import { Button, useColorScheme } from 'frappe-ui'
import { computed } from 'vue'

const { resolvedColorScheme, toggleColorScheme } = useColorScheme()
const icon = computed(() => (resolvedColorScheme.value === 'dark' ? 'lucide-sun' : 'lucide-moon'))
const label = computed(() => (resolvedColorScheme.value === 'dark' ? 'Switch to light' : 'Switch to dark'))
</script>

<template>
  <Button :icon="icon" variant="ghost" size="sm" :aria-label="label" :title="label" @click="toggleColorScheme" />
</template>
