import machineid
from src.domain.interfaces.license_repo import ILicenseRepository

class LicenseError(Exception):
    pass

class LicenseService:
    def __init__(self, repo: ILicenseRepository):
        self.repo = repo
        # Tạo mã vân tay độc nhất cho PC này (Chống share key)
        self.hwid = machineid.hashed_id('autoclip-ai-pro')

    def check_and_start(self, key: str) -> int:
        """Kiểm tra bản quyền trước khi chạy. Trả về quota còn lại."""
        if not key:
            raise LicenseError("Vui lòng nhập License Key trong Cài đặt!")

        lic = self.repo.get_license(key)
        
        if lic.status != "active":
            raise LicenseError("Tài khoản của bạn đã bị khóa!")
            
        # Ràng buộc phần cứng (HWID)
        if lic.hardware_id and lic.hardware_id != self.hwid:
            raise LicenseError("Key này đã được đăng ký trên một thiết bị khác!")
            
        if lic.quota_used >= lic.quota_limit:
            raise LicenseError(f"Đã hết Quota tháng này ({lic.quota_used}/{lic.quota_limit})!")
            
        return lic.quota_limit - lic.quota_used

    def consume_quota(self, key: str):
        """Gọi hàm này SAU KHI render xong 1 video để trừ Quota"""
        lic = self.repo.get_license(key)
        # Tăng số quota đã dùng lên 1 và ghim luôn Hardware ID vào DB
        self.repo.update_usage(key, self.hwid, lic.quota_used + 1)