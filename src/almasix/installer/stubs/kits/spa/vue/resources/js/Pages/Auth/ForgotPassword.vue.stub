<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import GuestLayout from "../../Layouts/GuestLayout.vue";
defineProps({ status: String, appName: String });
const form = useForm({ email: "" });
</script>
<template>
  <GuestLayout title="Reset password" :app-name="appName">
    <Head title="Forgot password" />
    <p class="mb-4 text-sm text-muted">Enter your email and we will send a reset link.</p>
    <p v-if="status" class="mb-4 text-sm text-brand">{{ status }}</p>
    <form class="space-y-4" @submit.prevent="form.post('/forgot-password')">
      <label class="block space-y-1.5"><span class="text-sm font-medium">Email</span><input v-model="form.email" type="email" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <button type="submit" class="w-full rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Email reset link</button>
    </form>
  </GuestLayout>
</template>
