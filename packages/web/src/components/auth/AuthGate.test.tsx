import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AuthGate, LogoutButton } from "./AuthGate";

vi.mock("@/lib/runtimeConfig", () => ({ requireAppAuth: () => true }));

function jsonResponse(body: unknown, status = 200) {
	return new Response(JSON.stringify(body), {
		status,
		headers: { "Content-Type": "application/json" },
	});
}

afterEach(() => vi.unstubAllGlobals());

function PrivateContent() {
	useQuery({ queryKey: ["private"], queryFn: () => fetch("/api/private") });
	return <p>Private workspace</p>;
}

it("does not mount protected queries when the session is unauthorized", async () => {
	const fetcher = vi.fn(async () => jsonResponse({ error: "Sign in required" }, 401));
	vi.stubGlobal("fetch", fetcher);
	render(
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
		>
			<AuthGate>
				<PrivateContent />
			</AuthGate>
		</QueryClientProvider>,
	);
	await screen.findByRole("button", { name: "Sign in" });
	expect(fetcher.mock.calls).toHaveLength(1);
});

it.each([
	200, 503,
])("clears private queries and hides protected content on logout (%s)", async (status) => {
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string) =>
			url.endsWith("logout")
				? jsonResponse(status === 200 ? { ok: true } : { error: "Sign out unavailable" }, status)
				: jsonResponse({ csrf: "test-csrf", providers: [] }),
		),
	);
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	client.setQueryData(["private-memory"], { secret: "private-test-data" });
	render(
		<QueryClientProvider client={client}>
			<AuthGate>
				<PrivateContent />
				<LogoutButton />
			</AuthGate>
		</QueryClientProvider>,
	);
	await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
	await screen.findByRole("button", { name: status === 200 ? "Sign in" : "Retry sign out" });
	expect(client.getQueryData(["private-memory"])).toBeUndefined();
});

it("shows a recoverable service error rather than an unlocked application", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn(async () => jsonResponse({ error: "Session service unavailable" }, 503)),
	);
	render(
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
		>
			<AuthGate>
				<PrivateContent />
			</AuthGate>
		</QueryClientProvider>,
	);
	expect(await screen.findByRole("button", { name: "Retry connection" })).toBeInTheDocument();
});

it("verifies the cookie session after signing in before showing private content", async () => {
	let authenticated = false;
	vi.stubGlobal(
		"fetch",
		vi.fn(async (url: string) => {
			if (url.endsWith("login")) {
				authenticated = true;
				return jsonResponse({ ok: true });
			}
			return authenticated
				? jsonResponse({ csrf: "test-csrf", providers: [] })
				: jsonResponse({ error: "Sign in required" }, 401);
		}),
	);
	render(
		<QueryClientProvider
			client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
		>
			<AuthGate>
				<PrivateContent />
			</AuthGate>
		</QueryClientProvider>,
	);
	const user = userEvent.setup();
	await user.type(await screen.findByLabelText("Username"), "operator");
	await user.type(screen.getByLabelText("Password"), "test-only-password");
	await user.click(screen.getByRole("button", { name: "Sign in" }));
	expect(await screen.findByText("Private workspace")).toBeInTheDocument();
});
