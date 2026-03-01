"use client";
import Sidebar from "@/components/Sidebar";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-[#0a0a0a]">
      <Sidebar onOpenSettings={() => {}} />
      <main className="flex-1 p-8">{children}</main>
    </div>
  );
}
