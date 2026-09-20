import { useQuery } from "@tanstack/react-query";

export interface AdminSession {
	csrf: string;
	providers: { id: string; name: string; configured: boolean }[];
}
export interface ModelCatalog {
	models: {
		id: string;
		name: string;
		input: string | null;
		output: string | null;
		cache: string | null;
		context?: number;
		parameters: string[];
	}[];
	count: number;
	currency: string | null;
	source: string;
	fetchedAt: string;
}
export interface ModelStatus {
	revision: string;
	model: string;
	provider: string;
	previous: { model?: string; provider?: string };
	state: string;
	slots: Record<string, string>;
	deployments: { name: string; ready: boolean }[];
	embedding: string;
}
export interface CompatibilityResult {
	proof: string;
	revision: string;
	passed: boolean;
	policy: string;
	results: {
		name: string;
		passed: boolean;
		detail: string;
		milliseconds: number;
		parameters?: Record<string, unknown>;
	}[];
}

export async function adminRequest<T>(path: string, csrf?: string, body?: unknown): Promise<T> {
	const response = await fetch(`/admin-api/${path}`, {
		method: body ? "POST" : "GET",
		credentials: "same-origin",
		cache: "no-store",
		signal: AbortSignal.timeout(body ? 360_000 : 60_000),
		headers: body ? { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" } : {},
		body: body ? JSON.stringify(body) : undefined,
	});
	if (!response.headers.get("Content-Type")?.includes("application/json")) {
		throw new Error(
			"Model administration is not enabled on this server. An operator must deploy the private admin service.",
		);
	}
	const result = await response.json();
	if (!response.ok)
		throw new Error(
			typeof result.error === "string" ? result.error : "Administrator request failed",
		);
	return result as T;
}

export function useAdminSession() {
	return useQuery({
		queryKey: ["model-admin-session"],
		queryFn: () => adminRequest<AdminSession>("session"),
		retry: false,
	});
}
export function useModelStatus(enabled: boolean) {
	return useQuery({
		queryKey: ["model-admin-status"],
		queryFn: () => adminRequest<ModelStatus>("status"),
		enabled,
		retry: false,
		refetchInterval: enabled ? 15_000 : false,
	});
}
export function useModelCatalog(provider: string, enabled: boolean) {
	return useQuery({
		queryKey: ["model-admin-catalog", provider],
		queryFn: () => adminRequest<ModelCatalog>(`catalog?provider=${encodeURIComponent(provider)}`),
		enabled,
		retry: false,
		staleTime: 300_000,
	});
}
