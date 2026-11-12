import { rngFromString, shuffle } from './rng';
import type { DailyQuestion, DailySet, Question } from './types';

/** Bump only on purpose: changes every past and future daily set. */
export const POOL_VERSION = 1;
/** Puzzle #1. */
export const EPOCH = '2026-11-12';
const SALT = 'odoo-support-trivia';
const DAY_MS = 86_400_000;

/**
 * Daily composition. Each bucket is a "deck": a seeded shuffle of its questions.
 * Day N deals the next cards, so nothing repeats until a deck is exhausted,
 * after which it is reshuffled with a new seed (the cycle number).
 */
const SLOTS: { bucket: string; count: number; match: (q: Question) => boolean }[] = [
	{ bucket: 'easy', count: 2, match: (q) => q.family !== 'curated' && q.difficulty === 1 },
	{ bucket: 'curated', count: 1, match: (q) => q.family === 'curated' },
	{ bucket: 'medium', count: 1, match: (q) => q.family !== 'curated' && q.difficulty === 2 },
	{ bucket: 'hard', count: 1, match: (q) => q.family !== 'curated' && q.difficulty === 3 }
];

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

const deckCache = new Map<string, Question[]>();

function deal(bucket: string, cards: Question[], position: number): Question {
	const cycle = Math.floor(position / cards.length);
	const cacheKey = `${bucket}:${cycle}:${cards.length}`;
	let deck = deckCache.get(cacheKey);
	if (!deck) {
		deck = shuffle(cards, rngFromString(`${SALT}:v${POOL_VERSION}:${bucket}:cycle${cycle}`));
		deckCache.set(cacheKey, deck);
	}
	return deck[position % cards.length];
}

export function pickDaily(key: string, pool: readonly Question[]): DailySet {
	const sorted = [...pool].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
	const day = Math.max(0, dayIndex(key));
	const rng = rngFromString(`${SALT}:v${POOL_VERSION}:${key}`);
	const used = new Set<string>();
	const questions: DailyQuestion[] = [];

	for (const slot of SLOTS) {
		let cards = sorted.filter(slot.match);
		if (cards.length < slot.count) cards = sorted; // degenerate pool fallback
		for (let i = 0; i < slot.count; i++) {
			let pos = day * slot.count + i;
			let q = deal(slot.bucket, cards, pos);
			// Guard against the fallback deck re-dealing a question already chosen today.
			for (let tries = 0; used.has(q.id) && tries < cards.length; tries++) {
				q = deal(slot.bucket, cards, ++pos + 7919);
			}
			used.add(q.id);
			const wrong = shuffle(q.distractors, rng).slice(0, 3);
			questions.push({ ...q, options: shuffle([q.answer, ...wrong], rng) });
		}
	}
	return { dateKey: key, number: puzzleNumber(key), questions };
}
