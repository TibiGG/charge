<script lang="ts">
	import { env } from '$env/dynamic/public';
	import { COPY } from '$lib/copy';
	const contact = env.PUBLIC_CONTACT_EMAIL;
</script>

<section class="hero">
	<h1>{COPY.privacy.title}</h1>
	<p class="muted">{COPY.privacy.updated}</p>
</section>

<section class="card stack">
	{#each COPY.privacy.sections as [h, body]}
		<h2>{h}</h2>
		<p>{body}</p>
	{/each}
	{#if contact}<p>{COPY.privacy.contact} <a href="mailto:{contact}">{contact}</a>.</p>{/if}
</section>

<p class="hint"><a href="/" onclick={(e) => { if (history.length > 1) { e.preventDefault(); history.back(); } }}>{COPY.privacy.back}</a></p>
