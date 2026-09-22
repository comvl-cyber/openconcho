import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PipelineExplainer } from "@/components/explainers/PipelineExplainer";

describe("PipelineExplainer", () => {
	it("renders all pipeline stages by default", () => {
		render(<PipelineExplainer />);
		expect(screen.getByText("Messages")).toBeTruthy();
		expect(screen.getByText("Dreams")).toBeTruthy();
		expect(screen.getByText("Dialectic recall")).toBeTruthy();
	});

	it("renders in compact variant only after expanding", () => {
		render(<PipelineExplainer variant="compact" />);
		expect(screen.queryByText("Conclusions")).toBeNull();
		fireEvent.click(screen.getByRole("button"));
		expect(screen.getByText("Conclusions")).toBeTruthy();
	});
});
