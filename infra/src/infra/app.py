"""CDK entry point. Deploy with: cdk deploy --all -c allowedCidr=<your-ip>/32"""

import aws_cdk as cdk

from infra.stacks.data import DataStack
from infra.stacks.network import NetworkStack


def build(app: cdk.App, allowed_cidr: str) -> dict[str, cdk.Stack]:
    """Create all stacks in dependency order."""
    network = NetworkStack(app, "Telemetry-Network")
    data = DataStack(app, "Telemetry-Data", vpc=network.vpc)
    cdk.Tags.of(app).add("project", "meddevops")
    return {"network": network, "data": data}


def main() -> None:
    app = cdk.App()
    allowed_cidr = app.node.try_get_context("allowedCidr")
    if not allowed_cidr:
        raise SystemExit("pass -c allowedCidr=<your-ip>/32")
    build(app, allowed_cidr)
    app.synth()


if __name__ == "__main__":
    main()
