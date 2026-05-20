"""Application logging configuration."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

from firefly_api.core.config import AppConfig


_daily_file_lock = Lock()


class DailyLogFileHandler(logging.Handler):
    """Write records to ``log_YYYYMMDD.txt`` and switch files at midnight."""

    def __init__(self, directory: str | Path) -> None:
        super().__init__()
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._current_date = ""
        self._stream = None
        self._open_for(datetime.now().strftime("%Y%m%d"))

    @property
    def baseFilename(self) -> str:  # noqa: N802 (logging handler convention)
        return str(self._path_for(datetime.now()))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            now = datetime.now()
            date_key = now.strftime("%Y%m%d")
            if self._stream is None or date_key != self._current_date:
                self._open_for(date_key)
            msg = self.format(record)
            assert self._stream is not None
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        finally:
            super().close()

    def _path_for(self, when: datetime) -> Path:
        return self.directory / f"log_{when:%Y%m%d}.txt"

    def _open_for(self, date_key: str) -> None:
        if self._stream is not None:
            self._stream.close()
        self._current_date = date_key
        self._stream = (self.directory / f"log_{date_key}.txt").open(
            "a", encoding="utf-8"
        )


def configure_logging(config: AppConfig, *, force: bool = False) -> None:
    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    handler_level = min(level, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    root = logging.getLogger()
    root.setLevel(handler_level)

    access_loggers = [
        logging.getLogger("firefly_api.access"),
        logging.getLogger("uvicorn.access"),
    ]
    for access_logger in access_loggers:
        access_logger.disabled = False
        access_logger.setLevel(logging.INFO)
        access_logger.propagate = False

    if force:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
    else:
        for handler in root.handlers[:]:
            if isinstance(handler, DailyLogFileHandler):
                root.removeHandler(handler)
                handler.close()
        for access_logger in access_loggers:
            _remove_daily_handlers(access_logger)

    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    file_handler = DailyLogFileHandler(config.logging.folder)
    file_handler.setLevel(handler_level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger(__name__).info(
        "Logging initialized; daily log folder=%s", config.logging.folder
    )


def append_daily_log_line(folder: str | Path, logger_name: str, level: str, message: str) -> None:
    now = datetime.now()
    directory = Path(folder)
    line = f"{now:%Y-%m-%d %H:%M:%S,%f}"[:23]
    line = f"{line} {level} [{logger_name}] {message}\n"
    with _daily_file_lock:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / f"log_{now:%Y%m%d}.txt").open(
            "a", encoding="utf-8"
        ) as fp:
            fp.write(line)


def _remove_daily_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        if isinstance(handler, DailyLogFileHandler):
            logger.removeHandler(handler)
            handler.close()


__all__ = ["DailyLogFileHandler", "append_daily_log_line", "configure_logging"]