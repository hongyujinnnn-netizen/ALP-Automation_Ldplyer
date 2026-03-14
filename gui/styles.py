import ttkbootstrap as tb


def configure_styles(root, style, palette, display_font, mono_font):
    """Configure custom ttkbootstrap styles."""
    root.configure(bg=palette["app_bg"])

    style.configure(
        ".",
        font=(display_font, 10),
        background=palette["surface"],
        foreground=palette["text"],
    )
    style.configure(
        "TLabelframe",
        borderwidth=0,
        relief="flat",
        background=palette["surface"]
    )
    style.configure(
        "TLabelframe.Label",
        font=(display_font, 13),
        foreground=palette["text"],
        background=palette["surface"]
    )
    style.configure("TEntry", padding=(8, 8))
    style.configure("TCombobox", padding=(8, 8))
    style.configure("Card.TFrame", background=palette["surface"], borderwidth=0, relief="flat")
    style.configure("CardInner.TFrame", background=palette["surface"], borderwidth=0, relief="flat")
    style.configure("Shadow.TFrame", background=palette["border"])
    style.configure("Sidebar.TFrame", background=palette["surface"])
    style.configure("Topbar.TFrame", background=palette["surface"])
    style.configure("SidebarTitle.TLabel", font=(display_font, 14), foreground=palette["text"], background=palette["surface"])
    style.configure("SidebarSub.TLabel", font=(mono_font, 9), foreground=palette["primary"], background=palette["surface"])
    style.configure("TopTitle.TLabel", font=(display_font, 15), foreground=palette["text"], background=palette["surface"])
    style.configure("TopSub.TLabel", font=(mono_font, 9), foreground=palette["muted"], background=palette["surface"])
    style.configure("Nav.TButton", font=(display_font, 10), anchor="w", padding=(10, 8))
    style.map(
        "Nav.TButton",
        background=[("active", palette["surface_alt"])],
        foreground=[("active", palette["text"])]
    )
    style.configure("NavActive.TButton", font=(display_font, 10), anchor="w", padding=(10, 8))
    style.configure("SidebarSection.TLabel", font=(display_font, 9), foreground="#64748B", background=palette["surface"])
    style.configure("MetricLabel.TLabel", font=(display_font, 8), foreground="#6B7B90", background=palette["surface"])
    style.configure("MetricValue.TLabel", font=(mono_font, 28), foreground=palette["text"], background=palette["surface"])
    style.configure("MetricSub.TLabel", font=(mono_font, 9), foreground=palette["muted"], background=palette["surface"])

    style.configure(
        "TNotebook.Tab",
        padding=(16, 11),
        font=(display_font, 10)
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", palette["surface"]), ("!selected", palette["surface_alt"])],
        foreground=[("selected", palette["primary"]), ("!selected", palette["muted"])],
        bordercolor=[("selected", palette["primary"]), ("!selected", palette["border"])]
    )
    # Hidden tab style - used only for the outer main notebook (tabs navigated via top bar buttons)
    style.layout("Hidden.TNotebook.Tab", [])
    style.configure("Hidden.TNotebook", tabmargins=0)

    # Configure Treeview row height
    style.configure(
        "Custom.Treeview",
        rowheight=28,
        font=(mono_font, 9),
        background=palette["surface"],
        fieldbackground=palette["surface"],
        foreground=palette["text"],
        borderwidth=0
    )
    
    style.configure(
        "Custom.Treeview.Heading",
        font=(display_font, 10),
        padding=(8, 7),
        relief="flat",
        foreground=palette["muted"],
        background=palette["surface_alt"]
    )
    
    # Configure button styles
    for button_style in ("success.TButton", "danger.TButton", "warning.TButton", "info.TButton"):
        style.configure(button_style, font=(display_font, 10), padding=(10, 7))
    
    # Configure label styles
    style.configure(
        "Title.TLabel",
        font=(display_font, 18),
        foreground=palette["text"]
    )
    
    style.configure(
        "Subtitle.TLabel",
        font=(mono_font, 10),
        foreground=palette["muted"]
    )
    style.configure(
        "SectionTitle.TLabel",
        font=(display_font, 16),
        foreground=palette["text"]
    )
    style.configure(
        "HeroTitle.TLabel",
        font=(display_font, 21),
        foreground=palette["text"]
    )
    style.configure(
        "HeroSub.TLabel",
        font=(mono_font, 10),
        foreground=palette["muted"]
    )
    style.configure(
        "Chip.TLabel",
        font=(display_font, 9),
        foreground=palette["text"]
    )

    # Custom scrollbars
    style.configure(
        "Vertical.TScrollbar",
        background=palette["border"],
        troughcolor=palette["surface"],
        arrowcolor=palette["muted"],
        borderwidth=0,
        relief="flat",
        width=8,
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=palette["border"],
        troughcolor=palette["surface"],
        arrowcolor=palette["muted"],
        borderwidth=0,
        relief="flat",
        width=6,
    )

    # Button hierarchy
    style.configure(
        "Primary.TButton",
        font=(display_font, 10),
        padding=(14, 8),
        background="#00C4D9",
        foreground="#040608",
    )
    style.map(
        "Primary.TButton",
        background=[("active", "#00E5FF"), ("disabled", "#1A2530")],
    )

    style.configure(
        "Ctrl.TButton",
        font=(display_font, 10),
        padding=(10, 7),
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border_alt"],
        relief="solid",
        borderwidth=1,
    )

    style.configure(
        "Ghost.TButton",
        font=("Segoe UI", 10),
        padding=(8, 6),
        background=palette["surface"],
        foreground=palette["muted"],
    )
    style.map(
        "Ghost.TButton",
        foreground=[("active", palette["text"])],
    )
