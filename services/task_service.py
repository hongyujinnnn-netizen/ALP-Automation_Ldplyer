from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from gui.main_window import MainWindow


@dataclass(slots=True)
class TaskRunRequest:
    selected_ld_names: list[str]
    task_type: str
    task_template: str
    parallel_ld: int
    start_same_time: bool
    auto_arrange_ld: bool
    boot_delay: int
    task_duration_seconds: int
    max_videos: int
    page_per_account: int
    scroll_after_post: bool
    verify_account: bool


class TaskService:
    """Creates and coordinates task runners without owning the UI."""

    def create_runner(
        self,
        request: TaskRunRequest,
        running_flag: Callable[[], bool],
        log_func: Callable[..., Any],
        task_handler: Any,
        progress_callback: Callable[[float], None] | None = None,
        emulator: Any = None,
        state_callback: Callable[..., Any] | None = None,
    ) -> MainWindow:
        return MainWindow(
            request.selected_ld_names,
            running_flag,
            request.parallel_ld,
            log_func,
            request.start_same_time,
            request.auto_arrange_ld,
            request.task_type,
            request.task_template,
            task_handler,
            progress_callback,
            request.boot_delay,
            request.task_duration_seconds,
            request.max_videos,
            request.page_per_account,
            request.scroll_after_post,
            request.verify_account,
            emulator=emulator,
            state_callback=state_callback,
        )
