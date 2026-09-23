import boto3
from simulator.cli import main
from telemetry import parse_log


def test_uploads_valid_and_invalid_files(aws, capsys):
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="raw-test")

    main(
        ["--bucket", "raw-test", "--devices", "2", "--procedures", "2", "--seed", "1", "--invalid"]
    )

    keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket="raw-test")["Contents"])
    assert len(keys) == 5
    assert all(k.startswith("raw/") for k in keys)
    valid = [k for k in keys if "invalid-" not in k]
    body = s3.get_object(Bucket="raw-test", Key=valid[0])["Body"].read()
    assert parse_log(body).header.device_id in {"dev-001", "dev-002"}
    assert capsys.readouterr().out.count("raw/") == 5
