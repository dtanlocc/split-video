import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
// Thay thế phần import lucide-react bằng:
import {
  Play, FolderOpen, FolderPlus, FileVideo, Settings,
  Cpu, HardDrive, Type, Scissors, X, Eye, Key,
  AlertTriangle, LogOut, AlertCircle, Film, ChevronDown, 
  Search, RefreshCw, Maximize2, Minimize2, Sparkles, 
  Trash2, CheckCircle2, ArrowUp, ArrowDown,
  ShieldCheck
} from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";

// ==============================================================================
// TYPES
// ==============================================================================
interface LicenseInfo {
  status: string;
  plan: string;
  quota_used: number;
  quota_limit: number;
  quota_remain: number;
  expires_at: string | null;
  is_expired: boolean;
}

type VideoStatus = "pending" | "processing" | "done" | "error";

interface VideoItem {
  id: string;
  path: string;
  name: string;
  dir: string;
  status: VideoStatus;
  addedAt: number;
  progress?: number;
  error?: string;
}

interface ProgressEvent {
  stage: "init" | "audio" | "stt" | "ai" | "cut" | "crop" | "render" | "complete";
  pct: number;
  status: "inf" | "ok" | "err" | "warn";
  msg: string;
  meta?: {
    video?: string;
    model?: string;
    suggestion?: string;
    retry_possible?: boolean;
    action?: "open_folder";
    path?: string;
    [key: string]: any;
  };
}

interface ErrorModalState {
  visible: boolean;
  message: string;
  suggestion?: string;
  retryPossible: boolean;
  videoId?: string;
  technical?: string;
}

interface Toast {
  id: string;
  type: "success" | "error" | "info" | "warning";
  message: string;
  duration?: number;
}

interface ConfigState {
  gemini_api_key: string;
  lang_code: string;
  whisper_model: string;
  whisper_device: string;
  whisper_compute_type: string;
  min_duration: number;
  max_duration: number;
  sharpen_strength: string;
  title_color: string;
  sub_bg_color: string;
  max_words_per_line: number;
  sub_margin_v: number;
  sub_font_size: number;
  video_speed: number;
  font_title_file: string;
  gemini_model: string;
}

// ==============================================================================
// CONSTANTS & HELPERS
// ==============================================================================
const STAGE_INFO: Record<ProgressEvent["stage"], { label: string; icon: any; color: string }> = {
  init: { label: "Khởi động", icon: Sparkles, color: "#6366f1" },
  audio: { label: "Tách audio", icon: Scissors, color: "#22c55e" },
  stt: { label: "Nhận diện", icon: Cpu, color: "#3b82f6" },
  ai: { label: "Phân tích AI", icon: Sparkles, color: "#a78bfa" },
  cut: { label: "Cắt video", icon: Scissors, color: "#f59e0b" },
  crop: { label: "Smart crop", icon: Eye, color: "#ec4899" },
  render: { label: "Render final", icon: Film, color: "#14b8a6" },
  complete: { label: "Hoàn tất", icon: CheckCircle2, color: "#4ade80" },
};

