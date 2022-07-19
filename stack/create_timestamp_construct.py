import datetime

import aws_cdk as cdk
from aws_cdk import (
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_sns as sns,
    aws_dynamodb as dynamodb,
    aws_ssm as ssm,
    Duration,
)
from constructs import Construct


class CreateTimestampConstruct(Construct):

    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)

        # プロジェクト全体で使用する設定

        description = self.node.try_get_context("description")
        time_now = datetime.datetime.utcnow().strftime("UTC%Y%m%d%H%M%S")

        def build_resource_name(resource_name: str) -> str:
            return f"{resource_name}_{self.node.try_get_context('projeckName')}_cdk"

        # 各種リソースの作成

        role = iam.Role(
            self, build_resource_name("rol"),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole")
            ],
            role_name=build_resource_name("rol"),
            description=description
        )

        layer = lambda_.LayerVersion(
            self, build_resource_name("lyr"),
            code=lambda_.Code.from_asset("layer"),
            layer_version_name=build_resource_name("lyr"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
            description=description,
        )

        fn = lambda_.Function(
            self, build_resource_name("lmd"),
            code=lambda_.Code.from_asset("src"),
            handler="lambda_function.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            function_name=build_resource_name("lmd"),
            environment=self.node.try_get_context("lambdaEnv"),
            description=time_now,
            timeout=Duration.seconds(300),
            memory_size=256,
            role=role,
            layers=[layer]
        )

        lambda_.Alias(
            self, f"alias_live",
            alias_name="live",
            version=lambda_.Version(
                self, time_now,
                lambda_=fn,
                removal_policy=cdk.RemovalPolicy.RETAIN,
            ),
        )

        loggroup_name = f"/aws/lambda/{fn.function_name}"
        logs.LogGroup(
            self, build_resource_name("log"),
            log_group_name=loggroup_name,
            retention=logs.RetentionDays.ONE_DAY,
        )

        output_bucket_name = self.node.try_get_context("awsS3OutputBucketName")
        output_bucket = s3.Bucket(
            self, output_bucket_name["value"],
            bucket_name=output_bucket_name["value"]
        )

        # 環境変数及び権限設定

        input_bucket_name = self.node.try_get_context("awsS3InputBucketName")
        input_bucket = s3.Bucket.from_bucket_name(
            self, input_bucket_name["value"],
            bucket_name=input_bucket_name["value"],
        )
        input_bucket.grant_read(role)
        input_bucket.add_event_notification(
            event=s3.EventType.OBJECT_CREATED,
            dest=s3n.LambdaDestination(fn),
        )

        output_bucket.grant_put(role)
        fn.add_environment(
            key=output_bucket_name["key"],
            value=output_bucket.bucket_name,
        )

        error_topic_name = self.node.try_get_context("awsSnsErrorTopicArn")
        error_topic_arn_arn = f"arn:aws:sns:{cdk.Stack.of(self).region}:{cdk.Stack.of(self).account}:{error_topic_name['value']}"
        error_topic = sns.Topic.from_topic_arn(
            self, error_topic_arn_arn,
            topic_arn=error_topic_arn_arn,
        )
        error_topic.grant_publish(role)
        fn.add_environment(
            key=error_topic_name["key"],
            value=error_topic.topic_arn,
        )

        notify_controller_table_name = self.node.try_get_context(
            "awsDynNotifyControllerTableName")
        notify_controller_table = dynamodb.Table.from_table_name(
            self, notify_controller_table_name["value"],
            table_name=notify_controller_table_name["value"],
        )
        notify_controller_table.grant_read_data(role)
        fn.add_environment(
            key=notify_controller_table_name["key"],
            value=notify_controller_table.table_name,
        )

        youtube_api_key_name = self.node.try_get_context("awsSsmYoutubeApiKey")
        youtube_api_key = ssm.StringParameter.from_secure_string_parameter_attributes(
            self, youtube_api_key_name["value"],
            version=1,
            parameter_name=youtube_api_key_name["value"],
        )
        youtube_api_key.grant_read(role)
        fn.add_environment(
            key=youtube_api_key_name["key"],
            value=youtube_api_key_name["value"],
        )
