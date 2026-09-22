import { useReducedMotion as useFramerReducedMotion } from "framer-motion";

/**
 * Boolean convenience wrapper around framer-motion's hook so components can
 * skip entrance animations entirely for users with reduced-motion enabled.
 */
export function useReducedMotion(): boolean {
	return Boolean(useFramerReducedMotion());
}
