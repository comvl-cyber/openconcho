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
	state: string;
	slots: Record<string, string>;
	deployments: { name: string; ready: boolean }[];
	embedding: string;
}
export interface CompatibilityResult {
	revision: string;
	passed: boolean;
	policy: string;
	proof?: string;
	expiresAt?: string;
	results: {
		name: string;
		passed: boolean;
		detail: string;
		milliseconds: number;
		parameters?: Record<string, unknown>;
	}[];
}

export interface ProviderPreset {
	id: string;
	name: string;
	url: string;
	credentialRef: string;
}

export interface AdminSession {
	csrf: string;
	providers: { id: string; name: string; configured: boolean }[];
	providerPresets: ProviderPreset[];
	favorites: { provider: string; model: string }[];
}

export interface AdminRequest {
	id: string;
	kind: "model-switch" | "model-add" | "provider-upsert";
	status: "queued" | "running" | "applied" | "rejected" | "failed";
	createdAt: string;
	updatedAt: string;
	submittedBy: string;
	payload: {
		provider: string;
		model?: string;
		revision?: string;
		proof?: string;
		validation?: { passed: boolean; testedAt: string; expiresAt: string };
		preset?: string;
		name?: string;
		url?: string;
		credentialRef?: string;
	};
	result?: { message: string; revision: string };
}

export class AdminError extends Error {
	constructor(message: string, status: number) {
		super(message);
		this.status = status;
	}
	public readonly status: number;
}

export const ADMIN_SESSION_KEY = ["model-admin-session"];
export const ADMIN_UNAUTHORIZED_EVENT = "openconcho:session-expired";

export async function adminRequest<T>(
	path: string,
	csrf?: string,
	body?: unknown,
	signal?: AbortSignal,
): Promise<T> {
	const response = await fetch(`/admin-api/${path}`, {
		method: body ? "POST" : "GET",
		credentials: "same-origin",
		cache: "no-store",
		signal: signal
			? AbortSignal.any([signal, AbortSignal.timeout(body ? 360_000 : 60_000)])
			: AbortSignal.timeout(body ? 360_000 : 60_000),
		headers: body ? { "Content-Type": "application/json", "X-CSRF-Token": csrf ?? "" } : {},
		body: body ? JSON.stringify(body) : undefined,
	});
	if (response.status === 401 && path !== "login" && path !== "session") {
		window.dispatchEvent(new Event(ADMIN_UNAUTHORIZED_EVENT));
	}
	if (!response.headers.get("Content-Type")?.includes("application/json")) {
		throw new Error(
			"Model administration is not enabled on this server. An operator must deploy the private admin service.",
		);
	}
	const result = await response.json();
	if (!response.ok)
		throw new AdminError(
			typeof result.error === "string" ? result.error : "Administrator request failed",
			response.status,
		);
	return result as T;
}

export function useAdminSession(enabled = true) {
	return useQuery({
		queryKey: ADMIN_SESSION_KEY,
		queryFn: ({ signal }) => adminRequest<AdminSession>("session", undefined, undefined, signal),
		enabled,
		refetchInterval: enabled ? 60_000 : false,
		staleTime: 30_000,
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

export function useProviderPresets(enabled: boolean) {
	return useQuery({
		queryKey: ["model-admin-presets"],
		queryFn: () => adminRequest<ProviderPreset[]>("presets"),
		enabled,
		retry: false,
		staleTime: 300_000,
	});
}

export function useAdminRequests(enabled: boolean) {
	return useQuery({
		queryKey: ["model-admin-requests"],
		queryFn: () => adminRequest<{ requests: AdminRequest[]; count: number }>("requests"),
		enabled,
		retry: false,
		refetchInterval: enabled ? 10_000 : false,
	});
}

export async function queueModelSwitch(
	csrf: string,
	provider: string,
	model: string,
	revision: string,
	proof: string,
) {
	return adminRequest<{ request: AdminRequest }>("requests", csrf, {
		kind: "model-switch",
		provider,
		model,
		revision,
		proof,
	});
}

export async function queueModelAdd(csrf: string, provider: string, model: string) {
	return adminRequest<{ request: AdminRequest }>("requests", csrf, {
		kind: "model-add",
		provider,
		model,
	});
}

export async function queueProviderUpsert(
	csrf: string,
	preset: string,
	name: string,
	url: string,
	credentialRef: string,
) {
	return adminRequest<{ request: AdminRequest }>("requests", csrf, {
		kind: "provider-upsert",
		preset,
		name,
		url,
		credentialRef,
	});
}
