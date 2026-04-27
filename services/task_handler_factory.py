"""Task handler creation and configuration.

Centralizes the selection and wiring of concrete task handlers so the GUI
layer no longer needs to know about handler classes, their import paths,
or their post-construction attribute contracts.

The factory is intentionally small and explicit. New task types are added
either by editing ``_BUILDERS`` or by calling :meth:`TaskHandlerFactory.register`
from a plugin module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict


class UnsupportedTaskTypeError(ValueError):
    """Raised when no handler is registered for a given task type."""


@dataclass(slots=True)
class TaskHandlerContext:
    """All inputs needed to construct and configure a task handler.

    Grouped into three logical sections:

    * Runtime primitives the handler needs to operate (emulator, logging,
      pause/running signals).
    * Common config shared by every task type.
    * Task-specific config consumed only by some handlers (registration
      contact info, content queue manager).

    Fields are kept optional where reasonable so the GUI can build one
    context object regardless of the task type currently selected.
    """

    # Runtime primitives
    emulator: Any
    log: Callable[..., Any]
    pause_event: Any
    running_flag: Callable[[], bool]

    # Common config
    blocked_countries: list[str] = field(default_factory=list)
    auto_arrange_ld: bool = False
    state_callback: Callable[..., Any] | None = None
    verify_account: bool = False
    scroll_after_post: bool = False
    random_like: bool = True
    clear_cache: bool = False

    # Task-specific config
    reg_contact_mode: str = "random_phone"
    reg_contact_value: str = ""
    reg_phone_prefix: str = ""
    content_manager: Any | None = None
    use_content_queue: bool = False


# Builders return a fully-configured handler instance.
HandlerBuilder = Callable[[TaskHandlerContext], Any]


def _apply_common_config(handler: Any, ctx: TaskHandlerContext) -> None:
    """Apply config attributes shared by every handler."""
    handler.blocked_countries = list(ctx.blocked_countries)
    handler.auto_arrange_ld = bool(ctx.auto_arrange_ld)
    handler.state_callback = ctx.state_callback


def _apply_reg_contact_config(handler: Any, ctx: TaskHandlerContext) -> None:
    """Apply registration/contact config used by scroll and reg_account."""
    handler.contact_mode = ctx.reg_contact_mode
    handler.contact_value = ctx.reg_contact_value.strip()
    handler.phone_prefix = ctx.reg_phone_prefix.strip()


def _build_scroll(ctx: TaskHandlerContext) -> Any:
    from core.logic.task_scroll import ScrollTaskHandler

    handler = ScrollTaskHandler(ctx.emulator, ctx.log, ctx.pause_event, ctx.running_flag)
    _apply_common_config(handler, ctx)
    _apply_reg_contact_config(handler, ctx)
    handler.random_like = bool(ctx.random_like)
    return handler


def _build_reg_account(ctx: TaskHandlerContext) -> Any:
    from core.logic.reg_account import RegAccountTaskHandler

    handler = RegAccountTaskHandler(ctx.emulator, ctx.log, ctx.pause_event, ctx.running_flag)
    _apply_common_config(handler, ctx)
    _apply_reg_contact_config(handler, ctx)
    return handler


def _build_reels(ctx: TaskHandlerContext) -> Any:
    from core.logic.task_reels import ReelsTaskHandler

    content_manager = ctx.content_manager if ctx.use_content_queue else None
    handler = ReelsTaskHandler(
        ctx.emulator,
        ctx.log,
        ctx.pause_event,
        ctx.running_flag,
        content_manager,
    )
    _apply_common_config(handler, ctx)
    return handler


def _build_test_feature(ctx: TaskHandlerContext) -> Any:
    from tests.test_feature import TestFeatureTaskHandler

    handler = TestFeatureTaskHandler(ctx.emulator, ctx.log, ctx.pause_event, ctx.running_flag)
    _apply_common_config(handler, ctx)
    return handler


def _build_login(ctx: TaskHandlerContext) -> Any:
    from core.logic.login_account import LoginAccountTaskHandler

    handler = LoginAccountTaskHandler(ctx.emulator, ctx.log, ctx.pause_event, ctx.running_flag)
    _apply_common_config(handler, ctx)
    return handler


_BUILDERS: Dict[str, HandlerBuilder] = {
    "scroll": _build_scroll,
    "reg_account": _build_reg_account,
    "reels": _build_reels,
    "test_feature": _build_test_feature,
    "login": _build_login,
}


class TaskHandlerFactory:
    """Resolve a ``task_type`` string to a fully-configured task handler.

    Keeping this in the service layer (instead of GUI) means adding a new
    task type does not require touching the GUI module. Handler imports are
    deferred to keep startup fast and to avoid pulling test-only modules
    into the main process unless requested.
    """

    def __init__(self, builders: Dict[str, HandlerBuilder] | None = None) -> None:
        self._builders: Dict[str, HandlerBuilder] = dict(builders or _BUILDERS)

    def register(self, task_type: str, builder: HandlerBuilder) -> None:
        """Register or override a builder for ``task_type``."""
        self._builders[task_type] = builder

    def supports(self, task_type: str) -> bool:
        return task_type in self._builders

    def create(self, task_type: str, context: TaskHandlerContext) -> Any:
        """Build and return a configured handler for ``task_type``.

        Raises:
            UnsupportedTaskTypeError: if ``task_type`` has no registered builder.
        """
        try:
            builder = self._builders[task_type]
        except KeyError as exc:
            raise UnsupportedTaskTypeError(
                f"No task handler registered for task_type={task_type!r}"
            ) from exc
        return builder(context)
