from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, NamedTuple

from aws_resource import S3, Ssm, Sns, NotifyControllerTable
from convert import CsvFile, KusaDistance, KusaGroup, LogReport, S3Param


logger = logging.getLogger(__name__)
logger.setLevel("INFO")


class SecretParams(NamedTuple):
    YOUTUBE_API_KEY: str

    @classmethod
    def of(cls, ssm: Ssm) -> SecretParams:
        return SecretParams(**{x: ssm.value(os.environ[x]) for x in SecretParams._fields})


class EnvironParams(NamedTuple):
    PATTERN: str
    ERROR_TOPIC_ARN: str
    ERROR_TITLE: str
    NOTIFY_CONTROLLER_TABLE_NAME: str
    OUTPUT_S3_BUCKET: str

    @classmethod
    def of(cls) -> EnvironParams:
        return EnvironParams(**{x: os.environ[x] for x in EnvironParams._fields})


class S3Event(NamedTuple):
    video_id: str
    channel_id: str
    bucket_name: str
    key: str

    @classmethod
    def of(cls, record: dict[str, Any]) -> S3Event:
        key: str = record["s3"]["object"]["key"]
        key_without_suffix: str = key.split(".")[0]
        key_split: list = key_without_suffix.split("/")
        return S3Event(
            channel_id=key_split[0],
            video_id=key_split[1],
            bucket_name=record["s3"]["bucket"]["name"],
            key=key,
        )


class LambdaService(NamedTuple):
    env_param: EnvironParams
    ssm_param: SecretParams
    s3_reocrds: list[S3Event]
    ssm: Ssm
    s3: S3
    sns: Sns
    profile: str | None

    @classmethod
    def of(cls, event: dict[str, Any]) -> LambdaService:
        profile = event.get("profile")
        ssm = Ssm(profile=profile)
        s3 = S3(profile=profile)
        sns = Sns(profile=profile)
        return LambdaService(
            env_param=EnvironParams.of(),
            ssm_param=SecretParams.of(ssm),
            s3_reocrds=[S3Event.of(x) for x in event["Records"]],
            ssm=ssm,
            s3=s3,
            sns=sns,
            profile=profile,
        )

    def __service(self) -> None:
        for record in self.s3_reocrds:
            s3_param = S3Param(
                bucket=record.bucket_name,
                key=record.key,
                s3=self.s3
            )
            csv = CsvFile.of(
                yt_api_kye=self.ssm_param.YOUTUBE_API_KEY,
                video_id=record.video_id,
                s3_param=s3_param,
            )
            kusa_distance = KusaDistance.of(
                csv=csv,
                pattern=self.env_param.PATTERN,
            )
            table = NotifyControllerTable.of(
                table_name=self.env_param.NOTIFY_CONTROLLER_TABLE_NAME,
                video_id=record.video_id,
                profile=self.profile,
            )
            kusa_group = KusaGroup.of(kusa_distance=kusa_distance)
            log_report = LogReport.of(item=kusa_group)
            output_md = log_report.write_log(table)
            self.s3.upload(
                data=output_md.encode("utf-8"),
                bucket_name=self.env_param.OUTPUT_S3_BUCKET,
                file_path=f"{record.channel_id}/{record.video_id}.md"
            )

    def __call__(self) -> None:
        return self.__service()

    def error(self, e: Exception) -> None:
        try:
            self.sns.publish(
                topick_arn=self.env_param.ERROR_TOPIC_ARN,
                message=str(e),
                subject=self.env_param.ERROR_TITLE,
            )
        except:
            logger.exception("Not Retry Error")


def lambda_handler(event, context):
    try:
        service = LambdaService.of(event=event)
        service()
    except Exception as e:
        service.error(e)
