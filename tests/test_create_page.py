import unittest
from unittest.mock import Mock, patch

from core.tasks.create_page import CreatePageTaskHandler, PageProfile


class CreatePageFlowTests(unittest.TestCase):
    def _handler(self):
        pause_event = Mock()
        pause_event.is_set.return_value = True
        return CreatePageTaskHandler(Mock(), lambda *_args, **_kwargs: None, pause_event, lambda: True)

    def _stub_common_steps(self, handler):
        handler._open_menu_tab = Mock(return_value=True)
        handler._open_pages_section = Mock(return_value=True)
        handler._tap_create_new_page = Mock(return_value=True)
        handler._tap_get_started = Mock(return_value=True)
        handler._fill_page_name = Mock(return_value=True)
        handler._tap_next = Mock(return_value=True)

    @patch("core.tasks.handler.handle_create_page.time.sleep", return_value=None)
    def test_category_submit_still_handles_next_prompts(self, _sleep):
        handler = self._handler()
        self._stub_common_steps(handler)
        handler._fill_page_category = Mock(return_value=True)
        handler._tap_create_page_submit = Mock(return_value=True)
        handler._handle_next_notifications_prompt = Mock(return_value=2)

        result = handler._run_create_page_steps_once(
            Mock(),
            "LDPlayer-1",
            PageProfile(name="Demo Page", category="Digital creator"),
        )

        self.assertTrue(result)
        handler._fill_page_category.assert_called_once()
        handler._tap_create_page_submit.assert_not_called()
        handler._handle_next_notifications_prompt.assert_called_once()

    @patch("core.tasks.handler.handle_create_page.time.sleep", return_value=None)
    def test_fallback_submit_handles_next_prompts_after_create(self, _sleep):
        handler = self._handler()
        self._stub_common_steps(handler)
        events = []
        handler._fill_page_category = Mock(return_value=False)
        handler._tap_create_page_submit = Mock(side_effect=lambda *_args: events.append("submit") or True)
        handler._handle_next_notifications_prompt = Mock(
            side_effect=lambda *_args: events.append("prompt") or 1
        )

        result = handler._run_create_page_steps_once(
            Mock(),
            "LDPlayer-1",
            PageProfile(name="Demo Page"),
        )

        self.assertTrue(result)
        handler._fill_page_category.assert_not_called()
        self.assertEqual(events, ["submit", "prompt"])


if __name__ == "__main__":
    unittest.main()
