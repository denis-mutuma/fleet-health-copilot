"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  SignInButton,
  SignedIn,
  SignedOut,
  UserButton
} from "@clerk/nextjs";

type AppShellProps = {
  children: React.ReactNode;
};

const NAV_ITEMS = [
  {
    href: "/",
    label: "Operations"
  },
  {
    href: "/chat",
    label: "Chat"
  },
  {
    href: "/rag",
    label: "Knowledge"
  }
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/" || pathname.startsWith("/incidents/");
  }

  return pathname.startsWith(href);
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand-block">
          <Link href="/" className="app-brand-link">
            <span>
              <strong>Fleet Health Copilot</strong>
              <span className="app-brand-subtitle">Fleet command</span>
            </span>
          </Link>
        </div>

        <nav className="app-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`app-nav-link ${isActive(pathname, item.href) ? "active" : ""}`}
            >
              <span className="app-nav-title">{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="app-sidebar-panel">
          <p className="sidebar-label">Ops cycle</p>
          <ul className="sidebar-list">
            <li>Detect anomaly</li>
            <li>Verify evidence</li>
            <li>Dispatch action</li>
          </ul>
        </div>
      </aside>

      <div className="app-canvas">
        <header className="app-topbar">
          <div>
            <p className="topbar-kicker">Command center</p>
            <h1 className="topbar-title">Fleet Health Copilot</h1>
          </div>
          <div className="app-topbar-actions">
            <span className="topbar-chip">Ops board</span>
            <span className="topbar-chip">Corpus linked</span>
            <SignedIn>
              <UserButton />
            </SignedIn>
            <SignedOut>
              <SignInButton mode="modal">
                <button type="button" className="button secondary-button">
                  Sign in
                </button>
              </SignInButton>
            </SignedOut>
          </div>
        </header>

        <div className="app-content">{children}</div>
      </div>
    </div>
  );
}
