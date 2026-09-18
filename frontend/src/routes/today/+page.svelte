<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona, getEquipment, getNow, getTaste, setVote, getProfile, type Taste, type Vote } from '$lib/api';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Latency from '$lib/Latency.svelte';
	import DayCard from '$lib/DayCard.svelte';

	let data = $state<any>(null);
	let err = $state<number | string>('');
	let overridden = $state(false);
	let taste = $state<Taste>({});
	let said = $state('');
	const whyOpen = typeof location !== 'undefined' && location.hash === '#why';

	async function load() {
		const p = getPersona();
		try {
			taste = getTaste(p);
			data = await api.today(p, { at: getNow(), equipment: getEquipment(p) ?? undefined, override_sleep: overridden, taste, profile: getProfile(p) });
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
	function vote(id: string, v: Vote | null) {
		taste = setVote(getPersona(), id, v);
		said = v === 'more' ? COPY.day.votedMore : v === 'less' ? COPY.day.votedLess : COPY.day.voteCleared;
		load();
	}

	const cards = $derived<any[]>(data?.cards ?? []);
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

	{#each cards as card (card.daypart)}
		<DayCard {card} {whyOpen} overridden={overridden && card.status === 'live'} {taste} onoverride={override} onvote={vote} />
	{/each}
{/if}
