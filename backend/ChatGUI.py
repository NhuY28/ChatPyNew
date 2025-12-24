# ChatGUI.py
import os
import queue
import tkinter as tk
import base64

import sounddevice as sd
import tempfile
import threading
import numpy as np
import time
import pygame
import wave
from app.VoiceCall import VoiceCall

from pathlib import Path
from tkinter import messagebox, filedialog

from PIL import Image, ImageTk, ImageDraw
from chatclient import ChatClient


class ChatGUI:
    def __init__(self, root=None):
        if root is None:
            self.root = tk.Tk()
            self.is_main = True
        else:
            self.root = tk.Toplevel(root)
            self.is_main = False

        self.root.title("ChatPy - Đăng nhập/Đăng ký")
        self.root.geometry("900x550")
        self.root.config(bg="#f5f5f5")

        self.client = ChatClient()
        self.username = None
        self.avatar_path = None
        self.user_avatars = {}    # dict username -> avatar_path
        self.current_users = []   # latest user list from server
        self.pending_users = []   # if update arrives before UI created
        self.current_chat_user = None

        # Quản lý nhiều khung chat
        self.chat_frames = {}     # username -> Frame
        self.unread_count = {}    # username -> số tin chưa đọc

        # --- Load icon ---
        # Ensure these files exist or replace with your own icons
        self.icon_user = ImageTk.PhotoImage(Image.open("username.png").resize((20, 20)))
        self.icon_pass = ImageTk.PhotoImage(Image.open("password.png").resize((20, 20)))
        self.icon_folder = ImageTk.PhotoImage(Image.open("folder.png").resize((20, 20)))

        self.show_register()

        if self.is_main:
            self.root.mainloop()

    # ------------------- ĐĂNG KÝ -------------------
    def show_register(self):
        self.clear_window()

        lbl_title = tk.Label(self.root, text="TẠO TÀI KHOẢN",
                             font=("Arial", 18, "bold"), bg="#f5f5f5", fg="#333")
        lbl_title.pack(pady=20)

        # --- Avatar ---
        self.avatar_frame = tk.Frame(self.root, bg="#f5f5f5")
        self.avatar_frame.pack(pady=10)

        self.avatar_image = ImageTk.PhotoImage(Image.open("folder.png").resize((40, 40)))
        self.avatar_label = tk.Label(self.avatar_frame, image=self.avatar_image, bg="#f5f5f5", cursor="hand2")
        self.avatar_label.pack()
        self.avatar_label.bind("<Button-1>", lambda e: self.choose_avatar())

        # Username
        frame_user = tk.Frame(self.root, bg="#f5f5f5")
        frame_user.pack(pady=10, padx=40, fill="x")
        tk.Label(frame_user, image=self.icon_user, bg="#f5f5f5").pack(side="left", padx=5)
        self.entry_user = tk.Entry(frame_user, font=("Arial", 16))
        self.entry_user.pack(side="left", fill="x", expand=True)

        # Password
        frame_pass = tk.Frame(self.root, bg="#f5f5f5")
        frame_pass.pack(pady=10, padx=40, fill="x")
        tk.Label(frame_pass, image=self.icon_pass, bg="#f5f5f5").pack(side="left", padx=5)
        self.entry_pass = tk.Entry(frame_pass, font=("Arial", 16), show="*")
        self.entry_pass.pack(side="left", fill="x", expand=True)

        # Confirm password
        frame_confirm = tk.Frame(self.root, bg="#f5f5f5")
        frame_confirm.pack(pady=10, padx=40, fill="x")
        tk.Label(frame_confirm, image=self.icon_pass, bg="#f5f5f5").pack(side="left", padx=5)
        self.entry_confirm = tk.Entry(frame_confirm, font=("Arial", 16), show="*")
        self.entry_confirm.pack(side="left", fill="x", expand=True)

        btn_register = tk.Button(self.root, text="Đăng ký", bg="#6a5acd", fg="white",
                                 font=("Arial", 12, "bold"), command=self.do_register)
        btn_register.pack(pady=20)

        lbl_login = tk.Label(self.root, text="Bạn đã có tài khoản? Đăng nhập ngay",
                             fg="red", bg="#f5f5f5", cursor="hand2", font=("Arial", 10, "underline"))
        lbl_login.pack()
        lbl_login.bind("<Button-1>", lambda e: self.show_login())

    def do_register(self):
        user = self.entry_user.get()
        pw = self.entry_pass.get()
        cf = self.entry_confirm.get()
        if pw != cf:
            messagebox.showerror("Lỗi", "Mật khẩu không khớp!")
            return
        avatar = self.avatar_path if self.avatar_path else "avatars/default.jpg"

        # connect and register
        self.client.connect()
        self.client.on_message = self.handle_server_message
        # original ChatClient.register expects "REGISTER|user|pw\n"
        self.client.register(user, pw, avatar)

    def choose_avatar(self):
        file = filedialog.askopenfilename(filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
        if file:
            img = Image.open(file).resize((90, 90))
            self.avatar_image = ImageTk.PhotoImage(img)
            self.avatar_label.config(image=self.avatar_image)
            self.avatar_path = file

    # ------------------- ĐĂNG NHẬP -------------------
    def show_login(self):
        self.clear_window()

        lbl_title = tk.Label(self.root, text="ĐĂNG NHẬP",
                             font=("Arial", 18, "bold"), bg="#f5f5f5", fg="#333")
        lbl_title.pack(pady=20)

        frame_user = tk.Frame(self.root, bg="#f5f5f5")
        frame_user.pack(pady=10, padx=40, fill="x")
        tk.Label(frame_user, image=self.icon_user, bg="#f5f5f5").pack(side="left", padx=5)
        self.login_user = tk.Entry(frame_user, font=("Arial", 14))
        self.login_user.pack(side="left", fill="x", expand=True)

        frame_pass = tk.Frame(self.root, bg="#f5f5f5")
        frame_pass.pack(pady=10, padx=40, fill="x")
        tk.Label(frame_pass, image=self.icon_pass, bg="#f5f5f5").pack(side="left", padx=5)
        self.login_pass = tk.Entry(frame_pass, font=("Arial", 14), show="*")
        self.login_pass.pack(side="left", fill="x", expand=True)

        btn_login = tk.Button(self.root, text="Đăng nhập", bg="#228B22", fg="white",
                              font=("Arial", 12, "bold"), command=self.do_login)
        btn_login.pack(pady=20)

        lbl_register = tk.Label(self.root, text="Chưa có tài khoản? Đăng ký ngay",
                                fg="blue", bg="#f5f5f5", cursor="hand2", font=("Arial", 10, "underline"))
        lbl_register.pack()
        lbl_register.bind("<Button-1>", lambda e: self.show_register())

    def do_login(self):
        user = self.login_user.get()
        pw = self.login_pass.get()
        self.client.connect()
        self.username = user
        self.client.on_message = self.handle_server_message
        self.client.login(user, pw)

    # ------------------- CỬA SỔ CHAT -------------------
    def show_chat(self, chat_frame=None):
        self.clear_window()
        self.root.title(f"ChatPy - {self.username}")

        main_frame = tk.Frame(self.root, bg="#f5f5f5")
        main_frame.pack(fill="both", expand=True)

        # --- Khung danh sách user online (bên trái) ---
        self.user_frame = tk.Frame(main_frame, width=150, bg="#e0e0e0")
        self.user_frame.pack(side="left", fill="y")
        self.user_frame.pack_propagate(False)  # không cho co giãn theo widget con

        tk.Label(self.user_frame, text="👥 Online", bg="#e0e0e0",
                 font=("Arial", 12, "bold")).pack(pady=5)

        btn_create_group = tk.Button(
            self.user_frame,
            text="➕ Tạo nhóm",
            bg="#ffa500",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            cursor="hand2",
            command=self.create_group_window  # hàm sẽ tạo sau
        )
        btn_create_group.pack(pady=5)

        # Container chứa danh sách user
        self.user_list_container = tk.Frame(self.user_frame, bg="#e0e0e0")
        self.user_list_container.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Khung trò chuyện (bên phải) ---
        self.chat_frame = tk.Frame(main_frame, bg="#f5f5f5")
        self.chat_frame.pack(side="right", fill="both", expand=True)

        # Header khung chat (hiển thị tên và avatar user đang chat)
        self.chat_header = tk.Frame(self.chat_frame, bg="#ddd", height=50)
        self.chat_header.pack(fill="x")
        self.chat_header.pack_propagate(False)

        self.chat_header_avatar = tk.Label(self.chat_header, bg="#ddd")
        self.chat_header_avatar.pack(side="left", padx=10)

        self.chat_header_name = tk.Label(self.chat_header, text="Chọn người để chat",
                                         font=("Arial", 12, "bold"), bg="#ddd", anchor="w")
        self.chat_header_name.pack(side="left", padx=5)

        # Nút gọi (Call)
        btn_call = tk.Button(
                self.chat_header,
                text="📞 Call",
                bg="#4CAF50",
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                cursor="hand2",
                command=self.start_call  # hàm bạn sẽ tự định nghĩa ở dưới
        )
        btn_call.pack(side="right", padx=10, pady=5)

        btn_video = tk.Button(
            self.chat_header,
            text="📹 Video",
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            cursor="hand2",
            command=self.start_video_call  # hàm bạn sẽ tự định nghĩa ở dưới
        )
        btn_video.pack(side="right", padx=10, pady=5)


        # --- Khung hiển thị tin nhắn ---
        chat_display = tk.Frame(self.chat_frame, bg="#f5f5f5")
        chat_display.pack(fill="both", expand=True)

        self.chat_canvas = tk.Canvas(chat_display, bg="#f5f5f5", highlightthickness=0)
        self.chat_scrollbar = tk.Scrollbar(chat_display, orient="vertical", command=self.chat_canvas.yview)
        self.chat_canvas.configure(yscrollcommand=self.chat_scrollbar.set)

        self.chat_canvas.pack(side="left", fill="both", expand=True)
        self.chat_scrollbar.pack(side="right", fill="y")

        self.chat_inner = tk.Frame(self.chat_canvas, bg="#f5f5f5")

        # Gán ID để có thể config lại width sau này
        self.chat_window = self.chat_canvas.create_window((0, 0), window=self.chat_inner, anchor="nw")

        # Khi canvas thay đổi kích thước, cập nhật width cho chat_inner
        def resize_inner(event):
            self.chat_canvas.itemconfig(self.chat_window, width=event.width)

        self.chat_canvas.bind("<Configure>", resize_inner)

        self.chat_inner.bind(
            "<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        )

        # --- Khung nhập tin nhắn ---
        frame_bottom = tk.Frame(self.chat_frame, bg="#ddd", height=45)
        frame_bottom.pack(fill="x", side="bottom")
        frame_bottom.pack_propagate(False)

        self.entry_msg = tk.Entry(frame_bottom, font=("Arial", 12))
        self.entry_msg.pack(side="left", fill="x", expand=True, padx=5, ipady=3)

        # Nút emoji
        btn_emoji = tk.Button(frame_bottom, text="😊", font=("Arial", 14), command=self.show_emoji_picker)
        btn_emoji.pack(side="left", padx=5)

        btn_send = tk.Button(frame_bottom, text="Gửi", command=self.send_message,
                             bg="#6a5acd", fg="white")
        btn_send.pack(side="left", padx=5)

        btn_img = tk.Button(frame_bottom, text="📷 Ảnh", command=self.send_image)
        btn_img.pack(side="left", padx=5)

        btn_file = tk.Button(frame_bottom, text="📂 File", command=self.send_file)
        btn_file.pack(side="left", padx=5)

        btn_voice = tk.Button(frame_bottom, text="🎙 Voice", command=self.record_voice)
        btn_voice.pack(side="left", padx=5)

        # Nếu đã nhận danh sách user trước đó thì hiển thị luôn
        if self.pending_users:
            self.update_user_list(self.pending_users)
            self.pending_users = []

    # ------------------- Cập nhật danh sách user online -------------------
    def update_user_list(self, users):
        self.current_users = users

        # If UI not ready yet -> store pending
        if not hasattr(self, "user_list_container"):
            self.pending_users = users
            return

        # Clear and render
        for widget in self.user_list_container.winfo_children():
            widget.destroy()

        # -------- Danh sách người dùng --------
        for u in users:
            if u == self.username:
                continue

            frame = tk.Frame(self.user_list_container, bg="#e0e0e0", pady=5)
            frame.pack(fill="x", padx=5, pady=2)

            avatar_path = self.user_avatars.get(u, "avatars/default.jpg")
            avatar_img = self.create_circle_avatar(avatar_path, size=36)
            lbl_avatar = tk.Label(frame, image=avatar_img, bg="#e0e0e0")
            lbl_avatar.image = avatar_img
            lbl_avatar.pack(side="left", padx=8)

            lbl_name = tk.Label(frame, text=u, bg="#e0e0e0", font=("Arial", 11))
            lbl_name.pack(side="left", padx=6)

            # Badge số tin nhắn chưa đọc
            count = self.unread_count.get(u, 0)
            if count > 0:
                lbl_notify = tk.Label(frame, text=str(count), fg="white", bg="red", font=("Arial", 9, "bold"))
                lbl_notify.pack(side="right", padx=5)

            # Bind click to the whole row
            frame.bind("<Button-1>", lambda e, user=u: self.select_chat_user(user))
            lbl_avatar.bind("<Button-1>", lambda e, user=u: self.select_chat_user(user))
            lbl_name.bind("<Button-1>", lambda e, user=u: self.select_chat_user(user))

        # -------- Hiển thị nhóm chat --------
        if hasattr(self, "user_groups") and self.user_groups:
            lbl_group_title = tk.Label(self.user_list_container, text="Nhóm của bạn:",
                                       bg="#e0e0e0", fg="black", font=("Arial", 11, "bold"))
            lbl_group_title.pack(fill="x", pady=(10, 2))

            for g in self.user_groups:
                # Khung chứa từng nhóm
                frame = tk.Frame(self.user_list_container, bg="#e0e0e0", pady=3)
                frame.pack(fill="x", padx=5, pady=1)

                lbl_name = tk.Label(frame, text=f"👥 {g}", anchor="w",
                                    bg="#e0e0e0", font=("Arial", 11))
                lbl_name.pack(side="left", padx=8)

                # 🔴 Hiển thị badge số tin chưa đọc (nếu có)
                count = self.unread_count.get(g, 0)
                if count > 0:
                    lbl_notify = tk.Label(frame, text=str(count), fg="white", bg="red",
                                          font=("Arial", 9, "bold"), width=2)
                    lbl_notify.pack(side="right", padx=6)

                # Gắn click để mở nhóm
                frame.bind("<Button-1>", lambda e, name=g: self.select_chat_user(name))
                lbl_name.bind("<Button-1>", lambda e, name=g: self.select_chat_user(name))

    # ------------------- Chọn người để chat -------------------
    def select_chat_user(self, user):
        # Nếu đang chọn cùng user -> bỏ chọn và quay về broadcast
        if self.current_chat_user == user:
            self.current_chat_user = None
            self.root.title(f"ChatPy - {self.username} (broadcast)")
            self.chat_header_name.config(text="🌐 Broadcast (Toàn server)")
            self.chat_header_avatar.config(image="")
            self.chat_header_avatar.image = None

            # Ẩn tất cả frame cũ
            for f in self.chat_frames.values():
                f.pack_forget()

            # Hiển thị lại frame broadcast (ALL)
            if "ALL" not in self.chat_frames:
                frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                frame.pack(fill="both", expand=True)
                self.chat_frames["ALL"] = frame
            else:
                self.chat_frames["ALL"].pack(fill="both", expand=True)

            self.messages_frame = self.chat_frames["ALL"]
            return

        # Bình thường: chọn user để chat riêng
        self.current_chat_user = user
        self.root.title(f"ChatPy - {self.username} (chat với {user})")

        # Cập nhật header
        avatar_path = self.user_avatars.get(user, "avatars/default.jpg")
        avatar_img = self.create_circle_avatar(avatar_path, size=36)
        self.chat_header_avatar.config(image=avatar_img)
        self.chat_header_avatar.image = avatar_img
        self.chat_header_name.config(text=user)

        # 👉 Nếu là nhóm thì thêm nút "Rời nhóm"
        if user in getattr(self, "user_groups", []):
            if hasattr(self, "btn_leave_group") and self.btn_leave_group:
                self.btn_leave_group.destroy()

            def confirm_leave_group(g=user):
                ans = messagebox.askyesno("Rời nhóm", f"Bạn có chắc muốn rời nhóm '{g}' không?")
                if ans:
                    try:
                        self.client.send(f"GROUP_LEAVE|{g}\n")
                        if g in self.chat_frames:
                            frame = self.chat_frames[g]
                            lbl = tk.Label(frame, text="(Bạn đã rời nhóm này)",
                                           bg="#f5f5f5", fg="gray",
                                           font=("Arial", 12, "italic"))
                            lbl.pack(pady=20)
                            self.entry_msg.delete(0, "end")
                            self.entry_msg.config(state="disabled")
                    except Exception as e:
                        messagebox.showerror("Lỗi", f"Không gửi được yêu cầu rời nhóm: {e}")

            self.btn_leave_group = tk.Button(
                self.chat_header,
                text="Rời nhóm",
                bg="#ff6666", fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                command=confirm_leave_group
            )
            self.btn_leave_group.pack(side="right", padx=10)
        else:
            if hasattr(self, "btn_leave_group") and self.btn_leave_group:
                self.btn_leave_group.destroy()

        # Ẩn tất cả frame cũ
        for f in self.chat_frames.values():
            f.pack_forget()

        # Tạo frame mới nếu chưa có
        if user not in self.chat_frames:
            frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
            frame.pack(fill="both", expand=True)
            self.chat_frames[user] = frame
        else:
            self.chat_frames[user].pack(fill="both", expand=True)

        self.messages_frame = self.chat_frames[user]

        # Reset tin nhắn chưa đọc
        self.unread_count[user] = 0
        self.update_user_list(self.current_users)

    # ------------------- Gửi tin nhắn -------------------
    def send_message(self):
        text = self.entry_msg.get().strip()
        if not text:
            return

        if self.current_chat_user:
            # send private message to the selected user
            try:
                self.client.send_private_message(self.current_chat_user, text)
            except Exception:
                # Nếu ChatClient không hỗ trợ send_private_message thì bỏ qua luôn
                pass

            # show locally in the correct chat frame
            self.show_message(self.username, text, self.avatar_path, target_user=self.current_chat_user)

        if self.current_chat_user:
            try:
                # Kiểm tra xem có phải nhóm không? Server định nghĩa GROUP|group_name|message
                if self.current_chat_user in self.chat_frames and self.current_chat_user not in self.current_users:
                    self.client.send(f"GROUP_MSG|{self.current_chat_user}|{text}\n")
                else:
                    self.client.send_private_message(self.current_chat_user, text)
            except Exception:
                pass
                self.show_message(self.username, text, self.avatar_path, target_user=self.current_chat_user)

        else:
            # no selected user -> broadcast (if supported)
            try:
                self.client.send_message(text)
            except Exception:
                try:
                    self.client.send(f"MSG|{self.username}|{text}\n")
                except Exception:
                    pass
            # Show in ALL frame
            self.show_message(self.username, text, self.avatar_path, target_user="ALL")

        self.entry_msg.delete(0, tk.END)

    def show_emoji_picker(self):
        """Hiển thị cửa sổ chọn emoji (có thanh cuộn hoạt động và nằm ngay trên nút emoji)"""
        emojis = [
            "😀","😁","😂","🤣","😊","😍","😎","😘","🥰","😢","😭","😡","😱","👍","🙏","🎉",
            "❤️","🔥","💯","🌹","🎂","✨","😴","🤔","😅","😆","😇","😋","😏","😜","😬","😴",
            "😪","😷","🤒","🤕","🤢","🤮","🤧","🥵","🥶","😵","🤯","🤠","🥳","🤡","👻","💀",
            "👽","👋","🤚","🖐","✋","🖖","👌","🤌","🤏","✌","🤞","🤟","🤘","🤙","👈","👉",
            "👆","👇","☝","👍","👎","✊","👊","🤛","🤜","👏","🙌","👐","🤲","🤝"
        ]

        picker = tk.Toplevel(self.root)
        picker.title("Chọn emoji")
        picker.config(bg="#fff")
        picker.resizable(False, False)

        # --- Đặt vị trí cửa sổ ngay trên khung chat ---
        picker_width = 300
        picker_height = 200
        try:
            # Lấy vị trí cửa sổ chính
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_width = self.root.winfo_width()
            root_height = self.root.winfo_height()
            x = root_x + root_width - picker_width - 40
            y = root_y + root_height - picker_height - 120
        except Exception:
            x = self.root.winfo_pointerx() - 150
            y = self.root.winfo_pointery() - 150

        picker.geometry(f"{picker_width}x{picker_height}+{x}+{y}")

        # --- Canvas + Scrollbar ---
        canvas = tk.Canvas(picker, bg="#fff", highlightthickness=0)
        scrollbar = tk.Scrollbar(picker, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#fff")

        # Cho phép canvas cuộn theo vùng chứa emoji
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Đặt kích thước cố định cho canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- Bật cuộn bằng bánh xe chuột ---
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))  # Linux
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))   # Linux

        # --- Hiển thị emoji theo lưới ---
        col = 0
        row = 0
        for emo in emojis:
            btn = tk.Button(
                scroll_frame, text=emo, font=("Segoe UI Emoji", 16),
                width=3, relief="flat", bg="#fff", cursor="hand2",
                command=lambda e=emo: self.insert_emoji(e, picker)
            )

            # Hiệu ứng hover cho đẹp
            def on_enter(e, b=btn): b.config(bg="#e0e0e0")
            def on_leave(e, b=btn): b.config(bg="#fff")
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)

            btn.grid(row=row, column=col, padx=3, pady=3)
            col += 1
            if col >= 8:
                col = 0
                row += 1

    def send_image(self):
        target = self.current_chat_user or "ALL"
        file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif")])
        if not file_path:
            return

        with open(file_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        filename = os.path.basename(file_path)

        # 🧠 Phân loại kiểu gửi
        if target == "ALL":
            # server expects IMG|ALL|filename|b64
            msg = f"IMG|ALL|{filename}|{b64_data}\n"
        elif target in getattr(self, "user_groups", []):
            # server expects GROUP_IMG|group_name|filename|b64
            msg = f"GROUP_IMG|{target}|{filename}|{b64_data}\n"
        else:
            # private: IMG|username|filename|b64
            msg = f"IMG|{target}|{filename}|{b64_data}\n"

        try:
            self.client.send(msg)
            # Hiển thị luôn hình ảnh bên phía người gửi
            self.show_image_message(self.username, file_path, target_user=target)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Gửi ảnh thất bại: {e}")

    def show_image_message(self, sender, filepath, target_user=None):
        if target_user is None:
            target_user = sender

        if target_user not in self.chat_frames:
            frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
            frame.pack(fill="both", expand=True)
            self.chat_frames[target_user] = frame
        else:
            frame = self.chat_frames[target_user]

        avatar_img = self.create_circle_avatar(
            self.user_avatars.get(sender, "avatars/default.jpg") if sender != self.username else self.avatar_path,
            size=36
        )

        outer_frame = tk.Frame(frame, bg="#f5f5f5")
        outer_frame.pack(fill="x", pady=5, padx=10)
        msg_container = tk.Frame(outer_frame, bg="#f5f5f5")
        msg_container.pack(anchor="w" if sender != self.username else "e")

        lbl_avatar = tk.Label(msg_container, image=avatar_img, bg="#f5f5f5")
        lbl_avatar.image = avatar_img
        lbl_avatar.pack(side="left" if sender != self.username else "right", padx=5)

        try:
            img = Image.open(filepath)
            img.thumbnail((200, 200))
            photo = ImageTk.PhotoImage(img)
        except Exception:
            lbl = tk.Label(msg_container, text=f"[Ảnh lỗi: {os.path.basename(filepath)}]", bg="#f0f0f0")
            lbl.pack(side="left")
            return

        lbl_img = tk.Label(msg_container, image=photo, bg="#f0f0f0", cursor="hand2", bd=1, relief="solid")
        lbl_img.image = photo
        lbl_img.pack(side="left" if sender != self.username else "right")
        lbl_img.bind("<Button-1>", lambda e: self.show_full_image(filepath))

        self.chat_canvas.update_idletasks()

        display_target = target_user if target_user is not None else sender

        # 🔹 Chỉ tăng unread nếu sender khác mình
        if sender != self.username:
            # Chỉ tăng nếu người dùng không đang chat với target
            if self.current_chat_user != display_target:
                self.unread_count[display_target] = self.unread_count.get(display_target, 0) + 1
                self.root.after(0, lambda: self.update_user_list(self.current_users))
        else:
            # Nếu sender là chính mình -> không tăng unread_count
            pass

        # Auto scroll nếu đang chat với target
        if self.current_chat_user == display_target:
            self.chat_canvas.yview_moveto(1.0)

        else:
            # Nếu sender là chính mình -> auto scroll
            if self.current_chat_user == display_target:
                self.chat_canvas.yview_moveto(1.0)
    def insert_emoji(self, emoji, picker_window=None):
        """Chèn emoji vào ô nhập tin nhắn"""
        self.entry_msg.insert(tk.END, emoji)
        if picker_window:
            picker_window.destroy()

    def show_full_image(self, filepath):
        if not os.path.exists(filepath):
            return
        top = tk.Toplevel(self.root)
        top.title("Xem ảnh")
        img = Image.open(filepath)
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(top, image=photo)
        lbl.image = photo
        lbl.pack()
    def send_file(self):
        target = self.current_chat_user or "ALL"
        file_path = filedialog.askopenfilename()
        if not file_path:
            return

        with open(file_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        filename = os.path.basename(file_path)

        # Gửi theo format mà server hiện tại xử lý:
        # - Private / Broadcast: FILE|<target>|<filename>|<b64>\n
        # - Group: GROUP_FILE|<group>|<filename>|<b64>\n
        try:
            if target == "ALL":
                msg = f"FILE|ALL|{filename}|{b64_data}\n"
                self.client.send(msg)
                # Hiển thị local trên frame ALL
                self.show_file_message(self.username, file_path, target_user="ALL")
            elif hasattr(self, "user_groups") and target in self.user_groups:
                # group
                msg = f"GROUP_FILE|{target}|{filename}|{b64_data}\n"
                self.client.send(msg)
                # Hiển thị local trên khung nhóm
                self.show_file_message(self.username, file_path, target_user=target)
            else:
                # private
                msg = f"FILE|{target}|{filename}|{b64_data}\n"
                self.client.send(msg)
                # Hiển thị local trên khung target (private)
                self.show_file_message(self.username, file_path, target_user=target)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Gửi file thất bại: {e}")

    def show_file_message(self, sender, filepath, target_user=None):
        """Hiển thị tin nhắn file với nút tải về + cập nhật badge chưa đọc"""
        if target_user is None:
            target_user = self.current_chat_user or "ALL"

        # Tạo frame nếu chưa có
        if target_user not in self.chat_frames:
            frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
            frame.pack(fill="both", expand=True)
            self.chat_frames[target_user] = frame

        frame = self.chat_frames[target_user]

        # Khung chứa message
        outer_frame = tk.Frame(frame, bg="#f5f5f5")
        outer_frame.pack(fill="x", pady=5, padx=10)
        msg_container = tk.Frame(outer_frame, bg="#f5f5f5")
        msg_container.pack(anchor="w" if sender != self.username else "e")

        # Avatar
        avatar_img = self.create_circle_avatar(
            self.user_avatars.get(sender, "avatars/default.jpg")
            if sender != self.username else self.avatar_path,
            size=36
        )
        lbl_avatar = tk.Label(msg_container, image=avatar_img, bg="#f5f5f5")
        lbl_avatar.image = avatar_img
        lbl_avatar.pack(side="left" if sender != self.username else "right", padx=5)

        # Nút tải file
        filename = os.path.basename(filepath)

        def download_file():
            save_path = filedialog.asksaveasfilename(initialfile=filename)
            if save_path:
                try:
                    with open(filepath, "rb") as fsrc, open(save_path, "wb") as fdst:
                        fdst.write(fsrc.read())
                    messagebox.showinfo("Tải xuống", f"Đã lưu file tại:\n{save_path}")
                except Exception as e:
                    messagebox.showerror("Lỗi", f"Không lưu được file: {e}")

        btn_file = tk.Button(
            msg_container,
            text=f"📄 {filename}",
            bg="#e6e6e6",
            relief="flat",
            command=download_file
        )
        btn_file.pack(side="left" if sender != self.username else "right")

        # --- ✅ Cập nhật badge chưa đọc ---
        # display_target = target_user if target_user else sender
        #
        # if self.current_chat_user == display_target:
        #     # Đang mở đúng khung chat → reset unread
        #     self.unread_count[display_target] = 0
        #     self.update_user_list(self.current_users)
        #     self.chat_canvas.update_idletasks()
        #     self.chat_canvas.yview_moveto(1.0)
        # else:
        #     # Nếu là tin từ người khác → tăng badge
        #     if sender != self.username:
        #         self.unread_count[display_target] = self.unread_count.get(display_target, 0) + 1
        #         self.update_user_list(self.current_users)

    def record_voice(self):
        """Mở cửa sổ ghi âm tự động, hiển thị sóng âm, chỉ có nút Dừng & Gửi"""
        samplerate = 44100
        self.is_recording = True
        self.recorded_audio = None
        self.audio_buffer = []
        q = queue.Queue()

        # --- Tạo cửa sổ ---
        rec_win = tk.Toplevel(self.root)
        rec_win.title("🎙 Ghi âm giọng nói")
        rec_win.geometry("400x220")
        rec_win.config(bg="#fafafa")
        rec_win.resizable(False, False)

        lbl_status = tk.Label(rec_win, text="🎙 Đang ghi âm... (nhấn Dừng để gửi)", bg="#fafafa", font=("Arial", 12))
        lbl_status.pack(pady=6)

        lbl_timer = tk.Label(rec_win, text="⏱ 0.0s", bg="#fafafa", font=("Arial", 11, "bold"), fg="#333")
        lbl_timer.pack(pady=4)

        # Canvas hiển thị sóng âm
        canvas = tk.Canvas(rec_win, width=360, height=80, bg="white", highlightthickness=1, highlightbackground="#ccc")
        canvas.pack(pady=10)

        btn_stop = tk.Button(rec_win, text="⏹ Dừng & Gửi", bg="#f44336", fg="white",
                             font=("Arial", 11, "bold"), width=14)
        btn_stop.pack(pady=5)

        # --- Xử lý ghi âm ---
        def audio_callback(indata, frames, time_, status):
            if status:
                print(status)
            q.put(indata.copy())

        def update_waveform():
            """Cập nhật sóng âm mỗi 0.1s"""
            if not self.is_recording:
                return
            try:
                data = q.get_nowait()
                self.audio_buffer.append(data)
                canvas.delete("wave")

                if len(data.shape) > 1:
                    y = data[:, 0]  # lấy 1 kênh
                else:
                    y = data

                # chuẩn hóa về giữa canvas
                w = int(canvas["width"])
                h = int(canvas["height"])
                step = max(1, len(y) // w)
                y = y[::step]
                points = []
                for i, val in enumerate(y):
                    x = i
                    yy = int(h / 2 - val * h / 2)
                    points.append((x, yy))
                for i in range(1, len(points)):
                    canvas.create_line(points[i - 1], points[i], fill="#4CAF50", tags="wave")

                # cập nhật timer
                elapsed = time.time() - start_time
                lbl_timer.config(text=f"⏱ {elapsed:.1f}s")

            except queue.Empty:
                pass
            rec_win.after(100, update_waveform)

        def record_thread():
            with sd.InputStream(samplerate=samplerate, channels=1, dtype='float32', callback=audio_callback):
                while self.is_recording:
                    sd.sleep(100)

            # sau khi dừng, chờ chút để lấy phần âm cuối
            sd.sleep(300)
            while not q.empty():
                self.audio_buffer.append(q.get())

            # khi dừng
            if len(self.audio_buffer) == 0:
                lbl_status.config(text="❌ Không có dữ liệu ghi âm!")
                return

            recorded = np.concatenate(self.audio_buffer, axis=0)
            tmp_path = tempfile.mktemp(suffix=".wav")
            from scipy.io.wavfile import write
            write(tmp_path, samplerate, (recorded * 32767).astype(np.int16))

            try:
                self.send_voice(tmp_path)
                lbl_status.config(text="✅ Voice đã được gửi!")
            except Exception as e:
                lbl_status.config(text=f"Không gửi được voice: {e}")

            time.sleep(1)
            try:
                rec_win.destroy()
            except Exception:
                pass

        def stop_recording():
            self.is_recording = False
            btn_stop.config(state="disabled")
            lbl_status.config(text="Đang xử lý và gửi voice...")

        btn_stop.config(command=stop_recording)

        start_time = time.time()
        threading.Thread(target=record_thread, daemon=True).start()
        update_waveform()

    def send_voice(self, filepath):
        """Gửi file âm thanh (voice) tới user, nhóm, hoặc broadcast"""
        if not filepath or not os.path.exists(filepath):
            messagebox.showerror("Lỗi", "Không tìm thấy file ghi âm.")
            return

        target = self.current_chat_user or "ALL"

        try:
            with open(filepath, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file âm thanh: {e}")
            return

        filename = os.path.basename(filepath)

        # 🧠 Phân loại loại tin nhắn để gửi đúng
        if target == "ALL":
            msg = f"VOICE|ALL|{filename}|{b64_data}\n"
        elif hasattr(self, "user_groups") and target in self.user_groups:
            msg = f"GROUP_VOICE|{target}|{filename}|{b64_data}\n"
        else:
            msg = f"VOICE|{target}|{filename}|{b64_data}\n"

        try:
            self.client.send(msg)
            # Hiển thị luôn bên local (chính người gửi)
            self.show_voice_message(self.username, filepath, target_user=target)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không gửi được voice: {e}")

    def show_voice_message(self, sender, filepath, target_user=None, duration=None):
        pygame.mixer.init()

        # Lấy thời lượng file (giây)
        if duration is None:
            try:
                with wave.open(filepath, 'rb') as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    duration = frames / float(rate)
            except Exception:
                duration = 0

        if target_user is None:
            target_user = self.current_chat_user or "ALL"

        if target_user not in self.chat_frames:
            frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
            frame.pack(fill="both", expand=True)
            self.chat_frames[target_user] = frame

        frame = self.chat_frames[target_user]

        outer_frame = tk.Frame(frame, bg="#f5f5f5")
        outer_frame.pack(fill="x", pady=5, padx=10)
        msg_container = tk.Frame(outer_frame, bg="#f5f5f5")
        msg_container.pack(anchor="w" if sender != self.username else "e")

        avatar_img = self.create_circle_avatar(
            self.user_avatars.get(sender, "avatars/default.jpg") if sender != self.username else self.avatar_path,
            size=36
        )
        lbl_avatar = tk.Label(msg_container, image=avatar_img, bg="#f5f5f5")
        lbl_avatar.image = avatar_img
        lbl_avatar.pack(side="left" if sender != self.username else "right", padx=5)

        lbl_duration = tk.Label(
            msg_container,
            text=f"{duration:.1f}s",
            bg="#f5f5f5",
            font=("Arial", 9),
            fg="#666"
        )

        btn_play = tk.Button(
            msg_container,
            text="▶ Voice",
            bg="#e6e6e6",
            relief="flat",
            font=("Arial", 11, "bold"),
            width=15
        )

        def toggle_play():
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
                btn_play.config(text="▶ Resume")
            else:
                try:
                    pygame.mixer.music.load(filepath)
                    pygame.mixer.music.play()
                    btn_play.config(text="⏸ Pause")
                    update_button()
                except Exception as e:
                    messagebox.showerror("Lỗi", f"Không phát được file âm thanh: {e}")

        def update_button():
            if not pygame.mixer.music.get_busy():
                btn_play.config(text="▶ Play")
            else:
                self.root.after(200, update_button)

        btn_play.config(command=toggle_play)

        if sender == self.username:
            btn_play.pack(side="right")
            lbl_duration.pack(side="right", padx=6)
        else:
            btn_play.pack(side="left")
            lbl_duration.pack(side="left", padx=6)

        # 🔹 CHỈ tăng unread nếu sender != mình và đang không chat với target
        # if sender != self.username and self.current_chat_user != target_user:
        #     self.unread_count[target_user] = self.unread_count.get(target_user, 0) + 1
        #     self.root.after(0, lambda: self.update_user_list(self.current_users))
        # else:
        #     if self.current_chat_user == target_user:
        #         self.chat_canvas.yview_moveto(1.0)

    def start_call(self):
        """Bắt đầu cuộc gọi thoại"""
        # Kiểm tra client đã đăng nhập chưa
        if not hasattr(self, "client") or not self.client:
            messagebox.showwarning("Gọi thoại", "Chưa kết nối tới server!")
            return

        # Kiểm tra xem người dùng có đang chọn ai để gọi chưa
        if not getattr(self, "current_chat_user", None):
            messagebox.showwarning("Gọi thoại", "Vui lòng chọn người để gọi trước!")
            return

        # Import VoiceCall (file riêng)
        try:
            from app.VoiceCall import VoiceCall
        except ImportError:
            messagebox.showerror("Lỗi", "Không tìm thấy file VoiceCall.py!")
            return

            # Gửi tín hiệu gọi đến người kia
        try:
            self.client.send(f"CALL_REQUEST|{self.current_chat_user}\n")
        except Exception as e:
            print("Không gửi được CALL_REQUEST:", e)

        # Mở cửa sổ gọi và bắt đầu thu âm
        try:
            self.voice_call = VoiceCall(self.client, self.current_chat_user, parent=self.root)
            self.voice_call.start()
        except Exception as e:
            print("Lỗi khi bắt đầu cuộc gọi:", e)
            messagebox.showerror("Lỗi", f"Không thể bắt đầu cuộc gọi: {e}")

    def start_video_call(self):
        """Bắt đầu cuộc gọi video"""
        # Kiểm tra client đã đăng nhập chưa
        if not hasattr(self, "client") or not self.client:
            messagebox.showwarning("Video Call", "Chưa kết nối tới server!")
            return

        # Kiểm tra xem người dùng có đang chọn ai để gọi chưa
        target_user = getattr(self, "current_chat_user", None)
        if not target_user:
            messagebox.showwarning("Video Call", "Vui lòng chọn người để gọi trước!")
            return

        # Import VideoCall (file riêng)
        try:
            from app.VideoCall import VideoCall
        except ImportError:
            messagebox.showerror("Lỗi", "Không tìm thấy file VideoCall.py!")
            return

        # Gửi tín hiệu gọi đến người kia
        try:
            self.client.send(f"VIDEO_REQUEST|{target_user}\n")
        except Exception as e:
            print("Không gửi được VIDEO_REQUEST:", e)

        # Mở cửa sổ gọi video
        try:
            # self.video_call = VideoCall(self.client, target_user, parent=self.root)
            # self.video_call.start()
            from app.VideoCall import VideoCall
            vc = VideoCall(self.client, target_user, parent=self.root)
            self.client.video_call = vc    # ⭐ Gán cho client để server nhận biết
            vc.start()
        except Exception as e:
            print("Lỗi khi bắt đầu cuộc gọi video:", e)
            messagebox.showerror("Lỗi", f"Không thể bắt đầu cuộc gọi video: {e}")

    def show_video_call_request(self, caller):
        if messagebox.askyesno("Video Call", f"{caller} đang gọi video bạn, chấp nhận?"):
            from app.VideoCall import VideoCall
            self.video_call = VideoCall(self.client, caller, parent=self.root)
            self.client.video_call = self.video_call  # ⭐ Dòng quan trọng
            self.video_call.start()
            self.client.send(f"VIDEO_ACCEPT|{caller}\n")
        else:
            self.client.send(f"VIDEO_DECLINE|{caller}\n")

    # ------------------- Avatar hình tròn -------------------
    def create_circle_avatar(self, path, size=40):
        if not os.path.exists(path):
            img = Image.new("RGB", (size, size), color="#cccccc")
        else:
            img = Image.open(path).resize((size, size))
        # ensure alpha channel
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        img.putalpha(mask)
        return ImageTk.PhotoImage(img)

    # ------------------- Hiển thị tin nhắn -------------------
    def show_message(self, sender, msg, avatar_path=None, target_user=None):
        if not target_user:
            target_user = self.current_chat_user or "ALL"

        # Tạo frame cho conversation nếu chưa có
        if target_user not in self.chat_frames:
            frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
            frame.pack(fill="both", expand=True)
            self.chat_frames[target_user] = frame

        frame = self.chat_frames[target_user]

        if getattr(self, "messages_frame", None) is frame:
            if not frame.winfo_ismapped():
                frame.pack(fill="both", expand=True)

        # Load avatar
        if avatar_path and os.path.exists(avatar_path):
            avatar_img = self.create_circle_avatar(avatar_path, size=36)
        else:
            avatar_img = self.create_circle_avatar("../avatars/default.jpg", size=36)

        # Outer frame cho mỗi tin nhắn
        outer_frame = tk.Frame(frame, bg="#f5f5f5")
        outer_frame.pack(fill="x", pady=5, padx=10)

        # Container cho avatar + bong bóng tin nhắn
        msg_container = tk.Frame(outer_frame, bg="#f5f5f5")
        if sender == self.username:
            msg_container.pack(anchor="e")
        else:
            msg_container.pack(anchor="w")

        # 👉 Hiển thị tên người gửi (dù là chính mình)
        name_label = tk.Label(
            msg_container,
            text=sender,
            font=("Segoe UI", 9, "bold"),
            fg="#0078D7" if sender != self.username else "#1E8449",
            bg="#f5f5f5",
            anchor="w" if sender != self.username else "e"
        )
        if sender == self.username:
            name_label.pack(anchor="e", padx=(0, 40))  # căn phải
        else:
            name_label.pack(anchor="w", padx=(40, 0))  # căn trái

        # Avatar
        lbl_avatar = tk.Label(msg_container, image=avatar_img, bg="#f5f5f5")
        lbl_avatar.image = avatar_img
        if sender == self.username:
            lbl_avatar.pack(side="right", padx=5)
        else:
            lbl_avatar.pack(side="left", padx=5)

        # Bong bóng tin nhắn
        lbl_msg = tk.Label(
            msg_container,
            text=msg,
            font=("Segoe UI Emoji", 14),
            bg="#d1ffd6" if sender == self.username else "#f0f0f0",
            wraplength=400,
            justify="right" if sender == self.username else "left",
            padx=10, pady=6,
            relief="solid", bd=1
        )

        if sender == self.username:
            lbl_msg.pack(side="right")
        else:
            lbl_msg.pack(side="left")

        # Tự cuộn xuống cuối
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    # ------------------- Server trả về -------------------
    def handle_server_message(self, msg):
        # This handler assumes server sends plain strings like:
        # REGISTER_OK, REGISTER_FAIL, LOGIN_OK|avatar_path, LOGIN_FAIL
        # USER_LIST|user1|user2|...
        # PRIVATE|sender|text
        # MSG|sender|text   (broadcast)
        # adapt to your server protocol accordingly

        if msg == "REGISTER_OK":
            self.root.after(0, lambda: [
                messagebox.showinfo("Thành công", "Đăng ký thành công!"),
                self.show_login()
            ])
            return
        if msg == "REGISTER_FAIL":
            self.root.after(0, lambda: messagebox.showerror("Lỗi", "Tên đăng nhập đã tồn tại!"))
            return

        if msg.startswith("LOGIN_OK"):
            parts = msg.split("|")
            avatar = parts[1] if len(parts) > 1 else "avatars/default.jpg"
            self.avatar_path = avatar
            self.user_avatars[self.username] = avatar   # cập nhật avatar chính mình
            self.root.after(0, self.show_chat)
            return
        if msg == "LOGIN_FAIL":
            self.root.after(0, lambda: messagebox.showerror("Lỗi", "Sai tài khoản hoặc mật khẩu!"))
            return

        if msg.startswith("PRIVATE|"):
            try:
                _, sender, text = msg.split("|", 2)
            except ValueError:
                return  # malformed message

            # --- Thêm kiểm tra duplicate ---
            key = ("PRIVATE", sender, text)
            if not hasattr(self, "_shown_messages"):
                self._shown_messages = set()
            if key in self._shown_messages:
                return  # đã hiển thị rồi, bỏ qua
            self._shown_messages.add(key)

            # Nếu chưa có frame cho sender thì tạo
            if sender not in self.chat_frames:
                frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                self.chat_frames[sender] = frame

            # Nếu người nhận chưa mở khung chat với sender -> đánh dấu chưa đọc
            if self.current_chat_user != sender:
                self.unread_count[sender] = self.unread_count.get(sender, 0) + 1
                self.root.after(0, lambda: self.update_user_list(self.current_users))

            # Hiển thị message
            self.root.after(0, lambda: self.show_message(sender, text, self.user_avatars.get(sender, "avatars/default.jpg"), target_user=sender))
            return

        # --- BROADCAST TEXT ---
        if msg.startswith("MSG|"):
            try:
                _, sender, text = msg.split("|", 2)
            except ValueError:
                self.root.after(0, lambda: self.show_message("Server", msg))
                return

            if sender == self.username:
                return  # bỏ qua tin của chính mình

            key = ("MSG", sender, text)
            if not hasattr(self, "_shown_messages"):
                self._shown_messages = set()
            if key in self._shown_messages:
                return
            self._shown_messages.add(key)

            self.root.after(0, lambda: self.show_message(sender, text, self.user_avatars.get(sender), target_user="ALL"))
            return

        # --- BROADCAST IMAGE ---
        # if msg.startswith("IMG|"):
        #     try:
        #         _, sender, filename, b64_data = msg.split("|", 3)
        #     except ValueError:
        #         return
        #
        #     if sender == self.username:
        #         return  # bỏ qua tin của chính mình
        #
        #     save_path = Path("downloads") / filename
        #     save_path.parent.mkdir(exist_ok=True)
        #     with open(save_path, "wb") as f:
        #         f.write(base64.b64decode(b64_data))
        #
        #     self.root.after(0, lambda: self.show_image_message(sender, save_path, target_user="ALL"))
        #     return
        #
        # # --- BROADCAST FILE ---
        # if msg.startswith("FILE|"):
        #     try:
        #         _, sender, filename, b64_data = msg.split("|", 3)
        #     except ValueError:
        #         return
        #
        #     if sender == self.username:
        #         return
        #
        #     if not hasattr(self, "pending_files"):
        #         self.pending_files = {}
        #     self.pending_files[(sender, filename)] = b64_data
        #
        #     self.root.after(0, lambda: self.show_file_message(sender, filename, target_user="ALL"))
        #     return
        #
        # # --- BROADCAST VOICE ---
        # if msg.startswith("VOICE|"):
        #     try:
        #         _, sender, filename, b64_data = msg.split("|", 3)
        #     except ValueError:
        #         return
        #
        #     if sender == self.username:
        #         return
        #
        #     save_path = Path("downloads") / filename
        #     save_path.parent.mkdir(exist_ok=True)
        #     with open(save_path, "wb") as f:
        #         f.write(base64.b64decode(b64_data))
        #
        #     # lấy duration (nếu cần)
        #     try:
        #         import wave
        #         with wave.open(str(save_path), "rb") as wf:
        #             frames = wf.getnframes()
        #             rate = wf.getframerate()
        #             duration = frames / float(rate)
        #     except Exception:
        #         duration = 0.0
        #
        #     self.root.after(0, lambda: self.show_voice_message(sender, save_path, target_user="ALL", duration=duration))
        #     return

        if msg.startswith("USER_LIST|"):
            parts = msg.split("|")[1:]
            users = []
            for p in parts:
                if ":" in p:
                    uname, avatar = p.split(":", 1)
                    users.append(uname)
                    self.user_avatars[uname] = avatar
                else:
                    users.append(p)
                    if p not in self.user_avatars:
                        self.user_avatars[p] = "avatars/default.jpg"
            self.root.after(0, lambda: self.update_user_list(users))
            return

        if msg.startswith("GROUP_LIST|"):
            parts = msg.split("|")[1:]
            groups = [g for g in parts if g.strip()]  # loại bỏ chuỗi rỗng
            self.user_groups = groups  # lưu lại để dùng sau

            def update_group_list():
                # Kiểm tra chat_inner đã tồn tại chưa
                if not hasattr(self, 'chat_inner') or self.chat_inner is None:
                    print("Warning: chat_inner chưa được tạo. Bỏ qua update_group_list tạm thời.")
                    return

                # Thêm nhóm mới
                for g in groups:
                    if g not in self.chat_frames:
                        frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                        frame.pack(fill="x", pady=2)  # đừng quên pack
                        self.chat_frames[g] = frame

                # Cập nhật hiển thị user
                self.update_user_list(self.current_users)

            self.root.after(0, update_group_list)


        if msg.startswith("IMG|"):
            try:
                _, sender, filename, b64_data = msg.split("|", 3)
            except ValueError:
                return

            save_dir = Path("../downloads")
            save_dir.mkdir(exist_ok=True)
            save_path = save_dir / filename

            data = base64.b64decode(b64_data)
            with open(save_path, "wb") as f:
                f.write(data)

            def show_img():
                # tạo frame nếu chưa có
                if sender not in self.chat_frames:
                    frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                    self.chat_frames[sender] = frame
                    if self.current_chat_user == sender:
                        frame.pack(fill="both", expand=True)
                else:
                    frame = self.chat_frames[sender]
                    if self.current_chat_user == sender:
                        frame.pack(fill="both", expand=True)

                # **Use the saved local path here, not the original filepath**
                self.show_image_message(sender, save_path, target_user=sender)

            self.root.after(0, show_img)

        # --- FILE HANDLING (PRIVATE / GROUP / BROADCAST) ---
        if msg.startswith("FILE|"):
            parts = msg.split("|")

            # --- Phân tích cấu trúc ---
            if len(parts) == 6:
                # Dạng mới: FILE|TYPE|SENDER|TARGET|FILENAME|DATA
                _, msg_type, sender, target, filename, b64_data = parts
            elif len(parts) == 4:
                # Dạng riêng tư hoặc broadcast: FILE|SENDER|FILENAME|DATA
                _, sender, filename, b64_data = parts
                # Nếu sender là người khác → PRIVATE, ngược lại coi là broadcast
                msg_type = "PRIVATE" if sender != self.username else "BROADCAST"
                target = sender if msg_type == "PRIVATE" else "ALL"
            else:
                print("[DEBUG] FILE format không hợp lệ:", msg)
                return

            # --- Giải mã file ---
            try:
                data = base64.b64decode(b64_data)
                save_dir = Path("../downloads")
                save_dir.mkdir(exist_ok=True)
                file_path = save_dir / filename
                with open(file_path, "wb") as f:
                    f.write(data)
            except Exception as e:
                print("[DEBUG] Lỗi ghi file:", e)
                return

            # --- Xác định khung hiển thị thực tế ---
            if msg_type == "PRIVATE":
                # nếu tin gửi riêng → hiển thị ở frame của người gửi hoặc người nhận, không "ALL"
                display_target = sender if sender != self.username else target
            elif msg_type == "GROUP":
                display_target = target
            else:
                display_target = "ALL"

            # --- Chặn hiển thị sai khung ---
            if msg_type == "PRIVATE" and display_target == "ALL":
                print("[DEBUG] Bỏ qua hiển thị FILE PRIVATE ở ALL")
                return

            # --- Cập nhật tin chưa đọc ---
            if sender != self.username and self.current_chat_user != display_target:
                self.unread_count[display_target] = self.unread_count.get(display_target, 0) + 1
                self.root.after(0, lambda: self.update_user_list(self.current_users))

            # --- Hiển thị file ---
            def show_file():
                self.show_file_message(sender, str(file_path), target_user=display_target)

            self.root.after(0, show_file)
            return

        if msg.startswith("VOICE|"):
            try:
                _, sender, filename, b64_data = msg.split("|", 3)
            except ValueError:
                return

            save_dir = Path("../downloads")
            save_dir.mkdir(exist_ok=True)
            save_path = save_dir / filename

            data = base64.b64decode(b64_data)
            with open(save_path, "wb") as f:
                f.write(data)

            time.sleep(0.1)

            try:
                import wave
                with wave.open(str(save_path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    duration = frames / float(rate)
            except Exception:
                duration = 0.0

            def show_voice():
                if sender not in self.chat_frames:
                    frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                    self.chat_frames[sender] = frame

                self.show_voice_message(sender, save_path, target_user=sender, duration=duration)

                display_target = target_user if target_user is not None else sender

                if self.current_chat_user != display_target:
                    self.unread_count[display_target] = self.unread_count.get(display_target, 0) + 1
                    self.root.after(0, lambda: self.update_user_list(self.current_users))
                else:
                    frame.pack(fill="both", expand=True)
                    self.chat_canvas.update_idletasks()
                    self.chat_canvas.yview_moveto(1.0)

            # 👉 THÊM DÒNG NÀY ĐỂ THỰC SỰ HIỂN THỊ VOICE
            self.root.after(0, show_voice)

        if msg.startswith("CALL_REQUEST|"):
            # ai đó gọi bạn
            try:
                _, caller = msg.split("|", 1)
            except ValueError:
                return
            def on_pop():
                ans = messagebox.askyesno("Cuộc gọi", f"{caller} đang gọi bạn. Chấp nhận?", parent=self.root)
                if ans:
                    # gửi accept
                    try:
                        self.client.send_call_accept(caller)
                    except Exception:
                        try:
                            self.client.send(f"CALL_ACCEPT|{caller}\n")
                        except:
                            pass
                    # tạo voice call receiver: bắt đầu nhận luồng (không cần gửi âm thanh nếu muốn 2 chiều thì start)
                    self.voice_call = VoiceCall(self.client, caller, parent=self.root)
                    # nếu muốn bắt đầu gửi âm thanh 2 chiều khi accept:
                    self.voice_call.start()
                else:
                    # gửi end / từ chối (tùy bạn)
                    try:
                        self.client.send_call_end(caller)
                    except Exception:
                        try:
                            self.client.send(f"CALL_END|{caller}\n")
                        except:
                            pass
            self.root.after(0, on_pop)
            return

        if msg.startswith("CALL_ACCEPT|"):
            try:
                _, acceptor = msg.split("|", 1)
            except ValueError:
                return
            # bên kia đã chấp nhận => nếu bạn là caller và chưa start, start
            if not hasattr(self, "voice_call") or not self.voice_call.is_calling:
                self.voice_call = VoiceCall(self.client, acceptor, parent=self.root)
                self.voice_call.start()
            return

        if msg.startswith("CALL_STREAM|"):
            try:
                _, sender, b64 = msg.split("|", 2)
            except ValueError:
                return
            # nếu đang trong cuộc gọi với sender -> phát
            if hasattr(self, "voice_call") and self.voice_call and self.voice_call.target_user == sender:
                # chạy trên luồng UI bằng after để an toàn
                self.root.after(0, lambda: self.voice_call.receive_audio(b64))
            return

        if msg.startswith("CALL_END|"):
            try:
                _, who = msg.split("|", 1)
            except ValueError:
                return
            if hasattr(self, "voice_call") and self.voice_call:
                self.voice_call.end()
            return

        if msg.startswith("VIDEO_REQUEST|"):
            user = msg.split("|")[1]
            self.show_video_call_request(user)  # hiển thị popup: có muốn nhận video call không
        elif msg.startswith("VIDEO_STREAM|"):
            # VIDEO_STREAM|sender|b64video|b64audio
            parts = msg.split("|", 4)
            sender, b64video, b64audio = parts[1:4]
            if hasattr(self, 'video_call') and self.video_call:
                self.video_call.receive_video(b64video, b64audio)
        elif msg.startswith("VIDEO_END|"):
            if hasattr(self, 'video_call') and self.video_call:
                self.video_call.end()

        if msg.startswith("GROUP_MSG|"):
            try:
                _, group_name, sender, text = msg.split("|", 3)
            except ValueError:
                return

            # Nếu chưa có frame cho nhóm -> tạo
            if group_name not in self.chat_frames:
                frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                self.chat_frames[group_name] = frame

            # Nếu chưa mở nhóm này -> đánh dấu tin chưa đọc
            if sender != self.username and self.current_chat_user != group_name:
                self.unread_count[group_name] = self.unread_count.get(group_name, 0) + 1
                self.root.after(0, lambda: self.update_user_list(self.current_users))

            else:
                frame = self.chat_frames[group_name]
                frame.pack(fill="both", expand=True)
                self.chat_canvas.update_idletasks()
                self.chat_canvas.yview_moveto(1.0)

            self.root.after(0, lambda: self.show_message(
                sender,
                text,
                self.user_avatars.get(sender, "avatars/default.jpg"),
                target_user=group_name
            ))
            return

        if msg.startswith("GROUP_LEAVE_OK|"):
            _, group, username = msg.split("|", 2)

            # Nếu là chính mình -> xoá nhóm khỏi danh sách, vô hiệu khung
            if username == self.username:
                if hasattr(self, "user_groups") and group in self.user_groups:
                    self.user_groups.remove(group)

                if group in self.chat_frames:
                    frame = self.chat_frames[group]
                    # Xóa toàn bộ nội dung cũ trong khung
                    for widget in frame.winfo_children():
                        widget.destroy()

                    # Hiển thị thông báo bạn đã rời nhóm
                    lbl = tk.Label(
                        frame,
                        text="(Bạn đã rời nhóm này)",
                        bg="#f5f5f5",
                        fg="gray",
                        font=("Arial", 12, "italic")
                    )
                    lbl.pack(pady=20)

                # Vô hiệu hóa nút và ô nhập
                if hasattr(self, "btn_leave_group") and self.btn_leave_group:
                    self.btn_leave_group.destroy()
                if hasattr(self, "entry_msg"):
                    self.entry_msg.config(state="disabled")
                if hasattr(self, "btn_send"):
                    self.btn_send.config(state="disabled")

                # Hiển thị popup thông báo và cập nhật danh sách
                self.root.after(0, lambda: messagebox.showinfo("Rời nhóm", f"Bạn đã rời nhóm '{group}'"))
                self.root.after(0, lambda: self.update_user_list(self.current_users))

            else:
                # Người khác rời nhóm -> hiển thị thông báo trong nhóm (dạng chữ nghiêng, không avatar)
                if group in self.chat_frames:
                    frame = self.chat_frames[group]
                    lbl = tk.Label(
                        frame,
                        text=f"({username} đã rời nhóm này)",
                        bg="#f5f5f5",
                        fg="gray",
                        font=("Arial", 12, "italic")
                    )
                    lbl.pack(pady=5)
                    self.chat_canvas.update_idletasks()
                    self.chat_canvas.yview_moveto(1.0)
            return

        if msg.startswith("GROUP_LEAVE_FAIL|"):
            _, reason = msg.split("|", 1)
            self.root.after(0, lambda: messagebox.showerror("Lỗi", reason))
            return

        if msg.startswith("GROUP_INFO|"):
            try:
                _, group_name, info_text = msg.split("|", 2)
            except ValueError:
                return

            def show_group_info():
                if group_name not in self.chat_frames:
                    frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                    frame.pack(fill="both", expand=True)
                    self.chat_frames[group_name] = frame
                frame = self.chat_frames[group_name]

                lbl = tk.Label(
                    frame,
                    text=f"({info_text})",
                    bg="#f5f5f5",
                    fg="gray",
                    font=("Arial", 12, "italic")
                )
                lbl.pack(pady=5)

                # Cuộn xuống cuối nếu có scrollbar
                self.chat_canvas.update_idletasks()
                self.chat_canvas.yview_moveto(1.0)

            self.root.after(0, show_group_info)
            return

        if msg.startswith("GROUP_IMG|"):
            try:
                _, group_name, sender, filename, b64_data = msg.split("|", 4)
            except ValueError:
                return

            # duplicate check
            if not hasattr(self, "_shown_messages"):
                self._shown_messages = set()
            key = ("GROUP_IMG", group_name, sender, filename)
            if key in self._shown_messages:
                return
            self._shown_messages.add(key)

            save_dir = Path("../downloads") / "group_images"
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(b64_data))

            def show_group_img():
                if group_name not in self.chat_frames:
                    frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                    frame.pack(fill="both", expand=True)
                    self.chat_frames[group_name] = frame

                self.show_image_message(sender, save_path, target_user=group_name)

                # chỉ tăng unread nếu sender khác mình
                # if sender != self.username and self.current_chat_user != group_name:
                #     self.unread_count[group_name] = self.unread_count.get(group_name, 0) + 1
                #     self.update_user_list(self.current_users)

            self.root.after(0, show_group_img)

        if msg.startswith("GROUP_FILE|"):
            try:
                _, group_name, sender, filename, b64_data = msg.split("|", 4)
            except ValueError:
                return

            save_dir = Path("../downloads") / "group_files"
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(b64_data))

            def show_group_file():
                if group_name not in self.chat_frames:
                    frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                    frame.pack(fill="both", expand=True)
                    self.chat_frames[group_name] = frame
                self.show_file_message(sender, save_path, target_user=group_name)

            if sender != self.username and self.current_chat_user != group_name:
                self.unread_count[group_name] = self.unread_count.get(group_name, 0) + 1
                self.root.after(0, lambda: self.update_user_list(self.current_users))

            self.root.after(0, show_group_file)
            return

        if msg.startswith("GROUP_VOICE|"):
            try:
                _, group_name, sender, filename, b64_data = msg.split("|", 4)
            except ValueError:
                return

            save_dir = Path("../downloads") / "group_voice"
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / filename
            with open(save_path, "wb") as f:
                f.write(base64.b64decode(b64_data))

            try:
                import wave
                with wave.open(str(save_path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    duration = frames / float(rate)
            except Exception:
                duration = 0.0

            def show_group_voice():
                if group_name not in self.chat_frames:
                    frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
                    frame.pack(fill="both", expand=True)
                    self.chat_frames[group_name] = frame
                self.show_voice_message(sender, save_path, target_user=group_name, duration=duration)

            if sender != self.username and self.current_chat_user != group_name:
                self.unread_count[group_name] = self.unread_count.get(group_name, 0) + 1
                self.root.after(0, lambda: self.update_user_list(self.current_users))

            self.root.after(0, show_group_voice)
            return

    def create_group_window(self):
        """Hiển thị cửa sổ tạo nhóm, chọn user"""
        if not self.current_users:
            messagebox.showinfo("Tạo nhóm", "Hiện không có user online")
            return

        win = tk.Toplevel(self.root)
        win.title("Tạo nhóm mới")
        win.geometry("300x400")
        win.config(bg="#f5f5f5")

        tk.Label(win, text="Chọn thành viên cho nhóm:", bg="#f5f5f5", font=("Arial", 12, "bold")).pack(pady=10)

        frame_list = tk.Frame(win, bg="#f5f5f5")
        frame_list.pack(fill="both", expand=True, padx=10)

        # Checkbox cho từng user
        self.group_vars = {}
        for u in self.current_users:
            if u == self.username:
                continue
            var = tk.BooleanVar()
            chk = tk.Checkbutton(frame_list, text=u, variable=var, bg="#f5f5f5", font=("Arial", 11))
            chk.pack(anchor="w", pady=2)
            self.group_vars[u] = var

        # Tên nhóm
        tk.Label(win, text="Tên nhóm:", bg="#f5f5f5").pack(pady=5)
        self.entry_group_name = tk.Entry(win)
        self.entry_group_name.pack(fill="x", padx=10)

        btn_create = tk.Button(win, text="Tạo nhóm", bg="#4CAF50", fg="white",
                               command=lambda: self.create_group(win))
        btn_create.pack(pady=10)

    def create_group(self, win):
        selected_users = [u for u, var in self.group_vars.items() if var.get()]
        group_name = self.entry_group_name.get().strip()

        if not group_name:
            messagebox.showerror("Lỗi", "Vui lòng nhập tên nhóm")
            return
        if not selected_users:
            messagebox.showerror("Lỗi", "Chọn ít nhất 1 thành viên")
            return

        # Gửi lệnh tạo nhóm tới server
        try:
            members = ",".join(selected_users)
            self.client.send(f"GROUP_CREATE|{group_name}|{members}\n")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không tạo được nhóm: {e}")
            return

        # Tạo frame chat nhóm local
        frame = tk.Frame(self.chat_inner, bg="#f5f5f5")
        frame.pack(fill="both", expand=True)
        self.chat_frames[group_name] = frame
        self.select_chat_user(group_name)  # tự động chuyển vào chat nhóm

        win.destroy()
        messagebox.showinfo("Tạo nhóm", f"Nhóm '{group_name}' đã được tạo")

    def on_group_left(self, group_name):
        """Xử lý sau khi rời nhóm thành công"""
        if group_name in self.chat_frames:
            frame = self.chat_frames[group_name]
            frame.pack_forget()
            del self.chat_frames[group_name]

        if group_name in self.user_groups:
            self.user_groups.remove(group_name)

        # Nếu đang mở khung chat nhóm đó -> quay về ALL
        if self.current_chat_user == group_name:
            self.select_chat_user("ALL")

        self.update_user_list(self.current_users)
        messagebox.showinfo("Rời nhóm", f"Bạn đã rời nhóm '{group_name}'")

    # fallback: show raw server text in an "ALL" conversation (or server frame)
        # self.root.after(0, lambda: self.show_message("Server", msg, target_user="ALL"))

    # ------------------- Tiện ích -------------------
    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # optional helper to gracefully close client socket if GUI is closed
    def close(self):
        try:
            self.client.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    ChatGUI()