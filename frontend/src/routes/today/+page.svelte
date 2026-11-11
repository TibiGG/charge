<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, getPersona, getEquipment, getNow, getTaste, getProfile, vote as sendVote, skip as sendSkip, getSkips, ME, type Taste, type Vote } from '$lib/api';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Latency from '$lib/Latency.svelte';
	import DayCard from '$lib/DayCard.svelte';
	import SourceChip from '$lib/SourceChip.svelte';
	import { getHealth } from '$lib/health';

	let data = $state<any>(null);
	let err = $state<number | string>('');
	let overridden = $state(false);
	let taste = $state<Taste>({});
	let said = $state('');
	const whyOpen = typeof location !== 'undefined' && location.hash === '#why';

	async function load() {
		const p = getPersona();
		try {
			if (p !== ME) taste = getTaste(p);
			data = await api.today(p, { at: getNow(), equipment: getEquipment(p) ?? undefined, override_sleep: overridden, taste, profile: getProfile(p) });
			if (p === ME) { taste = data.taste ?? {}; skipped = data.skipped ?? []; } else skipped = getSkips(p);
			err = '';
		} catch (e: any) {
			err = e.status ?? 'offline';
		}
	}
	onMount(load);

	// "Give me the harder one instead": the person overrules us on mixed evidence. Their call.
	function override(on: boolean) {
		overridden = on;
		load();
	}

	// A vote is the person's argument for or against one activity. We re-rank with it.
	async function vote(id: string, v: Vote | null) {
		taste = await sendVote(getPersona(), id, v, taste);
		said = v === 'more' ? COPY.day.votedMore : v === 'less' ? COPY.day.votedLess : COPY.day.voteCleared;
		load();
	}

	// "Something else": they don't fancy it. That idea is off the table until tomorrow.
	let skipped = $state<string[]>([]);
	async function skip(id: string) {
		await sendSkip(getPersona(), id);
		said = COPY.today.skipped;
		load();
	}
	async function unskip() {
		const p = getPersona();
		if (p === ME) return;
		await sendSkip(p, null);
		said = '';
		load();
	}

	// What they did with the live idea: it teaches Charge what they like.
	function feedback(id: string, signal: 'planned' | 'not_today') {
		if (getPersona() === ME) api.feedback(id, signal).catch(() => {});
	}

	// A question in place of a longer form (backend/app/learn.py). One at a time.
	async function reply(id: string, value: string) {
		if (value === 'change') return goto('/user#health');
		try {
			await api.answer(id, value);
			said = COPY.learn.thanks;
			load();
		} catch { said = COPY.welcome.failed; }
	}

	const cards = $derived<any[]>(data?.cards ?? []);
	const check = $derived(data?.health?.check_first);
	const ask = $derived(data?.ask?.[0]);
	const noHealth = $derived(typeof window !== 'undefined' && data
		&& (getPersona() === ME ? !data.health?.done : !getHealth(getPersona())));
	const liveCard = $derived(cards.find((c) => c.status === 'live'));
	const lateNight = $derived(data && !liveCard && cards.every((c) => c.status === 'past'));
	const sayAll = $derived(liveCard?.text?.read_aloud
		?? cards.map((c) => `${c.label}. ${c.text?.preview ?? ''}`).join(' '));
</script>

{#if err === 409}
	<section class="card"><p>{COPY.today.noWatch}</p><a class="primary" href="/">{COPY.today.back}</a></section>
{:else if err}
	<section class="card"><p>{COPY.offline}</p><button class="secondary" onclick={load}>{COPY.day.tryAgain}</button></section>
{:else if !data}
	<p class="loading" aria-live="polite">{COPY.day.loading}</p>
{:else}
	<section class="hero">
		<div class="hero-row">
			<h1>{COPY.day.title}</h1>
			<Latency clientMs={data.clientMs} timings={data.timings_ms} />
		</div>
		<p class="lede">{lateNight ? COPY.dayparts.lateNight : COPY.day.intro}</p>
		<Speak text={sayAll} />
	</section>
	{#if said}<p class="done" role="status">{said}</p>{/if}
	{#if check}
		<aside class="card mixed" aria-label={check.title}>
			<h2>{check.title}</h2>
			<p>{check.body}</p>
			<SourceChip source={check.source} id={check.source_id} />
			<p><a href="/user#health">{COPY.health.edit}</a></p>
		</aside>
	{:else if data.health?.readiness === 'gentle'}
		<p class="notice">{COPY.health.gentle} <a href="/user#health">{COPY.health.edit}</a></p>
	{:else if noHealth}
		<p class="notice">{COPY.health.notDone} <a href="/user#health">{COPY.health.doIt}</a></p>
	{/if}
	{#if ask}
		<aside class="card stack" aria-label={COPY.learn.asksTitle}>
			<p><strong>{ask.text}</strong></p>
			{#if ask.note}<p class="muted">{ask.note}</p>{/if}
			{#if ask.source}<SourceChip source={ask.source} id={ask.source_id} />{/if}
			<div class="votes">
				{#each ask.options as o}<button class="chip vote" onclick={() => reply(ask.id, o.value)}>{o.label}</button>{/each}
			</div>
		</aside>
	{/if}

	{#each cards as card (card.daypart)}
		<DayCard {card} {whyOpen} overridden={overridden && card.status === 'live'} {taste} onoverride={override} onvote={vote} onskip={skip} onfeedback={feedback} />
	{/each}
	{#if skipped.length && getPersona() !== ME}<p class="hint"><button class="link" onclick={unskip}>{COPY.today.undoSkip}</button></p>{/if}
{/if}
