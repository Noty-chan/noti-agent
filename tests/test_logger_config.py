import logging

from noty.utils.logger import configure_logging


def test_configure_logging_accepts_string_level(tmp_path):
    log_file = tmp_path / "noty.log"

    configure_logging(level="DEBUG", log_file=str(log_file))
    logging.getLogger("noty.test").debug("debug-message")

    root_level = logging.getLogger().level
    assert root_level == logging.DEBUG
    assert "debug-message" in log_file.read_text(encoding="utf-8")


def test_configure_logging_falls_back_to_info_for_invalid_level():
    configure_logging(level="NOT_A_LEVEL")

    assert logging.getLogger().level == logging.INFO
