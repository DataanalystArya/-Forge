"use client";

import React, { useEffect, useState } from "react";
import { Activity, Bell, ChevronDown, Shield, Terminal } from "lucide-react";
import { API_BASE_URL, fetchWithAuth } from "@/lib/utils";

interface UserProfile {
  id: string;
  email: string;
  full_name?: string;
}

export function Header() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "degraded">("checking");

  useEffect(() => {
    // Check API Health
    fetch(`${API_BASE_URL}/health`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.status === "healthy") {
          setApiStatus("online");
        } else {
          setApiStatus("degraded");
        }
      })
      .catch(() => setApiStatus("degraded"));

    // Fetch Current User
    fetchWithAuth("/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setUser(data);
      })
      .catch(() => {});
  }, []);

  return (
    <header className="h-16 border-b border-border bg-[#0B0F19]/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center gap-4">
        {/* System Health Status Indicator */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#111827] border border-border text-xs font-mono">
          <span
            className={`w-2 h-2 rounded-full ${
              apiStatus === "online"
                ? "bg-emerald-400 animate-pulse"
                : apiStatus === "checking"
                ? "bg-amber-400"
                : "bg-rose-400"
            }`}
          />
          <span className="text-muted-foreground">ENGINE:</span>
          <span
            className={`font-semibold ${
              apiStatus === "online"
                ? "text-emerald-400"
                : apiStatus === "checking"
                ? "text-amber-400"
                : "text-rose-400"
            }`}
          >
            {apiStatus.toUpperCase()}
          </span>
        </div>

        {/* Sandboxed Badge */}
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-violet-950/40 border border-violet-800/40 text-xs font-mono text-violet-300">
          <Shield className="w-3.5 h-3.5 text-violet-400" />
          <span>ISOLATED SANDBOX</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Notifications */}
        <button className="p-2 text-muted-foreground hover:text-foreground rounded-lg hover:bg-card transition-colors relative">
          <Bell className="w-4 h-4" />
          <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full absolute top-2 right-2" />
        </button>

        {/* User Badge */}
        <div className="flex items-center gap-3 pl-4 border-l border-border">
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-violet-600 to-cyan-500 flex items-center justify-center text-xs font-bold text-white uppercase shadow-sm">
            {user?.full_name ? user.full_name[0] : user?.email ? user.email[0] : "U"}
          </div>
          <div className="hidden md:block text-left">
            <div className="text-sm font-medium text-foreground leading-none">
              {user?.full_name || "Developer"}
            </div>
            <div className="text-xs text-muted-foreground font-mono mt-1 leading-none">
              {user?.email || "Signed in"}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
