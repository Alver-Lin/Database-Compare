from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pymysql
import psycopg2
from psycopg2 import sql as pg_sql


SYSTEM_MYSQL_DBS = {"information_schema", "mysql", "performance_schema", "sys"}
SYSTEM_OCEANBASE_DBS = SYSTEM_MYSQL_DBS | {"oceanbase", "lbacsys", "oraauditor", "orauser"}
SYSTEM_PG_DBS = {"template0", "template1"}
DAMENG_SYSTEM_SCHEMAS = {
    "SYS",
    "SYSSSO",
    "SYSAUDITOR",
    "SYSJOB",
    "SYSMAN",
    "PUBLIC",
}
# Hidden only when listing schemas; keep SYSDBA/CTISYS visible like GUI tools.
DAMENG_SCHEMA_LIST_SKIP = DAMENG_SYSTEM_SCHEMAS



class ConnectionError_(Exception):
    pass


def _normalize_endpoint_config(config: dict, default_port: int = 3306) -> dict:
    """Accept plain host or JDBC/URI pasted into host, and normalize fields."""
    result = dict(config or {})
    raw = str(result.get("host") or "").strip()
    if not raw:
        return result

    text = raw
    # jdbc:oceanbase://host:port/db?...  /  jdbc:mysql://...
    if text.lower().startswith("jdbc:"):
        text = text.split(":", 1)[1].strip()
    # oceanbase://host  /  mysql://host
    if "://" in text:
        text = text.split("://", 1)[1]

    # drop query/fragment
    text = text.split("?", 1)[0].split("#", 1)[0].strip()
    if not text:
        return result

    path = ""
    if "/" in text:
        text, path = text.split("/", 1)
        path = path.strip("/")

    host = text
    port = None
    # IPv6 in brackets: [::1]:2881
    if text.startswith("["):
        end = text.find("]")
        if end != -1:
            host = text[1:end]
            rest = text[end + 1 :]
            if rest.startswith(":") and rest[1:].isdigit():
                port = int(rest[1:])
    elif text.count(":") == 1:
        maybe_host, maybe_port = text.rsplit(":", 1)
        if maybe_port.isdigit():
            host = maybe_host
            port = int(maybe_port)

    if host:
        result["host"] = host
    if port is not None:
        result["port"] = port
    elif not result.get("port"):
        result["port"] = default_port
    if path and not (result.get("database") or "").strip():
        # path may be "db" or "tenant/db" — keep first segment as database name
        result["database"] = path.split("/", 1)[0]
    return result


def create_connector(config: dict) -> "BaseConnector":
    db_type = (config.get("db_type") or "").lower()
    if db_type in ("mysql", "mariadb"):
        return MySQLConnector(config)
    if db_type in ("postgresql", "postgres"):
        return PostgreSQLConnector(config)
    if db_type in ("sqlite", "sqlite3"):
        return SQLiteConnector(config)
    if db_type in ("oceanbase", "ob", "ocranbase"):
        return create_oceanbase_connector(config)
    if db_type in ("oracle", "orcl"):
        return OracleConnector(config)
    if db_type in ("dameng", "dm", "dm8", "达梦"):
        return DamengConnector(config)
    raise ConnectionError_(f"暂不支持的数据源类型: {db_type}")


def _is_oceanbase_oracle_tenant_error(exc: BaseException) -> bool:
    text = str(exc)
    return "1235" in text or "Oracle tenant for current client driver" in text


def _oceanbase_oracle_service_name(config: dict) -> str:
    service = (config.get("database") or "").strip()
    if service:
        return service
    user = (config.get("user") or "").strip()
    if "@" in user:
        tenant = user.split("@", 1)[1].split("#", 1)[0].strip()
        if tenant:
            return tenant
    raise ConnectionError_(
        "当前为 OceanBase Oracle 租户，请填写服务名/租户名（默认数据库栏），"
        "或在用户名中使用 user@租户名 格式。"
    )


def create_oceanbase_connector(config: dict) -> "BaseConnector":
    cfg = _normalize_endpoint_config(dict(config), default_port=2881)
    if not cfg.get("port"):
        cfg["port"] = 2881
    mode = (cfg.get("ob_mode") or "auto").strip().lower()

    # Official OceanBase JDBC works for Oracle tenants on MySQL-protocol OBProxy ports.
    if mode not in {"mysql", "mysql_mode", "obmysql"} and _oceanbase_jdbc_available():
        return OceanBaseJdbcConnector(cfg)

    if mode in {"oracle", "orcl", "oracle_mode", "oboracle"}:
        if _oceanbase_jdbc_available():
            return OceanBaseJdbcConnector(cfg)
        return OceanBaseOracleConnector(cfg)
    if mode in {"mysql", "mysql_mode", "obmysql"}:
        return OceanBaseMySQLConnector(cfg)

    mysql = OceanBaseMySQLConnector(cfg)
    try:
        conn = mysql._connect()
        conn.close()
        cfg["ob_mode"] = "mysql"
        mysql.config["ob_mode"] = "mysql"
        return mysql
    except ConnectionError_ as exc:
        if not _is_oceanbase_oracle_tenant_error(exc):
            raise
        if _oceanbase_jdbc_available():
            jdbc = OceanBaseJdbcConnector(cfg)
            jdbc.config["ob_mode"] = "oracle"
            return jdbc
        oracle = OceanBaseOracleConnector(cfg)
        oracle.config["ob_mode"] = "oracle"
        return oracle


def _jdbc_drivers_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "drivers"


def _java_executable() -> str | None:
    """Prefer a JRE shipped with the app, then JAVA_HOME, then PATH."""
    names = ("java.exe", "java") if os.name == "nt" else ("java",)
    roots = [
        Path(__file__).resolve().parents[2] / "jre",
        Path(__file__).resolve().parents[2] / "runtime" / "jre",
    ]
    java_home = os.environ.get("JAVA_HOME") or ""
    if java_home:
        roots.append(Path(java_home))
    for root in roots:
        for name in names:
            candidate = root / "bin" / name
            if candidate.is_file():
                return str(candidate)
    return shutil.which("java")


def _oceanbase_drivers_dir() -> Path:
    return _jdbc_drivers_dir()


def _jdbc_common_jars() -> list[Path]:
    drivers = _jdbc_drivers_dir()
    return [
        drivers / "jackson-core-2.17.2.jar",
        drivers / "jackson-annotations-2.17.2.jar",
        drivers / "jackson-databind-2.17.2.jar",
    ]


def _jdbc_classpath(*extra_jars: Path) -> str:
    drivers = _jdbc_drivers_dir()
    jars = [*extra_jars, *_jdbc_common_jars()]
    missing = [str(path) for path in jars if not path.is_file()]
    if missing:
        raise ConnectionError_(f"缺少 JDBC 依赖: {', '.join(missing)}")
    if not (drivers / "JdbcBridge.class").is_file() and not (drivers / "ObJdbcBridge.class").is_file():
        raise ConnectionError_("缺少 JDBC 桥接类，请编译 backend/drivers/JdbcBridge.java")
    sep = ";" if os.name == "nt" else ":"
    return sep.join(str(path) for path in jars) + sep + str(drivers)


def _oceanbase_jdbc_available() -> bool:
    jar = _jdbc_drivers_dir() / "oceanbase-client.jar"
    return jar.is_file() and bool(_java_executable())


def _dameng_jdbc_available() -> bool:
    jar = _jdbc_drivers_dir() / "DmJdbcDriver18.jar"
    return jar.is_file() and bool(_java_executable())


def _oceanbase_jdbc_classpath() -> str:
    return _jdbc_classpath(_jdbc_drivers_dir() / "oceanbase-client.jar")


def _dameng_jdbc_classpath() -> str:
    return _jdbc_classpath(_jdbc_drivers_dir() / "DmJdbcDriver18.jar")


def _jdbc_bridge_main_class() -> str:
    drivers = _jdbc_drivers_dir()
    if (drivers / "JdbcBridge.class").is_file():
        return "JdbcBridge"
    return "ObJdbcBridge"


