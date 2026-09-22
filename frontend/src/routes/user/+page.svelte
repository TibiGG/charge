<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona, getProfile, setProfile, setEquipment, tierOf, ME, type Kit, type GymWindow } from '$lib/api';
	import { signOut } from '$lib/auth';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Icon from '$lib/Icon.svelte';
	import WatchConnect from '$lib/WatchConnect.svelte';

	// Everything here becomes facts in the logic program (age/1, habit/2, has_item/3,
	// gym_window/3). Signed in: stored on the server. Demo: kept in this browser.
	type Busy = { days: number[]; from: string; to: string; label: string };
	let routine = $state<{ day_start: string; day_end: string; busy: Busy[] }>({ day_start: '06:30', day_end: '22:00', busy: [] });
	let birthYear = $state<number | null>(null);
	let bupaDialog: HTMLDialogElement | undefined = $state();
	let confirmText = $state('');
	let gone = $state(false);
	let persona = $state('margaret');
	let base = $state<any>(null);
	let age = $state(0);
	let habits = $state<string[]>([]);
	let kit = $state<Kit>({ home: [], gym: null });
	let err = $state('');
	let saved = $state(false);

	const HOME_ITEMS = ['mat', 'chair', 'dumbbells', 'band', 'bike'];
	const GYM_ITEMS = ['machines', 'dumbbells', 'bike', 'mat', 'band', 'pool'];
	const QUICK: GymWindow[] = [
		{ from: '06:30', to: '08:30', label: 'Before work' },
		{ from: '12:00', to: '13:30', label: 'Lunch break, gym near work' },
		{ from: '17:30', to: '19:30', label: 'After work' },
		{ from: '19:30', to: '21:30', label: 'Evenings, from home' }
	];

	function fill(b: any) {
		b = $state.snapshot(b);
		const mine = persona === ME ? {} as ReturnType<typeof getProfile> : getProfile(persona);
		age = mine.age ?? b.age;
		if (persona === ME) {
			birthYear = b.birth_year;
			routine = JSON.parse(JSON.stringify(b.routine ?? routine));
			routine.busy ??= [];
		}
		habits = [...(mine.habits ?? b.habits)];
		kit = JSON.parse(JSON.stringify(mine.kit ?? b.kit));
		if (kit.gym && !kit.gym.windows) kit.gym.windows = [];
	}

	onMount(async () => {
		persona = getPersona();
		try { base = await api.profile(persona); fill(base); } catch (e) { err = String(e); }
	});

	const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
	const touched = () => (saved = false);

	function setGym(on: boolean) {
		kit.gym = on ? { items: [...GYM_ITEMS], windows: [] } : null;
		touched();
	}
	function addWindow(w: GymWindow = { from: '12:00', to: '13:00', label: '' }) {
		if (!kit.gym) return;
		kit.gym.windows = [...kit.gym.windows, { ...w }];
		touched();
	}
	function removeWindow(i: number) {
		if (!kit.gym) return;
		kit.gym.windows = kit.gym.windows.filter((_, j) => j !== i);
		touched();
	}

	async function save() {
		const clean: Kit = {
			home: kit.home,
			gym: kit.gym ? { items: kit.gym.items, windows: kit.gym.windows.filter((w) => w.from < w.to) } : null
		};
		if (persona === ME) {
			try {
				base = await api.saveProfile({ birth_year: birthYear, habits, kit: clean,
					routine: { ...routine, busy: routine.busy.filter((b) => b.from < b.to && b.days.length) },
					timezone: Intl.DateTimeFormat().resolvedOptions().timeZone });
				err = '';
			} catch (e: any) { alertMsg = e.detail || COPY.welcome.failed; return; }
		} else setProfile(persona, { age, habits, kit: clean });
		setEquipment(persona, tierOf(clean));
		alertMsg = '';
		saved = true;
	}
	let alertMsg = $state('');

	function addBusy() {
		routine.busy = [...routine.busy, { days: [0, 1, 2, 3, 4], from: '09:00', to: '17:30', label: '' }];
		touched();
	}
	function toggleDay(b: Busy, d: number) {
		b.days = b.days.includes(d) ? b.days.filter((x) => x !== d) : [...b.days, d].sort();
		touched();
	}

	async function download() {
		const data = await api.exportData();
		const { clientMs: _c, ...rest } = data;
		const a = document.createElement('a');
		a.href = URL.createObjectURL(new Blob([JSON.stringify(rest, null, 1)], { type: 'application/json' }));
		a.download = 'charge-my-data.json';
		a.click();
	}
	async function erase() {
		if (confirmText !== 'DELETE') return;
		await api.deleteAccount();
		signOut();
		gone = true;
		setTimeout(() => (location.href = '/welcome'), 2000);
	}
	function leave() {
		signOut();
		location.href = '/welcome';
	}
	function reset() {
		setProfile(persona, {});
		fill(base);
		saved = true;
	}

	const sayAll = $derived(`${COPY.user.title}. ${COPY.user.intro}`);
