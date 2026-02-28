const API_BASE = "http://localhost:8000";

export interface Project {
  id: string;
  name: string;
  dish_name?: string;
  recipe_details?: string;
  instructions?: string;
  output_duration?: number;
  aspect_ratio?: string;  // "16:9", "9:16", "1:1"
  status: "created" | "uploading" | "processing" | "analyzing" | "selecting" | "review" | "stitching" | "completed" | "error";
  progress: number;
  current_step?: string;
  output_path?: string;
  created_at: string;
  updated_at?: string;
}

export interface VideoClip {
  id: string;
  project_id: string;
  filename: string;
  filepath: string;
  duration?: number;
  width?: number;
  height?: number;
}

export interface EditDecision {
  id: string;
  project_id: string;
  source_clip_id?: string;
  sequence_order: number;
  start_time: number;
  end_time: number;
  reason?: string;
  filename?: string;
}

export interface UploadedVideo {
  id: string;
  filename: string;
  filepath: string;
  size?: number;
}

export interface WSMessage {
  status: string;
  progress: number;
  current_step: string;
}

export interface ConversationMsg {
  id: string;
  role: "user" | "assistant";
  text: string;
  version: number;
  timestamp: string;
  undone: boolean;
}

function normalizeIds<T>(obj: T): T {
  if (Array.isArray(obj)) return obj.map(normalizeIds) as T;
  if (obj && typeof obj === "object") {
    const o = obj as Record<string, unknown>;
    if ("_id" in o && !("id" in o)) {
      o.id = o._id;
    }
    return o as T;
  }
  return obj;
}

let _userEmail = "anonymous";

export function setUserEmail(email: string) {
  _userEmail = email;
  if (typeof window !== "undefined") {
    sessionStorage.setItem("vp_user_email", email);
  }
}

function getUserEmail(): string {
  if (_userEmail !== "anonymous") return _userEmail;
  if (typeof window !== "undefined") {
    return sessionStorage.getItem("vp_user_email") || "anonymous";
  }
  return "anonymous";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("x-user-email", getUserEmail());
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  const data = await res.json();
  return normalizeIds(data);
}

export const api = {
  listProjects: () => apiFetch<Project[]>("/api/projects"),

  getProject: (id: string) => apiFetch<Project>(`/api/projects/${id}`),

  createProject: (data: {
    name: string;
    recipe_details?: string;
    dish_name?: string;
    instructions?: string;
    output_duration?: number;
    aspect_ratio?: string;
  }) =>
    apiFetch<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  deleteProject: (id: string) =>
    apiFetch<void>(`/api/projects/${id}`, { method: "DELETE" }),

  uploadVideo: (
    projectId: string,
    file: File,
    onProgress?: (pct: number) => void
  ): Promise<UploadedVideo> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/projects/${projectId}/upload`);
      xhr.setRequestHeader("x-user-email", getUserEmail());
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total);
        };
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      };
      xhr.onerror = () => reject(new Error("Upload network error"));
      const fd = new FormData();
      fd.append("file", file);
      xhr.send(fd);
    });
  },

  listUploads: (projectId: string) =>
    apiFetch<UploadedVideo[]>(`/api/projects/${projectId}/upload`),

  startProcessing: (projectId: string, outputDuration?: number) =>
    apiFetch<Project>(`/api/projects/${projectId}/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output_duration: outputDuration }),
    }),

  getClips: (projectId: string) =>
    apiFetch<VideoClip[]>(`/api/projects/${projectId}/clips`),

  getDecisions: (projectId: string) =>
    apiFetch<EditDecision[]>(`/api/projects/${projectId}/decisions`),

  // Edit plan endpoints
  getEditPlan: (projectId: string) =>
    apiFetch<any>(`/api/projects/${projectId}/edit-plan`),

  updateEditPlan: (projectId: string, clips: any[]) =>
    apiFetch<any>(`/api/projects/${projectId}/edit-plan`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clips }),
    }),

  confirmAndRender: (projectId: string) =>
    apiFetch<any>(`/api/projects/${projectId}/edit-plan/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),

  refineEditPlan: (projectId: string, instruction: string) =>
    apiFetch<any>(`/api/projects/${projectId}/edit-plan/refine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ instruction }),
    }),

  undoEdit: (projectId: string) =>
    apiFetch<any>(`/api/projects/${projectId}/edit-plan/undo`, {
      method: "POST",
    }),

  redoEdit: (projectId: string) =>
    apiFetch<any>(`/api/projects/${projectId}/edit-plan/redo`, {
      method: "POST",
    }),

  getConversation: (projectId: string) =>
    apiFetch<{ conversation: ConversationMsg[]; current_version: number }>(
      `/api/projects/${projectId}/edit-plan/conversation`
    ),

  getProxyPreview: (projectId: string) =>
    `${API_BASE}/api/projects/${projectId}/edit-plan/preview`,

  getClipThumbnailUrl: (projectId: string, clipId: string) =>
    `${API_BASE}/api/projects/${projectId}/edit-plan/thumbnails/${clipId}`,

  getOutputUrl: (projectId: string) =>
    `${API_BASE}/api/projects/${projectId}/output`,

  getVideoUrl: (outputPath: string) => {
    const clean = outputPath.replace(/^\.\//, "");
    return `${API_BASE}/${clean}`;
  },

  connectWS: (projectId: string, onMessage: (msg: WSMessage) => void) => {
    const ws = new WebSocket(`ws://localhost:8000/ws/${projectId}`);
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data));
      } catch {}
    };
    return ws;
  },
};
