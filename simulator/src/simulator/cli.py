"""Command line entry point: upload synthetic procedure logs to S3."""

import argparse
import random
from datetime import UTC, datetime, timedelta

import boto3
from telemetry import dump_log

from simulator.generate import INVALID_LOG, generate_procedure, invalid_key, object_key


def upload(s3, bucket: str, key: str, body: bytes) -> None:
    """Upload one log file."""
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/x-ndjson")


def main(argv: list[str] | None = None) -> None:
    """Generate logs for several devices and upload them."""
    parser = argparse.ArgumentParser(prog="simulator", description=__doc__)
    parser.add_argument("--bucket", required=True, help="raw bucket name")
    parser.add_argument("--devices", type=int, default=3)
    parser.add_argument("--procedures", type=int, default=2, help="procedures per device")
    parser.add_argument("--seed", type=int, help="random seed for repeatable output")
    parser.add_argument("--invalid", action="store_true", help="also upload one invalid file")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    s3 = boto3.client("s3")
    now = datetime.now(UTC)
    for d in range(1, args.devices + 1):
        for _ in range(args.procedures):
            started = now - timedelta(hours=rng.randint(1, 72))
            log = generate_procedure(f"dev-{d:03d}", started, rng)
            key = object_key(log.header)
            upload(s3, args.bucket, key, dump_log(log).encode())
            print(key)
    if args.invalid:
        key = invalid_key(now, rng)
        upload(s3, args.bucket, key, INVALID_LOG)
        print(key)
