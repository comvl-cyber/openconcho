import { describe, expect, it } from "vitest";
import {
	dreamHourHistogram,
	levelDistribution,
	observerObservedFlow,
	sparklineFromDreams,
} from "@/lib/charts";
import type { ExtendedConclusion } from "@/lib/dreams";

function c(overrides: Partial<ExtendedConclusion>): ExtendedConclusion {
	return {
		id: "id",
		content: "content",
		observer_id: "obs-a",
		observed_id: "obs-b",
		session_id: null,
		created_at: "2026-01-01T05:30:00Z",
		...overrides,
	} as ExtendedConclusion;
}

describe("dreamHourHistogram", () => {
	it("returns 24 buckets with zeroed levels", () => {
		const bins = dreamHourHistogram([]);
		expect(bins).toHaveLength(24);
		expect(bins[0]).toEqual({
			hour: 0,
			explicit: 0,
			deductive: 0,
			inductive: 0,
			contradiction: 0,
			total: 0,
		});
	});

	it("bins conclusions by UTC hour with level counts", () => {
		const bins = dreamHourHistogram([
			c({ id: "1", level: "explicit" }),
			c({ id: "2", level: "deductive" }),
			c({ id: "3", level: "deductive", created_at: "2026-01-01T05:59:00Z" }),
			c({ id: "4", level: "inductive", created_at: "2026-01-01T23:10:00Z" }),
		]);
		expect(bins[5]).toEqual({
			hour: 5,
			explicit: 1,
			deductive: 2,
			inductive: 0,
			contradiction: 0,
			total: 3,
		});
		expect(bins[23].inductive).toBe(1);
		expect(bins[0].total).toBe(0);
	});

	it("treats missing levels as explicit", () => {
		const bins = dreamHourHistogram([c({ id: "x" })]);
		expect(bins[5].explicit).toBe(1);
	});
});

describe("sparklineFromDreams", () => {
	it("produces bucket counts across the requested window", () => {
		const dreams = [
			{
				earliestMs: Date.parse("2026-01-01T01:00:00Z"),
				latestMs: Date.parse("2026-01-01T01:05:00Z"),
			},
			{
				earliestMs: Date.parse("2026-01-01T01:30:00Z"),
				latestMs: Date.parse("2026-01-01T01:35:00Z"),
			},
			{
				earliestMs: Date.parse("2026-01-01T03:00:00Z"),
				latestMs: Date.parse("2026-01-01T03:02:00Z"),
			},
		];
		const points = sparklineFromDreams(
			dreams as never[],
			24,
			Date.parse("2026-01-01T00:00:00Z"),
			Date.parse("2026-01-02T00:00:00Z"),
		);
		expect(points).toHaveLength(24);
		expect(points[1]).toBe(2);
		expect(points[3]).toBe(1);
		expect(points[0]).toBe(0);
	});

	it("handles an empty dream list with a flat zero series", () => {
		expect(sparklineFromDreams([], 12, 0, 1)).toEqual(new Array(12).fill(0));
		expect(sparklineFromDreams([], 12, 1000, 2000)).toEqual(new Array(12).fill(0));
	});
});

describe("levelDistribution", () => {
	it("counts conclusions by level with total and max", () => {
		const dist = levelDistribution([
			c({ id: "1", level: "explicit" }),
			c({ id: "2", level: "explicit" }),
			c({ id: "3", level: "deductive" }),
			c({ id: "4", level: "inductive" }),
			c({ id: "5" }),
		]);
		expect(dist.total).toBe(5);
		expect(dist.max).toBe(3);
		expect(dist.levels.explicit).toBe(3);
		expect(dist.levels.deductive).toBe(1);
		expect(dist.levels.inductive).toBe(1);
		expect(dist.levels.contradiction).toBe(0);
	});

	it("is empty for empty input", () => {
		const dist = levelDistribution([]);
		expect(dist.total).toBe(0);
		expect(dist.max).toBe(0);
	});
});

describe("observerObservedFlow", () => {
	it("aggregates conclusion counts per observer→observed pair, sorted desc", () => {
		const flows = observerObservedFlow([
			c({ id: "1", observer_id: "obs-a", observed_id: "obs-b" }),
			c({ id: "2", observer_id: "obs-a", observed_id: "obs-b" }),
			c({ id: "3", observer_id: "obs-c", observed_id: "obs-b" }),
		]);
		expect(flows).toEqual([
			{ observer: "obs-a", observed: "obs-b", count: 2 },
			{ observer: "obs-c", observed: "obs-b", count: 1 },
		]);
	});

	it("falls back to a null-safe label for missing observed_id", () => {
		const flows = observerObservedFlow([c({ observed_id: undefined as unknown as string })]);
		const [flow] = flows;
		expect(flow?.observed).toBeNull();
		expect(flows).toHaveLength(1);
	});
});
