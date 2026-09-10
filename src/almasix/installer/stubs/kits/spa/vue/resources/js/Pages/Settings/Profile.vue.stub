<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import AuthenticatedLayout from "../../Layouts/AuthenticatedLayout.vue";
const props = defineProps({ user: Object, status: String });
const form = useForm({ name: props.user?.name || "", email: props.user?.email || "" });
const destroy = useForm({ password: "" });
</script>
<template>
  <AuthenticatedLayout title="Profile">
    <Head title="Profile" />
    <div class="mx-auto max-w-xl space-y-10">
      <p v-if="status" class="text-sm text-brand">{{ status }}</p>
      <section class="rounded-2xl border border-line bg-panel p-6">
        <h2 class="font-display text-xl font-semibold">Profile information</h2>
        <form class="mt-6 space-y-4" @submit.prevent="form.patch('/settings/profile')">
          <label class="block space-y-1.5"><span class="text-sm font-medium">Name</span><input v-model="form.name" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
          <label class="block space-y-1.5"><span class="text-sm font-medium">Email</span><input v-model="form.email" type="email" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
          <button type="submit" class="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Save</button>
        </form>
      </section>
      <section class="rounded-2xl border border-red-200 bg-panel p-6 dark:border-red-900/40">
        <h2 class="font-display text-xl font-semibold text-red-700 dark:text-red-400">Delete account</h2>
        <form class="mt-6 space-y-4" @submit.prevent="destroy.delete('/settings/profile')">
          <label class="block space-y-1.5"><span class="text-sm font-medium">Confirm password</span><input v-model="destroy.password" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
          <button type="submit" class="rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white">Delete account</button>
        </form>
      </section>
    </div>
  </AuthenticatedLayout>
</template>
