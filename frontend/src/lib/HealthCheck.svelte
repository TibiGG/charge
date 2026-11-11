<script lang="ts">
	import { onMount } from 'svelte';
	import { COPY } from './copy';
	import { api, ME } from './api';
	import { CONDITIONS, EMPTY, SCREEN, anyYes, clearHealth, getHealth, readiness, setHealth, type Health } from './health';

	// The Health check. Signed in: saved in their sealed vault. Demo: kept in this browser.
	let { persona, onsaved }: { persona: string; onsaved?: () => void } = $props();

	let h = $state<Health>(structuredClone(EMPTY));
	let had = $state(false);
	let saved = $state(false);
	let gone = $state(false);
	let showReport = $state(false);
	let err = $state('');
	let busy = $state(false);

	onMount(async () => {
		let got: Health | null = null;
		if (persona === ME) {
			try { got = (await api.health()).health; } catch { err = COPY.offline; }
		} else got = getHealth(persona);
		had = !!got;
		if (got) {
			h = { ...structuredClone(EMPTY), ...got };
			showReport = !!got.report;
		}
	});

	const level = $derived(readiness(h));
	const touched = () => { saved = false; gone = false; };
	const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

	async function save(e: Event) {
		e.preventDefault();
		const clean: Health = $state.snapshot(h);
		delete clean.updated;
		if (!anyYes(clean)) clean.cleared = false;
		if (!showReport || (!clean.report?.bones && !clean.report?.heart)) clean.report = null;
		busy = true; err = '';
		try {
			if (persona === ME) await api.saveHealth(clean);
			else setHealth(persona, clean);
			had = saved = true;
			onsaved?.();
		} catch { err = COPY.welcome.failed; }
		busy = false;
	}
	async function clear() {
		try {
			if (persona === ME) await api.saveHealth(null);
			else clearHealth(persona);
		} catch { err = COPY.welcome.failed; return; }
		h = structuredClone(EMPTY);
		showReport = had = saved = false;
		gone = true;
	}
	function openReport() {
		showReport = true;
		h.report ??= { bones: '', heart: '', variants: [] };
	}
</script>

<form class="card user-form health" onsubmit={save}>
	<p class="notice">{persona === ME ? COPY.health.private : COPY.health.privateDemo}</p>

	<fieldset>
		<legend>{COPY.health.screenTitle}</legend>
		<p class="muted">{COPY.health.screenHint}</p>
		{#each SCREEN as k}
			<label class="check"><input type="checkbox" bind:checked={h.screen[k]} onchange={touched} /> {COPY.health.screen[k]}</label>
		{/each}
		{#if anyYes(h)}
			<label class="check cleared"><input type="checkbox" bind:checked={h.cleared} onchange={touched} /> <strong>{COPY.health.cleared}</strong></label>
			<p class="muted small">{COPY.health.clearedHint}</p>
		{/if}
	</fieldset>

	<fieldset>
		<legend>{COPY.health.moreTitle}</legend>
		<p class="muted">{COPY.health.moreHint}</p>
		{#each CONDITIONS as k}
			<label class="check"><input type="checkbox" checked={h.conditions.includes(k)}
				onchange={() => { h.conditions = toggle(h.conditions, k); touched(); }} /> {COPY.health.conditions[k]}</label>
		{/each}
		<label class="check"><input type="checkbox" bind:checked={h.easy_joints} onchange={touched} /> {COPY.health.joints}</label>
		<label class="field">{COPY.health.menopause}
			<select bind:value={h.menopause} onchange={touched}>
				{#each Object.entries(COPY.start.menoOptions) as [k, v]}<option value={k}>{v}</option>{/each}
			</select>
		</label>
	</fieldset>

	<fieldset>
		<legend>{COPY.health.reportTitle}</legend>
		<p class="muted">{COPY.health.reportBody}</p>
		{#if showReport && h.report}
			<label class="field">{COPY.health.bones}
				<select bind:value={h.report.bones} onchange={touched}>
					{#each Object.entries(COPY.health.bands) as [k, v]}<option value={k}>{v}</option>{/each}
				</select>
			</label>
			<label class="field">{COPY.health.heart}
				<select bind:value={h.report.heart} onchange={touched}>
					{#each Object.entries(COPY.health.bands) as [k, v]}<option value={k}>{v}</option>{/each}
				</select>
			</label>
			<p class="muted small">{COPY.health.genesTitle}:</p>
			{#each Object.entries(COPY.health.genes) as [k, v]}
				<label class="check"><input type="checkbox" checked={h.report.variants.includes(k)}
					onchange={() => { h.report!.variants = toggle(h.report!.variants, k); touched(); }} /> {v}</label>
			{/each}
		{:else}
			<button type="button" class="secondary" onclick={openReport}>{COPY.health.reportAdd}</button>
		{/if}
	</fieldset>

	<p class={level === 'ok' ? 'muted' : 'notice'} role="status">{COPY.health.outcome[level]}</p>
	<p class="muted small">{COPY.health.notAdvice}</p>
	{#if saved}<p class="done" role="status">{COPY.health.saved}</p>{/if}
	{#if gone}<p class="done" role="status">{COPY.health.gone}</p>{/if}
	{#if err}<p class="error" role="alert">{err}</p>{/if}
	<button class="primary" type="submit" disabled={busy}>{COPY.health.save}</button>
	{#if had}<button type="button" class="link" onclick={clear}>{COPY.health.clear}</button>{/if}
</form>
