import os
import duckdb

# Load credentials from .env
def load_env(path=".env"):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

load_env()

BUCKET   = "dev-finance-reports-cfvd"
ENDPOINT = "eu-central-1.linodeobjects.com"
REGION   = "eu-central-1"

con = duckdb.connect()
con.install_extension("httpfs")
con.load_extension("httpfs")

con.execute(f"""
    CREATE SECRET linode_s3 (
        TYPE s3,
        KEY_ID     '{os.environ["AWS_ACCESS_KEY_ID"]}',
        SECRET     '{os.environ["AWS_SECRET_ACCESS_KEY"]}',
        ENDPOINT   '{ENDPOINT}',
        REGION     '{REGION}',
        URL_STYLE  'path'
    )
""")

parquet_url = f"s3://{BUCKET}/expenses/expenses_2026-Q1.parquet"

print("=== Total spend by account ===")
con.sql(f"""
    SELECT account, ROUND(SUM(amount), 2) AS total
    FROM '{parquet_url}'
    GROUP BY account
    ORDER BY total DESC
""").show()

print("\n=== Top 10 transactions ===")
con.sql(f"""
    SELECT date, account, description, amount
    FROM '{parquet_url}'
    ORDER BY amount DESC
    LIMIT 10
""").show()
