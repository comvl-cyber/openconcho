import { motion } from "framer-motion";
import { Caption } from "@/components/ui/typography";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import type { LevelDistribution } from "@/lib/charts";
import { COLOR } from "@/lib/constants";
import type { ConclusionType } from "@/lib/dreams";

interface LevelBarChartProps {
	distribution: LevelDistribution;
}

const LEVELS: Array<{ type: ConclusionType; label: string; color: string }> = [
	{ type: "explicit", label: "Explicit", color: "var(--text-3)" },
	{ type: "deductive", label: "Deductive", color: "var(--accent)" },
	{ type: "inductive", label: "Inductive", color: COLOR.warning },
	{ type: "contradiction", label: "Contradiction", color: COLOR.destructive },
];

/** Horizontal bar chart of conclusion counts per reasoning level. */
export function LevelBarChart({ distribution }: LevelBarChartProps) {
	const reduced = useReducedMotion();
	const max = Math.max(distribution.max, 1);
	return (
		<div className="space-y-2" role="img" aria-label="Conclusions by reasoning level">
			{LEVELS.map(({ type, label, color }) => {
				const n = distribution.levels[type];
				const pct = (n / max) * 100;
				return (
					<div key={type} className="flex items-center gap-2">
						<Caption className="w-24 shrink-0 text-right">{label}</Caption>
						<div
							className="flex-1 h-4 rounded-md overflow-hidden relative"
							style={{ background: "var(--surface)", outline: "1px solid var(--border)" }}
						>
							<motion.div
								className="h-full rounded-md"
								style={{ background: color, opacity: 0.85 }}
								initial={reduced ? false : { width: 0 }}
								animate={{ width: `${pct}%` }}
								transition={{ duration: 0.5, ease: "easeOut" }}
							/>
						</div>
						<span
							className="w-10 text-right text-xs font-mono"
							style={{ color: n === 0 ? "var(--text-4)" : "var(--text-2)" }}
						>
							{n}
						</span>
					</div>
				);
			})}
		</div>
	);
}
