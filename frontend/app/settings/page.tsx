"use client";
import { useState, useEffect } from "react";

export default function SettingsPage() {
  const [showKey, setShowKey] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("videopeen_api_key") || "";
    setApiKey(stored);
  }, []);

  const connected = apiKey.length > 0 && saved;

  useEffect(() => {
    const stored = localStorage.getItem("videopeen_api_key") || "";
    setSaved(stored.length > 0 && stored === apiKey);
  }, [apiKey]);

  const handleSave = () => {
    localStorage.setItem("videopeen_api_key", apiKey);
    setSaved(true);
  };

  const handleRemove = () => {
    localStorage.removeItem("videopeen_api_key");
    setApiKey("");
    setSaved(false);
  };

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-white mb-8">Settings</h1>

      <section className="bg-surface rounded-xl border border-white/5 p-6 mb-6">
        <h2 className="text-base font-semibold text-white mb-1">API Key Management</h2>
        <p className="text-xs text-gray-500 mb-5">Connect your Anthropic API key for AI processing</p>
        <div className="flex items-center gap-2 mb-3">
          <div className="relative flex-1">
            <input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-ant-api03-..."
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-all duration-200"
            />
            <button
              onClick={() => setShowKey(!showKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-white transition-all duration-200"
            >
              {showKey ? "Hide" : "Show"}
            </button>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-500" : "bg-gray-600"}`} />
            <span className="text-xs text-gray-400">{connected ? "Connected ✓" : "Not set"}</span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={!apiKey.trim()}
              className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-all duration-200 disabled:opacity-50"
            >
              Save
            </button>
            <button
              onClick={handleRemove}
              className="px-4 py-2 rounded-lg border border-white/10 text-sm text-gray-400 hover:text-red-400 hover:border-red-400/30 transition-all duration-200"
            >
              Remove
            </button>
          </div>
        </div>
      </section>

      <section className="bg-surface rounded-xl border border-white/5 p-6">
        <h2 className="text-base font-semibold text-white mb-4">About</h2>
        <p className="text-sm text-gray-400">Videopeen v1.0 — AI Cooking Video Editor</p>
        <p className="text-xs text-gray-600 mt-1">Backend: http://localhost:8000</p>
      </section>
    </div>
  );
}
