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

Upload data only after `cdk deploy` finishes: the API applies database migrations on startup.

Look up the stack outputs:

```bash
BUCKET=$(aws cloudformation describe-stacks --stack-name Telemetry-Data --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text)
API_URL=$(aws cloudformation describe-stacks --stack-name Telemetry-Api --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
```

Load sample data:

```bash
uv run simulator --bucket "$BUCKET" --devices 5 --procedures 4 --invalid
```

The API docs are at `$API_URL/docs`. Only the IP passed in `allowedCidr` can reach it.

## Tear down

Running cost is roughly $70/month (NAT gateway, ALB, RDS, Fargate). Destroy between sessions:

```bash
cd infra && npx aws-cdk@2.1142.0 destroy --all --force -c allowedCidr=0.0.0.0/32
```

This removes every stack resource, including data. The CDK bootstrap stack remains.

Confirm nothing billable is left (each should print `[]`):

```bash
aws rds describe-db-instances --query "DBInstances[].DBInstanceIdentifier"
aws ec2 describe-nat-gateways --filter Name=state,Values=available --query "NatGateways[].NatGatewayId"
aws elbv2 describe-load-balancers --query "LoadBalancers[].LoadBalancerName"
```

CDK custom-resource Lambdas also leave behind small `/aws/lambda/Telemetry-Data-*` log
groups. List them with:

```bash
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/Telemetry- --query "logGroups[].logGroupName"
```

## Layout

| Path | Purpose |
|---|---|
| `packages/telemetry` | Shared log models and parsing |
| `simulator` | CLI that generates and uploads logs |
| `services/ingest` | Lambda: validate, store, quarantine |
| `services/api` | FastAPI service and SQL migrations |
| `infra` | CDK stacks: Network, Data, Ingest, Api |
| `scripts/smoke_test.py` | End-to-end check against a deployment |
