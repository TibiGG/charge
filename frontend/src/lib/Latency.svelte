<script lang="ts">
	import { COPY } from './copy';
	let { clientMs, timings }: { clientMs?: number; timings?: Record<string, number> } = $props();
	const secs = $derived(clientMs == null ? null : clientMs < 1000 ? (clientMs / 1000).toFixed(2) : (clientMs / 1000).toFixed(1));
	const detail = $derived(
		timings ? Object.entries(timings).map(([k, v]) => `${k}: ${v}ms`).join('\n') : ''
	);
</script>

{#if secs}
	<span class="latency" title={detail} aria-label="{COPY.latency}: {secs} seconds">
		<span class="dot" aria-hidden="true"></span>{secs}s
	</span>
{/if}
