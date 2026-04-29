#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod license;
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::thread;
use tauri::{Emitter, Manager, Window, Runtime}; 
use serde_json::json;

// Thư viện hỗ trợ ẩn cửa sổ Terminal trên Windows
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

// ==============================================================================
// HELPER: ĐỊNH VỊ THƯ MỤC LÀM VIỆC NGAY CẠNH FILE .EXE
// ==============================================================================
// ==============================================================================
// HELPER: ĐỊNH VỊ THƯ MỤC LÀM VIỆC (ĐÃ FIX LỖI QUYỀN ADMIN)
// ==============================================================================
fn get_workspace_dir() -> std::path::PathBuf {
    // ƯU TIÊN 1: Tạo thư mục ở C:\Users\[Tên_Khách_Hàng]\Documents\SmartVideoPro\workspace
    // Nơi này Windows cấp quyền Đọc/Ghi 100% thoải mái, không bao giờ cần Admin
    if let Ok(user_profile) = std::env::var("USERPROFILE") {
        return std::path::PathBuf::from(user_profile)
            .join("Documents")
            .join("SmartVideoPro")
            .join("workspace");
    }
    
    // ƯU TIÊN 2 (Dự phòng cho bản Portable): Để cạnh file .exe
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            return exe_dir.join("workspace");
        }
    }
    
    // Fallback cuối cùng
    std::env::current_dir().unwrap().join("workspace")
}

// ==============================================================================
// HELPER: RADAR TÌM ĐƯỜNG DẪN ENGINE AI (ĐÃ NÂNG CẤP XUYÊN THẤU DEV & RELEASE)
// ==============================================================================
fn get_engine_binary_path<R: Runtime>(app: &tauri::AppHandle<R>) -> std::path::PathBuf {
    let mut possible_paths = Vec::new();

    // 1. Thử từ resource_dir của Tauri (Chuẩn đóng gói)
    if let Ok(res_dir) = app.path().resource_dir() {
        possible_paths.push(res_dir.join("engine").join("smart-video-pro.exe"));
        possible_paths.push(res_dir.join("resources").join("engine").join("smart-video-pro.exe"));
    }

    // 2. Thử tìm ngay cạnh file chạy exe (Dành cho bản Release copy ra Desktop)
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            possible_paths.push(exe_dir.join("resources").join("engine").join("smart-video-pro.exe"));
            possible_paths.push(exe_dir.join("engine").join("smart-video-pro.exe"));
        }
    }

    // 3. Thử tìm từ thư mục làm việc hiện tại (CỨU CÁNH CHO LÚC CHẠY DEV)
    if let Ok(cwd) = std::env::current_dir() {
        // Nếu cwd đang ở gốc (autoclip-app)
        possible_paths.push(cwd.join("resources").join("engine").join("smart-video-pro.exe"));
        // Nếu cwd đang ở bên trong (src-tauri)
        possible_paths.push(cwd.join("..").join("resources").join("engine").join("smart-video-pro.exe"));
    }

    // 4. Quét qua danh sách radar, đường dẫn nào tồn tại thì lấy luôn!
    for path in possible_paths {
        if path.exists() {
            return path;
        }
    }

    // Fallback: Báo lỗi
    std::path::PathBuf::from("Không_tìm_thấy_smart-video-pro.exe")
}

// ==============================================================================
// DIRECTORY SCANNER
// ==============================================================================
#[tauri::command]
fn scan_directory(path: String) -> Vec<String> {
    use std::fs;
    let mut results = Vec::new();
    
    if let Ok(entries) = fs::read_dir(path) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                if let Some(ext) = path.extension() {
                    let ext_str = ext.to_string_lossy().to_lowercase();
                    if ["mp4", "mov", "mkv", "avi", "webm"].contains(&ext_str.as_str()) {
                        results.push(path.to_string_lossy().to_string());
                    }
                }
            }
        }
    }
    results.sort();
    results
}

