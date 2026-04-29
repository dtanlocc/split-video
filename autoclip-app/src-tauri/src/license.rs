// src-tauri/src/license.rs
// Thêm vào Cargo.toml:
//   reqwest = { version = "0.12", features = ["json", "rustls-tls"], default-features = false }
//   serde = { version = "1", features = ["derive"] }
//   serde_json = "1"
//   keyring = "2"        ← lưu key vào Windows Credential Manager

use keyring::Entry;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::time::Duration;

// ★ CHỈ có Edge Function URL ở đây — KHÔNG có service_role key
const EDGE_URL: &str = "https://ezsvulvxvcjxryyhqyga.supabase.co/functions/v1/verify-license";
const ANON_KEY: &str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV6c3Z1bHZ4dmNqeHJ5eWhxeWdhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY4NDY1OTgsImV4cCI6MjA5MjQyMjU5OH0.07-ynitsEw7LFyKLbWu4lt_M8wZXmmRyJWkaW73lDcw"; // anon key — OK để lộ
const KEYRING_SERVICE: &str = "autocip-ai-pro";
const KEYRING_USER: &str = "license_key";

// ==============================================================================
// DATA STRUCTURES
// ==============================================================================
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct LicenseInfo {
    pub status:         String,
    pub plan:           String,
    pub quota_used:     i64,
    pub quota_limit:    i64,
    pub quota_remain:   i64,
    pub expires_at:     Option<String>,
    pub is_expired:     bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SessionTokenResult {
    pub token:          String,
    pub quota_used:     i64,
    pub quota_limit:    i64,
    pub expires_at:     Option<String>,
    pub plan:           String,
}

// ==============================================================================
// HWID — dùng Windows WMI giống Python
// ==============================================================================
pub fn get_hwid() -> String {
    use std::process::Command;
    use sha2::{Sha256, Digest};

    let mut parts = Vec::new();

    // Dùng PowerShell thay wmic (wmic deprecated trên Windows 11)
    let cmds = vec![
        "Get-WmiObject Win32_ComputerSystemProduct | Select-Object -ExpandProperty UUID",
        "Get-WmiObject Win32_Processor | Select-Object -ExpandProperty ProcessorId",
        "Get-WmiObject Win32_DiskDrive | Select-Object -ExpandProperty SerialNumber",
    ];

    for cmd in cmds {
        let mut command = Command::new("powershell");
        command.args(["-NoProfile", "-Command", cmd]);

        // ✅ GẮN CỜ TÀNG HÌNH CHO WINDOWS Ở ĐÂY
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // 0x08000000 = CREATE_NO_WINDOW
        }

        let out = command.output();

        match out {
            Ok(o) => {
                let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
                if s.is_empty() {
                    parts.push("UNKNOWN".to_string());
                } else {
                    parts.push(s);
                }
            }
            Err(_) => parts.push("UNKNOWN".to_string()),
        }
    }

    let raw = format!("OVERLORD_{}_{}_SALT", parts.join("|"), "AUTOCIP");
    let mut hasher = Sha256::new();
    hasher.update(raw.as_bytes());
    let result = hasher.finalize();
    format!("{:X}", result)[..32].to_string()
}

// ==============================================================================
// HTTP CLIENT với timeout
// ==============================================================================
fn build_client() -> Client {
    Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("Failed to build HTTP client")
}

async fn call_edge(action: &str, body: Value) -> Result<Value, String> {
    let client = build_client();
    let mut payload = body;
    payload["action"] = json!(action);

    let resp = client
        .post(EDGE_URL)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", ANON_KEY))
        .json(&payload)
        .send()
        .await
        .map_err(|e| format!("Lỗi kết nối: {}", e))?;

    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();
    let data: Value = serde_json::from_str(&text)
        .unwrap_or_else(|_| json!({"error": text}));

    if !status.is_success() {
        let msg = data["error"].as_str().unwrap_or("Lỗi không xác định").to_string();
        return Err(msg);
    }
    Ok(data)
}

// ==============================================================================
// KEYRING: Lưu key vào Windows Credential Manager (encrypted by OS)
// ==============================================================================
fn save_key_local(key: &str) -> Result<(), String> {
    let entry = Entry::new(KEYRING_SERVICE, KEYRING_USER)
        .map_err(|e| e.to_string())?;
    entry.set_password(key).map_err(|e| e.to_string())
}

fn load_key_local() -> Option<String> {
    let entry = Entry::new(KEYRING_SERVICE, KEYRING_USER).ok()?;
    entry.get_password().ok()
}

fn delete_key_local() {
    if let Ok(entry) = Entry::new(KEYRING_SERVICE, KEYRING_USER) {
        let _ = entry.delete_password();
    }
}

// ==============================================================================
// TAURI COMMANDS
// ==============================================================================

/// Kích hoạt license key lần đầu
#[tauri::command]
pub async fn activate_license(key: String) -> Result<LicenseInfo, String> {
    let hwid = get_hwid();

    let data = call_edge("get_info", json!({
        "p_key":  key,
        "p_hwid": hwid,
    })).await?;

    let info: LicenseInfo = serde_json::from_value(data)
        .map_err(|e| format!("Parse lỗi: {}", e))?;

    if info.is_expired {
        return Err("Key đã hết hạn!".to_string());
    }

    // Lưu key vào Credential Manager
    save_key_local(&key)?;

    Ok(info)
}

/// Load license khi mở app (đọc từ Credential Manager + verify server)
#[tauri::command]
pub async fn load_license() -> Result<Option<LicenseInfo>, String> {
    let Some(key) = load_key_local() else {
        return Ok(None); // Chưa kích hoạt
    };

    let hwid = get_hwid();

    match call_edge("get_info", json!({
        "p_key":  key,
        "p_hwid": hwid,
    })).await {
        Ok(data) => {
            let info: LicenseInfo = serde_json::from_value(data)
                .map_err(|e| format!("Parse lỗi: {}", e))?;
            Ok(Some(info))
        }
        Err(e) => {
            // Server lỗi nhưng có local key → trả None để UI hiện offline mode
            eprintln!("License server error (offline?): {}", e);
            Ok(None)
        }
    }
}

/// Tạo session token trước khi render (quota bị trừ ngay tại đây)
#[tauri::command]
pub async fn create_render_token() -> Result<String, String> {
    let Some(key) = load_key_local() else {
        return Err("Chưa kích hoạt license!".to_string());
    };

    let hwid = get_hwid();

    let data = call_edge("create_token", json!({
        "p_key":  key,
        "p_hwid": hwid,
    })).await?;

    let result: SessionTokenResult = serde_json::from_value(data)
        .map_err(|e| format!("Parse lỗi: {}", e))?;

    Ok(result.token)
}

/// Xóa license (deactivate)
#[tauri::command]
pub fn deactivate_license() -> Result<(), String> {
    delete_key_local();
    Ok(())
}

/// Lấy HWID hiện tại (hiển thị cho user)
#[tauri::command]
pub fn get_device_id() -> String {
    get_hwid()
}