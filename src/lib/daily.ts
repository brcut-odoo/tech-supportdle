import { rngFromString, shuffle } from './rng';
import type { DailyQuestion, DailySet, Question } from './types';

/** Bump only on purpose: changes every past and future daily set. */
export const POOL_VERSION = 2;
/** Puzzle #1. */
export const EPOCH = '2026-11-12';
const SALT = 'odoo-support-trivia';
const DAY_MS = 86_400_000;

/**
 * Topics group question families so a day can be a mix: the five questions of a day never
 * share a topic (unless the pool is too small to allow it).
 */
export const TOPIC: Record<string, string> = {
	'field-origin': 'fields',
	'field-related': 'fields',
	'field-ondelete': 'fields',
	'company-dependent': 'fields',
	'access-rights': 'security',
	'record-rule': 'security',
	'group-implied': 'security',
	'model-name': 'models',
	'model-module': 'models',
	'model-order': 'models',
	'error-origin': 'errors',
	constraint: 'errors',
	cron: 'data',
	sequence: 'data',
	'mail-template': 'data',
	'config-param': 'setup',
	'server-option': 'setup',
	'manifest-depends': 'setup',
	'manifest-autoinstall': 'setup',
	'manifest-category': 'setup',
	'manifest-application': 'setup'
};

export const topicOf = (q: Question): string =>
	q.family === 'curated' ? 'curated' : (TOPIC[q.family] ?? q.family);

/**
 * Daily composition for experienced support engineers: 2 medium, 1 curated, 2 hard, every
 * generated question from a different topic.
 */
const MEDIUM_PER_DAY = 2;
const HARD_PER_DAY = 2;

export function dateKeyUTC(d: Date = new Date()): string {
	return d.toISOString().slice(0, 10);
}

export function isValidKey(key: string): boolean {
	if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) return false;
	const t = Date.parse(key + 'T00:00:00Z');
	return !Number.isNaN(t) && dateKeyUTC(new Date(t)) === key;
}

export function dayIndex(key: string): number {
	return Math.round((Date.parse(key + 'T00:00:00Z') - Date.parse(EPOCH + 'T00:00:00Z')) / DAY_MS);
}

export function keyFromIndex(index: number): string {
	return dateKeyUTC(new Date(Date.parse(EPOCH + 'T00:00:00Z') + index * DAY_MS));
}

export function puzzleNumber(key: string): number {
	return dayIndex(key) + 1;
}

export function msUntilNextDay(now: Date = new Date()): number {
	const next = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
	return next - now.getTime();
}

/**
 * Each deck (one per difficulty and topic, plus the curated deck) is a seeded shuffle of its
 * questions. A deck deals its next card every time its topic is picked, so nothing repeats
 * until that deck is exhausted; then it is reshuffled with a new seed (the cycle number).
 */
const shuffled = new Map<string, Question[]>();

function deal(deck: string, cards: Question[], position: number): Question {
	const cycle = Math.floor(position / cards.length);
	const cacheKey = `${deck}:${cycle}:${cards.length}:${cards[0].id}`;
	let order = shuffled.get(cacheKey);
	if (!order) {
		order = shuffle(cards, rngFromString(`${SALT}:v${POOL_VERSION}:${deck}:cycle${cycle}`));
		shuffled.set(cacheKey, order);
	}
	return order[position % cards.length];
}

interface Decks {
	hard: Map<string, Question[]>; // topic -> difficulty 3 questions
	medium: Map<string, Question[]>; // topic -> difficulty 2 questions
	curated: Question[];
	/** State at the start of day `day` (replayed from day 0; see `stateAt`). */
	day: number;
	state: History;
}

interface History {
	/** Cards dealt so far from each deck. */
	positions: Map<string, number>;
	/** Last day each topic was shown (as hard or medium). */
	lastUsed: Map<string, number>;
}

const cloneHistory = (h: History): History => ({ positions: new Map(h.positions), lastUsed: new Map(h.lastUsed) });

const decksByPool = new Map<string, Decks>();

