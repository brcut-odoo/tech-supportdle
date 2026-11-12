# Odoo Support Trivia

A daily 5-question trivia game for technical support, built from the **Odoo 19.0 Community** source code.
Everyone gets the same set each UTC day. Every answer shows the file and line it comes from.

It is a fully static SvelteKit 3 site (`adapter-static`). The question pool is committed JSON, so building
the site doesn't need an Odoo checkout.

## Develop

```bash
nix-shell            # node 22 + python3 with lxml (see shell.nix)
npm install
npm run dev          # http://localhost:5173
npm test             # determinism tests (vitest)
npm run check        # svelte-check / TypeScript
npm run build        # -> build/ (static files, host anywhere)
npm run preview      # serve build/
```

## How a day is picked

`src/lib/daily.ts`:

- The day key is the **UTC** date `YYYY-MM-DD`. Puzzle #1 is `EPOCH` (2026-11-12).
- The pool is sorted by `id`, so file order doesn't matter, then split into buckets:
  2 easy, 1 curated, 1 medium, 1 hard.
- Each bucket is a **deck** shuffled with a seeded PRNG (`cyrb128` → `mulberry32`, in `src/lib/rng.ts`).
  Day *N* deals cards `N*count … N*count+count-1`. When a deck runs out, it is reshuffled with the next
  cycle number as seed. As a result, nothing repeats until a bucket is exhausted.
- The 3 distractors and the option order come from a PRNG seeded with the date key.
- `?d=YYYY-MM-DD` replays a past day. Future dates and dates before the epoch fall back to today.
  Replays don't count toward stats.

The same date and the same pool always give the same set. **Regenerating or editing the pool changes
past and future sets.** That is fine between releases. Bump `POOL_VERSION` when you want an explicit
reshuffle.

## Question pool

| File | What |
|---|---|
| `src/lib/data/generated.json` | Output of `npm run generate`; ~1,000 questions in 15 families |
| `src/lib/data/curated.json` | Hand-written support classics (states, server limits, ORM, common errors), each checked against the code |

### Regenerate from the source

```bash
nix-shell --run 'npm run generate'                      # default: /home/odoo/odoo/dev/src/19.0/odoo
nix-shell --run 'python3 scripts/generate.py /path/to/odoo'   # any community checkout (repo root)
```

`scripts/generate.py` uses Python's `ast` and `lxml` on community addons only. It skips Enterprise,
`l10n_*`, `test_*` and non-installable modules. Each family lives in `scripts/extractors/`:

- `manifests.py`: category, application flag, direct dependencies, auto-install bridges
- `models.py`: `_description` → `_name`, defining module, `_order`, `raise UserError(...)` origin, `models.Constraint`
- `data.py`: cron intervals, sequence prefixes, implied groups, mail templates, `get_param` defaults
- `core.py`: server option defaults from `odoo/tools/config.py`

Distractors are chosen deterministically from nearby items: the same module, dependencies, name prefix or
category. The run fails on validation errors: duplicate ids, fewer than 3 distractors, or the answer
appearing among the distractors.

### Add a curated question

Append to `curated.json`:

```json
{
  "id": "curated:unique-slug",
  "difficulty": 2,
  "question": "Supports `code` and **bold**",
  "answer": "…",
  "distractors": ["…", "…", "…"],
  "explanation": "Why, with a pointer to the code.",
  "source": "odoo/addons/<module>/models/<file>.py:<line>",
  "code": "optional error text shown as a snippet"
}
```

## Deploy

### GitHub Pages (CI/CD)

`.github/workflows/deploy.yml` runs on every push to `main`/`master`, on pull requests and on manual
dispatch:

1. `npm ci` → `npm run check` → `npm test` → `npm run build`
2. On pushes and manual runs (not on PRs), it uploads `build/` and deploys it with `actions/deploy-pages`.

One-time setup on GitHub: go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.

The workflow passes the Pages base path (`/tech-supportdle` for https://brcut-odoo.github.io/tech-supportdle/)
to the build as `BASE_PATH`. It is empty for a user/org site or a custom domain. To reproduce a Pages
build locally:

```bash
BASE_PATH=/tech-supportdle npm run build
```

CI does **not** regenerate questions, because it has no Odoo checkout. Run `npm run generate` locally
and commit `src/lib/data/generated.json`. The site doesn't need a daily rebuild either: the date is read
in the browser.

### Elsewhere

`build/` is plain static files, so it also works on nginx, S3 or GitLab Pages. Set `BASE_PATH` if it is
served from a sub-path. Progress and stats are stored in the browser's `localStorage` (per device).