// ==============================================================================
// NATIVE OPENERS (MỞ FILE/THƯ MỤC CHUYÊN NGHIỆP)
// ==============================================================================
#[tauri::command]
fn open_external(path: String) {
    #[cfg(target_os = "windows")]
    {
        let safe_path = path.replace("/", "\\");
        let mut cmd = std::process::Command::new("powershell");
        cmd.args(["-NoProfile", "-Command", "Start-Process", &format!("\"{}\"", safe_path)]);
        
        #[cfg(target_os = "windows")]
        cmd.creation_flags(0x08000000); // TÀNG HÌNH
        
        if let Err(e) = cmd.spawn() {
            eprintln!("Lỗi mở file: {} - {}", safe_path, e);
        }
    }
    #[cfg(target_os = "macos")]
    let _ = Command::new("open").arg(&path).spawn();
    #[cfg(target_os = "linux")]
    let _ = Command::new("xdg-open").arg(&path).spawn();
}

#[tauri::command]
fn open_output(original_path: String) -> Result<(), String> {
    use std::path::Path;  
    
    let file_stem = Path::new(&original_path)
        .file_stem()
        .ok_or("Không thể lấy tên file")?
        .to_string_lossy()
        .to_string();

    let workspace_dir = get_workspace_dir();
    let final_dir = workspace_dir.join(&file_stem).join("final");

    let path_to_open = if final_dir.exists() && final_dir.is_dir() {
        final_dir
    } else {
        workspace_dir
    };

    let clean_path = path_to_open.to_string_lossy().to_string().replace("\\\\?\\", "");

    #[cfg(target_os = "windows")]
    {
        let mut cmd = Command::new("explorer");
        cmd.arg(&clean_path);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(0x08000000);
        cmd.spawn().map_err(|e| format!("Không thể mở thư mục: {}", e))?;
    }
    #[cfg(target_os = "macos")]
    Command::new("open").arg(&clean_path).spawn().map_err(|e| e.to_string())?;
    #[cfg(target_os = "linux")]
    Command::new("xdg-open").arg(&clean_path).spawn().map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
fn open_folder(folder_path: String) -> Result<(), String> {
    use std::path::Path;  
    
    let path = Path::new(&folder_path);
    if !path.exists() || !path.is_dir() {
        return Err(format!("Thư mục không tồn tại: {}", folder_path));
    }
    
    let clean_path = path
        .canonicalize()
        .unwrap_or(path.to_path_buf())
        .to_string_lossy()
        .to_string()
        .replace("\\\\?\\", "");
    
    #[cfg(target_os = "windows")]
    {
        let mut cmd = Command::new("explorer");
        cmd.arg(&clean_path);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(0x08000000); 
        cmd.spawn().map_err(|e| format!("Lỗi mở thư mục: {}", e))?;
    }
    #[cfg(target_os = "macos")]
    Command::new("open").arg(&clean_path).spawn().map_err(|e| e.to_string())?;
    #[cfg(target_os = "linux")]
    Command::new("xdg-open").arg(&clean_path).spawn().map_err(|e| e.to_string())?;
    
    Ok(())
}

#[tauri::command]
fn get_workspace_path(video_name: String) -> Result<String, String> {
    let workspace = get_workspace_dir().join(&video_name);
    if workspace.exists() && workspace.is_dir() {
        Ok(workspace.to_string_lossy().to_string().replace("\\\\?\\", ""))
    } else {
        Err(format!("Thư mục không tồn tại: {}", video_name))
    }
}

// ==============================================================================
// PIPELINE COMMAND (AI BACKEND EXECUTION)
// ==============================================================================
#[tauri::command]
async fn start_pipeline(
    window: Window,
    mode: String,
    video_path: String,
    config_obj: String,
    session_token: String,
) -> Result<String, String> {
    let hwid = license::get_hwid();
    
    // Tự động tìm đường dẫn file exe AI Backend
    let engine_path = get_engine_binary_path(&window.app_handle());
    if !engine_path.exists() {
        return Err(format!("Không tìm thấy engine AI tại: {:?}", engine_path));
    }

    let engine_dir = engine_path.parent().unwrap().to_path_buf();
    let workspace_dir = get_workspace_dir();

    thread::spawn(move || {
        let ui: serde_json::Value = serde_json::from_str(&config_obj).unwrap_or(json!({}));
        let final_payload = json!({
            "video_path": video_path,
            "mode": mode,
            "session_token": session_token,
            "workspace_dir": workspace_dir.to_string_lossy().to_string(),
            "hwid": hwid,
            "gemini_api_key": ui["gemini_api_key"],
            "stt_config": {
                "lang": ui["lang_code"],
                "model": ui["whisper_model"],
                "device": ui["whisper_device"].as_str().unwrap_or("cuda"),
                "compute_type": ui["whisper_compute_type"].as_str().unwrap_or("float16"),
            },
            "gemini_config": {
                "min_duration_sec": ui["min_duration"],
                "max_duration_sec": ui["max_duration"],
                "model_name": ui["gemini_model"].as_str().unwrap_or("gemini-2.5-flash"),
            },
            "crop_config": {
                "output_size": [1080, 1920],
                "sharpen_strength": ui["sharpen_strength"],
                "ffmpeg_codec": "h264_nvenc",
                "ffmpeg_preset": "p4",
            },
            "render_config": {
                "title_color": ui["title_color"],
                "sub_bg_color": ui["sub_bg_color"],
                "font_title_file": ui["font_title_file"].as_str().unwrap_or("").replace("\\", "/"),
                "video_speed": ui["video_speed"].as_f64().unwrap_or(1.03),
                "max_words_per_line": ui["max_words_per_line"].as_i64().unwrap_or(3),
                "sub_margin_v": ui["sub_margin_v"].as_i64().unwrap_or(250),
                "sub_font_size": ui["sub_font_size"].as_i64().unwrap_or(85),
                "max_parallel": 1,
            }
        }); 

        let payload_str = serde_json::to_string(&final_payload).unwrap();
        
        let mut cmd = Command::new(&engine_path);
        
        cmd.current_dir(&engine_dir)
            .arg("--payload")
            .arg(&payload_str)
            .stdin(Stdio::null())   
            .stdout(Stdio::piped())
            .stderr(Stdio::null()); // 🔥 ĐÓNG LUỒNG LỖI LẠI CHO SẠCH

        #[cfg(target_os = "windows")]
        cmd.creation_flags(0x08000000); 

        // BẮT LỖI MỞ ENGINE AN TOÀN
        let mut child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                let err_msg = format!("❌ Không thể khởi chạy tiến trình AI. Lỗi OS: {}", e);
                let _ = window.emit("ai-progress", json!({
                    "stage": "complete", "pct": 0, "status": "err", "msg": err_msg
                }).to_string());
                return; 
            }
        };

        let stdout = child.stdout.take().unwrap();
        let window_clone = window.clone();

        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                if !line.trim().is_empty() {
                    // 🔥 CHỈ LẤY JSON: Nếu Python gửi chuẩn JSON -> Cập nhật UI
                    // Các lệnh print() bình thường khác sẽ bị lờ đi (ẩn hoàn toàn)
                    if let Ok(_json_val) = serde_json::from_str::<serde_json::Value>(&line) {
                        let _ = window_clone.emit("ai-progress", &line);
                    }
                }
            }
        });

        let status = child.wait().unwrap();
        
        if status.success() {
            let _ = window.emit("ai-progress", json!({
                "stage": "complete", "pct": 100, "status": "ok", 
                "msg": "Hoàn tất! AI đã xử lý xong."
            }).to_string());
        } else {
            let exit_code = status.code().unwrap_or(-1);
            let _ = window.emit("ai-progress", json!({
                "stage": "complete", "pct": 0, "status": "err", 
                "msg": format!("❌ Python exit code: {}. Vui lòng thử lại.", exit_code)
            }).to_string());
        }
    });

    Ok("Pipeline started".into())
}

// ==============================================================================
// MAIN ENTRY POINT
// ==============================================================================
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            start_pipeline,
            scan_directory,
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