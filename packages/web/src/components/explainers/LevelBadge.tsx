import { HelpCircle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { COLOR } from "@/lib/constants";
import { getLevelExplanation } from "@/lib/explainers";

const KIND_STYLES: Record<string, { bg: string; fg: string; border: string }> = {
	explicit: { bg: "rgba(148,163,184,0.10)", fg: "var(--text-2)", border: "rgba(148,163,184,0.25)" },
	deductive: { bg: COLOR.accentSubtle, fg: COLOR.accentText, border: COLOR.accentBorder },
	inductive: { bg: "rgba(245,158,11,0.10)", fg: COLOR.warning, border: COLOR.warningBorder },
};

interface LevelBadgeProps {
	level: "explicit" | "deductive" | "inductive";
	count?: number;
}

/**
 * A small chip naming one of Honcho's memory levels with a hover tooltip
 * explaining it in plain language.
 */
export function LevelBadge({ level, count }: LevelBadgeProps) {
	const info = getLevelExplanation(level);
	if (!info) return null;
	const style = KIND_STYLES[level];

	return (
		<TooltipProvider>
			<Tooltip>
				<TooltipTrigger asChild>
					<span
						data-testid="level-badge"
						className="inline-flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded cursor-help"
						style={{ background: style.bg, color: style.fg, border: `1px solid ${style.border}` }}
					>
						{typeof count === "number" && <span>{count}</span>}
						<span className="hidden sm:inline">{info.label}</span>
						<HelpCircle className="w-3 h-3 opacity-60" strokeWidth={1.5} />
					</span>
				</TooltipTrigger>
				<TooltipContent className="max-w-56 font-normal leading-snug">
					{info.explanation}
				</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}
