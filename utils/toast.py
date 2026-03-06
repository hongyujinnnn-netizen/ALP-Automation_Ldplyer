import tkinter as tk
import time

# ==================== TOAST NOTIFICATION ====================
class ToastNotification:
    """Simplified toast notification system for standard tkinter"""
    
    def __init__(self, parent):
        self.parent = parent
        self.toasts = []
        self.toast_queue = []
        self.is_showing = False
        
    def show(self, message, title="Notification", duration=3000, style="info"):
        """Show a toast notification"""
        self.toast_queue.append({
            'message': message,
            'title': title,
            'duration': duration,
            'style': style
        })
        self._process_queue()
    
    def _process_queue(self):
        """Process the notification queue"""
        if self.is_showing or not self.toast_queue:
            return
            
        self.is_showing = True
        toast_data = self.toast_queue.pop(0)
        self._create_toast(**toast_data)
    
    def _create_toast(self, message, title, duration, style):
        """Create and show a toast window"""
        # Create toast window
        toast = tk.Toplevel(self.parent)
        toast.title(title)
        toast.geometry("350x100+{}+{}".format(
            self.parent.winfo_x() + self.parent.winfo_width() - 370,
            self.parent.winfo_y() + 50
        ))
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        
        # Set background color based on style
        colors = {
            "info": "#d1ecf1",
            "success": "#d4edda", 
            "warning": "#fff3cd",
            "danger": "#f8d7da"
        }
        bg_color = colors.get(style, "#d1ecf1")
        toast.configure(bg=bg_color)
        
        # Toast content
        content = tk.Frame(toast, bg=bg_color)
        content.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Title
        title_label = tk.Label(
            content,
            text=title,
            font=("Segoe UI", 10, "bold"),
            bg=bg_color,
            fg="#000000"
        )
        title_label.pack(anchor="w", padx=15, pady=(10, 0))
        
        # Message
        message_label = tk.Label(
            content,
            text=message,
            font=("Segoe UI", 9),
            bg=bg_color,
            fg="#000000",
            wraplength=300
        )
        message_label.pack(anchor="w", padx=15, pady=(5, 15), fill="x")
        
        # Progress bar for auto-close (simulated with a frame)
        progress_container = tk.Frame(content, bg=bg_color, height=4)
        progress_container.pack(fill="x", padx=10, pady=(0, 5))
        progress_container.pack_propagate(False)
        
        progress_bar = tk.Frame(progress_container, bg=self._get_progress_color(style), height=4)
        progress_bar.pack(side="left", fill="y")
        
        # Animate in
        toast.attributes('-alpha', 0.0)
        self._fade_in(toast)
        
        # Start auto-close
        self._start_auto_close(toast, progress_bar, duration, progress_container)
        
        self.toasts.append(toast)
    
    def _get_progress_color(self, style):
        """Get progress bar color based on style"""
        colors = {
            "info": "#17a2b8",
            "success": "#28a745",
            "warning": "#ffc107", 
            "danger": "#dc3545"
        }
        return colors.get(style, "#17a2b8")
    
    def _fade_in(self, toast):
        """Fade in animation"""
        current_alpha = toast.attributes('-alpha')
        if current_alpha < 1.0:
            toast.attributes('-alpha', current_alpha + 0.1)
            self.parent.after(20, lambda: self._fade_in(toast))
    
    def _start_auto_close(self, toast, progress_bar, duration, container):
        """Start auto-close countdown"""
        def update(step=0, total_steps=60):
            if step < total_steps:
                # Update progress bar width
                progress_width = int((container.winfo_width() * (total_steps - step)) / total_steps)
                progress_bar.configure(width=progress_width)
                self.parent.after(duration // total_steps, lambda: update(step + 1, total_steps))
            else:
                self._close_toast(toast)
        
        # Wait a bit for the window to be fully rendered
        self.parent.after(100, update)
    
    def _close_toast(self, toast):
        """Close toast with fade out"""
        def fade_out():
            current_alpha = toast.attributes('-alpha')
            if current_alpha > 0:
                toast.attributes('-alpha', current_alpha - 0.1)
                self.parent.after(20, fade_out)
            else:
                toast.destroy()
                if toast in self.toasts:
                    self.toasts.remove(toast)
                self.is_showing = False
                self._process_queue()
        
        fade_out()