class BaseConnector:
    def test_connection(self) -> dict:
        raise NotImplementedError

    def list_databases(self) -> list[str]:
        raise NotImplementedError

    def list_schemas(self, database: str) -> list[str]:
        return []

    def list_tables(self, database: str, schema_name: str | None = None) -> list[dict]:
        raise NotImplementedError

    def list_columns(self, database: str, table: str, schema_name: str | None = None) -> list[dict]:
        raise NotImplementedError

    def count_rows(self, database: str, table: str, schema_name: str | None = None) -> int:
        raise NotImplementedError

    def fetch_rows(
        self,
        database: str,
        table: str,
        schema_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        raise NotImplementedError

    def fetch_signatures(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> list[str]:
        raise NotImplementedError

    def iter_signature_hashes(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
        value_map: dict | None = None,
        extract_map: dict | None = None,
    ) -> Iterator[bytes]:
        raise NotImplementedError

    def iter_column_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> Iterator[dict]:
        raise NotImplementedError

    def search_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        keyword: str,
        schema_name: str | None = None,
        offset: int = 0,
        limit: int = 100,
        allowed_indices: set[int] | None = None,
        search_columns: list[str] | None = None,
        keywords: list[str] | None = None,
        negate: bool = False,
        conditions: list[dict] | None = None,
        condition_logic: str = "and",
    ) -> dict:
        normalized = []
        for raw in conditions or []:
            if hasattr(raw, "model_dump"):
                raw = raw.model_dump()
            terms = [str(t).strip() for t in (raw.get("keywords") or []) if str(t).strip()]
            cols = [c for c in (raw.get("search_columns") or []) if c]
            if not terms:
                continue
            mode = str(raw.get("mode") or "").strip().lower()
            if mode not in {"include", "exclude", "equals", "not_equals"}:
                mode = "exclude" if raw.get("negate") else "include"
            logic_value = str(raw.get("logic") or "").strip().lower()
            normalized.append(
                {
                    "keywords": terms,
                    "search_columns": cols,
                    "mode": mode,
                    "negate": mode in {"exclude", "not_equals"},
                    "logic": "or" if logic_value == "or" else "and",
                }
            )
        if not normalized:
            terms = [str(t).strip() for t in (keywords or []) if str(t).strip()]
            single = (keyword or "").strip()
            if single and single not in terms:
                terms.append(single)
            if terms:
                mode = "exclude" if negate else "include"
                normalized.append(
                    {
                        "keywords": terms,
                        "search_columns": [c for c in (search_columns or []) if c],
                        "mode": mode,
                        "negate": bool(negate),
                        "logic": "and",
                    }
                )
        if not normalized:
            return {"rows": [], "indices": [], "total": 0}

        fetch_cols = list(dict.fromkeys([*(columns or [])]))
        for cond in normalized:
            fetch_cols.extend(cond["search_columns"])
        if not fetch_cols:
            # fall back to condition columns only
            for cond in normalized:
                fetch_cols.extend(cond["search_columns"])
            fetch_cols = list(dict.fromkeys(fetch_cols))
        if not fetch_cols:
            return {"rows": [], "indices": [], "total": 0}

        fallback_logic = "or" if str(condition_logic or "and").strip().lower() == "or" else "and"
        matched = 0
        page_rows: list[dict] = []
        page_indices: list[int] = []
        end = offset + limit
        for idx, row in enumerate(self.iter_column_rows(database, table, fetch_cols, schema_name)):
            if allowed_indices is not None and idx not in allowed_indices:
                continue
            hits = []
            logics = []
            for cond in normalized:
                match_cols = cond["search_columns"] or fetch_cols
                hits.append(
                    bool(_condition_matches_row(row, match_cols, cond["keywords"], cond["mode"]))
                )
                logics.append(cond.get("logic") or fallback_logic)
            # 从左到右组合：首条为起点，后续用各自 logic（且/或）接入
            ok = bool(hits[0])
            for i in range(1, len(hits)):
                op = logics[i] if i < len(logics) else fallback_logic
                ok = (ok or hits[i]) if op == "or" else (ok and hits[i])
            if not ok:
                continue
            if offset <= matched < end:
                page_rows.append(_stringify_row(row))
                page_indices.append(idx)
            matched += 1
        return {"rows": page_rows, "indices": page_indices, "total": matched}

    def fetch_rows_by_indices(
        self,
        database: str,
        table: str,
        indices: list[int],
        schema_name: str | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    def distinct_values(
        self,
        database: str,
        table: str,
        column: str,
        schema_name: str | None = None,
        limit: int = 200,
    ) -> list[Any]:
        raise NotImplementedError

    def fetch_rows_by_column_values(
        self,
        database: str,
        table: str,
        column: str,
        values: list[Any],
        schema_name: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        raise NotImplementedError


class MySQLConnector(BaseConnector):
    def __init__(self, config: dict):
        config = _normalize_endpoint_config(config, default_port=3306)
        self.config = config
        self.host = config["host"]
        self.port = int(config.get("port") or 3306)
        self.user = config["user"]
        self.password = config.get("password") or ""
        self.database = config.get("database") or None

    def _connect(self, database: str | None = None, timeout: int = 30):
        try:
            return pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=database or self.database or None,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=8,
                read_timeout=timeout,
            )
        except Exception as exc:
            raise ConnectionError_(f"MySQL 连接失败: {exc}") from exc

    def test_connection(self) -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS version")
                row = cur.fetchone()
            return {
                "ok": True,
                "message": "连接成功",
                "version": row["version"] if row else "",
                "db_type": "mysql",
            }
        finally:
            conn.close()

    def list_databases(self) -> list[str]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW DATABASES")
                names = [list(row.values())[0] for row in cur.fetchall()]
            user_dbs = [n for n in names if n not in SYSTEM_MYSQL_DBS]
            sys_dbs = [n for n in names if n in SYSTEM_MYSQL_DBS]
            return user_dbs + sys_dbs
        finally:
            conn.close()

    def list_tables(self, database: str, schema_name: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT TABLE_NAME AS name,
                           TABLE_TYPE AS table_type,
                           ENGINE AS engine,
                           TABLE_ROWS AS row_estimate,
                           TABLE_COMMENT AS comment
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = %s
                    ORDER BY TABLE_NAME
                    """,
                    (database,),
                )
                rows = cur.fetchall()
            return [
                {
                    "name": r["name"],
                    "table_type": r["table_type"],
                    "engine": r["engine"],
                    "row_estimate": int(r["row_estimate"] or 0),
                    "comment": r["comment"] or "",
                }
                for r in rows
            ]
        finally:
            conn.close()

    def list_columns(self, database: str, table: str, schema_name: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COLUMN_NAME AS name,
                           COLUMN_TYPE AS column_type,
                           DATA_TYPE AS data_type,
                           IS_NULLABLE AS is_nullable,
                           COLUMN_KEY AS column_key,
                           COLUMN_DEFAULT AS column_default,
                           EXTRA AS extra,
                           COLUMN_COMMENT AS comment,
                           ORDINAL_POSITION AS position
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (database, table),
                )
                rows = cur.fetchall()
            return [
                {
                    "name": r["name"],
                    "column_type": r["column_type"],
                    "data_type": r["data_type"],
                    "nullable": r["is_nullable"] == "YES",
                    "key": r["column_key"] or "",
                    "default": None if r["column_default"] is None else str(r["column_default"]),
                    "extra": r["extra"] or "",
                    "comment": r["comment"] or "",
                    "position": r["position"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def count_rows(self, database: str, table: str, schema_name: str | None = None) -> int:
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM `{_ident(table)}`")
                row = cur.fetchone()
            return int(row["cnt"] if row else 0)
        finally:
            conn.close()

    def fetch_rows(
        self,
        database: str,
        table: str,
        schema_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS cnt FROM `{_ident(table)}`")
                total = int(cur.fetchone()["cnt"])
                cur.execute(
                    f"SELECT * FROM `{_ident(table)}` LIMIT %s OFFSET %s",
                    (int(limit), int(offset)),
                )
                rows = cur.fetchall()
            columns = list(rows[0].keys()) if rows else [c["name"] for c in self.list_columns(database, table)]
            return {
                "columns": columns,
                "rows": [_stringify_row(r) for r in rows],
                "total": total,
            }
        finally:
            conn.close()

    def fetch_signatures(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> list[str]:
        return list(self.iter_signature_hashes(database, table, columns, schema_name))

    def iter_signature_hashes(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
        value_map: dict | None = None,
        extract_map: dict | None = None,
    ) -> Iterator[bytes]:
        if not columns:
            return
            yield
        select_sql = ", ".join(f"`{_ident(c)}`" for c in columns)
        conn = self._connect(database, timeout=600)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {select_sql} FROM `{_ident(table)}`")
                while True:
                    rows = cur.fetchmany(8000)
                    if not rows:
                        break
                    for row in rows:
                        yield _sig_hash(row, columns, value_map, extract_map)
        finally:
            conn.close()

    def iter_column_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> Iterator[dict]:
        if not columns:
            return
            yield
        select_sql = ", ".join(f"`{_ident(c)}`" for c in columns)
        conn = self._connect(database, timeout=600)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT {select_sql} FROM `{_ident(table)}`")
                while True:
                    rows = cur.fetchmany(8000)
                    if not rows:
                        break
                    yield from rows
        finally:
            conn.close()

    def fetch_rows_by_indices(
        self,
        database: str,
        table: str,
        indices: list[int],
        schema_name: str | None = None,
    ) -> list[dict]:
        if not indices:
            return []
        wanted = set(indices)
        min_i = min(wanted)
        max_i = max(wanted)
        conn = self._connect(database, timeout=600)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM `{_ident(table)}` LIMIT %s OFFSET %s",
                    (max_i - min_i + 1, min_i),
                )
                found = {}
                idx = min_i
                while idx <= max_i:
                    rows = cur.fetchmany(8000)
                    if not rows:
                        break
                    for row in rows:
                        if idx in wanted:
                            found[idx] = _stringify_row(row)
                            if len(found) == len(wanted):
                                return [found[i] for i in indices]
                        idx += 1
                        if idx > max_i:
                            break
            return [found[i] for i in indices if i in found]
        finally:
            conn.close()

    def distinct_values(
        self,
        database: str,
        table: str,
        column: str,
        schema_name: str | None = None,
        limit: int = 200,
    ) -> list[Any]:
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT DISTINCT `{_ident(column)}` AS val FROM `{_ident(table)}` LIMIT %s",
                    (int(limit),),
                )
                rows = cur.fetchall()
            return [_stringify_value(r["val"]) for r in rows]
        finally:
            conn.close()

    def fetch_rows_by_column_values(
        self,
        database: str,
        table: str,
        column: str,
        values: list[Any],
        schema_name: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        uniq: list[Any] = []
        seen: set[str] = set()
        for v in values:
            if v is None:
                continue
            key = str(v)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(v)
        if not uniq:
            return []
        row_limit = max(int(limit), len(uniq))
        placeholders = ", ".join(["%s"] * len(uniq))
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM `{_ident(table)}` WHERE CAST(`{_ident(column)}` AS CHAR) IN ({placeholders}) LIMIT %s",
                    (*[str(v) for v in uniq], int(row_limit)),
                )
                rows = cur.fetchall()
            return [_stringify_row(r) for r in rows]
        finally:
            conn.close()


class PostgreSQLConnector(BaseConnector):
    def __init__(self, config: dict):
        self.config = config
        self.host = config["host"]
        self.port = int(config.get("port") or 5432)
        self.user = config["user"]
        self.password = config.get("password") or ""
        self.database = config.get("database") or "postgres"

    def _connect(self, database: str | None = None):
        try:
            return psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=database or self.database or "postgres",
                connect_timeout=8,
            )
        except Exception as exc:
            raise ConnectionError_(f"PostgreSQL 连接失败: {exc}") from exc

    def test_connection(self) -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
            return {
                "ok": True,
                "message": "连接成功",
                "version": version,
                "db_type": "postgresql",
            }
        finally:
            conn.close()

    def list_databases(self) -> list[str]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT datname
                    FROM pg_database
                    WHERE datallowconn = true
                    ORDER BY datname
                    """
                )
                names = [r[0] for r in cur.fetchall()]
            return [n for n in names if n not in SYSTEM_PG_DBS]
        finally:
            conn.close()

    def list_schemas(self, database: str) -> list[str]:
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                    ORDER BY schema_name
                    """
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def list_tables(self, database: str, schema_name: str | None = None) -> list[dict]:
        schema_name = schema_name or "public"
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT c.relname AS name,
                           CASE c.relkind
                             WHEN 'r' THEN 'BASE TABLE'
                             WHEN 'v' THEN 'VIEW'
                             WHEN 'm' THEN 'MATERIALIZED VIEW'
                             ELSE c.relkind::text
                           END AS table_type,
                           COALESCE(s.n_live_tup, 0) AS row_estimate,
                           COALESCE(d.description, '') AS comment
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_stat_user_tables s
                      ON s.relid = c.oid
                    LEFT JOIN pg_description d
                      ON d.objoid = c.oid AND d.objsubid = 0
                    WHERE n.nspname = %s
                      AND c.relkind IN ('r', 'v', 'm', 'p')
                    ORDER BY c.relname
                    """,
                    (schema_name,),
                )
                rows = cur.fetchall()
            return [
                {
                    "name": r[0],
                    "table_type": r[1],
                    "engine": "postgresql",
                    "row_estimate": int(r[2] or 0),
                    "comment": r[3] or "",
                    "schema": schema_name,
                }
                for r in rows
            ]
        finally:
            conn.close()

    def list_columns(self, database: str, table: str, schema_name: str | None = None) -> list[dict]:
        schema_name = schema_name or "public"
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT a.attname AS column_name,
                           format_type(a.atttypid, a.atttypmod) AS column_type,
                           t.typname AS udt_name,
                           CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END AS is_nullable,
                           pg_get_expr(ad.adbin, ad.adrelid) AS column_default,
                           a.attnum AS ordinal_position,
                           COALESCE(d.description, '') AS comment
                    FROM pg_attribute a
                    JOIN pg_class c ON c.oid = a.attrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_type t ON t.oid = a.atttypid
                    LEFT JOIN pg_attrdef ad
                      ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
                    LEFT JOIN pg_description d
                      ON d.objoid = c.oid AND d.objsubid = a.attnum
                    WHERE n.nspname = %s
                      AND c.relname = %s
                      AND a.attnum > 0
                      AND NOT a.attisdropped
                    ORDER BY a.attnum
                    """,
                    (schema_name, table),
                )
                rows = cur.fetchall()
                cur.execute(
                    """
                    SELECT kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                    WHERE tc.table_schema = %s
                      AND tc.table_name = %s
                      AND tc.constraint_type = 'PRIMARY KEY'
                    """,
                    (schema_name, table),
                )
                pk_cols = {r[0] for r in cur.fetchall()}
            result = []
            for r in rows:
                result.append(
                    {
                        "name": r[0],
                        "column_type": r[1],
                        "data_type": r[2],
                        "nullable": r[3] == "YES",
                        "key": "PRI" if r[0] in pk_cols else "",
                        "default": None if r[4] is None else str(r[4]),
                        "extra": "",
                        "comment": r[6] or "",
                        "position": r[5],
                    }
                )
            return result
        finally:
            conn.close()

    def count_rows(self, database: str, table: str, schema_name: str | None = None) -> int:
        schema_name = schema_name or "public"
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                query = pg_sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table),
                )
                cur.execute(query)
                return int(cur.fetchone()[0])
        finally:
            conn.close()

    def fetch_rows(
        self,
        database: str,
        table: str,
        schema_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        schema_name = schema_name or "public"
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                count_q = pg_sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table),
                )
                cur.execute(count_q)
                total = int(cur.fetchone()[0])
                data_q = pg_sql.SQL("SELECT * FROM {}.{} LIMIT %s OFFSET %s").format(
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table),
                )
                cur.execute(data_q, (int(limit), int(offset)))
                colnames = [desc[0] for desc in cur.description] if cur.description else []
                raw_rows = cur.fetchall()
            rows = [_stringify_row(dict(zip(colnames, r))) for r in raw_rows]
            return {"columns": colnames, "rows": rows, "total": total}
        finally:
            conn.close()

    def fetch_signatures(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> list[str]:
        return list(self.iter_signature_hashes(database, table, columns, schema_name))

    def iter_signature_hashes(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
        value_map: dict | None = None,
        extract_map: dict | None = None,
    ) -> Iterator[bytes]:
        if not columns:
            return
            yield
        schema_name = schema_name or "public"
        conn = self._connect(database)
        try:
            conn.autocommit = False
            with conn.cursor() as setup:
                setup.execute("SET LOCAL statement_timeout = 600000")
            col_idents = [pg_sql.Identifier(c) for c in columns]
            query = pg_sql.SQL("SELECT {} FROM {}.{}").format(
                pg_sql.SQL(", ").join(col_idents),
                pg_sql.Identifier(schema_name),
                pg_sql.Identifier(table),
            )
            with conn.cursor(name="sig_cursor") as cur:
                cur.itersize = 8000
                cur.execute(query)
                while True:
                    rows = cur.fetchmany(8000)
                    if not rows:
                        break
                    for row in rows:
                        yield _sig_hash(dict(zip(columns, row)), columns, value_map, extract_map)
            conn.commit()
        finally:
            conn.close()

    def iter_column_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> Iterator[dict]:
        if not columns:
            return
            yield
        schema_name = schema_name or "public"
        conn = self._connect(database)
        cur = None
        try:
            conn.autocommit = False
            with conn.cursor() as setup:
                setup.execute("SET LOCAL statement_timeout = 600000")
            col_idents = [pg_sql.Identifier(c) for c in columns]
            query = pg_sql.SQL("SELECT {} FROM {}.{}").format(
                pg_sql.SQL(", ").join(col_idents),
                pg_sql.Identifier(schema_name),
                pg_sql.Identifier(table),
            )
            cur = conn.cursor(name=f"search_{id(conn)}")
            cur.itersize = 8000
            cur.execute(query)
            while True:
                rows = cur.fetchmany(8000)
                if not rows:
                    break
                for row in rows:
                    yield dict(zip(columns, row))
            try:
                cur.close()
            except Exception:
                pass
            cur = None
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            conn.close()

    def fetch_rows_by_indices(
        self,
        database: str,
        table: str,
        indices: list[int],
        schema_name: str | None = None,
    ) -> list[dict]:
        if not indices:
            return []
        wanted = set(indices)
        min_i = min(wanted)
        max_i = max(wanted)
        schema_name = schema_name or "public"
        conn = self._connect(database)
        cur = None
        try:
            conn.autocommit = False
            with conn.cursor() as setup:
                setup.execute("SET LOCAL statement_timeout = 600000")
            query = pg_sql.SQL("SELECT * FROM {}.{} OFFSET %s LIMIT %s").format(
                pg_sql.Identifier(schema_name),
                pg_sql.Identifier(table),
            )
            found = {}
            idx = min_i
            cur = conn.cursor(name=f"idx_{id(conn)}")
            cur.itersize = 8000
            cur.execute(query, (min_i, max_i - min_i + 1))
            colnames = []
            done = False
            while not done and idx <= max_i:
                rows = cur.fetchmany(8000)
                if not rows:
                    break
                if not colnames and cur.description:
                    colnames = [desc[0] for desc in cur.description]
                for row in rows:
                    if idx in wanted:
                        found[idx] = _stringify_row(dict(zip(colnames, row)))
                        if len(found) == len(wanted):
                            done = True
                            break
                    idx += 1
                    if idx > max_i:
                        done = True
                        break
            try:
                cur.close()
            except Exception:
                pass
            cur = None
            conn.commit()
            return [found[i] for i in indices if i in found]
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            conn.close()

    def distinct_values(
        self,
        database: str,
        table: str,
        column: str,
        schema_name: str | None = None,
        limit: int = 200,
    ) -> list[Any]:
        schema_name = schema_name or "public"
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                query = pg_sql.SQL("SELECT DISTINCT {} FROM {}.{} LIMIT %s").format(
                    pg_sql.Identifier(column),
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table),
                )
                cur.execute(query, (int(limit),))
                return [_stringify_value(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()

    def fetch_rows_by_column_values(
        self,
        database: str,
        table: str,
        column: str,
        values: list[Any],
        schema_name: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        schema_name = schema_name or "public"
        uniq: list[Any] = []
        seen: set[str] = set()
        for v in values:
            if v is None:
                continue
            key = str(v)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(v)
        if not uniq:
            return []
        row_limit = max(int(limit), len(uniq))
        conn = self._connect(database)
        try:
            with conn.cursor() as cur:
                query = pg_sql.SQL("SELECT * FROM {}.{} WHERE {}::text = ANY(%s) LIMIT %s").format(
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table),
                    pg_sql.Identifier(column),
                )
                cur.execute(query, ([str(v) for v in uniq], int(row_limit)))
                colnames = [desc[0] for desc in cur.description] if cur.description else []
                return [_stringify_row(dict(zip(colnames, r))) for r in cur.fetchall()]
        finally:
            conn.close()


class SQLiteConnector(BaseConnector):
    def __init__(self, config: dict):
        self.config = config
        self.path = (config.get("database") or config.get("host") or "").strip()

    def _connect(self):
        if not self.path:
            raise ConnectionError_("请填写 SQLite 文件路径")
        try:
            conn = sqlite3.connect(self.path, timeout=8)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as exc:
            raise ConnectionError_(f"SQLite 连接失败: {exc}") from exc

    def test_connection(self) -> dict:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT sqlite_version() AS version")
            version = cur.fetchone()[0]
            return {
                "ok": True,
                "message": "连接成功",
                "version": f"SQLite {version}",
                "db_type": "sqlite",
            }
        finally:
            conn.close()

    def list_databases(self) -> list[str]:
        name = Path(self.path).stem or "main"
        return [name]

    def list_tables(self, database: str, schema_name: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT name, type
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
            rows = cur.fetchall()
            result = []
            for r in rows:
                cur.execute(f'SELECT COUNT(*) FROM "{_ident(r["name"])}"')
                count = int(cur.fetchone()[0])
                result.append(
                    {
                        "name": r["name"],
                        "table_type": "VIEW" if r["type"] == "view" else "BASE TABLE",
                        "engine": "sqlite",
                        "row_estimate": count,
                        "comment": "",
                    }
                )
            return result
        finally:
            conn.close()

    def list_columns(self, database: str, table: str, schema_name: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f'PRAGMA table_info("{_ident(table)}")')
            rows = cur.fetchall()
            return [
                {
                    "name": r["name"],
                    "column_type": r["type"] or "TEXT",
                    "data_type": (r["type"] or "TEXT").split("(")[0].lower(),
                    "nullable": r["notnull"] == 0,
                    "key": "PRI" if r["pk"] else "",
                    "default": None if r["dflt_value"] is None else str(r["dflt_value"]),
                    "extra": "",
                    "comment": "",
                    "position": r["cid"] + 1,
                }
                for r in rows
            ]
        finally:
            conn.close()

    def count_rows(self, database: str, table: str, schema_name: str | None = None) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*) FROM "{_ident(table)}"')
            return int(cur.fetchone()[0])
        finally:
            conn.close()

    def fetch_rows(
        self,
        database: str,
        table: str,
        schema_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*) FROM "{_ident(table)}"')
            total = int(cur.fetchone()[0])
            cur.execute(
                f'SELECT * FROM "{_ident(table)}" LIMIT ? OFFSET ?',
                (int(limit), int(offset)),
            )
            rows = [dict(r) for r in cur.fetchall()]
            columns = list(rows[0].keys()) if rows else [c["name"] for c in self.list_columns(database, table)]
            return {
                "columns": columns,
                "rows": [_stringify_row(r) for r in rows],
                "total": total,
            }
        finally:
            conn.close()

    def fetch_signatures(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> list[str]:
        return list(self.iter_signature_hashes(database, table, columns, schema_name))

    def iter_signature_hashes(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
        value_map: dict | None = None,
        extract_map: dict | None = None,
    ) -> Iterator[bytes]:
        if not columns:
            return
            yield
        select_sql = ", ".join(f'"{_ident(c)}"' for c in columns)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT {select_sql} FROM "{_ident(table)}"')
            while True:
                rows = cur.fetchmany(8000)
                if not rows:
                    break
                for row in rows:
                    yield _sig_hash(dict(row), columns, value_map, extract_map)
        finally:
            conn.close()

    def iter_column_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> Iterator[dict]:
        if not columns:
            return
            yield
        select_sql = ", ".join(f'"{_ident(c)}"' for c in columns)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT {select_sql} FROM "{_ident(table)}"')
            while True:
                rows = cur.fetchmany(8000)
                if not rows:
                    break
                for row in rows:
                    yield dict(row)
        finally:
            conn.close()

    def fetch_rows_by_indices(
        self,
        database: str,
        table: str,
        indices: list[int],
        schema_name: str | None = None,
    ) -> list[dict]:
        if not indices:
            return []
        wanted = set(indices)
        min_i = min(wanted)
        max_i = max(wanted)
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{_ident(table)}" LIMIT ? OFFSET ?',
                (max_i - min_i + 1, min_i),
            )
            found = {}
            idx = min_i
            while idx <= max_i:
                rows = cur.fetchmany(8000)
                if not rows:
                    break
                for row in rows:
                    if idx in wanted:
                        found[idx] = _stringify_row(dict(row))
                        if len(found) == len(wanted):
                            return [found[i] for i in indices]
                    idx += 1
                    if idx > max_i:
                        break
            return [found[i] for i in indices if i in found]
        finally:
            conn.close()

    def distinct_values(
        self,
        database: str,
        table: str,
        column: str,
        schema_name: str | None = None,
        limit: int = 200,
    ) -> list[Any]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT DISTINCT "{_ident(column)}" FROM "{_ident(table)}" LIMIT ?',
                (int(limit),),
            )
            return [_stringify_value(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()

    def fetch_rows_by_column_values(
        self,
        database: str,
        table: str,
        column: str,
        values: list[Any],
        schema_name: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        uniq: list[Any] = []
        seen: set[str] = set()
        for v in values:
            if v is None:
                continue
            key = str(v)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(v)
        if not uniq:
            return []
        row_limit = max(int(limit), len(uniq))
        placeholders = ", ".join(["?"] * len(uniq))
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT * FROM "{_ident(table)}" WHERE CAST("{_ident(column)}" AS TEXT) IN ({placeholders}) LIMIT ?',
                (*[str(v) for v in uniq], int(row_limit)),
            )
            return [_stringify_row(dict(r)) for r in cur.fetchall()]
        finally:
            conn.close()


class OceanBaseMySQLConnector(MySQLConnector):
    """OceanBase MySQL 租户，协议与 MySQL 兼容。"""

    def __init__(self, config: dict):
        config = _normalize_endpoint_config(dict(config), default_port=2881)
        if not config.get("port"):
            config["port"] = 2881
        self.config = config
        self.host = config["host"]
        self.port = int(config.get("port") or 2881)
        self.user = config.get("user") or ""
        self.password = config.get("password") or ""
        self.database = config.get("database") or None

    def _connect(self, database: str | None = None, timeout: int = 30):
        if not self.host or "://" in str(self.host) or str(self.host).lower().startswith("jdbc"):
            raise ConnectionError_(
                "OceanBase 主机地址无效。请填写主机名或 IP，例如 k8s.gjj.jxgjj，"
                "不要把整段 jdbc:oceanbase://... 当作主机名。"
            )
        try:
            return super()._connect(database, timeout)
        except ConnectionError_ as exc:
            message = str(exc).replace("MySQL 连接失败", "OceanBase 连接失败", 1)
            raise ConnectionError_(message) from exc

    def test_connection(self) -> dict:
        result = super().test_connection()
        result["db_type"] = "oceanbase"
        result["ob_mode"] = "mysql"
        result["message"] = "连接成功（MySQL 租户）"
        return result

    def list_databases(self) -> list[str]:
        names = super().list_databases()
        skip = {name.lower() for name in SYSTEM_OCEANBASE_DBS}
        user_dbs = [name for name in names if name.lower() not in skip]
        system_dbs = [name for name in names if name.lower() in skip]
        return user_dbs + system_dbs


# Backward-compatible alias
OceanBaseConnector = OceanBaseMySQLConnector


def _load_oracledb():
    try:
        import oracledb
    except ImportError as exc:
        raise ConnectionError_("未安装 Oracle 驱动。请在后端环境执行: pip install oracledb") from exc
    oracledb.defaults.fetch_lobs = False
    return oracledb


def _load_dm():
    try:
        import dmPython
    except ImportError as exc:
        raise ConnectionError_(
            "未安装达梦驱动 dmPython。请安装达梦客户端后执行 pip install dmPython，并确保 dpi 动态库在系统路径中。"
        ) from exc
    return dmPython


def _quote_ident(name: str) -> str:
    cleaned = str(name).replace('"', "")
    if not cleaned:
        raise ConnectionError_("非法标识符")
    return f'"{cleaned}"'


def _row_value(row: dict, name: str):
    if name in row:
        return row[name]
    upper = name.upper()
    if upper in row:
        return row[upper]
    lower = name.lower()
    if lower in row:
        return row[lower]
    return None


def _materialize_cell(value: Any) -> Any:
    read = getattr(value, "read", None)
    if callable(read) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return read()
        except Exception:
            return str(value)
    return value


def _format_oracle_type(row: dict) -> str:
    dtype = str(_row_value(row, "DATA_TYPE") or "")
    length = _row_value(row, "DATA_LENGTH")
    precision = _row_value(row, "DATA_PRECISION")
    scale = _row_value(row, "DATA_SCALE")
    if dtype in {"VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "RAW"} and length:
        return f"{dtype}({length})"
    if dtype == "NUMBER" and precision is not None:
        if scale not in (None, 0):
            return f"NUMBER({precision},{scale})"
        return f"NUMBER({precision})"
    return dtype


class OracleLikeConnector(BaseConnector):
    """Shared catalog and paging SQL for Oracle and Dameng."""

    engine_name = "oracle"
    connect_label = "Oracle"
    paramstyle = "numeric"
    use_oracle_maintained = True
    system_schemas: set[str] = set()

    def __init__(self, config: dict):
        self.config = config
        self.host = config.get("host") or "127.0.0.1"
        self.port = int(config.get("port") or self._default_port())
        self.user = config.get("user") or ""
        self.password = config.get("password") or ""
        self._cached_user = ""

    def _default_port(self) -> int:
        return 1521

    def _preferred_schema(self) -> str:
        return ""

    def _connect(self):
        raise NotImplementedError

    def _ph(self, index: int) -> str:
        if self.paramstyle == "qmark":
            return "?"
        return f":{index}"

    def _placeholders(self, count: int, start: int = 1) -> str:
        return ", ".join(self._ph(i) for i in range(start, start + count))

    def _fetchall(self, conn, sql: str, params: tuple | list = ()) -> list[dict]:
        cur = conn.cursor()
        try:
            if hasattr(cur, "arraysize"):
                cur.arraysize = 2000
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            return self._as_dicts(cur, rows)
        finally:
            cur.close()

    def _as_dicts(self, cur, rows) -> list[dict]:
        names = [desc[0] for desc in cur.description] if cur.description else []
        result = []
        for row in rows:
            if isinstance(row, dict):
                item = {key: _materialize_cell(value) for key, value in row.items()}
            else:
                item = {name: _materialize_cell(value) for name, value in zip(names, row)}
            item.pop("___RN", None)
            item.pop("___rn", None)
            item.pop("PAGE_RN", None)
            item.pop("page_rn", None)
            result.append(item)
        return result

    def _current_user(self, conn) -> str:
        if self._cached_user:
            return self._cached_user
        rows = self._fetchall(conn, "SELECT USER AS CURRENT_USER FROM DUAL")
        name = str(_row_value(rows[0], "CURRENT_USER") or "").strip() if rows else ""
        self._cached_user = name
        return name

    def _owner(self, conn, schema_name: str | None) -> str:
        name = (schema_name or "").strip()
        if name:
            return name
        preferred = self._preferred_schema()
        if preferred:
            return preferred
        user = self._current_user(conn)
        if not user:
            raise ConnectionError_(f"无法确定{self.connect_label}当前模式，请先选择模式")
        return user

    def _qualified(self, schema_name: str, table: str) -> str:
        return f"{_quote_ident(schema_name)}.{_quote_ident(table)}"

    def _skip_schema(self, name: str, current: str) -> bool:
        if name.upper() == (current or "").upper():
            return False
        upper = name.upper()
        if upper in self.system_schemas or upper.startswith(("APEX_", "FLOWS_", "ORDS_")):
            return True
        return False

    def test_connection(self) -> dict:
        conn = self._connect()
        try:
            version = ""
            try:
                rows = self._fetchall(conn, "SELECT BANNER FROM V$VERSION WHERE ROWNUM = 1")
                version = str(_row_value(rows[0], "BANNER") or "") if rows else ""
            except Exception:
                rows = self._fetchall(conn, "SELECT USER AS CURRENT_USER FROM DUAL")
                version = str(_row_value(rows[0], "CURRENT_USER") or "") if rows else ""
            return {
                "ok": True,
                "message": "连接成功",
                "version": version,
                "db_type": self.engine_name,
            }
        finally:
            conn.close()

    def list_databases(self) -> list[str]:
        service = (self.config.get("database") or "").strip()
        if service.lower().startswith("sid:"):
            service = service.split(":", 1)[1].strip()
        return [service or self.connect_label.upper()]

    def list_schemas(self, database: str) -> list[str]:
        conn = self._connect()
        try:
            current = self._current_user(conn)
            names: list[str] = []
            if self.use_oracle_maintained:
                try:
                    rows = self._fetchall(
                        conn,
                        "SELECT USERNAME FROM ALL_USERS WHERE ORACLE_MAINTAINED = 'N' ORDER BY USERNAME",
                    )
                    names = [str(_row_value(row, "USERNAME")) for row in rows if _row_value(row, "USERNAME")]
                except Exception:
                    names = []
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            if not names:
                rows = self._fetchall(conn, "SELECT USERNAME FROM ALL_USERS ORDER BY USERNAME")
                for row in rows:
                    name = _row_value(row, "USERNAME")
                    if not name or self._skip_schema(str(name), current):
                        continue
                    names.append(str(name))
            ordered: list[str] = []
            if current:
                ordered.append(current)
            preferred = self._preferred_schema()
            if preferred:
                match = next((name for name in names if name.upper() == preferred.upper()), preferred)
                if match not in ordered:
                    ordered.append(match)
            for name in names:
                if name not in ordered:
                    ordered.append(name)
            return ordered
        finally:
            conn.close()

    def list_tables(self, database: str, schema_name: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            sql = f"""
                SELECT TABLE_NAME AS NAME, 'BASE TABLE' AS TABLE_TYPE, NUM_ROWS AS ROW_ESTIMATE
                FROM ALL_TABLES
                WHERE OWNER = {self._ph(1)}
                UNION ALL
                SELECT VIEW_NAME, 'VIEW', NULL
                FROM ALL_VIEWS
                WHERE OWNER = {self._ph(2)}
                ORDER BY 1
            """
            try:
                rows = self._fetchall(conn, sql, (owner, owner))
            except Exception:
                rows = self._fetchall(
                    conn,
                    f"""
                    SELECT TABLE_NAME AS NAME, 'BASE TABLE' AS TABLE_TYPE, NUM_ROWS AS ROW_ESTIMATE
                    FROM ALL_TABLES
                    WHERE OWNER = {self._ph(1)}
                    ORDER BY TABLE_NAME
                    """,
                    (owner,),
                )
            comments: dict[str, str] = {}
            try:
                comment_rows = self._fetchall(
                    conn,
                    f"SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER = {self._ph(1)}",
                    (owner,),
                )
                for row in comment_rows:
                    table_name = _row_value(row, "TABLE_NAME")
                    if table_name:
                        comments[str(table_name)] = str(_row_value(row, "COMMENTS") or "")
            except Exception:
                comments = {}
            return [
                {
                    "name": _row_value(row, "NAME"),
                    "table_type": _row_value(row, "TABLE_TYPE") or "BASE TABLE",
                    "engine": self.engine_name,
                    "row_estimate": int(_row_value(row, "ROW_ESTIMATE") or 0),
                    "comment": comments.get(str(_row_value(row, "NAME") or ""), ""),
                    "schema": owner,
                }
                for row in rows
                if _row_value(row, "NAME")
            ]
        finally:
            conn.close()

    def list_columns(self, database: str, table: str, schema_name: str | None = None) -> list[dict]:
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            rows = self._fetchall(
                conn,
                f"""
                SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE,
                       NULLABLE, DATA_DEFAULT, COLUMN_ID
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = {self._ph(1)} AND TABLE_NAME = {self._ph(2)}
                ORDER BY COLUMN_ID
                """,
                (owner, table),
            )
            pk_cols: set[str] = set()
            try:
                pk_rows = self._fetchall(
                    conn,
                    f"""
                    SELECT cc.COLUMN_NAME
                    FROM ALL_CONSTRAINTS c
                    JOIN ALL_CONS_COLUMNS cc
                      ON c.OWNER = cc.OWNER
                     AND c.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
                     AND c.TABLE_NAME = cc.TABLE_NAME
                    WHERE c.CONSTRAINT_TYPE = 'P'
                      AND c.OWNER = {self._ph(1)}
                      AND c.TABLE_NAME = {self._ph(2)}
                    """,
                    (owner, table),
                )
                pk_cols = {str(_row_value(row, "COLUMN_NAME")) for row in pk_rows if _row_value(row, "COLUMN_NAME")}
            except Exception:
                pk_cols = set()
            result = []
            for row in rows:
                name = str(_row_value(row, "COLUMN_NAME") or "")
                default = _row_value(row, "DATA_DEFAULT")
                result.append(
                    {
                        "name": name,
                        "column_type": _format_oracle_type(row),
                        "data_type": _row_value(row, "DATA_TYPE") or "",
                        "nullable": str(_row_value(row, "NULLABLE") or "").upper() == "Y",
                        "key": "PRI" if name in pk_cols else "",
                        "default": None if default is None else str(default).strip(),
                        "extra": "",
                        "comment": "",
                        "position": _row_value(row, "COLUMN_ID"),
                    }
                )
            return result
        finally:
            conn.close()

    def count_rows(self, database: str, table: str, schema_name: str | None = None) -> int:
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            rows = self._fetchall(conn, f"SELECT COUNT(*) AS CNT FROM {self._qualified(owner, table)}")
            return int(_row_value(rows[0], "CNT") or 0) if rows else 0
        finally:
            conn.close()

    def _page_sql(self, qualified: str, select_sql: str = "*") -> str:
        # Alias must start with a letter. OceanBase Oracle mode rejects ___rn.
        return f"""
            SELECT * FROM (
                SELECT q.*, ROWNUM AS page_rn FROM (
                    SELECT {select_sql} FROM {qualified}
                ) q
                WHERE ROWNUM <= {self._ph(1)}
            )
            WHERE page_rn > {self._ph(2)}
        """

    def _page_params(self, offset: int, limit: int) -> tuple[int, int]:
        return (int(offset) + int(limit), int(offset))

    def fetch_rows(
        self,
        database: str,
        table: str,
        schema_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            qualified = self._qualified(owner, table)
            total = int(
                _row_value(self._fetchall(conn, f"SELECT COUNT(*) AS CNT FROM {qualified}")[0], "CNT") or 0
            )
            rows = self._fetchall(conn, self._page_sql(qualified), self._page_params(offset, limit))
            columns = list(rows[0].keys()) if rows else [col["name"] for col in self.list_columns(database, table, owner)]
            return {
                "columns": columns,
                "rows": [_stringify_row(row) for row in rows],
                "total": total,
            }
        finally:
            conn.close()

    def fetch_signatures(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> list[str]:
        return list(self.iter_signature_hashes(database, table, columns, schema_name))

    def _iter_selected_rows(self, conn, qualified: str, columns: list[str]) -> Iterator[dict]:
        select_sql = ", ".join(_quote_ident(column) for column in columns)
        cur = conn.cursor()
        try:
            if hasattr(cur, "arraysize"):
                cur.arraysize = 8000
            if hasattr(cur, "prefetchrows"):
                cur.prefetchrows = 8000
            cur.execute(f"SELECT {select_sql} FROM {qualified}")
            while True:
                batch = cur.fetchmany(8000)
                if not batch:
                    break
                for row in batch:
                    values = row.values() if isinstance(row, dict) else row
                    yield {
                        column: _materialize_cell(value)
                        for column, value in zip(columns, values)
                    }
        finally:
            cur.close()

    def iter_signature_hashes(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
        value_map: dict | None = None,
        extract_map: dict | None = None,
    ) -> Iterator[bytes]:
        if not columns:
            return
            yield
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            qualified = self._qualified(owner, table)
            for row in self._iter_selected_rows(conn, qualified, columns):
                yield _sig_hash(row, columns, value_map, extract_map)
        finally:
            conn.close()

    def iter_column_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ) -> Iterator[dict]:
        if not columns:
            return
            yield
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            qualified = self._qualified(owner, table)
            yield from self._iter_selected_rows(conn, qualified, columns)
        finally:
            conn.close()

    def fetch_rows_by_indices(
        self,
        database: str,
        table: str,
        indices: list[int],
        schema_name: str | None = None,
    ) -> list[dict]:
        if not indices:
            return []
        wanted = set(indices)
        min_i = min(wanted)
        max_i = max(wanted)
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            qualified = self._qualified(owner, table)
            rows = self._fetchall(
                conn,
                self._page_sql(qualified),
                self._page_params(min_i, max_i - min_i + 1),
            )
            found = {}
            for offset, row in enumerate(rows):
                idx = min_i + offset
                if idx in wanted:
                    found[idx] = _stringify_row(row)
            return [found[idx] for idx in indices if idx in found]
        finally:
            conn.close()

    def distinct_values(
        self,
        database: str,
        table: str,
        column: str,
        schema_name: str | None = None,
        limit: int = 200,
    ) -> list[Any]:
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            qualified = self._qualified(owner, table)
            sql = f"""
                SELECT VAL FROM (
                    SELECT DISTINCT CAST({_quote_ident(column)} AS VARCHAR2(4000)) AS VAL
                    FROM {qualified}
                )
                WHERE ROWNUM <= {self._ph(1)}
            """
            rows = self._fetchall(conn, sql, (int(limit),))
            return [_stringify_value(_row_value(row, "VAL")) for row in rows]
        finally:
            conn.close()

    def fetch_rows_by_column_values(
        self,
        database: str,
        table: str,
        column: str,
        values: list[Any],
        schema_name: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        uniq: list[Any] = []
        seen: set[str] = set()
        for value in values:
            if value is None:
                continue
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(value)
        if not uniq:
            return []
        row_limit = max(int(limit), len(uniq))
        conn = self._connect()
        try:
            owner = self._owner(conn, schema_name)
            qualified = self._qualified(owner, table)
            collected: list[dict] = []
            for start in range(0, len(uniq), 500):
                if len(collected) >= row_limit:
                    break
                chunk = uniq[start : start + 500]
                remaining = row_limit - len(collected)
                placeholders = self._placeholders(len(chunk))
                limit_ph = self._ph(len(chunk) + 1)
                sql = f"""
                    SELECT * FROM (
                        SELECT * FROM {qualified}
                        WHERE CAST({_quote_ident(column)} AS VARCHAR2(4000)) IN ({placeholders})
                    )
                    WHERE ROWNUM <= {limit_ph}
                """
                params = [str(value) for value in chunk] + [int(remaining)]
                collected.extend(_stringify_row(row) for row in self._fetchall(conn, sql, params))
            return collected[:row_limit]
        finally:
            conn.close()


class OracleConnector(OracleLikeConnector):
    engine_name = "oracle"
    connect_label = "Oracle"
    paramstyle = "numeric"
    use_oracle_maintained = True

    def _default_port(self) -> int:
        return 1521

    def _connect(self):
        oracledb = _load_oracledb()
        service = (self.config.get("database") or "").strip()
        if not service:
            raise ConnectionError_("请填写 Oracle 服务名")
        try:
            if service.lower().startswith("sid:"):
                sid = service.split(":", 1)[1].strip()
                if not sid:
                    raise ConnectionError_("请填写 Oracle SID")
                dsn = oracledb.makedsn(self.host, self.port, sid=sid)
            else:
                dsn = oracledb.makedsn(self.host, self.port, service_name=service)
            conn = oracledb.connect(
                user=self.user,
                password=self.password,
                dsn=dsn,
                tcp_connect_timeout=8,
            )
            conn.autocommit = True
            return conn
        except ConnectionError_:
            raise
        except Exception as exc:
            raise ConnectionError_(f"Oracle 连接失败: {exc}") from exc


class OceanBaseOracleConnector(OracleConnector):
    """OceanBase Oracle 租户，走 Oracle 协议（oracledb）。"""

    engine_name = "oceanbase"
    connect_label = "OceanBase"
    use_oracle_maintained = False

    def __init__(self, config: dict):
        config = _normalize_endpoint_config(dict(config), default_port=2881)
        if not config.get("port"):
            config["port"] = 2881
        try:
            if not (config.get("database") or "").strip():
                config["database"] = _oceanbase_oracle_service_name(config)
        except ConnectionError_:
            pass
        super().__init__(config)
        self.port = int(config.get("port") or 2881)

    def _default_port(self) -> int:
        return 2881

    def _connect(self):
        oracledb = _load_oracledb()
        service = _oceanbase_oracle_service_name(self.config)
        try:
            if service.lower().startswith("sid:"):
                sid = service.split(":", 1)[1].strip()
                if not sid:
                    raise ConnectionError_("请填写 OceanBase SID")
                dsn = oracledb.makedsn(self.host, self.port, sid=sid)
            else:
                dsn = oracledb.makedsn(self.host, self.port, service_name=service)
            conn = oracledb.connect(
                user=self.user,
                password=self.password,
                dsn=dsn,
                tcp_connect_timeout=8,
            )
            conn.autocommit = True
            return conn
        except ConnectionError_:
            raise
        except Exception as exc:
            raise ConnectionError_(f"OceanBase 连接失败: {exc}") from exc

    def test_connection(self) -> dict:
        result = super().test_connection()
        result["db_type"] = "oceanbase"
        result["ob_mode"] = "oracle"
        result["message"] = "连接成功（Oracle 租户）"
        return result

    def list_databases(self) -> list[str]:
        service = (self.config.get("database") or "").strip()
        if service.lower().startswith("sid:"):
            service = service.split(":", 1)[1].strip()
        if not service:
            try:
                service = _oceanbase_oracle_service_name(self.config)
            except ConnectionError_:
                service = "OCEANBASE"
        return [service or "OCEANBASE"]


def _jdbc_link_lost(message: str) -> bool:
    text = message.lower()
    markers = (
        "网络通信",
        "not connected",
        "connection reset",
        "connection refused",
        "broken pipe",
        "socket",
        "closed connection",
        "连接已关闭",
        "通信异常",
        "无响应",
        "桥接已退出",
        "通信失败",
    )
    return any(marker in text for marker in markers)


def _bridge_dead(message: str) -> bool:
    return any(marker in message for marker in ("无响应", "桥接已退出", "通信失败", "桥接未启动"))


class _JdbcBridgeSession:
    def __init__(self, classpath: str, label: str = "JDBC", default_driver: str | None = None):
        java = _java_executable()
        if not java:
            raise ConnectionError_(f"{label} JDBC 不可用：未找到 Java")
        self.label = label
        self.default_driver = default_driver
        self.classpath = classpath
        self._java = java
        self.conn_key: tuple | None = None
        self.conn_payload: dict | None = None
        self.reusable = True
        self._recovering = False
        self._stderr_lines: list[str] = []
        self.proc: subprocess.Popen | None = None
        self._spawn()

    def _spawn(self) -> None:
        self._stderr_lines = []
        self.proc = subprocess.Popen(
            [self._java, "-Djava.awt.headless=true", "-Dfile.encoding=UTF-8", "-cp", self.classpath, _jdbc_bridge_main_class()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_jdbc_drivers_dir()),
        )
        threading.Thread(target=self._drain_stderr, args=(self.proc,), daemon=True).start()

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        stderr = proc.stderr
        if stderr is None:
            return
        try:
            for line in stderr:
                text = line.strip()
                if not text:
                    continue
                self._stderr_lines.append(text)
                if len(self._stderr_lines) > 20:
                    del self._stderr_lines[0]
        except Exception:
            return

    def _stderr_tail(self) -> str:
        return " | ".join(self._stderr_lines[-3:])

    def alive(self) -> bool:
        return bool(self.proc) and self.proc.poll() is None

    def _kill_proc(self) -> None:
        proc = self.proc
        self.proc = None
        if not proc:
            return
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass

    def _restart(self, reconnect: bool) -> None:
        payload = self.conn_payload
        key = self.conn_key
        self._kill_proc()
        self.reusable = True
        self._spawn()
        self.conn_key = None
        if reconnect and payload:
            self._request_once(payload)
            self.conn_key = key
            self.conn_payload = payload

    def request(self, payload: dict) -> dict:
        try:
            return self._request_once(payload)
        except ConnectionError_ as exc:
            if self._recovering or not _bridge_dead(str(exc)):
                raise
            op = str(payload.get("op") or "")
            if op in {"quit", "close", "close_result"}:
                raise
            self._recovering = True
            try:
                self._restart(reconnect=op != "connect")
                return self._request_once(payload)
            finally:
                self._recovering = False

    def _request_once(self, payload: dict) -> dict:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            self.reusable = False
            raise ConnectionError_(f"{self.label} JDBC 桥接未启动")
        if self.proc.poll() is not None:
            self.reusable = False
            detail = self._stderr_tail()
            message = f"{self.label} JDBC 桥接已退出: {self.proc.returncode}"
            if detail:
                message = f"{message} ({detail})"
            raise ConnectionError_(message)
        body = dict(payload)
        if body.get("op") == "connect" and not body.get("driver") and self.default_driver:
            body["driver"] = self.default_driver
        try:
            self.proc.stdin.write(json.dumps(body, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        except Exception as exc:
            self.reusable = False
            raise ConnectionError_(f"{self.label} JDBC 通信失败: {exc}") from exc
        if not line:
            self.reusable = False
            detail = self._stderr_tail()
            message = f"{self.label} JDBC 无响应"
            if detail:
                message = f"{message}: {detail}"
            raise ConnectionError_(message)
        try:
            data = json.loads(line)
        except Exception as exc:
            self.reusable = False
            raise ConnectionError_(f"{self.label} JDBC 返回无效 JSON: {line}") from exc
        if not data.get("ok"):
            op = str(payload.get("op") or "")
            kind = "连接失败" if op == "connect" else "查询失败"
            raw_error = str(data.get("error") or data)
            message = f"{self.label} {kind}: {raw_error}"
            # MySQL 1146 / similar: make missing-table errors actionable
            if "doesn't exist" in raw_error or "does not exist" in raw_error.lower() or "1146" in raw_error:
                message = (
                    f"{message}。可能原因：已切换数据库，但对比任务仍引用旧库中的表；"
                    "请重新选择当前库中存在的表并连线"
                )
            if _jdbc_link_lost(message):
                self.reusable = False
                self.conn_key = None
            raise ConnectionError_(message)
        return data

    def shutdown(self):
        self.reusable = False
        self.conn_key = None
        self._kill_proc()


class _JdbcPool:
    """Keep a few warm JVM bridges so each query does not pay process startup."""

    def __init__(self, classpath: str, label: str, driver: str, max_size: int = 3):
        self.classpath = classpath
        self.label = label
        self.driver = driver
        self._max = max_size
        self._size = 0
        self._idle: list[_JdbcBridgeSession] = []
        self._cond = threading.Condition()

    def acquire(self) -> _JdbcBridgeSession:
        with self._cond:
            while True:
                while self._idle:
                    session = self._idle.pop()
                    if session.alive():
                        return session
                    self._size -= 1
                    session.shutdown()
                if self._size < self._max:
                    self._size += 1
                    break
                if not self._cond.wait(timeout=20):
                    raise ConnectionError_(f"{self.label} JDBC 桥接繁忙，请稍后重试")
        try:
            return _JdbcBridgeSession(self.classpath, label=self.label, default_driver=self.driver)
        except Exception:
            with self._cond:
                self._size -= 1
                self._cond.notify()
            raise

    def release(self, session: _JdbcBridgeSession):
        with self._cond:
            if session.alive() and session.reusable and session.conn_key is not None:
                self._idle.append(session)
            else:
                session.shutdown()
                self._size -= 1
            self._cond.notify()


_JDBC_POOLS: dict[str, _JdbcPool] = {}
_JDBC_POOLS_LOCK = threading.Lock()


def _jdbc_pool(classpath: str, label: str, driver: str) -> _JdbcPool:
    with _JDBC_POOLS_LOCK:
        pool = _JDBC_POOLS.get(classpath)
        if pool is None:
            pool = _JdbcPool(classpath, label, driver)
            _JDBC_POOLS[classpath] = pool
        return pool


def _open_jdbc_connection(
    classpath: str,
    label: str,
    driver: str,
    url: str,
    user: str,
    password: str,
) -> "_ObJdbcConnection":
    pool = _jdbc_pool(classpath, label, driver)
    session = pool.acquire()
    payload = {
        "op": "connect",
        "driver": driver,
        "url": url,
        "user": user,
        "password": password,
    }
    key = (url, user, password)
    try:
        if session.conn_key != key:
            session.request(payload)
            session.conn_key = key
            session.conn_payload = payload
        session.reusable = True
        return _ObJdbcConnection(session, pool)
    except Exception:
        session.reusable = False
        session.conn_key = None
        pool.release(session)
        raise


class _ObJdbcSession(_JdbcBridgeSession):
    def __init__(self):
        if not _oceanbase_jdbc_available():
            raise ConnectionError_(
                "OceanBase JDBC 不可用：请确保已安装 Java，并存在 backend/drivers/oceanbase-client.jar"
            )
        super().__init__(
            _oceanbase_jdbc_classpath(),
            label="OceanBase",
            default_driver="com.oceanbase.jdbc.Driver",
        )


class _ObJdbcCursor:
    def __init__(self, session: _JdbcBridgeSession):
        self._session = session
        self.description = None
        self.arraysize = 2000
        self.prefetchrows = 2000
        self._buffer: list[tuple] = []
        self._done = True

    def execute(self, sql: str, params: tuple | list | None = None):
        values = list(params or [])
        payload = {"op": "query", "sql": sql, "params": values}
        try:
            result = self._session.request(payload)
        except ConnectionError_ as exc:
            if not _jdbc_link_lost(str(exc)) or not self._session.conn_payload:
                raise
            self._session.conn_key = None
            self._session.request(self._session.conn_payload)
            self._session.conn_key = (
                self._session.conn_payload.get("url"),
                self._session.conn_payload.get("user"),
                self._session.conn_payload.get("password"),
            )
            result = self._session.request(payload)
        columns = result.get("columns") or []
        self.description = [(name,) for name in columns]
        self._buffer = []
        self._done = False
        return self

    def fetchmany(self, size: int | None = None) -> list[tuple]:
        if self._done and not self._buffer:
            return []
        want = int(size or self.arraysize or 1000)
        while len(self._buffer) < want and not self._done:
            result = self._session.request({"op": "fetch", "size": max(want - len(self._buffer), 1)})
            rows = result.get("rows") or []
            self._buffer.extend(tuple(row) for row in rows)
            if result.get("done") or not rows:
                self._done = True
                break
        out = self._buffer[:want]
        self._buffer = self._buffer[want:]
        return out

    def fetchall(self) -> list[tuple]:
        rows: list[tuple] = []
        while True:
            batch = self.fetchmany(self.arraysize or 2000)
            if not batch:
                break
            rows.extend(batch)
        return rows

    def close(self):
        try:
            self._session.request({"op": "close_result"})
        except Exception:
            self._session.reusable = False
        self._buffer = []
        self._done = True
        self.description = None


class _ObJdbcConnection:
    def __init__(self, session: _JdbcBridgeSession, pool: _JdbcPool | None = None):
        self._session = session
        self._pool = pool
        self._closed = False

    def cursor(self, *args, **kwargs):
        return _ObJdbcCursor(self._session)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._pool is not None:
            self._pool.release(self._session)
            return
        self._session.shutdown()

    def rollback(self):
        return None


class _JdbcReuse:
    """Share one pooled JDBC connection across nested connector calls."""

    def __init__(self, owner: "DamengConnector"):
        self._owner = owner
        self._closed = False

    def cursor(self, *args, **kwargs):
        live = self._owner._jdbc_live
        if live is None:
            raise ConnectionError_("达梦连接已关闭")
        return live.cursor()

    def close(self):
        if self._closed:
            return
        self._closed = True
        owner = self._owner
        owner._jdbc_depth = max(0, owner._jdbc_depth - 1)
        if owner._jdbc_depth == 0 and owner._jdbc_live is not None:
            live = owner._jdbc_live
            owner._jdbc_live = None
            live.close()

    def rollback(self):
        return None


class OceanBaseJdbcConnector(OracleLikeConnector):
    """OceanBase via official JDBC driver (supports Oracle tenants on MySQL OBProxy ports)."""

    engine_name = "oceanbase"
    connect_label = "OceanBase"
    paramstyle = "qmark"
    use_oracle_maintained = False

    def __init__(self, config: dict):
        config = _normalize_endpoint_config(dict(config), default_port=2881)
        if not config.get("port"):
            config["port"] = 2881
        super().__init__(config)
        self.port = int(config.get("port") or 2881)

    def _default_port(self) -> int:
        return 2881

    def _jdbc_url(self) -> str:
        host = self.host
        port = self.port
        database = (self.config.get("database") or "").strip()
        if database and not database.lower().startswith("sid:"):
            return f"jdbc:oceanbase://{host}:{port}/{database}"
        return f"jdbc:oceanbase://{host}:{port}"

    def _connect(self):
        return _open_jdbc_connection(
            _oceanbase_jdbc_classpath(),
            "OceanBase",
            "com.oceanbase.jdbc.Driver",
            self._jdbc_url(),
            self.user,
            self.password,
        )

    def test_connection(self) -> dict:
        conn = self._connect()
        try:
            version = ""
            try:
                rows = self._fetchall(conn, "SELECT USER AS CURRENT_USER FROM DUAL")
                user = str(_row_value(rows[0], "CURRENT_USER") or "") if rows else ""
                version = f"OceanBase JDBC / user={user}" if user else "OceanBase JDBC"
            except Exception:
                version = "OceanBase JDBC"
            return {
                "ok": True,
                "message": "连接成功（OceanBase JDBC / Oracle 租户）",
                "version": version,
                "db_type": "oceanbase",
                "ob_mode": "oracle",
            }
        finally:
            conn.close()

    def list_databases(self) -> list[str]:
        try:
            service = _oceanbase_oracle_service_name(self.config)
        except ConnectionError_:
            service = (self.config.get("database") or "").strip() or "OCEANBASE"
        if service.lower().startswith("sid:"):
            service = service.split(":", 1)[1].strip()
        return [service or "OCEANBASE"]


def _dameng_missing_table(exc: BaseException) -> bool:
    text = str(exc)
    return "无效的表或视图名" in text or "无效的模式名" in text


def _iter_skip_missing(inner):
    try:
        yield from inner
    except ConnectionError_ as exc:
        if _dameng_missing_table(exc):
            return
        raise


_DM_CACHE: dict[tuple, tuple[float, Any]] = {}
_DM_CACHE_LOCK = threading.Lock()


def _dm_cache_get(key: tuple, ttl: float):
    now = time.monotonic()
    with _DM_CACHE_LOCK:
        hit = _DM_CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    return None


def _dm_cache_put(key: tuple, value: Any) -> None:
    with _DM_CACHE_LOCK:
        _DM_CACHE[key] = (time.monotonic(), value)


def _dm_cache_key(config_host: str, port: int, user: str, password: str, *parts: str) -> tuple:
    digest = hashlib.sha256((password or "").encode("utf-8")).hexdigest()
    return (config_host, int(port), user, digest, *parts)


class DamengConnector(OracleLikeConnector):
    """达梦优先走官方 JDBC（无需完整客户端）；若不可用再回退 dmPython。"""

    engine_name = "dameng"
    connect_label = "达梦"
    paramstyle = "qmark"
    use_oracle_maintained = False
    system_schemas = DAMENG_SYSTEM_SCHEMAS

    def __init__(self, config: dict):
        config = _normalize_endpoint_config(dict(config), default_port=5236)
        if not config.get("port"):
            config["port"] = 5236
        super().__init__(config)
        self.port = int(config.get("port") or 5236)
        self._use_jdbc = _dameng_jdbc_available()
        self._jdbc_live = None
        self._jdbc_depth = 0

    def _default_port(self) -> int:
        return 5236

    def _preferred_schema(self) -> str:
        return (self.config.get("database") or "").strip()

    def _owner(self, conn, schema_name: str | None = None) -> str:
        """Resolve table owner/schema.

        Important: do NOT fall back to the optional "默认模式" for table ops.
        That field is only a UI preference; using it as owner causes lookups like
        HSGJJ.PERMISSIONS when the UI omits schema_name, which fails if the
        table only exists in another schema (e.g. SYSDBA/NACOS).
        """
        name = (schema_name or "").strip()
        if name:
            return name
        user = self._current_user(conn)
        if not user:
            raise ConnectionError_("无法确定达梦当前模式，请先选择模式")
        return user

    def _jdbc_url(self) -> str:
        # Never bind CURRENT_SCHEMA via JDBC URL. Optional database/mode is only
        # used as a preferred schema in the UI list, not as a sticky session schema.
        return f"jdbc:dm://{self.host}:{self.port}"

    def _cache_key(self, *parts: str) -> tuple:
        return _dm_cache_key(self.host, self.port, self.user, self.password, *parts)

    def _open_jdbc(self):
        if not self._use_jdbc:
            return self._connect()
        return _open_jdbc_connection(
            _dameng_jdbc_classpath(),
            "达梦",
            "dm.jdbc.driver.DmDriver",
            self._jdbc_url(),
            self.user,
            self.password,
        )

    def list_schemas(self, database: str) -> list[str]:
        """List Dameng schemas from object owners.

        ALL_USERS alone is incomplete on Dameng: many business schemas own tables
        but are not returned as users (e.g. CAP_GJJ_*), so we read SYSOBJECTS.
        """
        cached = _dm_cache_get(self._cache_key("schemas"), 180)
        if cached is not None:
            return list(cached)
        conn = self._connect()
        try:
            current = self._current_user(conn)
            names: list[str] = []
            seen: set[str] = set()
            try:
                rows = self._fetchall(
                    conn,
                    """
                    SELECT DISTINCT s.NAME AS USERNAME
                    FROM SYSOBJECTS o
                    JOIN SYSOBJECTS s ON o.SCHID = s.ID
                    WHERE s.TYPE$ = 'SCH' AND o.SUBTYPE$ IN ('UTAB', 'VIEW')
                    ORDER BY s.NAME
                    """,
                )
            except Exception:
                rows = self._fetchall(
                    conn,
                    """
                    SELECT OWNER AS USERNAME FROM ALL_TABLES
                    UNION
                    SELECT OWNER FROM ALL_VIEWS
                    UNION
                    SELECT USERNAME FROM ALL_USERS
                    ORDER BY 1
                    """,
                )
            for row in rows:
                name = _row_value(row, "USERNAME") or _row_value(row, "NAME")
                if not name:
                    continue
                text = str(name)
                upper = text.upper()
                if upper in seen:
                    continue
                if upper in DAMENG_SCHEMA_LIST_SKIP and upper != (current or "").upper():
                    continue
                seen.add(upper)
                names.append(text)

            ordered: list[str] = []
            if current:
                match = next((n for n in names if n.upper() == current.upper()), current)
                ordered.append(match)
            preferred = self._preferred_schema()
            if preferred:
                match = next((n for n in names if n.upper() == preferred.upper()), preferred)
                if match not in ordered:
                    ordered.append(match)
            for name in names:
                if name not in ordered:
                    ordered.append(name)
            _dm_cache_put(self._cache_key("schemas"), list(ordered))
            return ordered
        finally:
            conn.close()

    def list_tables(self, database: str, schema_name: str | None = None) -> list[dict]:
        schema = (schema_name or "").strip()
        if not schema:
            conn = self._connect()
            try:
                schema = self._owner(conn, None)
            finally:
                conn.close()
        cached = _dm_cache_get(self._cache_key("tables", schema), 60)
        if cached is not None:
            return [dict(item) for item in cached]
        with ThreadPoolExecutor(max_workers=2) as pool:
            comment_job = pool.submit(self._load_table_comments, schema)
            tables = self._load_table_names(schema)
            bases = [table for table in tables if str(table.get("table_type") or "").upper() != "VIEW"]
            if bases and len(bases) <= 80:
                self._fill_exact_counts_on_new_connection(bases)
            comments = comment_job.result()
        for table in tables:
            table["comment"] = comments.get(str(table.get("name") or ""), "")
        _dm_cache_put(self._cache_key("tables", schema), [dict(item) for item in tables])
        return tables

    def _load_table_names(self, schema: str) -> list[dict]:
        conn = self._open_jdbc()
        try:
            try:
                rows = self._fetchall(
                    conn,
                    """
                    SELECT o.NAME AS NAME, o.SUBTYPE$ AS SUBTYPE
                    FROM SYSOBJECTS o
                    JOIN SYSOBJECTS s ON o.SCHID = s.ID
                    WHERE s.NAME = ? AND s.TYPE$ = 'SCH' AND o.SUBTYPE$ IN ('UTAB', 'VIEW')
                    ORDER BY o.NAME
                    """,
                    (schema,),
                )
            except Exception:
                rows = self._fetchall(
                    conn,
                    """
                    SELECT TABLE_NAME AS NAME, 'UTAB' AS SUBTYPE
                    FROM ALL_TABLES
                    WHERE OWNER = ?
                    UNION ALL
                    SELECT VIEW_NAME, 'VIEW'
                    FROM ALL_VIEWS
                    WHERE OWNER = ?
                    ORDER BY 1
                    """,
                    (schema, schema),
                )
            tables = []
            for row in rows:
                name = _row_value(row, "NAME")
                if not name:
                    continue
                subtype = str(_row_value(row, "SUBTYPE") or "").upper()
                tables.append(
                    {
                        "name": str(name),
                        "table_type": "VIEW" if subtype == "VIEW" else "BASE TABLE",
                        "engine": self.engine_name,
                        "row_estimate": 0,
                        "comment": "",
                        "schema": schema,
                    }
                )
            return tables
        finally:
            conn.close()

    def _load_table_comments(self, schema: str) -> dict[str, str]:
        conn = self._open_jdbc()
        try:
            try:
                rows = self._fetchall(
                    conn,
                    "SELECT TVNAME AS TABLE_NAME, COMMENT$ AS COMMENTS FROM SYSTABLECOMMENTS WHERE SCHNAME = ?",
                    (schema,),
                )
            except Exception:
                rows = self._fetchall(
                    conn,
                    "SELECT TABLE_NAME, COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER = ?",
                    (schema,),
                )
            comments: dict[str, str] = {}
            for row in rows:
                name = _row_value(row, "TABLE_NAME") or _row_value(row, "TVNAME")
                if name:
                    comments[str(name)] = str(_row_value(row, "COMMENTS") or _row_value(row, "COMMENT$") or "")
            return comments
        except Exception:
            return {}
        finally:
            conn.close()

    def _fill_exact_counts_on_new_connection(self, tables: list[dict]) -> None:
        conn = self._open_jdbc()
        try:
            self._fill_exact_counts(conn, tables)
        finally:
            conn.close()

    def _fill_exact_counts(self, conn, tables: list[dict]) -> None:
        grouped: dict[str, list[dict]] = {}
        for table in tables:
            owner = str(table.get("schema") or "")
            name = str(table.get("name") or "")
            if owner and name:
                grouped.setdefault(owner, []).append(table)
        for owner, items in grouped.items():
            for start in range(0, len(items), 25):
                self._count_chunk(conn, owner, items[start : start + 25])

    def _count_chunk(self, conn, owner: str, chunk: list[dict]) -> None:
        parts: list[str] = []
        for table in chunk:
            name = str(table.get("name") or "")
            literal = name.replace("'", "''")
            parts.append(
                f"SELECT '{literal}' AS NAME, COUNT(*) AS CNT FROM {self._qualified(owner, name)}"
            )
        try:
            rows = self._fetchall(conn, " UNION ALL ".join(parts))
        except Exception:
            for table in chunk:
                name = str(table.get("name") or "")
                try:
                    counted = self._fetchall(
                        conn,
                        f"SELECT COUNT(*) AS CNT FROM {self._qualified(owner, name)}",
                    )
                    raw = counted[0] if counted else {}
                    value = _row_value(raw, "CNT")
                    if value is None and raw:
                        value = next(iter(raw.values()))
                    table["row_estimate"] = int(value or 0)
                except Exception:
                    continue
            return
        found: dict[str, Any] = {}
        for row in rows:
            key = str(_row_value(row, "NAME") or "")
            if key:
                found[key] = _row_value(row, "CNT")
        for table in chunk:
            name = str(table.get("name") or "")
            value = found.get(name)
            if value is None:
                value = found.get(name.upper())
            if value is not None:
                table["row_estimate"] = int(value or 0)

    def list_databases(self) -> list[str]:
        conn = self._connect()
        try:
            try:
                rows = self._fetchall(conn, "SELECT NAME FROM V$DATABASE")
                name = _row_value(rows[0], "NAME") if rows else None
                if name:
                    return [str(name)]
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return ["DAMENG"]
        finally:
            conn.close()

    def _connect(self):
        if self._use_jdbc:
            if self._jdbc_depth > 0 and self._jdbc_live is not None:
                self._jdbc_depth += 1
                return _JdbcReuse(self)
            live = _open_jdbc_connection(
                _dameng_jdbc_classpath(),
                "达梦",
                "dm.jdbc.driver.DmDriver",
                self._jdbc_url(),
                self.user,
                self.password,
            )
            self._jdbc_live = live
            self._jdbc_depth = 1
            return _JdbcReuse(self)

        dm = _load_dm()
        attempts = (
            {"user": self.user, "password": self.password, "server": self.host, "port": self.port},
            {"user": self.user, "password": self.password, "host": self.host, "port": self.port},
        )
        last_error: Exception | None = None
        for kwargs in attempts:
            try:
                conn = dm.connect(**kwargs)
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                raise ConnectionError_(f"达梦连接失败: {exc}") from exc
            try:
                conn.autocommit = True
            except Exception:
                pass
            return conn
        raise ConnectionError_(f"达梦连接失败: {last_error}")

    def test_connection(self) -> dict:
        conn = self._connect()
        try:
            version = "达梦 JDBC" if self._use_jdbc else "dmPython"
            try:
                rows = self._fetchall(conn, "SELECT USER AS CURRENT_USER FROM DUAL")
                user = str(_row_value(rows[0], "CURRENT_USER") or "") if rows else ""
                if user:
                    version = f"{version} / user={user}"
            except Exception:
                pass
            return {
                "ok": True,
                "message": "连接成功（达梦 JDBC）" if self._use_jdbc else "连接成功",
                "version": version,
                "db_type": "dameng",
            }
        finally:
            conn.close()

    def count_rows(self, database: str, table: str, schema_name: str | None = None) -> int:
        try:
            return super().count_rows(database, table, schema_name)
        except ConnectionError_ as exc:
            if _dameng_missing_table(exc):
                return 0
            raise

    def fetch_rows(
        self,
        database: str,
        table: str,
        schema_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        schema = (schema_name or "").strip()
        if not schema:
            conn = self._connect()
            try:
                schema = self._owner(conn, None)
            finally:
                conn.close()
        qualified = self._qualified(schema, table)

        def load_total() -> int:
            conn = self._open_jdbc()
            try:
                rows = self._fetchall(conn, f"SELECT COUNT(*) AS CNT FROM {qualified}")
                raw = rows[0] if rows else {}
                value = _row_value(raw, "CNT")
                if value is None and raw:
                    value = next(iter(raw.values()))
                return int(value or 0)
            finally:
                conn.close()

        def load_page() -> list[dict]:
            conn = self._open_jdbc()
            try:
                return self._fetchall(
                    conn,
                    self._page_sql(qualified),
                    self._page_params(int(offset), int(limit)),
                )
            finally:
                conn.close()

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                total_job = pool.submit(load_total)
                page_job = pool.submit(load_page)
                total = total_job.result()
                rows = page_job.result()
        except ConnectionError_ as exc:
            if _dameng_missing_table(exc):
                return {"columns": [], "rows": [], "total": 0}
            raise
        columns = list(rows[0].keys()) if rows else [col["name"] for col in self.list_columns(database, table, schema)]
        return {
            "columns": columns,
            "rows": [_stringify_row(row) for row in rows],
            "total": total,
        }

    def distinct_values(
        self,
        database: str,
        table: str,
        column: str,
        schema_name: str | None = None,
        limit: int = 200,
    ) -> list[Any]:
        try:
            return super().distinct_values(database, table, column, schema_name, limit=limit)
        except ConnectionError_ as exc:
            if _dameng_missing_table(exc):
                return []
            raise

    def fetch_rows_by_column_values(
        self,
        database: str,
        table: str,
        column: str,
        values: list[Any],
        schema_name: str | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        try:
            return super().fetch_rows_by_column_values(
                database, table, column, values, schema_name, limit=limit
            )
        except ConnectionError_ as exc:
            if _dameng_missing_table(exc):
                return []
            raise

    def fetch_rows_by_indices(
        self,
        database: str,
        table: str,
        indices: list[int],
        schema_name: str | None = None,
    ) -> list[dict]:
        try:
            return super().fetch_rows_by_indices(database, table, indices, schema_name)
        except ConnectionError_ as exc:
            if _dameng_missing_table(exc):
                return []
            raise

    def iter_column_rows(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
    ):
        return _iter_skip_missing(
            super().iter_column_rows(database, table, columns, schema_name)
        )

    def iter_signature_hashes(
        self,
        database: str,
        table: str,
        columns: list[str],
        schema_name: str | None = None,
        value_map: dict | None = None,
        extract_map: dict | None = None,
    ):
        return _iter_skip_missing(
            super().iter_signature_hashes(
                database,
                table,
                columns,
                schema_name,
                value_map=value_map,
                extract_map=extract_map,
            )
        )


def _alias_lookup_key(column: str, value: Any) -> tuple[str, str]:
    text = _stringify_value(value)
    if text is None:
        text = ""
    return (column, str(text).strip())


def _normalize_comparable_value(value: Any) -> Any:
    """Normalize values so cross-DB scalar forms can match.

    Examples treated as equal:
    - 0 / "0" / False
    - 1 / "1" / True
    - 文稿标题,内容 / ["文稿标题","内容"]
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    if not isinstance(value, str):
        return value
    text = value.strip()
    # 跨库常见差异：PG 空串 vs MySQL NULL，内容对比视为相等
    if not text or text.upper() == "NULL":
        return None

    # Numeric scalars stored as strings in one database.
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except Exception:
            pass
    if re.fullmatch(r"-?\d+\.\d+", text):
        try:
            num = float(text)
            return int(num) if num.is_integer() else num
        except Exception:
            pass
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return 1 if lowered == "true" else 0

    items: list[str] | None = None
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list) and all(
            x is None or isinstance(x, (str, int, float, bool)) for x in parsed
        ):
            items = ["" if x is None else str(x).strip() for x in parsed]

    if items is None and re.search(r"[,，;、]", text) and "[" not in text and "{" not in text:
        parts = [p.strip() for p in re.split(r"[,，;、]+", text)]
        if (
            len(parts) >= 2
            and all(parts)
            and all(len(p) <= 64 for p in parts)
            and all("\n" not in p for p in parts)
        ):
            items = parts

    if not items:
        return value
    return "\x1f".join(items)


