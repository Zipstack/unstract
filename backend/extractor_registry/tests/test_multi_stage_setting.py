"""The per-environment switch for offering Multi-Stage in the Studio (UN-3917).

`SimpleTestCase`: no DB, `unit-backend` tier.
"""

from django.test import SimpleTestCase, override_settings

from extractor_registry import ExtractorAgentKey, ExtractorAgentSpec, get_agent
from extractor_registry.catalogue import multi_stage_enabled


class MultiStageSettingTest(SimpleTestCase):
    @override_settings(APS_MULTI_STAGE_ENABLED=True)
    def test_on_when_the_setting_is_true(self) -> None:
        self.assertIs(multi_stage_enabled(), True)

    @override_settings(APS_MULTI_STAGE_ENABLED=False)
    def test_off_when_the_setting_is_false(self) -> None:
        self.assertIs(multi_stage_enabled(), False)

    def test_off_when_the_setting_is_missing(self) -> None:
        with self.settings():
            from django.conf import settings

            del settings.APS_MULTI_STAGE_ENABLED
            self.assertIs(multi_stage_enabled(), False)

    def test_the_shipped_row_follows_the_setting(self) -> None:
        """The row is built from the setting at import, under test settings."""
        self.assertEqual(
            get_agent(ExtractorAgentKey.MULTI_STAGE).available, multi_stage_enabled()
        )
        self.assertFalse(multi_stage_enabled(), "the setting must default off")

    def test_the_row_is_valid_when_switched_on(self) -> None:
        """Switching it on must not trip `__post_init__`, or the catalogue would
        fail to import on exactly the deployments that enable it."""
        multi = get_agent(ExtractorAgentKey.MULTI_STAGE)
        on = ExtractorAgentSpec(**{**multi.__dict__, "available": True})
        self.assertTrue(on.available)
        self.assertFalse(on.is_default, "turning it on must not make it the default")
