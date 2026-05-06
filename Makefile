VERSION ?= v0.1.0-$(shell git rev-parse --short HEAD)
IMAGE   ?= ghcr.io/joerx/finance-reports-dashboard:$(VERSION)

# Treat any version with a pre-release suffix (hyphen) as a pre-release
PRERELEASE := $(if $(findstring -,$(VERSION)),--prerelease,"")

.PHONY: docker-build
docker-build:
	docker build -t $(IMAGE) -f dashboard/Dockerfile .

.PHONY: docker-run
docker-run: docker-build
	docker run -p 8501:8501 --env-file .env ghcr.io/joerx/finance-reports-dashboard:latest

.PHONY: release
release: _require-token
	gh release create $(VERSION) $(PRERELEASE) --title "Release $(VERSION)" --target main --generate-notes

.PHONY: _require-token
_require-token:
ifndef GITHUB_TOKEN
	$(error GITHUB_TOKEN is not set. Export it before running make release)
endif
