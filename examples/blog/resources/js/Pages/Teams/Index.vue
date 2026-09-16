<script setup>
import { Head, Link, useForm } from "@inertiajs/vue3";
import AuthenticatedLayout from "../../Layouts/AuthenticatedLayout.vue";
defineProps({ teams: { type: Array, default: () => [] }, currentTeamId: [Number, String], status: String });
const form = useForm({ name: "" });
</script>
<template>
  <AuthenticatedLayout title="Teams">
    <Head title="Teams" />
    <div class="mx-auto max-w-2xl space-y-8">
      <p v-if="status" class="text-sm text-brand">{{ status }}</p>
      <section class="rounded-2xl border border-line bg-panel p-6">
        <h2 class="font-display text-xl font-semibold">Your teams</h2>
        <ul class="mt-4 divide-y divide-line">
          <li v-for="t in teams" :key="t.id" class="flex items-center justify-between py-3">
            <div><Link :href="`/teams/${t.id}`" class="font-medium hover:text-brand">{{ t.name }}</Link><span v-if="t.id === currentTeamId" class="ml-2 text-xs text-brand">current</span></div>
            <Link :href="`/teams/${t.id}/switch`" method="post" as="button" class="text-sm text-muted hover:text-ink">Switch</Link>
          </li>
          <li v-if="!teams.length" class="py-6 text-sm text-muted">No teams yet — create one below.</li>
        </ul>
      </section>
      <section class="rounded-2xl border border-line bg-panel p-6">
        <h2 class="font-display text-xl font-semibold">Create team</h2>
        <form class="mt-4 space-y-4" @submit.prevent="form.post('/teams')">
          <label class="block space-y-1.5"><span class="text-sm font-medium">Team name</span><input v-model="form.name" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
          <button type="submit" class="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Create</button>
        </form>
      </section>
    </div>
  </AuthenticatedLayout>
</template>
