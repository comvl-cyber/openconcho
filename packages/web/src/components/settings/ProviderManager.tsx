import { useState } from "react";
import { queueProviderUpsert, type useAdminSession, useProviderPresets } from "@/api/model-admin";
import { FormModal } from "@/components/shared/FormModal";
import { cn } from "@/lib/utils";

export function ProviderManager({
	session,
	csrf,
}: {
	session: ReturnType<typeof useAdminSession>;
	csrf: string;
}) {
	const presets = useProviderPresets(Boolean(session.data) && !session.error);
	const [dialogOpen, setDialogOpen] = useState<{ mode: "add" | "edit"; preset?: string } | null>(
		null,
	);
	const [form, setForm] = useState({ name: "", url: "", credentialRef: "", preset: "" });
	const [busy, setBusy] = useState("");
	const [message, setMessage] = useState("");

	function openAdd() {
		setForm({ name: "", url: "", credentialRef: "", preset: "" });
		setDialogOpen({ mode: "add" });
	}
	function openEdit(item: {
		id: string;
		name: string;
		configured?: boolean;
		url?: string;
		credentialRef?: string;
	}) {
		const preset = session.data?.providerPresets.find((p) => p.id === item.id);
		if (preset) {
			setForm({
				name: preset.name,
				url: preset.url,
				credentialRef: preset.credentialRef,
				preset: preset.id,
			});
			setDialogOpen({ mode: "edit", preset: preset.id });
		}
	}
	function close() {
		setDialogOpen(null);
	}

	const configuredIds = new Set(
		session.data?.providers.filter((p) => p.configured).map((p) => p.id),
	);
	async function submit() {
		if (!form.name || !form.url || !form.credentialRef || !form.preset) {
			setMessage("All fields required");
			return;
		}
		setBusy("Saving provider…");
		setMessage("");
		try {
			await queueProviderUpsert(csrf, form.preset, form.name, form.url, form.credentialRef);
			close();
		} catch (cause) {
			setMessage(cause instanceof Error ? cause.message : "Save failed");
		} finally {
			setBusy("");
		}
	}

	return (
		<div className="provider-grid">
			{session.data?.providers.map((p) => (
				<article key={p.id} className="provider-card">
					<header className="provider-card-header">
						<span className="provider-card-name">{p.name}</span>
						<span
							className={cn("provider-card-badge", p.configured ? "configured" : "not-configured")}
						>
							{p.configured ? "Credential configured" : "Not configured"}
						</span>
					</header>
					<p className="provider-card-url mono">
						{p.id === "openrouter"
							? "https://openrouter.ai/api/v1"
							: p.id === "openai"
								? "https://api.openai.com/v1"
								: "Private provider URL"}
					</p>
					<div className="provider-card-actions">
						{!p.configured ? (
							<button
								type="button"
								className="control-button"
								disabled={Boolean(busy)}
								onClick={() => openAdd()}
							>
								Add credential
							</button>
						) : (
							<button
								type="button"
								className="control-button"
								disabled={Boolean(busy)}
								onClick={() => openEdit(p)}
							>
								Edit
							</button>
						)}
					</div>
				</article>
			))}
			{presets.data?.map((item) => (
				<article key={item.id} className="provider-card">
					<header className="provider-card-header">
						<span className="provider-card-name">{item.name}</span>
						<span
							className={cn(
								"provider-card-badge",
								configuredIds.has(item.id) ? "configured" : "not-configured",
							)}
						>
							{configuredIds.has(item.id) ? "Credential configured" : "Not configured"}
						</span>
					</header>
					<p className="provider-card-url mono">{item.url}</p>
					<div className="provider-card-actions">
						{!configuredIds.has(item.id) ? (
							<button
								type="button"
								className="control-button"
								disabled={Boolean(busy)}
								onClick={() => {
									setForm({
										name: item.name,
										url: item.url,
										credentialRef: item.credentialRef,
										preset: item.id,
									});
									setDialogOpen({ mode: "add", preset: item.id });
								}}
							>
								Configure
							</button>
						) : (
							<button
								type="button"
								className="control-button"
								disabled={Boolean(busy)}
								onClick={() => openEdit(item)}
							>
								Edit
							</button>
						)}
					</div>
				</article>
			))}
			<FormModal
				open={!!dialogOpen}
				title={dialogOpen?.mode === "edit" ? "Edit provider" : "Add provider"}
				onClose={close}
				maxWidth="max-w-lg"
			>
				<div className="space-y-4">
					<label className="field">
						Provider preset
						<select
							value={form.preset}
							onChange={(event) => setForm((prev) => ({ ...prev, preset: event.target.value }))}
							disabled={dialogOpen?.mode === "edit"}
						>
							{session.data?.providerPresets.map((p) => (
								<option key={p.id} value={p.id}>
									{p.name} ({p.credentialRef})
								</option>
							))}
						</select>
					</label>
					<label className="field">
						Display name
						<input
							value={form.name}
							onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
							placeholder="e.g. My OpenAI"
							disabled={dialogOpen?.mode === "edit"}
						/>
					</label>
					<label className="field">
						Base URL
						<input
							value={form.url}
							onChange={(event) => setForm((prev) => ({ ...prev, url: event.target.value }))}
							placeholder="https://api.example.com/v1"
							disabled={dialogOpen?.mode === "edit"}
						/>
					</label>
					<label className="field">
						Credential reference (Vault key)
						<input
							value={form.credentialRef}
							onChange={(event) =>
								setForm((prev) => ({ ...prev, credentialRef: event.target.value }))
							}
							placeholder="OPENAI_API_KEY"
							disabled={dialogOpen?.mode === "edit"}
						/>
						<small className="muted">
							Must match the secret name in the server's Vault/Key vault. No keys are entered in the
							browser.
						</small>
					</label>
					{busy && (
						<p role="status" className="muted">
							{busy}
						</p>
					)}
					{message && (
						<p role="alert" className="notice notice-error">
							{message}
						</p>
					)}
					<div className="flex justify-end gap-2">
						<button
							type="button"
							className="control-button"
							onClick={close}
							disabled={Boolean(busy)}
						>
							Cancel
						</button>
						<button
							type="button"
							className="control-button primary"
							onClick={submit}
							disabled={Boolean(busy)}
						>
							{busy || (dialogOpen?.mode === "edit" ? "Save" : "Add")}
						</button>
					</div>
				</div>
			</FormModal>
		</div>
	);
}
