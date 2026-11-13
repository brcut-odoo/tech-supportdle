import curated from './data/curated.json';
import generated from './data/generated.json';
import type { Question } from './types';

type CuratedEntry = Omit<Question, 'family'> & {
	/** Ids of generated questions about the same fact; they are dropped so the two never meet. */
	supersedes?: string[];
};

const entries = curated.questions as CuratedEntry[];
const superseded = new Set(entries.flatMap((q) => q.supersedes ?? []));

const curatedQs: Question[] = entries.map(({ supersedes: _s, ...q }) => ({ ...q, family: 'curated' }));

export const pool: Question[] = [
	...(generated.questions as Question[]).filter((q) => !superseded.has(q.id)),
	...curatedQs
];
export const meta = generated as unknown as { meta?: Record<string, unknown> };