</script>

{#if err}
	<section class="card"><p>{COPY.offline}</p></section>
{:else if !base}
	<p class="loading">…</p>
{:else}
	<section class="hero">
		<h1>{COPY.user.title}</h1>
		<p class="lede">{COPY.user.intro}</p>
		<Speak text={sayAll} />
	</section>

	<section class="card user-form">
		<h2>{COPY.user.you}</h2>
		<p><strong>{COPY.user.name}:</strong> {base.name}</p>
		{#if persona === ME}
			<label class="field">{COPY.start.birthYear}
				<input type="number" min="1900" max="2100" bind:value={birthYear} oninput={touched} />
			</label>
		{:else}
			<label class="field">{COPY.user.age}
				<input type="number" min="18" max="110" bind:value={age} oninput={touched} />
			</label>
		{/if}
		<fieldset>
			<legend>{COPY.user.habits}</legend>
			{#each base.habit_options as h}
				<label class="check"><input type="checkbox" checked={habits.includes(h)} onchange={() => { habits = toggle(habits, h); touched(); }} /> {h}</label>
			{/each}
		</fieldset>
	</section>

	<section class="card user-form">
		<h2><Icon name="home" size={24} /> {COPY.user.homeKit}</h2>
		<p class="muted">{COPY.user.homeHint}</p>
		{#each HOME_ITEMS as i}
			<label class="check"><input type="checkbox" checked={kit.home.includes(i)} onchange={() => { kit.home = toggle(kit.home, i); touched(); }} /> {base.items[i]}</label>
		{/each}
		<button class="link" onclick={() => { kit.home = []; touched(); }}>{COPY.user.noKit}</button>
	</section>

	<section class="card user-form">
		<h2><Icon name="gym" size={24} /> {COPY.user.gym}</h2>
		<label class="check"><input type="checkbox" checked={!!kit.gym} onchange={(e) => setGym((e.target as HTMLInputElement).checked)} /> {COPY.user.gymToggle}</label>
		{#if kit.gym}
			<fieldset>
				<legend>{COPY.user.gymKit}</legend>
				{#each GYM_ITEMS as i}
					<label class="check"><input type="checkbox" checked={kit.gym.items.includes(i)} onchange={() => { kit.gym!.items = toggle(kit.gym!.items, i); touched(); }} /> {base.items[i]}</label>
				{/each}
			</fieldset>

			<h3>{COPY.user.when}</h3>
			<p class="muted">{COPY.user.whenHint}</p>
			{#if !kit.gym.windows.length}<p class="notice">{COPY.user.noWindows}</p>{/if}
			<ul class="windows">
				{#each kit.gym.windows as w, i}
					<li class="window">
						<label>{COPY.user.from} <input type="time" bind:value={w.from} oninput={touched} /></label>
						<label>{COPY.user.to} <input type="time" bind:value={w.to} oninput={touched} /></label>
						<label class="grow">{COPY.user.label} <input type="text" maxlength="60" bind:value={w.label} oninput={touched} /></label>
						<button class="link" onclick={() => removeWindow(i)}>{COPY.user.remove}</button>
					</li>
				{/each}
			</ul>
			<button class="secondary" onclick={() => addWindow()}>{COPY.user.add}</button>
			<p class="muted small">{COPY.user.quick}:</p>
			<div class="votes">
				{#each QUICK as q}
					<button class="chip vote" onclick={() => addWindow(q)}>{q.label} · {q.from}–{q.to}</button>
				{/each}
			</div>
		{/if}
	</section>

	{#if persona === ME}
		<section class="card user-form">
			<h2><Icon name="calendar" size={24} /> {COPY.account.routineTitle}</h2>
			<p class="muted">{COPY.account.routineHint}</p>
			<div class="row2">
				<label class="field">{COPY.account.dayStart}<input type="time" bind:value={routine.day_start} oninput={touched} /></label>
				<label class="field">{COPY.account.dayEnd}<input type="time" bind:value={routine.day_end} oninput={touched} /></label>
			</div>
			<h3>{COPY.account.busy}</h3>
			<p class="muted">{COPY.account.busyHint}</p>
			<ul class="windows">
				{#each routine.busy as b, i}
					<li class="window">
						<div class="days">
							{#each COPY.account.days as d, j}
								<label><input type="checkbox" checked={b.days.includes(j)} onchange={() => toggleDay(b, j)} /> {d}</label>
							{/each}
						</div>
						<label>{COPY.user.from} <input type="time" bind:value={b.from} oninput={touched} /></label>
						<label>{COPY.user.to} <input type="time" bind:value={b.to} oninput={touched} /></label>
						<label class="grow">{COPY.user.label} <input type="text" maxlength="60" bind:value={b.label} oninput={touched} /></label>
						<button class="link" onclick={() => { routine.busy = routine.busy.filter((_, j) => j !== i); touched(); }}>{COPY.user.remove}</button>
					</li>
				{/each}
			</ul>
			<button class="secondary" onclick={addBusy}>{COPY.account.addBusy}</button>
		</section>
	{/if}

	{#if saved}<p class="done" role="status">{COPY.user.saved}</p>{/if}
	{#if alertMsg}<p class="error" role="alert">{alertMsg}</p>{/if}
	<button class="primary" onclick={save}>{COPY.user.save}</button>
	<p class="hint">{#if persona !== ME}<button class="link" onclick={reset}>{COPY.user.reset}</button> · {/if}<a href="/today">{COPY.user.seeDay}</a></p>

	{#if persona === ME}
		<WatchConnect />

		<section class="card stack">
			<h2>{COPY.account.bupaTitle}</h2>
			<p>{COPY.account.bupaBody}</p>
			<button class="secondary sso sso-bupa" onclick={() => bupaDialog?.showModal()}>
				<span class="sso-mark" aria-hidden="true">B</span>{COPY.account.bupaButton}
			</button>
		</section>

		<section class="card stack">
			<h2>{COPY.account.title}</h2>
			<p><strong>{COPY.account.email}:</strong> {base.email}</p>
			<button class="secondary" onclick={leave}>{COPY.account.signOut}</button>
		</section>

		<section class="card stack">
			<h2>{COPY.account.dataTitle}</h2>
			<button class="secondary" onclick={download}>{COPY.account.download}</button>
			<p><a href="/privacy">{COPY.welcome.privacy}</a></p>
			<h3>{COPY.account.deleteTitle}</h3>
			<p>{COPY.account.deleteBody}</p>
			<label class="field">{COPY.account.deleteConfirm}<input bind:value={confirmText} autocomplete="off" /></label>
			{#if gone}<p class="done" role="status">{COPY.account.deleted}</p>{/if}
			<button class="secondary danger" disabled={confirmText !== 'DELETE'} onclick={erase}>{COPY.account.deleteButton}</button>
		</section>

		<dialog bind:this={bupaDialog} class="sheet">
			<h2>{COPY.account.bupaTitle}</h2>
			<p>{COPY.account.bupaSoon}</p>
			<form method="dialog"><button class="primary">{COPY.account.ok}</button></form>
		</dialog>
	{/if}
{/if}
