import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LevelBadge } from "@/components/explainers/LevelBadge";

describe("LevelBadge", () => {
	it("renders the level label", () => {
		render(<LevelBadge level="explicit" />);
		expect(screen.getByText("Explicit")).toBeTruthy();
	});

	it("exposes the plain-language explanation for assistive tech", () => {
		render(<LevelBadge level="inductive" />);
		const badge = screen.getByText("Inductive").closest("[data-testid='level-badge']");
		expect(badge).toBeTruthy();
	});

	it("renders the number of conclusions when provided", () => {
		render(<LevelBadge level="deductive" count={4} />);
		expect(screen.getByText("4")).toBeTruthy();
	});
});
