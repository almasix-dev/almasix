<script setup>
import { Head, Link, useForm } from "@inertiajs/vue3";
import GuestLayout from "../../Layouts/GuestLayout.vue";
defineProps({ status: String, email: String });
const form = useForm({});
</script>
<template>
  <GuestLayout title="Verify your email">
    <Head title="Verify email" />
    <p class="mb-4 text-sm text-muted">We sent a verification link<span v-if="email"> to {{ email }}</span>.</p>
    <p v-if="status" class="mb-4 text-sm text-brand">{{ status }}</p>
    <form @submit.prevent="form.post('/email/verification-notification')">
      <button type="submit" class="w-full rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Resend verification email</button>
    </form>
    <Link href="/logout" method="post" as="button" class="mt-4 block w-full text-center text-sm text-muted">Log out</Link>
  </GuestLayout>
</template>
