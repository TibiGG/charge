<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { pb, accountsEnabled, setDemo, signedIn } from '$lib/auth';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';

	let mode = $state<'in' | 'up'>('up');
	let email = $state('');
	let password = $state('');
	let name = $state('');
	let busy = $state(false);
	let err = $state('');
	let info = $state('');
	let providers = $state<string[]>([]);
	const enabled = accountsEnabled();

	onMount(async () => {
		if (signedIn()) return goto('/');
		if (!enabled) return;
		try {
			const m = await pb.collection('users').listAuthMethods();
			providers = (m.oauth2?.enabled ? m.oauth2.providers : []).map((p: any) => p.name);
		} catch {}
	});

	async function submit(e: Event) {
		e.preventDefault();
		busy = true; err = ''; info = '';
		try {
			if (mode === 'up') {
				await pb.collection('users').create({ email, password, passwordConfirm: password, name, emailVisibility: false });
				try { await pb.collection('users').requestVerification(email); } catch {}
			}
			await pb.collection('users').authWithPassword(email, password);
			setDemo(false);
			await goto('/start');
		} catch (e: any) {
			err = mode === 'in' ? COPY.welcome.badLogin
				: e?.response?.data?.email?.message ?? e?.response?.data?.password?.message ?? COPY.welcome.failed;
		}
		busy = false;
	}

	async function oauth(provider: string) {
		busy = true; err = '';
		try {
			await pb.collection('users').authWithOAuth2({ provider });
			setDemo(false);
			await goto('/start');
		} catch { err = COPY.welcome.failed; }
		busy = false;
	}

	async function forgot() {
		if (!email.includes('@')) { err = COPY.welcome.emailLabel; return; }
		try { await pb.collection('users').requestPasswordReset(email); } catch {}
		info = COPY.welcome.resetSent;
	}

	function demo() {
		setDemo(true);
		location.href = '/';
	}
	const sayAll = `${COPY.welcome.title}. ${COPY.welcome.intro}`;
</script>

<section class="hero">
	<h1>{COPY.welcome.title}</h1>
	<p class="lede">{COPY.welcome.intro}</p>
	<Speak text={sayAll} />
</section>

{#if enabled}
	<section class="card">
		<div class="auth-tabs" role="group">
			<button class="secondary" aria-pressed={mode === 'up'} onclick={() => (mode = 'up')}>{COPY.welcome.signUp}</button>
			<button class="secondary" aria-pressed={mode === 'in'} onclick={() => (mode = 'in')}>{COPY.welcome.signIn}</button>
		</div>

		{#each providers.filter((p) => p === 'google' || p === 'apple') as p}
			<button class="secondary sso" disabled={busy} onclick={() => oauth(p)}>
				<span class="sso-mark" aria-hidden="true">{p === 'google' ? 'G' : ''}</span>
				{p === 'google' ? COPY.welcome.google : COPY.welcome.apple}
			</button>
		{/each}
		{#if providers.length}<p class="or">{COPY.welcome.or}</p>{/if}

		<form class="stack" onsubmit={submit}>
			{#if mode === 'up'}
				<label class="field">{COPY.welcome.nameLabel}<input autocomplete="given-name" maxlength="80" bind:value={name} /></label>
			{/if}
			<label class="field">{COPY.welcome.emailLabel}<input type="email" required autocomplete="email" bind:value={email} /></label>
			<label class="field">{COPY.welcome.passwordLabel}
				<input type="password" required minlength={mode === 'up' ? 10 : 1}
					autocomplete={mode === 'up' ? 'new-password' : 'current-password'} bind:value={password} />
			</label>
			{#if mode === 'up'}<p class="muted small">{COPY.welcome.passwordHint}</p>{/if}
			{#if err}<p class="error" role="alert">{err}</p>{/if}
			{#if info}<p class="done" role="status">{info}</p>{/if}
			<button class="primary" type="submit" disabled={busy}>
				{busy ? COPY.welcome.working : mode === 'up' ? COPY.welcome.create : COPY.welcome.go}
			</button>
		</form>
		{#if mode === 'in'}<p class="hint"><button class="link" onclick={forgot}>{COPY.welcome.forgot}</button></p>{/if}
		<p class="muted small">{COPY.welcome.bupaNote}</p>
	</section>
{/if}

<section class="card">
	<button class="secondary" onclick={demo}>{COPY.welcome.demo}</button>
	<p class="muted small center">{COPY.welcome.demoNote}</p>
</section>

<p class="hint"><a href="/privacy">{COPY.welcome.privacy}</a></p>
