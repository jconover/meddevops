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


def all_resources(templates, resource_type, props=None):
    found = {}
    for template in templates.values():
        found |= template.find_resources(resource_type, props or {})
    return found


def test_lambda_is_arm64_container_in_vpc(templates):
    templates["ingest"].has_resource_properties(
        "AWS::Lambda::Function",
        {
            "PackageType": "Image",
            "Architectures": ["arm64"],
            "VpcConfig": Match.any_value(),
            "Environment": {"Variables": {"DB_SECRET_ARN": Match.any_value()}},
        },
    )


def test_lambda_reports_batch_item_failures(templates):
    templates["ingest"].has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {"FunctionResponseTypes": ["ReportBatchItemFailures"], "BatchSize": 10},
    )


def test_ingest_concurrency_is_limited(templates):
    templates["ingest"].has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {"ScalingConfig": {"MaximumConcurrency": 2}},
    )


def test_alb_accepts_only_allowed_cidr(templates):
    templates["api"].has_resource_properties(
        "AWS::EC2::SecurityGroup",
        {
            "GroupDescription": "ALB security group",
            "SecurityGroupIngress": [
                Match.object_like({"CidrIp": TEST_CIDR, "FromPort": 80, "ToPort": 80})
            ],
        },
    )


def test_service_accepts_only_alb(templates):
    alb_sg = next(
        iter(
            templates["api"].find_resources(
                "AWS::EC2::SecurityGroup",
                {"Properties": {"GroupDescription": "ALB security group"}},
            )
        )
    )
    ingress = all_resources(
        templates, "AWS::EC2::SecurityGroupIngress", {"Properties": {"FromPort": 8000}}
    )
    assert len(ingress) == 1
    rule = next(iter(ingress.values()))["Properties"]
    assert rule["SourceSecurityGroupId"] == {"Fn::GetAtt": [alb_sg, "GroupId"]}


def test_database_reachable_only_from_api_and_ingest(templates):
    """RDS's default port is a CloudFormation token, so match the rules by description."""
    ingress = all_resources(
        templates,
        "AWS::EC2::SecurityGroupIngress",
        {"Properties": {"Description": Match.string_like_regexp("to postgres")}},
    )
    assert len(ingress) == 2
    assert all("SourceSecurityGroupId" in r["Properties"] for r in ingress.values())


def test_fargate_task_is_arm64_with_db_secrets(templates):
    templates["api"].has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "RuntimePlatform": {"CpuArchitecture": "ARM64", "OperatingSystemFamily": "LINUX"},
            "ContainerDefinitions": [
                Match.object_like(
                    {"Secrets": Match.array_with([Match.object_like({"Name": "PGPASSWORD"})])}
                )
            ],
        },
    )


def test_api_url_output(templates):
    templates["api"].has_output("ApiUrl", {})


def test_ingest_s3_access_is_scoped_no_delete(templates):
    """Lambda's S3 grant must be read (raw/*) + put (quarantine/*) only, never delete."""
    policies = templates["ingest"].find_resources(
        "AWS::IAM::Policy", {"Properties": {"PolicyName": Match.string_like_regexp("IngestFn")}}
    )
    assert len(policies) == 1
    statements = next(iter(policies.values()))["Properties"]["PolicyDocument"]["Statement"]

    actions = []
    for statement in statements:
        action = statement["Action"]
        actions.extend(action if isinstance(action, list) else [action])
    assert not any(a.startswith("s3:DeleteObject") for a in actions)

    def key_suffixes(resource):
        resources = resource if isinstance(resource, list) else [resource]
        suffixes = []
        for r in resources:
            if isinstance(r, dict) and "Fn::Join" in r:
                suffixes.append("".join(p for p in r["Fn::Join"][1] if isinstance(p, str)))
        return suffixes

    suffixes = [s for statement in statements for s in key_suffixes(statement["Resource"])]
    assert "/raw/*" in suffixes
    assert "/quarantine/*" in suffixes
