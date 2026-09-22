import { createRootRoute, Outlet, redirect } from "@tanstack/react-router";
import { Menu, X } from "lucide-react";
import { useEffect } from "react";
import { AuthGate } from "@/components/auth/AuthGate";
import { Sidebar } from "@/components/layout/Sidebar";
import { useMobileSidebar } from "@/components/layout/SidebarContext";
import { loadConfig } from "@/lib/config";
import { applyTheme, getStoredTheme } from "@/lib/theme";

const SETTINGS_PATH = "/settings";

function RootLayout() {
	const { toggle, isOpen } = useMobileSidebar();
	useEffect(() => {
		applyTheme(getStoredTheme());
	}, []);

	return (
		<AuthGate>
			<div
				className="flex h-screen w-full overflow-hidden"
				style={{ background: "var(--bg)", position: "relative", zIndex: 1 }}
			>
				<Sidebar />
				<main className="flex-1 overflow-auto relative" style={{ position: "relative", zIndex: 1 }}>
					<button
						type="button"
						className="lg:hidden fixed top-4 left-4 z-30 w-10 h-10 rounded-lg flex items-center justify-center transition-colors"
						style={{
							background: "var(--surface)",
							border: "1px solid var(--border)",
							color: "var(--text-1)",
						}}
						onClick={toggle}
						aria-label={isOpen ? "Close menu" : "Open menu"}
						aria-expanded={isOpen}
					>
						{isOpen ? (
							<X className="w-5 h-5" strokeWidth={2} />
						) : (
							<Menu className="w-5 h-5" strokeWidth={2} />
						)}
					</button>
					<Outlet />
				</main>
			</div>
		</AuthGate>
	);
}

export const Route = createRootRoute({
	beforeLoad: ({ location }) => {
		// Redirect to settings synchronously when no config is present, so the
		// first paint already shows the settings form instead of a blank screen.
		if (location.pathname !== SETTINGS_PATH && !loadConfig()) {
			throw redirect({ to: SETTINGS_PATH as never });
		}
	},
	component: RootLayout,
});
