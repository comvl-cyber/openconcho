import { useId } from "react";

interface SparklineProps {
	points: number[];
	label: string;
	/** CSS color for the stroke. Defaults to the accent color token. */
	color?: string;
	height?: number;
}

/**
 * Tiny inline SVG line chart. No deps — pure <polyline>. Fills the parent
 * width; pass `height` in px. Renders an accessible label via role="img".
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
