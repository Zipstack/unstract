from django.test import SimpleTestCase

from platform_audit import actions
from platform_audit.actions import Action, all_actions, get_action, register_action


class ActionRegistryTests(SimpleTestCase):
    def setUp(self) -> None:
        snapshot = dict(actions._REGISTRY)
        self.addCleanup(lambda: actions._REGISTRY.clear() or actions._REGISTRY.update(snapshot))

    def test_every_oss_action_is_registered(self) -> None:
        for key in Action:
            with self.subTest(key=key):
                self.assertIsNotNone(get_action(key))

    def test_reregistering_the_same_action_is_a_noop(self) -> None:
        before = len(all_actions())
        register_action("key.rotated", "Key rotated", "keys")
        self.assertEqual(len(all_actions()), before)

    def test_conflicting_registration_raises(self) -> None:
        with self.assertRaises(ValueError):
            register_action("key.rotated", "Something else", "keys")

    def test_extension_registers_a_new_action(self) -> None:
        register_action("review_key.created", "Review key created", "keys")
        self.assertEqual(get_action("review_key.created").label, "Review key created")
