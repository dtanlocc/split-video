from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LicenseInfo:
    key: str
    hardware_id: str
    quota_limit: int
    quota_used: int
    status: str

class ILicenseRepository(ABC):
    @abstractmethod
    def get_license(self, key: str) -> LicenseInfo:
        pass
    
    @abstractmethod
    def update_usage(self, key: str, hardware_id: str, used_amount: int) -> bool:
        pass