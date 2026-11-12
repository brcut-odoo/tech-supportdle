<script lang="ts">
	import { onMount } from 'svelte';
	import { resolve } from '$app/paths';
	import { dateKeyUTC, isValidKey, keyFromIndex, dayIndex, msUntilNextDay, pickDaily } from '#lib/daily.ts';
	import { inline } from '#lib/inline.ts';
	import { pool } from '#lib/pool.ts';
	import { loadDay, loadStats, recordResult, saveDay, type DayState, type Stats } from '#lib/storage.ts';
	import type { DailySet } from '#lib/types.ts';

	const FAMILY_LABEL: Record<string, string> = {
		curated: 'Support classic',
		'manifest-category': 'Manifest',
		'manifest-application': 'Manifest',
		'manifest-depends': 'Dependencies',
		'manifest-autoinstall': 'Auto-install',
		'model-name': 'Models',
		'model-module': 'Models',
		'model-order': 'ORM',
		'error-origin': 'Error hunt',
		constraint: 'Constraints',
		cron: 'Scheduled actions',
		sequence: 'Sequences',
		'group-implied': 'Access rights',
		'mail-template': 'Mail templates',
		'config-param': 'System parameters',
		'server-option': 'Server config'
	};
	const DIFF = ['', 'Easy', 'Medium', 'Hard'];
	/** Identifiers (models, modules, xmlids, values) render as code; prose and labels don't. */
	const isMono = (s: string) => !/\s/.test(s) && !/^[A-Z][a-z]/.test(s) && !s.includes('`');

	let today = $state('');
	let set = $state<DailySet | null>(null);
	let day = $state<DayState>({ answers: [], correct: [] });
	let current = $state(0);
	let replay = $state(false);
	let stats = $state<Stats | null>(null);
	let countdown = $state('');
	let copied = $state(false);

	const total = $derived(set?.questions.length ?? 0);
	const score = $derived(day.correct.filter(Boolean).length);
	const finished = $derived(total > 0 && day.answers.every((a) => a !== null));
	const showResults = $derived(finished && current >= total);
	const q = $derived(set && current < total ? set.questions[current] : null);
	const picked = $derived(q ? day.answers[current] : null);

	function tick() {
		const ms = msUntilNextDay();
		const h = Math.floor(ms / 3.6e6);
		const m = Math.floor((ms % 3.6e6) / 6e4);
		const s = Math.floor((ms % 6e4) / 1000);
		countdown = `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
		if (today && dateKeyUTC() !== today && !replay) location.reload();
	}

	onMount(() => {
		today = dateKeyUTC();
		const requested = new URLSearchParams(location.search).get('d');
		let key = today;
		if (requested && isValidKey(requested) && requested < today && dayIndex(requested) >= 0) {
			key = requested;
			replay = true;
		}
		set = pickDaily(key, pool);
		day = loadDay(key, set.questions.length);
		const firstOpen = day.answers.findIndex((a) => a === null);
		current = firstOpen === -1 ? set.questions.length : firstOpen;
		stats = loadStats();
		tick();
		const id = setInterval(tick, 1000);
		return () => clearInterval(id);
	});

	function choose(i: number) {
		if (!set || !q || picked !== null) return;
		day.answers[current] = i;
		day.correct[current] = q.options[i] === q.answer;
		saveDay(set.dateKey, day);
		if (day.answers.every((a) => a !== null) && !replay) {
			stats = recordResult(set.dateKey, keyFromIndex(dayIndex(set.dateKey) - 1), score, total);
		}
	}

	function next() {
		current += 1;
		window.scrollTo({ top: 0, behavior: 'smooth' });
	}

	function onKey(e: KeyboardEvent) {
		if (!q || e.metaKey || e.ctrlKey || e.altKey) return;
		const n = Number(e.key);
		if (picked === null && n >= 1 && n <= q.options.length) choose(n - 1);
		else if (picked !== null && (e.key === 'Enter' || e.key === 'ArrowRight')) next();
	}

	const squares = $derived(day.correct.map((c) => (c ? '🟩' : c === false ? '🟥' : '⬜')).join(''));

	async function share() {
		if (!set) return;
		// Link to this exact day so the recipient plays the same set, even on a later day.
		const url = `${location.origin}${location.pathname}?d=${set.dateKey}`;
		const text = `Odoo Tech Supportdle #${set.number} (${set.dateKey})\n${squares} ${score}/${total}\n${url}`;
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			prompt('Copy your result:', text);
		}
	}

	const verdict = $derived(
		score === total ? 'Flawless. Support legend.' :
		score >= 4 ? 'Great work, ticket closed.' :
		score >= 3 ? 'Solid. Check the sources for the ones you missed.' :
		score >= 1 ? 'Time to grep the codebase.' : 'Ouch. Escalating to R&D.'
	);

	function prevDayHref(): string {
		if (!set) return resolve('/');
		const prev = keyFromIndex(dayIndex(set.dateKey) - 1);
		return dayIndex(prev) >= 0 ? `${resolve('/')}?d=${prev}` : resolve('/');
	}
