<script lang="ts">
	import type { Taste, Vote } from './api';
	import { COPY } from './copy';
	import Icon from './Icon.svelte';
	import Why from './Why.svelte';
	import Meaning from './Meaning.svelte';
	import SourceChip from './SourceChip.svelte';

	// One daypart. Only the live one is full-colour with an action; the others are dimmed
	// previews that open up so you can read the plan, but never get a button.
	let { card, overridden = false, whyOpen = false, taste = {}, onoverride, onvote }: {
		card: any;
		overridden?: boolean;
		whyOpen?: boolean;
		taste?: Taste;
		onoverride: (on: boolean) => void;
		onvote: (kind: string, v: Vote | null) => void;
	} = $props();

	let added = $state(false);
	let skipped = $state(false);
	let gotIt = $state(false);
	let showSeated = $state(false);

	const dp = $derived(card.daypart as 'morning' | 'afternoon' | 'evening');
	const live = $derived(card.status === 'live');
	const act = $derived(card.activity);
	const shown = $derived(showSeated && card.seated_alternative ? card.seated_alternative : act);
	const when = $derived(card.status === 'past' ? COPY.dayparts.earlier : card.status === 'live' ? COPY.dayparts.now : COPY.dayparts.later);
	const vote = $derived(act ? taste[act.id] : undefined);

	function ics() {
		const s = card.slot;
		const f = (x: string) => x.replace(/[-:]/g, '').slice(0, 15);
		const body = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Charge//EN', 'BEGIN:VEVENT',
			`UID:${Date.now()}@charge`, `DTSTART:${f(s.start)}`, `DTEND:${f(s.end)}`,
			`SUMMARY:${shown.title}`, `DESCRIPTION:${shown.video?.url ?? shown.steps.join(' ')}`,
			'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
		const a = document.createElement('a');
		a.href = URL.createObjectURL(new Blob([body], { type: 'text/calendar' }));
		a.download = 'charge.ics';
		a.click();
		added = true;
	}
</script>

