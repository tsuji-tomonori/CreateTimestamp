from __future__ import annotations
import logging

import re
import csv
import datetime
from pathlib import Path
from typing import NamedTuple

import requests

from aws_resource import S3, NotifyControllerTable


logger = logging.getLogger(__name__)


class ChatItem(NamedTuple):
    # メタ情報
    meta_type: str  # メッセージタイプ
    meta_publishedat: str  # メッセージが最初に公開された日時 ISO8601
    # メッセージ情報
    message_text: str  # メッセージ
    message_channelid: str  # メッセージを作成したユーザーのID
    # 削除情報
    deleted_messageid: str  # 削除されたメッセージを一意に識別するID
    # 無料スパチャ情報
    member_usercomment: str  # コメント
    member_month: int  # メンバー合計月数(切り上げ)
    member_lebelname: str  # メンバーレベル名
    # 新規メンバー情報
    newsponsor_lebelname: str  # メンバーレベル名
    newsponsor_upgrade: bool  # アップグレードの有無 新規メンバーはfalse
    # スパチャ情報
    superchat_amountmicros: float  # 金額(マイクロ単位)
    superchat_currency: str  # 通貨(ISO4217)
    superchat_usercomment: str  # コメント
    superchat_tier: int  # 有料メッセージの階級
    # スーパーチケット情報
    supersticker_id: str  # ステッカーを一意に識別するID
    supersticker_alttext: str  # ステッカーを説明する文字列
    supersticker_amountmicros: float  # 金額(マイクロ単位)
    supersticker_currency: str  # 通貨(ISO4217)
    supersticker_tier: int  # 有料メッセージの階級
    # メンバーギフト情報(送る側)
    membergift_count: int  # ユーザーが購入したメンバーシップギフトの数
    membergift_lebelname: str  # 購入したメンバーシップギフトのレベル
    # メンバーギフト情報(受け取る側)
    membergiftreceive_lebelname: str  # 受け取ったメンバーシップギフトのレベル
    # ユーザー情報
    author_channel_id: str  # チャンネルID
    author_display_name: str  # 表示名
    author_is_verified: bool  # YouTubeに確認されているか否か
    author_is_chatowner: bool  # ライブチャットの所有者か否か
    author_is_chatsponsor: bool  # メンバーシップに入っているか否か
    author_is_chatmoderator: bool  # ライブチャットのモデレーターか否か
    # ban情報
    ban_channelid: str  # banされたユーザーのチャンネルID
    ban_display_name: str  # banされたユーザーのチャンネル表示名


def read_csv(file: Path) -> list[ChatItem]:
    with file.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        result = []
        for x in list(reader)[1:]:
            try:
                result.append(ChatItem(*x))
            except TypeError as e:
                logger.exception(f"len({len(x)}), {x}")
        return result


class S3Param(NamedTuple):
    bucket: str
    key: str
    s3: S3


def read_s3_file(param: S3Param) -> list[ChatItem]:
    file_path = param.key.split('/')[-1]
    with open(f"{file_path}", "w", encoding="utf-8") as f:
        f.write(param.s3.read_file(bucket=param.bucket, key=param.key))
    return read_csv(Path.cwd() / file_path)


def format_secods(t: str) -> str:
    # 秒は6桁に統一
    # 2022-07-04T12:05:08.17237+00:00 -> 2022-07-04T12:05:08.172370+00:00
    split_all = t.split("+")
    split_date = split_all[0].split(".")
    seconds = split_date[-1] + "0"*(6-len(split_date[-1]))
    return f"{split_date[0]}.{seconds}+{split_all[-1]}"


def format_timezone(t: str) -> str:
    # 2022-07-13T13:03:06Z -> 2022-07-13T13:03:06+00:00
    return f"{t[:-1]}+00:00"


def to_unixtime(meta_publishedat: str) -> float:
    # 2022-07-04T12:05:08.172370+00:00 -> 1656903908
    return datetime.datetime.fromisoformat(meta_publishedat).timestamp()


