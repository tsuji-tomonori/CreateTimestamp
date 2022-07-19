import aws_cdk as cdk
from aws_cdk import Tags

from stack.crate_timestamp_stack import CreateTimestampStack


app = cdk.App()
stack = CreateTimestampStack(
    app, "CreateTimestampStack", stack_name="CreateTimestampStack")
Tags.of(stack).add("service", "CreateTimestamp")
app.synth()
