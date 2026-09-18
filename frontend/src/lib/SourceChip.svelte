<script lang="ts">
	import { COPY } from './copy';
	let { source, id }: { source: any; id?: string } = $props();
	const grade = $derived(source?.evidence_grade as keyof typeof COPY.grades);
</script>

{#if source}
	<a class="source" href={source.url} target="_blank" rel="noopener" data-source-id={id} title={source.title}>
		<span class="grade grade-{grade}">{COPY.grades[grade]}</span>
		<span class="cite"><em>{source.publisher}</em>, {source.year}</span>
	</a>
{/if}
