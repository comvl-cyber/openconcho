import { describe, expect, it } from "vitest";
import {
	getLevelExplanation,
	isMemoryLevel,
	MEMORY_LEVELS,
	MEMORY_PIPELINE,
} from "@/lib/explainers";

describe("MEMORY_PIPELINE", () => {
	it("describes the five stages of the Honcho memory model in order", () => {
		expect(MEMORY_PIPELINE.map((s) => s.id)).toEqual([
			"messages",
			"working-representation",
			"conclusions",
			"dreams",
			"dialectic",
		]);
	});

	it("gives every stage a plain-language title, summary, and detail", () => {
		for (const stage of MEMORY_PIPELINE) {
			expect(stage.title.length).toBeGreaterThan(0);
			expect(stage.summary.length).toBeGreaterThan(0);
			expect(stage.detail.length).toBeGreaterThan(0);
		}
	});
});

describe("MEMORY_LEVELS", () => {
	it("covers explicit, deductive, and inductive", () => {
		expect(Object.keys(MEMORY_LEVELS).sort()).toEqual(["deductive", "explicit", "inductive"]);
	});

	it("explains each level in plain language", () => {
		for (const info of Object.values(MEMORY_LEVELS)) {
			expect(info.label.length).toBeGreaterThan(0);
			expect(info.explanation.length).toBeGreaterThan(0);
		}
	});
});

describe("getLevelExplanation", () => {
	it("returns the entry for a known level", () => {
		expect(getLevelExplanation("explicit")?.label).toBe("Explicit");
	});

	it("returns undefined for an unknown level", () => {
		expect(getLevelExplanation("telepathic")).toBeUndefined();
	});
});

describe("isMemoryLevel", () => {
	it("narrows known levels", () => {
		expect(isMemoryLevel("deductive")).toBe(true);
		expect(isMemoryLevel("guess")).toBe(false);
	});
});
