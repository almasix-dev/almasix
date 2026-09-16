<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import AuthenticatedLayout from "../../Layouts/AuthenticatedLayout.vue";
defineProps({ status: String });
const form = useForm({ current_password: "", password: "", password_confirmation: "" });
</script>
<template>
  <AuthenticatedLayout title="Password">
    <Head title="Password" />
    <div class="mx-auto max-w-xl rounded-2xl border border-line bg-panel p-6">
      <h2 class="font-display text-xl font-semibold">Update password</h2>
      <p v-if="status" class="mt-3 text-sm text-brand">{{ status }}</p>
      <form class="mt-6 space-y-4" @submit.prevent="form.put('/settings/password', { onSuccess: () => form.reset() })">
        <label class="block space-y-1.5"><span class="text-sm font-medium">Current password</span><input v-model="form.current_password" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
        <label class="block space-y-1.5"><span class="text-sm font-medium">New password</span><input v-model="form.password" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
        <label class="block space-y-1.5"><span class="text-sm font-medium">Confirm password</span><input v-model="form.password_confirmation" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
        <button type="submit" class="rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Save password</button>
      </form>
    </div>
  </AuthenticatedLayout>
</template>
