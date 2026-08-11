from app.core.config import (
    AppConfig,
    DatabaseConfig,
    LogConfig,
    Settings,
    get_settings,
    resolve_env_files,
)


class TestAppConfig:
    def test_defaults(self):
        c = AppConfig()
        assert c.debug is False
        assert c.host == "0.0.0.0"
        assert c.json_camel_case is True


class TestDatabaseConfig:
    def test_defaults(self):
        c = DatabaseConfig()
        assert c.url == ""
        assert c.echo is False
        assert c.pool_size == 20
        assert c.auto_migrate is False


class TestLogConfig:
    def test_defaults(self):
        c = LogConfig()
        assert c.level == "INFO"
        assert c.dir == "logs/"
        assert c.types == "console"


class TestResolveEnvFiles:
    def test_baseline_only_without_app_env(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        assert resolve_env_files() == (".env",)

    def test_with_app_env(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "local")
        assert resolve_env_files() == (".env", ".env.local")

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "  test  ")
        assert resolve_env_files() == (".env", ".env.test")


class TestSettings:
    def test_from_env_file(self):
        get_settings.cache_clear()
        s = get_settings()
        assert s.app.name == "flowchart-toolbox"
        assert s.app.debug is False

    def test_get_settings_singleton(self):
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_database_url_from_env(self):
        get_settings.cache_clear()
        s = get_settings()
        assert "test_db" in s.database.url
        assert "postgresql" in s.database.url

    def test_database_echo_from_env(self):
        get_settings.cache_clear()
        s = get_settings()
        assert s.database.echo is True


class TestEnvLayering:
    def test_app_env_file_overrides_baseline(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "APP__DEBUG=false\nAPP__PORT=8000\nAPP__NAME=baseline\n"
        )
        (tmp_path / ".env.local").write_text("APP__DEBUG=true\nAPP__PORT=9090\n")
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.delenv("APP__DEBUG", raising=False)
        monkeypatch.delenv("APP__PORT", raising=False)
        monkeypatch.delenv("APP__NAME", raising=False)

        s = Settings(_env_file=resolve_env_files())
        assert s.app.debug is True
        assert s.app.port == 9090
        assert s.app.name == "baseline"

    def test_runtime_env_overrides_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("APP__PORT=8000\n")
        (tmp_path / ".env.local").write_text("APP__PORT=9090\n")
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("APP__PORT", "7070")

        s = Settings(_env_file=resolve_env_files())
        assert s.app.port == 7070

    def test_missing_overlay_file_uses_baseline(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("APP__PORT=8000\nAPP__NAME=only-baseline\n")
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.delenv("APP__PORT", raising=False)
        monkeypatch.delenv("APP__NAME", raising=False)
        assert not (tmp_path / ".env.local").exists()

        s = Settings(_env_file=resolve_env_files())
        assert s.app.port == 8000
        assert s.app.name == "only-baseline"


class TestEnvNestedDelimiter:
    def test_double_underscore_maps_to_app_debug(self, monkeypatch):
        monkeypatch.setenv("APP__DEBUG", "true")
        monkeypatch.setenv("APP__JSON_CAMEL_CASE", "true")
        s = Settings(_env_file=None)
        assert s.app.debug is True
        assert s.app.json_camel_case is True

    def test_double_underscore_maps_to_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE__URL", "postgresql://test:5432/db")
        s = Settings(_env_file=None)
        assert s.database.url == "postgresql://test:5432/db"

    def test_double_underscore_maps_to_log_level(self, monkeypatch):
        monkeypatch.setenv("LOG__LEVEL", "DEBUG")
        s = Settings(_env_file=None)
        assert s.log.level == "DEBUG"

    def test_double_underscore_maps_to_log_types(self, monkeypatch):
        monkeypatch.setenv("LOG__TYPES", "console,file")
        s = Settings(_env_file=None)
        assert s.log.types == "console,file"


class TestExtraIgnore:
    def test_unknown_env_vars_ignored(self, monkeypatch):
        monkeypatch.setenv("UNKNOWN_VAR", "something")
        monkeypatch.setenv("RANDOM_KEY", "value")
        s = Settings(_env_file=None)
        assert s.app.debug is False

    def test_partial_unknown_with_valid(self, monkeypatch):
        monkeypatch.setenv("APP__DEBUG", "true")
        monkeypatch.setenv("FOO_BAR", "baz")
        s = Settings(_env_file=None)
        assert s.app.debug is True
