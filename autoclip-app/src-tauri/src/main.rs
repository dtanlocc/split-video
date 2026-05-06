#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod license;
use std::io::{BufRead, BufReader, Write};
use std::process::{Command, Stdio, ChildStdin};
use std::sync::{Arc, Mutex};
use std::thread;
use tauri::{Emitter, Manager, Window, Runtime};
use serde_json::json;
use std::fs;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

// ==============================================================================
// PERSISTENT ENGINE STATE
// ==============================================================================
struct EngineState {
    stdin: Option<ChildStdin>,
    alive: bool,
}

impl EngineState {
    fn new() -> Self { EngineState { stdin: None, alive: false } }
}

type SharedEngine = Arc<Mutex<EngineState>>;

// ==============================================================================
// WORKSPACE & ENGINE PATH
// ==============================================================================
fn get_workspace_dir() -> std::path::PathBuf {
    if let Ok(user_profile) = std::env::var("USERPROFILE") {
        return std::path::PathBuf::from(user_profile)
            .join("Documents").join("SmartVideoPro").join("workspace");
    }
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            return exe_dir.join("workspace");
        }
    }
    std::env::current_dir().unwrap().join("workspace")
}

fn get_engine_binary_path<R: Runtime>(app: &tauri::AppHandle<R>) -> std::path::PathBuf {
    let mut paths = Vec::new();
    if let Ok(res_dir) = app.path().resource_dir() {
        paths.push(res_dir.join("engine").join("smart-video-pro.exe"));
        paths.push(res_dir.join("resources").join("engine").join("smart-video-pro.exe"));
    }
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            paths.push(exe_dir.join("resources").join("engine").join("smart-video-pro.exe"));
            paths.push(exe_dir.join("engine").join("smart-video-pro.exe"));
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        paths.push(cwd.join("resources").join("engine").join("smart-video-pro.exe"));
        paths.push(cwd.join("..").join("resources").join("engine").join("smart-video-pro.exe"));
    }
    for p in paths { if p.exists() { return p; } }
    std::path::PathBuf::from("engine_not_found.exe")
}

// ==============================================================================
// KHỞI ĐỘNG ENGINE SERVER (1 LẦN)
// ==============================================================================
fn ensure_engine_running<R: Runtime>(
    app: &tauri::AppHandle<R>,
    engine_state: &SharedEngine,
    window: &Window,
) -> Result<(), String> {
    let mut state = engine_state.lock().map_err(|e| e.to_string())?;
    if state.alive { return Ok(()); }

    let engine_path = get_engine_binary_path(app);
    if !engine_path.exists() {
        return Err(format!("Không tìm thấy engine: {:?}", engine_path));
    }

    let engine_dir = engine_path.parent().unwrap().to_path_buf();
    let workspace_dir = get_workspace_dir();

    let mut cmd = Command::new(&engine_path);
    cmd.current_dir(&engine_dir)
        .arg("--server")
        .arg("--workspace")
        .arg(workspace_dir.to_string_lossy().to_string())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped()); // bắt stderr để log debug

    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000);

    let mut child = cmd.spawn()
        .map_err(|e| format!("Không thể khởi chạy engine: {}", e))?;

    let child_stdin = child.stdin.take()
        .ok_or("Không lấy được stdin")?;

    state.stdin = Some(child_stdin);
    state.alive = true;

    // Thread đọc stdout → emit Tauri event
    let window_clone = window.clone();
    let engine_state_stdout = Arc::clone(engine_state);
    let stdout = child.stdout.take().unwrap();

    thread::spawn(move || {
        // ★ BufReader với UTF-8: trên Windows, pipe có thể trả raw bytes
        // Dùng lines() sẽ tự decode UTF-8 đúng nếu Python ghi UTF-8
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
            match line {
                Ok(l) if !l.trim().is_empty() => {
                    if serde_json::from_str::<serde_json::Value>(&l).is_ok() {
                        let _ = window_clone.emit("ai-progress", &l);
                    }
                }
                _ => {}
            }
        }
        if let Ok(mut s) = engine_state_stdout.lock() {
            s.alive = false;
            s.stdin = None;
        }
        let _ = window_clone.emit("ai-progress", json!({
            "stage": "server", "pct": 0, "status": "warn",
            "msg": "⚠️ AI engine đã tắt."
        }).to_string());
    });

    // Thread đọc stderr để log (không emit ra UI, chỉ để debug)
    let stderr = child.stderr.take().unwrap();
    thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines().flatten() {
            eprintln!("[Python STDERR] {}", line);
        }
    });

    Ok(())
}

