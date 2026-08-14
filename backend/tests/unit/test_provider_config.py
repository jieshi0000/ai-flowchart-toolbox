import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.providers.config import ProviderConfigurationError, load_provider_configs
from app.schemas.provider import ProviderConfig
from tests.unit.provider_fixtures import provider_entry


class TestProviderConfigLoader:
    def test_provider_file_setting_uses_nested_environment_name(self, monkeypatch):
        monkeypatch.setenv("AI__PROVIDERS_FILE", "config/custom.json")
        settings = Settings(_env_file=None)
        assert settings.ai.providers_file == "config/custom.json"

    def test_loads_list_and_object_shapes_without_exposing_private_fields(self, tmp_path: Path):
        path = tmp_path / "providers.json"
        path.write_text(json.dumps([provider_entry("p1")]), encoding="utf-8")
        configs = load_provider_configs(path)
        assert configs[0].provider_id == "p1"
        public = configs[0].model_dump(by_alias=True)
        assert "baseUrl" in public  # 内部配置可读取
        assert "apiKey" not in public

        path.write_text(json.dumps({"providers": [provider_entry("p2")]}), encoding="utf-8")
        assert load_provider_configs(path)[0].provider_id == "p2"

    def test_missing_file_can_be_empty_or_strict(self, tmp_path: Path):
        assert load_provider_configs(tmp_path / "missing.json") == ()
        with pytest.raises(ProviderConfigurationError):
            load_provider_configs(tmp_path / "missing.json", allow_missing=False)

    def test_duplicate_and_invalid_entries_are_rejected(self, tmp_path: Path):
        path = tmp_path / "providers.json"
        path.write_text(json.dumps([provider_entry("p1"), provider_entry("p1")]), encoding="utf-8")
        with pytest.raises(ProviderConfigurationError):
            load_provider_configs(path)
        path.write_text(json.dumps([provider_entry("p1", baseUrl="http://user:pass@example.com")]), encoding="utf-8")
        with pytest.raises(ProviderConfigurationError):
            load_provider_configs(path)

    def test_provider_config_cross_field_rules(self):
        with pytest.raises(ValidationError):
            ProviderConfig.model_validate(provider_entry("p", adapter="anthropic", protocol="openai_responses"))
        with pytest.raises(ValidationError):
            ProviderConfig.model_validate(provider_entry("p", pollIntervalSeconds=10, maxPollIntervalSeconds=3))
