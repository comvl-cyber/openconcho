import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, LockKeyhole, LogOut, ShieldCheck } from "lucide-react";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";
import {
	ADMIN_SESSION_KEY,
	ADMIN_UNAUTHORIZED_EVENT,
	AdminError,
	type AdminSession,
	adminRequest,
	useAdminSession,
} from "@/api/model-admin";
import { requireAppAuth } from "@/lib/runtimeConfig";

const AuthContext = createContext<(() => void) | null>(null);

export function LogoutButton() {
	const logout = useContext(AuthContext);
	return logout ? (
		<button type="button" className="control-button signout-button" onClick={logout}>
			<LogOut size={16} />
			<span>Sign out</span>
		</button>
	) : null;
}

export function AuthGate({ children }: { children: ReactNode }) {
	const [locked, setLocked] = useState(false);
	const [signingOut, setSigningOut] = useState(false);
	const [logoutError, setLogoutError] = useState("");
	const logoutCsrf = useRef("");
	const authRequired = requireAppAuth();
	const session = useAdminSession(!locked && authRequired);
	const queryClient = useQueryClient();
	const [error, setError] = useState("");
	const login = useMutation({
		mutationFn: async (credentials: { username: string; password: string }) => {
			await adminRequest<AdminSession>("login", undefined, credentials);
			return adminRequest<AdminSession>("session");
		},
	});

	useEffect(() => {
		const expire = () => {
			setLocked(true);
			void queryClient.cancelQueries();
			queryClient.clear();
			setError("Your session expired. Sign in again to continue.");
		};
		window.addEventListener(ADMIN_UNAUTHORIZED_EVENT, expire);
		return () => window.removeEventListener(ADMIN_UNAUTHORIZED_EVENT, expire);
	}, [queryClient]);

	useEffect(() => {
		if (!session.error) return;
		// A failed session check must not leave private data in the cache.
		const privateQueries = {
			predicate: (query: { queryKey: readonly unknown[] }) =>
				query.queryKey[0] !== ADMIN_SESSION_KEY[0],
		};
		void queryClient.cancelQueries(privateQueries);
		queryClient.removeQueries(privateQueries);
	}, [session.error, queryClient]);

	async function logout() {
		logoutCsrf.current = session.data?.csrf ?? logoutCsrf.current;
		setLocked(true);
		setSigningOut(true);
		setLogoutError("");
		await queryClient.cancelQueries();
		queryClient.clear();
		try {
			await adminRequest("logout", logoutCsrf.current, {});
			logoutCsrf.current = "";
		} catch (cause) {
			if (!(cause instanceof AdminError && cause.status === 401))
				setLogoutError(
					"The server could not confirm sign out. This screen is locked; retry to revoke your session.",
				);
		} finally {
			setSigningOut(false);
		}
	}

	if (!authRequired) return <AuthContext.Provider value={null}>{children}</AuthContext.Provider>;
	if (signingOut || (!locked && session.isPending))
		return (
			<div className="auth-shell">
				<p role="status">{signingOut ? "Signing out…" : "Checking your session…"}</p>
			</div>
		);
	if (logoutError)
		return (
			<div className="auth-shell">
				<section className="auth-card">
					<h1>Session locked</h1>
					<p role="alert">{logoutError}</p>
					<button type="button" className="control-button" onClick={() => void logout()}>
						Retry sign out
					</button>
				</section>
			</div>
		);
	if (
		!locked &&
		session.error &&
		!(session.error instanceof AdminError && session.error.status === 401)
	)
		return (
			<div className="auth-shell">
				<section className="auth-card">
					<h1>Cannot verify your session</h1>
					<p role="alert">{session.error.message}</p>
					<button type="button" className="control-button" onClick={() => void session.refetch()}>
						Retry connection
					</button>
				</section>
			</div>
		);
	if (!locked && session.data && !session.error)
		return <AuthContext.Provider value={() => void logout()}>{children}</AuthContext.Provider>;

	return (
		<div className="auth-shell">
			<section className="auth-intro" aria-label="About OpenConcho">
				<div className="brand-lockup">
					<img src="/favicon.svg" alt="" width="36" height="36" />
					OpenConcho
				</div>
				<div>
					<p className="eyebrow">YOUR MEMORY, UNDER CONTROL</p>
					<h1>
						A clearer view.
						<br />A better memory.
					</h1>
					<p>
						Explore what your agents remember. Connect your workspaces, choose your models, and keep
						every change in view.
					</p>
				</div>
				<p className="security-note">
					<ShieldCheck size={18} />
					Private infrastructure. Deliberate changes.
				</p>
			</section>
			<section className="auth-card" aria-labelledby="login-title">
				<div className="auth-icon">
					<LockKeyhole size={22} />
				</div>
				<p className="eyebrow">CONTROL CENTER</p>
				<h2 id="login-title">Welcome back</h2>
				<p className="muted">Sign in with your administrator account.</p>
				<form
					onSubmit={async (event) => {
						event.preventDefault();
						const form = event.currentTarget;
						const values = new FormData(form);
						setError("");
						try {
							const verified = await login.mutateAsync({
								username: String(values.get("username") ?? ""),
								password: String(values.get("password") ?? ""),
							});
							form.reset();
							queryClient.setQueryData(ADMIN_SESSION_KEY, verified);
							setLocked(false);
						} catch (cause) {
							setError(
								cause instanceof Error ? cause.message : "Sign in failed. Please try again.",
							);
							const password = form.elements.namedItem("password");
							if (password instanceof HTMLInputElement) password.value = "";
						} finally {
							login.reset();
						}
					}}
				>
					<label className="field">
						Username
						<input name="username" autoComplete="username" required disabled={login.isPending} />
					</label>
					<label className="field">
						Password
						<input
							name="password"
							type="password"
							autoComplete="current-password"
							required
							disabled={login.isPending}
						/>
					</label>
					{error && (
						<p role="alert" className="notice notice-error">
							{error}
						</p>
					)}
					<button className="control-button primary" type="submit" disabled={login.isPending}>
						{login.isPending ? "Signing in…" : "Sign in"}
						<ArrowRight size={16} />
					</button>
				</form>
				<p className="security-note">
					<ShieldCheck size={16} />
					Your session is protected by a secure cookie. App credentials are never saved in browser
					storage.
				</p>
			</section>
		</div>
	);
}
