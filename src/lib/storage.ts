import { POOL_VERSION } from './daily.ts';

const PREFIX = 'ost:v1:';
/** Saved answers are option indices, so they are only valid for the pool version they were made with. */
const dayKey = (dateKey: string) => `day:p${POOL_VERSION}:${dateKey}`;

export interface DayState {
	/** Index into the shuffled options chosen for each question, or null when unanswered. */
	answers: (number | null)[];
	correct: (boolean | null)[];
}

export interface Stats {
	played: number;
	perfect: number;
	streak: number;
	maxStreak: number;
	lastPlayed: string | null;
	/** distribution[score] = number of days with that score (0..5). */
	distribution: number[];
}

const emptyStats = (): Stats => ({
	played: 0,
	perfect: 0,
	streak: 0,
	maxStreak: 0,
	lastPlayed: null,
	distribution: [0, 0, 0, 0, 0, 0]
});

function read<T>(key: string): T | null {
	try {
		const raw = localStorage.getItem(PREFIX + key);
		return raw ? (JSON.parse(raw) as T) : null;
	} catch {
		return null;
	}
}

function write(key: string, value: unknown): void {
	try {
		localStorage.setItem(PREFIX + key, JSON.stringify(value));
	} catch {
		/* storage unavailable (private mode, blocked): game still works for this session */
	}
}

export function loadDay(dateKey: string, size: number): DayState {
	const s = read<DayState>(dayKey(dateKey));
	if (s && s.answers?.length === size) return s;
	return { answers: Array(size).fill(null), correct: Array(size).fill(null) };
}

export function saveDay(dateKey: string, state: DayState): void {
	write(dayKey(dateKey), state);
}

export function loadStats(): Stats {
	return { ...emptyStats(), ...(read<Stats>('stats') ?? {}) };
}

/** Record a finished *live* day (replays never count). Idempotent per dateKey. */
export function recordResult(dateKey: string, previousKey: string, score: number, total: number): Stats {
	const stats = loadStats();
	if (stats.lastPlayed === dateKey) return stats;
	stats.played += 1;
	if (score === total) stats.perfect += 1;
	stats.distribution[score] = (stats.distribution[score] ?? 0) + 1;
	// A day counts toward the streak when at least 3 of 5 are right.
	const passed = score >= Math.ceil(total / 2);
	stats.streak = passed ? (stats.lastPlayed === previousKey ? stats.streak + 1 : 1) : 0;
	stats.maxStreak = Math.max(stats.maxStreak, stats.streak);
	stats.lastPlayed = dateKey;
	write('stats', stats);
	return stats;
}
