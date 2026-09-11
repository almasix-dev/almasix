<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import AuthenticatedLayout from "../../Layouts/AuthenticatedLayout.vue";
defineProps({ notifications: { type: Array, default: () => [] }, status: String });
const form = useForm({});
</script>
<template>
  <AuthenticatedLayout title="Notifications">
    <Head title="Notifications" />
    <div class="mx-auto max-w-2xl">
      <div class="mb-6 flex items-center justify-between">
        <p class="text-muted">Database notification inbox.</p>
        <form @submit.prevent="form.post('/notifications/mark-all-read')">
          <button type="submit" class="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Mark all read</button>
        </form>
      </div>
      <p v-if="status" class="mb-4 text-sm text-brand">{{ status }}</p>
      <div v-if="!notifications.length" class="rounded-2xl border border-dashed border-line bg-panel px-6 py-16 text-center">
        <p class="font-display text-xl font-semibold">All clear</p>
        <p class="mt-2 text-sm text-muted">When something needs your attention, it will show up here.</p>
      </div>
      <ul v-else class="space-y-3">
        <li v-for="n in notifications" :key="n.id" class="rounded-xl border border-line bg-panel px-4 py-3">
          <pre class="whitespace-pre-wrap text-sm">{{ JSON.stringify(n.data, null, 2) }}</pre>
        </li>
      </ul>
    </div>
  </AuthenticatedLayout>
</template>
