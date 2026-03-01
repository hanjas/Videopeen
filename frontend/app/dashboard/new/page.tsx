"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function NewProjectPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to dashboard - modal will handle project creation now
    router.replace("/dashboard");
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="text-center">
        <div className="mb-4 flex justify-center text-gray-500"><Loader2 size={40} className="animate-spin" /></div>
        <p className="text-gray-500">Redirecting to dashboard...</p>
      </div>
    </div>
  );
}
