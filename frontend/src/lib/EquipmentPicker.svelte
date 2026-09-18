<script lang="ts">
	import { COPY } from './copy';
	import Icon from './Icon.svelte';
	let { value, onchange }: { value: string; onchange: (v: string) => void } = $props();
	const tiers = ['gym', 'home', 'none'] as const;
</script>

<fieldset class="equip">
	<legend>{COPY.equipment.title}</legend>
	<div class="equip-row">
		{#each tiers as t}
			<button type="button" class="equip-btn" aria-pressed={value === t} onclick={() => onchange(t)}>
				<Icon name={t} size={30} />
				<span>{COPY.equipment[t]}</span>
			</button>
		{/each}
	</div>
	<p class="muted small">{COPY.equipment.hint}</p>
</fieldset>