def _comparable_token(
    column: str,
    value: Any,
    value_map: dict | None = None,
    extract_positions: list[int] | None = None,
) -> Any:
    raw = _stringify_value(value)
    if extract_positions:
        extracted = extract_chars_by_positions(raw, extract_positions)
        if extracted is None:
            # Out-of-range positions must not collide across rows.
            return f"__EXTRACT_MISS__:{column}:{raw!s}"
        return extracted
    mapped = value_map.get(_alias_lookup_key(column, raw)) if value_map else None
    if mapped is not None:
        return mapped
    return _normalize_comparable_value(raw)


def _row_signature(
    row: dict,
    columns: list[str],
    value_map: dict | None = None,
    extract_map: dict | None = None,
) -> str:
    extract_map = extract_map or {}
    values = [
        _comparable_token(column, row.get(column), value_map, extract_map.get(column))
        for column in columns
    ]
    return json.dumps(values, ensure_ascii=False, default=str)


def _sig_hash(
    row: dict,
    columns: list[str],
    value_map: dict | None = None,
    extract_map: dict | None = None,
) -> bytes:
    return hashlib.blake2s(
        _row_signature(row, columns, value_map, extract_map).encode("utf-8"),
        digest_size=16,
    ).digest()


def values_sig_hash(
    columns: list[str],
    values: list[Any],
    value_map: dict | None = None,
    extract_map: dict | None = None,
) -> bytes:
    extract_map = extract_map or {}
    out = [
        _comparable_token(column, value, value_map, extract_map.get(column))
        for column, value in zip(columns, values)
    ]
    return hashlib.blake2s(
        json.dumps(out, ensure_ascii=False, default=str).encode("utf-8"),
        digest_size=16,
    ).digest()


