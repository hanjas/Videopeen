"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback, useRef } from "react";
import { api, Project } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { 
  X, 
  Clapperboard, 
  Upload, 
  Video, 
  Sparkles, 
  Smartphone, 
  Square, 
  Monitor, 
  Loader2, 
  Rocket,
  Trash2,
  FolderOpen
} from "lucide-react";

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

interface FileEntry {
  file: File;
  progress: number;
  uploaded: boolean;
  error?: string;
}

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const router = useRouter();
  const { toast } = useToast();

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [duration, setDuration] = useState("60s");
  const [style, setStyle] = useState("Fast-paced");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [transitionType, setTransitionType] = useState("fade");
  const [transitionDuration, setTransitionDuration] = useState(0.5);
  const [generating, setGenerating] = useState(false);
  const [modalError, setModalError] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const fetchProjects = useCallback(async () => {
    try {
      const data = await api.listProjects();
      setProjects(data);
      setError("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
    const interval = setInterval(fetchProjects, 5000);
    return () => clearInterval(interval);
  }, [fetchProjects]);

  // Modal functions
  const openModal = () => {
    setModalOpen(true);
    setName("");
    setFiles([]);
    setDuration("60s");
    setStyle("Fast-paced");
    setAspectRatio("16:9");
    setTransitionType("fade");
    setTransitionDuration(0.5);
    setModalError("");
  };

  const closeModal = () => {
    if (!generating) {
      setModalOpen(false);
    }
  };

  const addFiles = (newFiles: FileList | File[]) => {
    const entries: FileEntry[] = Array.from(newFiles).map((f) => ({
      file: f,
      progress: 0,
      uploaded: false,
    }));
    setFiles((prev) => [...prev, ...entries]);
  };

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const formatSize = (bytes: number) => {
    if (bytes >= 1e9) return (bytes / 1e9).toFixed(1) + " GB";
    if (bytes >= 1e6) return (bytes / 1e6).toFixed(0) + " MB";
    return (bytes / 1e3).toFixed(0) + " KB";
  };

  const handleGenerate = async () => {
    if (files.length === 0) {
      setModalError("Upload at least one video");
      return;
    }
    setGenerating(true);
    setModalError("");

    try {
      const durationSeconds = parseInt(duration);

      // 1. Create project
      const project = await api.createProject({
        name: name.trim() || "Untitled Project",
        output_duration: durationSeconds,
        instructions: style,
        aspect_ratio: aspectRatio,
        transition_type: transitionType,
        transition_duration: transitionDuration,
      });

      // 2. Upload files
      for (let i = 0; i < files.length; i++) {
        const idx = i;
        try {
          await api.uploadVideo(project.id, files[idx].file, (pct) => {
            setFiles((prev) =>
              prev.map((f, j) => (j === idx ? { ...f, progress: pct } : f))
            );
          });
          setFiles((prev) =>
            prev.map((f, j) => (j === idx ? { ...f, uploaded: true, progress: 1 } : f))
          );
        } catch {
          setFiles((prev) =>
            prev.map((f, j) =>
              j === idx ? { ...f, error: "Upload failed" } : f
            )
          );
          throw new Error(`Failed to upload ${files[idx].file.name}`);
        }
      }

      // 3. Start processing
      await api.startProcessing(project.id, durationSeconds);

      // 4. Close modal, refresh projects, show success message
      toast("success", `Project created successfully`);
      setModalOpen(false);
      setGenerating(false);
      fetchProjects();

      // 5. Navigate to project page
      router.push(`/dashboard/project/${project.id}`);
    } catch (e: unknown) {
      setModalError(e instanceof Error ? e.message : "Something went wrong");
      setGenerating(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string, name: string) => {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Delete "${name}"?`)) return;
    setDeleting(id);
    try {
      await api.deleteProject(id);
      setProjects((p) => p.filter((x) => x.id !== id));
      toast("success", `"${name}" deleted`);
    } catch {
      toast("error", "Failed to delete project");
    } finally {
      setDeleting(null);
    }
  };

  const timeAgo = (d: string | undefined) => {
    if (!d) return "";
    try {
      const date = new Date(d);
      if (isNaN(date.getTime())) return "";
      const now = Date.now();
      const diff = now - date.getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return "just now";
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      const days = Math.floor(hrs / 24);
      if (days < 7) return `${days}d ago`;
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    } catch {
      return "";
    }
  };

  if (loading) {
    return (
      <div>
        <div className="flex items-center justify-between mb-8">
          <div>
            <div className="h-7 w-32 bg-white/5 rounded animate-pulse" />
            <div className="h-4 w-16 bg-white/5 rounded animate-pulse mt-2" />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-surface rounded-xl border border-white/5 overflow-hidden">
              <div className="aspect-video bg-white/5 animate-pulse" />
              <div className="p-4 space-y-2">
                <div className="h-4 bg-white/5 rounded animate-pulse w-3/4" />
                <div className="h-3 bg-white/5 rounded animate-pulse w-1/2" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
          <button onClick={() => setError("")} className="ml-2 text-red-300 hover:text-white"><X size={16} /></button>
        </div>
      )}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Projects</h1>
          <p className="text-sm text-gray-500 mt-1">{projects.length} video{projects.length !== 1 ? "s" : ""}</p>
        </div>
        <button
          onClick={openModal}
          className="bg-accent hover:bg-accent-hover text-white px-5 py-2.5 rounded-lg font-medium text-sm transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20"
        >
          + New Project
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-20">
          <div className="mb-4 flex justify-center text-gray-600"><Clapperboard size={48} /></div>
          <h2 className="text-lg font-semibold text-white mb-2">No projects yet</h2>
          <p className="text-sm text-gray-500 mb-6">Create your first AI-edited cooking video</p>
          <button
            onClick={openModal}
            className="bg-accent hover:bg-accent-hover text-white px-6 py-3 rounded-lg font-medium text-sm transition-all duration-200"
          >
            + New Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {projects.map((p) => (
            <div
              key={p.id}
              onClick={() => router.push(`/dashboard/project/${p.id}`)}
              className="bg-surface rounded-xl border border-white/5 hover:border-white/10 transition-all duration-200 overflow-hidden group cursor-pointer relative"
            >
              <div className="aspect-video bg-[#141414] flex items-center justify-center text-gray-600 group-hover:bg-[#1a1a1a] transition-all duration-200">
                <Clapperboard size={32} />
              </div>
              <div className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold text-white group-hover:text-accent transition-all duration-200 truncate mr-2">
                    {p.name || "Untitled Project"}
                  </h3>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium text-white flex-shrink-0 ${statusColor[p.status] || "bg-gray-500"}`}>
                    {p.status}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>{timeAgo(p.created_at)}</span>
                  <button
                    onClick={(e) => handleDelete(e, p.id, p.name)}
                    disabled={deleting === p.id}
                    className="text-gray-600 hover:text-red-400 transition-all opacity-0 group-hover:opacity-100"
                  >
                    {deleting === p.id ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  </button>
                </div>
                {(p.status === "processing" || p.status === "analyzing" || p.status === "selecting" || p.status === "stitching") && (
                  <div className="mt-2 h-1 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full transition-all duration-500"
                      style={{ width: `${Math.min(p.progress || 0, 100)}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* New Project Modal */}
      {modalOpen && (
        <div 
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
          onClick={closeModal}
        >
          <div 
            className="bg-[#111] border border-white/10 rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="sticky top-0 bg-[#111] border-b border-white/10 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-bold text-white">New Project</h2>
                <p className="text-sm text-gray-500 mt-1">Upload your footage and let AI create an intelligent edit</p>
              </div>
              <button
                onClick={closeModal}
                disabled={generating}
                className="text-gray-500 hover:text-white transition-all duration-200 disabled:opacity-50"
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6">
              {modalError && (
                <div className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="text-red-400 font-medium mb-1">Upload failed</div>
                      <div className="text-red-400/80 text-sm">{modalError}</div>
                      <div className="text-red-400/60 text-xs mt-2">Click "Generate Video" to retry the upload.</div>
                    </div>
                    <button onClick={() => setModalError("")} className="text-red-300 hover:text-white ml-3"><X size={16} /></button>
                  </div>
                </div>
              )}

              {/* Project Name */}
              <div className="mb-6">
                <label className="text-sm text-gray-400 block mb-2">Project Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Pasta Carbonara"
                  disabled={generating}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 transition-all duration-200 disabled:opacity-50"
                />
              </div>

              {/* Upload Zone */}
              <input
                ref={fileInput}
                type="file"
                accept="video/*"
                multiple
                className="hidden"
                onChange={(e) => e.target.files && addFiles(e.target.files)}
              />
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
                }}
                onClick={() => !generating && fileInput.current?.click()}
                className={`border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-200 mb-6 ${
                  dragging ? "border-accent bg-accent/5" : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
                } ${generating ? "opacity-50 pointer-events-none" : ""}`}
              >
                <div className="mb-3 flex justify-center text-gray-500"><Upload size={40} /></div>
                <p className="text-white font-medium mb-1">Drag & drop video files here</p>
                <p className="text-sm text-gray-500">or <span className="text-accent hover:underline">browse files</span></p>
                <p className="text-xs text-gray-600 mt-2">MP4, MOV, AVI — up to 5GB</p>
              </div>

              {/* File List */}
              {files.length > 0 && (
                <div className="bg-[#0a0a0a] rounded-xl border border-white/5 p-4 mb-6">
                  {/* Overall Upload Status */}
                  {generating && (
                    <div className="mb-3 pb-3 border-b border-white/5">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-400 font-medium">
                          Uploading {files.filter(f => f.uploaded).length} / {files.length} files...
                        </span>
                        <span className="text-accent font-semibold">
                          {Math.round((files.filter(f => f.uploaded).length / files.length) * 100)}%
                        </span>
                      </div>
                    </div>
                  )}
                  
                  {/* Individual Files */}
                  <div className="space-y-3">
                    {files.map((f, i) => (
                      <div key={i} className="py-2 px-3 rounded-lg bg-white/5 hover:bg-white/[0.07] transition-all duration-200">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            <Video size={20} className="flex-shrink-0 text-gray-400" />
                            <span className="text-sm text-white truncate">{f.file.name}</span>
                          </div>
                          <div className="flex items-center gap-3 flex-shrink-0">
                            <span className="text-xs text-gray-500">{formatSize(f.file.size)}</span>
                            {f.uploaded && <span className="text-xs text-green-400 font-bold">✓</span>}
                            {!generating && (
                              <button onClick={() => removeFile(i)} className="text-xs text-gray-600 hover:text-red-400 transition-colors"><X size={14} /></button>
                            )}
                          </div>
                        </div>
                        
                        {/* Progress Bar */}
                        {generating && !f.uploaded && !f.error && (
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="text-gray-500">Uploading...</span>
                              <span className="text-accent font-semibold">{Math.round(f.progress * 100)}%</span>
                            </div>
                            <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-accent to-orange-400 rounded-full transition-all duration-300 ease-out"
                                style={{ width: `${f.progress * 100}%` }}
                              />
                            </div>
                          </div>
                        )}
                        
                        {/* Error State */}
                        {f.error && (
                          <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 px-2 py-1.5 rounded mt-2">
                            <X size={12} />
                            <span className="font-medium">{f.error}</span>
                          </div>
                        )}
                        
                        {/* Success State */}
                        {f.uploaded && (
                          <div className="text-xs text-green-400 mt-1">
                            ✓ Upload complete
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Intelligence Note */}
              <div className="bg-gradient-to-r from-accent/10 to-purple-500/10 border border-accent/20 rounded-xl p-4 mb-6">
                <div className="flex items-start gap-3">
                  <Sparkles size={24} className="text-accent flex-shrink-0" />
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-1">AI Will Analyze Your Footage</h4>
                    <p className="text-xs text-gray-300">
                      Our AI will identify key moments, detect actions, build a story structure, and create an intelligent edit optimized for engagement.
                    </p>
                  </div>
                </div>
              </div>

              {/* Simplified Settings */}
              <div className="bg-[#0a0a0a] rounded-xl border border-white/5 p-6 mb-6">
                <h3 className="text-sm font-semibold text-white mb-4">Output Format</h3>
                
                {/* Aspect Ratio Selector - Simplified */}
                <div className="flex gap-2">
                  {[
                    { value: "9:16", label: "9:16", Icon: Smartphone, desc: "Vertical" },
                    { value: "1:1", label: "1:1", Icon: Square, desc: "Square" },
                    { value: "16:9", label: "16:9", Icon: Monitor, desc: "Landscape" },
                  ].map((format) => (
                    <button
                      key={format.value}
                      onClick={() => setAspectRatio(format.value)}
                      disabled={generating}
                      className={`flex-1 px-3 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                        aspectRatio === format.value ? "bg-accent text-white" : "bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white"
                      } disabled:opacity-50 flex flex-col items-center gap-1`}
                      title={format.desc}
                    >
                      <format.Icon size={20} />
                      <span className="text-xs">{format.label}</span>
                    </button>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-3 text-center">
                  AI will use smooth transitions and optimize pacing automatically
                </p>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-3">
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="bg-accent hover:bg-accent-hover text-white px-8 py-3 rounded-xl font-semibold text-sm transition-all duration-200 hover:shadow-lg hover:shadow-orange-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {generating ? (
                    <span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Generating...</span>
                  ) : (
                    <span className="flex items-center gap-2"><Rocket size={16} /> Generate Video</span>
                  )}
                </button>
                <button 
                  onClick={closeModal}
                  disabled={generating}
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
