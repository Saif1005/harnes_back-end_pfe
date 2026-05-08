"""Persist and restore SQLite runtime database to/from S3."""
from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.core.config import get_settings

LOGGER = logging.getLogger(__name__)


def _sqlite_path_from_url(database_url: str) -> str:
    if not str(database_url).startswith("sqlite:///"):
        return ""
    return str(database_url).replace("sqlite:///", "", 1)


class SQLiteS3SyncManager:
    """Manages startup restore + periodic S3 snapshots for SQLite."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.bucket = str(self.settings.s3_memory_bucket or "").strip()
        self.key = str(self.settings.s3_sqlite_key or "runtime/cerveau.db").strip()
        self.snapshot_prefix = str(
            self.settings.s3_sqlite_snapshot_prefix or "runtime/snapshots"
        ).strip().rstrip("/")
        self.interval_seconds = max(30, int(self.settings.s3_sqlite_sync_interval_seconds or 180))
        self.db_path = _sqlite_path_from_url(self.settings.database_url)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._s3 = boto3.client("s3") if self.bucket and self.db_path else None

    def enabled(self) -> bool:
        return bool(self._s3 and self.bucket and self.db_path)

    def restore_if_available(self) -> None:
        """Restore latest runtime DB from S3 before app init."""
        if not self.enabled():
            return
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._s3.head_object(Bucket=self.bucket, Key=self.key)
        except ClientError:
            LOGGER.info("sqlite_s3_sync: no remote DB found at s3://%s/%s", self.bucket, self.key)
            return
        except (BotoCoreError, Exception):  # noqa: BLE001
            LOGGER.exception("sqlite_s3_sync: head_object failed")
            return

        try:
            self._s3.download_file(self.bucket, self.key, str(db_file))
            LOGGER.info("sqlite_s3_sync: restored DB from s3://%s/%s", self.bucket, self.key)
        except (BotoCoreError, ClientError, Exception):  # noqa: BLE001
            LOGGER.exception("sqlite_s3_sync: restore failed")

    def _create_sqlite_snapshot_file(self) -> str:
        src = sqlite3.connect(self.db_path, timeout=30)
        fd, tmp_name = tempfile.mkstemp(prefix="cerveau-db-", suffix=".sqlite3")
        os.close(fd)
        dst = sqlite3.connect(tmp_name, timeout=30)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return tmp_name

    def upload_snapshot(self, reason: str = "periodic") -> None:
        """Upload stable runtime key + timestamped snapshot."""
        if not self.enabled():
            return
        if not Path(self.db_path).exists():
            return
        tmp_name = ""
        try:
            tmp_name = self._create_sqlite_snapshot_file()
            self._s3.upload_file(tmp_name, self.bucket, self.key)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            snapshot_key = f"{self.snapshot_prefix}/cerveau-{ts}-{reason}.db"
            self._s3.upload_file(tmp_name, self.bucket, snapshot_key)
            LOGGER.info(
                "sqlite_s3_sync: uploaded DB to s3://%s/%s (%s)", self.bucket, self.key, reason
            )
        except (BotoCoreError, ClientError, sqlite3.Error, Exception):  # noqa: BLE001
            LOGGER.exception("sqlite_s3_sync: upload failed (%s)", reason)
        finally:
            if tmp_name and Path(tmp_name).exists():
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.upload_snapshot(reason="periodic")

    def start(self) -> None:
        if not self.enabled() or self._thread is not None:
            return
        self.upload_snapshot(reason="startup")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        LOGGER.info("sqlite_s3_sync: periodic sync started each %ss", self.interval_seconds)

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=10)
        self.upload_snapshot(reason="shutdown")
        self._thread = None
        self._stop.clear()

