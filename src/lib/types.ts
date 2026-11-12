export interface Question {
	/** Stable identifier, e.g. `model-name:sale.order`. Pool order is derived from it. */
	id: string;
	family: string;
	difficulty: 1 | 2 | 3;
	question: string;
	answer: string;
	/** At least 3 wrong answers; 3 of them are shown per day. */
	distractors: string[];
	explanation: string;
	/** Path inside the Odoo checkout, optionally with `:line`. */
	source: string;
	/** Optional inline code shown under the question (error message, snippet). */
	code?: string;
}

export interface DailyQuestion extends Question {
	options: string[];
}

export interface DailySet {
	dateKey: string;
	number: number;
	questions: DailyQuestion[];
}
