import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from infra.app import build

TEST_CIDR = "203.0.113.10/32"


@pytest.fixture(scope="module")
def templates() -> dict[str, Template]:
    stacks = build(cdk.App(), allowed_cidr=TEST_CIDR)
    return {name: Template.from_stack(stack) for name, stack in stacks.items()}


def test_single_nat_gateway(templates):
    templates["network"].resource_count_is("AWS::EC2::NatGateway", 1)


def test_database_is_private_and_encrypted(templates):
    templates["data"].has_resource_properties(
        "AWS::RDS::DBInstance",
        {"PubliclyAccessible": False, "StorageEncrypted": True, "DBInstanceClass": "db.t4g.micro"},
    )


def test_bucket_blocks_public_access(templates):
    templates["data"].has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_queue_has_dead_letter_queue(templates):
    templates["data"].has_resource_properties(
        "AWS::SQS::Queue",
        {"RedrivePolicy": {"maxReceiveCount": 3, "deadLetterTargetArn": Match.any_value()}},
    )


def test_bucket_notifies_queue_for_raw_prefix_only(templates):
    templates["data"].has_resource_properties(
        "Custom::S3BucketNotifications",
        {
            "NotificationConfiguration": {
                "QueueConfigurations": [
                    Match.object_like(
                        {"Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "raw/"}]}}}
                    )
                ]
            }
        },
    )