// ==============================================================================
// SCAN DIRECTORY & READ TEXT FILE
// ==============================================================================
#[tauri::command]
fn scan_directory(path: String) -> Vec<String> {
    let mut results = Vec::new();
    if let Ok(entries) = fs::read_dir(&path) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_file() {
                if let Some(ext) = p.extension() {
                    let ext_str = ext.to_string_lossy().to_lowercase();
                    if ["mp4","mov","mkv","avi","webm"].contains(&ext_str.as_str()) {
                        results.push(p.to_string_lossy().to_string());
                    }
                }
            }
        }
    }
    results.sort();
    results
}

#[tauri::command]
fn read_text_file(path: String) -> Result<String, String> {
    fs::read_to_string(&path).map_err(|e| format!("Không thể đọc file: {}", e))
}

// ==============================================================================
// OPENERS
// ==============================================================================
#[tauri::command]
fn open_external(path: String) {
    #[cfg(target_os = "windows")]
    {
        let safe_path = path.replace("/", "\\");
        let mut cmd = std::process::Command::new("powershell");
        cmd.args(["-NoProfile", "-Command", "Start-Process",
                  &format!("\"{}\"", safe_path)]);
        cmd.creation_flags(0x08000000);
        let _ = cmd.spawn();
    }
    #[cfg(not(target_os = "windows"))]
    { let _ = Command::new("open").arg(&path).spawn(); }
}

#[tauri::command]
fn open_output(original_path: String) -> Result<(), String> {
    let file_stem = std::path::Path::new(&original_path)
        .file_stem().ok_or("Không lấy được tên file")?
        .to_string_lossy().to_string();
    let workspace_dir = get_workspace_dir();
    let final_dir = workspace_dir.join(&file_stem).join("final");
    let path_to_open = if final_dir.exists() { final_dir } else { workspace_dir };
    let clean = path_to_open.to_string_lossy().to_string().replace("\\\\?\\", "");
    #[cfg(target_os = "windows")]
    { let mut cmd = Command::new("explorer"); cmd.arg(&clean);
      cmd.creation_flags(0x08000000);
      cmd.spawn().map_err(|e| e.to_string())?; }
    Ok(())
}

#[tauri::command]
fn open_folder(folder_path: String) -> Result<(), String> {
    let path = std::path::Path::new(&folder_path);
    if !path.exists() { return Err(format!("Không tồn tại: {}", folder_path)); }
    let clean = path.canonicalize().unwrap_or(path.to_path_buf())
        .to_string_lossy().to_string().replace("\\\\?\\", "");
    #[cfg(target_os = "windows")]
    { let mut cmd = Command::new("explorer"); cmd.arg(&clean);
      cmd.creation_flags(0x08000000);
      cmd.spawn().map_err(|e| e.to_string())?; }
    Ok(())
}

#[tauri::command]
fn get_workspace_path(video_name: String) -> Result<String, String> {
    let ws = get_workspace_dir().join(&video_name);
    if ws.exists() {
        Ok(ws.to_string_lossy().to_string().replace("\\\\?\\", ""))
    } else {
        Err(format!("Không tồn tại: {}", video_name))
    }
}

