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
        parallel_ld: int,
        start_same_time: bool,
        boot_delay: int,
        task_duration_seconds: int,
        max_videos: int,
    ) -> TaskRunRequest:
        return TaskRunRequest(
            selected_ld_names=selected_ld_names,
            task_type=task_type,
            parallel_ld=parallel_ld,
            start_same_time=start_same_time,
            boot_delay=boot_delay,
            task_duration_seconds=task_duration_seconds,
            max_videos=max_videos,
        )

    def create_runner(self, **kwargs) -> object:
        return self.task_service.create_runner(**kwargs)
