import tkinter as tk
import ttkbootstrap as tb
from gui.components.scrollable_frame import ScrollableFrame
from gui.components.state_views import StateView
from gui.components.status import StatusPill
from gui.gradient_progress import GradientProgressBar

class SchedulePageMixin:
    def create_schedule_tab(self):
        """Create Schedule tab"""
        schedule_tab = tb.Frame(self.notebook)
        self.notebook.add(schedule_tab, text="Schedule")

        scroller = ScrollableFrame(schedule_tab, bg=self.palette["surface"])
        scroller.pack(fill="both", expand=True)

        self.create_enhanced_schedule(scroller.body)


    def create_enhanced_schedule(self, parent):
        """Create enhanced scheduling section"""
        schedule_frame = self._create_card_section(
            parent,
            "Task Scheduling",
            "Define run windows and repeat cadence.",
        )
        
        # Time settings
        time_frame = tb.Frame(schedule_frame)
        time_frame.pack(fill="x", padx=10, pady=10)
        
        tb.Label(time_frame, text="Schedule Time:", bootstyle="secondary",
                width=15).pack(side="left", padx=5)
        
        # Time entry with better UI
        time_entry = tb.Entry(time_frame, textvariable=self.schedule_time,
                            width=10, font=("Segoe UI", 11))
        time_entry.pack(side="left", padx=5)
        
        # Add time picker button
        tb.Button(time_frame, text="Pick Time",
                 command=self.show_time_picker, bootstyle="secondary").pack(side="left", padx=5)
        
        # Repeat settings
        repeat_frame = tb.Frame(schedule_frame)
        repeat_frame.pack(fill="x", padx=10, pady=10)
        
        tb.Label(repeat_frame, text="Repeat Every:", bootstyle="secondary",
                width=15).pack(side="left", padx=5)
        
        repeat_spinbox = tb.Spinbox(repeat_frame, from_=0, to=24,
                                   textvariable=self.schedule_repeat_hours,
                                   width=5)
        repeat_spinbox.pack(side="left", padx=5)
        
        tb.Label(repeat_frame, text="hours").pack(side="left", padx=5)
        
        # Schedule type
        type_frame = tb.Labelframe(schedule_frame, text="Schedule Type",
                                  bootstyle="secondary", padding=10)
        type_frame.pack(fill="x", padx=10, pady=10)
        
        type_inner = tb.Frame(type_frame)
        type_inner.pack(fill="x", padx=5, pady=5)
        
        tb.Radiobutton(type_inner, text="Daily", variable=self.schedule_daily,
                      value=True, bootstyle="info-toolbutton",
                      command=self.on_schedule_type_change).pack(side="left", padx=10)
        
        tb.Radiobutton(type_inner, text="Weekly", variable=self.schedule_daily,
                      value=False, bootstyle="info-toolbutton",
                      command=self.on_schedule_type_change).pack(side="left", padx=10)
        
        # Days of week (initially hidden)
        self.days_frame = tb.Labelframe(schedule_frame, text="Days of Week",
                                       bootstyle="secondary", padding=10)
        
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        full_days = list(self.schedule_days.keys())
        
        for i, day in enumerate(days):
            chk = tb.Checkbutton(self.days_frame, text=day,
                               variable=self.schedule_days[full_days[i]],
                               bootstyle="primary-square-toggle")
            chk.grid(row=0, column=i, padx=8, pady=5)
        
        # Schedule control button
        control_frame = tb.Frame(schedule_frame)
        control_frame.pack(fill="x", padx=10, pady=20)

        self.schedule_state_pill = StatusPill(
            control_frame,
            "Disabled",
            palette=self.palette,
            text="Schedule: Disabled",
            font=(self.display_font, 9),
            padx=10,
            pady=4,
        )
        self.schedule_state_pill.pack(pady=(0, 10))
        
        self.schedule_enable_btn = tb.Button(
            control_frame,
            text="Enable Schedule",
            command=self.toggle_schedule,
            bootstyle="success",
            width=25
        )
        self.schedule_enable_btn.pack()
        
        # Next run info
        self.next_run_label = tb.Label(
            control_frame,
            text="Next run: Not scheduled",
            bootstyle="secondary"
        )
        self.next_run_label.pack(pady=5)

        self.schedule_state_view = StateView(
            schedule_frame,
            kind="empty",
            title="Schedule is disabled",
            message="Enable scheduling when you want automation to run without manual start.",
            actions=[
                {"text": "Enable", "command": self.start_schedule, "bootstyle": "outline-success"},
            ],
            palette=self.palette,
            display_font=self.display_font,
            mono_font=self.mono_font,
        )
        self.schedule_state_view.pack(fill="x", padx=10, pady=(0, 10))
        
        # Update visibility
        self.on_schedule_type_change()