const PLAN_COLORS: Record<string, { label: string; color: string; bg: string }> = {
  starter: { label: "Starter", color: "#94a3b8", bg: "rgba(148,163,184,0.1)" },
  pro: { label: "Pro", color: "#a78bfa", bg: "rgba(167,139,250,0.1)" },
  unlimited: { label: "Unlimited", color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
};

const fileName = (p: string) => p.split(/[\/\\]/).pop() ?? p;
const fileDir = (p: string) => p.split(/[\/\\]/).slice(0, -1).join("/") || p;

function formatExpiry(expiresAt: string | null): string {
  if (!expiresAt) return "Vĩnh viễn ♾️";
  const d = new Date(expiresAt);
  const diff = Math.ceil((d.getTime() - Date.now()) / 86400000);
  if (diff <= 0) return "Đã hết hạn ❌";
  if (diff <= 7) return `Còn ${diff} ngày ⚠️`;
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatETA(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} phút`;
  return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

function getLogColor(log: string): string {
  if (log.includes("❌") || log.includes("Lỗi") || log.includes("error") || log.includes("failed")) return "#f87171";
  if (log.includes("✅") || log.includes("Hoàn tất") || log.includes("success") || log.includes("done")) return "#4ade80";
  if (log.includes("⏳") || log.includes("Đang") || log.includes("processing") || log.includes("ing...")) return "#fbbf24";
  if (log.includes("⚠️") || log.includes("warning") || log.includes("cảnh báo")) return "#fcd34d";
  if (log.includes("🔍") || log.includes("🎬") || log.includes("🧠") || log.includes("🔐")) return "#a78bfa";
  return "#6b7280";
}

// ==============================================================================
// SHARED STYLES
// ==============================================================================
const IS: React.CSSProperties = {
  width: "100%", background: "#0c0c10", border: "1.5px solid #1e1e2a",
  borderRadius: 10, padding: "9px 12px", color: "white", fontSize: 14, outline: "none",
  transition: "border-color 0.2s", boxSizing: "border-box"
};

// ==============================================================================
// OPTIMIZED MICRO COMPONENTS (React.memo)
// ==============================================================================

function Spin({ size = 20, color = "#a78bfa" }: { size?: number; color?: string }) {
  return (
    <div style={{ width: size, height: size, border: `2px solid ${color}30`, borderTopColor: color, borderRadius: "50%", animation: "_spin 0.8s linear infinite", flexShrink: 0 }} />
  );
}

// function Sep() { return <div style={{ width: 1, height: 20, background: "#2a2a38" }} />; }

function Chip({ color, children, onClick }: { color: string; children: React.ReactNode; onClick?: () => void }) {
  return (
    <span onClick={onClick} style={{ fontSize: 12, fontWeight: 600, color, background: `${color}18`, borderRadius: 6, padding: "2px 8px", cursor: onClick ? "pointer" : "default", transition: "background 0.2s" }}>
      {children}
    </span>
  );
}

const StatusBadge = React.memo(({ status }: { status: VideoStatus }) => {
  const map = {
    pending: { label: "Chờ xử lý", color: "#6b7280", bg: "rgba(107,114,128,0.1)" },
    processing: { label: "Đang xử lý", color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
    done: { label: "Hoàn tất", color: "#4ade80", bg: "rgba(74,222,128,0.1)" },
    error: { label: "Lỗi", color: "#f87171", bg: "rgba(248,113,113,0.1)" },
  };
  const s = map[status];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 5, background: s.bg, borderRadius: 6, padding: "3px 9px", flexShrink: 0 }}>
      {status === "processing" && <Spin size={10} color="#fbbf24" />}
      {status === "done" && <CheckCircle2 size={12} color="#4ade80" />}
      {status === "error" && <AlertCircle size={12} color="#f87171" />}
      {status === "pending" && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4b5563" }} />}
      <span style={{ fontSize: 11, fontWeight: 700, color: s.color }}>{s.label}</span>
    </div>
  );
});

function Field({ label, children, style = {}, hint }: { label: string; children: React.ReactNode; style?: React.CSSProperties; hint?: string }) {
  return (
    <div style={style}>
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 6 }}>
        <label style={{ fontSize: 12, color: "#4b5563", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>{label}</label>
        {hint && <span style={{ fontSize: 10, color: "#6b7280" }} title={hint}>ⓘ</span>}
      </div>
      {children}
    </div>
  );
}

function GhostBtn({ onClick, icon, children, disabled, active }: { onClick?: () => void; icon?: React.ReactNode; children?: React.ReactNode; disabled?: boolean; active?: boolean }) {
  return (
    <button onClick={disabled ? undefined : onClick} disabled={disabled} style={{ display: "flex", alignItems: "center", gap: 6, background: active ? "rgba(124,58,237,0.15)" : "rgba(255,255,255,0.04)", border: `1px solid ${active ? "#7c3aed" : "#1e1e2a"}`, borderRadius: 10, padding: "7px 13px", color: active ? "#a78bfa" : "#9ca3af", fontSize: 13, fontWeight: 500, cursor: disabled ? "not-allowed" : "pointer", transition: "all 0.2s" }}>
      {icon}{children}
    </button>
  );
}

function SmallBtn({ onClick, children, disabled = false, danger = false, title = "", color }: { onClick?: () => void; children: React.ReactNode; disabled?: boolean; danger?: boolean; title?: string; color?: string }) {
  return (
    <button onClick={disabled ? undefined : onClick} title={title} disabled={disabled} style={{ background: "#1a1a26", border: "none", borderRadius: 7, padding: "6px 7px", cursor: disabled ? "not-allowed" : "pointer", display: "flex", alignItems: "center", opacity: disabled ? 0.3 : 1, color: color || (danger ? "#f87171" : "#9ca3af"), transition: "background 0.2s" }}
      onMouseEnter={(e) => { if (!disabled) e.currentTarget.style.background = "#2a2a3a"; }}
      onMouseLeave={(e) => { if (!disabled) e.currentTarget.style.background = "#1a1a26"; }}>
      {children}
    </button>
  );
}

function CollapsibleSection({ title, icon, color, expanded, onToggle, children }: { title: string; icon: React.ReactNode; color: string; expanded: boolean; onToggle: () => void; children: React.ReactNode; }) {
  return (
    <div>
      <button onClick={onToggle} style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10, background: "none", border: "none", cursor: "pointer", width: "100%", textAlign: "left", padding: 0 }}>
        <span style={{ color }}>{icon}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: "0.06em" }}>{title}</span>
        <span style={{ marginLeft: "auto", color: "#4b5563", transition: "transform 0.2s", transform: expanded ? "rotate(180deg)" : "" }}><ChevronDown size={14} /></span>
      </button>
      {expanded && (
        <div style={{ background: "#16161e", border: "1px solid #1e1e2a", borderRadius: 14, padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const ToastContainer = React.memo(({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: string) => void }) => {
  return (
    <div style={{ position: "fixed", bottom: 24, right: 24, display: "flex", flexDirection: "column", gap: 8, zIndex: 1000, pointerEvents: "none" }}>
      {toasts.map(toast => {
        const colors = { success: { bg: "rgba(74,222,128,0.12)", border: "#22c55e", text: "#4ade80", icon: CheckCircle2 }, error: { bg: "rgba(248,113,113,0.12)", border: "#ef4444", text: "#f87171", icon: AlertCircle }, warning: { bg: "rgba(251,191,36,0.12)", border: "#f59e0b", text: "#fbbf24", icon: AlertTriangle }, info: { bg: "rgba(124,58,237,0.12)", border: "#7c3aed", text: "#a78bfa", icon: Sparkles } };
        const c = colors[toast.type];
        const Icon = c.icon;
        return (
          <div key={toast.id} style={{ display: "flex", alignItems: "center", gap: 10, background: c.bg, border: `1px solid ${c.border}`, borderRadius: 12, padding: "12px 16px", minWidth: 280, maxWidth: 400, animation: "slideIn 0.2s ease-out", pointerEvents: "auto", boxShadow: "0 4px 20px rgba(0,0,0,0.3)" }}>
            <Icon size={18} color={c.text} style={{ flexShrink: 0 }} />
            <span style={{ color: c.text, fontSize: 14, flex: 1, lineHeight: 1.4 }}>{toast.message}</span>
            <button onClick={() => onDismiss(toast.id)} style={{ background: "none", border: "none", cursor: "pointer", color: c.text, opacity: 0.7, padding: 4 }} onMouseEnter={(e) => e.currentTarget.style.opacity = "1"} onMouseLeave={(e) => e.currentTarget.style.opacity = "0.7"}><X size={16} /></button>
          </div>
        );
      })}
    </div>
  );
});

const ErrorModal = React.memo(({ state, onClose, onRetry }: { state: ErrorModalState; onClose: () => void; onRetry: (videoId?: string) => void; }) => {
  if (!state.visible) return null;
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, backdropFilter: "blur(4px)" }} onClick={onClose}>
      <div style={{ background: "#16161e", border: "1px solid #2a2a38", borderRadius: 20, padding: 24, maxWidth: 480, width: "90%", boxShadow: "0 20px 60px rgba(0,0,0,0.5)", animation: "modalIn 0.2s ease-out" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <div style={{ width: 40, height: 40, borderRadius: 12, background: "rgba(239,68,68,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}><AlertCircle size={20} color="#f87171" /></div>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: "white" }}>Đã xảy ra lỗi</h3>
        </div>
        <p style={{ color: "#e5e7eb", fontSize: 15, marginBottom: 8, lineHeight: 1.5 }}>{state.message}</p>
        {state.suggestion && (
          <div style={{ background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.2)", borderRadius: 10, padding: "10px 14px", marginBottom: 16 }}><p style={{ color: "#fbbf24", fontSize: 14, margin: 0 }}>💡 {state.suggestion}</p></div>
        )}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          {state.retryPossible && (
            <button onClick={() => { onRetry(state.videoId); onClose(); }} style={{ padding: "10px 20px", background: "linear-gradient(135deg,#7c3aed,#4f46e5)", border: "none", borderRadius: 10, color: "white", fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, transition: "transform 0.1s, box-shadow 0.2s" }} onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 4px 20px rgba(124,58,237,0.4)"; }} onMouseLeave={(e) => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "none"; }}><RefreshCw size={16} /> Thử lại</button>
          )}
          <button onClick={onClose} style={{ padding: "10px 20px", background: "#1e1e2a", border: "1px solid #2a2a38", borderRadius: 10, color: "#9ca3af", fontWeight: 600, cursor: "pointer", transition: "background 0.2s" }} onMouseEnter={(e) => e.currentTarget.style.background = "#2a2a3a"} onMouseLeave={(e) => e.currentTarget.style.background = "#1e1e2a"}>Đóng</button>
        </div>
        {state.technical && (
          <details style={{ marginTop: 16, borderTop: "1px solid #2a2a38", paddingTop: 12 }}>
            <summary style={{ fontSize: 12, color: "#4b5563", cursor: "pointer", display: "flex", alignItems: "center", gap: 4, listStyle: "none" }}><ChevronDown size={12} style={{ transition: "transform 0.2s" }} /> Chi tiết kỹ thuật</summary>
            <pre style={{ fontSize: 11, color: "#6b7280", background: "#0c0c10", borderRadius: 8, padding: 10, marginTop: 8, overflowX: "auto", whiteSpace: "pre-wrap", border: "1px solid #1e1e2a" }}>{state.technical}</pre>
          </details>
        )}
      </div>
    </div>
  );
});

// ✅ FIXED: Stage Indicator chuẩn xác
const StageIndicator = React.memo(({ currentStage, progress }: { currentStage: ProgressEvent["stage"] | null; progress: number }) => {
  const stages: ProgressEvent["stage"][] = ["init", "audio", "stt", "ai", "cut", "crop", "render", "complete"];
  const currentIdx = currentStage ? stages.indexOf(currentStage) : -1;
  const isComplete = currentStage === "complete";

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, position: "relative" }}>
        <div style={{ position: "absolute", top: "50%", left: 14, right: 14, height: 2, background: "#1e1e2a", transform: "translateY(-50%)", borderRadius: 1, zIndex: 0 }} />
        <div style={{ position: "absolute", top: "50%", left: 14, height: 2, background: "linear-gradient(90deg, #7c3aed, #22c55e)", transform: "translateY(-50%)", borderRadius: 1, zIndex: 0, width: currentIdx >= 0 ? `${Math.min(100, (currentIdx / (stages.length - 1)) * 100)}%` : "0%", transition: "width 0.5s ease" }} />
        {stages.map((stage, index) => {
          const info = STAGE_INFO[stage];
          const StageIcon = info.icon;
          const isActive = index === currentIdx && !isComplete;
          const isDone = index < currentIdx || isComplete;
          return (
            <div key={stage} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flex: 1, position: "relative", zIndex: 1 }}>
              <div style={{ width: 28, height: 28, borderRadius: 8, background: isDone ? info.color : isActive ? `${info.color}20` : "#1e1e2a", border: `1.5px solid ${isActive || isDone ? info.color : "#2a2a38"}`, display: "flex", alignItems: "center", justifyContent: "center", color: isDone || isActive ? "white" : "#4b5563", transition: "all 0.3s ease", boxShadow: isActive ? `0 0 12px ${info.color}40` : "none" }}>
                {isDone ? <CheckCircle2 size={14} /> : <StageIcon size={14} />}
              </div>
              <span style={{ fontSize: 9, color: isActive ? "white" : "#4b5563", textAlign: "center", fontWeight: isActive ? 600 : 400 }}>{info.label}</span>
            </div>
          );
        })}
      </div>
      <div style={{ textAlign: "center", marginTop: 8 }}>
        <span style={{ fontSize: 12, color: "#6b7280" }}>{currentStage ? STAGE_INFO[currentStage].label : "Chờ xử lý"} • {progress}%</span>
      </div>
    </div>
  );
});

// ==============================================================================
// STUB COMPONENTS (Replace with actual implementation)
// ==============================================================================

function LicenseActivationScreen({ onActivated }: { onActivated: (info: LicenseInfo) => void }) {
  const [key, setKey] = useState("");
  const [loading, setLoading] = useState(false);

  const handleActivate = async () => {
    if (!key.trim()) return;
    setLoading(true);
    try {
      // ✅ GỌI THẲNG VÀO HÀM RUST CỦA BẠN (license.rs)
      const realInfo = await invoke<LicenseInfo>("activate_license", { key: key.trim() });
      
      // Nếu Rust báo thành công, đẩy data thật vào App
      onActivated(realInfo); 
    } catch (err) {
      // Nếu Rust hoặc Supabase báo lỗi (sai key, hết hạn...), hiện thông báo
      alert("❌ Lỗi kích hoạt: " + err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ 
      display: "flex", 
      alignItems: "center", 
      justifyContent: "center", 
      height: "100vh", 
      background: "#0c0c10",
      color: "#dde1f0",
      fontFamily: "'Segoe UI', system-ui, sans-serif"
    }}>
      <div style={{ 
        background: "#16161e", 
        border: "1px solid #2a2a38", 
        borderRadius: 20, 
        padding: 32, 
        maxWidth: 420, 
        width: "90%",
        textAlign: "center"
      }}>
        <Sparkles size={48} color="#a78bfa" style={{ marginBottom: 16 }} />
        <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>🔐 Kích hoạt License</h2>
        <p style={{ color: "#6b7280", fontSize: 14, marginBottom: 20 }}>
          Nhập license key để bắt đầu sử dụng
        </p>
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Nhập license key..."
          style={{ ...IS, marginBottom: 16, textAlign: "center" }}
          onKeyDown={(e) => e.key === "Enter" && handleActivate()}
        />
        <button
          onClick={handleActivate}
          disabled={loading || !key.trim()}
          style={{
            width: "100%",
            padding: "12px",
            background: loading || !key.trim() ? "#1a1a26" : "linear-gradient(135deg,#7c3aed,#4f46e5)",
            border: "none",
            borderRadius: 10,
            color: "white",
            fontWeight: 600,
            cursor: loading || !key.trim() ? "not-allowed" : "pointer",
            transition: "opacity 0.2s"
          }}
        >
          {loading ? "Đang xác thực..." : "Kích hoạt"}
        </button>
      </div>
    </div>
  );
}

function LicenseBadge({ info, onDeactivate }: { info: LicenseInfo; onDeactivate: () => void }) {
  const plan = PLAN_COLORS[info.plan] || PLAN_COLORS.starter;
  
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ 
        display: "flex", 
        alignItems: "center", 
        gap: 8, 
        padding: "6px 12px", 
        background: plan.bg, 
        border: `1px solid ${plan.color}40`, 
        borderRadius: 10 
      }}>
        <ShieldCheck size={14} color={plan.color} />
        <span style={{ fontSize: 12, fontWeight: 600, color: plan.color }}>{plan.label}</span>
        {info.plan !== "unlimited" && (
          <span style={{ fontSize: 11, color: "#6b7280" }}>
            {info.quota_remain}/{info.quota_limit}
          </span>
        )}
      </div>
      <button 
        onClick={onDeactivate}
        title="Đăng xuất"
        style={{
          background: "none",
          border: "none", 
          color: "#4b5563",
          cursor: "pointer",
          padding: 4,
          display: "flex",
          alignItems: "center",
          transition: "color 0.2s"
        }}
        onMouseEnter={(e) => e.currentTarget.style.color = "#f87171"}
        onMouseLeave={(e) => e.currentTarget.style.color = "#4b5563"}
      >
        <LogOut size={16} />
      </button>
    </div>
  );
}

// ==============================================================================
// MAIN APP COMPONENT (OPTIMIZED)
// ==============================================================================
export default function App() {
  const [activeTab, setActiveTab] = useState<"workspace" | "settings">("workspace");
  const [licenseInfo, setLicenseInfo] = useState<LicenseInfo | null>(null);
  const [licenseLoading, setLicenseLoading] = useState(true);

  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState("Sẵn sàng chờ lệnh");
  const [logs, setLogs] = useState<string[]>([]);
  const [videoQueue, setVideoQueue] = useState<VideoItem[]>([]);
  
  const [mode, setMode] = useState<"full" | "no-crop">("full");
  const currentVideoId = useRef<string | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const startTimeRef = useRef<number | null>(null);
  const unlistenRef = useRef<UnlistenFn | null>(null);

  const [config, setConfig] = useState<ConfigState>({
    gemini_api_key: "", lang_code: "vi", whisper_model: "medium", whisper_device: "cuda", whisper_compute_type: "float16",
    min_duration: 150, max_duration: 300, sharpen_strength: "medium", title_color: "#FFD700", sub_bg_color: "255, 0, 0, 160",
    max_words_per_line: 3, sub_margin_v: 250, sub_font_size: 85, video_speed: 1.03, font_title_file: "C:/Windows/Fonts/arialbd.ttf", gemini_model: "gemini-2.5-flash",
  });

  // UX States
  const [currentStage, setCurrentStage] = useState<ProgressEvent["stage"] | null>(null);
  const [errorModal, setErrorModal] = useState<ErrorModalState>({ visible: false, message: "", retryPossible: false });
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedVideos, setSelectedVideos] = useState<Set<string>>(new Set());
  const [configExpanded, setConfigExpanded] = useState({ ai: true, stt: true, subtitle: true });
  const [terminalExpanded, setTerminalExpanded] = useState(true);

  // 🔥 Optimized Toast System
  const addToast = useCallback((type: Toast["type"], message: string, duration = 4000) => {
    const id = crypto.randomUUID();
    setToasts(prev => {
      const updated = [...prev, { id, type, message, duration }];
      return updated.slice(-5); // Max 5 toasts
    });
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
  }, []);

  // 🔥 Debounce Progress Updates
  const progressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const debouncedSetProgress = useCallback((value: number) => {
    if (progressTimerRef.current) clearTimeout(progressTimerRef.current);
    progressTimerRef.current = setTimeout(() => setProgress(value), 100);
  }, []);

  // 🔥 License Init
  useEffect(() => {
    invoke<LicenseInfo | null>("load_license")
      .then(info => { setLicenseInfo(info); if (info) addToast("success", "✅ License đã được kích hoạt"); })
      .catch(() => setLicenseInfo(null))
      .finally(() => setLicenseLoading(false));
  }, [addToast]);

  // 🔥 AI Progress Listener (Optimized)
  useEffect(() => {
    const setupListener = async () => {
      try {
        unlistenRef.current = await listen<string>("ai-progress", (event) => {
          try {
            const data = JSON.parse(event.payload);
            setStatusMsg(data.msg);
            setCurrentStage(data.stage);
            debouncedSetProgress(data.pct);

            // Log management (limit 50 lines)
            setLogs(prev => {
              const newLog = `[${new Date().toLocaleTimeString()}] ${data.msg}`;
              const updated = [...prev, newLog];
              return updated.slice(-50);
            });
            setTimeout(() => logsEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50);

            if (data.meta?.action === "open_folder" && data.meta?.path) {
              setTimeout(() => invoke('open_folder', { folderPath: data.meta!.path }).catch(() => {}), 1000);
            }

            if (data.stage === "complete" && data.status === "ok") {
              setIsRunning(false);
              if (currentVideoId.current) {
                const targetId = currentVideoId.current;
                setVideoQueue(prev => prev.map(v => v.id === targetId ? { ...v, status: "done", progress: 100 } : v));
                currentVideoId.current = null;
              }
              invoke<LicenseInfo | null>("load_license").then(i => setLicenseInfo(i)).catch(() => {});
              addToast("success", "✅ Xử lý hoàn tất!");
            } else if (data.status === "err") {
              setIsRunning(false);
              if (currentVideoId.current) {
                const targetId = currentVideoId.current;
                setVideoQueue(prev => prev.map(v => v.id === targetId ? { ...v, status: "error", error: data.msg } : v));
                currentVideoId.current = null;
              }
              setErrorModal({ visible: true, message: data.msg, suggestion: data.meta?.suggestion, retryPossible: data.meta?.retry_possible ?? true, videoId: currentVideoId.current || undefined, technical: data.meta?.technical });
              addToast("error", data.msg);
            } else if (data.status === "warn") {
              addToast("warning", data.msg);
            }
          } catch (e) { console.error("Parse error:", e); }
        });
      } catch (err) { console.error("Setup listener error:", err); }
    };
    setupListener();
    return () => { if (unlistenRef.current) unlistenRef.current(); };
  }, [addToast, debouncedSetProgress]);

  // 🔥 Auto-scroll terminal
  useEffect(() => { if (terminalExpanded) logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs, terminalExpanded]);

  // 🔥 Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !isRunning) { e.preventDefault(); handleRunPipeline(); }
      if ((e.ctrlKey || e.metaKey) && e.key === "r" && errorModal.retryPossible) { e.preventDefault(); handleRetryError(); }
      if (e.key === "Escape") setErrorModal(prev => ({ ...prev, visible: false }));
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isRunning, errorModal]);

  // 🔥 Memoized Calculations
  const filteredQueue = useMemo(() => videoQueue.filter(v => v.name.toLowerCase().includes(searchQuery.toLowerCase()) || v.dir.toLowerCase().includes(searchQuery.toLowerCase())), [videoQueue, searchQuery]);
  const queueStats = useMemo(() => ({
    pending: videoQueue.filter(v => v.status === "pending").length,
    processing: videoQueue.filter(v => v.status === "processing").length,
    done: videoQueue.filter(v => v.status === "done" || v.status === "error").length,
  }), [videoQueue]);

  // 🔥 Handlers (useCallback)
  const toggleSelect = useCallback((id: string) => setSelectedVideos(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; }), []);
  const clearSelection = useCallback(() => setSelectedVideos(new Set()), []);
  const bulkRemove = useCallback(() => { setVideoQueue(prev => prev.filter(v => !selectedVideos.has(v.id))); clearSelection(); addToast("info", `Đã xoá ${selectedVideos.size} video`); }, [selectedVideos, clearSelection, addToast]);
  const clearDone = useCallback(() => { const c = videoQueue.filter(v => v.status === "done" || v.status === "error").length; setVideoQueue(prev => prev.filter(v => v.status !== "done" && v.status !== "error")); addToast("info", `Đã xoá ${c} video hoàn thành`); }, [videoQueue, addToast]);
  
  const handleRetryError = useCallback(async () => {
    if (!errorModal.videoId) return;
    const video = videoQueue.find(v => v.id === errorModal.videoId);
    if (!video) return;
    setVideoQueue(prev => prev.map(v => v.id === video.id ? { ...v, status: "pending", error: undefined } : v));
    setErrorModal(prev => ({ ...prev, visible: false }));
    addToast("info", "Đã reset video");
    if (videoQueue.filter(v => v.status === "pending").length === 1 && !isRunning) setTimeout(handleRunPipeline, 500);
  }, [errorModal, videoQueue, isRunning, addToast]);

  const handleAddFiles = useCallback(async () => {
    try {
      const selected = await open({ multiple: true, filters: [{ name: "Video", extensions: ["mp4","mov","avi","mkv","webm"] }] });
      if (!selected) return;
      const paths = Array.isArray(selected) ? selected : [selected];
      setVideoQueue(prev => [...prev, ...paths.map(p => ({ 
  id: crypto.randomUUID(), 
  path: p, 
  name: fileName(p), 
  dir: fileDir(p), 
  status: "pending" as VideoStatus,  // 👈 Thêm cast
  addedAt: Date.now() 
}))]);
      addToast("success", `Đã thêm ${paths.length} tệp`);
    } catch { addToast("error", "Không thể thêm file"); }
  }, [addToast]);

  const handleAddFolder = useCallback(async () => {
    try {
      const selected = await open({ directory: true });
      if (!selected || typeof selected !== "string") return;
      addToast("info", "Đang quét video...");
      const files = await invoke<string[]>("scan_directory", { path: selected });
      if (files.length === 0) { addToast("warning", "Không tìm thấy video"); return; }
      setVideoQueue(prev => [...prev, ...files.map(p => ({ 
  id: crypto.randomUUID(), 
  path: p, 
  name: fileName(p), 
  dir: fileDir(p), 
  status: "pending" as VideoStatus,  // 👈 Thêm cast
  addedAt: Date.now() 
}))]);
      addToast("success", `Đã thêm ${files.length} video`);
    } catch { addToast("error", "Không thể quét thư mục"); }
  }, [addToast]);

  const moveItem = useCallback((idx: number, dir: -1 | 1) => {
    setVideoQueue(prev => { const n = [...prev]; const s = idx + dir; if (s < 0 || s >= n.length) return prev; [n[idx], n[s]] = [n[s], n[idx]]; return n; });
  }, []);

  const removeItem = useCallback((id: string) => {
    setVideoQueue(prev => prev.filter(v => v.id !== id));
    setSelectedVideos(prev => { const n = new Set(prev); n.delete(id); return n; });
  }, []);

  const handleRunPipeline = useCallback(async () => {
    const pending = videoQueue.find(v => v.status === "pending");
    if (isRunning || !pending) return;
    if (!licenseInfo || licenseInfo.quota_remain <= 0) { addToast("error", "❌ Hết quota!"); return; }
    
    setIsRunning(true); setProgress(0); setCurrentStage("init"); startTimeRef.current = Date.now();
    currentVideoId.current = pending.id;
    setVideoQueue(prev => prev.map(v => v.id === pending.id ? { ...v, status: "processing", progress: 0 } : v));
    setLogs([`[System] Đang xác thực license...`]);
    addToast("info", `Bắt đầu xử lý: ${pending.name}`);

    try {
      const token = await invoke<string>("create_render_token");
      setLogs(prev => [...prev, "[System] ✅ Token hợp lệ..."]);
      await invoke("start_pipeline", { mode, videoPath: pending.path, configObj: JSON.stringify(config), sessionToken: token });
      if (licenseInfo?.plan !== "unlimited") setLicenseInfo(prev => prev ? { ...prev, quota_used: prev.quota_used + 1, quota_remain: prev.quota_remain - 1 } : prev);
    } catch (e: any) {
      const msg = typeof e === "string" ? e : "Lỗi không xác định";
      setLogs(prev => [...prev, `[Error] ❌ ${msg}`]);
      setIsRunning(false);
      if (currentVideoId.current) { setVideoQueue(prev => prev.map(v => v.id === currentVideoId.current ? { ...v, status: "error", error: msg } : v)); currentVideoId.current = null; }
      addToast("error", msg);
    }
  }, [isRunning, videoQueue, licenseInfo, mode, config, addToast]);

  const handleOpenOriginal = useCallback((path: string) => invoke("open_external", { path }).catch(() => addToast("error", "Không thể mở video gốc")), [addToast]);
  const handleOpenOutput = useCallback(async (path: string) => {
    try {
      const name = fileName(path).replace(/\.[^/.]+$/, "");
      const ws = await invoke<string>("get_workspace_path", { videoName: name }).catch(() => null);
      if (ws) await invoke("open_folder", { folderPath: `${ws}/final` }); else await invoke("open_output", { originalPath: path });
    } catch { addToast("error", "Không thể mở thư mục"); }
  }, [addToast]);

  const handleDeactivate = useCallback(async () => {
    if (!confirm("Đăng xuất license?")) return;
    await invoke("deactivate_license"); setLicenseInfo(null); addToast("info", "Đã đăng xuất");
  }, [addToast]);

  if (licenseLoading) return <div style={{ background: "#0c0c10", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}><div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}><Spin size={38} color="#7c3aed" /><p style={{ color: "#6b7280" }}>Đang kiểm tra license...</p></div></div>;
  if (!licenseInfo) return <LicenseActivationScreen onActivated={setLicenseInfo} />;

  return (
    <div style={{ display: "flex", height: "100vh", background: "linear-gradient(135deg, #0c0c10 0%, #111118 100%)", color: "#dde1f0", fontFamily: "'Segoe UI', system-ui, sans-serif", overflow: "hidden" }}>
      <style>{`@keyframes _spin{to{transform:rotate(360deg)}} @keyframes _pulse{0%,100%{opacity:1}50%{opacity:0.35}} @keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}} @keyframes modalIn{from{transform:scale(0.95);opacity:0}to{transform:scale(1);opacity:1}} ::-webkit-scrollbar{width:6px;height:6px} ::-webkit-scrollbar-track{background:#111118} ::-webkit-scrollbar-thumb{background:#2a2a3a;border-radius:3px} *{box-sizing:border-box;margin:0;padding:0;outline:none} select option{background:#16161e;color:white} input[type=number]::-webkit-inner-spin-button{opacity:0.4} details summary::-webkit-details-marker{display:none} input:focus,select:focus{border-color:#7c3aed!important}`}</style>

      <aside style={{ width: 72, background: "#111118", borderRight: "1px solid #1e1e2a", display: "flex", flexDirection: "column", alignItems: "center", padding: "20px 0", gap: 8, flexShrink: 0 }}>
        <div style={{ width: 44, height: 44, borderRadius: 14, background: "linear-gradient(135deg,#7c3aed,#4f46e5)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 20px rgba(124,58,237,0.4)", marginBottom: 14 }}><Sparkles size={22} color="white" /></div>
        {[{ id: "workspace", icon: <Play size={22} />, tip: "Studio" }, { id: "settings", icon: <Settings size={22} />, tip: "Cài đặt" }].map(({ id, icon, tip }) => (
          <button key={id} onClick={() => setActiveTab(id as any)} title={tip} style={{ width: 48, height: 48, borderRadius: 14, border: "none", cursor: "pointer", background: activeTab === id ? "rgba(124,58,237,0.15)" : "transparent", color: activeTab === id ? "#a78bfa" : "#4b5563", display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s" }}>{icon}</button>
        ))}
      </aside>

      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        <header style={{ height: 58, borderBottom: "1px solid #1e1e2a", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 24px", background: "#111118", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 18, fontWeight: 700, color: "white" }}>{activeTab === "workspace" ? "🎬 Studio" : "⚙️ Cài đặt"}</span>
            {activeTab === "workspace" && videoQueue.length > 0 && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <Chip color="#6b7280">{queueStats.pending} chờ</Chip>
                {queueStats.processing > 0 && <Chip color="#fbbf24">{queueStats.processing} xử lý</Chip>}
                {queueStats.done > 0 && <Chip color="#4ade80">{queueStats.done} xong</Chip>}
              </div>
            )}
          </div>
          <LicenseBadge info={licenseInfo} onDeactivate={handleDeactivate} />
        </header>

        {activeTab === "workspace" && (
          <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
            {/* Config Panel */}
            <div style={{ width: 460, background: "#111118", borderRight: "1px solid #1e1e2a", padding: 20, overflowY: "auto", flexShrink: 0, display: "flex", flexDirection: "column", gap: 16 }}>
              <CollapsibleSection title="Trí tuệ AI" icon={<Cpu size={15} />} color="#a78bfa" expanded={configExpanded.ai} onToggle={() => setConfigExpanded(p => ({ ...p, ai: !p.ai }))}>
                <Field label="Gemini API Key"><input type="password" value={config.gemini_api_key} onChange={e => setConfig({ ...config, gemini_api_key: e.target.value })} style={IS} placeholder="AIzaSy..." /></Field>
                <Field label="Model"><select value={config.gemini_model} onChange={e => setConfig({ ...config, gemini_model: e.target.value })} style={IS}><option value="gemini-2.5-flash">Gemini 2.5 Flash</option><option value="gemini-2.0-flash">Gemini 2.0 Flash</option><option value="gemini-1.5-pro">Gemini 1.5 Pro</option></select></Field>
                <div style={{ display: "flex", gap: 10 }}><Field label="Min (s)" style={{ flex: 1 }}><input type="number" min="30" max="600" value={config.min_duration} onChange={e => setConfig({ ...config, min_duration: Number(e.target.value) })} style={IS} /></Field><Field label="Max (s)" style={{ flex: 1 }}><input type="number" min="60" max="1800" value={config.max_duration} onChange={e => setConfig({ ...config, max_duration: Number(e.target.value) })} style={IS} /></Field></div>
              </CollapsibleSection>
              <CollapsibleSection title="Âm thanh & STT" icon={<Scissors size={15} />} color="#4ade80" expanded={configExpanded.stt} onToggle={() => setConfigExpanded(p => ({ ...p, stt: !p.stt }))}>
                <div style={{ display: "flex", gap: 10 }}><Field label="Ngôn ngữ" style={{ width: 80 }}><input type="text" value={config.lang_code} onChange={e => setConfig({ ...config, lang_code: e.target.value })} style={{ ...IS, width: "100%" }} placeholder="vi" /></Field><Field label="Model" style={{ flex: 1 }}><select value={config.whisper_model} onChange={e => setConfig({ ...config, whisper_model: e.target.value })} style={IS}><option value="tiny">Tiny</option><option value="base">Base</option><option value="small">Small</option><option value="medium">Medium</option><option value="large-v3">Large v3</option></select></Field></div>
                <div style={{ display: "flex", gap: 10 }}><Field label="Device" style={{ flex: 1 }}><select value={config.whisper_device} onChange={e => setConfig({ ...config, whisper_device: e.target.value })} style={IS}><option value="cuda">CUDA (GPU)</option><option value="cpu">CPU</option></select></Field><Field label="Precision" style={{ flex: 1 }}><select value={config.whisper_compute_type} onChange={e => setConfig({ ...config, whisper_compute_type: e.target.value })} style={IS}><option value="float16">float16</option><option value="int8">int8</option><option value="float32">float32</option></select></Field></div>
                <Field label="Sharpen"><select value={config.sharpen_strength} onChange={e => setConfig({ ...config, sharpen_strength: e.target.value })} style={IS}><option value="low">Thấp</option><option value="medium">Trung bình</option><option value="high">Cao</option></select></Field>
              </CollapsibleSection>
              <CollapsibleSection title="Phụ đề & Đồ hoạ" icon={<Type size={15} />} color="#fbbf24" expanded={configExpanded.subtitle} onToggle={() => setConfigExpanded(p => ({ ...p, subtitle: !p.subtitle }))}>
                <Field label="Màu tiêu đề"><div style={{ display: "flex", gap: 8 }}><input type="color" value={config.title_color} onChange={e => setConfig({ ...config, title_color: e.target.value })} style={{ width: 40, height: 38, border: "1.5px solid #1e1e2a", borderRadius: 8, cursor: "pointer" }} /><input value={config.title_color} onChange={e => setConfig({ ...config, title_color: e.target.value })} style={{ ...IS, flex: 1, fontFamily: "monospace" }} /></div></Field>
                <Field label="Màu nền sub"><input value={config.sub_bg_color} onChange={e => setConfig({ ...config, sub_bg_color: e.target.value })} style={{ ...IS, fontFamily: "monospace" }} placeholder="255, 0, 0, 160" /></Field>
                <div style={{ display: "flex", gap: 10 }}><Field label="Cỡ chữ" style={{ flex: 1 }}><input type="number" min="20" max="200" value={config.sub_font_size} onChange={e => setConfig({ ...config, sub_font_size: Number(e.target.value) })} style={IS} /></Field><Field label="Từ/dòng" style={{ flex: 1 }}><input type="number" min="1" max="10" value={config.max_words_per_line} onChange={e => setConfig({ ...config, max_words_per_line: Number(e.target.value) })} style={IS} /></Field><Field label="Margin V" style={{ flex: 1 }}><input type="number" min="50" max="500" value={config.sub_margin_v} onChange={e => setConfig({ ...config, sub_margin_v: Number(e.target.value) })} style={IS} /></Field></div>
                <Field label="Font"><input type="text" value={config.font_title_file} onChange={e => setConfig({ ...config, font_title_file: e.target.value })} style={{ ...IS, fontFamily: "monospace" }} placeholder="C:/Windows/Fonts/arialbd.ttf" /></Field>
                <Field label="Tốc độ"><input type="number" step="0.01" min="0.5" max="2.0" value={config.video_speed} onChange={e => setConfig({ ...config, video_speed: Number(e.target.value) })} style={IS} /></Field>
              </CollapsibleSection>
            </div>

            {/* Right Panel */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", padding: 20, gap: 14, overflow: "hidden", minWidth: 0 }}>
              <div style={{ flexShrink: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: "white" }}>📋 Hàng đợi Video</span>
                  <div style={{ display: "flex", gap: 7 }}>
                    <div style={{ position: "relative" }}>
                      <Search size={14} color="#4b5563" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }} />
                      <input type="text" placeholder="Tìm video..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} style={{ ...IS, width: 150, padding: "6px 10px 6px 30px", fontSize: 13 }} />
                      {searchQuery && <button onClick={() => setSearchQuery("")} style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "#4b5563", cursor: "pointer" }}><X size={12} /></button>}
                    </div>
                    {selectedVideos.size > 0 ? (<><GhostBtn onClick={bulkRemove} icon={<Trash2 size={13} />}>Xoá ({selectedVideos.size})</GhostBtn><GhostBtn onClick={clearSelection} icon={<X size={13} />}>Bỏ chọn</GhostBtn></>) : (<><GhostBtn onClick={clearDone} icon={<Trash2 size={13} />} active={false}>Xoá xong</GhostBtn><GhostBtn onClick={handleAddFiles} icon={<FileVideo size={13} />}>+ File</GhostBtn><GhostBtn onClick={handleAddFolder} icon={<FolderPlus size={13} />}>+ Thư mục</GhostBtn></>)}
                  </div>
                </div>
                
                <div style={{ background: "#111118", border: "1px solid #1e1e2a", borderRadius: 16, minHeight: 120, maxHeight: 230, overflowY: "auto" }}>
                  {filteredQueue.length === 0 ? (
                    <div style={{ height: 110, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#374151" }}><FolderOpen size={30} style={{ marginBottom: 8, opacity: 0.3 }} /><span>{searchQuery ? "Không tìm thấy" : "Chưa có video"}</span></div>
                  ) : (
                    <div style={{ padding: 8, display: "flex", flexDirection: "column", gap: 5 }}>
                      {filteredQueue.map((item) => {
                        const originalIdx = videoQueue.findIndex(v => v.id === item.id);
                        const isSelected = selectedVideos.has(item.id);
                        return (
                          <div key={item.id} style={{ display: "flex", alignItems: "center", gap: 10, background: isSelected ? "rgba(124,58,237,0.08)" : item.status === "processing" ? "rgba(251,191,36,0.04)" : "#16161e", border: `1px solid ${isSelected ? "#7c3aed" : item.status === "processing" ? "rgba(251,191,36,0.2)" : item.status === "done" ? "rgba(74,222,128,0.12)" : item.status === "error" ? "rgba(248,113,113,0.12)" : "#1e1e2a"}`, borderRadius: 10, padding: "9px 12px", transition: "all 0.2s" }}>
                            {item.status === "pending" && <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(item.id)} style={{ width: 16, height: 16, cursor: "pointer", accentColor: "#7c3aed" }} />}
                            <div style={{ background: "rgba(124,58,237,0.12)", borderRadius: 8, padding: "7px 8px", flexShrink: 0 }}><FileVideo size={15} color="#a78bfa" /></div>
                            <div style={{ flex: 1, overflow: "hidden" }}>
                              <p style={{ fontSize: 14, fontWeight: 600, color: "#e5e7eb", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</p>
                              <p style={{ fontSize: 11, color: "#4b5563", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.dir}</p>
                              {item.status === "error" && item.error && <p style={{ fontSize: 11, color: "#f87171", marginTop: 2 }}>{item.error.length > 40 ? item.error.slice(0, 40) + "..." : item.error}</p>}
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
                              <StatusBadge status={item.status} />
                              {item.status === "processing" && item.progress !== undefined && <span style={{ fontSize: 10, color: "#fbbf24", fontWeight: 600 }}>{item.progress}%</span>}
                            </div>
                            <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                              <SmallBtn onClick={() => moveItem(originalIdx, -1)} disabled={originalIdx === 0 || item.status !== "pending"} title="Lên"><ArrowUp size={13} /></SmallBtn>
                              <SmallBtn onClick={() => moveItem(originalIdx, 1)} disabled={originalIdx === videoQueue.length - 1 || item.status !== "pending"} title="Xuống"><ArrowDown size={13} /></SmallBtn>
                              <SmallBtn onClick={() => handleOpenOriginal(item.path)} title="Mở gốc"><Eye size={13} /></SmallBtn>
                              {item.status === "done" && <SmallBtn onClick={() => handleOpenOutput(item.path)} title="Mở kết quả"><Film size={13} color="#4ade80" /></SmallBtn>}
                              <SmallBtn onClick={() => removeItem(item.id)} disabled={item.status === "processing"} title="Xoá" danger><X size={13} /></SmallBtn>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: "flex", gap: 14, flexShrink: 0 }}>
                <div style={{ width: 180, background: "#111118", border: "1px solid #1e1e2a", borderRadius: 16, padding: 14, flexShrink: 0 }}>
                  <p style={{ fontSize: 11, color: "#4b5563", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>🎬 Chế độ</p>
                  {[{ val: "full" as const, label: "Smart Shorts 9:16", desc: "🤖 AI tracking" }, { val: "no-crop" as const, label: "Normal Short 9:16", desc: "✂️ Cắt 1:1" }].map(m => (
                    <button key={m.val} onClick={() => setMode(m.val)} style={{ width: "100%", padding: "8px 10px", marginBottom: 6, borderRadius: 10, border: mode === m.val ? "1.5px solid #7c3aed" : "1.5px solid #1e1e2a", background: mode === m.val ? "rgba(124,58,237,0.1)" : "transparent", cursor: "pointer", textAlign: "left" }}>
                      <p style={{ fontSize: 12, fontWeight: 600, color: mode === m.val ? "#a78bfa" : "#9ca3af" }}>{m.label}</p>
                      <p style={{ fontSize: 10, color: "#4b5563", marginTop: 2 }}>{m.desc}</p>
                    </button>
                  ))}
                </div>
                
                <div style={{ flex: 1, background: "#111118", border: "1px solid #1e1e2a", borderRadius: 16, padding: 16, display: "flex", flexDirection: "column", gap: 10, justifyContent: "space-between" }}>
                  <div>
                    <StageIndicator currentStage={currentStage} progress={progress} />
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 13, color: "#6b7280" }}>{currentStage ? STAGE_INFO[currentStage].label : "Trạng thái"}: <span style={{ color: "#a78bfa", fontWeight: 600 }}>{statusMsg}</span></span>
                      <span style={{ fontSize: 20, fontWeight: 800, color: "white" }}>{progress}%</span>
                    </div>
                    {isRunning && startTimeRef.current && progress > 0 && <p style={{ fontSize: 11, color: "#4b5563", marginTop: 4 }}>⏱️ Còn: {formatETA(Math.max(0, (Date.now() - startTimeRef.current) * (100 / progress - 1) / 1000))}</p>}
                    {licenseInfo.plan !== "unlimited" && <p style={{ fontSize: 11, color: "#4b5563", textAlign: "right", marginTop: 4 }}>🔋 Còn {licenseInfo.quota_remain} quota</p>}
                  </div>
                  <button onClick={handleRunPipeline} disabled={isRunning || queueStats.pending === 0 || licenseInfo.quota_remain <= 0} title="Ctrl + Enter" style={{ width: "100%", padding: "12px 0", background: (!isRunning && queueStats.pending > 0 && licenseInfo.quota_remain > 0) ? "linear-gradient(135deg,#7c3aed,#4f46e5)" : "#1a1a26", border: (!isRunning && queueStats.pending > 0 && licenseInfo.quota_remain > 0) ? "none" : "1px solid #2a2a38", borderRadius: 10, color: (!isRunning && queueStats.pending > 0 && licenseInfo.quota_remain > 0) ? "white" : "#4b5563", fontWeight: 700, fontSize: 14, cursor: (isRunning || queueStats.pending === 0 || licenseInfo.quota_remain <= 0) ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                    {isRunning ? <><Spin size={16} color="#a78bfa" /> Đang xử lý...</> : licenseInfo.quota_remain <= 0 ? "❌ Hết Quota" : queueStats.pending === 0 ? "Không có video" : <><Play size={14} fill="white" color="white" /> Bắt đầu ({queueStats.pending})</>}
                  </button>
                </div>
              </div>

              {/* ✅ FIXED: Terminal Optimized */}
              <div style={{ flex: 1, background: "#080810", border: "1px solid #1a1a26", borderRadius: 16, padding: 14, display: "flex", flexDirection: "column", overflow: "hidden", minHeight: 100 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <HardDrive size={12} color="#4b5563" />
                  <span style={{ fontSize: 10, color: "#374151", textTransform: "uppercase", fontWeight: 700 }}>📝 Terminal</span>
                  {isRunning && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#4ade80", animation: "_pulse 1s ease-in-out infinite", marginLeft: "auto" }} />}
                  <button onClick={() => setTerminalExpanded(p => !p)} style={{ marginLeft: "auto", background: "none", border: "none", color: "#4b5563", cursor: "pointer", fontSize: 10, display: "flex", alignItems: "center", gap: 4 }}>{terminalExpanded ? <Minimize2 size={10} /> : <Maximize2 size={10} />} {terminalExpanded ? "Thu" : "Mở"}</button>
                  <button onClick={() => setLogs([])} style={{ background: "none", border: "none", color: "#4b5563", cursor: "pointer", fontSize: 10 }}>Xoá</button>
                </div>
                <div style={{ flex: terminalExpanded ? 1 : "none", overflowY: "auto", fontFamily: "Consolas, Monaco, monospace", fontSize: 11, lineHeight: 1.5, display: "flex", flexDirection: "column", gap: 1, maxHeight: terminalExpanded ? "none" : "80px", transition: "max-height 0.3s" }}>
                  {logs.length === 0 ? <span style={{ color: "#374151", fontStyle: "italic" }}>Đang chờ lệnh...</span> : logs.map((log, i) => <div key={i} style={{ color: getLogColor(log), whiteSpace: "pre-wrap", wordBreak: "break-word", padding: "1px 0" }}>{log}</div>)}
                  <div ref={logsEndRef} />
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "settings" && (
          <div style={{ flex: 1, padding: 32, overflowY: "auto" }}>
            <h2 style={{ fontSize: 22, fontWeight: 800, color: "white", marginBottom: 24 }}>⚙️ Cài đặt</h2>
            <div style={{ maxWidth: 520, display: "flex", flexDirection: "column", gap: 20 }}>
              <CollapsibleSection title="License" icon={<Key size={15} />} color="#a78bfa" expanded={true} onToggle={() => {}}>
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {[{ label: "Gói hiện tại", value: PLAN_COLORS[licenseInfo.plan]?.label || licenseInfo.plan, color: PLAN_COLORS[licenseInfo.plan]?.color || "#a78bfa" }, { label: "Quota đã dùng", value: licenseInfo.plan === "unlimited" ? "Không giới hạn ♾️" : `${licenseInfo.quota_used} / ${licenseInfo.quota_limit}`, color: "white" }, { label: "Hết hạn", value: formatExpiry(licenseInfo.expires_at), color: "white" }].map(({ label, value, color }) => (
                    <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><span style={{ fontSize: 14, color: "#6b7280" }}>{label}</span><span style={{ fontSize: 14, fontWeight: 600, color: color }}>{value}</span></div>
                  ))}
                  <button onClick={handleDeactivate} style={{ padding: "10px 0", borderRadius: 10, border: "1.5px solid rgba(239,68,68,0.3)", background: "transparent", color: "#f87171", fontWeight: 600, fontSize: 14, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}><LogOut size={15} /> Đăng xuất License</button>
                </div>
              </CollapsibleSection>
              <CollapsibleSection title="GPU / Whisper" icon={<Cpu size={15} />} color="#4ade80" expanded={true} onToggle={() => {}}>
                <div style={{ display: "flex", gap: 12 }}>
                  <Field label="Device" style={{ flex: 1 }}><select value={config.whisper_device} onChange={e => setConfig({ ...config, whisper_device: e.target.value })} style={IS}><option value="cuda">🎮 CUDA (GPU)</option><option value="cpu">💻 CPU</option></select></Field>
                  <Field label="Precision" style={{ flex: 1 }}><select value={config.whisper_compute_type} onChange={e => setConfig({ ...config, whisper_compute_type: e.target.value })} style={IS}><option value="float16">float16</option><option value="int8">int8</option><option value="float32">float32</option></select></Field>
                </div>
                <p style={{ fontSize: 12, color: "#4b5563", marginTop: 8 }}>💡 Dùng GPU nếu có NVIDIA, chọn int8 cho máy RAM thấp.</p>
              </CollapsibleSection>
            </div>
          </div>
        )}
      </main>

      <ToastContainer toasts={toasts} onDismiss={(id) => setToasts(prev => prev.filter(t => t.id !== id))} />
      <ErrorModal state={errorModal} onClose={() => setErrorModal(prev => ({ ...prev, visible: false }))} onRetry={handleRetryError} />
    </div>
  );
}