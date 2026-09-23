"""FastAPI container on ECS Fargate behind an internet-facing ALB."""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_logs as logs
from constructs import Construct

from infra.paths import REPO_ROOT
from infra.stacks.data import DataStack

API_PORT = 8000


class ApiStack(Stack):
    """Read-only REST API. The ALB accepts traffic only from allowed_cidr."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        data: DataStack,
        allowed_cidr: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        task = ecs.FargateTaskDefinition(
            self,
            "Task",
            cpu=256,
            memory_limit_mib=512,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.ARM64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
        )
        secret = data.db_secret
        task.add_container(
            "api",
            image=ecs.ContainerImage.from_asset(
                str(REPO_ROOT),
                file="services/api/Dockerfile",
                platform=ecr_assets.Platform.LINUX_ARM64,
            ),
            port_mappings=[ecs.PortMapping(container_port=API_PORT)],
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="api",
                log_group=logs.LogGroup(
                    self,
                    "ApiLogs",
                    retention=logs.RetentionDays.ONE_WEEK,
                    removal_policy=RemovalPolicy.DESTROY,
                ),
            ),
            secrets={
                "PGHOST": ecs.Secret.from_secrets_manager(secret, "host"),
                "PGPORT": ecs.Secret.from_secrets_manager(secret, "port"),
                "PGDATABASE": ecs.Secret.from_secrets_manager(secret, "dbname"),
                "PGUSER": ecs.Secret.from_secrets_manager(secret, "username"),
                "PGPASSWORD": ecs.Secret.from_secrets_manager(secret, "password"),
            },
        )

        service_sg = ec2.SecurityGroup(
            self, "ServiceSg", vpc=vpc, description="API service security group"
        )
        service = ecs.FargateService(
            self,
            "Service",
            cluster=ecs.Cluster(self, "Cluster", vpc=vpc),
            task_definition=task,
            desired_count=1,
            security_groups=[service_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )
        # See ingest.py for why this rule is created directly here rather than via
        # data.db.connections.allow_default_port_from (would cycle DataStack <-> ApiStack).
        ec2.CfnSecurityGroupIngress(
            self,
            "DbIngressFromApi",
            ip_protocol="tcp",
            from_port=data.db.instance_endpoint.port,
            to_port=data.db.instance_endpoint.port,
            group_id=data.db.connections.security_groups[0].security_group_id,
            source_security_group_id=service_sg.security_group_id,
            description="api service to postgres",
        )

        alb_sg = ec2.SecurityGroup(
            self, "AlbSg", vpc=vpc, description="ALB security group", allow_all_outbound=False
        )
        alb_sg.add_ingress_rule(ec2.Peer.ipv4(allowed_cidr), ec2.Port.tcp(80), "operator access")
        alb = elbv2.ApplicationLoadBalancer(
            self, "Alb", vpc=vpc, internet_facing=True, security_group=alb_sg
        )
        listener = alb.add_listener("Http", port=80, open=False)
        listener.add_targets(
            "Api",
            port=API_PORT,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[service],
            health_check=elbv2.HealthCheck(path="/health", interval=Duration.seconds(30)),
            deregistration_delay=Duration.seconds(10),
        )

        CfnOutput(self, "ApiUrl", value=f"http://{alb.load_balancer_dns_name}")
