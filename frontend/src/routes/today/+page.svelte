<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona } from '$lib/api';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Latency from '$lib/Latency.svelte';
	import Why from '$lib/Why.svelte';
	import Meaning from '$lib/Meaning.svelte';
	import Icon from '$lib/Icon.svelte';

	let data = $state<any>(null);
	let err = $state<number | string>('');
	let added = $state(false);
	let skipped = $state(false);
	let showSeated = $state(false);
	const whyOpen = typeof location !== 'undefined' && location.hash === '#why';

	onMount(async () => {
		try { data = await api.today(getPersona()); } catch (e: any) { err = e.status ?? String(e); }
	});

	const rec = $derived(data?.recommendation);
	const video = $derived(rec ? (showSeated && rec.video.seated_alternative ? rec.video.seated_alternative : rec.video) : null);

	function ics() {
		const s = rec.slot;
		const f = (x: string) => x.replace(/[-:]/g, '').slice(0, 15);
		const body = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Charge//EN', 'BEGIN:VEVENT',
			`UID:${Date.now()}@charge`, `DTSTART:${f(s.start)}`, `DTEND:${f(s.end)}`,
			`SUMMARY:${rec.name}`, `DESCRIPTION:${rec.video.url}`, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
		const a = document.createElement('a');
		a.href = URL.createObjectURL(new Blob([body], { type: 'text/calendar' }));
		a.download = 'charge.ics';
		a.click();
		added = true;
	}
</script>

{#if err === 409}
	<section class="card"><p>{COPY.today.noWatch}</p><a class="primary" href="/">{COPY.today.back}</a></section>
{:else if err}
	<p class="card">Sorry, something went wrong. {err}</p>
{:else if !rec}
	<p class="loading" aria-live="polite">{COPY.today.loading}</p>
{:else}
	<article class="card today">
		<div class="hero-row">
			<p class="eyebrow">{COPY.today.title}</p>
			<Latency clientMs={data.clientMs} timings={data.timings_ms} />
		</div>
		<h1>{rec.text.headline}</h1>
		<p class="meta"><Icon name="calendar" size={22} /> {rec.text.how_long} {rec.text.when}</p>
		<div class="batt-tags">
			{#each rec.batteries as b}<span class="tag"><Icon name={b} size={18} /> {COPY.batteries[b as keyof typeof COPY.batteries].label}</span>{/each}
		</div>

		<div class="video">
			<iframe src={video.embed_url} title={video.title} loading="lazy"
				allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
		</div>
		<p class="muted">{COPY.today.video}: <em>{video.title}</em> · {video.channel} · {video.duration_min} min</p>
		{#if rec.video.seated_alternative}
			<button class="link" onclick={() => (showSeated = !showSeated)}>{showSeated ? rec.video.title : COPY.today.seated}</button>
		{/if}

		<div class="confidence band-{rec.confidence.key}">
			<h2>{COPY.today.howSure}</h2>
			<p>{rec.text.confidence}{#if rec.p != null} <span class="prob">({rec.p.toFixed(2)})</span>{/if}</p>
			{#if data.mode === 'quick'}<p>{COPY.today.quick}</p>{/if}
			{#if rec.text.genetic_frame}<p class="genetic-frame">{rec.text.genetic_frame}</p>{/if}
			<Meaning>
				<p>We add up every reason that points to this idea. Each reason has its own weight. The number is how much they add up to, from 0 to 1.</p>
			</Meaning>
		</div>

		<Speak text={rec.text.read_aloud} />

		{#if added}
			<p class="done" role="status">{COPY.today.added}</p>
		{:else if skipped}
			<p class="done" role="status">{COPY.today.notTodayDone}</p>
		{:else}
			<button class="primary" onclick={ics}>{COPY.today.addToCalendar}</button>
			<button class="secondary" onclick={() => (skipped = true)}>{COPY.today.notToday}</button>
		{/if}
	</article>

	<details class="card whybox" id="why" open={whyOpen}>
		<summary><h2>{COPY.today.why}</h2></summary>
		<h3>{COPY.today.whyTitle}</h3>
		<Why nodes={rec.derivation} sources={rec.sources} />
		<p class="howsure"><strong>{COPY.today.howSure}</strong> {rec.text.confidence}{#if rec.p != null} <em>({rec.p.toFixed(2)})</em>{/if}</p>

		{#if rec.proofs?.length}
			<details class="meaning proofs">
				<summary>{COPY.today.proofTitle}</summary>
				<p>{COPY.today.proofIntro}</p>
				<ol class="mono">
					{#each rec.proofs as pr}
						<li><code>{pr.uses.join('  ∧  ')}{#if pr.excludes.length}  ∧ ¬({pr.excludes.join(', ')}){/if}</code> <span class="prob">{pr.p}</span></li>
					{/each}
				</ol>
			</details>
		{/if}

		{#if rec.alternatives?.length}
			<h3>{COPY.today.otherIdeas}</h3>
			<ul>{#each rec.alternatives as a}<li>{a.name} <span class="prob">({a.p.toFixed(2)})</span></li>{/each}</ul>
		{/if}
	</details>
{/if}