def parse_position_spec(spec: str) -> list[int]:
    """Parse position input.

    From start (1-based):
    - "1245" -> [1, 2, 4, 5]
    - "4,5,7,8" -> [4, 5, 7, 8]

    From end (negative, -1 = last char):
    - "-1245" -> [-1, -2, -4, -5]
    - "-5,-4,-2,-1" -> [-5, -4, -2, -1]
    """
    text = (spec or "").strip()
    if not text:
        return []
    if re.search(r"[,，\s;；、]", text):
        parts = [p.strip() for p in re.split(r"[,，\s;；、]+", text) if p.strip()]
        out: list[int] = []
        for part in parts:
            if not re.fullmatch(r"-?[1-9]\d*", part):
                return []
            value = int(part)
            if value == 0:
                return []
            out.append(value)
        return out
    # Compact from-end: "-1245" -> [-1, -2, -4, -5]
    if re.fullmatch(r"-[1-9]+", text):
        return [-int(ch) for ch in text[1:]]
    if re.fullmatch(r"[1-9]+", text):
        return [int(ch) for ch in text]
    return []


def extract_chars_by_positions(value: Any, positions: list[int]) -> str | None:
    """Take characters by 1-based start indexes or negative end indexes (-1 = last)."""
    if not positions:
        return None
    raw = _stringify_value(value)
    text = "" if raw is None else str(raw)
    n = len(text)
    chars: list[str] = []
    for pos in positions:
        if pos > 0:
            idx = pos - 1
        elif pos < 0:
            idx = n + pos
        else:
            return None
        if idx < 0 or idx >= n:
            return None
        chars.append(text[idx])
    return "".join(chars)


