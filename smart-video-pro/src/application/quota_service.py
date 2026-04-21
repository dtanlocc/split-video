import hashlib
import json
import os
import subprocess

class QuotaService:
    def __init__(self, storage_path="license.dat", monthly_limit=600):
        self.path = storage_path
        self.limit = monthly_limit
        self.secret_salt = b"SUPER_SECRET_SALT_FOR_YOUR_APP" # Giấu kỹ trong code

    def _get_hwid(self) -> str:
        """Lấy Serial Number của ổ cứng làm ID định danh thiết bị"""
        try:
            output = subprocess.check_output("wmic diskdrive get serialnumber", shell=True)
            return output.decode().split("\n")[1].strip()
        except:
            return "UNKNOWN_DEVICE"

    def _generate_signature(self, used_count: int, month: str) -> str:
        data = f"{self._get_hwid()}_{month}_{used_count}".encode()
        return hashlib.sha256(data + self.secret_salt).hexdigest()

    def check_and_deduct(self, month: str) -> bool:
        """Kiểm tra và trừ Quota. Ném Exception nếu hết hoặc bị hack"""
        if not os.path.exists(self.path):
            used = 0
        else:
            with open(self.path, "r") as f:
                data = json.load(f)
                
            # Kiểm tra xem file có bị hacker tự sửa số không?
            expected_sig = self._generate_signature(data['used'], data['month'])
            if expected_sig != data['signature']:
                raise PermissionError("Phát hiện gian lận License! Quota bị khóa.")
                
            if data['month'] != month:
                used = 0 # Reset khi qua tháng mới
            else:
                used = data['used']

        if used >= self.limit:
            return False

        # Lưu lại Quota mới
        new_used = used + 1
        with open(self.path, "w") as f:
            json.dump({
                "month": month,
                "used": new_used,
                "signature": self._generate_signature(new_used, month)
            }, f)
        
        return True