import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter import messagebox as MessageBox

import ttkbootstrap as tb

from gui.components.cards import DetailCard
from gui.components.state_views import StateView


class ContentPageMixin:
    def create_content_tab(self):
        """Create Content Management tab"""
        content_tab = tb.Frame(self.notebook)
        self.notebook.add(content_tab, text="Content")

        self.create_content_management_section(content_tab)

    def create_content_management_section(self, parent):
        """Create content management section"""
        content_frame = self._create_card_section(
            parent,
            "Content Management",
            "Manage queue items and preview media metadata.",
            expand=True,
        )

        # Control buttons
        controls_frame = tb.Frame(content_frame)
        controls_frame.pack(fill="x", padx=6, pady=12)

        btn_configs = [
            ("Add Video", self.add_video, "primary"),
            ("Load Folder", self.load_video_folder, "outline-secondary"),
            ("Clear Used", self.clear_used_videos, "danger"),
            ("View Stats", self.show_content_stats, "secondary"),
        ]

        for text, command, style in btn_configs:
            btn = tb.Button(controls_frame, text=text, command=command, bootstyle=style, width=15)
            btn.pack(side="left", padx=5)

        split = ttk.Panedwindow(content_frame, orient=tk.HORIZONTAL)
        split.pack(fill="both", expand=True, padx=6, pady=(0, 12))

        left_card = DetailCard(split, "Content List", palette=self.palette, padding=12)
        right_card = DetailCard(split, "Preview", palette=self.palette, padding=12)
        split.add(left_card, weight=3)
        split.add(right_card, weight=2)

        left = left_card.body
        right = right_card.body

        self.content_list_state_view = StateView(
            left,
            kind="loading",
            title="Loading content queue...",
            message="Reading queued media and usage state.",
            actions=[
                {"text": "Refresh", "command": self.update_content_display, "bootstyle": "outline-info"},
                {"text": "Load Folder", "command": self.load_video_folder, "bootstyle": "outline-secondary"},
            ],
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self.content_list_state_view.pack(fill="x", padx=5, pady=(0, 8))

        self.content_listbox = tk.Listbox(
            left,
            font=(self.mono_font, 10),
            bg=self.palette["surface_alt"],
            fg=self.palette["text"],
            selectbackground="#253447",
            selectforeground=self.palette["text"],
            highlightthickness=0,
            relief="flat",
        )

        scrollbar = tb.Scrollbar(left, style="Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")

        self.content_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.content_listbox.yview)
        self.content_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.content_listbox.bind("<<ListboxSelect>>", self._on_content_selected)

        self.content_preview_text = tk.Text(
            right,
            wrap="word",
            font=(self.mono_font, 10),
            height=10,
            bg=self.palette["surface"],
            fg=self.palette["text"],
            insertbackground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
            padx=8,
            pady=8,
        )
        self.content_preview_state_view = StateView(
            right,
            kind="empty",
            title="Select content to preview",
            message="Choose a queued video to inspect caption and file metadata.",
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self.content_preview_state_view.pack(fill="x", pady=(0, 8))
        self.content_preview_text.pack(fill="both", expand=True)
        self.content_preview_text.insert("1.0", "Select an item to view details.")
        self.content_preview_text.config(state="disabled")

        # Stats label
        stats_frame = tb.Frame(content_frame)
        stats_frame.pack(fill="x", padx=6, pady=8)

        self.content_stats_label = tb.Label(
            stats_frame, text="Queue: 0 total, 0 available, 0 used", bootstyle="secondary"
        )
        self.content_stats_label.pack(side="left")

        # Update button
        tb.Button(
            stats_frame, text="Update", command=self.update_content_display, bootstyle="secondary", width=10
        ).pack(side="right", padx=5)

        # Initial update
        self.update_content_display()

    def add_video(self):
        """Add a single video file to the content queue."""
        video_file = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video Files", "*.mp4;*.mov;*.avi;*.mkv;*.webm;*.flv"),
                ("All Files", "*.*"),
            ],
        )
        if not video_file:
            return

        try:
            ok = self.content_manager.add_video_to_queue(video_file)
        except Exception as e:
            MessageBox.showerror("Add Video", f"Failed to add video: {e}")
            return

        if ok:
            self.log(f" Added video: {Path(video_file).name}", level="SUCCESS")
            self.update_content_display()
        else:
            MessageBox.showerror("Add Video", "Failed to add video to queue.")

    def load_video_folder(self):
        """Bulk-load video files from a folder into the queue."""
        folder = filedialog.askdirectory(title="Select folder with videos")
        if not folder:
            return

        try:
            added_count = self.content_manager.load_content_from_folder(folder)
        except Exception as e:
            MessageBox.showerror("Load Folder", f"Failed to load folder: {e}")
            return

        self.log(f" Loaded folder: {folder} (+{added_count} videos)", level="SUCCESS")
        self.update_content_display()

    def clear_used_videos(self):
        """Remove already-used videos from the queue."""
        if not MessageBox.askyesno("Clear Used Videos", "Remove all used items from the queue?"):
            return

        try:
            self.content_manager.clear_used_videos()
        except Exception as e:
            MessageBox.showerror("Clear Used", f"Failed to clear used videos: {e}")
            return

        self.log("Cleared used videos from queue", level="SUCCESS")
        self.update_content_display()

    def update_content_display(self):
        """Update content listbox display"""
        if hasattr(self, "content_list_state_view"):
            self.content_list_state_view.set(
                kind="loading",
                title="Loading content queue...",
                message="Reading queued media and usage state.",
                actions=[],
            )
            self.content_list_state_view.pack(fill="x", padx=5, pady=(0, 8))
            try:
                self.root.update_idletasks()
            except Exception:
                pass
        self.content_listbox.delete(0, tk.END)
        self._content_display_items = []

        try:
            content_items = self.content_manager.get_queue_items()
        except Exception as exc:
            self.content_list_state_view.set(
                kind="error",
                title="Could not read content queue",
                message=str(exc) or "The content queue could not be loaded from disk.",
                actions=[
                    {"text": "Retry", "command": self.update_content_display, "bootstyle": "outline-danger"},
                    {
                        "text": "Load Folder",
                        "command": self.load_video_folder,
                        "bootstyle": "outline-secondary",
                    },
                ],
            )
            self.update_content_stats(error=exc)
            self._set_content_preview_empty(
                "Content preview unavailable", "Fix the queue load error, then select an item to preview."
            )
            self.log(f"Failed to load content queue: {exc}", "ERROR", category="Content")
            return

        if not content_items and hasattr(self, "content_list_state_view"):
            self.content_list_state_view.set(
                kind="empty",
                title="Content queue is empty",
                message="Add a video or load a folder to prepare queue-backed automation tasks.",
                actions=[
                    {"text": "Add Video", "command": self.add_video, "bootstyle": "outline-info"},
                    {
                        "text": "Load Folder",
                        "command": self.load_video_folder,
                        "bootstyle": "outline-secondary",
                    },
                ],
            )
            self.content_list_state_view.pack(fill="x", padx=5, pady=(0, 8))
        elif hasattr(self, "content_list_state_view"):
            self.content_list_state_view.pack_forget()

        for item in content_items:
            filename = os.path.basename(item["path"])
            status = "[USED]" if item.get("used", False) else "[NEW]"
            self.content_listbox.insert(
                tk.END, f"{status} {filename[:30]:30} | Caption: {item.get('caption', 'N/A')[:20]}..."
            )
            self._content_display_items.append(item)

            # Color used items differently
            if item.get("used", False):
                self.content_listbox.itemconfig(tk.END, {"fg": "#95a5a6"})

        self.update_content_stats()
        if content_items:
            self.content_listbox.selection_clear(0, tk.END)
            self.content_listbox.selection_set(0)
            self._on_content_selected()
        else:
            self._set_content_preview_empty()

    def _on_content_selected(self, _event=None):
        """Update right-side preview panel for selected content."""
        if not hasattr(self, "content_preview_text"):
            return

        selected = self.content_listbox.curselection()
        if not selected:
            self._set_content_preview_empty()
            return
        else:
            idx = selected[0]
            item = self._content_display_items[idx] if idx < len(self._content_display_items) else {}
            preview = (
                f"File: {Path(item.get('path', '')).name}\n"
                f"Status: {'Used' if item.get('used', False) else 'Available'}\n"
                f"Caption: {item.get('caption', 'N/A')}\n\n"
                f"Path:\n{item.get('path', 'N/A')}"
            )

        self.content_preview_text.config(state="normal")
        self.content_preview_text.delete("1.0", "end")
        self.content_preview_text.insert("1.0", preview)
        self.content_preview_text.config(state="disabled")
        if hasattr(self, "content_preview_state_view"):
            self.content_preview_state_view.pack_forget()

    def _set_content_preview_empty(
        self,
        title="Select content to preview",
        message="Choose a queued video to inspect caption and file metadata.",
    ):
        if hasattr(self, "content_preview_state_view"):
            self.content_preview_state_view.set(kind="empty", title=title, message=message, actions=[])
            self.content_preview_state_view.pack(fill="x", pady=(0, 8))
        if hasattr(self, "content_preview_text"):
            self.content_preview_text.config(state="normal")
            self.content_preview_text.delete("1.0", "end")
            self.content_preview_text.insert("1.0", message)
            self.content_preview_text.config(state="disabled")

    def update_content_stats(self, error=None):
        """Update content queue statistics"""
        if error is not None:
            self.content_stats_label.config(text="Queue: unavailable")
            return
        try:
            stats = self.content_manager.get_queue_stats()
        except Exception as exc:
            self.content_stats_label.config(text="Queue: unavailable")
            self.log(f"Failed to read content stats: {exc}", "ERROR", category="Content")
            return
        self.content_stats_label.config(
            text=f"Queue: {stats['total']} total, {stats['available']} available, {stats['used']} used"
        )