def build_extract_alternatives(
    columns_source: list[str],
    columns_target: list[str],
    rules: list | None,
) -> dict[tuple[str, str], list[tuple[list[int], list[int]]]]:
    """Map (source_field, target_field) -> list of (source_positions, target_positions).

    Multiple rules on the same field pair are OR alternatives.
    """
    out: dict[tuple[str, str], list[tuple[list[int], list[int]]]] = {}
    if not rules:
        return out
    pairs = set(zip(columns_source, columns_target))
    for rule in rules or []:
        source_field = getattr(rule, "source_field", None) or (
            rule.get("source_field") if isinstance(rule, dict) else None
        )
        target_field = getattr(rule, "target_field", None) or (
            rule.get("target_field") if isinstance(rule, dict) else None
        )
        source_positions = getattr(rule, "source_positions", None) or (
            rule.get("source_positions") if isinstance(rule, dict) else None
        )
        target_positions = getattr(rule, "target_positions", None) or (
            rule.get("target_positions") if isinstance(rule, dict) else None
        )
        if not source_field or not target_field:
            continue
        pair = (source_field, target_field)
        if pair not in pairs:
            continue
        sp = parse_position_spec(str(source_positions or ""))
        tp = parse_position_spec(str(target_positions or ""))
        if not sp or not tp:
            continue
        out.setdefault(pair, []).append((sp, tp))
    return out


