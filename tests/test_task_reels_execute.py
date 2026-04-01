import unittest
from unittest.mock import Mock, patch

from core.logic.task_reels import ReelsTaskHandler


class TestReelsExecutePageLoop(unittest.TestCase):
    def test_execute_posts_all_videos_for_each_page_before_switching(self):
        logs = []
        emulator = Mock()
        emulator.is_ld_running.return_value = True
        emulator.name_to_serial = {"US - 01": "127.0.0.1:5555"}

        pause_event = Mock()
        pause_event.is_set.return_value = True

        handler = ReelsTaskHandler(
            emulator,
            lambda message, level="INFO": logs.append(message),
            pause_event,
            lambda: True,
        )
        handler.ensure_device_ready = Mock(return_value=True)
        handler.push_runtime_state = Mock()
        handler.rate_limiter = Mock()
        handler.rate_limiter.can_perform_action.return_value = True

        clicked_page_indexes = []
        folder_indexes = []

        handler.open_facebook = Mock(return_value=True)
        handler.click_facebook_menu = Mock(return_value=True)
        handler.click_profile_dropdown = Mock(return_value=True)
        handler.get_name_pages_by_bounds = Mock(return_value=["Page A", "Page B"])
        handler.click_on_page = Mock(
            side_effect=lambda d, pages, page_to_click: clicked_page_indexes.append(page_to_click) or True
        )
        handler._open_file_manager_with_retry = Mock(return_value=True)
        handler.navigate_to_pictures = Mock(return_value=True)
        handler.click_folder_post_page = Mock(
            side_effect=lambda d, index: folder_indexes.append(index) or True
        )
        handler.hold_on_video = Mock(return_value=True)
        handler.handle_context_menu_after_long_press = Mock(return_value=True)
        handler.check_and_handle_facebook_permission = Mock(return_value=False)
        handler.facebook_first_next = Mock(return_value=True)
        handler.handle_reels_description = Mock(return_value=True)
        handler.delete_video = Mock(return_value=True)
        handler.end_to_accoutn_profile = Mock(return_value=True)
        handler.scroll_facebook_reels = Mock()

        with patch("core.logic.task_reels.U2_AVAILABLE", True), \
             patch("core.logic.task_reels.u2") as mock_u2, \
             patch("core.logic.task_reels.time.sleep", return_value=None):
            device = Mock()
            device.serial = "127.0.0.1:5555"
            selector = Mock()
            selector.exists.return_value = True
            device.return_value = selector
            mock_u2.connect.return_value = device

            result = handler.execute(
                "US - 01",
                max_videos=2,
                page_per_account=2,
                scroll_after_post=False,
                use_content_queue=False,
            )

        self.assertTrue(result)
        self.assertEqual(clicked_page_indexes, [0, 1])
        self.assertEqual(folder_indexes, [2, 3])
        self.assertEqual(handler.hold_on_video.call_count, 4)
        self.assertEqual(handler.delete_video.call_count, 4)
        self.assertEqual(handler.push_runtime_state.call_args_list[-1].kwargs["task"], "Processed 4/4 video")
        self.assertEqual(logs[-1], "Task completed: Processed 4/4 videos successfully")


if __name__ == "__main__":
    unittest.main()
