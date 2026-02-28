"use client";

import { useState, useEffect } from "react";
import { useSession, signOut } from "next-auth/react";

const API_BASE = "http://localhost:8000";

function userHeaders(): Record<string, string> {
  const email = typeof window !== "undefined" ? sessionStorage.getItem("vp_user_email") || "anonymous" : "anonymous";
  return { "x-user-email": email };
}

interface SettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsDrawer({ isOpen, onClose }: SettingsDrawerProps) {
  const { data: session } = useSession();
  const [apiKey, setApiKey] = useState("");
  const [maskedKey, setMaskedKey] = useState<string | null>(null);
  const [hasKey, setHasKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchSettings();
    }
  }, [isOpen]);

  useEffect(() => {
    if (message) {
      const t = setTimeout(() => setMessage(null), 4000);
      return () => clearTimeout(t);
    }
  }, [message]);

  async function fetchSettings() {
    try {
      const res = await fetch(`${API_BASE}/api/settings`, { headers: userHeaders() });
      const data = await res.json();
      setHasKey(data.has_api_key);
      setMaskedKey(data.masked_key);
    } catch {
      // ignore
    }
  }

  async function handleSave() {
    if (!apiKey.trim()) return;
    if (!apiKey.trim().startsWith("sk-ant-")) {
      setMessage({ type: "error", text: "Invalid key format. Must start with sk-ant-" });
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/settings/api-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...userHeaders() },
        body: JSON.stringify({ api_key: apiKey.trim() }),
      });
      const data = await res.json();
      if (data.success) {
        setHasKey(true);
        setMaskedKey(data.masked_key);
        setApiKey("");
        setMessage({ type: "success", text: "API key saved successfully" });
      } else {
        setMessage({ type: "error", text: data.error || "Failed to save" });
      }
    } catch {
      setMessage({ type: "error", text: "Failed to save API key" });
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Remove your API key? You won't be able to process videos until you add a new one.")) return;
    setDeleting(true);
    try {
      await fetch(`${API_BASE}/api/settings/api-key`, { method: "DELETE", headers: userHeaders() });
      setHasKey(false);
      setMaskedKey(null);
      setApiKey("");
      setMessage({ type: "success", text: "API key removed" });
    } catch {
      setMessage({ type: "error", text: "Failed to remove API key" });
    } finally {
      setDeleting(false);
    }
  }

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-40 transition-opacity duration-300"
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-full md:w-[400px] bg-[#0a0a0a] border-l border-white/5 z-50 overflow-y-auto transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[#0a0a0a] border-b border-white/5 px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">Settings</h1>
            <p className="text-xs text-gray-500 mt-0.5">Manage your account and API configuration</p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors p-1"
            aria-label="Close settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Toast */}
          {message && (
            <div
              className={`mb-6 px-4 py-3 rounded-lg text-sm ${
                message.type === "success"
                  ? "bg-green-500/10 text-green-400 border border-green-500/20"
                  : "bg-red-500/10 text-red-400 border border-red-500/20"
              }`}
            >
              {message.text}
            </div>
          )}

          {/* Profile */}
          <section className="bg-[#111] rounded-xl border border-white/5 p-5 mb-6">
            <h2 className="text-sm font-semibold text-white mb-4">Profile</h2>
            <div className="flex items-center gap-4">
              {session?.user?.image ? (
                <img src={session.user.image} alt="" className="w-12 h-12 rounded-full" />
              ) : (
                <div className="w-12 h-12 rounded-full bg-accent/20 flex items-center justify-center text-lg text-accent font-bold">
                  {session?.user?.name?.[0] || "?"}
                </div>
              )}
              <div>
                <div className="text-white font-medium">{session?.user?.name || "User"}</div>
                <div className="text-sm text-gray-500">{session?.user?.email}</div>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-white/5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-white">Current plan</div>
                  <div className="text-xs text-gray-500">Free — Bring Your Own Key</div>
                </div>
                <button className="text-xs text-accent hover:text-accent-hover transition-colors" disabled>
                  Upgrade to Pro (coming soon)
                </button>
              </div>
            </div>
          </section>

          {/* API Key */}
          <section className="bg-[#111] rounded-xl border border-white/5 p-5 mb-6">
            <h2 className="text-sm font-semibold text-white mb-1">Anthropic API Key</h2>
            <p className="text-xs text-gray-500 mb-5">
              Required to process videos. Get your key from{" "}
              <a
                href="https://console.anthropic.com/settings/keys"
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline"
              >
                console.anthropic.com
              </a>
            </p>

            {hasKey && maskedKey && (
              <div className="flex items-center gap-3 mb-4 px-4 py-3 bg-white/5 rounded-lg">
                <div className="flex-1 font-mono text-sm text-gray-300 select-none truncate">{maskedKey}</div>
                <span className="text-xs text-green-400 bg-green-400/10 px-2 py-0.5 rounded-full">Active</span>
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50"
                >
                  {deleting ? "Removing..." : "Remove"}
                </button>
              </div>
            )}

            <div className="flex gap-3">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={hasKey ? "Enter new key to replace" : "sk-ant-api03-..."}
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-colors"
                onKeyDown={(e) => e.key === "Enter" && handleSave()}
              />
              <button
                onClick={handleSave}
                disabled={saving || !apiKey.trim()}
                className="px-5 py-2.5 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-lg transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {saving ? "Saving..." : hasKey ? "Update" : "Save"}
              </button>
            </div>

            <p className="mt-3 text-xs text-gray-600">
              Your key is stored securely and only used to process your videos. We never share it.
            </p>
          </section>

          {/* Danger Zone */}
          <section className="bg-[#111] rounded-xl border border-red-500/10 p-5">
            <h2 className="text-sm font-semibold text-red-400 mb-4">Danger Zone</h2>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-white">Sign out</div>
                <div className="text-xs text-gray-500">You&apos;ll need to sign in again</div>
              </div>
              <button
                onClick={() => {
                  onClose();
                  signOut({ callbackUrl: "/" });
                }}
                className="px-4 py-2 text-sm text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/10 transition-all duration-200"
              >
                Sign Out
              </button>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
