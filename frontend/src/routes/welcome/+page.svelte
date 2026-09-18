<script lang="ts">
	import { onMount } from 'svelte';
	import { getPersona } from '$lib/api';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Icon from '$lib/Icon.svelte';

	// Simulated on purpose: nothing is sent, no password is ever asked for.
	type State = { account?: string; wearable?: string };
	const ACCOUNTS: Record<string, string> = { bupa: 'Bupa', google: 'Google', email: 'email' };
	const WEARABLES = [
		{ id: 'apple', name: 'Apple Watch', mark: '⌚' },
		{ id: 'fitbit', name: 'Fitbit', mark: '◆' },
		{ id: 'garmin', name: 'Garmin', mark: '▲' },
		{ id: 'wearos', name: 'Google (Wear OS)', mark: '●' }
	];

	let persona = $state('margaret');
	let st = $state<State>({});
	let busy = $state<string | null>(null);
	let showEmail = $state(false);
	let email = $state('');

	const key = () => `onboard:${persona}`;
	onMount(() => {
		persona = getPersona();
		try { st = JSON.parse(localStorage.getItem(key()) ?? '{}'); } catch {}
	});
	function save() { try { localStorage.setItem(key(), JSON.stringify(st)); } catch {} }

	function fake(what: string, done: () => void) {
		busy = what;
		setTimeout(() => { done(); busy = null; save(); }, 1200);
	}
	const signIn = (how: string) => fake(how, () => (st = { ...st, account: how }));
	const connect = (id: string) => fake(id, () => (st = { ...st, wearable: id }));
	function reset() { st = {}; showEmail = false; email = ''; save(); }

	const wearableName = $derived(WEARABLES.find((w) => w.id === st.wearable)?.name);
	const sayAll = $derived(`${COPY.welcome.title}. ${COPY.welcome.intro}`);
</script>

<section class="hero">
	<h1>{COPY.welcome.title}</h1>
	<p class="lede">{COPY.welcome.intro}</p>
	<Speak text={sayAll} />
</section>

<section class="card onboard-step" class:done-step={st.account}>
	<h2>{COPY.welcome.step1}</h2>
	{#if st.account}
		<p class="done" role="status">✓ {COPY.welcome.signedIn} {COPY.welcome.signedInWith} {ACCOUNTS[st.account]}.</p>
	{:else if busy && busy in ACCOUNTS}
		<p class="loading" aria-live="polite">{COPY.welcome.signingIn}</p>
	{:else}
		<button class="primary sso sso-bupa" onclick={() => signIn('bupa')}><span class="sso-mark" aria-hidden="true">B</span>{COPY.welcome.bupa}</button>
		<button class="secondary sso" onclick={() => signIn('google')}><span class="sso-mark" aria-hidden="true">G</span>{COPY.welcome.google}</button>
		{#if showEmail}
			<form class="email-form" onsubmit={(e) => { e.preventDefault(); if (email.includes('@')) signIn('email'); }}>
				<label class="field">{COPY.welcome.emailLabel}<input type="email" required autocomplete="email" bind:value={email} /></label>
				<button class="secondary" type="submit">{COPY.welcome.emailGo}</button>
			</form>
		{:else}
			<button class="secondary sso" onclick={() => (showEmail = true)}><span class="sso-mark" aria-hidden="true">@</span>{COPY.welcome.email}</button>
		{/if}
	{/if}
</section>

<section class="card onboard-step" class:done-step={st.wearable} class:locked={!st.account}>
	<h2>{COPY.welcome.step2}</h2>
	{#if st.wearable}
		<p class="done" role="status">✓ {wearableName}: {COPY.welcome.connected} {COPY.welcome.found}</p>
	{:else if !st.account}
		<p class="muted">{COPY.welcome.step2Intro}</p>
	{:else}
		<p class="muted">{COPY.welcome.step2Intro}</p>
		<div class="wear-grid">
			{#each WEARABLES as w}
				<button class="equip-btn" disabled={!!busy} onclick={() => connect(w.id)}>
					<span class="wear-mark" aria-hidden="true">{w.mark}</span>
					<span>{w.name}</span>
					<span class="muted small">{busy === w.id ? COPY.welcome.connecting : COPY.welcome.connect}</span>
				</button>
			{/each}
		</div>
	{/if}
</section>

{#if st.account && st.wearable}
	<section class="card onboard-step done-step">
		<h2>{COPY.welcome.step3}</h2>
		<a class="secondary link-btn" href="/user"><Icon name="home" size={22} /> {COPY.welcome.kit}</a>
		<a class="primary" href="/">{COPY.welcome.go}</a>
	</section>
{/if}

<p class="hint"><button class="link" onclick={reset}>{COPY.welcome.startOver}</button></p>
<p class="muted small center">{COPY.welcome.demoNote}</p>
