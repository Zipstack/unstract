import logging
import unittest

from unstract.core.llm_helper.enums import LLMResult, PromptContext
from unstract.core.llm_helper.llm_helper import LLMHelper

CRON_GEN_ERROR = "Cron string could not be generated"


class LLMHelperTests(unittest.TestCase):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    # @unittest.skip("Skip")
    def test_cron_string_generation(self):
        prompt = "Run at 6:00 PM every single day"
        # prompt = "Run every alternate day in 4 hour intervals"
        # TODO: Below prompt fails, check on this
        # prompt = "Run every alternate day in 4 hour\
        #      intervals, starting from 4:00PM"
        logging.info(f"Generating for input: {prompt}")
        project_settings = {
            "guid": "test",
        }
        llm_helper = LLMHelper(
            cache_key=project_settings["guid"],
            prompt_context=PromptContext.GENERATE_CRON_STRING,
        )
        llm_response = llm_helper.get_response_from_llm(prompt, use_cache=True)
        if llm_response.result != LLMResult.OK:
            logging.error(f"{CRON_GEN_ERROR}: {llm_response.output}")
            self.fail(f"{CRON_GEN_ERROR}: {llm_response.output}")
        logging.info(
            f"Generated cron: {llm_response.output} "
            f"in {llm_response.time_taken:.3f}s"
        )
        self.assertEqual(llm_response.output, "0 18 * * *")


if __name__ == "__main__":
    unittest.main()