function buildDecks(sorted: Question[]): Decks {
	const hard = new Map<string, Question[]>();
	const medium = new Map<string, Question[]>();
	for (const q of sorted) {
		if (q.family === 'curated') continue;
		const target = q.difficulty === 3 ? hard : q.difficulty === 2 ? medium : null;
		if (!target) continue;
		const t = topicOf(q);
		if (!target.has(t)) target.set(t, []);
		target.get(t)!.push(q);
	}
	const curated = sorted.filter((q) => q.family === 'curated' && q.difficulty >= 2);
	const empty: History = { positions: new Map(), lastUsed: new Map() };
	return { hard, medium, curated: curated.length ? curated : sorted, day: 0, state: empty };
}

/**
 * Topics for one day: the least recently shown topics first, so every topic comes back within
 * a few days; ties are broken by a shuffle seeded with the date, so it stays reproducible.
 */
function topicsFor(key: string, d: Decks, h: History): { hard: string[]; medium: string[] } {
	const rng = rngFromString(`${SALT}:v${POOL_VERSION}:topics:${key}`);
	const stalest = (topics: string[]) => {
		const order = shuffle([...topics].sort(), rng);
		const tie = new Map(order.map((t, i) => [t, i]));
		const last = (t: string) => h.lastUsed.get(t) ?? -1;
		return order.sort((a, b) => last(a) - last(b) || tie.get(a)! - tie.get(b)!);
	};
	const hardTopics = stalest([...d.hard.keys()]);
	const hard = Array.from({ length: HARD_PER_DAY }, (_, i) => hardTopics[i % hardTopics.length]);
	const allMedium = [...d.medium.keys()];
	const fresh = allMedium.filter((t) => !hard.includes(t));
	const mediumTopics = stalest(fresh.length >= MEDIUM_PER_DAY ? fresh : allMedium);
	const medium = Array.from({ length: MEDIUM_PER_DAY }, (_, i) => mediumTopics[i % mediumTopics.length]);
	return { hard, medium };
}

function advance(h: History, day: number, t: { hard: string[]; medium: string[] }): void {
	const bump = (deck: string) => h.positions.set(deck, (h.positions.get(deck) ?? 0) + 1);
	for (const topic of t.hard) bump(`hard:${topic}`);
	for (const topic of t.medium) bump(`medium:${topic}`);
	for (const topic of [...t.hard, ...t.medium]) h.lastUsed.set(topic, day);
}

/**
 * History at the start of `day`: which cards each deck has dealt and when each topic was last
 * shown. It depends on every earlier day, so replay from the epoch (cheap, and cached so that
 * consecutive days only replay the difference).
 */
function stateAt(day: number, d: Decks): History {
	if (day < d.day) {
		d.day = 0;
		d.state = { positions: new Map(), lastUsed: new Map() };
	}
	for (; d.day < day; d.day++) {
		advance(d.state, d.day, topicsFor(keyFromIndex(d.day), d, d.state));
	}
	return cloneHistory(d.state);
}

export function pickDaily(key: string, pool: readonly Question[]): DailySet {
	const sorted = [...pool].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
	const poolKey = `${sorted.length}:${sorted[0]?.id}:${sorted.at(-1)?.id}`;
	let decks = decksByPool.get(poolKey);
	if (!decks) {
		decks = buildDecks(sorted);
		decksByPool.set(poolKey, decks);
	}
	const day = Math.max(0, dayIndex(key));
	const history = stateAt(day, decks);
	const pos = history.positions;
	const topics = topicsFor(keyFromIndex(day), decks, history);
	const rng = rngFromString(`${SALT}:v${POOL_VERSION}:${key}`);

	const take = (deck: string, cards: Question[]): Question => {
		const p = pos.get(deck) ?? 0;
		pos.set(deck, p + 1);
		return deal(deck, cards, p);
	};
	const chosen: Question[] = [
		...topics.medium.map((t) => take(`medium:${t}`, decks.medium.get(t)!)),
		deal('curated', decks.curated, day),
		...topics.hard.map((t) => take(`hard:${t}`, decks.hard.get(t)!))
	];

	const questions: DailyQuestion[] = chosen.map((q) => {
		const wrong = shuffle(q.distractors, rng).slice(0, 3);
		return { ...q, options: shuffle([q.answer, ...wrong], rng) };
	});
	return { dateKey: key, number: puzzleNumber(key), questions };
}
