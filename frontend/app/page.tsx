"use client";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sparkles, Download, Upload, Zap } from "lucide-react";

export default function LandingPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.push("/dashboard");
  }, [status, router]);

  if (status === "loading" || status === "authenticated") {
    return <div className="min-h-screen bg-[#0a0a0a]" />;
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      {/* Nav */}
      <nav className="flex items-center justify-between px-8 py-5 max-w-6xl mx-auto">
        <Link href="/" className="text-xl font-bold text-white tracking-tight">
          <span className="text-accent">Video</span>peen
        </Link>
        <div className="flex items-center gap-4">
          <button onClick={() => signIn("google")} className="text-sm text-gray-400 hover:text-white transition-all duration-200">
            Sign In
          </button>
          <button
            onClick={() => signIn("google")}
            className="text-sm bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg font-medium transition-all duration-200"
          >
            Get Started
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto text-center pt-24 pb-20 px-8">
        <div className="inline-flex items-center gap-1.5 mb-6 px-4 py-1.5 rounded-full border border-white/10 text-xs text-gray-400 bg-white/5">
          <Sparkles size={14} /> Now in public beta
        </div>
        <h1 className="text-5xl md:text-6xl font-bold text-white leading-tight mb-6">
          AI Cooking Video
          <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-amber-400">
            Editor
          </span>
        </h1>
        <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
          Upload your raw cooking footage. Our AI identifies the best moments, cuts, and transitions — delivering a polished short-form video in minutes.
        </p>
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => signIn("google")}
            className="bg-accent hover:bg-accent-hover text-white px-8 py-3.5 rounded-xl font-semibold text-base transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20"
          >
            Start Editing — Free
          </button>
          <a href="#how" className="text-gray-400 hover:text-white text-sm transition-all duration-200">
            See how it works ↓
          </a>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="max-w-5xl mx-auto py-20 px-8">
        <h2 className="text-2xl font-bold text-white text-center mb-14">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { step: "1", Icon: Upload, title: "Upload", desc: "Drop your raw cooking footage — any length, any format." },
            { step: "2", Icon: Zap, title: "AI Edits", desc: "Our AI detects key moments, adds cuts, transitions, and pacing." },
            { step: "3", Icon: Download, title: "Download", desc: "Get a polished short-form video ready for TikTok, Reels, or Shorts." },
          ].map((item) => (
            <div
              key={item.step}
              className="bg-surface rounded-2xl p-8 text-center hover:bg-surface-light transition-all duration-200 border border-white/5 hover:border-white/10"
            >
              <div className="mb-4 flex justify-center text-accent"><item.Icon size={40} /></div>
              <div className="text-xs text-accent font-semibold mb-2">STEP {item.step}</div>
              <h3 className="text-lg font-semibold text-white mb-2">{item.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="max-w-4xl mx-auto py-20 px-8">
        <h2 className="text-2xl font-bold text-white text-center mb-4">Simple pricing</h2>
        <p className="text-gray-400 text-center mb-14 text-sm">Start free with your own API key. Upgrade when you&apos;re ready.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-3xl mx-auto">
          <div className="bg-surface rounded-2xl p-8 border border-white/5 hover:border-white/10 transition-all duration-200">
            <div className="text-sm text-gray-400 font-medium mb-1">Free</div>
            <div className="text-3xl font-bold text-white mb-1">$0<span className="text-sm text-gray-500 font-normal">/mo</span></div>
            <div className="text-xs text-gray-500 mb-6">Bring your own API key</div>
            <ul className="space-y-3 text-sm text-gray-300 mb-8">
              {["Unlimited projects", "All video styles", "BYOK (Anthropic)", "Community support"].map((f) => (
                <li key={f} className="flex items-center gap-2"><span className="text-green-500">✓</span>{f}</li>
              ))}
            </ul>
            <button onClick={() => signIn("google")} className="block text-center w-full py-2.5 rounded-lg border border-white/10 text-sm text-white hover:bg-white/5 transition-all duration-200">
              Get Started
            </button>
          </div>
          <div className="bg-surface rounded-2xl p-8 border border-accent/30 hover:border-accent/50 transition-all duration-200 relative">
            <div className="absolute -top-3 left-8 px-3 py-0.5 bg-accent text-white text-xs rounded-full font-medium">Popular</div>
            <div className="text-sm text-accent font-medium mb-1">Pro</div>
            <div className="text-3xl font-bold text-white mb-1">$25<span className="text-sm text-gray-500 font-normal">/mo</span></div>
            <div className="text-xs text-gray-500 mb-6">No API key needed</div>
            <ul className="space-y-3 text-sm text-gray-300 mb-8">
              {["Everything in Free", "No API key required", "Priority processing", "Premium support", "Early access to features"].map((f) => (
                <li key={f} className="flex items-center gap-2"><span className="text-accent">✓</span>{f}</li>
              ))}
            </ul>
            <button onClick={() => signIn("google")} className="block text-center w-full py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-sm text-white font-medium transition-all duration-200">
              Upgrade to Pro
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 mt-10">
        <div className="max-w-6xl mx-auto px-8 py-10 flex items-center justify-between">
          <div className="text-sm text-gray-500">© 2025 Videopeen. All rights reserved.</div>
          <div className="flex gap-6 text-sm text-gray-500">
            <a href="#" className="hover:text-white transition-all duration-200">Twitter</a>
            <a href="#" className="hover:text-white transition-all duration-200">GitHub</a>
            <a href="#" className="hover:text-white transition-all duration-200">Discord</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