// ==============================================================================
// ★ PIPELINE — Gửi job qua stdin với encoding UTF-8 đúng cách
// ==============================================================================
#[tauri::command]
async fn start_pipeline(
    window: Window,
    mode: String,
    video_path: String,
    config_obj: String,
    session_token: String,
    engine_state: tauri::State<'_, SharedEngine>,
) -> Result<String, String> {
    let hwid = license::get_hwid();
    let app_handle = window.app_handle();

    ensure_engine_running(&app_handle, &engine_state, &window)?;

    let ui: serde_json::Value = serde_json::from_str(&config_obj)
        .unwrap_or(json!({}));
    let workspace_dir = get_workspace_dir();
    let title_lang = ui.get("title_language").cloned().unwrap_or(json!(null));

    // Build payload JSON
    let task_payload = json!({
        "video_path": video_path,   // ← serde_json tự escape Unicode đúng
        "mode": mode,
        "session_token": session_token,
        "workspace_dir": workspace_dir.to_string_lossy().to_string(),
        "hwid": hwid,

        "llm_backend": ui.get("llm_backend").cloned().unwrap_or(json!("gemini")),

        "gemini_api_key":  ui["gemini_api_key"],
        "gemini_api_keys": ui["gemini_api_keys"],

        "deepseek_api_key":  ui["deepseek_api_key"],
        "deepseek_api_keys": ui["deepseek_api_keys"],

        "stt_config": {
            "lang":         ui["lang_code"],
            "model":        ui["whisper_model"],
            "device":       ui["whisper_device"].as_str().unwrap_or("cuda"),
            "compute_type": ui["whisper_compute_type"].as_str().unwrap_or("float16"),
        },
        "gemini_config": {
            "min_duration_sec": ui["min_duration"],
            "max_duration_sec": ui["max_duration"],
            "model_name":       ui["gemini_model"].as_str().unwrap_or("gemini-2.5-flash"),
            "title_language":   title_lang.clone(),
        },
        "deepseek_config": {
            "model_name":       ui["deepseek_model"].as_str().unwrap_or("deepseek-chat"),
            "max_output_tokens":ui["deepseek_max_tokens"].as_u64().unwrap_or(8192),
            "temperature":      ui["deepseek_temperature"].as_f64().unwrap_or(0.1),
            "title_language":   title_lang.clone(),
        },
        "crop_config": {
            "output_size":      [1080, 1920],
            "sharpen_strength": ui["sharpen_strength"],
            "ffmpeg_codec":     "h264_nvenc",
            "ffmpeg_preset":    "p4",
        },
        "render_config": {
            "title_color":        ui["title_color"],
            "sub_bg_color":       ui["sub_bg_color"],
            "font_title_file":    ui["font_title_file"].as_str().unwrap_or("").replace("\\", "/"),
            "video_speed":        ui["video_speed"].as_f64().unwrap_or(1.03),
            "max_words_per_line": ui["max_words_per_line"].as_i64().unwrap_or(3),
            "sub_margin_v":       ui["sub_margin_v"].as_i64().unwrap_or(250),
            "sub_font_size":      ui["sub_font_size"].as_i64().unwrap_or(85),
            "max_parallel":       1,
        }
    });

    // ★ QUAN TRỌNG: serde_json::to_string() luôn tạo UTF-8 chuẩn
    // Ký tự Unicode như ： (U+FF1A) sẽ được giữ nguyên dạng UTF-8
    // KHÔNG dùng to_string() của Value vì có thể escape khác nhau
    let payload_str = serde_json::to_string(&task_payload)
        .map_err(|e| format!("Lỗi serialize JSON: {}", e))?;

    // Gửi qua stdin: payload_str là UTF-8 string + newline
    {
        let mut state = engine_state.lock().map_err(|e| e.to_string())?;

        if !state.alive {
            return Err("AI engine đã dừng! Vui lòng khởi động lại app.".to_string());
        }

        if let Some(stdin) = &mut state.stdin {
            // ★ Ghi bytes UTF-8 trực tiếp — không qua Windows ANSI conversion
            let mut bytes = payload_str.into_bytes();
            bytes.push(b'\n');
            stdin.write_all(&bytes)
                .map_err(|e| format!("Không thể gửi task: {}", e))?;
            stdin.flush()
                .map_err(|e| format!("Flush stdin lỗi: {}", e))?;
        } else {
            return Err("Engine stdin không khả dụng.".to_string());
        }
    }

    let _ = window.emit("ai-progress", json!({
        "stage": "init", "pct": 2, "status": "inf",
        "msg": "📤 Task đã được gửi tới AI engine..."
    }).to_string());

    Ok("ok".into())
}

// ==============================================================================
// MAIN
// ==============================================================================
fn main() {
    let engine_state: SharedEngine = Arc::new(Mutex::new(EngineState::new()));

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(engine_state)
        .invoke_handler(tauri::generate_handler![
            start_pipeline,
            scan_directory,
            read_text_file,
            open_external,
            open_output,
            open_folder,
            get_workspace_path,
            license::activate_license,
            license::load_license,
            license::create_render_token,
            license::deactivate_license,
            license::get_device_id,
        ])
        .run(tauri::generate_context!())
        .expect("Lỗi khi chạy Tauri app");
}