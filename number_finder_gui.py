#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外贸客户号码查找工具 - 桌面版 (GUI)
====================================
基于 CustomTkinter 的现代桌面应用，可打包为独立 .exe 分享他人使用。

打包为exe:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name "客户号码查找" --add-data "number_finder.py;." number_finder_gui.py
"""

import sys
import os
import csv
import re
import json
import logging
import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path

# ── 确保能找到同目录的 number_finder ──────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# ── 导入核心模块 ──────────────────────────────────────────
from number_finder import (
    COUNTRIES, DEFAULT_MAX_RESULTS, search_all,
    process_search_results, export_csv, export_excel,
    _IS_WIN, _safe,
)

# ── CustomTkinter ─────────────────────────────────────────
try:
    import customtkinter as ctk
    from customtkinter import filedialog
except ImportError:
    print("请先安装 customtkinter: pip install customtkinter")
    sys.exit(1)

# ── tkinter 组件 ──────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox

# ── 配置 ──────────────────────────────────────────────────
APP_NAME = "文人·外贸客户号码查找工具"
APP_VERSION = "1.0"
SETTINGS_FILE = Path.home() / ".number_finder_settings.json"

# 主题色
COLORS = {
    "primary": "#2F5496",
    "primary_light": "#3A6BC5",
    "success": "#2E7D32",
    "warning": "#E65100",
    "error": "#C62828",
    "bg_dark": "#1a1a2e",
    "card_dark": "#16213e",
}

# ── 国家分组（便于UI展示）────────────────────────────────
COUNTRY_GROUPS = {
    "🌍 欧洲": ["uk", "de", "fr", "es", "it", "pt", "nl", "pl", "se", "ru"],
    "🌎 美洲": ["com", "ca", "mx", "br", "ar", "cl"],
    "🌏 亚太": ["au", "in", "jp", "kr", "tr"],
}


# ═══════════════════════════════════════════════════════════════
# 自定义日志处理器（将日志发送到GUI队列）
# ═══════════════════════════════════════════════════════════════
class GuiLogHandler(logging.Handler):
    """将日志消息发送到GUI队列"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(("log", msg, record.levelname))
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 设置持久化
# ═══════════════════════════════════════════════════════════════
def load_settings() -> dict:
    """加载上次设置"""
    defaults = {
        "keyword": "",
        "countries": ["com", "uk", "de"],
        "engines": ["duckduckgo"],
        "max_results": 20,
        "output_format": "csv",
        "theme": "dark",
    }
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
    except Exception:
        pass
    return defaults


