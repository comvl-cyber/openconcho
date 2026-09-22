import { createContext, type ReactNode, useContext, useState } from "react";

const MobileSidebarContext = createContext<{
	toggle: () => void;
	isOpen: boolean;
	close: () => void;
} | null>(null);

export function useMobileSidebar() {
	const ctx = useContext(MobileSidebarContext);
	if (!ctx) throw new Error("useMobileSidebar must be used within SidebarProvider");
	return ctx;
}

export function SidebarProvider({ children }: { children: ReactNode }) {
	const [mobileOpen, setMobileOpen] = useState(false);
	const toggleMobile = () => setMobileOpen((v) => !v);
	const closeMobile = () => setMobileOpen(false);
	return (
		<MobileSidebarContext.Provider
			value={{ toggle: toggleMobile, isOpen: mobileOpen, close: closeMobile }}
		>
			{children}
		</MobileSidebarContext.Provider>
	);
}
