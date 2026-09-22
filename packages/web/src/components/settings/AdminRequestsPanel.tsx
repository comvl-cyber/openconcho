import { useAdminRequests, useAdminSession } from "@/api/model-admin";
import { cn } from "@/lib/utils";

export function AdminRequestsPanel() {
	const session = useAdminSession();
	const requests = useAdminRequests(Boolean(session.data) && !session.error);

	if (!session.data) return null;

	return (
		<div className="requests-list">
			{requests.data?.requests.slice(0, 50).map((item) => (
				<article key={item.id} className="request-item">
					<header className="request-item-header">
						<span className="request-kind">{item.kind.replace("-", " ")}</span>
						<span className={cn("request-status", item.status)}>
							{item.status === "running"
								? "◐"
								: item.status === "applied"
									? "✓"
									: item.status === "rejected" || item.status === "failed"
										? "✗"
										: "⏳"}{" "}
							{item.status}
						</span>
					</header>
					<div className="request-meta mono">
						<span>{item.submittedBy}</span>
						<span>{new Date(item.createdAt).toLocaleString()}</span>
						<span>
							{item.updatedAt !== item.createdAt ? new Date(item.updatedAt).toLocaleString() : ""}
						</span>
					</div>
					<div className="request-payload mono">{JSON.stringify(item.payload, null, 2)}</div>
					{item.result && (
						<div className="request-result mono">
							{item.result.message} — {item.result.revision}
						</div>
					)}
				</article>
			))}
			{!requests.data?.requests.length && (
				<p className="muted">No requests yet. Switch or add a model to create one.</p>
			)}
		</div>
	);
}
