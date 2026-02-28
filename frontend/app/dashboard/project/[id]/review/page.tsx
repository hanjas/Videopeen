"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";

interface Clip {
  clip_id: string;
  order: number;
  source_video: string;
  source_path: string;
  start_time: number;
  end_time: number;
  duration: number;
  effective_duration: number;
  speed_factor: number;
  action_id: number;
  description: string;
  reason: string;
  recipe_step: number | null;
  thumbnail_path: string | null;
  status: "included" | "excluded" | "added_by_user";
  added_by: "ai" | "user";
}

const STAGE_COLORS: Record<string, string> = {
  prep: "bg-blue-500",
  cooking: "bg-orange-500",
  plating: "bg-green-500",
  serve: "bg-yellow-500",
};

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { toast } = useToast();

  const [clips, setClips] = useState<Clip[]>([]);
  const [clipPool, setClipPool] = useState<Clip[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState("");
  const [totalDuration, setTotalDuration] = useState(0);
  const [targetDuration, setTargetDuration] = useState(60);
  const [previewClip, setPreviewClip] = useState<Clip | null>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [showPool, setShowPool] = useState(false);
  const [editorNotes, setEditorNotes] = useState("");

  const videoRef = useRef<HTMLVideoElement>(null);

  const fetchPlan = useCallback(async () => {
    try {
      const plan = await api.getEditPlan(id);
      const timelineClips = (plan.timeline?.clips || []).sort(
        (a: Clip, b: Clip) => a.order - b.order
      );
      setClips(timelineClips);
      setClipPool(plan.clip_pool || []);
      setTargetDuration(plan.timeline?.target_duration || 60);
      setTotalDuration(plan.timeline?.total_effective_duration || 0);
      setEditorNotes(plan.editor_notes || "");
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load edit plan");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchPlan();
  }, [fetchPlan]);

  // Recalculate total duration when clips change
  useEffect(() => {
    const total = clips
      .filter((c) => c.status === "included")
      .reduce((sum, c) => sum + c.effective_duration, 0);
    setTotalDuration(total);
  }, [clips]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  // Format AI notes into structured sections
  const formatAINotes = (notes: string) => {
    if (!notes) return null;
    
    // Try to detect and format sections
    const sections: { title: string; content: string }[] = [];
    
    // Common patterns in AI notes
    const patterns = [
      { regex: /This is (?:a |an )?([^.]+)\./i, title: "Recipe" },
      { regex: /Edit flow[s]?:\s*([^.]+(?:→[^.]+)*)/i, title: "Flow" },
      { regex: /Key moment[s]?:\s*([^.]+)/i, title: "Key Moments" },
      { regex: /Duration[^:]*:\s*([^.]+)/i, title: "Duration" },
      { regex: /(\d+)\s*clips?/i, title: "Clips" },
    ];
    
    let remainingNotes = notes;
    
    patterns.forEach(({ regex, title }) => {
      const match = remainingNotes.match(regex);
      if (match) {
        sections.push({ title, content: match[1] || match[0] });
        remainingNotes = remainingNotes.replace(match[0], "").trim();
      }
    });
    
    // If no patterns matched, just return the original notes
    if (sections.length === 0) {
      return <span className="text-gray-400">{notes}</span>;
    }
    
    return (
      <div className="space-y-2">
        {sections.map((section, idx) => (
          <div key={idx}>
            <span className="text-accent font-medium">{section.title}:</span>{" "}
            <span className="text-gray-400">{section.content}</span>
          </div>
        ))}
        {remainingNotes && (
          <div className="text-gray-500 text-xs mt-1">{remainingNotes}</div>
        )}
      </div>
    );
  };

  // ---- Drag & Drop ---- //
  const handleDragStart = (idx: number) => {
    setDragIdx(idx);
  };

  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    setDragOverIdx(idx);
  };

  const handleDrop = (idx: number) => {
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null);
      setDragOverIdx(null);
      return;
    }
    const newClips = [...clips];
    const [moved] = newClips.splice(dragIdx, 1);
    newClips.splice(idx, 0, moved);
    // Update order
    newClips.forEach((c, i) => (c.order = i));
    setClips(newClips);
    setDragIdx(null);
    setDragOverIdx(null);
  };

  const handleDragEnd = () => {
    setDragIdx(null);
    setDragOverIdx(null);
  };

  // ---- Actions ---- //
  const removeClip = (clipId: string) => {
    const clip = clips.find((c) => c.clip_id === clipId);
    if (!clip) return;
    // Move to pool
    setClips((prev) => prev.filter((c) => c.clip_id !== clipId));
    setClipPool((prev) => [...prev, { ...clip, status: "excluded" as const }]);
    toast("info", `Removed "${clip.description.slice(0, 30)}..."`);
  };

  const addFromPool = (clipId: string) => {
    const clip = clipPool.find((c) => c.clip_id === clipId);
    if (!clip) return;
    // Add to end of timeline
    const newClip: Clip = {
      ...clip,
      status: "included",
      added_by: "user",
      order: clips.length,
      speed_factor: clip.speed_factor || 1.0,
      effective_duration: clip.duration / (clip.speed_factor || 1.0),
    };
    setClips((prev) => [...prev, newClip]);
    setClipPool((prev) => prev.filter((c) => c.clip_id !== clipId));
    toast("success", `Added "${clip.description.slice(0, 30)}..."`);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateEditPlan(id, clips);
      toast("success", "Edit plan saved");
    } catch {
      toast("error", "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmRender = async () => {
    if (!confirm("Confirm and start rendering? This will generate the final video.")) return;
    setRendering(true);
    try {
      // Save latest changes first
      await api.updateEditPlan(id, clips);
      await api.confirmAndRender(id);
      toast("success", "Rendering started! 🎬");
      router.push(`/dashboard/project/${id}`);
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Failed to start render");
      setRendering(false);
    }
  };

  const handlePreview = (clip: Clip) => {
    setPreviewClip(clip);
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-white/5 rounded w-48" />
        <div className="flex gap-3 overflow-x-auto">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="flex-shrink-0 w-44 h-36 bg-white/5 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-red-400">{error}</p>
        <Link href={`/dashboard/project/${id}`} className="text-sm text-accent mt-4 inline-block">
          ← Back to Project
        </Link>
      </div>
    );
  }

  const durationPct = targetDuration > 0 ? Math.min((totalDuration / targetDuration) * 100, 150) : 0;
  const durationOk = totalDuration >= targetDuration - 10 && totalDuration <= targetDuration + 10;
  
  // More nuanced duration status: green (good), amber (slightly over), red (too much over)
  const getDurationStatus = () => {
    if (totalDuration <= targetDuration + 5) {
      return { color: "bg-green-500", text: "text-green-400", icon: "✓", message: "" };
    } else if (totalDuration <= targetDuration + 10) {
      return { color: "bg-yellow-500", text: "text-yellow-400", icon: "⚠", message: " (slightly over)" };
    } else {
      return { color: "bg-red-500", text: "text-red-400", icon: "✕", message: " (too long)" };
    }
  };
  
  const durationStatus = getDurationStatus();

  return (
    <div className="h-full flex flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between mb-6 flex-shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-white">Review & Arrange</h1>
          <p className="text-sm text-gray-500 mt-1">
            {clips.length} clips · {formatTime(totalDuration)} / {formatTime(targetDuration)} target
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2.5 rounded-lg border border-white/10 text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-all duration-200 disabled:opacity-50"
          >
            {saving ? "Saving..." : "💾 Save"}
          </button>
          <button
            onClick={handleConfirmRender}
            disabled={rendering || clips.length === 0}
            className="bg-accent hover:bg-accent-hover text-white px-6 py-2.5 rounded-lg font-medium text-sm transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20 disabled:opacity-50"
          >
            {rendering ? "Starting..." : "🎬 Render Final"}
          </button>
          <Link
            href={`/dashboard/project/${id}`}
            className="px-4 py-2.5 rounded-lg text-sm text-gray-500 hover:text-white transition-all duration-200"
          >
            ← Back
          </Link>
        </div>
      </div>

      {/* Duration gauge */}
      <div className="mb-6 flex-shrink-0">
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="text-gray-400">Duration</span>
          <span className={durationStatus.text}>
            {formatTime(totalDuration)} / {formatTime(targetDuration)} {durationStatus.icon}{durationStatus.message}
          </span>
        </div>
        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${durationStatus.color}`}
            style={{ width: `${Math.min(durationPct, 100)}%` }}
          />
        </div>
      </div>

      {/* Preview modal */}
      {previewClip && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center" onClick={() => setPreviewClip(null)}>
          <div className="max-w-lg w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <video
              ref={videoRef}
              src={`${api.getVideoUrl(previewClip.source_path)}#t=${previewClip.start_time},${previewClip.end_time}`}
              controls
              autoPlay
              className="w-full rounded-xl"
              style={{ maxHeight: "60vh" }}
            />
            <div className="mt-3 text-center">
              <p className="text-white text-sm">{previewClip.description}</p>
              <p className="text-gray-500 text-xs mt-1">
                {formatTime(previewClip.start_time)} – {formatTime(previewClip.end_time)} · {previewClip.source_video}
              </p>
              <button onClick={() => setPreviewClip(null)} className="mt-3 text-sm text-gray-400 hover:text-white">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Editor notes */}
      {editorNotes && (
        <div className="mb-4 px-4 py-3 bg-yellow-500/5 rounded-lg border border-yellow-500/20 text-xs flex-shrink-0">
          <div className="font-semibold text-yellow-400 mb-2 flex items-center gap-1">
            <span>✨</span> AI Analysis
          </div>
          {formatAINotes(editorNotes)}
        </div>
      )}

      {/* Timeline */}
      <div className="mb-6 flex-shrink-0">
        <h2 className="text-sm font-semibold text-white mb-3">Timeline ({clips.length} clips)</h2>
        <div className="relative">
          {/* Left scroll arrow */}
          <button
            onClick={() => {
              const container = document.getElementById('review-clip-timeline');
              if (container) container.scrollBy({ left: -200, behavior: 'smooth' });
            }}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-black/80 hover:bg-black/90 text-white rounded-full w-8 h-8 flex items-center justify-center transition-all duration-200 shadow-lg hover:shadow-xl"
            title="Scroll left"
          >
            ←
          </button>
          
          {/* Right scroll arrow */}
          <button
            onClick={() => {
              const container = document.getElementById('review-clip-timeline');
              if (container) container.scrollBy({ left: 200, behavior: 'smooth' });
            }}
            className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-black/80 hover:bg-black/90 text-white rounded-full w-8 h-8 flex items-center justify-center transition-all duration-200 shadow-lg hover:shadow-xl"
            title="Scroll right"
          >
            →
          </button>
          
          <div id="review-clip-timeline" className="flex gap-3 overflow-x-auto pb-3 scroll-smooth">
            {clips.map((clip, idx) => (
            <div
              key={clip.clip_id}
              draggable
              onDragStart={() => handleDragStart(idx)}
              onDragOver={(e) => handleDragOver(e, idx)}
              onDrop={() => handleDrop(idx)}
              onDragEnd={handleDragEnd}
              className={`flex-shrink-0 w-44 bg-[#141414] rounded-xl border transition-all duration-200 overflow-hidden group cursor-grab active:cursor-grabbing ${
                dragOverIdx === idx ? "border-accent scale-[1.02]" : "border-white/5 hover:border-white/15"
              } ${dragIdx === idx ? "opacity-40" : ""}`}
            >
              {/* Thumbnail */}
              <div
                className="aspect-video bg-[#1a1a1a] flex items-center justify-center relative cursor-pointer"
                onClick={() => handlePreview(clip)}
              >
                {clip.thumbnail_path ? (
                  <img
                    src={api.getClipThumbnailUrl(id, clip.clip_id)}
                    alt={clip.description}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <span className="text-2xl">🎬</span>
                )}
                {/* Duration badge */}
                <span className="absolute bottom-1 right-1 text-[10px] bg-black/70 text-white px-1.5 py-0.5 rounded">
                  {formatTime(clip.effective_duration)}
                </span>
                {/* Play icon on hover */}
                <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <span className="text-white text-xl">▶</span>
                </div>
              </div>

              {/* Info */}
              <div className="p-2.5">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-accent font-semibold">Clip {idx + 1}</span>
                  <div className="flex items-center gap-1.5">
                    {clip.speed_factor !== 1.0 && (
                      <span className="text-[9px] text-yellow-400 bg-yellow-400/10 px-1 rounded">
                        {clip.speed_factor}x
                      </span>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); removeClip(clip.clip_id); }}
                      className="text-gray-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100 text-xs"
                    >
                      ✕
                    </button>
                  </div>
                </div>
                <p className="text-[11px] text-gray-300 truncate" title={clip.description}>
                  {clip.description || "—"}
                </p>
                <p className="text-[9px] text-gray-600 mt-0.5 truncate">
                  {clip.source_video} · {formatTime(clip.start_time)}–{formatTime(clip.end_time)}
                </p>
              </div>
            </div>
          ))}

            {/* Add from pool button */}
            {clipPool.length > 0 && (
              <button
                onClick={() => setShowPool(!showPool)}
                className="flex-shrink-0 w-44 bg-[#141414] rounded-xl border border-dashed border-white/10 hover:border-accent/50 flex flex-col items-center justify-center text-gray-500 hover:text-accent transition-all duration-200"
              >
                <span className="text-2xl mb-1">+</span>
                <span className="text-xs">{clipPool.length} more clips</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Clip Pool (unused clips) */}
      {showPool && clipPool.length > 0 && (
        <div className="flex-shrink-0">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white">
              Available Clips ({clipPool.length})
            </h2>
            <button onClick={() => setShowPool(false)} className="text-xs text-gray-500 hover:text-white">
              Hide ✕
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3 pb-4">
            {clipPool.map((clip) => (
              <div
                key={clip.clip_id}
                className="bg-[#141414] rounded-xl border border-white/5 hover:border-accent/30 overflow-hidden group cursor-pointer transition-all duration-200 opacity-70 hover:opacity-100"
                onClick={() => addFromPool(clip.clip_id)}
              >
                <div className="aspect-video bg-[#1a1a1a] flex items-center justify-center relative">
                  {clip.thumbnail_path ? (
                    <img
                      src={api.getClipThumbnailUrl(id, clip.clip_id)}
                      alt={clip.description}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <span className="text-xl">🎬</span>
                  )}
                  <span className="absolute bottom-1 right-1 text-[10px] bg-black/70 text-white px-1.5 py-0.5 rounded">
                    {formatTime(clip.duration)}
                  </span>
                  <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <span className="text-accent text-lg font-bold">+ Add</span>
                  </div>
                </div>
                <div className="p-2">
                  <p className="text-[11px] text-gray-400 truncate">{clip.description || "—"}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
