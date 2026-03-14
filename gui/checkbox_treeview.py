import tkinter as tk
from tkinter import ttk
import time

class CheckboxTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        # Use ttkbootstrap Treeview
        super().__init__(master, **kwargs)
        self.checkboxes = {}
        self.selection_enabled = True
        self._clicked_item = None
        self._click_time = 0

        # Configure tags; keep checked rows uncolored so only the checkmark indicates selection.
        self.tag_configure("checked", background="", foreground="")
        self.tag_configure("unchecked", background="", foreground="")
        self.tag_configure("active", background="#10B981", foreground="#E2E8F0")
        self.tag_configure("inactive", background="", foreground="")
        self.tag_configure("running", background="#F59E0B", foreground="#E2E8F0")
        self.tag_configure("paused", background="#7C3AED", foreground="#E2E8F0")
        self.tag_configure("completed", background="#10B981", foreground="#E2E8F0")
        self.tag_configure("selected", background="#00E5FF", foreground="#0A0C10")
        self.tag_configure("hover", background="#1E2330")
        
        # Custom checkbox tags
        self.tag_configure("checkbox_checked", background="#10B981", foreground="white")
        self.tag_configure("checkbox_unchecked", background="#64748B", foreground="white")
        
        # Bind events
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-1>", self._on_double_click)
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-A>", self._select_all)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        
        # Right-click context menu
        self.context_menu = tk.Menu(self, tearoff=0, bg="#343a40", fg="white")
        self.context_menu.add_command(label="Select", command=self._context_select)
        self.context_menu.add_command(label="Deselect", command=self._context_deselect)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All", command=self._context_select_all)
        self.context_menu.add_command(label="Deselect All", command=self._context_deselect_all)
        self.bind("<Button-3>", self._show_context_menu)
        
        self.context_item = None
        self.hover_item = None

    def _on_click(self, event):
        """Handle single click for selection"""
        item = self.identify_row(event.y)
        column = self.identify_column(event.x)
        
        if item:
            self._clicked_item = item
            self._click_time = time.time()
            
            # In heading-only mode use first visible column for checkbox toggle behavior
            if column in ("#0", "#1"):
                self.toggle_checkbox(item)
            else:
                # Single click selection
                self.select_item(item)

    def select_item(self, item):
        """Select an item (visual feedback)"""
        # Clear previous selection
        for iid in self.get_children():
            current_tags = list(self.item(iid, "tags"))
            if "selected" in current_tags:
                current_tags.remove("selected")
                self.item(iid, tags=current_tags)

        # Add selection to clicked item
        if item:
            current_tags = list(self.item(item, "tags"))
            if "selected" not in current_tags:
                current_tags.append("selected")
            self.item(item, tags=current_tags)

    def insert(self, parent, index, iid=None, **kwargs):
        """Override insert to initialize checkbox state"""
        if "text" not in kwargs:
            kwargs["text"] = "☐"
        item = super().insert(parent, index, iid, **kwargs)
        self.checkboxes[item] = False
        
        # Set initial tags based on status
        values = kwargs.get('values', [])
        if len(values) > 2:
            status = values[2]
            if status == "Active":
                tags = ("unchecked", "active")
            elif status == "Running":
                tags = ("unchecked", "running")
            elif status == "Completed":
                tags = ("unchecked", "completed")
            else:
                tags = ("unchecked", "inactive")
        else:
            tags = ("unchecked", "inactive")
            
        self.item(item, tags=tags)
        return item
        
    def _on_double_click(self, event):
        """Handle double-click to toggle checkbox"""
        item = self.identify_row(event.y)
        if item:
            self.toggle_checkbox(item)

    def _select_all(self, event):
        """Select all items with Ctrl+A"""
        for item in self.get_children():
            if not self.checkboxes[item]:
                self.toggle_checkbox(item)
        return "break"

    def _show_context_menu(self, event):
        """Show context menu on right-click"""
        item = self.identify_row(event.y)
        if item:
            self.context_item = item
            self.context_menu.post(event.x_root, event.y_root)

    def _on_motion(self, event):
        """Simple row hover feedback."""
        item = self.identify_row(event.y)
        if item == self.hover_item:
            return
        self._clear_hover()
        self.hover_item = item
        if not item:
            return
        tags = list(self.item(item, "tags"))
        if "hover" not in tags:
            tags.append("hover")
            self.item(item, tags=tags)

    def _on_leave(self, _event):
        self._clear_hover()

    def _clear_hover(self):
        if not self.hover_item:
            return
        if self.exists(self.hover_item):
            tags = [t for t in self.item(self.hover_item, "tags") if t != "hover"]
            self.item(self.hover_item, tags=tags)
        self.hover_item = None

    def toggle_checkbox(self, item):
        """Toggle checkbox state with visual feedback"""
        if item in self.checkboxes:
            self.checkboxes[item] = not self.checkboxes[item]
        else:
            self.checkboxes[item] = True
            
        current_tags = list(self.item(item, "tags"))
        
        # Remove checkbox tags
        new_tags = [t for t in current_tags if t not in ("checked", "unchecked")]
        
        # Add appropriate checkbox tag
        if self.checkboxes[item]:
            new_tags.append("checked")
            self.item(item, text="☑")
        else:
            new_tags.append("unchecked")
            self.item(item, text="☐")
            
        self.item(item, tags=new_tags)

    def _context_select(self):
        """Context menu: select current item"""
        if self.context_item:
            if not self.checkboxes[self.context_item]:
                self.toggle_checkbox(self.context_item)

    def _context_deselect(self):
        """Context menu: deselect current item"""
        if self.context_item:
            if self.checkboxes[self.context_item]:
                self.toggle_checkbox(self.context_item)

    def _context_select_all(self):
        """Context menu: select all items"""
        for item in self.get_children():
            if not self.checkboxes[item]:
                self.toggle_checkbox(item)

    def _context_deselect_all(self):
        """Context menu: deselect all items"""
        for item in self.get_children():
            if self.checkboxes[item]:
                self.toggle_checkbox(item)

    def get_checked_items(self):
        """Get all checked items"""
        return [item for item, checked in self.checkboxes.items() if checked]

    def delete(self, *items):
        """Ensure checkbox state is cleaned when items are removed."""
        result = super().delete(*items)
        for item in items:
            self.checkboxes.pop(item, None)
        return result
