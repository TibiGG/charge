<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { signOut } from '$lib/auth';
	import { COPY } from '$lib/copy';
	import { forgetKey, setUpNow, startAgain, unlockWithRecovery } from '$lib/vault';

	// Their data is sealed and this device doesn't hold the key: they bring it with their recovery key.
	let mode = $state<'wait' | 'locked' | 'setting'>('wait');
	let recovery = $state('');
	let confirmText = $state('');
	let lost = $state(false);
	let busy = $state(false);
	let err = $state('');

	onMount(async () => {
		try {
			const me = await api.me();
			if (me.vault === 'open') return goto('/', { replaceState: true });
			if (me.vault === 'none') {
				mode = 'setting';
				await setUpNow();
				return goto('/start', { replaceState: true });
			}
			forgetKey(); // whatever this device had doesn't open it
			mode = 'locked';
		} catch { err = COPY.offline; mode = 'locked'; }
	});

	async function open(e: Event) {
		e.preventDefault();
		busy = true; err = '';
		try {
			if (await unlockWithRecovery(recovery)) return goto('/', { replaceState: true });
			err = COPY.vault.unlockBad;
		} catch { err = COPY.welcome.failed; }
		busy = false;
	}

	async function again() {
		if (confirmText !== 'START AGAIN') return;
		busy = true; err = '';
		try {
			await startAgain();
			return goto('/start', { replaceState: true });
		} catch { err = COPY.welcome.failed; }
		busy = false;
	}

	function leave() {
		signOut();
		location.href = '/welcome';
	}
</script>

{#if mode === 'wait'}
	<p class="loading">…</p>
{:else if mode === 'setting'}
	<p class="loading" aria-live="polite">{COPY.vault.settingUp}</p>
{:else}
	<section class="hero"><h1>{COPY.vault.unlockTitle}</h1><p class="lede">{COPY.vault.unlockBody}</p></section>
	<form class="card stack" onsubmit={open}>
		<label class="field">{COPY.vault.unlockLabel}
			<input autocomplete="off" autocapitalize="characters" spellcheck="false" required bind:value={recovery}
				placeholder="XXXX-XXXX-XXXX-XXXX-XXXX" />
		</label>
		{#if err}<p class="error" role="alert">{err}</p>{/if}
		<button class="primary" type="submit" disabled={busy}>{COPY.vault.unlockGo}</button>
	</form>
	<p class="hint"><button class="link" onclick={() => (lost = !lost)}>{COPY.vault.lost}</button></p>
	{#if lost}
		<section class="card stack">
			<p>{COPY.vault.lostBody}</p>
			<label class="field">{COPY.vault.lostConfirm}<input bind:value={confirmText} autocomplete="off" /></label>
			<button class="secondary danger" disabled={confirmText !== 'START AGAIN' || busy} onclick={again}>{COPY.vault.lostButton}</button>
		</section>
	{/if}
	<p class="hint"><button class="link" onclick={leave}>{COPY.vault.signOut}</button></p>
{/if}
