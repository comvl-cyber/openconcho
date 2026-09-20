import { useParams } from "@tanstack/react-router";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, Eye, Moon } from "lucide-react";
import { useMemo, useState } from "react";
import { useDreams } from "@/api/queries";
import { HourHistogram } from "@/components/charts/HourHistogram";
import { Sparkline } from "@/components/charts/Sparkline";
import { MemoryPipeline } from "@/components/explainers/MemoryPipeline";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorAlert } from "@/components/shared/ErrorAlert";
import { Skeleton } from "@/components/shared/Skeleton";
import { TimestampChip } from "@/components/shared/TimestampChip";
import { Caption, MonoCaption, Muted, PageTitle } from "@/components/ui/typography";
import { useDemo } from "@/hooks/useDemo";
import { dreamHourHistogram, sparklineFromDreams } from "@/lib/charts";
import { COLOR } from "@/lib/constants";
import {
	clusterConclusionsIntoDreams,
	type Dream,
	dreamCounts,
	type ExtendedConclusion,
} from "@/lib/dreams";
import { DreamDetail } from "./DreamDetail";

const itemVariants = {
	hidden: { opacity: 0, y: 8 },
	show: (i: number) => ({
		opacity: 1,
		y: 0,
		transition: { delay: i * 0.03, type: "spring" as const, stiffness: 300, damping: 25 },
	}),
};

export function DreamList() {
	const { workspaceId } = useParams({ strict: false }) as { workspaceId: string };
	const { data, isLoading, error } = useDreams(workspaceId);
	const [selectedId, setSelectedId] = useState<string | null>(null);

	const dreams = useMemo<Dream[]>(() => {
		const conclusions = (data as ExtendedConclusion[] | undefined) ?? [];
		return clusterConclusionsIntoDreams(conclusions);
	}, [data]);

	const selected = useMemo(
		() => (selectedId ? (dreams.find((d) => d.id === selectedId) ?? null) : null),
		[dreams, selectedId],
	);

	const allConclusions = useMemo<ExtendedConclusion[]>(
		() => (data as ExtendedConclusion[] | undefined) ?? [],
		[data],
	);
	const hourBins = useMemo(() => dreamHourHistogram(allConclusions), [allConclusions]);
	const sparkPoints = useMemo(() => {
		if (dreams.length === 0) return [];
		const times = dreams.flatMap((d) => [d.earliestMs, d.latestMs]);
		const startMs = Math.min(...times);
		const endMs = Math.max(...times) + 1;
		return sparklineFromDreams(dreams, 28, startMs, endMs);
	}, [dreams]);

	return (
		<div className="page-container">
			<motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
				<Breadcrumb />
				<div className="flex items-center gap-2 mb-1">
					<Moon className="w-5 h-5" style={{ color: "var(--accent)" }} strokeWidth={1.5} />
					<PageTitle>Dreams</PageTitle>
					{dreams.length > 0 && (
						<span
							className="ml-1 text-xs font-mono px-2 py-0.5 rounded-full"
							style={{
								background: COLOR.accentSubtle,
								color: COLOR.accentText,
								border: `1px solid ${COLOR.accentBorder}`,
							}}
						>
							{dreams.length}
						</span>
					)}
				</div>
				<Muted className="mt-0.5">
					Each run produces explicit, deductive, and inductive conclusions for one peer pair.
				</Muted>
			</motion.div>

			<ErrorAlert error={error instanceof Error ? error : null} />

			<div className="mb-6">
				<MemoryPipeline emphasize="dreams" />
			</div>

			{dreams.length > 0 && (
				<motion.div
					initial={{ opacity: 0, y: 8 }}
					animate={{ opacity: 1, y: 0 }}
					transition={{ delay: 0.05 }}
					className="rounded-xl p-4 mb-6"
					style={{
						background: "var(--surface)",
						border: "1px solid var(--border)",
						backdropFilter: "blur(6px)",
					}}
				>
					<div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-end">
						<div>
							<Caption className="mb-2">Dream activity by hour of day</Caption>
							<HourHistogram bins={hourBins} label="Dream activity by hour of day" />
						</div>
						<div>
							<Caption className="mb-2">Dreams over time</Caption>
							<Sparkline points={sparkPoints} label="Dreams over time" height={40} />
							<div
								className="flex justify-between mt-1 text-[10px] font-mono"
								style={{ color: "var(--text-4)" }}
							>
								<span>oldest</span>
								<span>
									{dreams.length} dream{dreams.length === 1 ? "" : "s"}
								</span>
								<span>newest</span>
							</div>
						</div>
					</div>
				</motion.div>
			)}

			{isLoading && <DreamsSkeleton />}

			{!isLoading && dreams.length === 0 && !error && (
				<EmptyState
					icon={Moon}
					title="No dream runs yet"
					description="Dreams are background consolidation runs that clean up and generalize conclusions."
					guidance={[
						"Chat with a peer or add conclusions so there is material to consolidate.",
						"Trigger a dream from the workspace detail or queue page.",
						"Return here to watch each run's explicit, deductive, and inductive output.",
					]}
				/>
			)}

			<AnimatePresence>
				{selected && (
					<motion.div
						key="detail"
						initial={{ opacity: 0, height: 0 }}
						animate={{ opacity: 1, height: "auto" }}
						exit={{ opacity: 0, height: 0 }}
						transition={{ duration: 0.22, ease: "easeInOut" }}
						className="overflow-hidden mb-6"
					>
						<DreamDetail dream={selected} onClose={() => setSelectedId(null)} />
					</motion.div>
				)}
			</AnimatePresence>

			{dreams.length > 0 && (
				<ul className="space-y-2.5">
					{dreams.map((d, i) => (
						<motion.li
							key={d.id}
							custom={i}
							variants={itemVariants}
							initial="hidden"
							animate="show"
						>
							<DreamRow
								dream={d}
								active={d.id === selectedId}
								onSelect={() => setSelectedId(d.id === selectedId ? null : d.id)}
							/>
						</motion.li>
					))}
				</ul>
			)}
		</div>
	);
}

