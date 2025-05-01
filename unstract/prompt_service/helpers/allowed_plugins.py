from typing import List

ALLOWED_PLUGINS = [
    "unstract.prompt_service.plugins.default",
    "unstract.prompt_service.plugins.langchain",
    "unstract.prompt_service.plugins.openai",
    "unstract.prompt_service.plugins.anthropic",
    "unstract.prompt_service.plugins.cohere",
    "unstract.prompt_service.plugins.azure_openai",
    "unstract.prompt_service.plugins.bedrock",
    "unstract.prompt_service.plugins.vertex",
    "unstract.prompt_service.plugins.llama",
    # Add other allowed plugins here
]

def is_plugin_allowed(plugin_name: str) -> bool:
    """
    Check if the plugin name is in the allowed list.
    
    Args:
        plugin_name: The name of the plugin to check
        
    Returns:
        bool: True if the plugin is allowed, False otherwise
    """
    return plugin_name in ALLOWED_PLUGINS
