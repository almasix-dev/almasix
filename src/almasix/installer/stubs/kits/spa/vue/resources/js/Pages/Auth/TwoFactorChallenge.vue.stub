<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import GuestLayout from "../../Layouts/GuestLayout.vue";
const form = useForm({ code: "", recovery_code: "" });
</script>
<template>
  <GuestLayout title="Two-factor challenge">
    <Head title="Two-factor" />
    <p class="mb-4 text-sm text-muted">Enter an authenticator code or a recovery code.</p>
    <form class="space-y-4" @submit.prevent="form.post('/two-factor-challenge')">
      <label class="block space-y-1.5"><span class="text-sm font-medium">Authentication code</span><input v-model="form.code" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Recovery code</span><input v-model="form.recovery_code" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <button type="submit" class="w-full rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Continue</button>
    </form>
  </GuestLayout>
</template>
