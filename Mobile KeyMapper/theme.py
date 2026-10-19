"""Calm, high-contrast dark theme with roomy cards. Colours are tokens at the top; everything else uses them."""

ACCENT = "#7c5cff"
ACCENT_HOVER = "#907aff"
OK = "#35d07f"
WARN = "#ffb020"
ERROR = "#ff5c6c"
MUTED = "#8a93a8"
TEXT = "#e8ebf4"
BG = "#0e1118"
PANEL = "#131825"
CARD = "#1a2030"
CARD_BORDER = "#262e45"
FIELD = "#10141f"

STYLE_SHEET = f"""
* {{ font-family: "Segoe UI"; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {CARD}; border: 1px solid {ACCENT}; padding: 6px; color: {TEXT}; }}

/* ---- layout surfaces ---------------------------------------------------------------- */
QWidget#sidebar {{ background: {PANEL}; border-right: 1px solid {CARD_BORDER}; }}
QWidget#toolbar {{ background: {PANEL}; border-bottom: 1px solid {CARD_BORDER}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 14px; }}
QFrame#card QLabel {{ background: transparent; }}
QWidget#sidebarFooter {{ background: {PANEL}; border-top: 1px solid {CARD_BORDER}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}

/* ---- text ---------------------------------------------------------------------------- */
QLabel#appTitle {{ font-size: 20px; font-weight: 700; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#cardTitle {{ font-size: 14px; font-weight: 600; }}
QLabel#stepBadge {{ background: {ACCENT}; color: white; border-radius: 11px; font-weight: 700; min-width: 22px;
                    max-width: 22px; min-height: 22px; max-height: 22px; qproperty-alignment: AlignCenter; }}
QLabel#tip {{ background: rgba(124, 92, 255, 0.12); border: 1px solid rgba(124, 92, 255, 0.35); border-radius: 10px;
              padding: 9px 11px; color: {TEXT}; }}
QLabel#statusDot {{ font-size: 15px; }}

/* ---- buttons --------------------------------------------------------------------------- */
QPushButton {{ background: {CARD}; border: 1px solid #2f3856; border-radius: 9px; padding: 8px 14px; }}
QPushButton:hover {{ background: #242c44; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #1c2338; }}
QPushButton:disabled {{ color: #5a627a; background: #151a28; border-color: #1f263a; }}
QPushButton:checked {{ background: #2c2460; border-color: {ACCENT}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}

QPushButton#primary {{ background: {ACCENT}; border: 0; color: white; font-weight: 600; font-size: 14px;
                       padding: 11px 16px; }}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #2a2750; color: #8c86b8; }}
QPushButton#danger {{ background: #4a1f2b; border: 1px solid {ERROR}; font-weight: 600; font-size: 14px; padding: 11px 16px; }}
QPushButton#danger:hover {{ background: #5c2535; }}

QPushButton#play {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2fd37f, stop:1 #1fa862); border: 0;
                    color: #04170d; font-size: 16px; font-weight: 700; padding: 15px 18px; border-radius: 12px; }}
QPushButton#play:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #44e194, stop:1 #26bd70); }}
QPushButton#play:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff6f7f, stop:1 #d9455a);
                            color: white; }}
QPushButton#play:disabled {{ background: #1b2a26; color: #5f7a6f; }}

QPushButton#editToggle {{ font-weight: 600; padding: 11px 16px; font-size: 14px; }}
QPushButton#editToggle:checked {{ background: {WARN}; border-color: {WARN}; color: #2b1c00; }}

QPushButton#chip {{ padding: 7px 10px; border-radius: 16px; background: {FIELD}; border: 1px solid #2a3350; }}
QPushButton#chip:hover {{ border-color: {ACCENT}; background: #1d2540; }}
QPushButton#chip:disabled {{ color: #565e75; }}
QPushButton#chip::menu-indicator {{ subcontrol-origin: padding; subcontrol-position: right center; right: 10px; }}

QPushButton#flat {{ background: transparent; border: 0; color: {MUTED}; padding: 6px 8px; }}
QPushButton#flat:hover {{ color: {TEXT}; background: rgba(255,255,255,0.05); }}
QPushButton#flat:disabled {{ color: #444b5f; }}
QPushButton#tool {{ background: {CARD}; border: 1px solid #2b3350; padding: 6px 12px; border-radius: 8px; }}
QPushButton#tool:disabled {{ color: #4d546a; }}

/* ---- inputs -------------------------------------------------------------------------- */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {FIELD}; border: 1px solid #2b3350; border-radius: 8px;
                                                  padding: 7px 10px; min-height: 18px; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: #3d4870; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: #565e75; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {CARD_BORDER}; selection-background-color: {ACCENT};
                               padding: 4px; outline: 0; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3a4468; background: {FIELD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QSlider::groove:horizontal {{ height: 6px; background: #2b3350; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {TEXT}; border: 2px solid {ACCENT}; width: 14px; height: 14px; margin: -7px 0;
                              border-radius: 9px; }}
QSlider::handle:horizontal:hover {{ background: white; }}

/* ---- groups, tabs, tables ------------------------------------------------------------- */
QGroupBox {{ border: 1px solid {CARD_BORDER}; border-radius: 12px; margin-top: 16px; padding: 14px 12px 12px 12px;
             background: {PANEL}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {MUTED}; font-weight: 600; }}
QTabWidget::pane {{ border: 0; }}
QTabBar::tab {{ background: transparent; padding: 9px 14px; color: {MUTED}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTableWidget {{ background: {FIELD}; gridline-color: #1f2638; border: 1px solid {CARD_BORDER}; border-radius: 10px; }}
QTableWidget QDoubleSpinBox, QTableWidget QComboBox {{ padding: 2px 4px; border-radius: 4px; }}
QTableWidget::item:selected {{ background: #2c2460; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: 0; border-bottom: 1px solid {CARD_BORDER}; padding: 6px; }}
QPlainTextEdit {{ background: #0b0d12; border: 1px solid {CARD_BORDER}; border-radius: 8px; font-family: Consolas; font-size: 12px; }}
QStatusBar {{ background: {BG}; border-top: 1px solid {CARD_BORDER}; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2c3550; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3b4770; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QMessageBox {{ background: {PANEL}; }}
"""
