import sys
from unittest.mock import MagicMock, patch

from app.core.logging import setup_logging


class TestSetupLogging:
    @patch("app.core.logging.get_settings")
    def test_console_mode_adds_stdout_handler(self, mock_settings):
        s = MagicMock()
        s.log.level = "INFO"
        s.log.types = "console"
        s.log.dir = "logs/"
        s.app.name = "python-server"
        mock_settings.return_value = s

        with patch("app.core.logging.logger") as mock_logger:
            setup_logging()
            mock_logger.remove.assert_called_once()
            mock_logger.add.assert_called_once()
            call_args = mock_logger.add.call_args
            assert call_args[0][0] == sys.stdout

    @patch("app.core.logging.get_settings")
    def test_file_mode_creates_log_dir(self, mock_settings, tmp_path):
        s = MagicMock()
        s.log.level = "INFO"
        s.log.types = "file"
        s.log.dir = str(tmp_path / "logs")
        s.app.name = "test-app"
        mock_settings.return_value = s

        with patch("app.core.logging.logger"):
            setup_logging()
            assert (tmp_path / "logs").exists()

    @patch("app.core.logging.get_settings")
    def test_dual_mode_registers_two_handlers(self, mock_settings):
        s = MagicMock()
        s.log.level = "DEBUG"
        s.log.types = "console,file"
        s.log.dir = "logs/"
        s.app.name = "test-app"
        mock_settings.return_value = s

        with patch("app.core.logging.logger") as mock_logger:
            setup_logging()
            assert mock_logger.add.call_count == 2

    @patch("app.core.logging.get_settings")
    def test_log_level_passed_to_handler(self, mock_settings):
        s = MagicMock()
        s.log.level = "WARNING"
        s.log.types = "console"
        s.log.dir = "logs/"
        s.app.name = "test-app"
        mock_settings.return_value = s

        with patch("app.core.logging.logger") as mock_logger:
            setup_logging()
            call_kwargs = mock_logger.add.call_args[1]
            assert call_kwargs["level"] == "WARNING"

    @patch("app.core.logging.get_settings")
    def test_none_types_registers_no_handlers(self, mock_settings):
        s = MagicMock()
        s.log.level = "INFO"
        s.log.types = ""
        s.log.dir = "logs/"
        s.app.name = "test-app"
        mock_settings.return_value = s

        with patch("app.core.logging.logger") as mock_logger:
            setup_logging()
            mock_logger.remove.assert_called_once()
            mock_logger.add.assert_not_called()
