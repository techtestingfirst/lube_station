<script setup lang="ts">
defineProps<{ modelValue: string; tabs: { label: string; count: number }[] }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <div class="flex flex-wrap gap-2">
    <button
      v-for="t in tabs"
      :key="t.label"
      class="rounded-full border px-3 py-1 text-sm"
      :class="modelValue === t.label
        ? 'border-ink-gray-8 bg-ink-gray-8 text-surface-white'
        : 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-1'"
      @click="$emit('update:modelValue', t.label)"
    >
      {{ t.label }} ({{ t.count }})
    </button>
  </div>
</template>
