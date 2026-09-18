<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona } from '$lib/api';
	import { COPY } from '$lib/copy';
	import Latency from '$lib/Latency.svelte';
	import SourceChip from '$lib/SourceChip.svelte';
	import Speak from '$lib/Speak.svelte';
	import Icon from '$lib/Icon.svelte';

	let text = $state('');
	let res = $state<any>(null);
	let busy = $state(false);

	onMount(() => {
		const q = new URLSearchParams(location.search).get('q');
		if (q) send(q);
	});

	async function send(q?: string) {
		if (q) text = q;
		if (!text.trim()) return;
		busy = true;
		try { res = await api.ask(text, getPersona()); } finally { busy = false; }
	}
</script>

<section class="card">
	<h1>{COPY.ask.title}</h1>
	<p>{COPY.ask.intro}</p>
	<form onsubmit={(e) => { e.preventDefault(); send(); }}>
		<label class="sr-only" for="q">{COPY.ask.placeholder}</label>
		<textarea id="q" rows="3" placeholder={COPY.ask.placeholder} bind:value={text}></textarea>
		<button class="primary" disabled={busy}>{COPY.ask.send}</button>
	</form>
	<p class="muted">{COPY.ask.examplesTitle}</p>
	<div class="chips">
		{#each COPY.ask.examples as ex}<button class="chip" onclick={() => send(ex)}>{ex}</button>{/each}
	</div>
</section>

{#if res?.refusal}
	<section class="card refusal" role="alert">
		<div class="hero-row"><h2>{COPY.ask.refusalTitle}</h2><Latency clientMs={res.clientMs} timings={res.timings_ms} /></div>
		<p>{COPY.ask.refusalBody}</p>
		<p><strong>{COPY.ask.refusalCta}</strong></p>
		<a class="primary" href="tel:"><Icon name="phone" size={22} /> {COPY.ask.refusalButton}</a>
		<p class="safety"><em>{COPY.ask.safety}</em></p>
		<Speak text={`${COPY.ask.refusalTitle} ${COPY.ask.refusalBody} ${COPY.ask.refusalCta} ${COPY.ask.safety}`} />
	</section>
{:else if res?.answer}
	<section class="card">
		<div class="hero-row"><h2>{res.answer.title}</h2><Latency clientMs={res.clientMs} timings={res.timings_ms} /></div>
		{#each res.answer.lines as l}<p>{l}</p>{/each}
		{#if res.answer.source}<SourceChip source={res.answer.source} id={res.answer.source_id} />{/if}
		<Speak text={res.answer.lines.join(' ')} />
		<a class="primary" href={res.answer.cta === COPY.ask.refusalButton ? 'tel:' : '/today'}>{res.answer.cta}</a>
	</section>
{/if}
