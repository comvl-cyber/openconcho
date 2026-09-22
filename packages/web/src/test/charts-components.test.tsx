import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HourHistogram } from "@/components/charts/HourHistogram";
import { LevelBarChart } from "@/components/charts/LevelBarChart";
import { PairFlowChart } from "@/components/charts/PairFlowChart";
import { Sparkline } from "@/components/charts/Sparkline";

describe("Sparkline", () => {
	it("renders a polyline path and keeps an accessible label", () => {
		render(<Sparkline points={[0, 2, 1]} label="Dreams per day" />);
		expect(screen.getByRole("img", { name: "Dreams per day" })).toBeTruthy();
		expect(document.querySelector("polyline[chart-sparkline]")).toBeTruthy();
	});

	it("renders a flat line when all points are zero", () => {
		render(<Sparkline points={[0, 0, 0]} label="flat" />);
		expect(document.querySelector("polyline[chart-sparkline]")).toBeTruthy();
	});
});

describe("HourHistogram", () => {
	it("renders 24 hour cells with hour labels", () => {
		const bins = Array.from({ length: 24 }, (_, hour) => ({
			hour,
			explicit: 0,
			deductive: 0,
			inductive: 0,
			contradiction: 0,
			total: 0,
		}));
		bins[9].deductive = 3;
		render(<HourHistogram bins={bins} label="Dream activity by hour" />);
		expect(screen.getByRole("img", { name: "Dream activity by hour" })).toBeTruthy();
		expect(document.querySelectorAll("[data-hour-cell]")).toHaveLength(24);
	});

	it("marks active cells with a data attribute value", () => {
		const bins = Array.from({ length: 24 }, (_, hour) => ({
			hour,
			explicit: 0,
			deductive: 0,
			inductive: 0,
			contradiction: 0,
			total: 0,
		}));
		bins[3].explicit = 5;
		bins[3].total = 5;
		render(<HourHistogram bins={bins} label="hist" />);
		const active = document.querySelector('[data-hour-cell="3"]');
		expect(active?.getAttribute("data-active")).toBe("true");
	});
});

describe("LevelBarChart", () => {
	it("renders one bar row per reasoning level with counts", () => {
		render(
			<LevelBarChart
				distribution={{
					levels: { explicit: 4, deductive: 2, inductive: 1, contradiction: 0 },
					total: 7,
					max: 4,
				}}
			/>,
		);
		expect(screen.getByText("Explicit")).toBeTruthy();
		expect(screen.getByText("4")).toBeTruthy();
		expect(screen.getByText("Deductive")).toBeTruthy();
		expect(screen.getByText("Contradiction")).toBeTruthy();
	});
});

describe("PairFlowChart", () => {
	it("renders rows for each observer→observed pair", () => {
		render(
			<PairFlowChart
				flows={[
					{ observer: "alice", observed: "bob", count: 3 },
					{ observer: "carol", observed: null, count: 1 },
				]}
			/>,
		);
		expect(screen.getByText("alice")).toBeTruthy();
		expect(screen.getByText("bob")).toBeTruthy();
		expect(screen.getByText("(unassigned)")).toBeTruthy();
		expect(screen.getByText("3")).toBeTruthy();
	});
});
