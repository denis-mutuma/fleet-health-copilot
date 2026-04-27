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
    label: "Operations",
    description: "Dashboard and incidents"
  },
  {
    href: "/chat",
    label: "Chat",
    description: "Operator copilot"
  },
  {
    href: "/rag",
    label: "Knowledge",
    description: "Retrieval corpus"
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
            <span className="app-brand-mark">FH</span>
            <span>
              <strong>Fleet Health Copilot</strong>
              <span className="app-brand-subtitle">Operations console</span>
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
              <span className="app-nav-description">{item.description}</span>
            </Link>
          ))}
        </nav>

        <div className="app-sidebar-panel">
          <p className="sidebar-label">Live workflow</p>
          <ul className="sidebar-list">
            <li>Monitor telemetry anomalies</li>
            <li>Inspect grounded evidence</li>
            <li>Coordinate action in chat</li>
          </ul>
        </div>
      </aside>

      <div className="app-canvas">
        <header className="app-topbar">
          <div>
            <p className="topbar-kicker">Multi-agent incident operations</p>
            <h1 className="topbar-title">Fleet Health Copilot</h1>
          </div>
          <div className="app-topbar-actions">
            <span className="topbar-chip">RAG-enabled</span>
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