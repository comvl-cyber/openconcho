import { useState } from "react";
import type { ModelCatalog } from "@/api/model-admin";

export function ModelCatalogBrowser({
	catalog,
	loading,
	selected,
	onSelect,
}: {
	catalog?: ModelCatalog;
	loading: boolean;
	selected: string;
	onSelect: (id: string) => void;
}) {
	const [search, setSearch] = useState("");
	const [knownOnly, setKnownOnly] = useState(false);
	const models =
		catalog?.models.filter(
			(item) =>
				`${item.id} ${item.name}`.toLowerCase().includes(search.toLowerCase()) &&
				(!knownOnly || (item.input !== null && item.output !== null)),
		) ?? [];
	const price = (value: string | null) =>
		value === null ? "Unavailable" : `${catalog?.currency ?? "Currency unavailable"} ${value}`;
	return (
		<div className="model-catalog">
			<div className="model-search">
				<input
					type="search"
					aria-label="Search models"
					className="model-search-input"
					placeholder="Search models or vendors…"
					value={search}
					onChange={(event) => setSearch(event.target.value)}
				/>
				<label className="model-filter-checkbox">
					<input
						type="checkbox"
						checked={knownOnly}
						onChange={(event) => setKnownOnly(event.target.checked)}
					/>
					Known pricing only
				</label>
			</div>
			<p className="muted">
				Input / output prices per 1 million tokens. Provider estimates; route-specific costs and
				taxes may vary.
			</p>
			{loading && <p role="status">Fetching provider catalog…</p>}
			<div className="model-grid">
				{models.map((item) => (
					<button
						type="button"
						className={`model-card ${selected === item.id ? "selected" : ""}`}
						key={item.id}
						aria-label={`Select ${item.id}`}
						aria-pressed={selected === item.id}
						onClick={() => onSelect(item.id)}
					>
						<span className="model-card-name">{item.name}</span>
						<span className="model-card-meta mono">{item.id}</span>
						<span className="model-card-pricing">
							<span>
								Input<strong>{price(item.input)}</strong>
							</span>
							<span>
								Output<strong>{price(item.output)}</strong>
							</span>
						</span>
						<span className="model-card-meta">
							Cached input: {price(item.cache)}
							{item.context ? ` · ${item.context.toLocaleString()} context` : ""}
						</span>
					</button>
				))}
			</div>
			{!loading && !models.length && <p className="notice">No models match these filters.</p>}
			{catalog && (
				<details className="catalog-source">
					<summary>
						{models.length} of {catalog.count} catalog models · Pricing source
					</summary>
					<p>
						{catalog.source} · Fetched: {catalog.fetchedAt}
					</p>
				</details>
			)}
		</div>
	);
}
