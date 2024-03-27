import logging
import unittest

from unstract.core.llm_helper.llm_cache import LLMCache

CRON_GEN_ERROR = "Cron string could not be generated"


class LLMCacheTests(unittest.TestCase):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    # @unittest.skip("Skip")
    def test_cache_clear(self):
        cache = LLMCache(cache_key_prefix="cache:test:")
        cache.set_for_prompt("prompt1", "response1")
        cache.set_for_prompt("prompt2", "response2")
        cache.clear_by_prefix()
        self.assertEqual(
            cache.get_for_prompt("prompt1"), "", "Cache is not cleared"
        )


if __name__ == "__main__":
    unittest.main()
