export function requireAppAuth(): boolean {
	return typeof window !== "undefined" && window.__OPENCONCHO_REQUIRE_APP_AUTH__ === true;
}

export function defaultHonchoUrl(): string | null {
	return typeof window !== "undefined" &&
		typeof window.__OPENCONCHO_DEFAULT_HONCHO_URL__ === "string"
		? window.__OPENCONCHO_DEFAULT_HONCHO_URL__.trim() || null
		: null;
}
