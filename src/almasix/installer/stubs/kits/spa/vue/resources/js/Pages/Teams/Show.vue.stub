<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import AuthenticatedLayout from "../../Layouts/AuthenticatedLayout.vue";
const props = defineProps({ team: Object, members: { type: Array, default: () => [] }, invitations: { type: Array, default: () => [] }, isOwner: Boolean, status: String });
const rename = useForm({ name: props.team?.name || "" });
const invite = useForm({ email: "", role: "member" });
</script>
<template>
  <AuthenticatedLayout :title="team?.name || 'Team'">
    <Head :title="team?.name || 'Team'" />
    <div class="mx-auto max-w-2xl space-y-8">
      <p v-if="status" class="text-sm text-brand">{{ status }}</p>
      <section v-if="isOwner" class="rounded-2xl border border-line bg-panel p-6">
        <h2 class="font-display text-xl font-semibold">Team settings</h2>
        <form class="mt-4 space-y-4" @submit.prevent="rename.put(`/teams/${team.id}`)">
          <label class="block space-y-1.5"><span class="text-sm font-medium">Name</span><input v-model="rename.name" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
          <button type="submit" class="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Save</button>
        </form>
      </section>
      <section class="rounded-2xl border border-line bg-panel p-6">
        <h2 class="font-display text-xl font-semibold">Members</h2>
        <ul class="mt-4 space-y-2">
          <li v-for="m in members" :key="m.id" class="flex justify-between text-sm"><span>{{ m.name }} <span class="text-muted">({{ m.email }})</span></span><span class="text-muted">{{ m.role }}</span></li>
        </ul>
      </section>
      <section v-if="isOwner" class="rounded-2xl border border-line bg-panel p-6">
        <h2 class="font-display text-xl font-semibold">Invite</h2>
        <form class="mt-4 space-y-4" @submit.prevent="invite.post(`/teams/${team.id}/members`)">
          <label class="block space-y-1.5"><span class="text-sm font-medium">Email</span><input v-model="invite.email" type="email" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
          <button type="submit" class="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Send invite</button>
        </form>
      </section>
    </div>
  </AuthenticatedLayout>
</template>