def timestamp(start: str, target: str) -> str:
    start_time = datetime.datetime.fromisoformat(start)
    target_time = datetime.datetime.fromisoformat(target)
    diff_time = target_time - start_time

    diff_sec = diff_time.total_seconds()
    hh = int(diff_sec // 3600)
    remain_sec = diff_sec - (hh * 3600)
    mm = int(remain_sec // 60)
    ss = int(remain_sec - (mm * 60))

    if hh == 0:
        return f"{mm:02}:{ss:02}"
    else:
        return f"{hh}:{mm:02}:{ss:02}"


class LiveStreamingDetails(NamedTuple):
    actualStartTime: str
    actualEndTime: str
    scheduledStartTime: str

    @classmethod
    def of(cls, api_key: str, video_id: str) -> LiveStreamingDetails:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "key": api_key,
            "id": video_id,
            "part": "liveStreamingDetails",
            "maxResults": 50
        }
        res = requests.get(url, params=params).json()
        if res.get("error"):
            raise Exception(f"videos api error: {res}")
        return LiveStreamingDetails(**res["items"][0]["liveStreamingDetails"])


class MessageItem(NamedTuple):
    timestamp: str
    date_time: str
    unixtime: float
    message: str

    @classmethod
    def of(cls, item: ChatItem, start: str) -> MessageItem:
        start_time = format_timezone(start)
        target_time = format_secods(item.meta_publishedat)
        return MessageItem(
            timestamp=timestamp(start=start_time, target=target_time),
            message=item.message_text,
            date_time=target_time,
            unixtime=to_unixtime(target_time),
        )

    def has_kusa(self, pattern) -> bool:
        return re.search(pattern, self.message)


class CsvFile(NamedTuple):
    records: list[MessageItem]

    @classmethod
    def of(cls, yt_api_kye: str, video_id: str, s3_param: S3Param) -> CsvFile:
        live_detail = LiveStreamingDetails.of(
            api_key=yt_api_kye, video_id=video_id)
        records_raw = [
            record for record in read_s3_file(s3_param) if record.meta_type == "textMessageEvent"]
        result = [MessageItem.of(item=x, start=live_detail.actualStartTime)
                  for x in records_raw]
        return CsvFile(sorted(result, key=lambda x: x.unixtime))


class KusaDistanceBase(NamedTuple):
    item: MessageItem
    distance: int


class KusaDistance(NamedTuple):
    records: list[KusaDistanceBase]
    avarage: float

    @classmethod
    def of(cls, csv: CsvFile, pattern: str = r"草|w|くさ|kusa") -> KusaDistance:
        sum_distance = 0.0
        before = csv.records[0].unixtime
        index_distance: list[KusaDistanceBase] = []
        for record in csv.records:
            if not record.has_kusa(pattern):
                continue
            distance = record.unixtime - before
            index_distance.append(KusaDistanceBase(
                item=record, distance=distance))
            before = record.unixtime
            sum_distance += distance
        return KusaDistance(
            records=index_distance,
            avarage=sum_distance / len(index_distance),
        )


class KusaGroup(NamedTuple):
    groups: list[list[KusaDistanceBase]]

    @classmethod
    def of(cls, kusa_distance: KusaDistance) -> KusaGroup:
        groups: list[list[KusaDistanceBase]] = []
        temp = []
        for record in kusa_distance.records:
            temp.append(record)
            if record.distance > kusa_distance.avarage:
                groups.append([x for x in temp])
                temp.clear()
        return KusaGroup(groups=groups)


class LogRecord(NamedTuple):
    index: str
    n_record: str
    start_timestamp: str
    end_timestamp: str
    record: str

    @classmethod
    def of(cls, n_index: int, group: list[KusaDistanceBase]) -> LogRecord:
        return LogRecord(
            index=str(n_index).zfill(3),
            n_record=str(len(group)).zfill(4),
            start_timestamp=group[0].item.timestamp,
            end_timestamp=group[-1].item.timestamp,
            record="\n".join(",".join(str(x) for x in record.item)
                             for record in group)
        )

    def full_report(self) -> str:
        result = f"[index: {self.index} len: {self.n_record}]" + "\n"
        result += f"{self.start_timestamp} ~ {self.end_timestamp}" + "\n"
        result += self.record + "\n"
        result += "-"*10 + "\n"
        return result

    def report(self) -> str:
        return f"★ [{self.start_timestamp}]: {self.n_record} comments!\n"


class LogReport(NamedTuple):
    records: list[LogRecord]

    @classmethod
    def of(cls, item: KusaGroup) -> LogReport:
        idx = 1
        log_records = []
        for group in item.groups:
            log_records.append(LogRecord.of(n_index=idx, group=group))
            idx += 1
        return LogReport(records=log_records)

    def create_md(self, table: NotifyControllerTable, n_target: int = 5) -> str:
        target = sorted(self.records, key=lambda x: x.n_record,
                        reverse=True)[:n_target]
        result = f"{table.title}\n"
        result += "".join(record.report()
                          for record in sorted(target, key=lambda x: x.index))
        return result
