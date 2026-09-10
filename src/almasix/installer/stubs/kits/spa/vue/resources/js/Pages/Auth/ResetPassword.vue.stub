<script setup>
import { Head, useForm } from "@inertiajs/vue3";
import GuestLayout from "../../Layouts/GuestLayout.vue";
const props = defineProps({ token: String, email: String, appName: String });
const form = useForm({ token: props.token, email: props.email || "", password: "", password_confirmation: "" });
</script>
<template>
  <GuestLayout title="Choose a new password" :app-name="appName">
    <Head title="Reset password" />
    <form class="space-y-4" @submit.prevent="form.post('/reset-password')">
      <label class="block space-y-1.5"><span class="text-sm font-medium">Email</span><input v-model="form.email" type="email" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Password</span><input v-model="form.password" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Confirm password</span><input v-model="form.password_confirmation" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <button type="submit" class="w-full rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Reset password</button>
    </form>
  </GuestLayout>
</template>
