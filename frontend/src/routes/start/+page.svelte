<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { COPY } from '$lib/copy';
	import WatchConnect from '$lib/WatchConnect.svelte';

	// Three steps for a new account: agree how we use their data, tell us their age, bring in the watch.
	let me = $state<any>(null);
	let step = $state<'consent' | 'about' | 'watch'>('consent');
	let health = $state(false);
	let recs = $state(false);
	let birthYear = $state<number | null>(null);
	let sex = $state('unknown');
	let meno = $state('');
	let err = $state('');
	let busy = $state(false);
	const thisYear = new Date().getFullYear();

	onMount(async () => {
		try {
			me = await api.me();
			step = !me.consent ? 'consent' : !me.profile_ready ? 'about' : 'watch';
			if (me.consent && me.profile_ready && me.has_data) goto('/');
		} catch { err = COPY.offline; }
	});

	async function agree() {
		busy = true; err = '';
		try { await api.consent(me.consent_version); step = 'about'; } catch { err = COPY.welcome.failed; }
		busy = false;
	}

	async function about(e: Event) {
		e.preventDefault();
		if (!birthYear || thisYear - birthYear < 18 || thisYear - birthYear > 110) { err = COPY.start.adultsOnly; return; }
		busy = true; err = '';
		try {
			await api.saveProfile({ birth_year: birthYear, sex, menopause_status: meno,
				timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
			step = 'watch';
		} catch (e: any) { err = e.detail || COPY.welcome.failed; }
		busy = false;
	}
</script>

{#if !me && !err}
	<p class="loading">…</p>
{:else if step === 'consent'}
	<section class="hero"><h1>{COPY.start.title}</h1></section>
	<section class="card stack">
		<h2>{COPY.start.consentTitle}</h2>
		<p>{COPY.start.consentBody}</p>
		<label class="check"><input type="checkbox" bind:checked={health} /> {COPY.start.consentHealth}</label>
		<label class="check"><input type="checkbox" bind:checked={recs} /> {COPY.start.consentRecs}</label>
		<p><a href="/privacy" target="_blank">{COPY.start.readMore}</a></p>
		{#if err}<p class="error" role="alert">{err}</p>{/if}
		<button class="primary" disabled={!health || !recs || busy} onclick={agree}>{COPY.start.agree}</button>
	</section>
{:else if step === 'about'}
	<section class="hero"><h1>{COPY.start.aboutTitle}</h1><p class="lede">{COPY.start.aboutBody}</p></section>
	<form class="card stack" onsubmit={about}>
		<label class="field">{COPY.start.birthYear}
			<input type="number" inputmode="numeric" min={thisYear - 110} max={thisYear - 18} required bind:value={birthYear} />
		</label>
		<p class="muted small">{COPY.start.adultsOnly}</p>
		<label class="field">{COPY.start.sex}
			<select bind:value={sex}>
				{#each Object.entries(COPY.start.sexOptions) as [k, v]}<option value={k}>{v}</option>{/each}
			</select>
		</label>
		{#if sex === 'female'}
			<label class="field">{COPY.start.menopause}
				<select bind:value={meno}>
					{#each Object.entries(COPY.start.menoOptions) as [k, v]}<option value={k}>{v}</option>{/each}
				</select>
			</label>
		{/if}
		{#if err}<p class="error" role="alert">{err}</p>{/if}
		<button class="primary" type="submit" disabled={busy}>{COPY.start.next}</button>
	</form>
{:else}
	<section class="hero"><h1>{COPY.start.watchTitle}</h1><p class="lede">{COPY.start.watchBody}</p></section>
	<WatchConnect />
	<a class="primary" href="/">{COPY.start.done}</a>
	<p class="hint"><a href="/">{COPY.start.skip}</a></p>
{/if}
