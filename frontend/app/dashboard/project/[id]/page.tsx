"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import { api, Project, EditDecision, TextOverlay } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { EditSummaryCard } from "@/components/EditSummaryCard";
import {
  ArrowLeft,
  ArrowRight,
  X,
  Save,
  Download,
  Clapperboard,
  Settings,
  MessageSquare,
  Undo2,
  Redo2,
  Lightbulb,
  Film,
  Sparkles,
  Plus,
  Loader2,
  Smartphone,
  Square,
  Monitor,
  ArrowUpLeft,
  ArrowUp,
  ArrowDown,
  Circle,
  Bot,
  XCircle,
  Play,
  Check,
  AlertTriangle
} from "lucide-react";

const STEPS = [
  { key: "analyzing", label: "Extracting Frames" },
  { key: "selecting", label: "Detecting Actions" },
  { key: "stitching", label: "Rendering" },
  { key: "completed", label: "Ready" },
];

const statusColor: Record<string, string> = {
  created: "bg-gray-500",
  uploading: "bg-blue-500",
  processing: "bg-yellow-500",
  analyzing: "bg-yellow-500",
  selecting: "bg-yellow-500",
  review: "bg-blue-500",
  stitching: "bg-yellow-500",
  completed: "bg-green-500",
  error: "bg-red-500",
};

