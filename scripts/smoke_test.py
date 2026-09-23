"""End-to-end check against the deployed stacks: one valid and one invalid upload."""

import random
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

import boto3
import httpx2
from simulator.cli import upload
from simulator.generate import INVALID_LOG, generate_procedure, invalid_key, object_key
from telemetry import dump_log


def stack_output(cf, stack: str, key: str) -> str:
    outputs = cf.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    return next(o["OutputValue"] for o in outputs if o["OutputKey"] == key)


def wait_for(check: Callable[[], bool], what: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            print(f"ok: {what}")
            return
        time.sleep(5)
    sys.exit(f"timed out waiting for: {what}")


def main() -> None:
    cf = boto3.client("cloudformation")
    s3 = boto3.client("s3")
    bucket = stack_output(cf, "Telemetry-Data", "BucketName")
    api = stack_output(cf, "Telemetry-Api", "ApiUrl")

    rng = random.Random()
    now = datetime.now(UTC)
    log = generate_procedure("dev-smoke", now, rng, n_events=10)
    upload(s3, bucket, object_key(log.header), dump_log(log).encode())
    bad_key = invalid_key(now, rng)
    upload(s3, bucket, bad_key, INVALID_LOG)

    wait_for(lambda: httpx2.get(f"{api}/health").status_code == 200, "api healthy")
    wait_for(
        lambda: httpx2.get(f"{api}/procedures/{log.header.procedure_id}").status_code == 200,
        "valid log ingested",
    )
    wait_for(
        lambda: (
            bad_key
            in {f["s3_key"] for f in httpx2.get(f"{api}/ingest/files?status=quarantined").json()}
        ),
        "invalid log quarantined",
    )
    print("smoke test passed")


if __name__ == "__main__":
    main()
