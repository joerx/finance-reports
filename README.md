# Expense Dashboard

A Streamlit dashboard that reads quarterly expense data from Parquet files stored in Linode Object Storage (S3-compatible) and visualises spend by category.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [k3d](https://k3d.io/) with a running cluster
- `kubectl` configured to point at the cluster
- [Helm 3](https://helm.sh/docs/intro/install/)
- A `.env` file in the project root containing S3 credentials:

### Environment

Create make sure these are set in your shell or create a `.env` file in your working directory:

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=...
S3_REGION=eu-central
S3_ENDPOINT=eu-central-1.linodeobjects.com
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

The app will be available at http://localhost:8501.

## Deploying to k3d

### 1. Pull or build the Docker image

The image is published to GHCR on every push to `main`. Pull it directly:

```bash
docker pull ghcr.io/<your-github-username>/finance-reports-dashboard:latest
```

Or build it locally if you are working off an unpublished branch:

```bash
docker build -t finance-reports-dashboard:latest dashboard/
```

### 2. Import the image into k3d

k3d clusters cannot pull images directly — they must be imported into the cluster's internal registry first:

```bash
# From GHCR
k3d image import ghcr.io/<your-github-username>/finance-reports-dashboard:latest

# Or from a local build
k3d image import finance-reports-dashboard:latest
```

> Re-run this step every time you update the image.

When using the GHCR image, set the repository in the Helm values:

```bash
helm install finance-reports-dashboard helm/finance-reports-dashboard \
  --set image.repository=ghcr.io/<your-github-username>/finance-reports-dashboard \
  --set image.pullPolicy=IfNotPresent
```

### 3. Install with Helm

```bash
helm upgrade --install --namespace finance-reports --create-namespace finance-reports-dashboard charts/dashboard
```

The chart uses `finance-reports-dashboard-s3` as the default secret name. If you used a different name, override it:

```bash
helm install finance-reports-dashboard helm/finance-reports-dashboard \
  --set secretName=my-secret
```

### 4. Create the Kubernetes Secret

The app reads S3 credentials from environment variables injected by an existing Secret. Create it from your `.env` file:

```bash
kubectl create secret generic finance-reports-s3 \
  -n finance-reports \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 5. Get the external address

k3d's built-in load balancer assigns an external IP automatically:

```bash
kubectl get svc finance-reports-dashboard
```

Once `EXTERNAL-IP` is populated, open http://\<EXTERNAL-IP\>:8501 in your browser.

If the IP stays in `<pending>`, use port-forward as an alternative:

```bash
kubectl port-forward svc/finance-reports-dashboard 8501:8501
```

Then open http://localhost:8501.

---

## Updating the app

Push to `main` — the GitHub Actions workflow builds and publishes the image to GHCR automatically. Then pull and reimport:

```bash
docker pull ghcr.io/<your-github-username>/finance-reports-dashboard:latest
k3d image import ghcr.io/<your-github-username>/finance-reports-dashboard:latest
helm upgrade finance-reports-dashboard helm/finance-reports-dashboard
```

For local iteration without pushing:

```bash
docker build -t finance-reports-dashboard:latest dashboard/
k3d image import finance-reports-dashboard:latest
helm upgrade finance-reports-dashboard helm/finance-reports-dashboard
```

---

## Loading Data

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
