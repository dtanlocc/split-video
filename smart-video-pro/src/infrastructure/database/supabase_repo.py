import os
from supabase import create_client, Client
from src.domain.interfaces.license_repo import ILicenseRepository, LicenseInfo

class SupabaseLicenseRepository(ILicenseRepository):
    def __init__(self):
        # Thông tin Supabase của hệ thống bạn (Lưu trong .env hệ thống, KHÔNG nhận từ UI)
        url = os.environ.get("SUPABASE_URL", "https://xyz.supabase.co")
        key = os.environ.get("SUPABASE_KEY", "eyJhbG...")
        self.client: Client = create_client(url, key)

    def get_license(self, key: str) -> LicenseInfo:
        res = self.client.table("licenses").select("*").eq("key_string", key).execute()
        if not res.data:
            raise ValueError("Key bản quyền không tồn tại!")
        
        data = res.data[0]
        return LicenseInfo(
            key=data["key_string"],
            hardware_id=data.get("hardware_id", ""),
            quota_limit=data["quota_limit"],
            quota_used=data["quota_used"],
            status=data["status"]
        )

    def update_usage(self, key: str, hardware_id: str, used_amount: int) -> bool:
        res = self.client.table("licenses").update({
            "hardware_id": hardware_id,
            "quota_used": used_amount
        }).eq("key_string", key).execute()
        return len(res.data) > 0