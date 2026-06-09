#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import threading
import subprocess
import getpass
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from number_manager import NumberManager

# 新建文档时，顶部预留空白行数。内部会换算成页边距偏移。
DOC_TOP_BLANK_LINES = 20
DOC_TOP_BASE_MARGIN_CM = 1.8
DOC_LINE_HEIGHT_PT = 10.5

# 自动刷新轮询间隔。仅当日志文件变化时才真正刷新。
REFRESH_INTERVAL_MS = 15000

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg": "#0f172a",
    "card": "#1e293b",
    "input": "#334155",
    "border": "#475569",
    "t1": "#f1f5f9",
    "t2": "#94a3b8",
    "t3": "#64748b",
    "accent": "#818cf8",
    "accent_h": "#6366f1",
    "accent_d": "#4f46e5",
    "warn": "#fb923c",
    "warn_h": "#f97316",
    "ok": "#34d399",
    "danger": "#f87171",
    "danger_h": "#ef4444",
    "num_bg": "#1e1b4b",
    "num_fg": "#a5b4fc",
    "row0": "#1e293b",
    "row1": "#253449",
    "head": "#334155",
}


class CompactGUIDev:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("协作编号管理器")
        self.root.geometry("430x720")
        self.root.minsize(400, 600)
        self.root.configure(fg_color=C["bg"])

        self._setup_dpi()
        self.manager = None

        self.last_allocated_number = None
        self.hide_number_after_id = None
        self.running = True
        self.operation_in_progress = False
        self.refresh_in_progress = False
        self.current_logs = []
        self.visible_logs_cache = []
        self.last_log_mtime = None

        self._build_ui()
        self._bind_keys()
        self._set_loading_state()
        threading.Thread(target=self._init_manager_worker, daemon=True).start()

        self.root.after(REFRESH_INTERVAL_MS, self._bg_refresh)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._center()

    def _setup_dpi(self):
        try:
            if sys.platform.startswith("win"):
                import ctypes

                ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    def _build_ui(self):
        wrapper = ctk.CTkFrame(self.root, fg_color=C["bg"], corner_radius=0)
        wrapper.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        self._build_header(wrapper)
        ctk.CTkFrame(wrapper, height=1, fg_color=C["border"]).pack(fill="x", pady=(8, 10))
        self._build_action(wrapper)
        self._build_history(wrapper)

        self.msg_var = ctk.StringVar()
        ctk.CTkLabel(
            wrapper,
            textvariable=self.msg_var,
            font=ctk.CTkFont(size=11),
            text_color=C["ok"],
        ).pack(fill="x", pady=(6, 0))

    def _build_header(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x")

        ctk.CTkLabel(
            bar,
            text="编号生成器",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=16, weight="bold"),
            text_color=C["t1"],
        ).pack(side="left")

        ctk.CTkLabel(
            bar,
            text="Dev",
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=C["accent"],
            text_color="white",
            corner_radius=4,
            padx=5,
            pady=0,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            bar,
            text="⚙",
            width=30,
            height=30,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            hover_color=C["input"],
            text_color=C["t3"],
            corner_radius=6,
            command=self.show_settings,
        ).pack(side="right")

        self.username_var = ctk.StringVar(value=getpass.getuser())
        self.username_entry = ctk.CTkEntry(
            bar,
            textvariable=self.username_var,
            width=90,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=C["input"],
            border_color=C["border"],
            corner_radius=6,
        )
        self.username_entry.pack(side="right", padx=(0, 4))
        self.username_entry.bind("<Return>", lambda _: self._save_user())
        self.username_entry.bind("<FocusOut>", lambda _: self._save_user())

        ctk.CTkLabel(
            bar,
            text="用户",
            font=ctk.CTkFont(size=11),
            text_color=C["t3"],
        ).pack(side="right", padx=(0, 4))

    def _build_action(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=C["card"],
            corner_radius=12,
            border_width=1,
            border_color=C["border"],
        )
        card.pack(fill="x", pady=(0, 10))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)

        self.num_frame = ctk.CTkFrame(inner, fg_color="transparent")

        num_bg = ctk.CTkFrame(self.num_frame, fg_color=C["num_bg"], corner_radius=10)
        num_bg.pack(fill="x", pady=(0, 12))

        self.num_var = ctk.StringVar()
        self.num_label = ctk.CTkLabel(
            num_bg,
            textvariable=self.num_var,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=32, weight="bold"),
            text_color=C["num_fg"],
            cursor="hand2",
        )
        self.num_label.pack(pady=(18, 4))
        self.num_label.bind("<Button-1>", self._copy_number)

        self.copy_hint_label = ctk.CTkLabel(
            num_bg,
            text="点击编号可复制",
            font=ctk.CTkFont(size=11),
            text_color=C["t2"],
        )
        self.copy_hint_label.pack(pady=(0, 12))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack()

        self.get_btn = ctk.CTkButton(
            btn_row,
            text="获取编号",
            command=self.get_number,
            width=150,
            height=40,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold"),
            fg_color=C["accent"],
            hover_color=C["accent_h"],
            corner_radius=10,
        )
        self.get_btn.pack(side="left", padx=(0, 6))

        self.del_btn = ctk.CTkButton(
            btn_row,
            text="撤销",
            command=self.delete_number,
            width=64,
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color=C["warn"],
            hover_color=C["warn_h"],
            corner_radius=10,
        )

        self.open_btn = ctk.CTkButton(
            btn_row,
            text="打开文档",
            command=self._open_current_doc,
            width=92,
            height=40,
            font=ctk.CTkFont(size=12),
            fg_color=C["input"],
            hover_color=C["border"],
            corner_radius=10,
        )

        path_row = ctk.CTkFrame(inner, fg_color="transparent")
        path_row.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            path_row,
            text="路径",
            font=ctk.CTkFont(size=10),
            text_color=C["t3"],
        ).pack(side="left")

        self.path_var = ctk.StringVar()
        path_label = ctk.CTkLabel(
            path_row,
            textvariable=self.path_var,
            font=ctk.CTkFont(size=10),
            text_color=C["accent"],
            cursor="hand2",
        )
        path_label.pack(side="left", padx=(4, 0))
        path_label.bind("<Button-1>", self._open_path)

    def _build_history(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=C["card"],
            corner_radius=12,
            border_width=1,
            border_color=C["border"],
        )
        card.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=(12, 10))

        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header,
            text="历史记录",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            text_color=C["t1"],
        ).pack(side="left")

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            header,
            textvariable=self.search_var,
            placeholder_text="搜索编号...",
            width=120,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color=C["input"],
            border_color=C["border"],
            corner_radius=6,
        )
        self.search_entry.pack(side="left", padx=15)
        self.search_entry.bind("<KeyRelease>", lambda _: self._on_search())

        self.refresh_var = ctk.StringVar()
        ctk.CTkLabel(
            header,
            textvariable=self.refresh_var,
            font=ctk.CTkFont(size=9),
            text_color=C["t3"],
        ).pack(side="right")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "D.Treeview",
            background=C["row0"],
            foreground=C["t1"],
            fieldbackground=C["row0"],
            rowheight=32,
            font=("Microsoft YaHei UI", 9),
            borderwidth=0,
        )
        style.configure(
            "D.Treeview.Heading",
            background=C["head"],
            foreground=C["t2"],
            font=("Microsoft YaHei UI", 9, "bold"),
            relief="flat",
            borderwidth=0,
        )
        style.map("D.Treeview", background=[("selected", C["accent_d"])], foreground=[("selected", "#fff")])
        style.map("D.Treeview.Heading", background=[("active", C["border"])])
        style.layout("D.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        table_frame = tk.Frame(inner, bg=C["row0"], highlightthickness=0, bd=0)
        table_frame.pack(fill="both", expand=True)

        cols = ("编号", "数量", "用户", "时间")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=15, style="D.Treeview")

        widths = {"编号": 80, "数量": 50, "用户": 70, "时间": 150}
        for col in cols:
            self.tree.heading(col, text=col, anchor="center")
            self.tree.column(col, width=widths[col], anchor="center", stretch=True)

        self.tree.tag_configure("even", background=C["row0"])
        self.tree.tag_configure("odd", background=C["row1"])

        scrollbar = ctk.CTkScrollbar(
            table_frame,
            command=self.tree.yview,
            fg_color=C["card"],
            button_color=C["border"],
            button_hover_color=C["t3"],
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._ctx = tk.Menu(
            self.root,
            tearoff=False,
            bg=C["card"],
            fg=C["t1"],
            activebackground=C["accent"],
            activeforeground="white",
            font=("Microsoft YaHei UI", 9),
            relief="flat",
            bd=0,
        )
        self._ctx.add_command(label="打开文档", command=self._open_sel_doc)
        self._ctx.add_command(label="复制编号", command=self._copy_sel)
        self._ctx.add_command(label="删除编号", command=self._del_sel)

        self.tree.bind("<Button-3>", self._on_ctx)
        self.tree.bind("<Double-1>", self._on_double_click)

    def _bind_keys(self):
        self.root.bind_all("<Control-g>", lambda _: self.get_number())
        self.root.bind_all("<F5>", lambda _: self.refresh())
        self.root.bind_all("<Delete>", lambda _: self.delete_number())
        self.root.bind("<FocusIn>", lambda _: self._refresh_table(force=True))

    def _set_loading_state(self):
        self.path_var.set("正在连接共享目录...")
        self.refresh_var.set("初始化中")
        self.get_btn.configure(state="disabled")
        self.username_entry.configure(state="disabled")

    def _init_manager_worker(self):
        try:
            manager = NumberManager()
            self.root.after(0, lambda: self._finish_manager_init(manager))
        except Exception as exc:
            self.root.after(0, lambda: self._handle_manager_init_error(exc))

    def _finish_manager_init(self, manager):
        if not self.running:
            return

        self.manager = manager
        self.username_var.set(manager.username)
        self.username_entry.configure(state="normal")
        self.get_btn.configure(state="normal")
        self.path_var.set(manager.doc_dir)
        self.refresh_var.set("就绪")
        self._msg("共享目录已连接")
        self.load_history()

    def _handle_manager_init_error(self, exc):
        self.path_var.set(f"连接失败: {exc}")
        self.refresh_var.set("连接失败")
        self.get_btn.configure(state="disabled")
        self.username_entry.configure(state="normal")
        self._msg("共享目录连接失败")

    def _ensure_manager_ready(self, show_message=True):
        if self.manager is not None:
            return True
        if show_message:
            self._msg("共享目录未就绪，请稍等")
        return False

    def _center(self):
        self.root.update_idletasks()
        width, height = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = (self.root.winfo_screenheight() - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _save_user(self):
        new_name = self.username_var.get().strip()
        if not self._ensure_manager_ready(show_message=False):
            if not new_name:
                self.username_var.set(getpass.getuser())
            return
        if not new_name:
            self.username_var.set(self.manager.username)
            return
        if new_name != self.manager.username:
            try:
                self.manager.set_username(new_name)
                self._msg(f"用户名已更新: {new_name}")
            except Exception:
                self.username_var.set(self.manager.username)

    def _set_operation_state(self, busy):
        self.operation_in_progress = busy
        self.get_btn.configure(state="disabled" if busy else "normal")
        self.del_btn.configure(state="disabled" if busy else "normal")
        self.open_btn.configure(state="disabled" if busy else "normal")

    def get_number(self):
        if not self._ensure_manager_ready():
            return
        if self.operation_in_progress:
            return
        self._set_operation_state(True)
        threading.Thread(target=self._get_number_worker, daemon=True).start()

    def _get_number_worker(self):
        try:
            number = self.manager.get_next_number()
            doc_path = self._ensure_doc(number)
            self.root.after(0, lambda: self._after_get_number(number, doc_path))
        except Exception as exc:
            self.root.after(0, lambda: self._handle_operation_error(f"获取失败: {exc}"))

    def _after_get_number(self, number, doc_path):
        self.last_allocated_number = number
        self.num_var.set(str(number))

        self.num_frame.pack(fill="x", before=self.get_btn.master)
        self.del_btn.pack(side="left")
        self.open_btn.pack(side="left", padx=(6, 0))

        self._msg(f"获取成功，编号: {number}")
        self._toast(str(number))
        self._refresh_table(force=True)

        if not doc_path:
            self._msg("文档创建失败，可稍后手动打开")

        if self.hide_number_after_id:
            self.root.after_cancel(self.hide_number_after_id)
        self.hide_number_after_id = self.root.after(8000, self._hide_number)
        self._set_operation_state(False)

    def delete_number(self):
        if not self._ensure_manager_ready():
            return
        if self.last_allocated_number is None or self.operation_in_progress:
            return
        if not messagebox.askyesno("确认", f"撤销编号 {self.last_allocated_number}？"):
            return

        self._set_operation_state(True)
        num = self.last_allocated_number
        threading.Thread(target=self._delete_number_worker, args=(num,), daemon=True).start()

    def _delete_number_worker(self, num):
        try:
            self.manager.delete_number(num)
            self._delete_doc(num)
            self.root.after(0, lambda: self._after_delete_number(num))
        except Exception as exc:
            self.root.after(0, lambda: self._handle_operation_error(f"删除失败: {exc}"))

    def _after_delete_number(self, num):
        self._msg(f"编号 {num} 已撤销")
        self._hide_number()
        self._refresh_table(force=True)
        self._set_operation_state(False)

    def _handle_operation_error(self, message):
        self._set_operation_state(False)
        messagebox.showerror("错误", message)

    def _hide_number(self):
        try:
            self.num_frame.pack_forget()
            self.del_btn.pack_forget()
            self.open_btn.pack_forget()
            self.last_allocated_number = None
            self.hide_number_after_id = None
        except Exception:
            pass

    def load_history(self):
        self._refresh_table(force=True)

    def refresh(self):
        if not self._ensure_manager_ready():
            return
        self._refresh_table(force=True)
        self._msg("已刷新")

    def _refresh_table(self, force=False):
        if not self._ensure_manager_ready(show_message=False):
            return
        if self.refresh_in_progress:
            return
        if not force and not self._can_refresh_in_background():
            return

        self.refresh_in_progress = True
        threading.Thread(target=self._refresh_table_worker, args=(force,), daemon=True).start()

    def _refresh_table_worker(self, force):
        manager = self.manager
        if manager is None:
            self.root.after(0, lambda: setattr(self, "refresh_in_progress", False))
            return

        try:
            latest_mtime = self._get_log_mtime_for_manager(manager)
            if not force and latest_mtime == self.last_log_mtime:
                self.root.after(0, self._finish_refresh_no_change)
                return

            logs = manager.get_recent_logs(200)
            doc_dir = manager.doc_dir
            self.root.after(0, lambda: self._apply_refresh_result(logs, latest_mtime, doc_dir))
        except Exception as exc:
            self.root.after(0, lambda: self._apply_refresh_error(exc))

    def _finish_refresh_no_change(self):
        self.refresh_in_progress = False

    def _apply_refresh_result(self, logs, latest_mtime, doc_dir):
        self.refresh_in_progress = False
        self.current_logs = logs
        self.last_log_mtime = latest_mtime
        self.visible_logs_cache = self._build_visible_logs(self.current_logs)
        self._render_table(self._filter_logs(self.visible_logs_cache))
        self.path_var.set(doc_dir)
        self.refresh_var.set(datetime.now().strftime("%H:%M:%S"))

    def _apply_refresh_error(self, exc):
        self.refresh_in_progress = False
        self.path_var.set(f"加载失败: {exc}")
        self.refresh_var.set("刷新失败")

    def _build_visible_logs(self, logs):
        pending_deletes = {}
        visible_logs = []

        for log in reversed(logs):
            number = log.get("number")
            action = log.get("action", "")
            count = log.get("count", 1)

            if action == "delete" or count <= 0:
                pending_deletes[number] = pending_deletes.get(number, 0) + 1
                continue

            if number in pending_deletes and pending_deletes[number] > 0:
                pending_deletes[number] -= 1
                continue

            visible_logs.append(log)

        return visible_logs

    def _filter_logs(self, logs):
        keyword = self.search_var.get().strip()
        if not keyword:
            return logs
        return [log for log in logs if keyword in str(log.get("number", ""))]

    def _render_table(self, logs):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for index, log in enumerate(logs):
            count = log.get("count", 1)
            number_text = str(log["number"])
            if count > 1:
                number_text = f"{log['number']}~{log['number'] + count - 1}"

            tag = "even" if index % 2 == 0 else "odd"
            self.tree.insert(
                "",
                "end",
                values=(number_text, count, log.get("user", ""), f"{log.get('date', '')} {log.get('time', '')}"),
                tags=(tag,),
            )

    def _on_search(self):
        self._render_table(self._filter_logs(self.visible_logs_cache))

    def _get_log_mtime_for_manager(self, manager):
        try:
            if os.path.exists(manager.log_file):
                return os.path.getmtime(manager.log_file)
        except Exception:
            pass
        return None

    def _can_refresh_in_background(self):
        if not self.running or self.operation_in_progress:
            return False
        try:
            if not self.root.winfo_exists() or self.root.state() == "iconic":
                return False
        except Exception:
            return False
        return True

    def _msg(self, text):
        self.msg_var.set(text)
        self.root.after(3000, lambda: self.msg_var.set(""))

    def _toast(self, number_text):
        top = ctk.CTkToplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        width, height = 200, 52
        x = self.root.winfo_x() + self.root.winfo_width() - width - 14
        y = self.root.winfo_y() + 56
        top.geometry(f"{width}x{height}+{x}+{y}")
        top.configure(fg_color=C["accent_d"])

        ctk.CTkLabel(
            top,
            text=f"编号 {number_text}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="white",
        ).pack(expand=True)

        top.attributes("-alpha", 0.0)

        def fade_in(alpha=0.0):
            alpha = min(alpha + 0.2, 1.0)
            try:
                top.attributes("-alpha", alpha)
                if alpha < 1.0:
                    top.after(15, lambda: fade_in(alpha))
            except Exception:
                pass

        fade_in()
        top.after(1800, lambda: self._fade_destroy(top))

    def _fade_destroy(self, widget):
        try:
            alpha = float(widget.attributes("-alpha"))
            if alpha > 0.05:
                widget.attributes("-alpha", alpha - 0.15)
                widget.after(15, lambda: self._fade_destroy(widget))
            else:
                widget.destroy()
        except Exception:
            try:
                widget.destroy()
            except Exception:
                pass

    def _get_doc_path(self, number):
        if not self._ensure_manager_ready():
            return None
        return os.path.join(self.manager.doc_dir, f"{number}.docx")

    def _load_docx_modules(self):
        from docx import Document
        from docx.oxml.ns import qn
        from docx.shared import Cm, Inches, Pt

        return Document, qn, Cm, Inches, Pt

    def _ensure_doc(self, number):
        try:
            path = self._get_doc_path(number)
            if not path:
                return None
            os.makedirs(self.manager.doc_dir, exist_ok=True)

            if os.path.exists(path):
                return path

            Document, qn, Cm, Inches, Pt = self._load_docx_modules()
            doc = Document()
            section = doc.sections[0]
            section.page_width = Inches(8.27)
            section.page_height = Inches(11.69)

            top_margin_pt = DOC_TOP_BASE_MARGIN_CM * 28.35 + DOC_TOP_BLANK_LINES * DOC_LINE_HEIGHT_PT
            section.top_margin = Pt(top_margin_pt)
            section.bottom_margin = Cm(1.6)
            section.left_margin = Cm(2.8)
            section.right_margin = Cm(2.0)

            style = doc.styles["Normal"]
            style.font.name = "Times New Roman"
            style._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            style._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
            style._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
            style._element.rPr.rFonts.set(qn("w:cs"), "Times New Roman")
            style.font.size = Pt(10.5)
            style.paragraph_format.space_before = Pt(0)
            style.paragraph_format.space_after = Pt(0)
            style.paragraph_format.line_spacing = 1.0

            doc.save(path)
            return path
        except Exception as exc:
            self.root.after(0, lambda: self._msg(f"文档创建失败: {exc}"))
            return None

    def _open_doc(self, number):
        path = self._ensure_doc(number)
        if not path:
            return
        try:
            os.startfile(path)
        except Exception as exc:
            self._msg(f"文档打开失败: {exc}")

    def _open_current_doc(self):
        if self.last_allocated_number is None:
            return
        self._open_doc(self.last_allocated_number)

    def _delete_doc(self, number):
        try:
            path = self._get_doc_path(number)
            if not path:
                return
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def _open_doc_by_number(self, number_text):
        text = str(number_text).strip()
        if "~" in text:
            text = text.split("~")[0].strip()
        try:
            number = int(text)
        except ValueError:
            return

        path = self._get_doc_path(number)
        if os.path.exists(path):
            self._open_doc(number)
        else:
            self._msg(f"文档不存在: {number}.docx")

    def _on_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        values = self.tree.item(row, "values")
        if values:
            self._open_doc_by_number(values[0])

    def _open_sel_doc(self):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if values:
            self._open_doc_by_number(values[0])

    def _open_path(self, _event=None):
        path = self.path_var.get().strip()
        if not path or path.startswith(("错误", "加载失败", "刷新失败")):
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def _copy_number(self, _event=None):
        text = self.num_var.get().strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._msg(f"已复制: {text}")

    def _on_ctx(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self._ctx.tk_popup(event.x_root, event.y_root)

    def _copy_sel(self):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if values:
            self.root.clipboard_clear()
            self.root.clipboard_append(str(values[0]))
            self._msg(f"已复制: {values[0]}")

    def _del_sel(self):
        if not self._ensure_manager_ready():
            return
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if not values:
            return

        text = str(values[0]).strip()
        if "~" in text:
            messagebox.showinfo("提示", "仅支持删除单个编号")
            return

        try:
            number = int(text)
        except ValueError:
            return

        if not messagebox.askyesno("确认", f"删除编号 {number}？"):
            return

        try:
            self.manager.delete_number(number)
            self._delete_doc(number)
            self._msg(f"编号 {number} 已删除")
            self._refresh_table(force=True)
        except Exception as exc:
            messagebox.showerror("错误", str(exc))

    def show_settings(self):
        if not self._ensure_manager_ready():
            return
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("设置")
        dialog.geometry("320x240")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=C["bg"])

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 320) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 240) // 2
        dialog.geometry(f"320x240+{x}+{y}")

        card = ctk.CTkFrame(dialog, fg_color=C["card"], corner_radius=12)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            card,
            text="系统设置",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C["t1"],
        ).pack(pady=(16, 12))

        ctk.CTkLabel(
            card,
            text=f"当前起始编号: {self.manager.config['start_number']}",
            font=ctk.CTkFont(size=11),
            text_color=C["t2"],
        ).pack(pady=(0, 8))

        start_var = ctk.StringVar(value=str(self.manager.config["start_number"]))
        ctk.CTkEntry(
            card,
            textvariable=start_var,
            width=140,
            height=34,
            font=ctk.CTkFont(size=12),
            fg_color=C["input"],
            border_color=C["border"],
            corner_radius=8,
            justify="center",
        ).pack(pady=(0, 14))

        def save():
            try:
                number = int(start_var.get())
                if self.manager.config.get("initialized"):
                    if not messagebox.askyesno("确认", f"修改起始编号为 {number}？"):
                        return
                    self.manager.update_start_number(number)
                else:
                    self.manager.set_start_number(number)
                messagebox.showinfo("成功", f"起始编号已设为 {number}")
                dialog.destroy()
                self.refresh()
            except ValueError:
                messagebox.showerror("错误", "请输入有效数字")
            except Exception as exc:
                messagebox.showerror("错误", str(exc))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=24)

        ctk.CTkButton(
            btn_row,
            text="保存",
            command=save,
            width=90,
            height=34,
            fg_color=C["accent"],
            hover_color=C["accent_h"],
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", expand=True, padx=3)

        ctk.CTkButton(
            btn_row,
            text="关闭",
            command=dialog.destroy,
            width=90,
            height=34,
            fg_color=C["input"],
            hover_color=C["border"],
            corner_radius=8,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", expand=True, padx=3)

    def _bg_refresh(self):
        if not self.running:
            return
        try:
            if self._can_refresh_in_background():
                self._refresh_table()
        finally:
            if self.running:
                self.root.after(REFRESH_INTERVAL_MS, self._bg_refresh)

    def on_closing(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = CompactGUIDev()
    app.run()
