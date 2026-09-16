<script setup>
import { Head } from "@inertiajs/vue3";
import AuthenticatedLayout from "../../Layouts/AuthenticatedLayout.vue";
import ThemeToggle from "../../Components/ThemeToggle.vue";
defineProps({ status: String });
</script>
<template>
  <AuthenticatedLayout title="Appearance">
    <Head title="Appearance" />
    <div class="mx-auto max-w-xl rounded-2xl border border-line bg-panel p-6">
      <h2 class="font-display text-xl font-semibold">Theme</h2>
      <p class="mt-1 text-sm text-muted">Forge supports light and dark. Your choice is stored in this browser.</p>
      <div class="mt-6 flex items-center gap-4"><ThemeToggle /><span class="text-sm text-muted">Toggle light / dark</span></div>
    </div>
  </AuthenticatedLayout>
</template>
