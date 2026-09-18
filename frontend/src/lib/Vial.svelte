<script lang="ts">
	import { COPY, type BatteryId } from './copy';
	import Icon from './Icon.svelte';
	let { b, onopen, emptiest = false }: { b: any; onopen: () => void; emptiest?: boolean } = $props();
	const pct = $derived(Math.round(b.fill * 100));
	const label = $derived(COPY.batteries[b.id as BatteryId].label);
	const fmt = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(1));
</script>

<button class="vial-wrap" class:emptiest onclick={onopen}
	aria-label="{label}: {COPY.bands[b.band.key as keyof typeof COPY.bands]}. {b.said}{b.added > 0 ? ` ${COPY.includesYours}` : ''}">
	<span class="vial-icon"><Icon name={b.id} size={30} /></span>
	<span class="vial vial-{b.id}" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
		<span class="fill band-{b.band.key}" style="height: {Math.max(pct, 3)}%"></span>
		{#each [25, 50, 75] as tick}<span class="tick" style="bottom: {tick}%"></span>{/each}
	</span>
	<span class="vial-label">{label}</span>
	<span class="vial-state state-{b.band.key}">{COPY.bands[b.band.key as keyof typeof COPY.bands]}</span>
	<span class="vial-num">{fmt(b.value)} {COPY.of} {b.target}</span>
	{#if b.added > 0}<span class="vial-added">+{fmt(b.added)} {COPY.fromYou}</span>{/if}
</button>
