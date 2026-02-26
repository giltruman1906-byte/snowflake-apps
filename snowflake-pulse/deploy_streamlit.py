"""
Deploy Snowflake Pulse Streamlit app to Snowflake (Streamlit in Snowflake).

Usage:
    source .env && python deploy_streamlit.py
"""

import os
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from snowflake.snowpark import Session


def load_private_key(key_path: str) -> bytes:
    key_bytes = Path(key_path).read_bytes()
    private_key = serialization.load_pem_private_key(
        key_bytes, password=None, backend=default_backend()
    )
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def main():
    # ── Connect ──
    print("Connecting to Snowflake...")
    session = Session.builder.configs({
        "account": os.getenv("SNOWFLAKE_ACCOUNT"),
        "user": os.getenv("SNOWFLAKE_USER"),
        "private_key": load_private_key(os.getenv("SNOWFLAKE_RSA_KEY_PATH")),
        "role": os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "schema": "core",
    }).create()

    user = session.sql("SELECT CURRENT_USER()").collect()[0][0]
    print(f"  Connected as {user}")

    # ── Step 1: Create stage ──
    print("\n1. Creating stage...")
    session.sql("""
        CREATE STAGE IF NOT EXISTS SANDBOX.core.pulse_streamlit_stage
            DIRECTORY = (ENABLE = TRUE)
    """).collect()
    print("  Stage: SANDBOX.core.pulse_streamlit_stage")

    # ── Step 2: Upload files ──
    print("\n2. Uploading Streamlit files...")

    files_to_upload = [
        ("streamlit/Home.py", "@SANDBOX.core.pulse_streamlit_stage/"),
        ("streamlit/pages/1_Task_Detail.py", "@SANDBOX.core.pulse_streamlit_stage/pages/"),
        ("streamlit/pages/2_Run_Detail.py", "@SANDBOX.core.pulse_streamlit_stage/pages/"),
        ("streamlit/pages/3_Settings.py", "@SANDBOX.core.pulse_streamlit_stage/pages/"),
        ("streamlit/pages/4_Monthly_Analysis.py", "@SANDBOX.core.pulse_streamlit_stage/pages/"),
    ]

    for local_path, stage_path in files_to_upload:
        abs_path = str(Path(local_path).resolve())
        result = session.file.put(
            abs_path,
            stage_path,
            auto_compress=False,
            overwrite=True,
        )
        status = result[0].status
        print(f"  {local_path} -> {stage_path}  [{status}]")

    # ── Step 3: Verify uploads ──
    print("\n3. Verifying stage contents...")
    files = session.sql("LIST @SANDBOX.core.pulse_streamlit_stage").collect()
    for f in files:
        print(f"  {f['name']}")

    # ── Step 4: Create Streamlit app ──
    print("\n4. Creating Streamlit app...")
    session.sql("""
        CREATE OR REPLACE STREAMLIT SANDBOX.core.pulse_app
            ROOT_LOCATION  = '@SANDBOX.core.pulse_streamlit_stage'
            MAIN_FILE      = 'Home.py'
            QUERY_WAREHOUSE = COMPUTE_WH
    """).collect()
    print("  Created: SANDBOX.core.pulse_app")

    # ── Done ──
    print("\n" + "=" * 50)
    print("Deployment complete!")
    print("Open Snowsight -> Projects -> Streamlit -> PULSE_APP")
    print("=" * 50)

    session.close()


if __name__ == "__main__":
    main()
