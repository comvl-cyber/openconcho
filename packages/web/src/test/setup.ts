import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeAll, vi } from "vitest";

// jsdom defines scrollTo but leaves it unimplemented; router scroll restoration calls it.
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;

if (!window.matchMedia) {
	window.matchMedia = vi.fn().mockImplementation((query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: vi.fn(),
		removeListener: vi.fn(),
		addEventListener: vi.fn(),
		removeEventListener: vi.fn(),
		dispatchEvent: vi.fn(),
	}));
}

// localStorage is not available in jsdom by default; polyfill with an in-memory store.
const localStorageStore: Record<string, string> = {};
Object.defineProperty(window, "localStorage", {
	value: {
		getItem: (key: string) => localStorageStore[key] ?? null,
		setItem: (key: string, value: string) => {
			localStorageStore[key] = String(value);
		},
		removeItem: (key: string) => {
			delete localStorageStore[key];
		},
		clear: () => {
			for (const k of Object.keys(localStorageStore)) delete localStorageStore[k];
		},
		key: (index: number) => Object.keys(localStorageStore)[index] ?? null,
		get length() {
			return Object.keys(localStorageStore).length;
		},
	},
	writable: true,
	configurable: true,
});

beforeAll(() => {
	localStorage.clear();
});

afterEach(() => {
	cleanup();
	localStorage.clear();
});
