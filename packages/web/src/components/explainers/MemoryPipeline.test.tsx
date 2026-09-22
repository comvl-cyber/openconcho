import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryPipeline } from "@/components/explainers/MemoryPipeline";

describe("MemoryPipeline", () => {
	it("renders a summary button describing the memory model", () => {
		render(<MemoryPipeline />);
		const trigger = screen.getByRole("button");
		expect(trigger.getAttribute("aria-expanded")).toBe("false");
		expect(trigger.textContent).toContain("How Honcho remembers");
	});

	it("expands to reveal all five pipeline stages", () => {
		render(<MemoryPipeline defaultOpen />);
		for (const title of [
			"Messages",
			"Working representation",
			"Conclusions",
			"Dreams",
			"Dialectic recall",
		]) {
			expect(screen.getByText(title)).toBeTruthy();
		}
	});

	it("toggles open and closed on click", () => {
		render(<MemoryPipeline />);
		const trigger = screen.getByRole("button");
		expect(trigger.getAttribute("aria-expanded")).toBe("false");
		fireEvent.click(trigger);
		expect(trigger.getAttribute("aria-expanded")).toBe("true");
		expect(screen.getByText("Raw conversation turns between your app and a peer.")).toBeTruthy();
		fireEvent.click(trigger);
		expect(trigger.getAttribute("aria-expanded")).toBe("false");
	});

	it("marks the emphasized stage when requested", () => {
		render(<MemoryPipeline defaultOpen emphasize="dreams" />);
		const item = screen.getByTestId("pipeline-stage-dreams");
		expect(item.getAttribute("data-emphasized")).toBe("true");
	});
});