interface DreamRowProps {
	dream: Dream;
	active: boolean;
	onSelect: () => void;
}

function DreamRow({ dream, active, onSelect }: DreamRowProps) {
	const { mask } = useDemo();
	const counts = useMemo(() => dreamCounts(dream), [dream]);

	return (
		<button
			type="button"
			onClick={onSelect}
			aria-pressed={active}
			className="group w-full text-left rounded-xl p-4 transition-colors"
			style={{
				background: active ? COLOR.accentDim : "var(--surface)",
				border: `1px solid ${active ? COLOR.accentBorder : "var(--border)"}`,
			}}
		>
			<div className="flex items-center gap-3 flex-wrap">
				<TimestampChip value={dream.latestIso.replace("T", " ").replace(/\.\d+Z?$/, "")} />

				<div className="flex items-center gap-1.5">
					<Eye className="w-3 h-3" style={{ color: "var(--text-4)" }} strokeWidth={1.5} />
					<MonoCaption>{mask(dream.observer_id)}</MonoCaption>
				</div>
				{dream.observed_id && (
					<div className="flex items-center gap-1">
						<ChevronRight className="w-3 h-3" style={{ color: "var(--text-4)" }} strokeWidth={2} />
						<MonoCaption>{mask(dream.observed_id)}</MonoCaption>
					</div>
				)}

				<div className="ml-auto flex items-center gap-1.5">
					<CountChip label="explicit" value={counts.explicit} kind="neutral" />
					<CountChip label="deductive" value={counts.deductive} kind="accent" />
					<CountChip label="inductive" value={counts.inductive} kind="warning" />
					{counts.contradiction > 0 && (
						<CountChip label="contradiction" value={counts.contradiction} kind="destructive" />
					)}
					<ChevronRight
						className="w-4 h-4 ml-1 transition-transform"
						style={{
							color: active ? "var(--accent-text)" : "var(--text-4)",
							transform: active ? "rotate(90deg)" : undefined,
						}}
						strokeWidth={1.5}
					/>
				</div>
			</div>

			{dream.earliestIso !== dream.latestIso && (
				<Caption className="mt-2 block">
					Span: {formatSpan(dream.latestMs - dream.earliestMs)}
				</Caption>
			)}
		</button>
	);
}

type ChipKind = "neutral" | "accent" | "warning" | "destructive";

function CountChip({ label, value, kind }: { label: string; value: number; kind: ChipKind }) {
	const palette: Record<ChipKind, { bg: string; fg: string; border: string }> = {
		neutral: {
			bg: "rgba(148,163,184,0.10)",
			fg: "var(--text-2)",
			border: "rgba(148,163,184,0.25)",
		},
		accent: { bg: COLOR.accentSubtle, fg: COLOR.accentText, border: COLOR.accentBorder },
		warning: { bg: "rgba(245,158,11,0.10)", fg: COLOR.warning, border: COLOR.warningBorder },
		destructive: {
			bg: COLOR.destructiveDim,
			fg: COLOR.destructive,
			border: COLOR.destructiveBorder,
		},
	};
	const cfg = palette[kind];
	const dim = value === 0;
	return (
		<span
			title={`${value} ${label}`}
			className="inline-flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded"
			style={{
				background: dim ? "transparent" : cfg.bg,
				color: dim ? "var(--text-4)" : cfg.fg,
				border: `1px solid ${dim ? "var(--border)" : cfg.border}`,
				opacity: dim ? 0.6 : 1,
			}}
		>
			<span>{value}</span>
			<span className="hidden sm:inline"> {label}</span>
		</span>
	);
}

function formatSpan(ms: number): string {
	if (ms < 1000) return `${ms}ms`;
	const s = Math.round(ms / 1000);
	if (s < 60) return `${s}s`;
	const m = Math.floor(s / 60);
	const rem = s % 60;
	return rem === 0 ? `${m}m` : `${m}m ${rem}s`;
}

function DreamsSkeleton() {
	return (
		<div className="space-y-2.5" aria-hidden="true">
			{Array.from({ length: 5 }).map((_, index) => (
				<div
					key={index}
					className="rounded-xl p-4"
					style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
				>
					<div className="flex items-center gap-3">
						<Skeleton className="h-6 w-28 rounded-full" />
						<Skeleton className="h-3 w-20 rounded" />
						<Skeleton className="h-3 w-20 rounded" />
						<Skeleton className="ml-auto h-5 w-12 rounded" />
						<Skeleton className="h-5 w-12 rounded" />
						<Skeleton className="h-5 w-12 rounded" />
					</div>
				</div>
			))}
		</div>
	);
}
