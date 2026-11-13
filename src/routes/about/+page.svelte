<script lang="ts">
	import { EPOCH, POOL_VERSION } from '#lib/daily.ts';
	import generated from '#lib/data/generated.json';
	import curated from '#lib/data/curated.json';

	import { resolve } from '$app/paths';
	const meta = (generated as { meta: { version: string; commit: string | null; modules: number; families: Record<string, number> } }).meta;
	const families = Object.entries(meta.families).sort((a, b) => b[1] - a[1]);
</script>

<svelte:head><title>How it works · Odoo Tech Supportdle</title></svelte:head>

<p><a href={resolve('/')}>← Back to today's set</a></p>
<article class="card">
	<h1>How it works</h1>
	<p>
		Every day at 00:00 UTC, everyone gets the same five questions. The date is the seed: questions are
		grouped into decks by topic and difficulty, each shuffled with a seeded PRNG (cyrb128 → mulberry32).
		A deck deals its next card whenever its topic comes up, so no question repeats until its deck runs out.
		Answer options are shuffled with a seed derived from the date. The set is fully reproducible:
		<code>?d=YYYY-MM-DD</code> replays any past day.
	</p>
	<p>
		The game is tuned for experienced support engineers. Each set has 2 medium questions, 1 hand-curated
		support classic and 2 hard ones. There are no easy questions. The five always cover five different topics
		(fields, security, models, errors, data, setup), and the least recently seen topics come first, so every
		topic is back within a few days. Hard questions only ask about models you can open from a menu in an app
		or a widely used module, not framework internals.
	</p>

	<h2>Where the questions come from</h2>
	<p>
		A Python script scans Odoo <strong>{meta.version}</strong> Community{meta.commit ? ` (commit ${meta.commit.slice(0, 12)})` : ''}
		across {meta.modules} modules. Localisations and test modules are skipped, and Enterprise is not included.
		The script reads manifests, model classes, <code>raise UserError(...)</code> calls, constraints, data XML
		(crons, sequences, groups, mail templates, record rules), <code>ir.model.access.csv</code>, field definitions
		(which module adds a field, related paths, <code>ondelete</code>, company-dependent fields), <code>get_param</code>
		defaults and <code>odoo/tools/config.py</code>.
		Every answer links to the file and line it comes from.
	</p>
	<table>
		<tbody>
			{#each families as [name, count]}
				<tr><td><code>{name}</code></td><td>{count}</td></tr>
			{/each}
			<tr><td><code>curated</code></td><td>{curated.questions.length}</td></tr>
		</tbody>
	</table>
	<p class="muted">Pool version {POOL_VERSION} · Puzzle #1 = {EPOCH}</p>
</article>

<style>
	h1 { margin-top: 0; font-size: 1.4rem; }
	h2 { font-size: 1.1rem; margin-top: 1.6em; }
	table { border-collapse: collapse; width: 100%; font-size: 0.92rem; }
	td { padding: 5px 0; border-bottom: 1px solid var(--border); }
	td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
	.muted { color: var(--muted); font-size: 0.85rem; margin-top: 18px; }
</style>
