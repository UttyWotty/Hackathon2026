"""Central Snowflake configuration read once from environment variables.

All Snowflake connection parameters are declared here as module-level constants
so credentials are read in exactly one place. Other modules import from here
rather than calling os.getenv inline.
"""

import os

SNOWFLAKE_ACCOUNT = os.getenv("SNOWFLAKE_ACCOUNT", "")
SNOWFLAKE_USER = os.getenv("SNOWFLAKE_USER", "")
SNOWFLAKE_PASSWORD = os.getenv("SNOWFLAKE_PASSWORD", "")
SNOWFLAKE_WAREHOUSE = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
SNOWFLAKE_DATABASE = os.getenv("SNOWFLAKE_DATABASE", "DEMO")
SNOWFLAKE_SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")
SNOWFLAKE_ROLE = os.getenv("SNOWFLAKE_ROLE", "")
SNOWFLAKE_PRIVATE_KEY_PATH = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", "")
SNOWFLAKE_PRIVATE_KEY_PASSWORD = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSWORD", "")
SNOWFLAKE_NETWORK_TIMEOUT = int(os.getenv("SNOWFLAKE_NETWORK_TIMEOUT", "3600"))
SNOWFLAKE_LOGIN_TIMEOUT = int(os.getenv("SNOWFLAKE_LOGIN_TIMEOUT", "60"))
SNOWFLAKE_OCSP_FAIL_OPEN = (
    os.getenv("SNOWFLAKE_OCSP_FAIL_OPEN", "true").lower() == "true"
)
SNOWFLAKE_INSECURE_MODE = (
    os.getenv("SNOWFLAKE_INSECURE_MODE", "false").lower() == "true"
)
