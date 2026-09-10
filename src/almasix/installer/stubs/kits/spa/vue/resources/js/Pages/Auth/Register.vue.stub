<script setup>
import { Head, Link, useForm } from "@inertiajs/vue3";
import GuestLayout from "../../Layouts/GuestLayout.vue";
defineProps({ appName: String });
const form = useForm({ name: "", email: "", password: "", password_confirmation: "" });
</script>
<template>
  <GuestLayout title="Create your account" :app-name="appName">
    <Head title="Register" />
    <form class="space-y-4" @submit.prevent="form.post('/register')">
      <label class="block space-y-1.5"><span class="text-sm font-medium">Name</span><input v-model="form.name" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Email</span><input v-model="form.email" type="email" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Password</span><input v-model="form.password" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Confirm password</span><input v-model="form.password_confirmation" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm" /></label>
      <button type="submit" class="w-full rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white">Create account</button>
    </form>
    <p class="mt-6 text-center text-sm text-muted">Already registered? <Link href="/login" class="text-brand">Log in</Link></p>
  </GuestLayout>
</template>
