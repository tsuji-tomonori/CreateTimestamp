from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import Tags
from constructs import Construct

from stack.create_timestamp_construct import CreateTimestampConstruct


class CreateTimestampStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        create_time_stamp = CreateTimestampConstruct(
            self, "CreateTimestampConstruct")
        Tags.of(create_time_stamp).add("resource", "CreateTimestamp")