{#snippet details()}
	{#if card.state === 'full'}<p class="notice">{card.text.notice}</p>{/if}

	<h1>{shown.title}</h1>
	<p class="meta"><Icon name="calendar" size={22} /> {shown.minutes} minutes{#if card.text?.when && card.state === 'ok'}&nbsp;· {card.text.when}{/if}</p>
	<div class="batt-tags">
		{#each shown.batteries as b}<span class="tag"><Icon name={b} size={18} /> {COPY.batteries[b as keyof typeof COPY.batteries].label}</span>{/each}
	</div>
	<p class="muted">{shown.equipment_text} {COPY.day.noise}: {shown.noise_text}.{#if shown.seated_option} {COPY.day.canSit}{/if}</p>

	{#if card.sleep_notice && !overridden}
		<aside class="mixed" aria-label={card.sleep_notice.title}>
			<h2>{card.sleep_notice.title} <span class="tag mixed-tag">{COPY.day.mixed}</span></h2>
			<p>{card.sleep_notice.body}</p>
			<SourceChip source={card.sleep_notice.source} id={card.sleep_notice.source_id} />
			{#if live}<button class="secondary" onclick={() => onoverride(true)}>{card.sleep_notice.button}</button>{/if}
		</aside>
	{:else if overridden}
		<aside class="mixed">
			<p>{COPY.day.harderChosen}</p>
			<button class="link" onclick={() => onoverride(false)}>{COPY.day.backToGentle}</button>
		</aside>
	{/if}

	{#if shown.video}
		<div class="video">
			<iframe src={shown.video.embed_url} title={shown.video.title} loading="lazy"
				allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
		</div>
		<p class="muted">{COPY.today.video}: <em>{shown.video.title}</em> · {shown.video.channel}</p>
	{/if}
	{#if shown.steps?.length}
		<h2 class="steps-title">{COPY.day.steps}</h2>
		<ol class="steps">{#each shown.steps as s}<li>{s}</li>{/each}</ol>
	{/if}
	{#if card.seated_alternative}
		<button class="link" onclick={() => (showSeated = !showSeated)}>{showSeated ? act.title : COPY.today.seated}</button>
	{/if}

	<div class="votes" role="group" aria-label={shown.title}>
		<button class="chip vote" aria-pressed={vote === 'more'} onclick={() => onvote(act.id, vote === 'more' ? null : 'more')}>
			<span aria-hidden="true">▲</span> {COPY.day.moreLike}
		</button>
		<button class="chip vote" aria-pressed={vote === 'less'} onclick={() => onvote(act.id, vote === 'less' ? null : 'less')}>
			<span aria-hidden="true">▼</span> {COPY.day.lessLike}
		</button>
	</div>

	{#if card.confidence?.sentence}
		<div class="confidence band-{card.confidence.key}">
			<h2>{COPY.today.howSure}</h2>
			<p>{card.text?.confidence ?? card.confidence.sentence}{#if card.p != null} <span class="prob">({card.p.toFixed(2)})</span>{/if}</p>
			{#if card.mode === 'quick'}<p>{COPY.today.quick}</p>{/if}
			{#if card.text?.genetic_frame}<p class="genetic-frame">{card.text.genetic_frame}</p>{/if}
			<Meaning>
				<p>We add up every reason that points to this idea. Each reason has its own weight. The number is how much they add up to, from 0 to 1.</p>
			</Meaning>
		</div>
	{/if}
{/snippet}

{#snippet why()}
	<details class="card whybox" id={live ? 'why' : undefined} open={live && whyOpen}>
		<summary><h2>{COPY.today.why}</h2></summary>

		<h3>{COPY.day.whyContext}</h3>
		<ul class="context">
			{#each card.context as n}
				<li class="ctx ctx-{n.kind}">
					<p>{n.text}</p>
					{#if n.certainty === 'mixed'}<span class="tag mixed-tag">{COPY.day.mixed}</span>{/if}
					{#if n.health_claim && n.source_id}
						<SourceChip source={card.sources[n.source_id]} id={n.source_id} />
					{:else if !n.health_claim}
						<span class="tag choice-tag">{COPY.day.ourChoice}</span>
					{/if}
					{#if n.design_note}
						<details class="meaning"><summary>{COPY.today.productChoice}</summary><p>{n.design_note}</p></details>
					{/if}
				</li>
			{/each}
		</ul>

		<h3>{COPY.today.whyTitle}</h3>
		<Why nodes={card.derivation} sources={card.sources} />
		<p class="howsure"><strong>{COPY.today.howSure}</strong> {card.text.confidence}{#if card.p != null} <em>({card.p.toFixed(2)})</em>{/if}</p>

		{#if card.proofs?.length}
			<details class="meaning proofs">
				<summary>{COPY.today.proofTitle}</summary>
				<p>{COPY.today.proofIntro}</p>
				<ol class="mono">
					{#each card.proofs as pr}
						<li><code>{pr.uses.join('  ∧  ')}{#if pr.excludes.length}  ∧ ¬({pr.excludes.join(', ')}){/if}</code> <span class="prob">{pr.p}</span></li>
					{/each}
				</ol>
			</details>
		{/if}

		{#if card.ranking?.length > 1}
			<h3>{COPY.day.ranking}</h3>
			<ul>{#each card.ranking.slice(1) as r}<li>{r.title} <span class="prob">({r.score.toFixed(2)})</span></li>{/each}</ul>
		{/if}
	</details>
{/snippet}

{#if !live && act}
	<details class="card daypart dim inspect">
		<summary>
			<Icon name={dp} size={28} />
			<span class="summary-text">
				<span class="eyebrow">{card.label} · {when}</span>
				<span class="preview">{when}: {card.text?.preview ?? ''}</span>
				<span class="look">{COPY.day.look}</span>
			</span>
		</summary>
		<div class="inspect-body">
			<p class="muted">{card.status === 'past' ? COPY.day.lookEarlier : COPY.day.lookLater}</p>
			{@render details()}
			{#if card.state === 'ok'}{@render why()}{/if}
		</div>
	</details>
{:else if !live}
	<section class="card daypart dim" aria-label="{card.label}, {when}">
		<Icon name={dp} size={28} />
		<div>
			<p class="eyebrow">{card.label} · {when}</p>
			<p class="preview">{card.text?.preview ?? ''}</p>
		</div>
	</section>
{:else if card.state === 'away' || card.state === 'none'}
	<section class="card daypart live">
		<p class="eyebrow"><Icon name={dp} size={20} /> {card.label} · {COPY.dayparts.now}</p>
		<p class="preview">{card.text.preview}</p>
	</section>
{:else}
	<article class="card daypart live today">
		<p class="eyebrow"><Icon name={dp} size={20} /> {card.label} · {COPY.dayparts.now}</p>
		{@render details()}

		{#if card.state === 'full'}
			{#if gotIt}
				<p class="done" role="status">{COPY.today.notTodayDone}</p>
			{:else}
				<button class="primary" onclick={() => (gotIt = true)}>{COPY.day.gotIt}</button>
			{/if}
		{:else if added}
			<p class="done" role="status">{COPY.today.added}</p>
		{:else if skipped}
			<p class="done" role="status">{COPY.today.notTodayDone}</p>
		{:else}
			<button class="primary" onclick={ics}>{COPY.today.addToCalendar}</button>
			<button class="secondary" onclick={() => (skipped = true)}>{COPY.today.notToday}</button>
		{/if}
	</article>

	{#if card.state === 'ok'}{@render why()}{/if}
{/if}
