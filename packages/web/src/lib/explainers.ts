/**
 * Plain-language content about the Honcho memory model, shared by the
 * explainer panels and tooltips. Pure data — no React — so it is fully unit
 * tested and safe to reuse anywhere in the app.
 */

export type MemoryLevel = "explicit" | "deductive" | "inductive";

export interface MemoryPipelineStage {
	id: string;
	title: string;
	/** One sentence, plain language. */
	summary: string;
	/** A little more detail for readers who want it. */
	detail: string;
}

export const MEMORY_PIPELINE: MemoryPipelineStage[] = [
	{
		id: "messages",
		title: "Messages",
		summary: "Raw conversation turns between your app and a peer.",
		detail:
			"Everything starts here: the plain chat history stored per session. Nothing is interpreted yet — Honcho keeps the original words.",
	},
	{
		id: "working-representation",
		title: "Working representation",
		summary: "A living summary of what a peer is like, updated as messages arrive.",
		detail:
			"Honcho distills the message stream into a compact profile of the peer. It's rewritten continuously, so it always reflects the latest conversation.",
	},
	{
		id: "conclusions",
		title: "Conclusions",
		summary: "Named facts Honcho has decided are true about a peer.",
		detail:
			"Derived from the working representation, each conclusion is a standalone statement (with a confidence level) you can browse, search, and delete individually.",
	},
	{
		id: "dreams",
		title: "Dreams",
		summary: "Background runs that consolidate conclusions while the peer is idle.",
		detail:
			"A dream processes the accumulated conclusions — merging duplicates, resolving contradictions, and generalizing — then writes back cleaner, higher-level conclusions.",
	},
	{
		id: "dialectic",
		title: "Dialectic recall",
		summary: "On-demand answers that reason over everything Honcho knows.",
		detail:
			"When your app asks a question, Honcho reasons across messages, representation, and conclusions to produce a grounded answer instead of a flat lookup.",
	},
];

export interface MemoryLevelInfo {
	level: MemoryLevel;
	label: string;
	explanation: string;
}

export const MEMORY_LEVELS: Record<MemoryLevel, MemoryLevelInfo> = {
	explicit: {
		level: "explicit",
		label: "Explicit",
		explanation:
			"Directly stated in the conversation — quoted or paraphrased from what was actually said. The safest kind of memory.",
	},
	deductive: {
		level: "deductive",
		label: "Deductive",
		explanation:
			"Logically derived from explicit statements. If a peer says they take the train every weekday, 'commutes by train' is deductive.",
	},
	inductive: {
		level: "inductive",
		label: "Inductive",
		explanation:
			"A pattern generalized from repeated observations. Useful, but a guess — treat inductive conclusions as likely rather than certain.",
	},
};

export function getLevelExplanation(level: string): MemoryLevelInfo | undefined {
	return isMemoryLevel(level) ? MEMORY_LEVELS[level] : undefined;
}

export function isMemoryLevel(level: string): level is MemoryLevel {
	return level === "explicit" || level === "deductive" || level === "inductive";
}
