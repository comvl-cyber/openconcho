/**
 * Pure data transforms for the UI charts. No React, no SVG — just arrays the
 * chart components render. Fully unit-tested.
 */

import {
	CONCLUSION_TYPES,
	type ConclusionType,
	type Dream,
	type DreamCounts,
	type ExtendedConclusion,
	inferConclusionType,
} from "@/lib/dreams";

export interface HourBin extends DreamCounts {
	hour: number;
}

/** Bin conclusions by UTC hour-of-day, counting each reasoning level. */
export function dreamHourHistogram(conclusions: ExtendedConclusion[]): HourBin[] {
	const bins: HourBin[] = Array.from({ length: 24 }, (_, hour) => ({
		hour,
		explicit: 0,
		deductive: 0,
		inductive: 0,
		contradiction: 0,
		total: 0,
	}));
	for (const c of conclusions) {
		const t = Date.parse(c.created_at);
		if (!Number.isFinite(t)) continue;
		const hour = new Date(t).getUTCHours();
		const bin = bins[hour];
		bin[inferConclusionType(c)]++;
		bin.total++;
	}
	return bins;
}

/**
 * Count conclusions per time bucket across a [start, end) window. Returns a
 * flat zero series when there is nothing to plot; callers render an empty state.
 */
export function sparklineFromDreams(
	dreams: Pick<Dream, "earliestMs" | "latestMs">[],
	buckets: number,
	startMs: number,
	endMs: number,
): number[] {
	const span = endMs - startMs;
	if (!Number.isFinite(span) || span <= 0 || buckets < 1) return [0];
	const width = span / buckets;
	const out = new Array<number>(buckets).fill(0);
	for (const d of dreams) {
		const t = Math.min(Math.max(d.latestMs, startMs), endMs - 1);
		const idx = Math.floor((t - startMs) / width);
		if (idx >= 0 && idx < buckets) out[idx]++;
	}
	return out;
}

export interface LevelDistribution {
	levels: Record<ConclusionType, number>;
	total: number;
	max: number;
}

/** Count conclusions per reasoning level, plus the largest bucket for scaling. */
export function levelDistribution(conclusions: ExtendedConclusion[]): LevelDistribution {
	const levels: Record<ConclusionType, number> = {
		explicit: 0,
		deductive: 0,
		inductive: 0,
		contradiction: 0,
	};
	for (const c of conclusions) levels[inferConclusionType(c)]++;
	let total = 0;
	let max = 0;
	for (const t of CONCLUSION_TYPES) {
		total += levels[t];
		if (levels[t] > max) max = levels[t];
	}
	return { levels, total, max };
}

export interface PairFlow {
	observer: string;
	observed: string | null;
	count: number;
}

/** Aggregate conclusion counts per observer→observed pair, largest first. */
export function observerObservedFlow(conclusions: ExtendedConclusion[]): PairFlow[] {
	const map = new Map<string, PairFlow>();
	for (const c of conclusions) {
		const key = `${c.observer_id}→${c.observed_id ?? ""}`;
		const entry = map.get(key);
		if (entry) entry.count++;
		else map.set(key, { observer: c.observer_id, observed: c.observed_id ?? null, count: 1 });
	}
	return [...map.values()].sort((a, b) => b.count - a.count);
}
