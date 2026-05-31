# Expense Dashboard

A Streamlit dashboard that reads quarterly expense data from Parquet files stored in Linode Object Storage (S3-compatible) and visualises spend by category.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [k3d](https://k3d.io/) with a running cluster
- `kubectl` configured to point at the cluster
- [Helm 3](https://helm.sh/docs/intro/install/)


## Credentials

- Generate Linode OSS credentials:

```sh
linode object-storage keys-create --label "${USER}@${HOSTNAME}-cli"
```

- Use the credentials generated above with `aws configure --profile linode`
- To use Linode OSS with the `aws` CLI, use the `--endpoint-url` parameter:

```sh
aws --profile linode --endpoint-url https://eu-central-1.linodeobjects.com s3 ls
```

- To avoid having to use `--endpoint-url` each time, update `~/.aws/config`:

```sh
[profile linode]
region = eu-central-1
endpoint_url = https://eu-central-1.linodeobjects.com
```

- A `.env` file in the project root containing S3 credentials:


### Python

```bash
# Install dependencies (first time only)
python -m venv venv
venv/bin/pip install -r requirements.txt
```

### Environment

- Create make sure these are set in your shell or create a `.env` file in your working directory
- You can skip the `AWS_` vars if you have the AWS SDK set up with a different authentication method

```sh
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=...
S3_REGION=eu-central
S3_ENDPOINT=eu-central-1.linodeobjects.com
```

## Data Extraction

Expense data is extracted from a GnuCash database and uploaded to S3 as Parquet using `upload.sh`:

```bash
./scripts/sync.sh <db-file> <quarter>

# Example
./scripts/sync.sh ~/Downloads/2026.sqlite.gnucash 2026-Q2
```

The quarter format is `YYYY-QN` (e.g. `2026-Q1`, `2026-Q4`). The file is uploaded to:

```
s3://dev-finance-reports-cfvd/expenses/expenses_<quarter>.parquet
```

The dashboard quarter selector must match a file that has been uploaded.

## Querying data directly with DuckDB

The `.duckdbrc` in the project root pre-loads the S3 secret and creates a `transactions` view over the full parquet dataset. Use the wrapper script so that credentials from `.env` are picked up automatically:

```bash
./scripts/duckdb.sh                   # interactive shell
./scripts/duckdb.sh -c "SELECT ..."   # one-shot query
```

Once in the shell, the `transactions` view is ready:

```sql
-- Spend by account type
SELECT account_type, round(sum(gbp_value), 2) AS gbp
FROM transactions
GROUP BY 1 ORDER BY 2 DESC;

-- Monthly expenses
SELECT year, month, round(sum(gbp_value), 2) AS gbp
FROM transactions
WHERE account_type = 'expenses'
GROUP BY 1, 2 ORDER BY 1, 2;
```

The view uses hive partitioning, so filtering on `year` and `month` is efficient — DuckDB prunes irrelevant files without scanning them.

## Dashboard

```
streamlit run dashboard/app.py
```

The app will be available at http://localhost:8501.

## Building

```bash
docker build -t finance-reports-dashboard:latest dashboard/
```

## Deployment

### k3d

See [docs/k3d.md](./docs/k3d.md)
  