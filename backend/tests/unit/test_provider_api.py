import pytest

from app.schemas.provider import ProviderPublicInfo


@pytest.mark.asyncio
async def test_provider_list_api_returns_only_public_schema(monkeypatch):
    from app.api import provider_api

    monkeypatch.setattr(
        provider_api,
        "list_public_providers",
        lambda capabilities: [
            ProviderPublicInfo(
                providerId="provider-a",
                displayName="model-a",
                model="model-a",
                capabilities=["text_generation"],
            )
        ],
    )
    result = await provider_api.get_provider_list()
    dumped = result.model_dump(by_alias=True)
    assert dumped["data"][0]["providerId"] == "provider-a"
    assert "baseUrl" not in dumped["data"][0]
    assert "apiKeyEnv" not in dumped["data"][0]
