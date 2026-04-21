# main.py
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Import MainWindow
from src.presentation.ui.main_window import MainWindow
from src.presentation.utils.signal_bus import bus


def main():
    # Cấu hình High DPI (cho giao diện sắc nét hơn)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Style đẹp cho dark theme

    # Tạo cửa sổ chính
    window = MainWindow()
    window.show()

    # Thông báo khởi động
    bus.log_emitted.emit("ok", "AutoClip AI v2.1.0 đã khởi động thành công.")
    bus.log_emitted.emit("inf", "Chào mừng bạn đến với AutoClip AI!")

    sys.exit(app.exec())


if __name__ == "__main__":
    # Đảm bảo thư mục config tồn tại
    Path("verify_results/final").mkdir(parents=True, exist_ok=True)
    Path("verify_results/tmp").mkdir(parents=True, exist_ok=True)
    
    main()