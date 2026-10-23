import csv
import io
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import snowflake.connector
from cryptography.hazmat.primitives import serialization
import truststore
truststore.inject_into_ssl()

IST = ZoneInfo("Asia/Kolkata")


def get_connection():
    params = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],      # e.g. myorg-myaccount
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    )
    # Optional context
    for env_name, key in [("SNOWFLAKE_ROLE", "role"),
                          ("SNOWFLAKE_DATABASE", "database"),
                          ("SNOWFLAKE_SCHEMA", "schema")]:
        if os.environ.get(env_name):
            params[key] = os.environ[env_name]

    # Key-pair auth (recommended) or password
    if os.environ.get("SNOWFLAKE_PRIVATE_KEY"):
        key = serialization.load_pem_private_key(
            os.environ["SNOWFLAKE_PRIVATE_KEY"].encode(), password=None
        )
        params["private_key"] = key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    else:
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]

    return snowflake.connector.connect(**params)


def run_query(sql):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        headers = [c[0] for c in cur.description]
        rows = cur.fetchall()
        return headers, rows
    finally:
        conn.close()


def build_csv(headers, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode("utf-8")


def upload_to_slack(token, channel_id, filename, csv_bytes, comment):
    auth = {"Authorization": f"Bearer {token}"}

    # Step 1: get an upload URL
    r = requests.post(
        "https://slack.com/api/files.getUploadURLExternal",
        headers=auth,
        data={"filename": filename, "length": len(csv_bytes)},
        timeout=30,
    ).json()
    if not r.get("ok"):
        raise RuntimeError(f"getUploadURLExternal failed: {r}")

    # Step 2: upload the raw bytes
    u = requests.post(r["upload_url"], data=csv_bytes, timeout=60)
    if u.status_code != 200:
        raise RuntimeError(f"Upload failed: {u.status_code} {u.text}")

    # Step 3: finish and share to the channel
    c = requests.post(
        "https://slack.com/api/files.completeUploadExternal",
        headers=auth,
        json={
            "files": [{"id": r["file_id"], "title": filename}],
            "channel_id": channel_id,
            "initial_comment": comment,
        },
        timeout=30,
    ).json()
    if not c.get("ok"):
        raise RuntimeError(f"completeUploadExternal failed: {c}")


def main():
    sql = os.environ["SQL_QUERY"]
    channel_id = os.environ["SLACK_CHANNEL_ID"]
    token = os.environ["SLACK_BOT_TOKEN"]

    headers, rows = run_query(sql)
    csv_bytes = build_csv(headers, rows)

    now = datetime.now(IST)
    filename = f"query_results_{now:%Y%m%d_%H%M}.csv"
    comment = f"*SQL Execution Results* ({len(rows)} rows) - {now:%d %b %Y %I:%M %p} IST"

    upload_to_slack(token, channel_id, filename, csv_bytes, comment)
    print(f"SUCCESS: posted {filename} ({len(rows)} rows)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)