import unittest
from unittest.mock import Mock

from test_feature import TestFeatureTaskHandler


class TestFeaturePageRowHelpers(unittest.TestCase):
    def _build_handler(self):
        pause_event = Mock()
        pause_event.is_set.return_value = True
        return TestFeatureTaskHandler(Mock(), lambda *_args, **_kwargs: None, pause_event, lambda: True)

    def test_hierarchy_target_prefers_first_row_below_anchor(self):
        handler = self._build_handler()
        xml = """
        <hierarchy>
            <node text="Pages you manage" bounds="[40,180][680,230]" />
            <node text="My First Page" bounds="[88,286][412,334]" clickable="false" />
            <node text="See options" bounds="[620,282][708,334]" clickable="true" />
            <node text="Second Page" bounds="[88,416][360,462]" clickable="false" />
        </hierarchy>
        """

        target = handler._find_page_row_target_from_hierarchy(xml, screen_width=720)

        self.assertIsNotNone(target)
        self.assertEqual(target["label"], "My First Page")
        self.assertEqual(target["bounds"]["top"], 286)

    def test_hierarchy_target_can_match_requested_page_name(self):
        handler = self._build_handler()
        xml = """
        <hierarchy>
            <node text="Pages you manage" bounds="[40,180][680,230]" />
            <node text="Alpha Page" bounds="[88,286][348,334]" clickable="false" />
            <node text="Bravo Page" bounds="[88,416][360,462]" clickable="false" />
        </hierarchy>
        """

        target = handler._find_page_row_target_from_hierarchy(
            xml,
            screen_width=720,
            page_name="Bravo",
        )

        self.assertIsNotNone(target)
        self.assertEqual(target["label"], "Bravo Page")
        self.assertEqual(target["bounds"]["top"], 416)

    def test_fallback_points_stay_in_row_area_not_screen_bottom(self):
        points = TestFeatureTaskHandler._build_page_row_fallback_points(
            {
                "left": 36,
                "top": 980,
                "right": 520,
                "bottom": 1040,
            },
            screen_width=720,
            screen_height=1280,
        )

        self.assertEqual(points[0][0], 113)
        self.assertLessEqual(points[0][1], int(1280 * 0.72))
        self.assertLessEqual(points[-1][1], int(1280 * 0.72))

    def test_extract_managed_page_names_handles_large_anchor_container(self):
        handler = self._build_handler()
        xml = """
        <hierarchy>
            <node package="com.facebook.katana" text="Pages you manage" content-desc="Pages you manage" bounds="[0,136][720,616]" />
            <node package="com.facebook.katana" text="Alpha Studio" bounds="[92,286][360,336]" />
            <node package="com.facebook.katana" content-desc="Bravo Market" bounds="[92,408][390,458]" />
            <node package="com.facebook.katana" text="Search" bounds="[616,48][720,136]" />
        </hierarchy>
        """

        names = handler._extract_managed_page_names_from_hierarchy(xml, screen_height=1280)

        self.assertEqual(names, ["Alpha Studio", "Bravo Market"])

    def test_extract_managed_page_names_ignores_noise(self):
        handler = self._build_handler()
        xml = """
        <hierarchy>
            <node package="com.facebook.katana" text="Pages you manage" bounds="[40,180][680,230]" />
            <node package="com.facebook.katana" text="See all" bounds="[520,182][670,228]" />
            <node package="com.facebook.katana" text="2 new" bounds="[88,270][180,312]" />
            <node package="com.facebook.katana" text="My Real Page" bounds="[88,338][360,386]" />
        </hierarchy>
        """

        names = handler._extract_managed_page_names_from_hierarchy(xml, screen_height=1280)

        self.assertEqual(names, ["My Real Page"])


if __name__ == "__main__":
    unittest.main()
