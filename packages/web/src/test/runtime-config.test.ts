import { afterEach, describe, expect, it } from "vitest";
import { defaultHonchoUrl } from "@/lib/runtimeConfig";

const KEY = "__OPENCONCHO_DEFAULT_HONCHO_URL__";

afterEach(() => {
	delete (globalThis as Record<string, unknown>)[KEY];
});

describe("defaultHonchoUrl", () => {
	it("returns an injected absolute URL verbatim", () => {
		(globalThis as Record<string, unknown>)[KEY] = "https://honcho.example.net";
		expect(defaultHonchoUrl()).toBe("https://honcho.example.net");
	});

	it("returns null when unset or empty", () => {
		expect(defaultHonchoUrl()).toBeNull();
		(globalThis as Record<string, unknown>)[KEY] = "   ";
		expect(defaultHonchoUrl()).toBeNull();
	});
});
