<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona, getProfile, setProfile, setEquipment, tierOf, type Kit, type GymWindow } from '$lib/api';
	import { COPY } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Icon from '$lib/Icon.svelte';

	// Everything here is sent with every plan and becomes facts in the logic program
	// (age/1, habit/2, has_item/3, gym_window/3). Kept in this browser only.
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
		const mine = getProfile(persona);
		age = mine.age ?? b.age;
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

	function save() {
		const clean: Kit = {
			home: kit.home,
			gym: kit.gym ? { items: kit.gym.items, windows: kit.gym.windows.filter((w) => w.from < w.to) } : null
		};
		setProfile(persona, { age, habits, kit: clean });
		setEquipment(persona, tierOf(clean));
		saved = true;
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
		<label class="field">{COPY.user.age}
			<input type="number" min="18" max="110" bind:value={age} oninput={touched} />
		</label>
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

	{#if saved}<p class="done" role="status">{COPY.user.saved}</p>{/if}
	<button class="primary" onclick={save}>{COPY.user.save}</button>
	<p class="hint"><button class="link" onclick={reset}>{COPY.user.reset}</button> · <a href="/today">{COPY.user.seeDay}</a></p>
{/if}
