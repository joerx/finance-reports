# Expense Dashboard

A Streamlit dashboard that reads quarterly expense data from Parquet files stored in Linode Object Storage (S3-compatible) and visualises spend by category.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [k3d](https://k3d.io/) with a running cluster
- `kubectl` configured to point at the cluster
- [Helm 3](https://helm.sh/docs/intro/install/)
- A `.env` file in the project root containing S3 credentials:

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Running locally

```bash
# Install dependencies (first time only)
python -m venv venv
venv/bin/pip install -r dashboard/requirements.txt

# Run
source .env
streamlit run dashboard/app.py
```

The app is available at http://localhost:8501.

## Deploying to k3d

### 1. Pull or build the Docker image

The image is published to GHCR on every push to `main`. Pull it directly:

```bash
docker pull ghcr.io/<your-github-username>/expense-dashboard:latest
```

Or build it locally if you are working off an unpublished branch:

```bash
docker build -t expense-dashboard:latest dashboard/
```

### 2. Import the image into k3d

k3d clusters cannot pull images directly — they must be imported into the cluster's internal registry first:

```bash
# From GHCR
k3d image import ghcr.io/<your-github-username>/expense-dashboard:latest

# Or from a local build
k3d image import expense-dashboard:latest
```

> Re-run this step every time you update the image.

When using the GHCR image, set the repository in the Helm values:

```bash
helm install expense-dashboard helm/expense-dashboard \
  --set image.repository=ghcr.io/<your-github-username>/expense-dashboard \
  --set image.pullPolicy=IfNotPresent
```

### 3. Create the Kubernetes Secret

The app reads S3 credentials from environment variables injected by an existing Secret. Create it from your `.env` file:

```bash
kubectl create secret generic expense-dashboard-s3 \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Install with Helm

```bash
helm install expense-dashboard helm/expense-dashboard
```

The chart uses `expense-dashboard-s3` as the default secret name. If you used a different name, override it:

```bash
helm install expense-dashboard helm/expense-dashboard \
  --set secretName=my-secret
```

### 5. Get the external address

k3d's built-in load balancer assigns an external IP automatically:

```bash
kubectl get svc expense-dashboard
```

Once `EXTERNAL-IP` is populated, open http://\<EXTERNAL-IP\>:8501 in your browser.

If the IP stays in `<pending>`, use port-forward as an alternative:

```bash
kubectl port-forward svc/expense-dashboard 8501:8501
```

Then open http://localhost:8501.

---

## Updating the app

Push to `main` — the GitHub Actions workflow builds and publishes the image to GHCR automatically. Then pull and reimport:

```bash
docker pull ghcr.io/<your-github-username>/expense-dashboard:latest
k3d image import ghcr.io/<your-github-username>/expense-dashboard:latest
helm upgrade expense-dashboard helm/expense-dashboard
```

For local iteration without pushing:

```bash
docker build -t expense-dashboard:latest dashboard/
k3d image import expense-dashboard:latest
helm upgrade expense-dashboard helm/expense-dashboard
```

---

## Uploading expense data

Expense data is extracted from a GnuCash database and uploaded to S3 as Parquet using `upload.sh`:

```bash
./upload.sh <db-file> <quarter>

# Example
./upload.sh 2026.gnucash 2026-Q1
```

The quarter format is `YYYY-QN` (e.g. `2026-Q1`, `2026-Q4`). The file is uploaded to:

```
s3://dev-finance-reports-cfvd/expenses/expenses_<quarter>.parquet
```

The dashboard quarter selector must match a file that has been uploaded.
