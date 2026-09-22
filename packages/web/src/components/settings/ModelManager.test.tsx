import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ModelManager } from "./ModelManager";

const session = {
	csrf: "csrf",
	providers: [
		{ id: "openrouter", name: "OpenRouter", configured: true },
		{ id: "openai", name: "OpenAI", configured: false },
	],
	providerPresets: [
		{
			id: "openai",
			name: "OpenAI",
			url: "https://api.openai.com/v1",
			credentialRef: "OPENAI_API_KEY",
		},
	],
	favorites: [{ provider: "openrouter", model: "test/model" }],
};
const catalog = {
	models: [
		{
			id: "test/model",
			name: "Test model",
			input: "0.2",
			output: "0.4",
			cache: null,
			parameters: ["tools"],
			context: 32000,
		},
		{
			id: "test/other",
			name: "Other model",
			input: null,
			output: null,
			cache: null,
			parameters: [],
		},
	],
	count: 2,
	currency: "USD",
	source: "provider catalog",
	fetchedAt: "2026-09-22T00:00:00Z",
};
const status = {
	revision: "rev",
	model: "current",
	provider: "openrouter",
	state: "Ready",
	slots: { DERIVER: "current" },
	deployments: [],
	embedding: "baai/bge-m3",
};
function response(body: unknown, code = 200) {
	return new Response(JSON.stringify(body), {
		status: code,
		headers: { "Content-Type": "application/json" },
	});
}
function setup(overrides: Record<string, unknown> = {}) {
	const writes: { path: string; body: Record<string, unknown> }[] = [];
	const requests: unknown[] = [];
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string, init?: RequestInit) => {
			const path = url.replace("/admin-api/", "").split("?")[0];
			if (init?.method === "POST") {
				const body = JSON.parse(String(init.body));
				writes.push({ path, body });
				if (path === "test")
					return response(
						overrides.test ?? {
							passed: true,
							revision: "rev",
							proof: "signed-proof",
							expiresAt: new Date(Date.now() + 600_000).toISOString(),
							results: [],
						},
					);
				const request = {
					id: `request-${requests.length}`,
					kind: body.kind,
					status: "queued",
					payload: body,
					createdAt: "2026-09-22T00:00:00Z",
					updatedAt: "2026-09-22T00:00:00Z",
					submittedBy: "operator",
				};
				requests.unshift(request);
				return response({ request }, 202);
			}
			return response(
				overrides[path] ??
					{ session, catalog, status, requests: { requests, count: requests.length } }[path],
			);
		}),
	);
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	render(
		<QueryClientProvider client={client}>
			<ModelManager />
		</QueryClientProvider>,
	);
	return { writes, client, user: userEvent.setup() };
}
afterEach(() => vi.unstubAllGlobals());

it("shows searchable price cards and a saved model library", async () => {
	const { user } = setup();
	await user.type(await screen.findByRole("searchbox", { name: "Search models" }), "Test model");
	const card = screen.getByRole("button", { name: "Select test/model" });
	expect({
		tabs: screen.getAllByRole("tab").map((tab) => tab.textContent),
		price: within(card).getByText("USD 0.2").textContent,
		other: screen.queryByRole("button", { name: "Select test/other" }),
		library: screen.getByRole("region", { name: "Saved model library" }).textContent,
	}).toMatchObject({
		tabs: ["Models", "Providers", "Activity"],
		price: "USD 0.2",
		other: null,
		library: expect.stringContaining("test/model"),
	});
});
