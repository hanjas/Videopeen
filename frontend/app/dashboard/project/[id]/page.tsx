"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import { api, Project, EditDecision } from "@/lib/api";
import { useToast } from "@/components/Toast";

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

          {/* Primary Action: Export */}
          <div className="text-center mb-6">
            <button
              onClick={handleDownload}
              className="bg-accent hover:bg-accent-hover text-white px-8 py-4 rounded-xl font-semibold text-base transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/30"
            >
              ⬇️ Export Video
            </button>
          </div>

          {/* Conversational Edit Section */}
          <div className="max-w-2xl mx-auto mb-6">
            <div className="bg-surface border border-white/5 rounded-xl p-6">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                💬 Adjust Your Edit
                <span className="text-xs text-gray-500 font-normal">(optional)</span>
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

              {/* Undo/Redo Buttons */}
              <div className="flex gap-2 mb-3">
                <button
                  onClick={handleUndo}
                  disabled={refining}
                  className="flex-1 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  title="Undo last edit"
                >
                  <span>↶</span> Undo
                </button>
                <button
                  onClick={handleRedo}
                  disabled={refining}
                  className="flex-1 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  title="Redo next edit"
                >
                  <span>↷</span> Redo
                </button>
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

              <p className="text-xs text-gray-500 mt-3">
                Examples: "Make it 30 seconds", "Remove idle moments", "Add the close-up shot"
              </p>
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
          <div className="flex gap-3 overflow-x-auto pb-3 max-w-full">
            {decisions
              .sort((a, b) => a.sequence_order - b.sequence_order)
              .map((clip) => (
                <div
                  key={clip.id}
                  className="flex-shrink-0 w-44 bg-surface rounded-xl border border-white/5 hover:border-accent/30 transition-all duration-200 overflow-hidden group cursor-pointer"
                >
                  <div className="aspect-video bg-[#141414] flex items-center justify-center text-2xl group-hover:bg-[#1a1a1a] transition-all duration-200">
                    🎞
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
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
