"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import { api, Project, EditDecision } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { EditSummaryCard } from "@/components/EditSummaryCard";

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

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [decisions, setDecisions] = useState<EditDecision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [regenerating, setRegenerating] = useState(false);
  
  // Conversational editing state
  const [instruction, setInstruction] = useState("");
  const [refining, setRefining] = useState(false);
  const [conversation, setConversation] = useState<ConversationMessage[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  
  // Proxy preview state
  const [proxyVideoUrl, setProxyVideoUrl] = useState<string | null>(null);
  const [hdRendering, setHdRendering] = useState(false);
  const [videoKey, setVideoKey] = useState(0); // Force video reload
  const [selectedExportFormat, setSelectedExportFormat] = useState<string | null>(null); // For re-export
  
  // Text overlay state
  const [overlays, setOverlays] = useState<api.TextOverlay[]>([]);
  const [overlayModalOpen, setOverlayModalOpen] = useState(false);
  const [editingOverlay, setEditingOverlay] = useState<api.TextOverlay | null>(null);
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
  const [showAIAnalysis, setShowAIAnalysis] = useState(true);
  
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
        // HD render complete - swap from proxy to HD
        if (hdRendering) {
          setHdRendering(false);
          setProxyVideoUrl(null);
          setVideoKey((k) => k + 1);
        }
      } else if (msg.status === "error") {
        toast("error", "Processing failed");
        fetchProject();
        setRefining(false);
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
      } catch (err) {
        console.error("Failed to load edit plan:", err);
      }
    }
    
    loadEditPlan();
  }, [id, project?.status]);

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
      
      // Remove loading message
      setConversation((prev) => prev.filter((m) => m.id !== "loading"));
      
      if (result.proxy_preview_url) {
        const proxyUrl = `${api.getVideoUrl("outputs/" + result.proxy_preview_url.split("/outputs/")[1])}`;
        setProxyVideoUrl(proxyUrl);
        setVideoKey((k) => k + 1);
        setHdRendering(result.hd_rendering || false);
        
        // Use conversation messages from backend (source of truth)
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
      // Remove loading, add error
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
      
      // Grey out messages from undone version
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
      
      // Un-grey messages from redone version
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
    
    // Check action_type first
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
    
    // Check for hero/key moments in description or reason
    if (description.includes("hero") || description.includes("money shot") || description.includes("cheese pull") || 
        description.includes("chocolate ooze") || description.includes("drizzle") || reason.includes("key moment")) {
      return { icon: "✨", label: "Hero", color: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" };
    }
    
    // Check for action moments
    if (clip.shows_action_moment || description.includes("action") || description.includes("flip") || description.includes("pour")) {
      return { icon: "⚡", label: "Action", color: "bg-red-500/20 text-red-400 border-red-500/30" };
    }
    
    // Check for beauty shots
    if (description.includes("beauty") || description.includes("close-up") || description.includes("close up") || (clip.visual_quality && clip.visual_quality >= 8)) {
      return { icon: "📸", label: "Beauty", color: "bg-pink-500/20 text-pink-400 border-pink-500/30" };
    }
    
    return null;
  };
  
  // Text overlay functions
  const openOverlayModal = (overlay?: api.TextOverlay, index?: number) => {
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
    
    const newOverlay: api.TextOverlay = {
      text: overlayText.trim(),
      start_time: overlayStartTime,
      end_time: overlayEndTime,
      position: overlayPosition,
      style: overlayStyle,
      font_size: overlayFontSize,
    };
    
    let updatedOverlays: api.TextOverlay[];
    
    if (editingOverlayIndex !== null) {
      // Update existing overlay
      updatedOverlays = [...overlays];
      updatedOverlays[editingOverlayIndex] = newOverlay;
    } else {
      // Add new overlay
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
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-white/5 rounded w-48" />
        <div className="aspect-video bg-white/5 rounded-2xl" />
        <div className="h-20 bg-white/5 rounded-xl" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-20">
        <p className="text-red-400">{error || "Project not found"}</p>
        <Link href="/dashboard" className="text-sm text-accent mt-4 inline-block">← Back to Dashboard</Link>
      </div>
    );
  }

  const stepIdx = getStepIndex();

  return (
    <div>
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
          <button onClick={() => setError("")} className="ml-2 text-red-300 hover:text-white">✕</button>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">{project.name}</h1>
          <div className="flex items-center gap-4 mt-1 text-xs text-gray-500">
            <span>{formatDate(project.created_at)}</span>
            {decisions.length > 0 && (
              <>
                <span>•</span>
                <span>{decisions.length} clips</span>
              </>
            )}
            <span className={`text-white text-[10px] px-2 py-0.5 rounded-full font-medium ml-1 ${statusColor[project.status]}`}>
              {project.status}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleRegenerate}
            disabled={regenerating || isProcessing(project.status)}
            className="px-4 py-2.5 rounded-lg border border-white/10 text-sm text-gray-400 hover:text-white hover:bg-white/5 transition-all duration-200 disabled:opacity-50"
          >
            {regenerating ? "..." : "↻ Regenerate"}
          </button>
          <Link href="/dashboard" className="px-4 py-2.5 rounded-lg text-sm text-gray-500 hover:text-white transition-all duration-200">
            ← Back
          </Link>
        </div>
      </div>

      {/* Video Player / Status */}
      {project.status === "completed" && project.output_path ? (
        <div className="mb-6">
          <div className="mx-auto mb-6 relative" style={{ maxWidth: "350px" }}>
            {/* HD Rendering Badge */}
            {hdRendering && (
              <div className="absolute top-3 right-3 bg-yellow-500/90 text-black text-xs px-3 py-1.5 rounded-full font-semibold z-10 flex items-center gap-1">
                <span className="animate-pulse">⚙️</span> HD rendering...
              </div>
            )}
            
            <video
              key={`${videoKey}-${proxyVideoUrl || project.output_path}`}
              src={proxyVideoUrl || api.getVideoUrl(project.output_path)}
              controls
              autoPlay
              className="w-full rounded-2xl border border-white/5 bg-black"
              style={{ maxHeight: "55vh" }}
            />
          </div>

          {/* Edit Summary Card - Intelligence Layer */}
          {editorNotes && editPlan && (
            <EditSummaryCard
              editorNotes={editorNotes}
              clipCount={timelineClips.length || decisions.length}
              totalDuration={editPlan.timeline?.total_effective_duration || 0}
              targetDuration={editPlan.timeline?.target_duration || project.output_duration || 60}
              recipeDetails={project.recipe_details}
              dishName={project.dish_name}
            />
          )}

          {/* AI Analysis Section */}
          {editorNotes && (
            <div className="max-w-2xl mx-auto mb-6">
              <button
                onClick={() => setShowAIAnalysis(!showAIAnalysis)}
                className="w-full bg-yellow-500/5 border border-yellow-500/20 rounded-xl px-4 py-3 text-left hover:bg-yellow-500/10 transition-all duration-200"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">🤖</span>
                    <span className="text-sm font-semibold text-yellow-400">AI Analysis</span>
                  </div>
                  <svg
                    className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${showAIAnalysis ? "rotate-180" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>
              
              {showAIAnalysis && (
                <div className="mt-2 bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-4">
                  <div className="text-xs text-gray-300 whitespace-pre-wrap">{editorNotes}</div>
                </div>
              )}
            </div>
          )}

          {/* Conversational Edit Section */}
          <div className="max-w-2xl mx-auto mb-6">
            <div className="bg-surface border border-white/5 rounded-xl p-6">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                💬 Tell AI What to Change
              </h3>

              {/* Conversation History */}
              {historyLoading ? (
                <div className="mb-4 space-y-3 animate-pulse">
                  {[...Array(2)].map((_, i) => (
                    <div key={i} className={`flex ${i % 2 === 0 ? "justify-end" : "justify-start"}`}>
                      <div className={`rounded-lg h-8 ${i % 2 === 0 ? "bg-accent/10 w-40" : "bg-white/5 w-48"}`} />
                    </div>
                  ))}
                </div>
              ) : conversation.length > 0 && (
                <div className="mb-4 max-h-60 overflow-y-auto space-y-2 pb-2">
                  {conversation.map((msg, idx) => {
                    // Undo/redo pills
                    if (msg.type === "undo" || msg.type === "redo") {
                      return (
                        <div key={msg.id || idx} className="flex justify-center py-1">
                          <span className="text-xs text-gray-500 bg-white/5 px-3 py-1 rounded-full">
                            {msg.type === "undo" ? "↶" : "↷"} {msg.text}
                          </span>
                        </div>
                      );
                    }
                    
                    // Loading bubble
                    if (msg.type === "loading") {
                      return (
                        <div key="loading" className="flex justify-start">
                          <div className="bg-white/5 px-4 py-2 rounded-lg text-sm text-gray-400 flex items-center gap-2">
                            <span className="animate-pulse">●</span> Working on it…
                          </div>
                        </div>
                      );
                    }
                    
                    // Regular user/system messages
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
                </div>
              )}

              {/* Undo/Redo Toolbar - Compact */}
              <div className="flex gap-2 mb-3 items-center">
                <button
                  onClick={handleUndo}
                  disabled={refining}
                  className="px-3 py-2 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-base transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Undo last edit"
                >
                  ↶
                </button>
                <button
                  onClick={handleRedo}
                  disabled={refining}
                  className="px-3 py-2 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-base transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Redo next edit"
                >
                  ↷
                </button>
                <span className="text-xs text-gray-500 ml-1">Edit history</span>
              </div>

              {/* Input Form */}
              <form onSubmit={handleRefine} className="flex gap-2">
                <input
                  type="text"
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder="Describe changes... e.g. 'Remove the chopping part'"
                  disabled={refining}
                  className="flex-1 px-4 py-3 bg-[#111] border border-white/10 rounded-lg text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-accent/50 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={refining || !instruction.trim()}
                  className="px-6 py-3 bg-accent hover:bg-accent-hover text-white rounded-lg font-medium text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {refining ? "..." : "Send"}
                </button>
              </form>

              {/* Suggested Prompt Chips */}
              <div className="mt-3">
                <p className="text-xs text-gray-400 mb-2">💡 Try these:</p>
                <div className="flex flex-wrap gap-2">
                  {[
                    { text: "Make it 30 seconds", condition: (editPlan?.timeline?.total_effective_duration || 0) > 35 },
                    { text: "Make it shorter", condition: (editPlan?.timeline?.total_effective_duration || 0) > 45 },
                    { text: "Remove blurry clips", condition: true },
                    { text: "Speed up prep section", condition: editorNotes.toLowerCase().includes("prep") },
                    { text: "Add the close-up shot", condition: true },
                    { text: "Remove idle moments", condition: true },
                    { text: "Focus on the plating", condition: editorNotes.toLowerCase().includes("plat") },
                  ]
                    .filter(chip => chip.condition)
                    .slice(0, 4)
                    .map((chip, idx) => (
                      <button
                        key={idx}
                        onClick={() => {
                          setInstruction(chip.text);
                          // Auto-submit if not already refining
                          if (!refining && chip.text.trim()) {
                            setTimeout(() => {
                              const form = document.querySelector('form');
                              if (form) form.requestSubmit();
                            }, 100);
                          }
                        }}
                        disabled={refining}
                        className="px-3 py-1.5 bg-white/5 hover:bg-accent/20 border border-white/10 hover:border-accent/50 text-gray-300 hover:text-white rounded-lg text-xs transition-all duration-200 disabled:opacity-50"
                      >
                        {chip.text}
                      </button>
                    ))}
                </div>
              </div>
            </div>

            {/* Advanced Edit Link */}
            <div className="text-center mt-4">
              <Link
                href={`/dashboard/project/${id}/review`}
                className="text-xs text-gray-500 hover:text-accent transition-all duration-200 underline"
              >
                Advanced Edit (Manual)
              </Link>
            </div>
          </div>

          {/* Text Overlay Section */}
          <div className="max-w-2xl mx-auto mb-6">
            <div className="bg-surface border border-white/5 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  📝 Text Overlays
                  <span className="text-xs text-gray-500 font-normal">({overlays.length})</span>
                </h3>
                <div className="flex gap-2">
                  <button
                    onClick={handleAutoGenerateOverlays}
                    disabled={autoGenerating || savingOverlays}
                    className="px-3 py-1.5 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-xs font-medium transition-all duration-200 disabled:opacity-50"
                  >
                    {autoGenerating ? "⏳" : "✨"} Auto-generate
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

              {/* Overlay List */}
              {overlays.length > 0 ? (
                <div className="space-y-2">
                  {overlays.map((overlay, idx) => (
                    <div
                      key={idx}
                      className="bg-[#111] rounded-lg p-3 flex items-start justify-between gap-3 hover:bg-[#151515] transition-all"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white font-medium truncate mb-1">{overlay.text}</p>
                        <div className="flex items-center gap-3 text-xs text-gray-500">
                          <span>⏱ {formatTime(overlay.start_time)} - {formatTime(overlay.end_time)}</span>
                          <span>•</span>
                          <span>📍 {overlay.position}</span>
                          <span>•</span>
                          <span>🎨 {overlay.style}</span>
                        </div>
                      </div>
                      <div className="flex gap-1 flex-shrink-0">
                        <button
                          onClick={() => openOverlayModal(overlay, idx)}
                          disabled={savingOverlays}
                          className="px-2 py-1 text-xs text-gray-400 hover:text-white transition-all disabled:opacity-50"
                          title="Edit"
                        >
                          ✏️
                        </button>
                        <button
                          onClick={() => handleDeleteOverlay(idx)}
                          disabled={savingOverlays}
                          className="px-2 py-1 text-xs text-gray-400 hover:text-red-400 transition-all disabled:opacity-50"
                          title="Delete"
                        >
                          🗑
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500 text-center py-4">
                  No text overlays yet. Click "Add Text" or "Auto-generate" to create overlays.
                </p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="aspect-video bg-[#111] rounded-2xl border border-white/5 flex items-center justify-center mb-8">
          {project.status === "error" ? (
            <div className="text-center">
              <div className="text-5xl mb-3">❌</div>
              <p className="text-red-400 text-sm">{project.current_step || "Processing failed"}</p>
            </div>
          ) : isProcessing(project.status) || refining ? (
            <div className="text-center w-full max-w-md px-8">
              <div className="text-5xl mb-4 animate-pulse">⚙️</div>
              <p className="text-white font-medium mb-1">
                {refining ? "Re-editing..." : project.current_step || "Processing..."}
              </p>
              <p className="text-xs text-gray-500 mb-4">{Math.round(project.progress || 0)}%</p>
              <div className="h-2 bg-white/5 rounded-full overflow-hidden mb-6">
                <div
                  className="h-full bg-accent rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(project.progress || 0, 100)}%` }}
                />
              </div>
              {/* Step indicators */}
              <div className="flex justify-between text-xs">
                {STEPS.map((step, i) => (
                  <div key={step.key} className={`flex flex-col items-center gap-1 ${i <= stepIdx ? "text-accent" : "text-gray-600"}`}>
                    <div className={`w-3 h-3 rounded-full border-2 ${i < stepIdx ? "bg-accent border-accent" : i === stepIdx ? "border-accent" : "border-gray-600"}`} />
                    <span className="text-[10px]">{step.label}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center">
              <div className="text-6xl mb-3">▶</div>
              <p className="text-sm text-gray-500">Ready to process</p>
            </div>
          )}
        </div>
      )}

      {/* Clip Timeline */}
      {decisions.length > 0 && (
        <div className="mb-4 min-w-0">
          <h2 className="text-base font-semibold text-white mb-4">Clip Timeline</h2>
          <div className="relative">
            {/* Left scroll arrow */}
            <button
              onClick={() => {
                const container = document.getElementById('editor-clip-timeline');
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
                const container = document.getElementById('editor-clip-timeline');
                if (container) container.scrollBy({ left: 200, behavior: 'smooth' });
              }}
              className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-black/80 hover:bg-black/90 text-white rounded-full w-8 h-8 flex items-center justify-center transition-all duration-200 shadow-lg hover:shadow-xl"
              title="Scroll right"
            >
              →
            </button>
            
            <div id="editor-clip-timeline" className="flex gap-3 overflow-x-auto pb-3 max-w-full scroll-smooth">
              {decisions
                .sort((a, b) => a.sequence_order - b.sequence_order)
                .map((clip) => {
                  // Try to find the clip in timeline data for more info
                  const timelineClip = timelineClips.find(c => c.clip_id === clip.id || c.action_id === clip.action_id);
                  const clipTag = getClipTag(timelineClip || clip);
                  
                  return (
                    <div
                      key={clip.id}
                      className="flex-shrink-0 w-44 bg-surface rounded-xl border border-white/5 hover:border-accent/30 transition-all duration-200 overflow-hidden group cursor-pointer"
                    >
                      <div className="aspect-video bg-[#141414] flex items-center justify-center relative group-hover:bg-[#1a1a1a] transition-all duration-200">
                        {/* Try to load thumbnail, fallback to icon */}
                        <img
                          src={api.getClipThumbnailUrl(id, clip.id)}
                          alt={clip.reason || "Clip"}
                          className="w-full h-full object-cover"
                          loading="lazy"
                          onError={(e) => {
                            // Hide image and show fallback icon on error
                            e.currentTarget.style.display = 'none';
                            const fallback = e.currentTarget.nextElementSibling;
                            if (fallback) (fallback as HTMLElement).style.display = 'block';
                          }}
                        />
                        <span className="text-2xl absolute" style={{ display: 'none' }}>🎞</span>
                        
                        {/* Clip Tag Badge */}
                        {clipTag && (
                          <div className={`absolute top-2 left-2 px-2 py-0.5 rounded-full text-[10px] font-semibold border flex items-center gap-1 ${clipTag.color}`}>
                            <span>{clipTag.icon}</span>
                            <span>{clipTag.label}</span>
                          </div>
                        )}
                      </div>
                      <div className="p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-accent font-semibold">Clip {clip.sequence_order + 1}</span>
                          <span className="text-xs text-gray-500">
                            {formatTime(clip.start_time)} – {formatTime(clip.end_time)}
                          </span>
                        </div>
                        <p className="text-xs text-gray-300 truncate">{clip.reason || clip.filename || "—"}</p>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}

      {/* Export Section - Moved to bottom after all editing tools */}
      {project.status === "completed" && project.output_path && (
        <div className="max-w-2xl mx-auto mt-8 mb-6">
          <div className="bg-surface border border-white/5 rounded-xl p-6">
            <h3 className="text-sm font-semibold text-white mb-4 text-center">Ready to Export</h3>
            
            {/* Export Format Selector */}
            <div className="mb-4">
              <label className="text-xs text-gray-500 block mb-2 text-center">Export Format</label>
              <div className="flex gap-2 justify-center">
                {[
                  { value: "9:16", label: "9:16", icon: "📱", desc: "Vertical" },
                  { value: "1:1", label: "1:1", icon: "⬜", desc: "Square" },
                  { value: "16:9", label: "16:9", icon: "🖥", desc: "Landscape" },
                ].map((format) => {
                  const isCurrentFormat = project?.aspect_ratio === format.value;
                  const isSelected = selectedExportFormat === format.value;
                  return (
                    <button
                      key={format.value}
                      onClick={() => setSelectedExportFormat(isSelected ? null : format.value)}
                      disabled={hdRendering}
                      className={`px-4 py-2.5 rounded-lg text-xs font-medium transition-all duration-200 flex items-center gap-2 ${
                        isSelected 
                          ? "bg-accent text-white" 
                          : isCurrentFormat
                          ? "bg-green-500/20 text-green-400 border border-green-500/30"
                          : "bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white"
                      } disabled:opacity-50`}
                      title={isCurrentFormat ? `${format.desc} (Original)` : format.desc}
                    >
                      <span>{format.icon}</span>
                      <span>{format.label}</span>
                      {isCurrentFormat && <span className="text-[9px]">✓</span>}
                    </button>
                  );
                })}
              </div>
              {selectedExportFormat && selectedExportFormat !== project?.aspect_ratio && (
                <p className="text-xs text-orange-400 mt-2 text-center">
                  ⚠️ Re-exporting in {selectedExportFormat} format (not implemented yet - coming soon!)
                </p>
              )}
            </div>

            {/* Primary Action: Export */}
            <div className="text-center">
              <button
                onClick={handleDownload}
                className="bg-accent hover:bg-accent-hover text-white px-8 py-4 rounded-xl font-semibold text-base transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/30"
              >
                ⬇️ Export Video
              </button>
            </div>
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
            {/* Modal Header */}
            <div className="sticky top-0 bg-[#111] border-b border-white/10 px-6 py-4 flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">
                {editingOverlay ? "Edit Text Overlay" : "Add Text Overlay"}
              </h2>
              <button
                onClick={closeOverlayModal}
                disabled={savingOverlays}
                className="text-gray-500 hover:text-white transition-all duration-200 disabled:opacity-50"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-6">
              {/* Text Input */}
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

              {/* Time Inputs */}
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

              {/* Style Picker */}
              <div>
                <label className="text-sm text-gray-400 block mb-2">Style</label>
                <div className="flex gap-2">
                  {[
                    { value: "bold-white", label: "Bold White", desc: "White text with black outline" },
                    { value: "subtitle-bar", label: "Subtitle Bar", desc: "White text on black background" },
                    { value: "minimal", label: "Minimal", desc: "Small text with subtle shadow" },
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
                      title={style.desc}
                    >
                      {style.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Position Picker */}
              <div>
                <label className="text-sm text-gray-400 block mb-2">Position</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { value: "top-left", label: "Top Left", icon: "↖️" },
                    { value: "top-center", label: "Top Center", icon: "⬆️" },
                    { value: "bottom-center", label: "Bottom Center", icon: "⬇️" },
                    { value: "center", label: "Center", icon: "⏺" },
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
                      <span>{pos.icon}</span>
                      <span>{pos.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Font Size */}
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
                  <span>24px (Small)</span>
                  <span>72px (Large)</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-3 pt-4 border-t border-white/10">
                <button
                  onClick={handleSaveOverlay}
                  disabled={savingOverlays || !overlayText.trim()}
                  className="bg-accent hover:bg-accent-hover text-white px-8 py-3 rounded-xl font-semibold text-sm transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {savingOverlays ? "⏳ Saving..." : editingOverlay ? "💾 Update" : "➕ Add"}
                </button>
                <button
                  onClick={closeOverlayModal}
                  disabled={savingOverlays}
                  className="text-sm text-gray-500 hover:text-white transition-all duration-200 disabled:opacity-50"
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
