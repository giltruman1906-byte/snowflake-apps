import os
from pathlib import Path

import streamlit as st
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from snowflake.snowpark import Session


def _load_private_key(key_path: str) -> bytes:
    """Load an RSA private key from a .p8 file and return DER bytes."""
    key_bytes = Path(key_path).read_bytes()
    private_key = serialization.load_pem_private_key(
        key_bytes, password=None, backend=default_backend()
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _get_params_from_secrets():
    try:
        conf = st.secrets["snowflake"]
    except Exception:
        return None

    keys = [
        "account",
        "user",
        "role",
        "warehouse",
        "database",
        "schema",
    ]
    params = {k: conf.get(k) for k in keys}

    rsa_key_path = conf.get("rsa_key_path")
    if rsa_key_path:
        params["private_key"] = _load_private_key(rsa_key_path)
    else:
        params["password"] = conf.get("password")

    return params


def _get_params_from_env():
    params = {
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "user": os.getenv("SNOWFLAKE_USER"),
        "role": os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA"),
    }

    rsa_key_path = os.getenv("SNOWFLAKE_RSA_KEY_PATH")
    if rsa_key_path:
        params["private_key"] = _load_private_key(rsa_key_path)
    else:
        params["password"] = os.getenv("SNOWFLAKE_PASSWORD")

    return params


def get_session() -> Session:
    params = _get_params_from_secrets() or _get_params_from_env()

    required = ["account", "user", "role", "warehouse", "database", "schema"]
    missing = [k for k in required if not params.get(k)]

    has_auth = params.get("private_key") or params.get("password")
    if not has_auth:
        missing.append("SNOWFLAKE_RSA_KEY_PATH or SNOWFLAKE_PASSWORD")

    if missing:
        st.error(
            "Snowflake configuration is incomplete. Missing: "
            + ", ".join(missing)
        )
        st.stop()

    return Session.builder.configs(params).create()
