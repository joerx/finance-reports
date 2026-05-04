
## Deploying to k3d

Deployment instructions for a locally running k3d cluster. Useful to test the helm chart or other k8s related features. Does not cover how to set up a k3d cluster - to get something closer to a production cluster, check out the [lab-cluster.sh](https://github.com/joerx/lab-cluster.sh) project.

### 1. Pull or build the Docker image

Build locally:


```bash
docker build -t finance-reports-dashboard:latest dashboard/
```

Or pull it directly - Image is published to GHCR on every push to `main`:

```bash
docker pull ghcr.io/<your-github-username>/finance-reports-dashboard:latest
```

### 2. Import the image into k3d

- The k8s control plane clusters may not share the registry credentials of the underlying container engine
- You either need to set up an [image pull secret](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/) or import the image into the clusters registry first:

```bash
# Or from a local build
k3d image import finance-reports-dashboard:latest

# From GHCR
k3d image import ghcr.io/<your-github-username>/finance-reports-dashboard:latest
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
