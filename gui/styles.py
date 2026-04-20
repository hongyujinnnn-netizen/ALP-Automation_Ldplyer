import ttkbootstrap as tb


def configure_styles(root, style, palette, display_font, mono_font, appearance=None):
    """Configure custom ttkbootstrap styles."""
    root.configure(bg=palette["app_bg"])
    spacing = getattr(appearance, "spacing", {}) or {}
    font_sizes = getattr(appearance, "font_sizes", {}) or {}

    def f(name, default):
        return int(font_sizes.get(name, default))

    def s(name, default):
        return spacing.get(name, default)

    style.configure(
        ".",
        font=(display_font, f("body", 10)),
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
        font=(display_font, f("card_title", 13)),
        foreground=palette["text"],
        background=palette["surface"]
    )
    style.configure("TEntry", padding=s("input_pad", (8, 8)))
    style.configure("TCombobox", padding=s("input_pad", (8, 8)))
    style.configure("Card.TFrame", background=palette["surface"], borderwidth=0, relief="flat")
    style.configure("CardInner.TFrame", background=palette["surface"], borderwidth=0, relief="flat")
    style.configure("Shadow.TFrame", background=palette["border"])
    style.configure("Sidebar.TFrame", background=palette["surface"])
    style.configure("Topbar.TFrame", background=palette["surface"])
    style.configure("SidebarTitle.TLabel", font=(display_font, f("sidebar_title", 14)), foreground=palette["text"], background=palette["surface"])
    style.configure("SidebarSub.TLabel", font=(mono_font, f("meta", 9)), foreground=palette["primary"], background=palette["surface"])
    style.configure("TopTitle.TLabel", font=(display_font, f("top_title", 15)), foreground=palette["text"], background=palette["surface"])
    style.configure("TopSub.TLabel", font=(mono_font, f("meta", 9)), foreground=palette["muted"], background=palette["surface"])
    style.configure("Nav.TButton", font=(display_font, f("button", 10)), anchor="w", padding=s("nav_pad", (10, 8)))
    style.map(
        "Nav.TButton",
        background=[("active", palette["surface_alt"])],
        foreground=[("active", palette["text"])]
    )
    style.configure("NavActive.TButton", font=(display_font, f("button", 10)), anchor="w", padding=s("nav_pad", (10, 8)))
    style.configure("SidebarSection.TLabel", font=(display_font, f("meta", 9)), foreground=palette["muted"], background=palette["surface"])
    style.configure("MetricLabel.TLabel", font=(display_font, f("small", 8)), foreground=palette["muted"], background=palette["surface"])
    style.configure("MetricValue.TLabel", font=(mono_font, f("metric", 28)), foreground=palette["text"], background=palette["surface"])
    style.configure("MetricSub.TLabel", font=(mono_font, f("meta", 9)), foreground=palette["muted"], background=palette["surface"])

    style.configure(
        "TNotebook.Tab",
        padding=s("notebook_tab_pad", (16, 11)),
        font=(display_font, f("body", 10))
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
        rowheight=int(s("tree_row_height", 28)),
        font=(mono_font, f("meta", 9)),
        background=palette["surface"],
        fieldbackground=palette["surface"],
        foreground=palette["text"],
        borderwidth=0
    )
    
    style.configure(
        "Custom.Treeview.Heading",
        font=(display_font, f("body", 10)),
        padding=s("tree_heading_pad", (8, 7)),
        relief="flat",
        foreground=palette["muted"],
        background=palette["surface_alt"]
    )
    
    # Configure button styles
    for button_style in ("success.TButton", "danger.TButton", "warning.TButton", "info.TButton"):
        style.configure(button_style, font=(display_font, f("button", 10)), padding=s("button_pad", (10, 7)))
    
    # Configure label styles
    style.configure(
        "Title.TLabel",
        font=(display_font, f("title", 18)),
        foreground=palette["text"]
    )
    
    style.configure(
        "Subtitle.TLabel",
        font=(mono_font, f("subtitle", 10)),
        foreground=palette["muted"]
    )
    style.configure(
        "SectionTitle.TLabel",
        font=(display_font, f("section", 16)),
        foreground=palette["text"]
    )
    style.configure(
        "CardItemTitle.TLabel",
        font=(display_font, f("card_title", 11)),
        foreground=palette["text"],
        background=palette["surface"],
    )
    style.configure(
        "HeroTitle.TLabel",
        font=(display_font, f("hero", 21)),
        foreground=palette["text"]
    )
    style.configure(
        "HeroSub.TLabel",
        font=(mono_font, f("subtitle", 10)),
        foreground=palette["muted"]
    )
    style.configure(
        "Chip.TLabel",
        font=(display_font, f("meta", 9)),
        foreground=palette["text"]
    )
    style.configure(
        "StatusPill.TLabel",
        font=(display_font, f("meta", 9)),
        foreground=palette["text"],
        background=palette["surface_alt"],
        padding=s("status_pad", (8, 3)),
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
        font=(display_font, f("button", 10)),
        padding=s("primary_button_pad", (14, 8)),
        background=palette["primary"],
        foreground=palette["primary_fg"],
    )
    style.map(
        "Primary.TButton",
        background=[("active", palette["primary_active"]), ("disabled", palette["surface_alt_2"])],
    )

    style.configure(
        "Ctrl.TButton",
        font=(display_font, f("button", 10)),
        padding=s("button_pad", (10, 7)),
        background=palette["surface_alt"],
        foreground=palette["text"],
        bordercolor=palette["border_alt"],
        relief="solid",
        borderwidth=1,
    )

    style.configure(
        "Ghost.TButton",
        font=(display_font, f("button", 10)),
        padding=s("button_pad", (8, 6)),
        background=palette["surface"],
        foreground=palette["muted"],
    )
    style.map(
        "Ghost.TButton",
        foreground=[("active", palette["text"])],
    )
