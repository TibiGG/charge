<script lang="ts">
	import SourceChip from './SourceChip.svelte';
	import Why from './Why.svelte';
	import { COPY } from './copy';
	let { nodes, sources, depth = 0 }: { nodes: any[]; sources: Record<string, any>; depth?: number } = $props();
</script>

<ol class="why depth-{depth}">
	{#each nodes as n}
		<li class="why-node" class:genetic={n.genetic}>
			{#each n.facts ?? [] as f}
				{#if f.said}
					<p class="why-fact">{f.said}</p>
					{#if f.source_id}<SourceChip source={sources[f.source_id]} id={f.source_id} />{/if}
				{/if}
			{/each}
			{#if n.children?.length}
				<Why nodes={n.children} {sources} depth={depth + 1} />
			{/if}
			<p class="why-text"><strong>{n.text}</strong></p>
			{#if n.genetic}<p class="genetic-frame">{COPY.genetic}</p>{/if}
			{#if n.source_id}<SourceChip source={sources[n.source_id]} id={n.source_id} />{/if}
			{#if n.design_note}
				<details class="meaning"><summary>{COPY.today.productChoice}</summary><p>{n.design_note}</p></details>
			{/if}
		</li>
	{/each}
</ol>
