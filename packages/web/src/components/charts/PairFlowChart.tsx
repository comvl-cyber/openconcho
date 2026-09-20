import { motion } from "framer-motion";
import { Caption, MonoCaption } from "@/components/ui/typography";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import type { PairFlow } from "@/lib/charts";
import { COLOR } from "@/lib/constants";

interface PairFlowChartProps {
	flows: PairFlow[];
}

/**
 * Simple observer→observed flow diagram: one row per pair with a proportional
 * connecting bar. Sankey-lite — no heavy deps, just flex rows.
 */
export function PairFlowChart({ flows }: PairFlowChartProps) {
	const reduced = useReducedMotion();
	if (flows.length === 0) {
		return <Caption className="italic">No observer→observed pairs yet.</Caption>;
	}
	const max = Math.max(...flows.map((f) => f.count), 1);

	return (
		<div
			className="space-y-1.5"
			role="img"
			aria-label="Conclusion flow from observers to observed peers"
		>
			{flows.slice(0, 12).map((f, i) => (
				<div key={`${f.observer}-${f.observed ?? ""}`} className="flex items-center gap-2 min-w-0">
					<MonoCaption className="w-28 truncate text-right" style={{ color: "var(--text-2)" }}>
						{f.observer}
					</MonoCaption>
					<div className="flex-1 relative h-5 min-w-0">
						<motion.div
							className="absolute inset-y-0 rounded-md"
							style={{
								background: `linear-gradient(90deg, ${COLOR.accentSubtle}, var(--accent-dim))`,
								border: `1px solid ${COLOR.accentBorder}`,
							}}
							initial={reduced ? false : { width: 0 }}
							animate={{ width: `${Math.max((f.count / max) * 100, 8)}%` }}
							transition={{ duration: 0.45, ease: "easeOut", delay: reduced ? 0 : i * 0.04 }}
						/>
						<span
							className="absolute inset-y-0 flex items-center pl-2 text-[10px] font-mono"
							style={{ color: "var(--accent-text)" }}
						>
							{f.count}
						</span>
					</div>
					<MonoCaption className="w-28 truncate" style={{ color: "var(--text-2)" }}>
						{f.observed ?? "(unassigned)"}
					</MonoCaption>
				</div>
			))}
			{flows.length > 12 && (
				<Caption className="text-center">+ {flows.length - 12} more pairs</Caption>
			)}
		</div>
	);
}