def extract_alternatives_equal(
    source_value: Any,
    target_value: Any,
    alternatives: list[tuple[list[int], list[int]]] | None,
) -> bool | None:
    """Return True/False when alternatives exist; None when no extract rules."""
    if not alternatives:
        return None
    for source_positions, target_positions in alternatives:
        left = extract_chars_by_positions(source_value, source_positions)
        right = extract_chars_by_positions(target_value, target_positions)
        if left is not None and right is not None and left == right:
            return True
    return False


def _extract_side_tokens(
    value: Any,
    alternatives: list[tuple[list[int], list[int]]],
    side: str,
) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for source_positions, target_positions in alternatives:
        positions = source_positions if side == "source" else target_positions
        extracted = extract_chars_by_positions(value, positions)
        if extracted is None or extracted in seen:
            continue
        seen.add(extracted)
        tokens.append(extracted)
    return tokens


def values_sig_hashes_with_extracts(
    columns: list[str],
    values: list[Any],
    partner_columns: list[str],
    value_map: dict | None,
    extract_alternatives: dict[tuple[str, str], list[tuple[list[int], list[int]]]] | None,
    side: str,
) -> list[bytes]:
    """Build one or more signature hashes; extract OR rules expand into multiple keys."""
    import itertools

    extract_alternatives = extract_alternatives or {}
    token_lists: list[list[Any]] = []
    for column, value, partner in zip(columns, values, partner_columns):
        pair = (column, partner) if side == "source" else (partner, column)
        alternatives = extract_alternatives.get(pair) or []
        if alternatives:
            tokens = _extract_side_tokens(value, alternatives, side)
            token_lists.append(tokens or [f"__EXTRACT_MISS__:{column}:{value!s}"])
        else:
            token_lists.append([_comparable_token(column, value, value_map)])

    hashes: list[bytes] = []
    seen: set[bytes] = set()
    for combo in itertools.product(*token_lists):
        digest = hashlib.blake2s(
            json.dumps(list(combo), ensure_ascii=False, default=str).encode("utf-8"),
            digest_size=16,
        ).digest()
        if digest in seen:
            continue
        seen.add(digest)
        hashes.append(digest)
    return hashes


