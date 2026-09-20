import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ModelManager } from "./ModelManager";

afterEach(() => vi.unstubAllGlobals());

it("disables apply until the selected model has passed a compatibility test", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string) => {
			const body = url.includes("session")
				? { csrf: "csrf", providers: [{ id: "openrouter", name: "OpenRouter", configured: true }] }
				: url.includes("catalog")
					? {
							models: [
								{
									id: "test/model",
									name: "Test model",
									input: "0.2",
									output: "0.4",
									cache: null,
									parameters: [],
								},
							],
							count: 1,
							currency: "USD",
							source: "https://openrouter.ai/api/v1/models",
							fetchedAt: "2026-09-20",
						}
					: {
							revision: "rev",
							model: "current",
							provider: "openrouter",
							previous: {},
							state: "Ready",
							slots: {},
							deployments: [],
							embedding: "baai/bge-m3",
						};
			return new Response(JSON.stringify(body), {
				headers: { "Content-Type": "application/json" },
			});
		}),
	);
	render(
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
		>
			<ModelManager />
		</QueryClientProvider>,
	);
	fireEvent.click(await screen.findByRole("button", { name: "Select test/model" }));
	expect(screen.getByRole("button", { name: "Apply model via GitOps" })).toBeDisabled();
});

it("explains authentication failures without exposing a credential form", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn(
			async () =>
				new Response(
					JSON.stringify({
						error:
							"Model administration is not enabled on this server. An operator must deploy the private admin service.",
					}),
					{ status: 401, headers: { "Content-Type": "application/json" } },
				),
		),
	);
	render(
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
		>
			<ModelManager />
		</QueryClientProvider>,
	);
	expect(await screen.findByText(/Model administration is not enabled/)).toBeInTheDocument();
});