def save_settings(settings: dict):
    """保存设置"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ── 窗口配置 ──
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1150x780")
        self.minsize(950, 680)

        # 设置图标（如果有的话）
        icon_path = SCRIPT_DIR / "icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 1100) // 2
        y = (self.winfo_screenheight() - 750) // 2
        self.geometry(f"+{x}+{y}")

        # ── 加载设置 ──
        self.settings = load_settings()

        # ── 设置主题 ──
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        # ── 搜索线程相关 ──
        self.log_queue = queue.Queue()
        self.search_thread = None
        self.is_searching = False
        self.current_results = []

        # ── 构建UI ──
        self._build_ui()

        # ── 启动日志轮询 ──
        self._poll_log_queue()

    # ═══════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        """构建完整UI"""
        # ── 顶部标题栏 ──
        self._build_header()

        # ── 主内容区（选项卡） ──
        self.tabview = ctk.CTkTabview(self, fg_color="transparent")
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.tab_search = self.tabview.add("  🔍 搜索配置  ")
        self.tab_results = self.tabview.add("  📊 搜索结果  ")

        self._build_search_tab()
        self._build_results_tab()

        # ── 底部状态栏 ──
        self._build_statusbar()

    def _build_header(self):
        """顶部标题栏"""
        self.header_frame = ctk.CTkFrame(self, fg_color=COLORS["primary"], corner_radius=0, height=50)
        pack_args = {"fill": "x", "side": "top"}
        if hasattr(self, 'tabview'):
            pack_args["before"] = self.tabview
        self.header_frame.pack(**pack_args)
        self.header_frame.pack_propagate(False)

        title_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_frame.pack(side="left", padx=20, pady=8)

        ctk.CTkLabel(
            title_frame, text="🔍", font=ctk.CTkFont(size=22)
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            title_frame, text=APP_NAME,
            font=ctk.CTkFont(size=16, weight="bold"), text_color="white"
        ).pack(side="left")

        ctk.CTkLabel(
            title_frame, text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11), text_color="#A0B4D0"
        ).pack(side="left", padx=(8, 0))

        # 右侧：帮助 + 主题切换
        theme_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        theme_frame.pack(side="right", padx=20, pady=8)

        ctk.CTkButton(
            theme_frame, text="❓ 帮助", width=60, height=28,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="gray30", border_width=1, border_color="gray50",
            command=self._open_help,
        ).pack(side="right", padx=(0, 10))

        self.theme_var = ctk.StringVar(value=self.settings.get("theme", "dark"))
        ctk.CTkSegmentedButton(
            theme_frame, values=["dark", "light"],
            variable=self.theme_var,
            command=self._on_theme_change,
        ).pack(side="right")

    def _build_statusbar(self):
        """底部状态栏"""
        self.statusbar = ctk.CTkFrame(self, height=32, corner_radius=0)
        self.statusbar.pack(fill="x", side="bottom")

        self.status_label = ctk.CTkLabel(
            self.statusbar, text="✅ 就绪",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.status_label.pack(side="left", padx=15, pady=3)

        # 联系方式
        self.contact_label = ctk.CTkLabel(
            self.statusbar, text="by 文人  v:wen302561781",
            font=ctk.CTkFont(size=10), text_color="gray"
        )
        self.contact_label.pack(side="left", padx=(5, 0), pady=3)

        self.progress_bar = ctk.CTkProgressBar(self.statusbar, width=200)
        self.progress_bar.pack(side="right", padx=15, pady=5)
        self.progress_bar.set(0)

    # ═══════════════════════════════════════════════════════════
    # 搜索配置页
    # ═══════════════════════════════════════════════════════════

    def _build_search_tab(self):
        """构建搜索配置页面"""
        tab = self.tab_search

        # 左列：关键词+地区（可滚动）
        left = ctk.CTkScrollableFrame(tab, label_text="", width=430)
        left.pack(side="left", fill="both", expand=True, padx=(5, 2), pady=5)

        # 右列：设置+搜索按钮（可滚动，确保所有内容可见）
        right = ctk.CTkScrollableFrame(tab, label_text="", width=380)
        right.pack(side="right", fill="both", expand=True, padx=(2, 5), pady=5)

        # ── 左列：关键词和地区 ──
        kw_frame = ctk.CTkFrame(left, fg_color="transparent")
        kw_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(kw_frame, text="📝 产品关键词", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        self.kw_entry = ctk.CTkEntry(kw_frame, height=38, placeholder_text="例如：steel pipe, LED lights...", font=ctk.CTkFont(size=13))
        self.kw_entry.pack(fill="x", pady=(5, 0))
        self.kw_entry.insert(0, self.settings.get("keyword", ""))

        # 地区
        region_frame = ctk.CTkFrame(left, fg_color="transparent")
        region_frame.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(region_frame, text="🌍 搜索地区", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")

        self.country_vars = {}
        selected_countries = set(self.settings.get("countries", ["com", "uk", "de"]))
        for group_name, codes in COUNTRY_GROUPS.items():
            gf = ctk.CTkFrame(region_frame, fg_color="transparent")
            gf.pack(fill="x", pady=(5, 0))
            ctk.CTkLabel(gf, text=group_name, font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
            cf = ctk.CTkFrame(gf, fg_color="transparent")
            cf.pack(fill="x", pady=(2, 0))
            for code in codes:
                info = COUNTRIES.get(code, {})
                var = ctk.BooleanVar(value=code in selected_countries)
                self.country_vars[code] = var
                ctk.CTkCheckBox(cf, text=f"{info.get('name', code)}({code})", variable=var,
                    font=ctk.CTkFont(size=11), checkbox_width=16, checkbox_height=16, border_width=1,
                ).pack(side="left", padx=(0, 8), pady=2)

        tbf = ctk.CTkFrame(region_frame, fg_color="transparent")
        tbf.pack(fill="x", pady=(5, 0))
        ctk.CTkButton(tbf, text="全选", width=50, height=22, font=ctk.CTkFont(size=11), command=lambda: self._toggle_countries(True)).pack(side="left", padx=(0, 5))
        ctk.CTkButton(tbf, text="取消", width=50, height=22, font=ctk.CTkFont(size=11), fg_color="gray", command=lambda: self._toggle_countries(False)).pack(side="left")

        # ── 右列 ──
        # 搜索引擎
        eng_f = ctk.CTkFrame(right, fg_color="transparent")
        eng_f.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(eng_f, text="🔎 搜索引擎", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        self.engine_vars = {}
        for eng_id, eng_label in [("duckduckgo", "DuckDuckGo (推荐)"), ("google", "Google (需API)"), ("bing", "Bing (需API)")]:
            var = ctk.BooleanVar(value=eng_id in set(self.settings.get("engines", ["duckduckgo"])))
            self.engine_vars[eng_id] = var
            ctk.CTkCheckBox(eng_f, text=eng_label, variable=var, font=ctk.CTkFont(size=12),
                checkbox_width=18, checkbox_height=18, command=self._on_engine_change,
            ).pack(anchor="w", pady=3)
        self.engine_warning = ctk.CTkLabel(eng_f, text="", font=ctk.CTkFont(size=10), text_color=COLORS["warning"])
        self.engine_warning.pack(anchor="w", pady=(2, 0))

        # API密钥（折叠）
        self.api_header = ctk.CTkFrame(right, fg_color="transparent")
        self.api_header.pack(fill="x", padx=15, pady=(10, 0))
        self.api_expand_btn = ctk.CTkButton(self.api_header, text="🔑 API密钥 (可选) ▸", height=28,
            font=ctk.CTkFont(size=12), fg_color="transparent", border_width=1, border_color="gray40",
            command=self._toggle_api_section)
        self.api_expand_btn.pack(fill="x")

        self.api_body = ctk.CTkFrame(right, fg_color="transparent")
        # 默认隐藏
        hint = ctk.CTkLabel(self.api_body, text="Google免费100次/天 | Bing免费1000次/月\n不填则DuckDuckGo完全免费", font=ctk.CTkFont(size=9), text_color="gray")
        hint.pack(anchor="w", pady=(2, 3))

        gf = ctk.CTkFrame(self.api_body, fg_color="transparent"); gf.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(gf, text="Google:", font=ctk.CTkFont(size=11), width=50).pack(side="left")
        self.google_key_var = ctk.StringVar(value=self.settings.get("google_key", ""))
        ctk.CTkEntry(gf, textvariable=self.google_key_var, height=24, font=ctk.CTkFont(size=10), placeholder_text="API Key").pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.google_cx_var = ctk.StringVar(value=self.settings.get("google_cx", ""))
        ctk.CTkEntry(gf, textvariable=self.google_cx_var, height=24, font=ctk.CTkFont(size=10), placeholder_text="CX", width=160).pack(side="left")

        bf = ctk.CTkFrame(self.api_body, fg_color="transparent"); bf.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(bf, text="Bing:", font=ctk.CTkFont(size=11), width=50).pack(side="left")
        self.bing_key_var = ctk.StringVar(value=self.settings.get("bing_key", ""))
        ctk.CTkEntry(bf, textvariable=self.bing_key_var, height=24, font=ctk.CTkFont(size=10), placeholder_text="API Key (Azure)").pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(self.api_body, text="📖 帮助: 点标题栏❓查看图文教程", font=ctk.CTkFont(size=8), text_color="gray").pack(anchor="w", pady=(2, 0))

        # 结果数
        nf = ctk.CTkFrame(right, fg_color="transparent")
        nf.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(nf, text="📊 最大结果数", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        sf = ctk.CTkFrame(nf, fg_color="transparent"); sf.pack(fill="x", pady=(5, 0))
        self.num_var = ctk.IntVar(value=self.settings.get("max_results", 20))
        self.num_slider = ctk.CTkSlider(sf, from_=5, to=100, number_of_steps=19, variable=self.num_var, command=self._on_slider_change, width=250)
        self.num_slider.pack(side="left", padx=(0, 10))
        self.num_label = ctk.CTkLabel(sf, text=str(self.num_var.get()), font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["primary_light"], width=40)
        self.num_label.pack(side="left")

        # 输出格式
        of = ctk.CTkFrame(right, fg_color="transparent")
        of.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(of, text="💾 输出格式", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        self.output_var = ctk.StringVar(value=self.settings.get("output_format", "csv"))
        for val, label in [("csv", "CSV"), ("excel", "Excel"), ("both", "CSV + Excel")]:
            ctk.CTkRadioButton(of, text=label, variable=self.output_var, value=val, font=ctk.CTkFont(size=12), radiobutton_width=16, radiobutton_height=16).pack(anchor="w", pady=2)

        # 输出目录
        df = ctk.CTkFrame(right, fg_color="transparent")
        df.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(df, text="📁 保存目录", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w")
        ds = ctk.CTkFrame(df, fg_color="transparent"); ds.pack(fill="x", pady=(5, 0))
        self.output_dir_var = ctk.StringVar(value=str(SCRIPT_DIR))
        ctk.CTkEntry(ds, textvariable=self.output_dir_var, height=30, font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(ds, text="浏览", width=60, height=30, command=self._browse_output_dir).pack(side="right")

        # ── 搜索按钮（加大，显眼）──
        self.btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=15, pady=(15, 20))

        self.search_btn = ctk.CTkButton(
            self.btn_frame, text="▶  开始搜索", height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=COLORS["success"], hover_color="#1B5E20",
            command=self._start_search,
        )
        self.search_btn.pack(fill="x")

        self.stop_btn = ctk.CTkButton(
            self.btn_frame, text="⏹ 停止搜索", height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["error"], hover_color="#B71C1C",
            command=self._stop_search,
        )

        self._api_expanded = False

    def _toggle_api_section(self):
        """展开/折叠API密钥区域"""
        self._api_expanded = not getattr(self, '_api_expanded', False)
        if self._api_expanded:
            self.api_body.pack(fill="x", padx=15, pady=(5, 0), after=self.api_header)
            self.api_expand_btn.configure(text="🔑 API密钥 (可选) ▾")
        else:
            self.api_body.pack_forget()
            self.api_expand_btn.configure(text="🔑 API密钥 (可选) ▸")

    def _show_search_button(self):
        """显示搜索按钮，隐藏停止按钮（立即反馈）"""
        self.stop_btn.pack_forget()
        self.search_btn.pack(fill="x")
        self.search_btn.configure(state="normal", text="▶  开始搜索")
        self.update_idletasks()

    def _show_stop_button(self):
        """显示停止按钮，隐藏搜索按钮（立即反馈）"""
        self.search_btn.pack_forget()
        self.stop_btn.pack(fill="x")
        self.stop_btn.configure(state="normal", text="⏹ 停止搜索")
        self.update_idletasks()

    # ═══════════════════════════════════════════════════════════
    # 搜索结果页
    # ═══════════════════════════════════════════════════════════

    def _configure_tree_style(self):
        """配置Treeview样式（dark/light）"""
        style = ttk.Style()
        is_dark = self.theme_var.get() == "dark"

        if is_dark:
            bg = "#1e2430"; fg = "#e0e0e0"; sel_bg = "#2F5496"
            sel_fg = "#ffffff"; head_bg = "#2a3040"; head_fg = "#c0c8d0"
            alt_bg = "#252d38"
        else:
            bg = "#ffffff"; fg = "#222222"; sel_bg = "#2F5496"
            sel_fg = "#ffffff"; head_bg = "#e8ecf2"; head_fg = "#333333"
            alt_bg = "#f5f7fa"

        style.configure("Leads.Treeview",
                        background=bg, foreground=fg,
                        fieldbackground=bg, rowheight=28,
                        borderwidth=0, font=("Microsoft YaHei UI", 10))
        style.configure("Leads.Treeview.Heading",
                        background=head_bg, foreground=head_fg,
                        borderwidth=0, font=("Microsoft YaHei UI", 10, "bold"),
                        padding=(6, 4))
        style.map("Leads.Treeview",
                  background=[("selected", sel_bg)],
                  foreground=[("selected", sel_fg)])
        style.map("Leads.Treeview.Heading",
                  background=[("active", head_bg)])
        self._tree_alt_bg = alt_bg

    def _build_results_tab(self):
        """构建搜索结果页面"""
        tab = self.tab_results

        # 工具栏
        toolbar = ctk.CTkFrame(tab, height=40)
        toolbar.pack(fill="x", padx=5, pady=5)

        self.result_count_label = ctk.CTkLabel(
            toolbar, text="等待搜索...",
            font=ctk.CTkFont(size=12)
        )
        self.result_count_label.pack(side="left", padx=10)

        # 引擎状态指示器
        self.engine_status_label = ctk.CTkLabel(
            toolbar, text="",
            font=ctk.CTkFont(size=11)
        )
        self.engine_status_label.pack(side="left", padx=20)

        ctk.CTkButton(
            toolbar, text="📥 导出CSV", width=100, height=30,
            command=lambda: self._export("csv")
        ).pack(side="right", padx=(5, 5))

        ctk.CTkButton(
            toolbar, text="📊 导出Excel", width=100, height=30,
            command=lambda: self._export("excel")
        ).pack(side="right", padx=(0, 5))

        ctk.CTkButton(
            toolbar, text="📋 复制邮箱", width=90, height=30,
            command=self._copy_emails
        ).pack(side="right", padx=(0, 5))

        # 结果表格
        table_frame = ctk.CTkFrame(tab)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 配置 Treeview 样式
        self._configure_tree_style()

        # 使用Treeview显示结果
        columns = ("#", "URL", "标题", "邮箱", "电话")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            selectmode="browse", style="Leads.Treeview",
        )

        col_widths = [40, 200, 250, 200, 180]
        for col, width in zip(columns, col_widths):
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_tree(c))
            self.tree.column(col, width=width, minwidth=30)

        # 滚动条
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # 双击打开URL
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # 详情面板
        detail_frame = ctk.CTkFrame(tab, height=80)
        detail_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.detail_text = ctk.CTkTextbox(detail_frame, height=70, wrap="word")
        self.detail_text.pack(fill="both", padx=5, pady=5)
        self.detail_text.insert("1.0", "选择上方结果行查看详情...")
        self.detail_text.configure(state="disabled")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    # ═══════════════════════════════════════════════════════════
    # 日志轮询
    # ═══════════════════════════════════════════════════════════

    def _poll_log_queue(self):
        """轮询日志队列，更新UI"""
        try:
            while True:
                item = self.log_queue.get_nowait()
                item_type = item[0]
                if item_type == "log":
                    self._update_status(item[1])
                elif item_type == "progress":
                    self.progress_bar.set(item[1])
                elif item_type == "result":
                    self._add_result(item[1])
                elif item_type == "done":
                    self._search_done(item[1])
                elif item_type == "error":
                    self._search_error(item[1])
                elif item_type == "engine_status":
                    self.engine_status_label.configure(text=item[1])
        except queue.Empty:
            pass

        # 继续轮询
        self.after(100, self._poll_log_queue)

    def _update_status(self, msg: str):
        """更新状态栏"""
        # 提取关键信息显示在状态栏
        msg_clean = _safe(msg).replace("\n", " ").strip()
        if len(msg_clean) > 100:
            msg_clean = msg_clean[:97] + "..."
        self.status_label.configure(text=msg_clean)

    # ═══════════════════════════════════════════════════════════
    # 搜索控制
    # ═══════════════════════════════════════════════════════════

    def _get_selected_countries(self) -> list[str]:
        """获取选中的国家代码列表"""
        return [code for code, var in self.country_vars.items() if var.get()]

    def _get_selected_engines(self) -> list[str]:
        """获取选中的搜索引擎列表"""
        return [eng for eng, var in self.engine_vars.items() if var.get()]

    def _start_search(self):
        """开始搜索"""
        keyword = self.kw_entry.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入产品关键词！")
            self.kw_entry.focus()
            return

        countries = self._get_selected_countries()
        if not countries:
            messagebox.showwarning("提示", "请至少选择一个搜索地区！")
            return

        engines = self._get_selected_engines()
        if not engines:
            messagebox.showwarning("提示", "请至少选择一个搜索引擎！")
            return

        # 保存设置
        self.settings.update({
            "keyword": keyword,
            "countries": countries,
            "engines": engines,
            "max_results": self.num_var.get(),
            "output_format": self.output_var.get(),
            "theme": self.theme_var.get(),
            "google_key": self.google_key_var.get().strip(),
            "google_cx": self.google_cx_var.get().strip(),
            "bing_key": self.bing_key_var.get().strip(),
        })
        save_settings(self.settings)

        # 清空旧结果
        self.current_results = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.result_count_label.configure(text="正在搜索...")
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", "搜索中，请稍候...")
        self.detail_text.configure(state="disabled")

        # 更新按钮状态
        self._show_stop_button()
        self.is_searching = True
        self.progress_bar.set(0)
        self.status_label.configure(text="🔍 正在搜索...")

        # 在后台线程中运行
        self.search_thread = threading.Thread(
            target=self._search_worker,
            args=(keyword, countries, engines),
            daemon=True,
        )
        self.search_thread.start()

    def _stop_search(self):
        """停止搜索（即时视觉反馈）"""
        self.is_searching = False
        self.stop_btn.configure(text="⏹ 已停止", state="disabled")
        self.status_label.configure(text="[停止] 搜索已中止")
        self.after(800, self._show_search_button)

    def _search_worker(self, keyword: str, countries: list[str], engines: list[str]):
        """后台搜索工作线程"""
        root_log = logging.getLogger("finder")

        try:
            # 安装GUI日志处理器
            handler = GuiLogHandler(self.log_queue)
            root_log.addHandler(handler)
            root_log.setLevel(logging.INFO)

            max_results = self.num_var.get()

            # 步骤1：搜索（带引擎状态回调）
            self.log_queue.put(("log", "[>] 第一步：搜索引擎搜索...", "INFO"))

            engine_ok = {}  # {engine_name: True/False} — only selected engines
            def on_engine_status(engine, country, ok):
                if engine in engines:
                    engine_ok[engine] = ok or engine_ok.get(engine, False)
                # 只显示选中的引擎状态
                status_parts = []
                for eng_name in engines:
                    if eng_name in engine_ok:
                        status_parts.append(f"{eng_name}=OK" if engine_ok[eng_name] else f"{eng_name}=被拦截")
                    else:
                        status_parts.append(f"{eng_name}=搜索中...")
                self.log_queue.put(("engine_status", " | ".join(status_parts), ""))

            search_results = search_all(
                query=keyword,
                countries=countries,
                engines=engines,
                max_results=min(max_results * 2, 60),
                engine_status_callback=on_engine_status,
                google_api_key=self.google_key_var.get().strip(),
                google_cx=self.google_cx_var.get().strip(),
                bing_api_key=self.bing_key_var.get().strip(),
            )
            self.log_queue.put(("log", f"[OK] 搜索完成，共 {len(search_results)} 条去重结果", "INFO"))

            if not search_results:
                self.log_queue.put(("error", "没有搜索到任何结果"))
                return

            if not self.is_searching:
                return

            # 步骤2：分析网站（使用回调实时推送结果）
            self.log_queue.put(("log", "[#] 第二步：分析网站、提取联系信息...", "INFO"))

            # 定义回调：每找到一个结果就推送到GUI
            def on_result(result, found_count, visited, total):
                if not self.is_searching:
                    return
                self.log_queue.put(("result", result))
                # 更新进度条
                progress = min(1.0, visited / max(total, 1))
                self.log_queue.put(("progress", progress))

            results = process_search_results(
                search_results=search_results,
                keyword=keyword,
                max_sites=max_results,
                result_callback=on_result,
                stop_check=lambda: not self.is_searching,
            )

            if not self.is_searching:
                return

            self.log_queue.put(("done", results))

        except Exception as e:
            self.log_queue.put(("error", f"搜索出错: {e}\n{traceback.format_exc()}"))
        finally:
            root_log.removeHandler(handler)

    def _add_result(self, result: dict):
        """添加一条结果到表格"""
        self.current_results.append(result)

        idx = len(self.current_results)
        domain = result.get("domain", "")
        url = result.get("url", "")
        title = result.get("title", "")[:80]
        emails = "; ".join(result.get("emails", []))
        phones = "; ".join(result.get("phones", []))

        tag = "even" if idx % 2 == 0 else "odd"
        is_dark = self.theme_var.get() == "dark"
        ev_bg = "#252d38" if is_dark else "#f0f4f8"
        od_bg = "#1e2430" if is_dark else "#ffffff"
        fg = "#e0e0e0" if is_dark else "#222222"
        self.tree.tag_configure("even", background=ev_bg, foreground=fg)
        self.tree.tag_configure("odd", background=od_bg, foreground=fg)

        self.tree.insert("", "end", values=(idx, domain, title, emails, phones), tags=(tag,))

        self.result_count_label.configure(text=f"已找到 {idx} 个潜在客户")

    def _search_done(self, results: list):
        """搜索完成"""
        self.is_searching = False
        self._show_search_button()
        self.progress_bar.set(1)
        count = len(results)

        if count > 0:
            self.status_label.configure(text=f"[OK] 完成！共找到 {count} 个潜在客户网站")
            self.result_count_label.configure(text=f"共找到 {count} 个潜在客户网站")
            self.engine_status_label.configure(text="")

            # 自动导出
            keyword = self.kw_entry.get().strip()
            output_dir = self.output_dir_var.get()
            fmt = self.output_var.get()
            try:
                if fmt in ("csv", "both"):
                    path = export_csv(results, keyword, output_dir)
                    self.log_queue.put(("log", f"[=] CSV已保存: {path}", "INFO"))
                if fmt in ("excel", "both"):
                    path = export_excel(results, keyword, output_dir)
                    if path:
                        self.log_queue.put(("log", f"[=] Excel已保存: {path}", "INFO"))
            except Exception as e:
                self.log_queue.put(("log", f"[!!] 导出失败: {e}", "WARNING"))

            # 自动切换到结果页
            self.tabview.set("  📊 搜索结果  ")
        else:
            self.status_label.configure(text=":( 未找到匹配的企业网站")
            self.result_count_label.configure(text="未找到结果")
            # 保留引擎状态，让用户看到哪些引擎被拦截
            current_engine_text = self.engine_status_label.cget("text")
            if "被拦截" in current_engine_text:
                self.engine_status_label.configure(
                    text=current_engine_text + "  [提示：请勾选DuckDuckGo引擎]")

            self.detail_text.configure(state="normal")
            self.detail_text.delete("1.0", "end")
            tips = (
                "未找到匹配的企业网站。建议：\n"
                "1. 确保勾选了 DuckDuckGo 搜索引擎（最稳定，Google/Bing经常被拦截）\n"
                "2. 更换更精准的产品关键词（如加上 manufacturer, supplier, factory）\n"
                "3. 扩大搜索地区范围\n"
                "4. 缩短关键词（1-3个词效果最好）\n"
            )
            self.detail_text.insert("1.0", tips)
            self.detail_text.configure(state="disabled")

    def _search_error(self, msg: str):
        """搜索出错"""
        self.is_searching = False
        self._show_search_button()

        self.status_label.configure(text=f"[X] {msg[:80]}")

    # ═══════════════════════════════════════════════════════════
    # 事件处理
    # ═══════════════════════════════════════════════════════════

    def _on_theme_change(self, value: str):
        """主题切换"""
        ctk.set_appearance_mode(value)
        self.settings["theme"] = value
        save_settings(self.settings)
        # 重新配置表格样式
        if hasattr(self, 'tree'):
            self._configure_tree_style()
            is_dark = value == "dark"
            ev_bg = "#252d38" if is_dark else "#f0f4f8"
            od_bg = "#1e2430" if is_dark else "#ffffff"
            fg = "#e0e0e0" if is_dark else "#222222"
            self.tree.tag_configure("even", background=ev_bg, foreground=fg)
            self.tree.tag_configure("odd", background=od_bg, foreground=fg)

    def _open_help(self):
        """打开API接入指南网页"""
        import webbrowser
        guide_path = SCRIPT_DIR / "api_guide.html"
        if guide_path.exists():
            webbrowser.open(str(guide_path))
        else:
            messagebox.showinfo("帮助", (
                "API密钥申请指南：\n\n"
                "【DuckDuckGo】免费无限，无需密钥，推荐！\n\n"
                "【Google API】免费100次/天\n"
                "  1. 打开 https://programmablesearchengine.google.com/\n"
                "  2. 创建搜索引擎，选'搜索整个网络'\n"
                "  3. 获取 CX 和 API Key\n\n"
                "【Bing API】免费1000次/月\n"
                "  1. 打开 https://portal.azure.com\n"
                "  2. 创建 Bing Search v7 资源，选 F0 免费层\n"
                "  3. 在'密钥和终结点'获取 Key\n\n"
                "详细图文教程请查看 api_guide.html"
            ))

    def _on_engine_change(self):
        """引擎选择变更时检查并显示警告"""
        if not self.engine_vars.get("duckduckgo", ctk.BooleanVar(value=True)).get():
            self.engine_warning.configure(
                text="[!!] 建议勾选DuckDuckGo（最稳定），Google和Bing经常被拦截"
            )
        else:
            self.engine_warning.configure(text="")

    def _on_slider_change(self, value):
        """滑块值变化"""
        v = int(float(value))
        self.num_label.configure(text=str(v))

    def _toggle_countries(self, select_all: bool):
        """全选/取消国家"""
        for var in self.country_vars.values():
            var.set(select_all)

    def _browse_output_dir(self):
        """选择输出目录"""
        path = filedialog.askdirectory(title="选择保存目录")
        if path:
            self.output_dir_var.set(path)

    def _on_tree_select(self, event):
        """表格行选择事件"""
        selection = self.tree.selection()
        if not selection:
            return

        idx = int(self.tree.item(selection[0], "values")[0]) - 1
        if 0 <= idx < len(self.current_results):
            r = self.current_results[idx]
            detail = (
                f"网址: {r.get('url', '')}\n"
                f"邮箱: {'; '.join(r.get('emails', [])) or '无'}\n"
                f"电话: {'; '.join(r.get('phones', [])) or '无'}\n"
                f"来源: {r.get('search_engine', '?')} | "
                f"地区: {r.get('search_country', '?')} | "
                f"发现: {r.get('found_at', '?')}"
            )
            self.detail_text.configure(state="normal")
            self.detail_text.delete("1.0", "end")
            self.detail_text.insert("1.0", detail)
            self.detail_text.configure(state="disabled")

    def _on_tree_double_click(self, event):
        """双击打开URL"""
        selection = self.tree.selection()
        if not selection:
            return
        idx = int(self.tree.item(selection[0], "values")[0]) - 1
        if 0 <= idx < len(self.current_results):
            url = self.current_results[idx].get("url", "")
            if url:
                import webbrowser
                webbrowser.open(url)

    def _sort_tree(self, col: str):
        """排序表格"""
        # 获取当前数据
        data = [(self.tree.item(child, "values"), child) for child in self.tree.get_children("")]

        # 确定排序的列索引
        col_map = {"#": 0, "URL": 1, "标题": 2, "邮箱": 3, "电话": 4}
        idx = col_map.get(col, 0)

        # 排序（支持数字和字符串）
        reverse = getattr(self, "_sort_reverse", False)
        try:
            data.sort(key=lambda x: int(x[0][idx]) if idx == 0 else str(x[0][idx]).lower(), reverse=reverse)
        except Exception:
            data.sort(key=lambda x: str(x[0][idx]).lower(), reverse=reverse)

        self._sort_reverse = not reverse

        # 重新排列
        for i, (_, child) in enumerate(data):
            self.tree.move(child, "", i)

    def _export(self, fmt: str):
        """导出结果"""
        if not self.current_results:
            messagebox.showinfo("提示", "没有可导出的结果！")
            return

        keyword = self.kw_entry.get().strip() or "export"
        output_dir = self.output_dir_var.get()

        try:
            if fmt == "csv":
                path = export_csv(self.current_results, keyword, output_dir)
                messagebox.showinfo("导出成功", f"CSV文件已保存到:\n{path}")
            elif fmt == "excel":
                path = export_excel(self.current_results, keyword, output_dir)
                if path:
                    messagebox.showinfo("导出成功", f"Excel文件已保存到:\n{path}")
                else:
                    messagebox.showwarning("导出失败", "请先安装 openpyxl:\npip install openpyxl")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _copy_emails(self):
        """复制所有邮箱到剪贴板"""
        all_emails = []
        for r in self.current_results:
            all_emails.extend(r.get("emails", []))

        if not all_emails:
            messagebox.showinfo("提示", "没有邮箱可复制！")
            return

        text = "\n".join(all_emails)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("复制成功", f"已复制 {len(all_emails)} 个邮箱到剪贴板！")


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

def main():
    # Windows DPI适配
    if _IS_WIN:
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
