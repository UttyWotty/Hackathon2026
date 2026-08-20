"""
Snowflake connection pooling for efficient query execution.

Features:
- Connection pooling for performance
- Multi-database support (Main: ONTOLOGY_DATABASE, Raw: SNOWFLAKE_DATABASE)
- Read-only query validation
- Automatic connection retry
- Query result caching option

Author: Utku Gulbardak
Date: 2025-10-22
"""

import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Dict, Literal, Optional

import pandas as pd
import snowflake.connector

logger = logging.getLogger(__name__)


DatabaseType = Literal["Main", "Raw"]


class SnowflakeSessionPool:
    """
    Manages Snowflake connections with pooling and multi-database support.

    Features:
    - Connection reuse and pooling
    - Read-only query validation
    - Multi-database support
    - Error handling and retry logic
    - Query result caching
    """

    def __init__(self):
        """
        Initialize Snowflake session pool.

        Environment Variables Required:
        - SNOWFLAKE_ACCOUNT
        - SNOWFLAKE_USER or SNOWFLAKE_USERNAME
        - SNOWFLAKE_PASSWORD
        - SNOWFLAKE_WAREHOUSE
        - SNOWFLAKE_DATABASE (Main database - typically ONTOLOGY_DATABASE)
        - SNOWFLAKE_SCHEMA
        - SNOWFLAKE_ROLE (optional)
        """
        # Initialize the pool first so close_all() is safe even if the
        # env-var validation below raises (e.g. missing credentials in CI).
        self._connections: Dict[str, snowflake.connector.SnowflakeConnection] = {}

        # Validate required environment variables
        required_vars = [
            "SNOWFLAKE_ACCOUNT",
            "SNOWFLAKE_WAREHOUSE",
            "SNOWFLAKE_DATABASE",
            "SNOWFLAKE_SCHEMA",
        ]

        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        # Require either password OR private key
        has_password = bool(os.getenv("SNOWFLAKE_PASSWORD"))
        has_private_key = bool(os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"))

        if not has_password and not has_private_key:
            raise ValueError(
                "Either SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH must be set"
            )

        # Connection configuration
        self.config = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER") or os.getenv("SNOWFLAKE_USERNAME"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),  # Main database
            "schema": os.getenv("SNOWFLAKE_SCHEMA"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
        }

        # Add timeout settings for long-running queries
        # network_timeout: Timeout for network operations (default: 3600 seconds = 1 hour)
        # login_timeout: Timeout for login (default: 60 seconds)
        # ocsp_fail_open: Allow connection even if OCSP certificate validation fails
        self.config["network_timeout"] = int(
            os.getenv("SNOWFLAKE_NETWORK_TIMEOUT", "3600")
        )
        self.config["login_timeout"] = int(os.getenv("SNOWFLAKE_LOGIN_TIMEOUT", "60"))
        self.config["ocsp_fail_open"] = (
            os.getenv("SNOWFLAKE_OCSP_FAIL_OPEN", "True").lower() == "true"
        )

        # Add authentication (password or private key)
        password = os.getenv("SNOWFLAKE_PASSWORD")
        private_key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")

        if private_key_path:
            # Use private key authentication
            try:
                from cryptography.hazmat.backends import default_backend
                from cryptography.hazmat.primitives import serialization

                # Read private key
                with open(private_key_path, "rb") as key_file:
                    p_key = key_file.read()

                # Decode private key (with optional password)
                key_password = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSWORD")
                password_bytes = key_password.encode() if key_password else None

                private_key = serialization.load_pem_private_key(
                    p_key, password=password_bytes, backend=default_backend()
                )

                # Convert to DER format for Snowflake
                private_key_der = private_key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )

                self.config["private_key"] = private_key_der
                logger.info("✅ Using private key authentication")

            except Exception as e:
                logger.warning(f"⚠️  Could not load private key: {e}")
                if password:
                    self.config["password"] = password
                    logger.info("Falling back to password authentication")
                else:
                    raise ValueError(
                        f"Failed to load private key and no password provided: {e}"
                    )
        elif password:
            # Use password authentication
            self.config["password"] = password
            logger.info("Using password authentication")

        # Add timeout settings for long-running queries
        # network_timeout: Timeout for network operations (default: 3600 seconds = 1 hour)
        # login_timeout: Timeout for login (default: 60 seconds)
        # ocsp_fail_open: Allow connection even if OCSP certificate validation fails
        self.config["network_timeout"] = int(
            os.getenv("SNOWFLAKE_NETWORK_TIMEOUT", "3600")
        )
        self.config["login_timeout"] = int(os.getenv("SNOWFLAKE_LOGIN_TIMEOUT", "60"))
        self.config["ocsp_fail_open"] = (
            os.getenv("SNOWFLAKE_OCSP_FAIL_OPEN", "True").lower() == "true"
        )

        # Secondary database (Raw) - optional
        self.raw_database = os.getenv(
            "SNOWFLAKE_RAW_DATABASE", os.getenv("SNOWFLAKE_DATABASE")
        )

        logger.info("✅ Snowflake Session Pool initialized")
        logger.info(f"   Main Database: {self.config['database']}")
        logger.info(f"   Raw Database: {self.raw_database}")
        logger.info(f"   Network Timeout: {self.config.get('network_timeout', 3600)}s")
        logger.info(f"   OCSP Fail-Open: {self.config.get('ocsp_fail_open', True)}")

    @contextmanager
    def get_connection(
        self, database: Optional[DatabaseType] = None, schema: Optional[str] = None
    ):
        """
        Get a connection from the pool (context manager).

        Args:
            database: Which database to use ("Main" or "Raw", defaults to Main)
            schema: Schema name (defaults to configured schema from .env)

        Yields:
            snowflake.connector.SnowflakeConnection
        """
        # Determine target database
        if database == "Raw":
            target_db = self.raw_database
        else:
            target_db = self.config["database"]

        # Determine target schema
        target_schema = schema or self.config["schema"]

        # Get or create connection (keyed by database+schema)
        conn_key = f"{target_db}.{target_schema}"

        if conn_key not in self._connections or not self._is_connection_valid(
            self._connections[conn_key]
        ):
            logger.info(f"Creating new connection to {target_db}.{target_schema}")
            config = self.config.copy()
            config["database"] = target_db
            config["schema"] = target_schema
            self._connections[conn_key] = snowflake.connector.connect(**config)

        try:
            yield self._connections[conn_key]
        except Exception as e:
            logger.error(f"Connection error: {e}")
            # Invalidate connection on error
            if conn_key in self._connections:
                try:
                    self._connections[conn_key].close()
                except (AttributeError, Exception) as e:
                    logger.debug(f"Error closing invalid connection: {e}")
                del self._connections[conn_key]
            raise

    def _is_connection_valid(
        self, conn: snowflake.connector.SnowflakeConnection
    ) -> bool:
        """Check if connection is still valid."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except (AttributeError, Exception) as e:
            logger.debug(f"Connection validation failed: {e}")
            return False

    def _validate_read_only(self, query: str) -> bool:
        """
        Validate that query is read-only (SELECT only).

        Args:
            query: SQL query string

        Returns:
            bool: True if read-only, False otherwise
        """
        # Remove comments and normalize whitespace
        query_clean = re.sub(r"--.*$", "", query, flags=re.MULTILINE)
        query_clean = re.sub(r"/\*.*?\*/", "", query_clean, flags=re.DOTALL)
        query_clean = query_clean.strip().upper()

        # Check if starts with SELECT or WITH (for CTEs)
        if not (query_clean.startswith("SELECT") or query_clean.startswith("WITH")):
            return False

        # Check for dangerous keywords
        dangerous_keywords = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "REPLACE",
            "MERGE",
            "GRANT",
            "REVOKE",
        ]

        for keyword in dangerous_keywords:
            if re.search(r"\b" + keyword + r"\b", query_clean):
                return False

        return True

    def execute_query(
        self,
        query: str,
        database: Optional[DatabaseType] = None,
        params: Optional[Dict[str, Any]] = None,
        schema: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Execute a read-only SQL query and return results as DataFrame.

        Args:
            query: SQL SELECT query
            database: Target database ("Main" or "Raw")
            params: Optional query parameters for binding
            schema: Target schema (defaults to configured schema from .env)

        Returns:
            pd.DataFrame: Query results

        Raises:
            ValueError: If query is not read-only
            Exception: If query execution fails
        """
        from utils.sql_validation import SQLValidationError, validate_sql_query

        try:
            validate_sql_query(query)
        except SQLValidationError as exc:
            raise ValueError(str(exc)) from exc

        schema_info = f".{schema}" if schema else ""
        logger.info(f"Executing query on {database or 'Main'}{schema_info} database")
        logger.debug(f"Query: {query[:200]}...")

        with self.get_connection(database, schema) as conn:
            try:
                # Execute query
                if params:
                    df = pd.read_sql(query, conn, params=params)
                else:
                    df = pd.read_sql(query, conn)

                logger.info(
                    f"✅ Query returned {len(df)} rows, {len(df.columns)} columns"
                )
                return df

            except Exception as e:
                logger.error(f"❌ Query execution failed: {e}")
                raise

    def execute_query_to_csv(
        self,
        query: str,
        output_path: str,
        database: Optional[DatabaseType] = None,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute query and save results directly to CSV.

        Args:
            query: SQL SELECT query
            output_path: Path to save CSV file
            database: Target database
            schema: Target schema

        Returns:
            dict: Metadata about saved file (rows, size, path)
        """
        df = self.execute_query(query, database, schema=schema)

        # Save to CSV
        df.to_csv(output_path, index=False)

        # Get file stats
        import os

        file_size = os.path.getsize(output_path)

        return {
            "path": output_path,
            "rows": len(df),
            "columns": len(df.columns),
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
        }

    def list_tables(
        self,
        database: Optional[DatabaseType] = None,
        schema: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        List all tables in a schema.

        Args:
            database: Target database
            schema: Schema name (defaults to configured schema)

        Returns:
            pd.DataFrame: Table information
        """
        schema_name = schema or self.config["schema"]

        query = """
        SELECT
            TABLE_CATALOG,
            TABLE_SCHEMA,
            TABLE_NAME,
            TABLE_TYPE,
            ROW_COUNT,
            BYTES,
            CREATED,
            LAST_ALTERED
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
        """

        return self.execute_query(query, database, params=[schema_name])

    def describe_table(
        self,
        table_name: str,
        database: Optional[DatabaseType] = None,
        schema: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get detailed column information for a table.

        Args:
            table_name: Name of the table
            database: Target database
            schema: Schema name

        Returns:
            pd.DataFrame: Column information
        """
        schema_name = schema or self.config["schema"]

        query = """
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            IS_NULLABLE,
            COLUMN_DEFAULT,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """

        return self.execute_query(query, database, params=[schema_name, table_name])

    def get_table_sample(
        self,
        table_name: str,
        limit: int = 100,
        database: Optional[DatabaseType] = None,
        schema: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get sample rows from a table.

        Args:
            table_name: Name of the table
            limit: Number of rows to sample (clamped to 10000)
            database: Target database
            schema: Schema name

        Returns:
            pd.DataFrame: Sample data
        """
        from utils.sql_validation import sanitize_sql_identifier

        schema_name = sanitize_sql_identifier(schema or self.config["schema"])
        safe_table = sanitize_sql_identifier(table_name)
        safe_limit = min(int(limit), 10000)

        query = f"""
        SELECT *
        FROM {schema_name}.{safe_table}
        LIMIT {safe_limit}
        """

        return self.execute_query(query, database)

    def close_all(self):
        """Close all connections in the pool."""
        logger.info("Closing all Snowflake connections...")
        for conn_key, conn in self._connections.items():
            try:
                conn.close()
                logger.info(f"  Closed connection: {conn_key}")
            except Exception as e:
                logger.warning(f"  Error closing {conn_key}: {e}")

        self._connections.clear()
        logger.info("✅ All connections closed")

    def __del__(self):
        """Cleanup on deletion."""
        self.close_all()


# Global session pool instance (singleton pattern)
_global_pool: Optional[SnowflakeSessionPool] = None


def get_session_pool() -> SnowflakeSessionPool:
    """
    Get the global Snowflake session pool instance.

    Returns:
        SnowflakeSessionPool: Global pool instance
    """
    global _global_pool
    if _global_pool is None:
        _global_pool = SnowflakeSessionPool()
    return _global_pool


if __name__ == "__main__":
    # Test connection
    print("🧪 Testing Snowflake Session Pool")
    print("=" * 60)

    try:
        pool = SnowflakeSessionPool()

        # Test query
        df = pool.execute_query(
            "SELECT CURRENT_USER(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
        )
        print("\n✅ Connection successful!")
        print(df)

        # List tables
        print("\n📊 Available tables:")
        tables = pool.list_tables()
        print(f"Found {len(tables)} tables")
        print(tables[["TABLE_NAME", "ROW_COUNT"]].head(10))

        pool.close_all()

    except Exception as e:
        print(f"\n❌ Error: {e}")

    print("=" * 60)
