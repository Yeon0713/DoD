"""Create the private Ncloud Storage buckets listed in Terraform's storage output."""

import argparse
import json
import os
import re
import sys

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ENDPOINT = "https://kr.ncloudstorage.com"
REGION = "kr"


def ensure_bucket(client, name: str) -> str:
    try:
        client.head_bucket(Bucket=name)
        return "exists"
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
            raise

    try:
        client.create_bucket(Bucket=name, CreateBucketConfiguration={"LocationConstraint": REGION})
    except ClientError as error:
        if error.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise
    client.head_bucket(Bucket=name)
    return "ready"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only verify the listed buckets")
    args = parser.parse_args()

    try:
        storage = json.load(sys.stdin)
        if storage["endpoint"] != ENDPOINT or storage["region"] != REGION:
            raise ValueError
        buckets = storage["buckets"]
        if not isinstance(buckets, dict) or set(buckets) not in (
            {"releases", "media", "instagram"}, {"releases", "media", "instagram", "backups"}
        ):
            raise ValueError
        for purpose, name in buckets.items():
            if not re.fullmatch(rf"donna-(staging|production)-{purpose}-[a-z0-9][a-z0-9-]{{1,19}}[a-z0-9]", name):
                raise ValueError
    except (ValueError, KeyError, TypeError):
        raise SystemExit("Expected the Ncloud Storage configuration from terraform output -json storage.") from None

    access_key, secret_key = os.getenv("NCLOUD_ACCESS_KEY"), os.getenv("NCLOUD_SECRET_KEY")
    if not access_key or not secret_key:
        raise SystemExit("Set NCLOUD_ACCESS_KEY and NCLOUD_SECRET_KEY before running this command.")
    client = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name=REGION,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(
            signature_version="s3v4", s3={"addressing_style": "path"}, connect_timeout=5, read_timeout=15,
        ),
    )
    for purpose, name in buckets.items():
        try:
            if args.check:
                client.head_bucket(Bucket=name)
                status = "exists"
            else:
                status = ensure_bucket(client, name)
        except ClientError as error:
            code = error.response["Error"]["Code"]
            raise SystemExit(f"{purpose} ({name}): Ncloud Storage error {code}.") from None
        except BotoCoreError as error:
            raise SystemExit(f"{purpose} ({name}): {type(error).__name__}.") from None
        print(f"{purpose}: {name} ({status})")


if __name__ == "__main__":
    main()
