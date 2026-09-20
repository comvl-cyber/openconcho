import { useId } from "react";
import { COLOR } from "@/lib/constants";

interface SparklineProps {
	points: number[];
	label: string;
	/** CSS color for the stroke. Defaults to the accent color token. */
	color?: string;
	height?: number;
}

/**
 * Tiny inline SVG line chart. No deps — pure <polyline>. Fills the parent
 * width; pass `height` in px. Renders an accessible <title> via role="img".
 */
export function Sparkline({ points, label, color = "var(--accent)", height = 32 }: SparklineProps) {
	const gradientId = useId();
	const w = 100;
	const h = 100;
	const max = Math.max(...points, 1);
	const step = points.length > 1 ? w / (points.length - 1) : w;
	const path = points
		.map((v, i) => `${(i * step).toFixed(2)},${(h - (v / max) * (h - 8) - 4).toFixed(2)}`)
		.join(" ");

	return (
		<svg
			role="img"
			aria-label={label}
			viewBox={`0 0 ${w} ${h}`}
			preserveAspectRatio="none"
			className="w-full"
			style={{ height }}
		>
			<defs>
				<linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
					<stop offset="0%" stopColor={color} stopOpacity="0.35" />
					<stop offset="100%" stopColor={color} stopOpacity="0" />
				</linearGradient>
			</defs>
			<polygon points={`0,${h} ${path} ${w},${h}`} fill={`url(#${gradientId})`} />
			<polyline
				chart-sparkline=""
				points={path}
				fill="none"
				stroke={color}
				strokeWidth="2.5"
				strokeLinejoin="round"
				strokeLinecap="round"
				vectorEffect="non-scaling-stroke"
			/>
		</svg>
	);
}

interface HourBin {
	hour: number;
	explicit: number;
	deductive: number;
	inductive: number;
	contradiction: number;
	total: number;
}

interface HourHistogramProps {
	bins: HourBin[];
	label: string;
}

const HOUR_CELL_LEVEL_ORDER = ["explicit", "deductive", "inductive", "contradiction"] as const;

const LEVEL_FILL: Record<(typeof HOUR_CELL_LEVEL_ORDER)[number], string> = {
	explicit: "var(--text-3)",
	deductive: "var(--accent)",
	inductive: COLOR.warning,
	contradiction: COLOR.destructive,
};

/**
 * 24-cell hour-of-day activity heatmap. Each cell is a stacked mini-column of
 * reasoning levels; hovering shows the exact counts via native title.
 */
export function HourHistogram({ bins, label }: HourHistogramProps) {
	const max = Math.max(...bins.map((b) => b.total), 1);
	return (
		<div role="img" aria-label={label}>
			<div
				className="grid grid-cols-24 gap-[2px]"
				style={{ gridTemplateColumns: "repeat(24, 1fr)" }}
			>
				{bins.map((bin) => {
					const intensity = bin.total / max;
					return (
						<div
							key={bin.hour}
							data-hour-cell={bin.hour}
							data-active={bin.total > 0 ? "true" : "false"}
							title={`${String(bin.hour).padStart(2, "0")}:00 UTC — ${bin.total} conclusion${bin.total === 1 ? "" : "s"}${
								bin.total > 0
									? ` (${bin.explicit} explicit, ${bin.deductive} deductive, ${bin.inductive} inductive${
											bin.contradiction ? `, ${bin.contradiction} contradiction` : ""
										})`
									: ""
							}`}
							className="rounded-[3px] flex flex-col justify-end overflow-hidden transition-transform"
							style={{
								height: 40,
								background: "var(--surface)",
								outline: `1px solid var(--border)`,
								transform: bin.total > 0 ? `scaleY(${0.55 + 0.45 * intensity})` : undefined,
								transformOrigin: "bottom",
							}}
						>
							{HOUR_CELL_LEVEL_ORDER.map((level) => {
								const n = bin[level];
								if (n === 0) return null;
								return (
									<div
										key={level}
										style={{
											height: `${(n / bin.total) * 100}%`,
											background: LEVEL_FILL[level],
											opacity: 0.85,
										}}
									/>
								);
							})}
						</div>
					);
				})}
			</div>
			<div
				className="flex justify-between mt-1 text-[10px] font-mono"
				style={{ color: "var(--text-4)" }}
			>
				<span>00h</span>
				<span>06h</span>
				<span>12h</span>
				<span>18h</span>
				<span>23h UTC</span>
			</div>
		</div>
	);
}