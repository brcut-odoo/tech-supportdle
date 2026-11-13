import { describe, expect, it } from 'vitest';
import { dateKeyUTC, dayIndex, isValidKey, keyFromIndex, pickDaily, puzzleNumber, topicOf } from '../src/lib/daily';
import { cyrb128, mulberry32 } from '../src/lib/rng';
import { pool } from '../src/lib/pool';
import type { Question } from '../src/lib/types';

const ids = (key: string, p: readonly Question[] = pool) => pickDaily(key, p).questions.map((q) => q.id);

describe('rng', () => {
	it('is deterministic', () => {
		const a = mulberry32(cyrb128('x')[0]);
		const b = mulberry32(cyrb128('x')[0]);
		expect([a(), a(), a()]).toEqual([b(), b(), b()]);
	});
});

describe('dates', () => {
	it('numbers puzzles from the epoch', () => {
		expect(puzzleNumber('2026-11-12')).toBe(1);
		expect(puzzleNumber('2026-11-13')).toBe(2);
		expect(keyFromIndex(dayIndex('2027-03-01'))).toBe('2027-03-01');
	});
	it('validates keys', () => {
		expect(isValidKey('2026-02-30')).toBe(false);
		expect(isValidKey('2026-12-01')).toBe(true);
		expect(isValidKey('nope')).toBe(false);
	});
	it('uses UTC', () => {
		expect(dateKeyUTC(new Date('2026-11-12T23:59:59Z'))).toBe('2026-11-12');
	});
});

describe('pickDaily', () => {
	it('has a usable pool', () => {
		expect(pool.filter((q) => q.family === 'curated').length).toBeGreaterThan(20);
		for (const d of [2, 3] as const) {
			expect(pool.filter((q) => q.family !== 'curated' && q.difficulty === d).length).toBeGreaterThan(20);
		}
		// Advanced audience: no easy generated questions, and enough hard ones for 3 a day.
		expect(pool.filter((q) => q.family !== 'curated' && q.difficulty === 1)).toHaveLength(0);
		expect(pool.filter((q) => q.family !== 'curated' && q.difficulty === 3).length).toBeGreaterThan(300);
	});

	it('is reproducible for the same date', () => {
		const a = pickDaily('2026-11-20', pool);
		const b = pickDaily('2026-11-20', [...pool].reverse());
		expect(b).toEqual(a);
	});

	it('gives 5 distinct questions with 4 distinct options including the answer', () => {
		for (let i = 0; i < 400; i++) {
			const set = pickDaily(keyFromIndex(i), pool);
			expect(set.questions).toHaveLength(5);
			expect(new Set(set.questions.map((q) => q.id)).size).toBe(5);
			for (const q of set.questions) {
				expect(q.options).toHaveLength(4);
				expect(new Set(q.options).size).toBe(4);
				expect(q.options).toContain(q.answer);
			}
		}
	});

	it('differs between days and does not repeat on consecutive days', () => {
		for (let i = 0; i < 60; i++) {
			const today = new Set(ids(keyFromIndex(i)));
			const tomorrow = ids(keyFromIndex(i + 1));
			expect(tomorrow.some((id) => today.has(id))).toBe(false);
		}
	});

	it('drops generated questions that a curated one supersedes', () => {
		const ids = new Set(pool.map((q) => q.id));
		expect(ids.has('config-param:mail.mail.force.send.limit')).toBe(false);
		expect(ids.has('server-option:limit_time_real_cron')).toBe(false);
		expect(ids.has('curated:force-send-limit')).toBe(true);
	});

	it('mixes topics: the 5 questions of a day never share a topic', () => {
		for (let i = 0; i < 400; i++) {
			const topics = pickDaily(keyFromIndex(i), pool).questions.map(topicOf);
			expect(new Set(topics).size, `day ${i}: ${topics.join(', ')}`).toBe(5);
		}
	});

	it('shows every topic regularly', () => {
		const lastSeen = new Map<string, number>();
		let worstGap = 0;
		for (let i = 0; i < 365; i++) {
			for (const t of pickDaily(keyFromIndex(i), pool).questions.map(topicOf)) {
				worstGap = Math.max(worstGap, i - (lastSeen.get(t) ?? 0));
				lastSeen.set(t, i);
			}
		}
		expect(lastSeen.size).toBeGreaterThanOrEqual(6);
		expect(worstGap).toBeLessThanOrEqual(5);
	});

	it('does not repeat a generated question within 30 days', () => {
		const seen = new Map<string, number>();
		for (let i = 0; i < 30; i++) {
			for (const q of pickDaily(keyFromIndex(i), pool).questions) {
				if (q.family === 'curated') continue;
				expect(seen.has(q.id), `${q.id} on day ${i} and ${seen.get(q.id)}`).toBe(false);
				seen.set(q.id, i);
			}
		}
	});
});
