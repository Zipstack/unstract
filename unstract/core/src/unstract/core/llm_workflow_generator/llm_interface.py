import hashlib
import json
import logging
import os
import time
import uuid

import redis
from llama_index.llms import AzureOpenAI
from unstract.core.llm_helper.config import AzureOpenAIConfig
from unstract.tool_registry.dto import Properties, Tool

# Refactor dated: 19/12/2023 ( Removal of Appkit removal)


class LLMInterface:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    )

    def __init__(
        self,
        prompt_template: str = "azure-open-ai/version-0.1",
    ):
        self.prompt_template = prompt_template
        prompt_file_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "prompts",
            prompt_template,
            "prompt",
        )
        with open(prompt_file_path) as file:
            self.prompt = file.read()

    def get_provisional_workflow_from_llm(
        self,
        workflow_id: str,
        tools: list[Tool],
        user_prompt: str,
        use_cache: bool = False,
    ):
        redis_host = os.environ.get("REDIS_HOST")
        redis_port = os.environ.get("REDIS_PORT")

        if redis_host is None:
            raise RuntimeError("REDIS_HOST environment variable not set")
        redis_password = os.environ.get("REDIS_PASSWORD")
        if redis_password and (
            redis_password == "" or redis_password.lower() == "none"
        ):
            redis_password = None
        ai_service = self.prompt_template.split("/")[0]
        prompt_for_model = self.prompt
        tools_prompt = self.get_tools_description_for_llm(tools)
        prompt_for_model = prompt_for_model.replace("{$tools}", tools_prompt)
        prompt_for_model = prompt_for_model.replace("{$task}", user_prompt)
        logging.debug(prompt_for_model)
        _hash = hashlib.sha1()
        _hash.update(prompt_for_model.encode("utf-8"))
        hash_hex = _hash.hexdigest()
        if ai_service == "azure-open-ai":
            logging.info("Using Azure OpenAI")
            if use_cache:
                try:
                    r = redis.Redis(
                        host=redis_host,
                        port=int(redis_port),
                        password=redis_password,
                    )
                    redis_key = (
                        f"cache:{workflow_id}:workflow_prompt:{hash_hex}"
                    )
                    workflow_bin = r.get(redis_key)
                    if workflow_bin is not None:
                        logging.info("Cache hit")
                        workflow = json.loads(workflow_bin.decode("utf-8"))
                        return {
                            "result": "OK",
                            "output": workflow,
                            "cost_type": "cache",
                            "cost": 0,
                            "time_taken": 0,
                        }
                    else:
                        logging.warning("Cache miss. Will call OpenAI API")
                except Exception as e:
                    logging.warning(f"Error loading from cache: {e}")
                    logging.warning("Will call OpenAI API")

            start_time = time.time()
            try:
                azure_openai_config = AzureOpenAIConfig.from_env()
                llm = AzureOpenAI(
                    model=azure_openai_config.model,
                    deployment_name=azure_openai_config.deployment_name,
                    engine=azure_openai_config.engine,
                    api_key=azure_openai_config.api_key,
                    api_version=azure_openai_config.api_version,
                    azure_endpoint=azure_openai_config.azure_endpoint,
                    api_type=azure_openai_config.api_type,
                    temperature=0,
                    max_retries=10,
                )
                resp = llm.complete(prompt_for_model, stop=["//End of JSON"])
            except Exception as e:
                logging.error(f"OpenAI error: {e}")
                return {
                    "result": "NOK",
                    "output": f"Error from OpenAI: {e}",
                    "cost_type": ai_service,
                    "cost": 0,
                    "time_taken": 0,
                }
            end_time = time.time()
            resp = resp.text
            logging.info(f"OpenAI Response: {resp}")
            time_taken = end_time - start_time

            try:
                workflow = json.loads(resp)
                logging.info("Workflow parsed successfully")
                logging.info(workflow)
            except Exception as e:
                logging.error("Error parsing workflow")
                logging.error(e)
                return {
                    "result": "NOK",
                    "output": "Error from OpenAI",
                    "cost_type": ai_service,
                    "cost": 0,
                    "time_taken": 0,
                }

            for step in workflow["steps"]:
                step["id"] = uuid.uuid4().hex
            # Let's add it to the cache
            try:
                r = redis.Redis(
                    host=redis_host,
                    port=int(redis_port),
                    password=redis_password,
                )
                redis_key = f"cache:{workflow_id}:workflow_prompt:{hash_hex}"
                r.set(redis_key, json.dumps(workflow))
                r.close()
            except Exception as e:
                logging.warning(f"Error saving workflow to cache: {e}")
            return {
                "result": "OK",
                "output": workflow,
                "cost_type": ai_service,
                "cost": 0,
                "time_taken": time_taken,
            }
        else:
            logging.error(f"AI service '{ai_service}' not found")
        return None

    def get_tools_description_for_llm(self, tools: list[Tool]):
        desc = ""
        for tool in tools:
            desc += self.tool_description_for_llm(tool.properties) + "\n"
        return desc

    def tool_description_for_llm(self, properties: Properties) -> str:
        if not properties:
            return ""
        desc = f"- {properties.function_name}("
        desc += f") : {properties.description}"
        return desc
