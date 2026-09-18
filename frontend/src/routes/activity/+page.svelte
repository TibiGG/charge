<script lang="ts">
	import { onMount } from 'svelte';
	import { api, getPersona, getLogs, setLogs, getSynced, setSynced, type ActivityLog } from '$lib/api';
	import { COPY, type BatteryId } from '$lib/copy';
	import Speak from '$lib/Speak.svelte';
	import Icon from '$lib/Icon.svelte';

	const ORDER: BatteryId[] = ['strength', 'cardio', 'peak', 'balance', 'mobility'];
	const CARDIO = new Set(['Walking', 'Running', 'Cycling', 'Swimming', 'Dance', 'HighIntensityIntervalTraining']);

	let persona = $state('margaret');
	let act = $state<any>(null);
	let now = $state<any>(null);      // batteries as they are
	let after = $state<any>(null);    // batteries if the draft is added
	let err = $state('');
	let syncing = $state(false);
	let justSaved = $state<any>(null); // before/after of the last save, for the demo

	// The draft
	let type = $state('TraditionalStrengthTraining');
	let when = $state('');
	let minutes = $state(30);
	let effort = $state<'easy' | 'moderate' | 'hard'>('moderate');
	let counts = $state<string[]>(['strength']);
	let note = $state('');

	function defaults(t: string, e: string): string[] {
		const base = [...(act?.types?.[t]?.counts ?? [])];
		if (CARDIO.has(t) && e === 'hard' && !base.includes('peak')) base.push('peak');
		if (e !== 'hard' && t !== 'HighIntensityIntervalTraining') return base.filter((c) => c !== 'peak');
		return base;
	}
	function pickType(t: string) { type = t; counts = defaults(t, effort); }
	function pickEffort(e: 'easy' | 'moderate' | 'hard') { effort = e; counts = defaults(type, e); }
	const toggle = (c: string) => (counts = counts.includes(c) ? counts.filter((x) => x !== c) : [...counts, c]);

	const draft = $derived<ActivityLog>({ id: 'draft', type, start: when, duration_min: Number(minutes) || 0, effort, counts, note });

	async function load() {
		try {
			[act, now] = await Promise.all([api.activity(persona), api.batteries(persona)]);
			if (!when) when = `${act.as_of}T${new Date().toTimeString().slice(0, 5)}`;
		} catch (e) { err = String(e); }
	}
	onMount(() => { persona = getPersona(); load(); });

	// Live preview: the real battery maths, with the draft added.
	let timer: ReturnType<typeof setTimeout>;
	$effect(() => {
		const d = draft;
		if (!act || !d.start || !d.duration_min) return;
		clearTimeout(timer);
		timer = setTimeout(async () => { try { after = await api.batteries(persona, [d]); } catch {} }, 150);
	});

	const byId = (b: any) => Object.fromEntries((b?.batteries ?? []).map((x: any) => [x.id, x]));
	const diff = $derived.by(() => {
		if (!now || !after) return [];
		const a = byId(now), z = byId(after);
		return ORDER.map((id) => ({ id, before: a[id], after: z[id], changed: a[id].value !== z[id].value }));
	});

	async function save() {
		const log = { ...draft, id: `log-${Date.now()}` };
		const before = now;
		setLogs(persona, [...getLogs(persona), log]);
		await load();
		justSaved = { before: byId(before), after: byId(now), title: act.types[type].label };
		note = '';
	}
	async function remove(id: string) {
		setLogs(persona, getLogs(persona).filter((l) => l.id !== id));
		justSaved = null;
		await load();
	}
	async function sync(on: boolean) {
		syncing = true;
		const before = now;
		setSynced(persona, on);
		await load();
		syncing = false;
		justSaved = on ? { before: byId(before), after: byId(now), title: COPY.activity.sync } : null;
	}

	const label = (id: string) => COPY.batteries[id as BatteryId].label;
	const mine = $derived((act?.items ?? []).filter((it: any) => it.source === 'you'));
	const fmt = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(1));
	const sayAll = $derived(`${COPY.activity.title}. ${COPY.activity.intro}`);
</script>

