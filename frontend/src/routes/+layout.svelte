<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { api, getPersona, setPersona } from '$lib/api';
	import { COPY } from '$lib/copy';

	let { children } = $props();
	let personas = $state<any[]>([]);
	let persona = $state('margaret');

	onMount(async () => {
		persona = getPersona();
		try { personas = await api.personas() as any; personas = Object.values(personas).filter((x: any) => x?.id); } catch {}
	});

	function change(e: Event) {
		setPersona((e.target as HTMLSelectElement).value);
		location.href = `${location.pathname}?p=${(e.target as HTMLSelectElement).value}`;
	}
</script>

<svelte:head><title>{COPY.appName}</title></svelte:head>

<header class="top">
	<a class="brand" href="/">⚡ {COPY.appName}</a>
	<nav aria-label="Main">
		<a href="/" aria-current={page.url.pathname === '/' ? 'page' : undefined}>{COPY.nav.home}</a>
		<a href="/today" aria-current={page.url.pathname === '/today' ? 'page' : undefined}>{COPY.nav.today}</a>
		<a href="/ask" aria-current={page.url.pathname === '/ask' ? 'page' : undefined}>{COPY.nav.ask}</a>
		<a href="/user" aria-current={page.url.pathname === '/user' ? 'page' : undefined}>{COPY.nav.user}</a>
	</nav>
	<label class="persona">
		<span class="sr-only">Demo person</span>
		<select value={persona} onchange={change}>
			{#each personas as p}<option value={p.id}>{p.name}{p.watch_connected ? `, ${p.age}` : ' (no watch)'}</option>{/each}
		</select>
	</label>
</header>

<main>{@render children()}</main>
