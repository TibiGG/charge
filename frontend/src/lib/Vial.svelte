<script lang="ts">
	import { COPY, type BatteryId } from './copy';
	import Icon from './Icon.svelte';
	let { b, onopen, emptiest = false }: { b: any; onopen: () => void; emptiest?: boolean } = $props();
	import { onMount } from 'svelte';
	const pct = $derived(Math.round(b.fill * 100));
	// What their own logs / the watch sync added: drawn as a separate segment that grows in.
	const basePct = $derived(Math.max(0, Math.min(pct, Math.round(Math.min(1, (b.value - (b.added ?? 0)) / b.target) * 100))));
	const newPct = $derived(pct - basePct);
	let grown = $state(false);
	onMount(() => { setTimeout(() => (grown = true), 250); });
	const label = $derived(COPY.batteries[b.id as BatteryId].label);
	const fmt = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(1));
</script>

<button class="vial-wrap" class:emptiest onclick={onopen}
	aria-label="{label}: {COPY.bands[b.band.key as keyof typeof COPY.bands]}. {b.said}{b.added > 0 ? ` ${COPY.includesYours}` : ''}">
	<span class="vial-icon"><Icon name={b.id} size={30} /></span>
	<span class="vial vial-{b.id}" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
		<span class="fill band-{b.band.key}" style="height: {Math.max(basePct, newPct ? 0 : 3)}%"></span>
		{#if newPct > 0}
			<span class="fill fill-new" style="bottom: {basePct}%; height: {grown ? newPct : 0}%"></span>
		{/if}
		{#each [25, 50, 75] as tick}<span class="tick" style="bottom: {tick}%"></span>{/each}
	</span>
	<span class="vial-label">{label}</span>
	<span class="vial-state state-{b.band.key}">{COPY.bands[b.band.key as keyof typeof COPY.bands]}</span>
	<span class="vial-num">{fmt(b.value)} {COPY.of} {b.target}</span>
</button>
