<script setup>
import { onMounted, ref } from "vue";
const dark = ref(false);
onMounted(() => {
  dark.value = document.documentElement.classList.contains("dark");
});
function toggle() {
  const next = !document.documentElement.classList.contains("dark");
  document.documentElement.classList.toggle("dark", next);
  localStorage.setItem("forge-theme", next ? "dark" : "light");
  dark.value = next;
}
defineProps({ className: { type: String, default: "" } });
</script>
<template>
  <button type="button" @click="toggle" :class="['inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-panel text-sm text-muted hover:text-ink', className]" aria-label="Toggle theme">
    {{ dark ? "☀" : "☾" }}
  </button>
</template>