</script>

<svelte:window onkeydown={onKey} />
<svelte:head><title>Odoo Tech Supportdle</title></svelte:head>

<header>
	<div class="brand">
		<span class="logo" aria-hidden="true">?</span>
		<div>
			<h1>Odoo Tech Supportdle</h1>
			{#if set}
				<p class="sub">
					#{set.number} · {set.dateKey}
					{#if replay}<span class="pill">Replay</span>{/if}
				</p>
			{/if}
		</div>
	</div>
	{#if set}
		<ol class="progress" aria-label="Progress">
			{#each set.questions as _, i}
				<li
					class:done={day.correct[i] !== null}
					class:ok={day.correct[i] === true}
					class:bad={day.correct[i] === false}
					class:cur={i === current}
					aria-label={`Question ${i + 1}`}
				></li>
			{/each}
		</ol>
	{/if}
</header>

{#if !set}
	<div class="card skeleton" aria-busy="true">Loading today's questions…</div>
{:else if q}
	{#key current}
	<article class="card" aria-live="polite">
		<div class="meta">
			<span class="tag">{FAMILY_LABEL[q.family] ?? q.family}</span>
			<span class="diff d{q.difficulty}">{DIFF[q.difficulty]}</span>
			<span class="count">{current + 1} / {total}</span>
		</div>
		<h2>{@html inline(q.question)}</h2>
		{#if q.code}
			<pre class="snippet"><code>{q.code}</code></pre>
		{/if}

		<div class="options" role="group" aria-label="Answers">
			{#each q.options as opt, i}
				{@const isAnswer = opt === q.answer}
				<button
					class="opt"
					class:right={picked !== null && isAnswer}
					class:wrong={picked === i && !isAnswer}
					class:dim={picked !== null && picked !== i && !isAnswer}
					disabled={picked !== null}
					onclick={() => choose(i)}
				>
					<span class="key">{i + 1}</span>
					<span class="label">{@html inline(isMono(opt) ? '`' + opt + '`' : opt)}</span>
				</button>
			{/each}
		</div>

		{#if picked !== null}
			<div class="feedback" class:good={day.correct[current]}>
				<p class="result">{day.correct[current] ? 'Correct!' : 'Not quite.'}</p>
				<p>{@html inline(q.explanation)}</p>
				<p class="source">
					<span>Source</span> <code>{q.source}</code>
				</p>
			</div>
			<div class="actions">
				{#if finished && current + 1 < total}
					<button class="btn ghost" onclick={() => (current = total)}>Back to results</button>
				{/if}
				<button class="btn" onclick={next}>
					{current + 1 < total ? 'Next question' : 'See results'} <span aria-hidden="true">→</span>
				</button>
			</div>
		{/if}
	</article>
	{/key}
{:else if showResults}
	<section class="card results">
		<p class="big">{score}<span>/{total}</span></p>
		<p class="squares" aria-label={`${score} out of ${total} correct`}>{squares}</p>
		<p class="verdict">{verdict}</p>
		<div class="actions center">
			<button class="btn" onclick={share}>{copied ? 'Copied!' : 'Share result'}</button>
		</div>

		<ol class="recap" aria-label="Your answers">
			{#each set.questions as rq, i}
				{@const chosen = day.answers[i]}
				{@const yours = chosen !== null ? rq.options[chosen] : null}
				{@const ok = day.correct[i] === true}
				<li class:ok class:bad={!ok}>
					<button class="recap-item" onclick={() => (current = i)} title="Show explanation and source">
						<span class="mark" aria-label={ok ? 'Correct' : 'Wrong'}>{ok ? '✓' : '✗'}</span>
						<span class="recap-body">
							<span class="recap-q">{@html inline(rq.question)}</span>
							<span class="recap-a">
								<span class="lbl">Your answer</span>
								<span class="yours">{@html inline(yours === null ? '—' : isMono(yours) ? '`' + yours + '`' : yours)}</span>
							</span>
							{#if !ok}
								<span class="recap-a">
									<span class="lbl">Correct</span>
									<span class="right">{@html inline(isMono(rq.answer) ? '`' + rq.answer + '`' : rq.answer)}</span>
								</span>
							{/if}
						</span>
						<span class="chev" aria-hidden="true">›</span>
					</button>
				</li>
			{/each}
		</ol>

		{#if stats && stats.played > 0}
			<dl class="stats">
				<div><dt>Played</dt><dd>{stats.played}</dd></div>
				<div><dt>Perfect</dt><dd>{stats.perfect}</dd></div>
				<div><dt>Streak</dt><dd>{stats.streak}</dd></div>
				<div><dt>Best streak</dt><dd>{stats.maxStreak}</dd></div>
			</dl>
		{/if}

		{#if replay}
			<p class="next"><a href={resolve('/')}>Back to today's set</a></p>
		{:else}
			<p class="next">Next set in <strong class="mono">{countdown}</strong></p>
		{/if}
		{#if dayIndex(set.dateKey) > 0}
			<p class="archive"><a href={prevDayHref()}>Play the previous day ←</a></p>
		{/if}
	</section>
{/if}

<style>
	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		margin-bottom: 18px;
	}
	.brand { display: flex; align-items: center; gap: 12px; }
	.logo {
		width: 42px; height: 42px; border-radius: 11px;
		display: grid; place-items: center;
		background: var(--brand); color: var(--brand-ink);
		font-weight: 800; font-size: 1.4rem;
	}
	h1 { font-size: 1.2rem; margin: 0; letter-spacing: -0.01em; }
	.sub { margin: 0; color: var(--muted); font-size: 0.9rem; display: flex; align-items: center; gap: 8px; }
	.pill {
		background: var(--surface-2); border: 1px solid var(--border);
		border-radius: 999px; padding: 0 8px; font-size: 0.75rem;
	}
	.progress { display: flex; gap: 6px; list-style: none; margin: 0; padding: 0; }
	.progress li {
		width: 26px; height: 8px; border-radius: 4px;
		background: var(--border); transition: background 0.2s;
	}
	.progress li.cur { outline: 2px solid var(--brand); outline-offset: 2px; }
	.progress li.ok { background: var(--ok); }
	.progress li.bad { background: var(--bad); }

	.skeleton { color: var(--muted); text-align: center; }

	.meta { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; margin-bottom: 10px; }
	.tag { background: var(--surface-2); color: var(--brand); font-weight: 600; padding: 2px 9px; border-radius: 999px; }
	.diff { color: var(--muted); }
	.diff.d3 { color: var(--bad); }
	.diff.d2 { color: var(--accent); }
	.count { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }

	h2 { font-size: 1.18rem; line-height: 1.45; margin: 0 0 14px; font-weight: 600; }
	.snippet {
		margin: 0 0 16px; padding: 12px 14px;
		background: var(--code-bg); border-left: 3px solid var(--bad);
		border-radius: 8px; white-space: pre-wrap; overflow-wrap: anywhere;
	}
	.snippet code { background: none; padding: 0; }

	.options { display: grid; gap: 10px; }
	.opt {
		display: flex; align-items: center; gap: 12px; text-align: left;
		width: 100%; padding: 12px 14px;
		border: 1.5px solid var(--border); border-radius: 11px;
		background: var(--surface); cursor: pointer;
		transition: border-color 0.15s, background 0.15s, opacity 0.15s;
	}
	.opt:not(:disabled):hover { border-color: var(--brand); background: var(--surface-2); }
	.opt:disabled { cursor: default; }
	.opt .key {
		flex: none; width: 26px; height: 26px; border-radius: 7px;
		display: grid; place-items: center; font-size: 0.8rem; font-weight: 700;
		background: var(--surface-2); color: var(--muted);
	}
	.opt .label { min-width: 0; overflow-wrap: anywhere; }
	.opt.right { border-color: var(--ok); background: var(--ok-bg); }
	.opt.right .key { background: var(--ok); color: var(--surface); }
	.opt.wrong { border-color: var(--bad); background: var(--bad-bg); }
	.opt.wrong .key { background: var(--bad); color: var(--surface); }
	.opt.dim { opacity: 0.55; }

	.feedback {
		margin-top: 16px; padding: 14px 16px; border-radius: 11px;
		background: var(--bad-bg); border: 1px solid color-mix(in srgb, var(--bad) 30%, transparent);
	}
	.feedback.good { background: var(--ok-bg); border-color: color-mix(in srgb, var(--ok) 30%, transparent); }
	.feedback p { margin: 0 0 8px; }
	.feedback p:last-child { margin-bottom: 0; }
	.result { font-weight: 700; }
	.feedback.good .result { color: var(--ok); }
	.feedback:not(.good) .result { color: var(--bad); }
	.source { font-size: 0.85rem; color: var(--muted); }
	.source span { text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.72rem; font-weight: 700; margin-right: 4px; }

	.actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; flex-wrap: wrap; }
	.actions.center { justify-content: center; }

	.results { text-align: center; }
	.big { font-size: 3.4rem; font-weight: 800; margin: 0; line-height: 1; letter-spacing: -0.03em; }
	.big span { font-size: 1.6rem; color: var(--muted); font-weight: 600; }
	.squares { font-size: 1.6rem; letter-spacing: 4px; margin: 10px 0 4px; }
	.verdict { color: var(--muted); margin: 0 0 6px; }
	.stats {
		display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
		margin: 22px 0 6px; padding: 14px 0; border-block: 1px solid var(--border);
	}
	.stats div { display: flex; flex-direction: column-reverse; }
	.stats dt { font-size: 0.75rem; color: var(--muted); }
	.stats dd { margin: 0; font-size: 1.4rem; font-weight: 700; font-variant-numeric: tabular-nums; }
	.recap { list-style: none; margin: 22px 0 0; padding: 0; display: grid; gap: 8px; text-align: left; }
	.recap-item {
		display: flex; align-items: flex-start; gap: 12px; width: 100%;
		padding: 12px 14px; text-align: left; cursor: pointer;
		background: var(--surface); border: 1.5px solid var(--border); border-radius: 11px;
	}
	.recap-item:hover { background: var(--surface-2); }
	.recap-item:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
	.recap li.ok .recap-item { border-color: color-mix(in srgb, var(--ok) 45%, var(--border)); }
	.recap li.bad .recap-item { border-color: color-mix(in srgb, var(--bad) 45%, var(--border)); }
	.mark {
		flex: none; width: 24px; height: 24px; border-radius: 50%;
		display: grid; place-items: center; font-size: 0.8rem; font-weight: 800; color: var(--surface);
	}
	.recap li.ok .mark { background: var(--ok); }
	.recap li.bad .mark { background: var(--bad); }
	.recap-body { display: grid; gap: 4px; min-width: 0; flex: 1; }
	.recap-q { font-weight: 600; font-size: 0.95rem; line-height: 1.4; overflow-wrap: anywhere; }
	.recap-a { display: flex; gap: 8px; align-items: baseline; font-size: 0.88rem; min-width: 0; }
	.recap-a .lbl {
		flex: none; min-width: 96px; white-space: nowrap; color: var(--muted);
		font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700;
	}
	.recap-a > span:last-child { min-width: 0; overflow-wrap: anywhere; }
	.recap li.ok .yours { color: var(--ok); font-weight: 600; }
	.recap li.bad .yours { color: var(--bad); text-decoration: line-through; text-decoration-thickness: 1px; }
	.right { color: var(--ok); font-weight: 600; }
	.chev { flex: none; color: var(--muted); font-size: 1.3rem; line-height: 1; align-self: center; }
	.next { margin: 14px 0 0; }
	.archive { margin: 8px 0 0; font-size: 0.9rem; }
	@media (max-width: 420px) {
		.card { padding: 18px 16px; }
		.progress li { width: 18px; }
		.stats { grid-template-columns: repeat(2, 1fr); }
	}
</style>
