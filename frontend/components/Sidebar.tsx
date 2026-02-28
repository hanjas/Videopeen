"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession, signOut } from "next-auth/react";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: "▦" },
];

interface SidebarProps {
  onOpenSettings: () => void;
}

export default function Sidebar({ onOpenSettings }: SidebarProps) {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <aside className="w-56 bg-[#111] border-r border-white/5 min-h-screen flex flex-col">
      <Link href="/" className="px-5 py-5 text-lg font-bold text-white tracking-tight block">
        <span className="text-accent">Video</span>peen
      </Link>
      <nav className="flex-1 px-3 mt-2">
        {nav.map((item) => {
          const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm mb-0.5 transition-all duration-200 ${
                active ? "bg-white/10 text-white" : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
        
        {/* Settings - Opens drawer instead of navigating */}
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm mb-0.5 transition-all duration-200 text-gray-400 hover:text-white hover:bg-white/5"
        >
          <span className="text-base">⚙</span>
          Settings
        </button>
      </nav>
      <div className="p-4 border-t border-white/5">
        <div className="flex items-center gap-3">
          {session?.user?.image ? (
            <img src={session.user.image} alt="" className="w-8 h-8 rounded-full" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center text-sm text-accent font-bold">
              {session?.user?.name?.[0] || "?"}
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-sm text-white font-medium truncate">{session?.user?.name || "User"}</div>
            <div className="text-xs text-gray-500">Free plan</div>
          </div>
        </div>
        <button
          onClick={() => signOut({ callbackUrl: "/" })}
          className="mt-3 w-full text-xs text-gray-500 hover:text-white transition-all duration-200 text-left"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
