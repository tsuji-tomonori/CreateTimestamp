from __future__ import annotations
from typing import NamedTuple

import boto3


class AwsResource:
    def __init__(self, profile: str = None):
        if profile is not None:
            self.session = boto3.Session(
                profile_name=profile, region_name="ap-northeast-1")
        else:
            self.session = boto3.Session()


class Sns(AwsResource):
    def __init__(self, profile: str = None):
        super().__init__(profile)
        self.client = self.session.client("sns")

    def publish(self, topick_arn: str, message: str, subject: str) -> None:
        self.client.publish(
            TopicArn=topick_arn,
            Message=message,
            Subject=subject
        )


class S3(AwsResource):
    def __init__(self, profile: str = None):
        super().__init__(profile)
        self.client = self.session.client("s3")

    def upload(self, data: bin, bucket_name: str, file_path: str) -> None:
        self.client.put_object(
            Body=data,
            Bucket=bucket_name,
            Key=file_path,
        )

    def read_file(self, bucket: str, key: str) -> list[str]:
        res = self.client.get_object(
            Bucket=bucket,
            Key=key
        )
        return res["Body"].read().decode("utf-8")


class Ssm(AwsResource):
    def __init__(self, profile: str = None):
        super().__init__(profile)
        self.client = self.session.client("ssm")

    def value(self, key: str):
        value = self.client.get_parameter(
            Name=key,
            WithDecryption=True
        )
        return value["Parameter"]["Value"]


class Dynamodb(AwsResource):
    def __init__(self, profile: str = None):
        super().__init__(profile)
        self.resource = self.session.resource("dynamodb")

    def get_item(self, table_name: str, key: str) -> dict:
        table = self.resource.Table(table_name)
        return table.get_item(Key=key)["Item"]


class NotifyControllerTable(NamedTuple):
    video_id: str
    version: str
    scheduled_start_time: str
    time_stamp: str
    title: str

    @classmethod
    def of(cls, table_name: str, video_id: str, profile: str = None) -> NotifyControllerTable:
        dynamodb = Dynamodb(profile=profile)
        master = dynamodb.get_item(table_name=table_name, key={
                                   "video_id": video_id, "version": "master"})
        return NotifyControllerTable(**dynamodb.get_item(table_name=table_name, key={"video_id": video_id, "version": master["current_version"]}))
