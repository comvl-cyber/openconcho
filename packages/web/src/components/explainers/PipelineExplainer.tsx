import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, HelpCircle } from "lucide-react";
import { useState } from "react";
import { Caption, MonoCaption, Muted } from "@/components/ui/typography";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { COLOR } from "@/lib/constants";
import { MEMORY_PIPELINE, type MemoryPipelineStage } from "@/lib/explainers";

interface PipelineExplainerProps {
	/** `panel` shows details inline; `compact` is a one-line collapsible strip. */
	variant?: "panel" | "compact";
	/** Restrict to a subset of stage ids, in pipeline order. */
	stages?: string[];
	className?: string;
}

/**
 * "How it works" explainer for the Honcho memory pipeline. Inline, glassy,
 * collapsible — teaches extraction → derivation → dreams → dialectic in plain
 * language right where users encounter those concepts.
 */
export function PipelineExplainer({
	variant = "panel",
	stages,
	className,
}: PipelineExplainerProps) {
	const [open, setOpen] = useState(variant === "panel");
	const reduced = useReducedMotion();
	const shown = stages ? MEMORY_PIPELINE.filter((s) => stages.includes(s.id)) : MEMORY_PIPELINE;

	return (
		<div
			className={`rounded-xl overflow-hidden ${className ?? ""}`}
			style={{
				background: "linear-gradient(135deg, var(--accent-subtle) 0%, rgba(148,163,184,0.05) 60%)",
				border: `1px solid ${COLOR.accentBorder}`,
				backdropFilter: "blur(8px)",
			}}
		>
			<button
				type="button"
				onClick={() => setOpen((v) => !v)}
				aria-expanded={open}
				className="w-full flex items-center gap-2 px-4 py-2.5 text-left"
			>
				<HelpCircle
					className="w-4 h-4 shrink-0"
					style={{ color: "var(--accent)" }}
					strokeWidth={1.5}
				/>
				<span className="text-xs font-semibold" style={{ color: "var(--text-1)" }}>
					How this works — the memory pipeline
				</span>
				<ChevronDown
					className="w-3.5 h-3.5 ml-auto transition-transform"
					style={{ color: "var(--text-3)", transform: open ? "rotate(180deg)" : undefined }}
					strokeWidth={2}
				/>
			</button>
			<AnimatePresence initial={false}>
				{open && (
					<motion.div
						initial={reduced ? false : { opacity: 0, height: 0 }}
						animate={{ opacity: 1, height: "auto" }}
						exit={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
						transition={{ duration: 0.22, ease: "easeInOut" }}
						className="overflow-hidden"
					>
						<ol className="px-4 pb-4 pt-1 space-y-3">
							{shown.map((stage, i) => (
								<PipelineStageRow
									key={stage.id}
									stage={stage}
									index={i}
									last={i === shown.length - 1}
								/>
							))}
						</ol>
					</motion.div>
				)}
			</AnimatePresence>
		</div>
	);
}

function PipelineStageRow({
	stage,
	index,
	last,
}: {
	stage: MemoryPipelineStage;
	index: number;
	last: boolean;
}) {
	return (
		<li className="flex gap-3">
			<div className="flex flex-col items-center pt-0.5">
				<span
					className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono font-semibold shrink-0"
					style={{
						background: COLOR.accentDim,
						color: "var(--accent-text)",
						border: `1px solid ${COLOR.accentBorder}`,
					}}
				>
					{index + 1}
				</span>
				{!last && (
					<span
						className="w-px flex-1 mt-1"
						style={{ background: `linear-gradient(180deg, ${COLOR.accentBorder}, transparent)` }}
					/>
				)}
			</div>
			<div className="pb-1 min-w-0">
				<MonoCaption className="font-semibold" style={{ color: "var(--text-1)" }}>
					{stage.title}
				</MonoCaption>
				<Muted className="text-xs leading-snug">{stage.summary}</Muted>
				<Caption className="text-[11px] leading-snug mt-0.5">{stage.detail}</Caption>
			</div>
		</li>
	);
}