def values_equal_with_extracts(
    source_cols: list[str],
    source_values: list[Any],
    source_map: dict | None,
    target_cols: list[str],
    target_values: list[Any],
    target_map: dict | None,
    extract_alternatives: dict[tuple[str, str], list[tuple[list[int], list[int]]]] | None = None,
) -> bool:
    extract_alternatives = extract_alternatives or {}
    for source_col, source_value, target_col, target_value in zip(
        source_cols, source_values, target_cols, target_values
    ):
        alternatives = extract_alternatives.get((source_col, target_col))
        extracted = extract_alternatives_equal(source_value, target_value, alternatives)
        if extracted is not None:
            if not extracted:
                return False
            continue
        if _comparable_token(source_col, source_value, source_map) != _comparable_token(
            target_col, target_value, target_map
        ):
            return False
    return True


_COMPACT_RE = re.compile(r"[\s_\-./]")


def _is_null_search_keyword(term) -> bool:
    return str(term or "").strip().upper() == "NULL"


def _is_empty_search_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (bytes, bytearray)):
        return False
    text = str(value).strip()
    return not text or text.upper() == "NULL"


def _row_search_text(row: dict, columns: list[str]) -> str:
    parts = []
    for column in columns:
        raw = row.get(column)
        if _is_empty_search_value(raw):
            # 空值在界面显示为 NULL；写入 NULL 便于关键词 "NULL" 模糊命中
            parts.append(f"{column}=NULL")
            parts.append("NULL")
            continue
        value = _stringify_value(raw)
        parts.append(f"{column}={'' if value is None else value}")
        if value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _fuzzy_match_text(text: str, keyword: str) -> bool:
    kw = (keyword or "").strip().lower()
    if not kw:
        return True
    haystack = (text or "").lower()
    compact = _COMPACT_RE.sub("", haystack)
    for part in kw.split():
        if not part:
            continue
        if part in haystack:
            continue
        compact_part = _COMPACT_RE.sub("", part)
        if compact_part and compact_part in compact:
            continue
        return False
    return True


