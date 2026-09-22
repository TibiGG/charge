<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { api, getPersona, setPersona } from '$lib/api';
	import { isDemo, setDemo, signedIn, signOut, refresh } from '$lib/auth';
	import { COPY } from '$lib/copy';

	let { children } = $props();
	let personas = $state<any[]>([]);
	let persona = $state('margaret');
	let demo = $state(false);
	let ready = $state(false);

	// Open to anyone. Everything else needs an account, or the demo.
	const PUBLIC = ['/welcome', '/privacy'];

	async function gate(path: string) {
		demo = isDemo();
		if (demo) {
			persona = getPersona();
			if (!personas.length) {
				try { personas = Object.values(await api.personas()).filter((x: any) => x?.id); } catch {}
			}
			ready = true;
			return;
		}
		if (!signedIn() || !(await refresh())) {
			ready = PUBLIC.includes(path);
			if (!ready) await goto('/welcome', { replaceState: true }).then(() => (ready = true));
			return;
		}
		if (path !== '/start' && !PUBLIC.includes(path)) {
			try {
				const me = await api.me();
				if (!me.consent || !me.profile_ready) {
					await goto('/start', { replaceState: true });
				}
			} catch (e: any) {
				if (e.status === 401) { signOut(); await goto('/welcome', { replaceState: true }); }
			}
		}
		ready = true;
	}

	onMount(() => { gate(page.url.pathname); });
	let last = '';
	$effect(() => {
		const path = page.url.pathname;
		if (last && path !== last) gate(path);
		last = path;
	});

	function change(e: Event) {
		setPersona((e.target as HTMLSelectElement).value);
		location.href = `${location.pathname}?p=${(e.target as HTMLSelectElement).value}`;
	}
	function leaveDemo() {
		setDemo(false);
		location.href = '/welcome';
	}
	const bare = $derived(!demo && (PUBLIC.includes(page.url.pathname) || page.url.pathname === '/start'));
</script>

<svelte:head><title>{COPY.appName}</title></svelte:head>

<header class="top">
	<a class="brand" href="/">⚡ {COPY.appName}</a>
	{#if !bare}
		<nav aria-label="Main">
			<a href="/" aria-current={page.url.pathname === '/' ? 'page' : undefined}>{COPY.nav.home}</a>
			<a href="/today" aria-current={page.url.pathname === '/today' ? 'page' : undefined}>{COPY.nav.today}</a>
			<a href="/activity" aria-current={page.url.pathname === '/activity' ? 'page' : undefined}>{COPY.nav.activity}</a>
			<a href="/user" aria-current={page.url.pathname === '/user' ? 'page' : undefined}>{COPY.nav.user}</a>
			<!-- Ask tab disabled for now; the /ask route and its API are kept. -->
		</nav>
	{/if}
	{#if demo}
		<label class="persona">
			<span class="sr-only">Demo person</span>
			<select value={persona} onchange={change}>
				{#each personas as p}<option value={p.id}>{p.name}{p.watch_connected ? `, ${p.age}` : ' (no watch)'}</option>{/each}
			</select>
		</label>
	{/if}
</header>

{#if demo}
	<p class="demo-banner" role="note">{COPY.demo.banner} <button class="link" onclick={leaveDemo}>{COPY.demo.exit}</button></p>
{/if}

<main>
	{#if ready}{@render children()}{:else}<p class="loading">…</p>{/if}
</main>
