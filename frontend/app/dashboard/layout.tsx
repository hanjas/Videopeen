"use client";
import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import SettingsDrawer from "@/components/SettingsDrawer";
import { setUserEmail } from "@/lib/api";
import { ToastProvider } from "@/components/Toast";

function SyncUser() {
  const { data: session } = useSession();
  useEffect(() => {
    if (session?.user?.email) {
      setUserEmail(session.user.email);
    }
  }, [session]);
  return null;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <ToastProvider>
      <div className="flex min-h-screen bg-[#0a0a0a]">
        <SyncUser />
        <Sidebar onOpenSettings={() => setIsSettingsOpen(true)} />
        <main className="flex-1 p-6 min-w-0 overflow-x-hidden overflow-y-auto h-screen">{children}</main>
        <SettingsDrawer isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
      </div>
    </ToastProvider>
  );
}
