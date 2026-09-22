import { ChevronRight, Lightbulb } from "lucide-react";
import { useState } from "react";
import { Body, Caption } from "@/components/ui/typography";
import { COLOR } from "@/lib/constants";
import { MEMORY_PIPELINE } from "@/lib/explainers";

interface MemoryPipelineProps {
	/** Render expanded on first paint. */
	defaultOpen?: boolean;
	/** Stage id to visually emphasize (matches the host page's focus). */
	emphasize?: string;
}

/**
 * Collapsible plain-language explanation of the Honcho memory model:
 * messages -> working representation -> conclusions -> dreams -> dialectic recall.
 */
export function MemoryPipeline({ defaultOpen = false, emphasize }: MemoryPipelineProps) {
	const [open, setOpen] = useState(defaultOpen);

	return (
		<div
			className="rounded-xl theme-card"
			style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
		>
			<button
				type="button"
				onClick={() => setOpen((o) => !o)}
				aria-expanded={open}
				className="w-full flex items-center gap-2 p-4 text-left cursor-pointer"
			>
				<Lightbulb
					className="w-4 h-4 flex-shrink-0"
					style={{ color: "var(--accent)" }}
					strokeWidth={1.5}
				/>
				<Body className="font-medium">How Honcho remembers</Body>
				<Caption className="hidden md:inline">the memory pipeline, in plain language</Caption>
				<ChevronRight
					className="w-4 h-4 ml-auto transition-transform"
					style={{
						color: "var(--text-4)",
						transform: open ? "rotate(90deg)" : undefined,
					}}
					strokeWidth={1.5}
				/>
			</button>
			{open && (
				<ol className="px-4 pb-4 space-y-3">
					{MEMORY_PIPELINE.map((stage, i) => {
						const emphasized = stage.id === emphasize;
						return (
							<li
								key={stage.id}
								data-testid={`pipeline-stage-${stage.id}`}
								data-emphasized={emphasized ? "true" : "false"}
								className="flex gap-3 p-2.5 rounded-lg"
								style={{
									background: emphasized ? COLOR.accentSubtle : "transparent",
									border: `1px solid ${emphasized ? COLOR.accentBorder : "transparent"}`,
								}}
							>
								<span
									className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-mono"
									style={{
										background: emphasized ? COLOR.accentBorder : "var(--bg-3)",
										color: emphasized ? COLOR.accentText : "var(--text-3)",
									}}
								>
									{i + 1}
								</span>
								<div>
									<Body className="font-medium">{stage.title}</Body>
									<Caption as="p" className="mt-0.5">
										{stage.summary}
									</Caption>
									<Caption as="p" className="mt-1 opacity-70">
										{stage.detail}
									</Caption>
								</div>
							</li>
						);
					})}
				</ol>
			)}
		</div>
	);
}
