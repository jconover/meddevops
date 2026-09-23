# meddevops

A personal learning project: an AWS data pipeline for synthetic medical device telemetry.

Devices upload procedure logs to S3. An SQS-triggered Lambda validates them and writes them
to RDS Postgres. A FastAPI service on ECS Fargate, behind an ALB, serves them over REST.
All infrastructure is AWS CDK (Python). All data is synthetic.

```
simulator -> S3 (raw/) -> SQS (+DLQ) -> Lambda -> RDS Postgres <- FastAPI on Fargate <- ALB
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/), Docker, Node.js 22+, AWS CLI v2 with credentials configured

## Develop

```bash
uv sync --all-packages
uv run pytest          # needs Docker running (tests use a real Postgres container)
uv run ruff check
```

## Deploy

```bash
cd infra
npx aws-cdk@2.1142.0 bootstrap                      # once per account/region
npx aws-cdk@2.1142.0 deploy --all -c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32
cd ..
uv run python scripts/smoke_test.py
```

Load sample data:

```bash
uv run simulator --bucket <BucketName output> --devices 5 --procedures 4 --invalid
```

The API docs are at `<ApiUrl output>/docs`. Only the IP passed in `allowedCidr` can reach it.

## Tear down

Running cost is roughly $70/month (NAT gateway, ALB, RDS, Fargate). Destroy between sessions:

```bash
cd infra && npx aws-cdk@2.1142.0 destroy --all --force -c allowedCidr=0.0.0.0/32
```

This removes every stack resource, including data. The CDK bootstrap stack remains.

## Layout

| Path | Purpose |
|---|---|
| `packages/telemetry` | Shared log models and parsing |
| `simulator` | CLI that generates and uploads logs |
| `services/ingest` | Lambda: validate, store, quarantine |
| `services/api` | FastAPI service and SQL migrations |
| `infra` | CDK stacks: Network, Data, Ingest, Api |
| `scripts/smoke_test.py` | End-to-end check against a deployment |
