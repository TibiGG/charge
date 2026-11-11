<script lang="ts">
	import { COPY } from './copy';

	// Shown once, right after we make it. We can't show it again: we never had it.
	let { value, ondone }: { value: string; ondone: () => void } = $props();
	let copied = $state(false);

	async function copy() {
		try { await navigator.clipboard.writeText(value); copied = true; } catch {}
	}
</script>

<section class="card stack">
	<h2>{COPY.vault.keyTitle}</h2>
	<p>{COPY.vault.keyBody}</p>
	<p>{COPY.vault.keyWhen}</p>
	<div class="token"><code class="recovery" aria-label={COPY.vault.unlockLabel}>{value}</code>
		<button class="secondary" onclick={copy}>{copied ? COPY.vault.copied : COPY.vault.copy}</button></div>
	<p class="notice">{COPY.vault.keyLost}</p>
	<button class="primary" onclick={ondone}>{COPY.vault.saved}</button>
</section>
