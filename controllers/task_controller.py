from __future__ import annotations

from services.task_service import TaskRunRequest, TaskService


class TaskController:
    """Controller facade for task orchestration requests."""

    def __init__(self, task_service: TaskService) -> None:
        self.task_service = task_service

    def build_request(
        self,
        selected_ld_names: list[str],
        task_type: str,
        task_template: str,
        parallel_ld: int,
        start_same_time: bool,
        auto_arrange_ld: bool,
        boot_delay: int,
        task_duration_seconds: int,
        max_videos: int,
        page_per_account: int,
        scroll_after_post: bool,
        verify_account: bool,
    ) -> TaskRunRequest:
        return TaskRunRequest(
            selected_ld_names=selected_ld_names,
            task_type=task_type,
            task_template=task_template,
            parallel_ld=parallel_ld,
            start_same_time=start_same_time,
            auto_arrange_ld=auto_arrange_ld,
            boot_delay=boot_delay,
            task_duration_seconds=task_duration_seconds,
            max_videos=max_videos,
            page_per_account=page_per_account,
            scroll_after_post=scroll_after_post,
            verify_account=verify_account,
        )

    def create_runner(self, **kwargs) -> object:
        return self.task_service.create_runner(**kwargs)
