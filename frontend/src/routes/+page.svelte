<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona } from '$lib/api';
	import { COPY, type BatteryId } from '$lib/copy';
	import Vial from '$lib/Vial.svelte';
	import Speak from '$lib/Speak.svelte';
	import SourceChip from '$lib/SourceChip.svelte';
	import Latency from '$lib/Latency.svelte';
	import Meaning from '$lib/Meaning.svelte';
	import Icon from '$lib/Icon.svelte';

	let data = $state<any>(null);
	let open = $state<any>(null);
	let persona = $state('margaret');
	let err = $state('');
	let uploading = $state(false);
	let dialog: HTMLDialogElement | undefined = $state();

	async function load() {
		try { data = await api.batteries(persona); } catch (e) { err = String(e); }
	}
	onMount(() => {
		persona = getPersona();
		load();
		// Live watch samples: poll gently so a tap on the watch fills the vial on screen.
		const t = setInterval(load, 3000);
		return () => clearInterval(t);
	});

	function show(b: any) { open = b; dialog?.showModal(); }

	async function upload(e: Event) {
		const f = (e.target as HTMLInputElement).files?.[0];
		if (!f) return;
		uploading = true;
		try {
			const r = await api.uploadHealth(f);
			data = { ...data, ...r, persona: { ...data.persona, watch_connected: true } };
		} catch (e) { err = String(e); }
		uploading = false;
	}

	const sayAll = $derived(data ? [COPY.tagline,
		...data.batteries.map((b: any) => `${COPY.batteries[b.id as BatteryId].label}: ${COPY.bands[b.band.key as keyof typeof COPY.bands]}.`),
		COPY.noStreak].join(' ') : '');
</script>

{#if err}<p class="card">Sorry, something went wrong. {err}</p>{/if}

{#if data && !data.persona.watch_connected}
	<section class="card onboarding">
		<Icon name="watch" size={48} />
		<h1>{COPY.onboarding.title}</h1>
		<p>{COPY.onboarding.body}</p>
		<ol class="steps">
			<li>{COPY.onboarding.step1}</li>
			<li>{COPY.onboarding.step2}</li>
			<li>{COPY.onboarding.step3}</li>
		</ol>
		<label class="primary file-btn">
			{uploading ? COPY.onboarding.working : COPY.onboarding.button}
			<input type="file" accept=".zip,.xml" onchange={upload} />
		</label>
	</section>
{:else if data}
	<section class="hero">
		<div class="hero-row">
			<h1>{COPY.tagline}</h1>
			<Latency clientMs={data.clientMs} timings={data.timings_ms} />
		</div>
		<p class="lede">{COPY.noStreak}</p>
		<Speak text={sayAll} />
	</section>

	<section class="vials" aria-label="Your five batteries">
		{#each data.batteries as b}
			<Vial {b} emptiest={b.id === data.emptiest} onopen={() => show(b)} />
		{/each}
	</section>
	<p class="hint">{COPY.tapVial}</p>

	<a class="primary" href="/today">{COPY.primaryToday}</a>
{:else}
	<p class="loading">…</p>
{/if}

<dialog bind:this={dialog} class="sheet" onclose={() => (open = null)}>
	{#if open}
		{@const c = COPY.batteries[open.id as BatteryId]}
		<div class="sheet-head">
			<Icon name={open.id} size={36} />
			<h2>{c.label} · <span class="state-{open.band.key}">{COPY.bands[open.band.key as keyof typeof COPY.bands]}</span></h2>
		</div>
		<h3>{COPY.sheet.whatThisIs}</h3>
		<p>{c.what}</p>
		<Meaning><p>{c.examples}</p></Meaning>
		<h3>{COPY.sheet.whereYouAre}</h3>
		<p>{open.said}</p>
		<p class="muted">{COPY.sheet.lastWeek} {open.previous_value} {open.unit.replace(' a week', '')}.</p>
		<h3>{COPY.sheet.whatPeopleAimFor}</h3>
		<p>{open.target} {open.unit}.</p>
		<SourceChip source={open.source} id={open.source_id} />
		{#if open.low_confidence}<p class="weak">{COPY.sheet.weakSource}</p>{/if}
		<Speak text={`${c.label}. ${c.what} ${open.said}`} />
		<form method="dialog"><button class="primary">{COPY.sheet.close}</button></form>
	{/if}
</dialog>
