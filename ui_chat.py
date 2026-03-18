import socket
import threading
import time
from datetime import datetime
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os

from database import init_db, load_messages, save_message
from self_destruct import display_then_delete
import tkinter as tk


class ChatApp(ctk.CTk):
	def __init__(self):
		super().__init__()
		ctk.set_appearance_mode("dark")
		ctk.set_default_color_theme("green")
		self.title("SecureLink — Dashboard")
		self.geometry("1000x650")

		init_db()

		# try bundled fonts folder (optional) -- if a TTF is present in ./fonts we will try to use it for avatars
		self._bundled_font_path = None
		fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
		if os.path.isdir(fonts_dir):
			for fn in os.listdir(fonts_dir):
				if fn.lower().endswith(".ttf"):
					self._bundled_font_path = os.path.join(fonts_dir, fn)
					break

		# Top header
		header = ctk.CTkFrame(self, height=64, corner_radius=0)
		header.pack(side="top", fill="x")
		title = ctk.CTkLabel(header, text="SecureLink", font=ctk.CTkFont(size=20, weight="bold"))
		title.pack(side="left", padx=16)
		self.status = ctk.CTkLabel(header, text=self._build_status_text(), anchor="e")
		self.status.pack(side="right", padx=16)

		# Theme switch (dark <-> light)
		self.theme_var = tk.BooleanVar(value=False)
		theme_switch = ctk.CTkSwitch(header, text="Light Mode", command=lambda: self._on_theme_toggle(), variable=self.theme_var)
		theme_switch.pack(side="right", padx=8)

		# Main area: Sidebar | Chat
		content = ctk.CTkFrame(self)
		content.pack(expand=True, fill="both")

		# Sidebar
		self.sidebar = ctk.CTkFrame(content, width=260)
		self.sidebar.pack(side="left", fill="y", padx=(12, 6), pady=12)

		# Search & users list
		search = ctk.CTkEntry(self.sidebar, placeholder_text="Search users...")
		search.pack(fill="x", padx=12, pady=(8, 6))

		self.users_scroll = ctk.CTkScrollableFrame(self.sidebar, height=520)
		self.users_scroll.pack(fill="both", expand=True, padx=8, pady=6)

		# Chat main panel
		self.main_area = ctk.CTkFrame(content)
		self.main_area.pack(side="right", expand=True, fill="both", padx=(6, 12), pady=12)

		# Messages area with a dedicated canvas for proper auto-scrolling
		self.msg_container = ctk.CTkFrame(self.main_area)
		self.msg_container.pack(expand=True, fill="both")

		self.msg_frame = ctk.CTkScrollableFrame(self.msg_container)
		self.msg_frame.pack(expand=True, fill="both", padx=12, pady=12)

		# Entry area
		entry_frame = ctk.CTkFrame(self.main_area, height=72)
		entry_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

		self.entry = ctk.CTkTextbox(entry_frame, height=56)
		self.entry.pack(side="left", expand=True, fill="x", padx=(8, 6), pady=8)
		self.entry.bind('<Return>', self._on_enter_press)

		send_btn = ctk.CTkButton(entry_frame, text="Send", width=96, command=self._on_send)
		send_btn.pack(side="right", padx=(6, 8), pady=8)

		# Load history and peers
		self._load_history()
		self._discovery_thread = threading.Thread(target=self._discover_peers, daemon=True)
		self._discovery_thread.start()

	def _build_status_text(self) -> str:
		ip = self._get_local_ip() or "0.0.0.0"
		return f"Connected to {ip} | Encryption: ON"

	def _on_theme_toggle(self):
		# Toggle theme based on the switch variable
		try:
			if self.theme_var.get():
				ctk.set_appearance_mode("light")
			else:
				ctk.set_appearance_mode("dark")
		except Exception:
			pass

	def _get_local_ip(self) -> Optional[str]:
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			# doesn't need to be reachable
			s.connect(("8.8.8.8", 80))
			ip = s.getsockname()[0]
			s.close()
			return ip
		except Exception:
			return None

	def _format_timestamp(self, ts: str) -> str:
		try:
			dt = datetime.fromisoformat(ts)
			return dt.strftime("%Y-%m-%d %H:%M")
		except Exception:
			return ts

	def _add_message_bubble(self, sender: str, message: str, timestamp: Optional[str] = None):
		if timestamp is None:
			timestamp = datetime.utcnow().isoformat()

		# Choose style
		is_me = sender == "me"
		bg = "#16a34a" if is_me else "#2b2b2b"
		fg = "white" if is_me else "#e5e7eb"
		anchor = "e" if is_me else "w"

		# Outer container to keep width constrained
		bubble = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
		bubble.pack(anchor=anchor, pady=6, padx=12)

		# Avatar + inner bubble
		row = ctk.CTkFrame(bubble, fg_color="transparent")
		row.pack(anchor=anchor)

		avatar_img = self._create_avatar(sender, size=36)
		if is_me:
			# message on right: bubble then avatar
			inner = ctk.CTkFrame(row, fg_color=bg, corner_radius=12)
			inner.pack(side="right", padx=(8, 0))
			lbl_img = ctk.CTkLabel(row, image=avatar_img, text="")
			lbl_img.image = avatar_img
			lbl_img.pack(side="right", padx=(6, 0))
		else:
			lbl_img = ctk.CTkLabel(row, image=avatar_img, text="")
			lbl_img.image = avatar_img
			lbl_img.pack(side="left", padx=(0, 6))
			inner = ctk.CTkFrame(row, fg_color=bg, corner_radius=12)
			inner.pack(side="left", padx=(0, 8))

		txt = ctk.CTkLabel(inner, text=message, wraplength=520, justify="left", text_color=fg)
		txt.pack(padx=12, pady=(10, 6))

		meta = ctk.CTkLabel(inner, text=f"{sender} • {self._format_timestamp(timestamp)}", font=ctk.CTkFont(size=10), text_color=fg)
		meta.pack(anchor="e", padx=10, pady=(0, 8))

		# Simple slide-in animation: animate padx from offset to normal
		try:
			start = 220
			end = 12
			steps = 10
			delta = (start - end) / steps

			def animate(step=0, current=start):
				if step >= steps:
					bubble.pack_configure(padx=end)
					return
				bubble.pack_configure(padx=int(current))
				self.after(16, lambda: animate(step + 1, current - delta))

			animate()
		except Exception:
			pass

		# Auto-scroll to bottom
		try:
			self.msg_frame.update_idletasks()
			self.msg_frame.yview_moveto(1.0)
		except Exception:
			pass

	def _on_send(self):
		text = self.entry.get("1.0", "end").strip()
		if not text:
			return
		# add to UI
		self._add_message_bubble("me", text)
		# save to DB
		save_message("me", text, datetime.utcnow().isoformat())
		self.entry.delete("1.0", "end")

	def _load_history(self):
		rows = load_messages()
		for _id, sender, message, timestamp in rows:
			self._add_message_bubble(sender, message, timestamp)

	def _on_enter_press(self, event):
		# Enter to send, Shift+Enter for newline
		if event.state & 0x0001:  # Shift key (platform dependent but works commonly)
			return
		self._on_send()
		return "break"

	def _discover_peers(self):
		# Placeholder auto-discovery: this would be replaced by actual LAN discovery logic.
		sample = [
			("Alice", "192.168.1.2"),
			("Bob", "192.168.1.3"),
		]
		for name, ip in sample:
			self._add_peer_safe(name, ip)

		# Simulate dynamic peers to demonstrate UI
		counter = 3
		while True:
			time.sleep(10)
			name = f"Peer-{counter}"
			ip = f"192.168.1.{10+counter}"
			self._add_peer_safe(name, ip)
			counter += 1

	def _create_avatar(self, name: str, size: int = 40) -> ImageTk.PhotoImage:
		# Create a simple circular avatar with initials
		initials = "".join([part[0].upper() for part in name.split()][:2]) or "?"
		# Choose a pseudo-random background color based on name
		h = sum(ord(c) for c in name) % 360
		hue = h / 360.0
		# convert hue to rgb (simple HSL->RGB approximation)
		import colorsys

		r, g, b = colorsys.hsv_to_rgb(hue, 0.5, 0.95)
		bg = (int(r * 255), int(g * 255), int(b * 255))

		img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
		draw = ImageDraw.Draw(img)
		draw.ellipse((0, 0, size - 1, size - 1), fill=bg)

		# Draw initials, prefer bundled font if available
		try:
			if getattr(self, '_bundled_font_path', None):
				fnt = ImageFont.truetype(self._bundled_font_path, int(size / 2))
			else:
				fnt = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size / 2))
		except Exception:
			fnt = ImageFont.load_default()
		# Compute text size with compatibility across Pillow versions
		try:
			# Pillow >=8: textbbox is available
			bbox = draw.textbbox((0, 0), initials, font=fnt)
			w = bbox[2] - bbox[0]
			h = bbox[3] - bbox[1]
		except Exception:
			try:
				# Older fallback
				w, h = fnt.getsize(initials)
			except Exception:
				# Last resort: approximate
				w, h = (int(size / 2), int(size / 2))
		draw.text(((size - w) / 2, (size - h) / 2), initials, font=fnt, fill=(255, 255, 255))
		return ImageTk.PhotoImage(img)

	def _add_peer_safe(self, name: str, ip: str):
		def _do():
			frame = ctk.CTkFrame(self.users_scroll, corner_radius=8)
			frame.pack(fill="x", padx=8, pady=6)
			avatar = self._create_avatar(name, size=40)
			lbl_img = ctk.CTkLabel(frame, image=avatar, width=40, height=40, text="")
			lbl_img.image = avatar
			lbl_img.pack(side="left", padx=8, pady=6)
			lbl_txt = ctk.CTkLabel(frame, text=f"{name}\n{ip}", anchor="w")
			lbl_txt.pack(side="left", padx=6)

		try:
			_do()
		except Exception:
			self.after(0, _do)

	def trigger_self_destruct_demo(self, text: str = "This message will self-destruct in 10s"):
		# Demonstrate self-destruct by creating a label in the main area and calling helper
		banner = ctk.CTkLabel(self.main_area, text="", fg_color="#333333", text_color="#fff", corner_radius=6)
		banner.pack(side="top", pady=6, padx=12)
		display_then_delete(banner, text, delay=10)


if __name__ == "__main__":
	app = ChatApp()
	# demo self-destruct after 2s
	app.after(2000, lambda: app.trigger_self_destruct_demo())
	app.mainloop()

