"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function NewProjectPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to dashboard - modal will handle project creation now
    router.replace("/dashboard");
  }, [router]);

  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="text-center">
        <div className="text-4xl mb-4">🔄</div>
        <p className="text-gray-500">Redirecting to dashboard...</p>
      </div>
    </div>
  );
}
