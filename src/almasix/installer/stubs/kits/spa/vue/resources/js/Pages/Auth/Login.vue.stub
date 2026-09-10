<script setup>
import { Head, Link, useForm } from "@inertiajs/vue3";
import GuestLayout from "../../Layouts/GuestLayout.vue";
defineProps({ status: String, canResetPassword: Boolean, canRegister: Boolean, appName: String });
const form = useForm({ email: "", password: "", remember: false });
</script>
<template>
  <GuestLayout title="Welcome back" :app-name="appName">
    <Head title="Log in" />
    <p v-if="status" class="mb-4 text-sm text-brand">{{ status }}</p>
    <form class="space-y-4" @submit.prevent="form.post('/login')">
      <label class="block space-y-1.5"><span class="text-sm font-medium">Email</span><input v-model="form.email" type="email" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm outline-none ring-brand/30 focus:ring-2" /></label>
      <label class="block space-y-1.5"><span class="text-sm font-medium">Password</span><input v-model="form.password" type="password" class="w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm outline-none ring-brand/30 focus:ring-2" /></label>
      <label class="flex items-center gap-2 text-sm text-muted"><input v-model="form.remember" type="checkbox" /> Remember me</label>
      <button type="submit" class="inline-flex w-full items-center justify-center rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white" :disabled="form.processing">Log in</button>
    </form>
    <div class="mt-6 flex justify-between text-sm text-muted">
      <Link v-if="canResetPassword" href="/forgot-password" class="hover:text-brand">Forgot password?</Link>
      <Link v-if="canRegister" href="/register" class="hover:text-brand">Create account</Link>
    </div>
  </GuestLayout>
</template>