{#if err}
	<section class="card"><p>{COPY.offline}</p></section>
{:else if !act}
	<p class="loading">…</p>
{:else}
	<section class="hero">
		<h1>{COPY.activity.title}</h1>
		<p class="lede">{COPY.activity.intro}</p>
		<Speak text={sayAll} />
	</section>

	{#if justSaved}
		<section class="card changed" role="status">
			<p class="done">{justSaved.title}: {COPY.activity.saved}</p>
			<ul class="delta">
				{#each ORDER as id}
					{@const a = justSaved.before[id]}{@const z = justSaved.after[id]}
					<li class:moved={a.value !== z.value}>
						<Icon name={id} size={20} /> <span class="dname">{label(id)}</span>
						<span class="bar"><span class="fill was" style="width:{a.fill * 100}%"></span><span class="fill now" style="width:{z.fill * 100}%"></span></span>
						<span class="num">{fmt(a.value)} → <strong>{fmt(z.value)}</strong> / {z.target}</span>
					</li>
				{/each}
			</ul>
			<a class="primary" href="/">{COPY.activity.seeBatteries}</a>
		</section>
	{/if}

	<section class="card">
		<h2>{COPY.activity.yours}</h2>
		{#if mine.length}
			<ul class="log-list">
				{#each mine as it}
					<li>
						<div class="log-head"><strong>{it.label}</strong> · {it.duration_min} min <span class="tag choice-tag">{COPY.activity.fromYou}</span></div>
						<div class="muted small">
							{new Date(it.start).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
							· {it.counts.length ? `${COPY.activity.fills}: ${it.counts.map(label).join(', ')}` : COPY.activity.nothing}
							{#if it.note} · {it.note}{/if}
						</div>
						<button class="link" onclick={() => remove(it.id)}>{COPY.activity.remove}</button>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="muted">{COPY.activity.noneYet}</p>
		{/if}
	</section>

	<section class="card">
		<h2><Icon name="watch" size={24} /> {COPY.activity.fromWatch}</h2>
		{#if act.pending_sync > 0}
			<p><strong>{act.pending_sync}</strong> {COPY.activity.found}.</p>
			<button class="secondary" disabled={syncing} onclick={() => sync(true)}>{syncing ? COPY.activity.syncing : COPY.activity.sync}</button>
		{:else}
			<p>{COPY.activity.synced}</p>
			{#if getSynced(persona)}<button class="link" onclick={() => sync(false)}>{COPY.activity.unsync}</button>{/if}
		{/if}
	</section>

	<section class="card user-form">
		<h2>{COPY.activity.add}</h2>
		<h3>{COPY.activity.what}</h3>
		<div class="type-grid">
			{#each Object.entries(act.types) as [t, info]}
				<button class="equip-btn small-btn" aria-pressed={type === t} onclick={() => pickType(t)}>{(info as any).label}</button>
			{/each}
		</div>
		<div class="row2">
			<label class="field">{COPY.activity.when}<input type="datetime-local" bind:value={when} /></label>
			<label class="field">{COPY.activity.howLong}<input type="number" min="1" max="600" bind:value={minutes} /></label>
		</div>
		<h3>{COPY.activity.effort}</h3>
		<div class="votes">
			{#each ['easy', 'moderate', 'hard'] as e}
				<button class="chip vote" aria-pressed={effort === e} onclick={() => pickEffort(e as any)}>{COPY.activity[e as 'easy']}</button>
			{/each}
		</div>
		<fieldset>
			<legend>{COPY.activity.counts}</legend>
			<p class="muted">{COPY.activity.countsHint}</p>
			{#each ORDER as c}
				<label class="check"><input type="checkbox" checked={counts.includes(c)} onchange={() => toggle(c)} /> <Icon name={c} size={20} /> {label(c)}</label>
			{/each}
		</fieldset>
		<label class="field">{COPY.activity.note}<input type="text" maxlength="80" bind:value={note} /></label>

		<h3>{COPY.activity.change}</h3>
		{#if diff.length && !diff.some((d) => d.changed)}
			<p class="notice">{COPY.activity.noChange}</p>
		{/if}
		<ul class="delta">
			{#each diff as d}
				<li class:moved={d.changed}>
					<Icon name={d.id} size={20} /> <span class="dname">{label(d.id)}</span>
					<span class="bar"><span class="fill was" style="width:{d.before.fill * 100}%"></span><span class="fill now" style="width:{d.after.fill * 100}%"></span></span>
					<span class="num">{fmt(d.before.value)} → <strong>{fmt(d.after.value)}</strong> / {d.after.target} {d.after.unit}</span>
				</li>
			{/each}
		</ul>
		<button class="primary" disabled={!draft.start || !draft.duration_min} onclick={save}>{COPY.activity.save}</button>
	</section>

	<section class="card">
		<h2>{COPY.activity.list}</h2>
		<ul class="log-list">
			{#each act.items.filter((it: any) => it.source !== 'you') as it}
				<li class:old={!it.in_window}>
					<div class="log-head">
						<strong>{it.label}</strong> · {it.duration_min} min
						<span class="tag {it.source === 'you' ? 'choice-tag' : ''}">{it.source === 'you' ? COPY.activity.fromYou : COPY.activity.fromWatch}</span>
					</div>
					<div class="muted small">
						{new Date(it.start).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
						{#if !it.in_window} · {COPY.activity.olderThanWeek}{/if}
						· {it.counts.length ? `${COPY.activity.fills}: ${it.counts.map(label).join(', ')}` : COPY.activity.nothing}
						{#if it.note} · {it.note}{/if}
					</div>
				</li>
			{/each}
		</ul>
	</section>
{/if}
