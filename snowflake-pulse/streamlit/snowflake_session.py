import streamlit as st
from snowflake.snowpark import Session


def get_session():
    """
    Use the native get_active_session() when running inside Snowflake,
    otherwise create a Snowpark session from local Streamlit secrets.
    """
    try:
        from snowflake.snowpark.context import get_active_session

        return get_active_session()
    except Exception:
        if "snowflake" not in st.secrets:
            st.error(
                "Snowflake connection is not configured.\n\n"
                "Add a [snowflake] section to your .streamlit/secrets.toml file "
                "with account, user, password, role, warehouse, database, and schema."
            )
            st.stop()

        connection_parameters = dict(st.secrets["snowflake"])
        return Session.builder.configs(connection_parameters).create()

