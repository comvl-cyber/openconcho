import { useState } from "react";
import {
	adminRequest,
	type CompatibilityResult,
	useAdminSession,
	useModelCatalog,
	useModelStatus,
} from "@/api/model-admin";

const controlStyle = {
	background: "var(--bg-2)",
	color: "var(--text-1)",
	border: "1px solid var(--border)",
};
const buttonClass = "rounded-lg px-3 py-2 text-sm disabled:opacity-40 disabled:cursor-not-allowed";

export function ModelManager() {
	const session = useAdminSession();
	const [provider, setProvider] = useState("openrouter");
	const [model, setModel] = useState("");
	const [search, setSearch] = useState("");
	const [knownOnly, setKnownOnly] = useState(false);
	const [confirmation, setConfirmation] = useState("");
	const [test, setTest] = useState<CompatibilityResult>();
	const [rollback, setRollback] = useState(false);
	const [busy, setBusy] = useState("");
	const [message, setMessage] = useState("");
	const status = useModelStatus(Boolean(session.data) && !busy);
	const catalog = useModelCatalog(provider, Boolean(session.data) && !busy);
	const error = session.error ?? status.error ?? catalog.error;
	const models =
		catalog.data?.models.filter(
			(item) =>
				`${item.id} ${item.name}`.toLowerCase().includes(search.toLowerCase()) &&
				(!knownOnly || (item.input !== null && item.output !== null)),
		) ?? [];
	const select = (id: string, nextProvider = provider, restoring = false) => {
		setProvider(nextProvider);
		setModel(id);
		setTest(undefined);
		setConfirmation("");
		setRollback(restoring);
		setMessage("");
	};
	async function runTest() {
		setBusy(
			"Testing production parameters… This makes paid API calls and can take several minutes.",
		);
		setTest(undefined);
		setMessage("");
		try {
			setTest(
				await adminRequest<CompatibilityResult>("test", session.data?.csrf, { provider, model }),
			);
		} catch (cause) {
			setMessage(cause instanceof Error ? cause.message : "Test failed");
		} finally {
			setBusy("");
		}
	}
	async function apply() {
		setBusy("Committing desired state to GitOps…");
		setMessage("");
		try {
			const result = await adminRequest<{ commit: string; state: string }>(
				"apply",
				session.data?.csrf,
				{
					provider,
					model,
					proof: test?.proof,
					revision: test?.revision,
					confirm: confirmation,
					rollback,
				},
			);
			setMessage(
				`${result.state}. Commit ${result.commit}. Honcho API and deriver will restart; allow a few minutes.`,
			);
			setTest(undefined);
			setConfirmation("");
			await status.refetch();
		} catch (cause) {
			setMessage(cause instanceof Error ? cause.message : "Apply failed");
		} finally {
			setBusy("");
		}
	}
	return (
		<section
			aria-label="Honcho model administration"
			className="mt-8 rounded-xl p-5 space-y-4"
			style={{ ...controlStyle, background: "var(--bg-1)" }}
		>
			<div>
				<h2 className="text-xl font-semibold">Honcho models</h2>
				<p className="text-sm mt-1" style={{ color: "var(--text-3)" }}>
					Manage this server’s nine chat slots, not the browser’s active connection. Provider keys
					stay on the server. Embeddings are never changed.
				</p>
			</div>
			{session.isPending && <p>Checking administrator access…</p>}
			{error && <p role="alert">{error.message}</p>}
			{session.data && (
				<>
					{status.data && (
						<div className="rounded-lg p-3 text-sm space-y-1" style={controlStyle}>
							<p>
								<strong>Current desired model:</strong> {status.data.provider} / {status.data.model}
							</p>
							<p>
								<strong>Rollout:</strong> {status.data.state}{" "}
								{status.data.deployments
									.map((d) => `${d.name}: ${d.ready ? "ready" : "pending"}`)
									.join(" · ")}
							</p>
							<p>Embedding: {status.data.embedding} (unchanged)</p>
							<details>
								<summary>Git revision and all chat slots</summary>
								<p className="break-all">{status.data.revision}</p>
								{Object.entries(status.data.slots).map(([slot, value]) => (
									<p key={slot} className="break-all">
										{slot}: {value}
									</p>
								))}
							</details>
							<button
								type="button"
								className={buttonClass}
								style={controlStyle}
								disabled={Boolean(busy) || !status.data.previous.model}
								onClick={() =>
									select(status.data?.previous.model ?? "", status.data?.previous.provider, true)
								}
							>
								Prepare rollback to {status.data.previous.model ?? "previous model (none yet)"}
							</button>
						</div>
					)}
					<div className="flex flex-wrap gap-2 items-center">
						<label>
							Provider{" "}
							<select
								aria-label="API provider"
								className="rounded-lg p-2"
								style={controlStyle}
								value={provider}
								disabled={Boolean(busy)}
								onChange={(e) => select("", e.target.value)}
							>
								{session.data.providers.map((p) => (
									<option key={p.id} value={p.id} disabled={!p.configured}>
										{p.name}
										{!p.configured ? " (not configured)" : ""}
									</option>
								))}
							</select>
						</label>
						<button
							type="button"
							className={buttonClass}
							style={controlStyle}
							disabled={Boolean(busy) || catalog.isFetching}
							onClick={() => {
								setTest(undefined);
								void catalog.refetch();
							}}
						>
							Refresh catalog & pricing
						</button>
					</div>
					<p className="text-xs" style={{ color: "var(--text-3)" }}>
						Additional OpenAI-compatible providers must be configured by an operator in the private
						service’s trusted provider profiles and Kubernetes Secrets. Arbitrary URLs and browser
						API keys are not accepted. Providers without published pricing show “Unavailable”.
					</p>
					{catalog.data && (
						<p className="text-xs break-all">
							{catalog.data.count} models · Source: {catalog.data.source} · Fetched:{" "}
							{catalog.data.fetchedAt} · Prices per 1 million tokens
							{catalog.data.currency ? ` (${catalog.data.currency})` : " (currency unavailable)"}.
							Provider estimates; taxes and route-specific costs may vary.
						</p>
					)}
					<div className="flex flex-wrap gap-3">
						<input
							aria-label="Search models"
							placeholder="Search model or vendor…"
							className="flex-1 min-w-40 rounded-lg p-2"
							style={controlStyle}
							value={search}
							onChange={(e) => setSearch(e.target.value)}
						/>
						<label className="text-sm flex items-center gap-2">
							<input
								type="checkbox"
								checked={knownOnly}
								onChange={(e) => setKnownOnly(e.target.checked)}
							/>
							Known pricing only
						</label>
					</div>
					<div className="overflow-auto max-h-72 rounded-lg" style={controlStyle}>
						<table className="w-full text-sm text-left">
							<thead>
								<tr>
									<th className="p-2">Model</th>
									<th className="p-2">Input / 1M</th>
									<th className="p-2">Output / 1M</th>
									<th className="p-2">Cached input / 1M</th>
								</tr>
							</thead>
							<tbody>
								{models.map((item) => (
									<tr
										key={item.id}
										style={{ background: model === item.id ? "var(--bg-3)" : undefined }}
									>
										<td className="p-2">
											<button
												type="button"
												aria-label={`Select ${item.id}`}
												className="text-left break-all"
												disabled={Boolean(busy)}
												onClick={() => select(item.id)}
											>
												{item.id}
												{model === item.id ? " ✓" : ""}
											</button>
										</td>
										{[item.input, item.output, item.cache].map((price, index) => (
											<td
												key={["input", "output", "cache"][index]}
												className="p-2 whitespace-nowrap"
											>
												{price === null
													? "Unavailable"
													: `${catalog.data?.currency ?? ""} ${price}`}
											</td>
										))}
									</tr>
								))}
							</tbody>
						</table>
						{!models.length && (
							<p className="p-3">
								{catalog.isFetching
									? "Fetching provider catalog…"
									: "No models match these filters."}
							</p>
						)}
					</div>
					{model && (
						<div className="space-y-3">
							<p className="break-all">
								<strong>{rollback ? "Rollback target" : "Selected"}:</strong> {model}
							</p>
							<p className="text-xs">
								Compatibility checks plain chat, structured output and tools with production token
								budgets, temperature and reasoning settings. A passing test is required before
								applying and expires after 10 minutes. Applying normalizes chat structured output to
								json_object; rollback restores the previous managed settings.
							</p>
							<button
								type="button"
								className={buttonClass}
								style={controlStyle}
								disabled={Boolean(busy)}
								onClick={() => void runTest()}
							>
								Test compatibility (uses API credits)
							</button>
							{test && (
								<div role="status">
									<p>
										<strong>
											{test.passed
												? "Compatibility passed"
												: "Compatibility failed — apply blocked"}
										</strong>
									</p>
									{test.results.map((result) => (
										<p key={result.name} className="text-xs">
											{result.passed ? "PASS" : "FAIL"} · {result.name} · {result.milliseconds} ms ·{" "}
											{result.detail}
										</p>
									))}
								</div>
							)}
							<label className="block text-sm">
								Type the exact selected model ID to confirm restart
								<input
									aria-label="Confirm model ID"
									className="block w-full rounded-lg p-2 mt-1"
									style={controlStyle}
									value={confirmation}
									disabled={Boolean(busy)}
									onChange={(e) => setConfirmation(e.target.value)}
								/>
							</label>
							<button
								type="button"
								className={buttonClass}
								style={controlStyle}
								disabled={
									Boolean(busy) ||
									!test?.passed ||
									confirmation !== model ||
									test.revision !== status.data?.revision
								}
								onClick={() => void apply()}
							>
								Apply model via GitOps
							</button>
						</div>
					)}
				</>
			)}
			{busy && <p role="status">{busy}</p>}
			{message && (
				<p role="status" className="break-words">
					{message}
				</p>
			)}
		</section>
	);
}
