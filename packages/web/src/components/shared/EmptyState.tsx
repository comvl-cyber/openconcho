import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { Body, Caption } from "@/components/ui/typography";
import { COLOR } from "@/lib/constants";

interface EmptyStateProps {
	icon?: LucideIcon;
	title: string;
	description?: string;
	/** Short numbered steps telling the user what to do next. */
	guidance?: string[];
	action?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, guidance, action }: EmptyStateProps) {
	return (
		<motion.div
			initial={{ opacity: 0, y: 8 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.4 }}
			className="flex flex-col items-center justify-center py-20 text-center"
		>
			{Icon && (
				<div
					className="w-12 h-12 rounded-xl flex items-center justify-center mb-4"
					style={{
						background: COLOR.accentSubtle,
						border: `1px solid ${COLOR.accentBorderStrong}`,
					}}
				>
					<Icon className="w-5 h-5" style={{ color: COLOR.accentMuted }} strokeWidth={1.5} />
				</div>
			)}
			<Body className="font-medium">{title}</Body>
			{description && <Caption className="mt-1.5 max-w-xs leading-relaxed">{description}</Caption>}
			{guidance && guidance.length > 0 && (
				<ol className="mt-3 max-w-xs text-left space-y-1.5">
					{guidance.map((step, i) => (
						<li key={step} className="flex gap-2 items-start">
							<span
								className="flex-shrink-0 w-4 h-4 mt-0.5 rounded-full flex items-center justify-center text-[10px] font-mono"
								style={{ background: COLOR.accentSubtle, color: COLOR.accentText }}
							>
								{i + 1}
							</span>
							<Caption className="leading-relaxed">{step}</Caption>
						</li>
					))}
				</ol>
			)}
			{action && <div className="mt-4">{action}</div>}
		</motion.div>
	);
}
