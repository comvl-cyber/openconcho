import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SidebarProvider } from "@/components/layout/SidebarContext";
import { DemoProvider } from "@/context/DemoContext";
import { MetadataProvider } from "@/context/MetadataContext";
import { saveConfig } from "@/lib/config";
import { routeTree } from "@/routeTree.gen";

export function renderApp(path = "/workspaces") {
	const router = createRouter({
		routeTree,
		history: createMemoryHistory({ initialEntries: [path] }),
	});
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	render(
		<QueryClientProvider client={client}>
			<DemoProvider>
				<MetadataProvider>
					<SidebarProvider>
						<RouterProvider router={router} />
					</SidebarProvider>
				</MetadataProvider>
			</DemoProvider>
		</QueryClientProvider>,
	);
	return client;
}

afterEach(() => {
	vi.unstubAllGlobals();
	delete window.__OPENCONCHO_REQUIRE_APP_AUTH__;
});

it("never starts protected route or sidebar queries while unauthorized", async () => {
	window.__OPENCONCHO_REQUIRE_APP_AUTH__ = true;
	saveConfig({ baseUrl: "https://honcho.test", token: "" });
	const requested: string[] = [];
	vi.stubGlobal(
		"fetch",
		vi.fn(async (input: RequestInfo | URL) => {
			const url = input instanceof Request ? input.url : String(input);
			requested.push(url);
			return new Response(JSON.stringify({ error: "Sign in required" }), {
				status: 401,
				headers: { "Content-Type": "application/json" },
			});
		}),
	);
	const client = renderApp();
	await screen.findByRole("button", { name: "Sign in" });
	expect(
		client
			.getQueryCache()
			.getAll()
			.map((query) => query.queryKey),
	).toEqual([["model-admin-session"]]);
});
