<script lang="ts">
	import { api } from './api';
	import { COPY } from './copy';
	import Icon from './Icon.svelte';

	let { ondone }: { ondone?: () => void } = $props();

	let stage = $state<'' | 'reading' | 'saving' | 'done' | 'error'>('');
	let result = $state<any>(null);
	let key = $state('');
	let copied = $state(false);
	let err = $state('');

	async function upload(e: Event) {
		const f = (e.target as HTMLInputElement).files?.[0];
		if (!f) return;
		stage = 'reading'; err = '';
		try {
			const { job } = await api.importHealth(f);
			for (;;) {
				await new Promise((r) => setTimeout(r, 1500));
				const s = await api.importStatus(job);
				stage = s.stage;
				if (s.stage === 'done') { result = s; ondone?.(); break; }
				if (s.stage === 'error') break;
			}
		} catch { stage = 'error'; }
	}

	async function makeKey() {
		try { key = (await api.syncToken()).token; copied = false; } catch { err = COPY.welcome.failed; }
	}
	async function copy(text: string) {
		try { await navigator.clipboard.writeText(text); copied = true; } catch {}
	}
</script>

<section class="card" id="watch">
	<h2><Icon name="watch" size={24} /> {COPY.watch.exportTitle}</h2>
	<ol class="steps">
		<li>{COPY.watch.exportStep1}</li>
		<li>{COPY.watch.exportStep2}</li>
		<li>{COPY.watch.exportStep3}</li>
	</ol>
	{#if stage === 'reading' || stage === 'saving'}
		<p class="loading" aria-live="polite">{stage === 'reading' ? COPY.watch.reading : COPY.watch.saving}</p>
	{:else}
		<label class="primary file-btn">
			{COPY.watch.exportButton}
			<input type="file" accept=".zip,.xml" onchange={upload} />
		</label>
	{/if}
	{#if stage === 'done'}<p class="done" role="status">{COPY.watch.imported} {result?.new ?? 0}</p>{/if}
	{#if stage === 'error'}<p class="error" role="alert">{COPY.watch.failed}</p>{/if}
</section>

<section class="card">
	<h2>{COPY.watch.shortcutTitle}</h2>
	<p>{COPY.watch.shortcutBody}</p>
	{#if key}
		<p class="notice">{COPY.watch.tokenOnce}</p>
		<div class="token"><code>{key}</code><button class="secondary" onclick={() => copy(key)}>{copied ? COPY.watch.copied : COPY.watch.copy}</button></div>
	{/if}
	<button class="secondary" onclick={makeKey}>{key ? COPY.watch.newToken : COPY.watch.makeToken}</button>
	{#if err}<p class="error" role="alert">{err}</p>{/if}
	<details>
		<summary>{COPY.watch.shortcutSteps}</summary>
		<ol class="steps">
			<li>{COPY.watch.step1}</li>
			<li>{COPY.watch.step2}</li>
			<li>{COPY.watch.step3}</li>
			<li>{COPY.watch.step4}</li>
			<li>{COPY.watch.step5}</li>
			<li>{COPY.watch.step6}</li>
		</ol>
		<p><strong>{COPY.watch.url}:</strong></p>
		<div class="token"><code>{api.syncUrl()}</code><button class="secondary" onclick={() => copy(api.syncUrl())}>{COPY.watch.copy}</button></div>
	</details>
	<p class="muted">{COPY.watch.manual} <a href="/activity">{COPY.watch.addByHand}</a></p>
</section>
