def provider_entry(provider_id: str, *, key_env: str = "TEST_PROVIDER_KEY", **overrides):
    value = {
        "providerId": provider_id,
        "displayName": "model-a",
        "adapter": "openai_compatible",
        "protocol": "openai_chat_completions",
        "baseUrl": "https://provider.example/v1",
        "model": "model-a",
        "apiKeyEnv": key_env,
        "capabilities": ["text_generation", "structured_output"],
        "priority": 1,
    }
    value.update(overrides)
    return value
