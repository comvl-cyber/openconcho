import { useState } from "react";
import {
	adminRequest,
	type CompatibilityResult,
	queueModelAdd,
	queueModelSwitch,
	useAdminSession,
	useModelCatalog,
	useModelStatus,
} from "@/api/model-admin";
import { FormModal } from "@/components/shared/FormModal";
import { cn } from "@/lib/utils";
import { AdminRequestsPanel } from "./AdminRequestsPanel";
import { ModelCatalogBrowser } from "./ModelCatalogBrowser";
import { ProviderManager } from "./ProviderManager";

const TABS = ["Models", "Providers", "Activity"] as const;

export function ModelManager() {
	const session = useAdminSession();
	const [tab, setTab] = useState<(typeof TABS)[number]>("Models");
	const [chosenProvider, setProvider] = useState("");
	const [model, setModel] = useState("");
	const [test, setTest] = useState<CompatibilityResult | null>(null);
	const [busy, setBusy] = useState("");
	const [message, setMessage] = useState("");
	const [dialogOpen, setDialogOpen] = useState<{
		kind: "confirm-switch" | "confirm-add";
		provider: string;
		model: string;
		revision?: string;
		proof?: string;
	} | null>(null);
	const provider =
		chosenProvider || session.data?.providers.find((item) => item.configured)?.id || "";
	const configured =
		session.data?.providers.some((item) => item.id === provider && item.configured) ?? false;
	const enabled = Boolean(session.data) && !session.error;
	const status = useModelStatus(enabled);
	const catalog = useModelCatalog(provider, enabled && configured);
	const error = session.error ?? status.error ?? catalog.error;

	async function runTest() {
		if (!provider || !model || !session.data) return;
		setBusy(
			"Testing production parameters… This makes paid API calls and can take several minutes.",
		);
		setTest(null);
		setMessage("");
		try {
			setTest(
				await adminRequest<CompatibilityResult>("test", session.data.csrf, { provider, model }),
			);
		} catch (cause) {
			setMessage(cause instanceof Error ? cause.message : "Test failed");
		} finally {
			setBusy("");
		}
	}

	async function confirmSwitch() {
		if (!dialogOpen || !session.data || !test?.passed || !test.proof || !dialogOpen.revision) {
			return;
		}
		setBusy("Submitting model switch…");
		try {
			await queueModelSwitch(
				session.data.csrf,
				dialogOpen.provider,
				dialogOpen.model,
				dialogOpen.revision,
				test.proof,
			);
			setMessage("Model switch request queued");
		} catch (cause) {
			setMessage(cause instanceof Error ? cause.message : "Failed to queue switch");
		} finally {
			setBusy("");
			setDialogOpen(null);
		}
	}

	async function confirmAdd() {
		if (!dialogOpen || !session.data) return;
		setBusy("Submitting model add…");
		try {
			await queueModelAdd(session.data.csrf, dialogOpen.provider, dialogOpen.model);
			setMessage("Model add request queued");
		} catch (cause) {
			setMessage(cause instanceof Error ? cause.message : "Failed to queue add");
		} finally {
			setBusy("");
			setDialogOpen(null);
		}
	}

	return (
		<section aria-label="Honcho model administration" className="model-manager">
			<header className="model-manager-header">
				<div className="model-manager-title">
					<div>
						<p className="eyebrow">SERVER CONFIGURATION</p>
						<h2>Honcho models</h2>
						<p>Choose deliberately. Test compatibility. Track every change.</p>
					</div>
				</div>
			</header>
			<p className="muted">
				Manage this server's nine chat slots, not the browser's active connection. Provider keys
				stay on the server. Embeddings are never changed.
			</p>
			{session.isPending && <p role="status">Checking administrator access…</p>}
			{error && (
				<p role="alert" className="notice notice-error">
					{error.message}
				</p>
			)}
			{enabled && session.data && (
				<>
					{status.data && (
						<section className="model-current" aria-label="Current configuration">
							<div>
								<p className="eyebrow">CURRENT DESIRED MODEL</p>
								<strong>{status.data.model}</strong>
								<p className="muted">
									{status.data.provider} · Rollout: {status.data.state}
								</p>
							</div>
							<p className="muted">Embedding: {status.data.embedding} (unchanged)</p>
							<details>
								<summary>Live revision and all chat slots</summary>
								<p className="mono">{status.data.revision}</p>
								{Object.entries(status.data.slots).map(([slot, value]) => (
									<p key={slot} className="mono">
										{slot}: {value}
									</p>
								))}
								{status.data.deployments.map((item) => (
									<p key={item.name}>
										{item.name}: {item.ready ? "ready" : "pending"}
									</p>
								))}
							</details>
						</section>
					)}
					<div className="model-manager-tabs" role="tablist" aria-label="Model administration">
						{TABS.map((item) => (
							<button
								type="button"
								key={item}
								role="tab"
								aria-selected={tab === item}
								aria-controls={`model-panel-${item}`}
								id={`model-tab-${item}`}
								className={`model-manager-tab ${tab === item ? "active" : ""}`}
								onClick={() => setTab(item)}
							>
								{item}
							</button>
						))}
					</div>
					<div role="tabpanel" id={`model-panel-${tab}`} aria-labelledby={`model-tab-${tab}`}>
						{(() => {
							if (tab === "Models")
								return (
									<div className="model-manager-section">
										<div className="model-toolbar">
											<label className="field">
												API provider
												<select
													aria-label="API provider"
													value={provider}
													onChange={(event) => {
														setProvider(event.target.value);
														setModel("");
														setTest(null);
													}}
												>
													{!provider && <option value="">Select a provider</option>}
													{session.data.providers.map((item) => (
														<option key={item.id} value={item.id}>
															{item.name}
															{item.configured ? "" : " (credential not configured)"}
														</option>
													))}
												</select>
											</label>
											<button
												type="button"
												className="control-button"
												disabled={!configured || catalog.isFetching}
												onClick={() => void catalog.refetch()}
											>
												Refresh catalog & pricing
											</button>
										</div>
										{!configured ? (
											<p className="notice">
												No server credential configured for this provider. See Providers for setup.
											</p>
										) : (
											<ModelCatalogBrowser
												catalog={catalog.data}
												loading={catalog.isFetching}
												selected={model}
												onSelect={setModel}
											/>
										)}
										<section aria-label="Saved model library" className="model-library">
											<h3>Saved model library</h3>
											<p className="muted">
												Saved selections are not active until tested and switched.
											</p>
											{(session.data.favorites ?? []).length ? (
												<div className="model-library-items">
													{session.data.favorites.map((item) => (
														<button
															type="button"
															className="control-button"
															key={`${item.provider}/${item.model}`}
															onClick={() => {
																setProvider(item.provider);
																setModel(item.model);
																setTest(null);
															}}
														>
															<span>
																{item.model}
																<small>{item.provider}</small>
															</span>
														</button>
													))}
												</div>
											) : (
												<p className="muted">No saved models yet.</p>
											)}
										</section>
										{model && (
											<div className="model-selected">
												<div className="model-selected-header">
													<span className="model-selected-name">{model}</span>
													<span className="muted">{provider}</span>
												</div>
												<p className="muted">
													Compatibility checks plain chat, structured output and tools with
													production token budgets, temperature and reasoning settings. Model
													changes are deliberately not available from the dashboard; an operator
													applies a passing selection through the controlled GitOps workflow.
												</p>
												<button
													type="button"
													className="control-button primary"
													onClick={() => void runTest()}
													disabled={Boolean(busy) || !configured}
												>
													{busy || "Test compatibility (uses API credits)"}
												</button>
												{test && (
													<div
														className={cn("model-test-result", test.passed ? "passed" : "failed")}
														role="status"
													>
														<div className="model-test-result-header">
															<strong>
																{test.passed
																	? "Compatibility passed — ready to switch"
																	: "Compatibility failed — operator change blocked"}
															</strong>
														</div>
														<div className="model-test-result details">
															{test.results.map((result) => (
																<p key={result.name}>
																	{result.passed ? "PASS" : "FAIL"} · {result.name} ·{" "}
																	{result.milliseconds} ms · {result.detail}
																</p>
															))}
														</div>
													</div>
												)}
											</div>
										)}
										{message && (
											<p role="status" className="break-words">
												{message}
											</p>
										)}
										<FormModal
											open={!!dialogOpen}
											title={
												dialogOpen?.kind === "confirm-switch"
													? "Confirm model switch"
													: "Confirm model add"
											}
											onClose={() => setDialogOpen(null)}
											maxWidth="max-w-lg"
										>
											<div className="space-y-4">
												{dialogOpen?.kind === "confirm-switch" ? (
													<>
														<p>
															Switch <strong>{dialogOpen.provider}</strong> /{" "}
															<strong>{dialogOpen.model}</strong> to revision{" "}
															<code>{dialogOpen.revision}</code>?
														</p>
														<p className="muted">
															This makes a paid API call test. Proof expires at{" "}
															{test?.expiresAt ? new Date(test.expiresAt).toLocaleString() : "N/A"}.
														</p>
														<div className="notice">
															<strong>Warning:</strong> This tests the model against production
															parameters and consumes API credits. Only proceed if the test passed
															above.
														</div>
													</>
												) : (
													<p>
														Add <strong>{dialogOpen?.provider}</strong> /{" "}
														<strong>{dialogOpen?.model}</strong> to the server catalog?
													</p>
												)}
												{busy && (
													<p role="status" className="muted">
														{busy}
													</p>
												)}
												<div className="flex justify-end gap-2">
													<button
														type="button"
														className="control-button"
														onClick={() => setDialogOpen(null)}
														disabled={Boolean(busy)}
													>
														Cancel
													</button>
													<button
														type="button"
														className="control-button primary"
														onClick={
															dialogOpen?.kind === "confirm-switch" ? confirmSwitch : confirmAdd
														}
														disabled={Boolean(busy)}
													>
														{busy || "Confirm"}
													</button>
												</div>
											</div>
										</FormModal>
									</div>
								);
							if (tab === "Providers")
								return <ProviderManager session={session} csrf={session.data?.csrf ?? ""} />;
							return <AdminRequestsPanel />;
						})()}
					</div>
				</>
			)}
		</section>
	);
}
