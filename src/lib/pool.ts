import curated from './data/curated.json';
import generated from './data/generated.json';
import type { Question } from './types';

const curatedQs: Question[] = (curated.questions as Omit<Question, 'family'>[]).map((q) => ({
	...q,
	family: 'curated'
})) as Question[];

export const pool: Question[] = [...(generated.questions as Question[]), ...curatedQs];
export const meta = generated as unknown as { meta?: Record<string, unknown> };
