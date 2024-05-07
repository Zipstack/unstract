# KEY_FUNCTION for cache settings
def custom_key_function(key: str, key_prefix: str, version: int) -> str:
    version = int(version)
    if version > 1:
        return f"{key_prefix}:{version}:{key}"
    if key_prefix:
        return f"{key_prefix}:{key}"
    else:
        return key