interface ConversationMessage {
  id: string;
  type: "user" | "system" | "undo" | "redo" | "loading";
  text: string;
  timestamp: number;
  version?: number;
  undone?: boolean;
}

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

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [decisions, setDecisions] = useState<EditDecision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [regenerating, setRegenerating] = useState(false);

  // Tab state
  const [activeTab, setActiveTab] = useState<"ai" | "manual">("ai");

  // Conversational editing state
  const [instruction, setInstruction] = useState("");
  const [refining, setRefining] = useState(false);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const conversationEndRef = useRef<HTMLDivElement>(null);

  // Proxy preview state
  const [proxyVideoUrl, setProxyVideoUrl] = useState<string | null>(null);
  const [hdRendering, setHdRendering] = useState(false);
  const [videoKey, setVideoKey] = useState(0);

  // Text overlay state
  const [overlays, setOverlays] = useState<TextOverlay[]>([]);
  const [overlayModalOpen, setOverlayModalOpen] = useState(false);
  const [editingOverlay, setEditingOverlay] = useState<TextOverlay | null>(null);
  const [editingOverlayIndex, setEditingOverlayIndex] = useState<number | null>(null);
  const [overlayText, setOverlayText] = useState("");
  const [overlayStartTime, setOverlayStartTime] = useState(0);
  const [overlayEndTime, setOverlayEndTime] = useState(5);
  const [overlayPosition, setOverlayPosition] = useState("bottom-center");
  const [overlayStyle, setOverlayStyle] = useState("bold-white");
  const [overlayFontSize, setOverlayFontSize] = useState(48);
  const [savingOverlays, setSavingOverlays] = useState(false);
  const [autoGenerating, setAutoGenerating] = useState(false);

  // Edit plan / AI intelligence state
  const [editPlan, setEditPlan] = useState<any>(null);
  const [editorNotes, setEditorNotes] = useState("");
  const [timelineClips, setTimelineClips] = useState<any[]>([]);

  // Manual arrange state
  const [manualClips, setManualClips] = useState<Clip[]>([]);
  const [clipPool, setClipPool] = useState<Clip[]>([]);
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);
  const [savingManual, setSavingManual] = useState(false);
  const [renderingManual, setRenderingManual] = useState(false);
  const [totalDuration, setTotalDuration] = useState(0);
  const [targetDuration, setTargetDuration] = useState(60);

  const wsRef = useRef<WebSocket | null>(null);
  const { toast } = useToast();

  const isProcessing = (s: string) =>
    ["processing", "analyzing", "selecting", "stitching", "uploading"].includes(s);

  const fetchProject = useCallback(async () => {
    try {
      const p = await api.getProject(id);
      setProject(p);
      if (p.status === "completed") {
        const d = await api.getDecisions(id);
        setDecisions(d);
      }
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [id]);

  // WebSocket for live updates
  useEffect(() => {
    if (!id) return;
    const ws = api.connectWS(id, (msg) => {
      setProject((prev) =>
        prev
          ? { ...prev, status: msg.status as Project["status"], progress: msg.progress, current_step: msg.current_step }
          : prev
      );
      if (msg.status === "completed") {
        toast("success", "Video generation complete! 🎬");
        fetchProject();
        setRefining(false);
        setRenderingManual(false);
        if (hdRendering) {
          setHdRendering(false);
          setProxyVideoUrl(null);
          setVideoKey((k) => k + 1);
        }
      } else if (msg.status === "error") {
        toast("error", "Processing failed");
        fetchProject();
        setRefining(false);
        setRenderingManual(false);
      }
    });
    wsRef.current = ws;
    return () => ws.close();
  }, [id, fetchProject, toast, hdRendering]);

  useEffect(() => {
    fetchProject();
  }, [fetchProject]);

  // Load text overlays
  useEffect(() => {
    if (!id || project?.status !== "completed") return;

    async function loadOverlays() {
      try {
        const result = await api.getOverlays(id);
        setOverlays(result.overlays);
      } catch (err) {
        console.error("Failed to load overlays:", err);
      }
    }

    loadOverlays();
  }, [id, project?.status]);

  // Load edit plan for AI intelligence data
  useEffect(() => {
    if (!id || project?.status !== "completed") return;

    async function loadEditPlan() {
      try {
        const plan = await api.getEditPlan(id);
        setEditPlan(plan);
        setEditorNotes(plan.editor_notes || "");
        setTimelineClips(plan.timeline?.clips || []);

        // Load manual arrange data
        const timelineClips = (plan.timeline?.clips || []).sort(
          (a: Clip, b: Clip) => a.order - b.order
        );
        setManualClips(timelineClips);
        setClipPool(plan.clip_pool || []);
        setTargetDuration(plan.timeline?.target_duration || 60);
        setTotalDuration(plan.timeline?.total_effective_duration || 0);
      } catch (err) {
        console.error("Failed to load edit plan:", err);
      }
    }

    loadEditPlan();
  }, [id, project?.status]);

  // Recalculate total duration when manual clips change
  useEffect(() => {
    const total = manualClips
      .filter((c) => c.status === "included")
      .reduce((sum, c) => sum + c.effective_duration, 0);
    setTotalDuration(total);
  }, [manualClips]);

  // Load conversation history
  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    async function loadConversation() {
      try {
        const data = await api.getConversation(id);
        if (cancelled) return;

        const messages: ConversationMessage[] = data.conversation
          .filter((m) => !m.undone)
          .map((m) => ({
            id: m.id,
            type: m.role === "user" ? "user" as const : "system" as const,
            text: m.text,
            timestamp: new Date(m.timestamp).getTime(),
            version: m.version,
          }));

        setConversation(messages);
      } catch (err) {
        console.error("Failed to load conversation:", err);
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }

    loadConversation();
    return () => { cancelled = true; };
  }, [id]);

  // Auto-scroll conversation
  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation]);

  const handleRegenerate = async () => {
    if (!project) return;
    setRegenerating(true);
    try {
      await api.startProcessing(project.id, project.output_duration);
      setProject((p) => p ? { ...p, status: "processing", progress: 0 } : p);
      toast("info", "Regeneration started");
    } catch {
      toast("error", "Failed to start regeneration");
    } finally {
      setRegenerating(false);
    }
  };

  const handleDownload = () => {
    window.open(api.getOutputUrl(id), "_blank");
  };

  const handleRefine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!instruction.trim() || refining) return;

    const userMsg: ConversationMessage = {
      id: `user-${Date.now()}`,
      type: "user",
      text: instruction.trim(),
      timestamp: Date.now(),
    };

    const loadingMsg: ConversationMessage = {
      id: "loading",
      type: "loading",
      text: "",
      timestamp: Date.now(),
    };

    setConversation((prev) => [...prev, userMsg, loadingMsg]);
    setInstruction("");
    setRefining(true);

    try {
      const result = await api.refineEditPlan(id, userMsg.text);

      setConversation((prev) => prev.filter((m) => m.id !== "loading"));

      if (result.proxy_preview_url) {
        const proxyUrl = `${api.getVideoUrl("outputs/" + result.proxy_preview_url.split("/outputs/")[1])}`;
        setProxyVideoUrl(proxyUrl);
        setVideoKey((k) => k + 1);
        setHdRendering(result.hd_rendering || false);

        if (result.conversation_messages) {
          const newMsgs: ConversationMessage[] = result.conversation_messages
            .filter((m: any) => m.role === "assistant")
            .map((m: any) => ({
              id: m.id,
              type: "system" as const,
              text: `✓ ${m.text}${result.hd_rendering ? " (HD rendering...)" : ""}`,
              timestamp: new Date(m.timestamp).getTime(),
              version: m.version,
            }));
          setConversation((prev) => [...prev, ...newMsgs]);
        }

        toast("success", result.changes_summary || "Edit applied!");
      }

      setTimeout(() => {
        fetchProject();
      }, 1000);
      setRefining(false);

    } catch (e: unknown) {
      setConversation((prev) => prev.filter((m) => m.id !== "loading"));
      const errorMsg: ConversationMessage = {
        id: `err-${Date.now()}`,
        type: "system",
        text: `✗ ${e instanceof Error ? e.message : "Failed to refine edit"}`,
        timestamp: Date.now(),
      };
      setConversation((prev) => [...prev, errorMsg]);
      toast("error", "Edit failed");
      setRefining(false);
    }
  };

  const handleUndo = async () => {
    try {
      const result = await api.undoEdit(id);
      if (result.proxy_preview_url) {
        const proxyUrl = `${api.getVideoUrl("outputs/" + result.proxy_preview_url.split("/outputs/")[1])}`;
        setProxyVideoUrl(proxyUrl);
        setVideoKey((k) => k + 1);
      }

      if (result.undone_version) {
        setConversation((prev) => {
          const updated = prev.map((m) =>
            m.version === result.undone_version ? { ...m, undone: true } : m
          );
          const undoMsg: ConversationMessage = {
            id: `undo-${Date.now()}`,
            type: "undo",
            text: `Reverted to version ${result.version}`,
            timestamp: Date.now(),
            version: result.version,
          };
          return [...updated, undoMsg];
        });
      }

      toast("success", "Undone to previous version");
      fetchProject();
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Cannot undo");
    }
  };

  const handleRedo = async () => {
    try {
      const result = await api.redoEdit(id);
      if (result.proxy_preview_url) {
        const proxyUrl = `${api.getVideoUrl("outputs/" + result.proxy_preview_url.split("/outputs/")[1])}`;
        setProxyVideoUrl(proxyUrl);
        setVideoKey((k) => k + 1);
      }

      if (result.redone_version) {
        setConversation((prev) => {
          const updated = prev.map((m) =>
            m.version === result.redone_version ? { ...m, undone: false } : m
          );
          const redoMsg: ConversationMessage = {
            id: `redo-${Date.now()}`,
            type: "redo",
            text: `Restored to version ${result.redone_version}`,
            timestamp: Date.now(),
            version: result.redone_version,
          };
          return [...updated, redoMsg];
        });
      }

      toast("success", "Redone to next version");
      fetchProject();
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Cannot redo");
    }
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  // Get clip tag based on action_type or description
  const getClipTag = (clip: any): { icon: string; label: string; color: string } | null => {
    const actionType = clip.action_type || "";
    const description = (clip.description || "").toLowerCase();
    const reason = (clip.reason || "").toLowerCase();

    if (actionType === "ingredient_add" || description.includes("prep") || description.includes("chop") || description.includes("dice")) {
      return { icon: "🔪", label: "Prep", color: "bg-blue-500/20 text-blue-400 border-blue-500/30" };
    }
    if (actionType === "cooking" || description.includes("cook") || description.includes("fry") || description.includes("sizzl")) {
      return { icon: "🍳", label: "Cook", color: "bg-orange-500/20 text-orange-400 border-orange-500/30" };
    }
    if (actionType === "plating" || description.includes("plat") || description.includes("final") || description.includes("reveal")) {
      return { icon: "🎬", label: "Reveal", color: "bg-purple-500/20 text-purple-400 border-purple-500/30" };
    }
    if (actionType === "mixing" || description.includes("mix") || description.includes("stir") || description.includes("whisk")) {
      return { icon: "🥄", label: "Mix", color: "bg-green-500/20 text-green-400 border-green-500/30" };
    }

    if (description.includes("hero") || description.includes("money shot") || description.includes("cheese pull") ||
        description.includes("chocolate ooze") || description.includes("drizzle") || reason.includes("key moment")) {
      return { icon: "✨", label: "Hero", color: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" };
    }

    if (clip.shows_action_moment || description.includes("action") || description.includes("flip") || description.includes("pour")) {
      return { icon: "⚡", label: "Action", color: "bg-red-500/20 text-red-400 border-red-500/30" };
    }

    if (description.includes("beauty") || description.includes("close-up") || description.includes("close up") || (clip.visual_quality && clip.visual_quality >= 8)) {
      return { icon: "📸", label: "Beauty", color: "bg-pink-500/20 text-pink-400 border-pink-500/30" };
    }

    return null;
  };

  // Text overlay functions
  const openOverlayModal = (overlay?: TextOverlay, index?: number) => {
    if (overlay && index !== undefined) {
      setEditingOverlay(overlay);
      setEditingOverlayIndex(index);
      setOverlayText(overlay.text);
      setOverlayStartTime(overlay.start_time);
      setOverlayEndTime(overlay.end_time);
      setOverlayPosition(overlay.position);
      setOverlayStyle(overlay.style);
      setOverlayFontSize(overlay.font_size);
    } else {
      setEditingOverlay(null);
      setEditingOverlayIndex(null);
      setOverlayText("");
      setOverlayStartTime(0);
      setOverlayEndTime(5);
      setOverlayPosition("bottom-center");
      setOverlayStyle("bold-white");
      setOverlayFontSize(48);
    }
    setOverlayModalOpen(true);
  };

  const closeOverlayModal = () => {
    setOverlayModalOpen(false);
    setEditingOverlay(null);
    setEditingOverlayIndex(null);
  };

  const handleSaveOverlay = async () => {
    if (!overlayText.trim()) {
      toast("error", "Text is required");
      return;
    }

    if (overlayEndTime <= overlayStartTime) {
      toast("error", "End time must be greater than start time");
      return;
    }

    const newOverlay: TextOverlay = {
      text: overlayText.trim(),
      start_time: overlayStartTime,
      end_time: overlayEndTime,
      position: overlayPosition,
      style: overlayStyle,
      font_size: overlayFontSize,
    };

    let updatedOverlays: TextOverlay[];

    if (editingOverlayIndex !== null) {
      updatedOverlays = [...overlays];
      updatedOverlays[editingOverlayIndex] = newOverlay;
    } else {
      updatedOverlays = [...overlays, newOverlay];
    }

    setSavingOverlays(true);
    try {
      await api.updateOverlays(id, updatedOverlays);
      setOverlays(updatedOverlays);
      closeOverlayModal();
      toast("success", editingOverlayIndex !== null ? "Overlay updated" : "Overlay added");
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Failed to save overlay");
    } finally {
      setSavingOverlays(false);
    }
  };

  const handleDeleteOverlay = async (index: number) => {
    if (!confirm("Delete this text overlay?")) return;

    const updatedOverlays = overlays.filter((_, i) => i !== index);

    setSavingOverlays(true);
    try {
      await api.updateOverlays(id, updatedOverlays);
      setOverlays(updatedOverlays);
      toast("success", "Overlay deleted");
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Failed to delete overlay");
    } finally {
      setSavingOverlays(false);
    }
  };

  const handleAutoGenerateOverlays = async () => {
    if (!confirm("Auto-generate overlays from recipe steps? This will replace existing overlays.")) return;

    setAutoGenerating(true);
    try {
      const result = await api.autoGenerateOverlays(id, overlayStyle);
      setOverlays(result.overlays);
      toast("success", `Generated ${result.count} overlays from recipe steps`);
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Failed to auto-generate overlays");
    } finally {
      setAutoGenerating(false);
    }
  };

  // Manual arrange functions
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
    const newClips = [...manualClips];
    const [moved] = newClips.splice(dragIdx, 1);
    newClips.splice(idx, 0, moved);
    newClips.forEach((c, i) => (c.order = i));
    setManualClips(newClips);
    setDragIdx(null);
    setDragOverIdx(null);
  };

  const handleDragEnd = () => {
    setDragIdx(null);
    setDragOverIdx(null);
  };

  const removeClip = (clipId: string) => {
    const clip = manualClips.find((c) => c.clip_id === clipId);
    if (!clip) return;
    setManualClips((prev) => prev.filter((c) => c.clip_id !== clipId));
    setClipPool((prev) => [...prev, { ...clip, status: "excluded" as const }]);
    toast("info", `Removed "${clip.description.slice(0, 30)}..."`);
  };

  const addFromPool = (clipId: string) => {
    const clip = clipPool.find((c) => c.clip_id === clipId);
    if (!clip) return;
    const newClip: Clip = {
      ...clip,
      status: "included",
      added_by: "user",
      order: manualClips.length,
      speed_factor: clip.speed_factor || 1.0,
      effective_duration: clip.duration / (clip.speed_factor || 1.0),
    };
    setManualClips((prev) => [...prev, newClip]);
    setClipPool((prev) => prev.filter((c) => c.clip_id !== clipId));
    toast("success", `Added "${clip.description.slice(0, 30)}..."`);
  };

  const handleSaveManual = async () => {
    setSavingManual(true);
    try {
      await api.updateEditPlan(id, manualClips);
      toast("success", "Edit plan saved");
    } catch {
      toast("error", "Failed to save");
    } finally {
      setSavingManual(false);
    }
  };

  const handleRenderFinal = async () => {
    if (!confirm("Start rendering final video? This may take a few minutes.")) return;
    setRenderingManual(true);
    try {
      await api.updateEditPlan(id, manualClips);
      await api.confirmAndRender(id);
      toast("success", "Rendering started! 🎬");
      setActiveTab("ai"); // Switch to AI tab to see progress
    } catch (e: unknown) {
      toast("error", e instanceof Error ? e.message : "Failed to start render");
      setRenderingManual(false);
    }
  };

  const formatDate = (d: string) => {
    try {
      return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return d;
    }
  };

  const getStepIndex = () => {
    if (!project) return -1;
    const s = project.status;
    if (s === "processing") return 0;
    if (s === "analyzing") return 1;
    if (s === "selecting") return 2;
    if (s === "stitching") return 2;
    if (s === "completed") return 3;
    return -1;
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="animate-pulse space-y-6 w-full max-w-4xl px-8">
          <div className="h-8 bg-white/5 rounded w-48" />
          <div className="aspect-video bg-white/5 rounded-2xl" />
          <div className="h-20 bg-white/5 rounded-xl" />
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">{error || "Project not found"}</p>
          <Link href="/dashboard" className="text-sm text-accent hover:text-accent-hover inline-flex items-center gap-1.5"><ArrowLeft size={14} /> Back to Dashboard</Link>
        </div>
      </div>
    );
  }

  const stepIdx = getStepIndex();
  const durationPct = targetDuration > 0 ? Math.min((totalDuration / targetDuration) * 100, 150) : 0;
  const getDurationStatus = () => {
    if (totalDuration <= targetDuration + 5) {
      return { color: "bg-green-500", text: "text-green-400", Icon: Check };
    } else if (totalDuration <= targetDuration + 10) {
      return { color: "bg-yellow-500", text: "text-yellow-400", Icon: AlertTriangle };
    } else {
      return { color: "bg-red-500", text: "text-red-400", Icon: X };
    }
  };
  const durationStatus = getDurationStatus();

  return (
    <div className="h-screen flex flex-col bg-[#0a0a0a] overflow-hidden">
      {/* Fixed Header */}
      <header className="flex-shrink-0 border-b border-white/5 bg-[#0a0a0a] px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="text-gray-500 hover:text-white transition-all duration-200 inline-flex items-center gap-1.5"
              title="Back to Projects"
            >
              <ArrowLeft size={16} /> Projects
            </Link>
            <div className="h-6 w-px bg-white/10" />
            <div>
              <h1 className="text-lg font-bold text-white">{project.name}</h1>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>{formatDate(project.created_at)}</span>
                {decisions.length > 0 && (
                  <>
                    <span>•</span>
                    <span>{decisions.length} clips</span>
                  </>
                )}
                <span className={`text-white text-[10px] px-2 py-0.5 rounded-full font-medium ${statusColor[project.status]}`}>
                  {project.status}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {project.status === "completed" && (
              <>
                <button
                  onClick={handleDownload}
                  className="px-4 py-2 rounded-lg border border-white/10 text-sm text-gray-300 hover:text-white hover:bg-white/5 transition-all duration-200 inline-flex items-center gap-2"
                >
                  <Save size={16} /> Save
                </button>
                <button
                  onClick={handleDownload}
                  className="bg-accent hover:bg-accent-hover text-white px-6 py-2 rounded-lg font-semibold text-sm transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20 inline-flex items-center gap-2"
                >
                  <Download size={16} /> Export
                </button>
              </>
            )}
            {isProcessing(project.status) && (
              <button
                onClick={handleRegenerate}
                disabled={regenerating}
                className="px-4 py-2 rounded-lg border border-white/10 text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-all duration-200 disabled:opacity-50"
              >
                {regenerating ? "..." : "↻ Regenerate"}
              </button>
            )}
          </div>
        </div>
      </header>

      {error && (
        <div className="flex-shrink-0 mx-6 mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-red-300 hover:text-white"><X size={16} /></button>
        </div>
      )}

      {/* Main Content Area - Split Panel */}
      {project.status === "completed" && project.output_path ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Split Panel Container */}
          <div className="flex-1 flex overflow-hidden">
            {/* Left Panel - Video Preview */}
            <div className="w-[55%] flex flex-col border-r border-white/5 bg-[#0a0a0a] p-6 overflow-y-auto">
              <div className="flex-shrink-0">
                {/* Video Player */}
                <div className="mx-auto mb-4 relative" style={{ maxWidth: "400px" }}>
                  {hdRendering && (
                    <div className="absolute top-3 right-3 bg-yellow-500/90 text-black text-xs px-3 py-1.5 rounded-full font-semibold z-10 flex items-center gap-1">
                      <Settings size={14} className="animate-spin" /> HD rendering...
                    </div>
                  )}

                  <video
                    key={`${videoKey}-${proxyVideoUrl || project.output_path}`}
                    src={proxyVideoUrl || api.getVideoUrl(project.output_path)}
                    controls
                    className="w-full rounded-xl border border-white/10 bg-black"
                    style={{ maxHeight: "60vh" }}
                  />
                </div>

                {/* Aspect Ratio Selector */}
                <div className="flex justify-center gap-2 mb-4">
                  {[
                    { value: "9:16", label: "9:16", Icon: Smartphone },
                    { value: "1:1", label: "1:1", Icon: Square },
                    { value: "16:9", label: "16:9", Icon: Monitor },
                  ].map((format) => {
                    const isCurrentFormat = project?.aspect_ratio === format.value;
                    return (
                      <button
                        key={format.value}
                        disabled
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 ${
                          isCurrentFormat
                            ? "bg-green-500/20 text-green-400 border border-green-500/30"
                            : "bg-white/5 text-gray-500 border border-white/10"
                        }`}
                        title={isCurrentFormat ? "Current format" : format.label}
                      >
                        <format.Icon size={14} />
                        <span>{format.label}</span>
                        {isCurrentFormat && <Check size={12} />}
                      </button>
                    );
                  })}
                </div>

                {/* Edit Summary Card */}
                {editorNotes && editPlan && (
                  <div className="mb-4">
                    <EditSummaryCard
                      editorNotes={editorNotes}
                      clipCount={timelineClips.length || decisions.length}
                      totalDuration={editPlan.timeline?.total_effective_duration || 0}
                      targetDuration={editPlan.timeline?.target_duration || project.output_duration || 60}
                      recipeDetails={project.recipe_details}
                      dishName={project.dish_name}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Right Panel - Tabbed Interface */}
            <div className="w-[45%] flex flex-col bg-[#0a0a0a]">
              {/* Tab Headers */}
              <div className="flex-shrink-0 border-b border-white/5 px-6">
                <div className="flex gap-1">
                  <button
                    onClick={() => setActiveTab("ai")}
                    className={`px-4 py-3 text-sm font-medium transition-all duration-200 border-b-2 ${
                      activeTab === "ai"
                        ? "border-accent text-white"
                        : "border-transparent text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    <span className="inline-flex items-center gap-2"><MessageSquare size={16} /> AI Chat</span>
                  </button>
                  <button
                    onClick={() => setActiveTab("manual")}
                    className={`px-4 py-3 text-sm font-medium transition-all duration-200 border-b-2 ${
                      activeTab === "manual"
                        ? "border-accent text-white"
                        : "border-transparent text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    <span className="inline-flex items-center gap-2"><Clapperboard size={16} /> Manual</span>
                  </button>
                </div>
              </div>

              {/* Tab Content */}
              <div className="flex-1 overflow-hidden">
                {activeTab === "ai" ? (
                  /* AI Chat Panel */
                  <div className="h-full flex flex-col p-6">
                    {/* Conversation History */}
                    <div className="flex-1 overflow-y-auto mb-4 pr-2 space-y-2">
                      {historyLoading ? (
                        <div className="animate-pulse space-y-3">
                          {[...Array(3)].map((_, i) => (
                            <div key={i} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
                              <div className={`rounded-lg h-8 ${i % 2 === 0 ? "bg-accent/10 w-40" : "bg-white/5 w-48"}`} />
                            </div>
                          ))}
                        </div>
                      ) : conversation.length === 0 ? (
                        <div className="text-center py-8">
                          <p className="text-sm text-gray-500 mb-2">Start a conversation with AI</p>
                          <p className="text-xs text-gray-600">Try: "Make it shorter" or "Remove blurry clips"</p>
                        </div>
                      ) : (
                        <>
                          {conversation.map((msg, idx) => {
                            if (msg.type === "undo" || msg.type === "redo") {
                              return (
                                <div key={msg.id || idx} className="flex justify-center py-1">
                                  <span className="text-xs text-gray-500 bg-white/5 px-3 py-1 rounded-full inline-flex items-center gap-1.5">
                                    {msg.type === "undo" ? <Undo2 size={12} /> : <Redo2 size={12} />} {msg.text}
                                  </span>
                                </div>
                              );
                            }

                            if (msg.type === "loading") {
                              return (
                                <div key="loading" className="flex justify-start">
                                  <div className="bg-white/5 px-4 py-2 rounded-lg text-sm text-gray-400 flex items-center gap-2">
                                    <span className="animate-pulse">●</span> Working on it…
                                  </div>
                                </div>
                              );
                            }

                            return (
                              <div
                                key={msg.id || idx}
                                className={`flex ${msg.type === "user" ? "justify-end" : "justify-start"} ${msg.undone ? "opacity-30" : ""}`}
                              >
                                <div
                                  className={`max-w-[80%] px-4 py-2 rounded-lg text-sm ${
                                    msg.type === "user"
                                      ? "bg-accent/20 text-white"
                                      : "bg-white/5 text-gray-300"
                                  } ${msg.undone ? "line-through" : ""}`}
                                >
                                  {msg.text}
                                </div>
                              </div>
                            );
                          })}
                          <div ref={conversationEndRef} />
                        </>
                      )}
                    </div>

                    {/* Prompt Chips */}
                    {!historyLoading && (
                      <div className="flex-shrink-0 mb-3">
                        <p className="text-xs text-gray-500 mb-2 inline-flex items-center gap-1.5"><Lightbulb size={14} /> Try these:</p>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { text: "Make it 30 seconds", condition: (editPlan?.timeline?.total_effective_duration || 0) > 35 },
                            { text: "Remove blurry clips", condition: true },
                            { text: "Speed up prep section", condition: editorNotes.toLowerCase().includes("prep") },
                            { text: "Focus on the plating", condition: editorNotes.toLowerCase().includes("plat") },
                          ]
                            .filter(chip => chip.condition)
                            .slice(0, 4)
                            .map((chip, idx) => (
                              <button
                                key={idx}
                                onClick={() => {
                                  setInstruction(chip.text);
                                  setTimeout(() => {
                                    const form = document.getElementById('chat-form') as HTMLFormElement;
                                    if (form) form.requestSubmit();
                                  }, 100);
                                }}
                                disabled={refining}
                                className="px-3 py-1.5 bg-white/5 hover:bg-accent/20 border border-white/10 hover:border-accent/50 text-gray-400 hover:text-white rounded-lg text-xs transition-all duration-200 disabled:opacity-50"
                              >
                                {chip.text}
                              </button>
                            ))}
                        </div>
                      </div>
                    )}

                    {/* Chat Input */}
                    <div className="flex-shrink-0">
                      {/* Undo/Redo Toolbar */}
                      <div className="flex gap-2 mb-3 items-center">
                        <button
                          onClick={handleUndo}
                          disabled={refining}
                          className="px-3 py-2 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-base transition-all duration-200 disabled:opacity-50"
                          title="Undo last edit"
                        >
                          <Undo2 size={18} />
                        </button>
                        <button
                          onClick={handleRedo}
                          disabled={refining}
                          className="px-3 py-2 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-base transition-all duration-200 disabled:opacity-50"
                          title="Redo next edit"
                        >
                          <Redo2 size={18} />
                        </button>
                        <span className="text-xs text-gray-500">Edit history</span>
                      </div>

                      <form id="chat-form" onSubmit={handleRefine} className="flex gap-2">
                        <input
                          type="text"
                          value={instruction}
                          onChange={(e) => setInstruction(e.target.value)}
                          placeholder="Tell AI what to change..."
                          disabled={refining}
                          className="flex-1 px-4 py-3 bg-[#111] border border-white/10 rounded-lg text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-accent/50 disabled:opacity-50"
                        />
                        <button
                          type="submit"
                          disabled={refining || !instruction.trim()}
                          className="px-6 py-3 bg-accent hover:bg-accent-hover text-white rounded-lg font-medium text-sm transition-all duration-200 disabled:opacity-50"
                        >
                          {refining ? "..." : "Send"}
                        </button>
                      </form>
                    </div>
                  </div>
                ) : (
                  /* Manual Arrange Panel */
                  <div className="h-full flex flex-col p-6">
                    {/* Duration Progress */}
                    <div className="flex-shrink-0 mb-4">
                      <div className="flex items-center justify-between text-xs text-gray-400 mb-2">
                        <span>Duration</span>
                        <span className={`${durationStatus.text} flex items-center gap-1.5`}>
                          <durationStatus.Icon size={14} /> {formatTime(totalDuration)} / {formatTime(targetDuration)}
                        </span>
                      </div>
                      <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${durationStatus.color} rounded-full transition-all duration-300`}
                          style={{ width: `${Math.min(durationPct, 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* AI Notes */}
                    {editorNotes && (
                      <div className="flex-shrink-0 bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-3 mb-4">
                        <div className="flex items-start gap-2">
                          <Bot size={18} className="text-yellow-400 flex-shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-semibold text-yellow-400 mb-1">AI Notes</p>
                            <p className="text-xs text-gray-400 line-clamp-3">{editorNotes}</p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Clip Grid - Scrollable */}
                    <div className="flex-1 overflow-y-auto pr-2">
                      <div className="grid grid-cols-2 gap-3 mb-4">
                        {manualClips.map((clip, idx) => {
                          const clipTag = getClipTag(clip);
                          return (
                            <div
                              key={clip.clip_id}
                              draggable
                              onDragStart={() => handleDragStart(idx)}
                              onDragOver={(e) => handleDragOver(e, idx)}
                              onDrop={() => handleDrop(idx)}
                              onDragEnd={handleDragEnd}
                              className={`bg-surface rounded-lg border overflow-hidden cursor-move hover:border-accent/30 transition-all duration-200 ${
                                dragOverIdx === idx ? "border-accent" : "border-white/5"
                              }`}
                            >
                              <div className="aspect-video bg-[#141414] flex items-center justify-center relative">
                                <img
                                  src={api.getClipThumbnailUrl(id, clip.clip_id)}
                                  alt={clip.description}
                                  className="w-full h-full object-cover"
                                  loading="lazy"
                                  onError={(e) => {
                                    e.currentTarget.style.display = 'none';
                                    const fallback = e.currentTarget.nextElementSibling;
                                    if (fallback) (fallback as HTMLElement).style.display = 'flex';
                                  }}
                                />
                                <span className="absolute hidden items-center justify-center w-full h-full text-gray-600"><Film size={24} /></span>

                                {clipTag && (
                                  <div className={`absolute top-1 left-1 px-1.5 py-0.5 rounded-full text-[9px] font-semibold border flex items-center gap-1 ${clipTag.color}`}>
                                    <span>{clipTag.icon}</span>
                                  </div>
                                )}

                                {/* Remove button */}
                                <button
                                  onClick={() => removeClip(clip.clip_id)}
                                  className="absolute top-1 right-1 w-6 h-6 bg-black/70 hover:bg-red-500 text-white rounded-full flex items-center justify-center text-xs transition-all duration-200"
                                  title="Remove clip"
                                >
                                  <X size={14} />
                                </button>
                              </div>
                              <div className="p-2">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-[10px] text-accent font-semibold">#{idx + 1}</span>
                                  <span className="text-[10px] text-gray-500">
                                    {formatTime(clip.start_time)} - {formatTime(clip.end_time)}
                                  </span>
                                </div>
                                <p className="text-[10px] text-gray-400 truncate">{clip.description}</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Clip Pool */}
                      {clipPool.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-white/5">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="text-xs font-semibold text-gray-400">Excluded Clips ({clipPool.length})</h4>
                            <button
                              onClick={() => setManualClips((prev) => [...prev, ...clipPool.map((c, i) => ({ ...c, status: "included" as const, order: prev.length + i }))])}
                              className="text-xs text-accent hover:text-accent-hover"
                            >
                              + Add All
                            </button>
                          </div>
                          <div className="grid grid-cols-2 gap-2">
                            {clipPool.map((clip) => (
                              <button
                                key={clip.clip_id}
                                onClick={() => addFromPool(clip.clip_id)}
                                className="bg-white/5 hover:bg-white/10 rounded-lg p-2 text-left transition-all duration-200 border border-white/5 hover:border-accent/30"
                              >
                                <p className="text-[10px] text-gray-400 truncate">{clip.description}</p>
                                <p className="text-[9px] text-gray-600 mt-1">{formatTime(clip.duration)}s</p>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex-shrink-0 flex gap-2 pt-4 border-t border-white/5">
                      <button
                        onClick={handleSaveManual}
                        disabled={savingManual}
                        className="flex-1 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50"
                      >
                        {savingManual ? (
                          <span className="inline-flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Saving...</span>
                        ) : (
                          <span className="inline-flex items-center gap-2"><Save size={16} /> Save</span>
                        )}
                      </button>
                      <button
                        onClick={handleRenderFinal}
                        disabled={renderingManual || manualClips.length === 0}
                        className="flex-1 bg-accent hover:bg-accent-hover text-white px-4 py-2.5 rounded-lg font-semibold text-sm transition-all duration-200 disabled:opacity-50"
                      >
                        {renderingManual ? (
                          <span className="inline-flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Starting...</span>
                        ) : (
                          <span className="inline-flex items-center gap-2"><Clapperboard size={16} /> Render</span>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Bottom Strip - Clip Timeline & Text Overlays */}
          <div className="flex-shrink-0 border-t border-white/5 bg-[#0a0a0a] p-6">
            {/* Clip Timeline */}
            {decisions.length > 0 && (
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-white mb-3">Clip Timeline</h3>
                <div className="relative">
                  <button
                    onClick={() => {
                      const container = document.getElementById('bottom-clip-timeline');
                      if (container) container.scrollBy({ left: -200, behavior: 'smooth' });
                    }}
                    className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-black/80 hover:bg-black/90 text-white rounded-full w-7 h-7 flex items-center justify-center transition-all duration-200 shadow-lg text-sm"
                  >
                    <ArrowLeft size={16} />
                  </button>

                  <button
                    onClick={() => {
                      const container = document.getElementById('bottom-clip-timeline');
                      if (container) container.scrollBy({ left: 200, behavior: 'smooth' });
                    }}
                    className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-black/80 hover:bg-black/90 text-white rounded-full w-7 h-7 flex items-center justify-center transition-all duration-200 shadow-lg text-sm"
                  >
                    <ArrowRight size={16} />
                  </button>

                  <div id="bottom-clip-timeline" className="flex gap-2 overflow-x-auto pb-2 px-8 scroll-smooth">
                    {(timelineClips.length > 0 ? timelineClips : decisions)
                      .sort((a: any, b: any) => (a.order ?? a.sequence_order ?? 0) - (b.order ?? b.sequence_order ?? 0))
                      .map((clip: any, idx: number) => {
                        const clipId = clip.clip_id || clip.id;
                        const clipTag = getClipTag(clip);

                        return (
                          <div
                            key={clipId || `clip-${idx}`}
                            className="flex-shrink-0 w-32 bg-surface rounded-lg border border-white/5 hover:border-accent/30 transition-all duration-200 overflow-hidden group cursor-pointer"
                          >
                            <div className="aspect-video bg-[#141414] flex items-center justify-center relative">
                              {clipId ? (
                                <img
                                  src={api.getClipThumbnailUrl(id, clipId)}
                                  alt={clip.reason || clip.description || "Clip"}
                                  className="w-full h-full object-cover"
                                  loading="lazy"
                                  onError={(e) => {
                                    e.currentTarget.style.display = 'none';
                                    const fallback = e.currentTarget.nextElementSibling;
                                    if (fallback) (fallback as HTMLElement).style.display = 'block';
                                  }}
                                />
                              ) : null}
                              <span className="absolute text-gray-600" style={{ display: clipId ? 'none' : 'block' }}><Film size={20} /></span>

                              {clipTag && (
                                <div className={`absolute top-1 left-1 px-1.5 py-0.5 rounded-full text-[9px] font-semibold border flex items-center gap-0.5 ${clipTag.color}`}>
                                  <span className="text-[10px]">{clipTag.icon}</span>
                                </div>
                              )}
                            </div>
                            <div className="p-2">
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] text-accent font-semibold">#{(clip.order ?? clip.sequence_order ?? idx) + 1}</span>
                                <span className="text-[9px] text-gray-600">{formatTime((clip.end_time - clip.start_time) / (clip.speed_factor || 1))}</span>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </div>
              </div>
            )}

            {/* Text Overlays */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <h3 className="text-sm font-semibold text-white">Text Overlays ({overlays.length})</h3>
                {overlays.slice(0, 3).map((overlay, idx) => (
                  <span key={idx} className="text-xs text-gray-500 bg-white/5 px-2 py-1 rounded">
                    {overlay.text.slice(0, 20)}...
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAutoGenerateOverlays}
                  disabled={autoGenerating || savingOverlays}
                  className="px-3 py-1.5 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-xs font-medium transition-all duration-200 disabled:opacity-50"
                >
                  <span className="inline-flex items-center gap-1.5">
                    {autoGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />} Auto-generate
                  </span>
                </button>
                <button
                  onClick={() => openOverlayModal()}
                  disabled={savingOverlays}
                  className="px-3 py-1.5 bg-accent hover:bg-accent-hover text-white rounded-lg text-xs font-medium transition-all duration-200 disabled:opacity-50"
                >
                  + Add Text
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Processing State - Fullscreen */
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="w-full max-w-md">
            {project.status === "error" ? (
              <div className="text-center">
                <div className="mb-4 flex justify-center text-red-400">
                  <XCircle size={64} />
                </div>
                <p className="text-red-400 text-sm">{project.current_step || "Processing failed"}</p>
              </div>
            ) : isProcessing(project.status) ? (
              <div className="text-center">
                <div className="mb-4 flex justify-center text-gray-600"><Settings size={64} className="animate-spin" /></div>
                <p className="text-white font-medium mb-2">
                  {project.current_step || "Processing..."}
                </p>
                <p className="text-sm text-gray-500 mb-4">{Math.round(project.progress || 0)}%</p>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden mb-6">
                  <div
                    className="h-full bg-accent rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(project.progress || 0, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs px-4">
                  {STEPS.map((step, i) => (
                    <div key={step.key} className={`flex flex-col items-center gap-1 ${i <= stepIdx ? "text-accent" : "text-gray-600"}`}>
                      <div className={`w-2.5 h-2.5 rounded-full border-2 ${i < stepIdx ? "bg-accent border-accent" : i === stepIdx ? "border-accent" : "border-gray-600"}`} />
                      <span className="text-[9px]">{step.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center">
                <div className="mb-4 flex justify-center text-gray-600">
                  <Play size={64} />
                </div>
                <p className="text-sm text-gray-500">Ready to process</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Text Overlay Editor Modal */}
      {overlayModalOpen && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={closeOverlayModal}
        >
          <div
            className="bg-[#111] border border-white/10 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-[#111] border-b border-white/10 px-6 py-4 flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">
                {editingOverlay ? "Edit Text Overlay" : "Add Text Overlay"}
              </h2>
              <button
                onClick={closeOverlayModal}
                disabled={savingOverlays}
                className="text-gray-500 hover:text-white transition-all duration-200 disabled:opacity-50"
              >
                <X size={20} />
              </button>
            </div>

            <div className="p-6 space-y-6">
              <div>
                <label className="text-sm text-gray-400 block mb-2">Text</label>
                <textarea
                  value={overlayText}
                  onChange={(e) => setOverlayText(e.target.value)}
                  placeholder="Enter text to display..."
                  rows={3}
                  disabled={savingOverlays}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-all duration-200 disabled:opacity-50 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-2">Start Time (seconds)</label>
                  <input
                    type="number"
                    value={overlayStartTime}
                    onChange={(e) => setOverlayStartTime(parseFloat(e.target.value) || 0)}
                    min={0}
                    step={0.1}
                    disabled={savingOverlays}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-all duration-200 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-400 block mb-2">End Time (seconds)</label>
                  <input
                    type="number"
                    value={overlayEndTime}
                    onChange={(e) => setOverlayEndTime(parseFloat(e.target.value) || 0)}
                    min={0}
                    step={0.1}
                    disabled={savingOverlays}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-all duration-200 disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm text-gray-400 block mb-2">Style</label>
                <div className="flex gap-2">
                  {[
                    { value: "bold-white", label: "Bold White" },
                    { value: "subtitle-bar", label: "Subtitle Bar" },
                    { value: "minimal", label: "Minimal" },
                  ].map((style) => (
                    <button
                      key={style.value}
                      onClick={() => setOverlayStyle(style.value)}
                      disabled={savingOverlays}
                      className={`flex-1 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                        overlayStyle === style.value
                          ? "bg-accent text-white"
                          : "bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white"
                      } disabled:opacity-50`}
                    >
                      {style.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm text-gray-400 block mb-2">Position</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { value: "top-left", label: "Top Left", Icon: ArrowUpLeft },
                    { value: "top-center", label: "Top Center", Icon: ArrowUp },
                    { value: "bottom-center", label: "Bottom Center", Icon: ArrowDown },
                    { value: "center", label: "Center", Icon: Circle },
                  ].map((pos) => (
                    <button
                      key={pos.value}
                      onClick={() => setOverlayPosition(pos.value)}
                      disabled={savingOverlays}
                      className={`px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2 ${
                        overlayPosition === pos.value
                          ? "bg-accent text-white"
                          : "bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white"
                      } disabled:opacity-50`}
                    >
                      <pos.Icon size={16} />
                      <span>{pos.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm text-gray-400 block mb-2">
                  Font Size: {overlayFontSize}px
                </label>
                <input
                  type="range"
                  min="24"
                  max="72"
                  step="4"
                  value={overlayFontSize}
                  onChange={(e) => setOverlayFontSize(parseInt(e.target.value))}
                  disabled={savingOverlays}
                  className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-accent disabled:opacity-50"
                />
                <div className="flex justify-between text-xs text-gray-600 mt-1">
                  <span>24px</span>
                  <span>72px</span>
                </div>
              </div>

              <div className="flex items-center gap-3 pt-4 border-t border-white/10">
                <button
                  onClick={handleSaveOverlay}
                  disabled={savingOverlays || !overlayText.trim()}
                  className="bg-accent hover:bg-accent-hover text-white px-8 py-3 rounded-xl font-semibold text-sm transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20 disabled:opacity-50"
                >
                  {savingOverlays ? (
                    <span className="inline-flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Saving...</span>
                  ) : editingOverlay ? (
                    <span className="inline-flex items-center gap-2"><Save size={16} /> Update</span>
                  ) : (
                    <span className="inline-flex items-center gap-2"><Plus size={16} /> Add</span>
                  )}
                </button>
                <button
                  onClick={closeOverlayModal}
                  disabled={savingOverlays}
                  className="px-8 py-3 border border-white/10 hover:bg-white/5 text-gray-400 hover:text-white rounded-xl font-medium text-sm transition-all duration-200 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
