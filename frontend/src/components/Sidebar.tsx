"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FolderGit2,
  Search,
  Bug,
  Bot,
  ShieldCheck,
  CheckCircle2,
  GitPullRequest,
  Activity,
  Settings,
  LogOut,
  Flame,
} from "lucide-react";
import { clearStoredToken, cn } from "@/lib/utils";

const navigationItems = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Repository Explorer", href: "/repositories", icon: FolderGit2 },
  { name: "Code Intelligence", href: "/code-search", icon: Search },
  { name: "AI Debugging", href: "/debugging", icon: Bug },
  { name: "Agent Control Center", href: "/agents", icon: Bot },
  { name: "Security Center", href: "/security", icon: ShieldCheck },
  { name: "Testing Center", href: "/testing", icon: CheckCircle2 },
  { name: "Pull Requests", href: "/pull-requests", icon: GitPullRequest },
  { name: "Monitoring & Eval", href: "/monitoring", icon: Activity },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    clearStoredToken();
    router.push("/login");
  };

  return (
    <aside className="w-64 bg-[#0B0F19] border-r border-border flex flex-col h-screen select-none shrink-0">
      {/* Brand Header */}
      <div className="h-16 flex items-center px-6 border-b border-border/80 gap-3">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-600 via-indigo-600 to-cyan-500 flex items-center justify-center shadow-lg shadow-violet-900/30">
          <Flame className="w-5 h-5 text-white" />
        </div>
        <div>
          <span className="font-bold text-lg tracking-wider text-white">FORGE</span>
          <span className="text-[10px] block font-mono text-cyan-400 tracking-widest uppercase">Autonomous AI</span>
        </div>
      </div>

      {/* Nav links */}
      <div className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navigationItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-violet-600/15 text-violet-400 border border-violet-500/30 shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-[#111827]"
              )}
            >
              <Icon className={cn("w-4 h-4", isActive ? "text-violet-400" : "text-muted-foreground")} />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </div>

      {/* Footer / Logout */}
      <div className="p-4 border-t border-border/80">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 w-full px-3 py-2 text-sm font-medium text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}
