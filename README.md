# Odoo Tech Supportdle

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
- The pool is sorted by `id`, so file order doesn't matter. A day is 2 medium, 1 curated (medium or hard)
  and 2 hard questions. The game targets experienced support engineers, so the generator drops easy
  questions entirely. Hard generated questions are limited to "familiar" models (`Scan.familiar_models`
  in `scripts/extractors/common.py`): models with a window action, no wizards or `ir.*` internals, owned by
  an app or a widely used module.
- Families are grouped into **topics** (`TOPIC` in `daily.ts`: fields, security, models, errors, data,
  setup). The 2 hard questions come from 2 different topics and the 2 medium ones from two others. Topics are
  chosen least-recently-shown first, with ties broken by a date-seeded shuffle, so every topic returns
  within a few days.
- Each topic × difficulty (and the curated set) is a **deck** shuffled with a seeded PRNG
  (`cyrb128` → `mulberry32`, in `src/lib/rng.ts`). A deck deals its next card each time its topic is
  picked; deck positions are replayed from the epoch, which is cheap and cached. When a deck runs out, it
  is reshuffled with the next cycle number as seed, so nothing repeats until that deck is exhausted.
- When you add a new family in the generator, add it to `TOPIC`. Otherwise it becomes its own topic.
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
  "code": "optional error text shown as a snippet",
  "supersedes": ["config-param:some.key"]
}
```

`supersedes` is optional. It lists ids of generated questions about the same fact. Those are dropped from
the pool, so one question can never give away another's answer on the same day.

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
