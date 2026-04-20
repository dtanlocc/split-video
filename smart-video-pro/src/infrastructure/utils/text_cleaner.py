"""Step 0: High-performance text normalization."""

# src/infrastructure/utils/text_cleaner.py
import re
from typing import Generator

class TextNormalizer:
    @staticmethod
    def clean_stream(file_path: str) -> Generator[str, None, None]:
        """
        Xử lý chuẩn hóa text theo dòng. 
        Tối ưu cho file cực lớn, tránh tốn CPU cho việc cấp phát mảng lớn.
        """
        # Quy tắc: Sử dụng Regex đã được compile để tăng tốc xử lý
        pattern = re.compile(r'[^\w\s\d]') 
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # Xử lý từng dòng và yield kết quả
                cleaned_line = pattern.sub('', line).strip().lower()
                if cleaned_line:
                    yield cleaned_line