"""Container-image Lambda that consumes the ingest queue."""

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as event_sources
from aws_cdk import aws_logs as logs
from constructs import Construct

from infra.paths import REPO_ROOT
from infra.stacks.data import DataStack


class IngestStack(Stack):
    """Validate uploaded logs and write them to Postgres."""

    def __init__(
        self, scope: Construct, construct_id: str, *, vpc: ec2.IVpc, data: DataStack, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        log_group = logs.LogGroup(
            self,
            "IngestLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        fn = lambda_.DockerImageFunction(
            self,
            "IngestFn",
            code=lambda_.DockerImageCode.from_image_asset(
                str(REPO_ROOT),
                file="services/ingest/Dockerfile",
                platform=ecr_assets.Platform.LINUX_ARM64,
            ),
            architecture=lambda_.Architecture.ARM_64,
            memory_size=512,
            timeout=Duration.seconds(60),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            environment={"DB_SECRET_ARN": data.db_secret.secret_arn},
            log_group=log_group,
        )
        data.db_secret.grant_read(fn)
        data.bucket.grant_read(fn, "raw/*")
        data.bucket.grant_put(fn, "quarantine/*")
        # Adding the ingress rule via data.db.connections would make DataStack depend on
        # IngestStack (a cycle), since the rule's source is this stack's Lambda security
        # group. Create the rule here instead, referencing the DB's security group id.
        ec2.CfnSecurityGroupIngress(
            self,
            "DbIngressFromIngest",
            ip_protocol="tcp",
            from_port=data.db.instance_endpoint.port,
            to_port=data.db.instance_endpoint.port,
            group_id=data.db.connections.security_groups[0].security_group_id,
            source_security_group_id=fn.connections.security_groups[0].security_group_id,
            description="ingest lambda to postgres",
        )
        fn.add_event_source(
            event_sources.SqsEventSource(
                data.queue,
                batch_size=10,
                report_batch_item_failures=True,
                max_concurrency=2,
            )
        )