def _exact_match_values(row: dict, columns: list[str], keywords: list[str]) -> bool:
    targets = {str(term).strip() for term in keywords if str(term).strip()}
    if not targets:
        return True
    null_wanted = any(_is_null_search_keyword(term) for term in targets)
    plain_targets = {term for term in targets if not _is_null_search_keyword(term)}
    for column in columns:
        raw = row.get(column)
        if _is_empty_search_value(raw):
            if null_wanted:
                return True
            continue
        value = _stringify_value(raw)
        text = "" if value is None else str(value).strip()
        if text in plain_targets:
            return True
    return False


def _condition_matches_row(row: dict, columns: list[str], keywords: list[str], mode: str) -> bool:
    mode = (mode or "include").strip().lower()
    if mode in {"equals", "not_equals"}:
        hit = _exact_match_values(row, columns, keywords)
        return (not hit) if mode == "not_equals" else hit
    haystack = _row_search_text(row, columns)
    hit = any(_fuzzy_match_text(haystack, term) for term in keywords)
    return (not hit) if mode == "exclude" else hit


def _ident(name: str) -> str:
    return name.replace("`", "").replace('"', "").replace(";", "")


def _stringify_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if isinstance(value, bool):
        return value
    # Keep JS-safe: integers beyond Number.MAX_SAFE_INTEGER must be strings.
    if isinstance(value, int):
        if value > 9007199254740991 or value < -9007199254740991:
            return str(value)
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str):
        return value
    return str(value)


def _extract_content_tokens(value: Any) -> list[str]:
    """Extract comparable content tokens from plain text, CSV, JSON array, or list."""
    if value is None:
        return []
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            # Structured list/JSON array items are already clauses — keep atomic.
            if isinstance(item, str):
                text = item.strip()
                if text:
                    out.append(text)
            else:
                out.extend(_extract_content_tokens(item))
        return out
    if isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return [text] if text else []

    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return _extract_content_tokens(parsed)
    # Numbered Chinese duty clauses often joined as "。……,(二)……"
    clause_parts = [p.strip() for p in re.split(r"(?<=[。．])\s*,\s*", text) if p.strip()]
    if len(clause_parts) >= 2:
        return clause_parts
    if re.search(r"[,，;、]", text) and "[" not in text and "{" not in text:
        parts = [p.strip() for p in re.split(r"[,，;、]+", text)]
        if len(parts) >= 2 and all(parts) and all(len(p) <= 64 for p in parts):
            return parts
    return [text]


def _fuzzy_tokens_for(
    column: str,
    value: Any,
    value_map: dict | None = None,
    extract_positions: list[int] | None = None,
) -> list[str]:
    raw = _stringify_value(value)
    if extract_positions:
        extracted = extract_chars_by_positions(raw, extract_positions)
        if extracted is None:
            return []
        return [extracted]
    mapped = value_map.get(_alias_lookup_key(column, raw)) if value_map else None
    if mapped is not None:
        return [str(mapped)]
    return _extract_content_tokens(value if not isinstance(value, str) else raw)


def _compact_content_blob(tokens: list[str]) -> str:
    return re.sub(r'[\s\[\]"\'“”‘’",，、;；:：]+', "", "".join(tokens))


def fuzzy_content_equal(
    source_column: str,
    source_value: Any,
    source_map: dict | None,
    target_column: str,
    target_value: Any,
    target_map: dict | None,
    extract_alternatives: list[tuple[list[int], list[int]]] | None = None,
) -> bool:
    extracted = extract_alternatives_equal(source_value, target_value, extract_alternatives)
    if extracted is not None:
        return extracted
    left = _fuzzy_tokens_for(source_column, source_value, source_map)
    right = _fuzzy_tokens_for(target_column, target_value, target_map)
    if left == right:
        return True
    if set(left) == set(right):
        return True
    if len(left) == 1 and left[0] in right:
        return True
    if len(right) == 1 and right[0] in left:
        return True
    if left and right and "".join(left) == "".join(right):
        return True
    # Ignore punctuation/format differences between plain text and JSON arrays.
    if left and right and _compact_content_blob(left) == _compact_content_blob(right):
        return True
    return False


def fuzzy_index_keys(
    column: str,
    value: Any,
    value_map: dict | None = None,
    extract_alternatives: list[tuple[list[int], list[int]]] | None = None,
    side: str = "source",
) -> list[str]:
    if extract_alternatives:
        tokens = _extract_side_tokens(value, extract_alternatives, side)
        if not tokens:
            return [""]
        keys = {"\x1f".join(sorted(tokens))}
        keys.update(tokens)
        return list(keys)
    tokens = _fuzzy_tokens_for(column, value, value_map)
    keys = {"\x1f".join(sorted(tokens))}
    for token in set(tokens):
        keys.add(token)
    if not tokens:
        keys.add("")
    return list(keys)


def values_fuzzy_equal(
    source_cols: list[str],
    source_values: list[Any],
    source_map: dict | None,
    target_cols: list[str],
    target_row: dict,
    target_map: dict | None,
    extract_alternatives: dict[tuple[str, str], list[tuple[list[int], list[int]]]] | None = None,
) -> bool:
    extract_alternatives = extract_alternatives or {}
    for source_col, source_value, target_col in zip(source_cols, source_values, target_cols):
        if not fuzzy_content_equal(
            source_col,
            source_value,
            source_map,
            target_col,
            target_row.get(target_col),
            target_map,
            extract_alternatives.get((source_col, target_col)),
        ):
            return False
    return True


def _stringify_row(row: dict) -> dict:
    return {k: _stringify_value(v) for k, v in row.items()}
