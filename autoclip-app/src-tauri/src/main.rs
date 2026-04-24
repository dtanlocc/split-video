#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod license;
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::thread;
use tauri::{Emitter, Window};
use serde_json::json;

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
// NATIVE OPENERS
// ==============================================================================
#[tauri::command]
fn open_external(path: String) {
    #[cfg(target_os = "windows")]
    {
        let safe_path = path.replace("/", "\\");
        // ✅ FIX: Dùng if let để handle error thay vì unwrap_or_else sai type
        if let Err(e) = std::process::Command::new("powershell")
            .args(["-NoProfile", "-Command", "Start-Process", &format!("\"{}\"", safe_path)])
            .spawn()
        {
            eprintln!("Lỗi mở file: {} - {}", safe_path, e);
        }
    }
    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open").arg(&path).spawn();
    }
    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("xdg-open").arg(&path).spawn();
    }
}

#[tauri::command]
fn open_output(original_path: String) -> Result<(), String> {
    use std::path::Path;  // ✅ Chỉ import Path, bỏ PathBuf
    
    let file_stem = Path::new(&original_path)
        .file_stem()
        .ok_or("Không thể lấy tên file")?
        .to_string_lossy()
        .to_string();

    let current_dir = std::env::current_dir()
        .map_err(|e| format!("Lỗi lấy đường dẫn: {}", e))?;
    
    let mut final_dir = current_dir.clone();
    final_dir.push("..");
    final_dir.push("smart-video-pro");
    final_dir.push("workspace");
    final_dir.push(&file_stem);
    final_dir.push("final");

    let path_to_open = if final_dir.exists() && final_dir.is_dir() {
        final_dir
    } else {
        let mut fallback = current_dir;
        fallback.push("..");
        fallback.push("smart-video-pro");
        fallback.push("workspace");
        fallback
    };

    let clean_path = path_to_open
        .canonicalize()
        .unwrap_or(path_to_open)
        .to_string_lossy()
        .to_string()
        .replace("\\\\?\\", "");

    #[cfg(target_os = "windows")]
    Command::new("explorer").arg(&clean_path).spawn()
        .map_err(|e| format!("Không thể mở thư mục: {}", e))?;
    #[cfg(target_os = "macos")]
    Command::new("open").arg(&clean_path).spawn()
        .map_err(|e| format!("Không thể mở thư mục: {}", e))?;
    #[cfg(target_os = "linux")]
    Command::new("xdg-open").arg(&clean_path).spawn()
        .map_err(|e| format!("Không thể mở thư mục: {}", e))?;

    Ok(())
}

// 🔥 NEW: Open specific folder path
#[tauri::command]
fn open_folder(folder_path: String) -> Result<(), String> {
    use std::process::Command;
    use std::path::Path;  // ✅ Chỉ import Path
    
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
    Command::new("explorer").arg(&clean_path).spawn()
        .map_err(|e| format!("Lỗi mở thư mục: {}", e))?;
    #[cfg(target_os = "macos")]
    Command::new("open").arg(&clean_path).spawn()
        .map_err(|e| format!("Lỗi mở thư mục: {}", e))?;
    #[cfg(target_os = "linux")]
    Command::new("xdg-open").arg(&clean_path).spawn()
        .map_err(|e| format!("Lỗi mở thư mục: {}", e))?;
    
    Ok(())
}

// 🔥 NEW: Get workspace path for a video
#[tauri::command]
fn get_workspace_path(video_name: String) -> Result<String, String> {
    // ✅ XÓA dòng: use std::path::Path;
    
    let current_dir = std::env::current_dir()
        .map_err(|e| format!("Lỗi lấy đường dẫn: {}", e))?;
    
    let mut workspace = current_dir;
    workspace.push("..");
    workspace.push("smart-video-pro");
    workspace.push("workspace");
    workspace.push(&video_name);
    
    if workspace.exists() && workspace.is_dir() {
        Ok(workspace
            .canonicalize()
            .unwrap_or(workspace)
            .to_string_lossy()
            .to_string()
            .replace("\\\\?\\", ""))
    } else {
        Err(format!("Thư mục không tồn tại: {}", video_name))
    }
}

// ==============================================================================
// PIPELINE COMMAND
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

    thread::spawn(move || {
        let ui: serde_json::Value = serde_json::from_str(&config_obj).unwrap_or(json!({}));
        let final_payload = json!({
            "video_path": video_path,
            "mode": mode,
            "session_token": session_token,
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
        let engine_dir = std::env::current_dir()
            .unwrap()
            .join("..")
            .join("..")
            .join("smart-video-pro");

        let mut child = Command::new("python")
            .current_dir(&engine_dir)
            .arg("main_cli.py")
            .arg("--payload")
            .arg(&payload_str)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .expect("Không thể khởi chạy Python");

        let stdout = child.stdout.take().unwrap();
        let window_clone = window.clone();

        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                if line.trim().is_empty() { continue; }
                
                // Try parse JSON, nếu fail thì log debug thay vì emit
                if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&line) {
                    let _ = window_clone.emit("ai-progress", &line);
                } else {
                    // Log non-JSON lines để debug, không emit lên frontend
                    eprintln!("[DEBUG] Non-JSON output: {}", line);
                }
            }
        });

        // // Thread đọc stderr (bắt lỗi Python)
        // std::thread::spawn(move || {
        //     let reader = BufReader::new(stderr);
        //     for line in reader.lines() {
        //         if let Ok(err_line) = line {
        //             if err_line.trim().is_empty() { continue; }
                    
        //             // 🔥 Lọc tqdm progress bars
        //             if err_line.contains("|") && 
        //                (err_line.contains("Transcribe:") || 
        //                 err_line.contains("sec/s") ||
        //                 err_line.chars().filter(|c| *c == '#' || *c == '-').count() > 5) {
        //                 continue;
        //             }
                    
        //             // 🔥 Chuyển warning/info thành log thường
        //             if err_line.contains("WARNING:") || 
        //                err_line.contains("⚠️") ||
        //                err_line.contains("✅") ||
        //                err_line.contains("🧠") ||
        //                err_line.contains("🔍") ||
        //                err_line.contains("🎬") {
        //                 let _ = window_clone.emit("ai-progress", 
        //                     json!({"stage": 0, "pct": 0, "status": "inf", "msg": err_line}).to_string()
        //                 );
        //                 continue;
        //             }
                    
        //             // Chỉ emit thật sự là error
        //             let err_json = json!({
        //                 "stage": -1,
        //                 "pct": 0,
        //                 "status": "err",
        //                 "msg": format!("🐍 {}", err_line)
        //             }).to_string();
        //             let _ = window_clone.emit("ai-progress", err_json);
        //         }
        //     }
        // });

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
                "msg": format!("❌ Python exit code: {}. Kiểm tra log phía trên.", exit_code)
            }).to_string());
        }
    });

    Ok("Pipeline started".into())
}

// ==============================================================================
// MAIN
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
            open_folder,           // ✅ NEW
            get_workspace_path,    // ✅ NEW
            license::activate_license,
            license::load_license,
            license::create_render_token,
            license::deactivate_license,
            license::get_device_id,
        ])
        .run(tauri::generate_context!())
        .expect("Lỗi khi chạy Tauri app");
}