import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta
import secrets

# ----------------------------------------------------------------------
# 1. CẤU HÌNH KẾT NỐI (THAY BẰNG THÔNG TIN CỦA BẠN)
# ----------------------------------------------------------------------
SUPABASE_URL = "https://ezsvulvxvcjxryyhqyga.supabase.co"
# BẮT BUỘC PHẢI DÙNG SERVICE_ROLE KEY ĐỂ VƯỢT QUA RLS BẢO MẬT
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV6c3Z1bHZ4dmNqeHJ5eWhxeWdhIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Njg0NjU5OCwiZXhwIjoyMDkyNDIyNTk4fQ.ZlmM1ltc_CZHyizh3xjbzzCul_IwTk1V3hNAKks-bdM" 

@st.cache_resource
def init_connection() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# Cài đặt giao diện
st.set_page_config(page_title="Smart Video Pro - Admin", layout="wide")
st.title("🛡️ Bảng Điều Khiển Quản Trị License")

# ----------------------------------------------------------------------
# 2. GIAO DIỆN CHÍNH (TABS)
# ----------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📋 Danh sách License", "➕ Tạo Key Mới", "⚙️ Chỉnh sửa / Xóa"])

# HÀM LẤY DỮ LIỆU
def fetch_licenses():
    response = supabase.table("licenses").select("*").order("created_at", desc=True).execute()
    return response.data

# ----------------- TAB 1: DANH SÁCH -----------------
with tab1:
    st.subheader("Danh sách các Key hiện tại")
    if st.button("🔄 Làm mới dữ liệu"):
        st.rerun()
        
    data = fetch_licenses()
    if data:
        df = pd.DataFrame(data)
        # Sắp xếp cột cho đẹp
        cols = ['key', 'plan', 'status', 'quota_used', 'quota_limit', 'expires_at', 'hwid', 'note', 'last_seen_at']
        st.dataframe(df[cols], use_container_width=True)
    else:
        st.info("Chưa có license nào trong cơ sở dữ liệu.")

# ----------------- TAB 2: TẠO KEY MỚI -----------------
with tab2:
    st.subheader("Cấp phát Key mới")
    with st.form("create_key_form"):
        col1, col2 = st.columns(2)
        with col1:
            # Tự động sinh key ngẫu nhiên dạng XXXX-XXXX-XXXX
            new_key = st.text_input("License Key", value=f"SVP-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}")
            plan = st.selectbox("Gói (Plan)", ["starter", "pro", "unlimited"])
            quota = st.number_input("Số lượng video tối đa (Quota)", min_value=1, value=100)
        
        with col2:
            duration = st.selectbox("Thời hạn", ["1 Tháng", "3 Tháng", "6 Tháng", "1 Năm", "Vĩnh viễn"])
            note = st.text_input("Ghi chú (Tên khách hàng, SĐT...)")

        submit_btn = st.form_submit_button("Tạo Key", type="primary")

        if submit_btn:
            expires_at = None
            if duration == "1 Tháng": expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            elif duration == "3 Tháng": expires_at = (datetime.now() + timedelta(days=90)).isoformat()
            elif duration == "6 Tháng": expires_at = (datetime.now() + timedelta(days=180)).isoformat()
            elif duration == "1 Năm": expires_at = (datetime.now() + timedelta(days=365)).isoformat()

            try:
                supabase.table("licenses").insert({
                    "key": new_key,
                    "plan": plan,
                    "quota_limit": quota,
                    "expires_at": expires_at,
                    "note": note
                }).execute()
                st.success(f"🎉 Tạo thành công Key: {new_key}")
            except Exception as e:
                st.error(f"Lỗi: {e}")

# ----------------- TAB 3: SỬA / XÓA KEY -----------------
with tab3:
    st.subheader("Chỉnh sửa hoặc Xóa Key")
    data = fetch_licenses()
    if data:
        key_list = [row['key'] for row in data]
        selected_key = st.selectbox("Chọn Key cần xử lý", key_list)
        
        # Lấy thông tin key đang chọn
        current_data = next(item for item in data if item["key"] == selected_key)
        
        with st.form("edit_key_form"):
            st.write(f"**Đang sửa Key:** `{selected_key}`")
            col1, col2 = st.columns(2)
            
            with col1:
                new_status = st.selectbox("Trạng thái", ["active", "expired", "banned"], index=["active", "expired", "banned"].index(current_data['status']))
                new_plan = st.selectbox("Gói", ["starter", "pro", "unlimited"], index=["starter", "pro", "unlimited"].index(current_data['plan']))
                
            with col2:
                new_quota = st.number_input("Cập nhật Quota Limit", min_value=1, value=current_data['quota_limit'])
                new_note = st.text_input("Cập nhật Ghi chú", value=current_data['note'] if current_data['note'] else "")
            
            reset_hwid = st.checkbox("🗑️ Reset HWID (Mở khóa máy cho khách)")
            
            col_btn1, col_btn2 = st.columns([1, 4])
            with col_btn1:
                update_btn = st.form_submit_button("Cập nhật", type="primary")
            with col_btn2:
                # Nút xóa nguy hiểm nên cần check
                delete_btn = st.form_submit_button("Xóa vĩnh viễn Key này")
                
            if update_btn:
                update_payload = {
                    "status": new_status,
                    "plan": new_plan,
                    "quota_limit": new_quota,
                    "note": new_note
                }
                if reset_hwid:
                    update_payload["hwid"] = None # Mở khóa máy
                    
                supabase.table("licenses").update(update_payload).eq("key", selected_key).execute()
                st.success("✅ Cập nhật thành công! Hãy tải lại trang.")
                
            if delete_btn:
                supabase.table("licenses").delete().eq("key", selected_key).execute()
                st.warning("🗑️ Đã xóa Key vĩnh viễn! Hãy tải lại trang.")