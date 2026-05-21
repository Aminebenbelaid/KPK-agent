import sqlite3
import json
from contextlib import contextmanager
from src.config import get_settings


def _dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    result = {}
    for field, value in zip(fields, row):
        if field in ("job_data", "status_history", "tags", "match_details", "sources_used", "event_data"):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
        result[field] = value
    return result


@contextmanager
def get_db():
    settings = get_settings()
    conn = sqlite3.connect(settings.TRACKER_DB_PATH)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
