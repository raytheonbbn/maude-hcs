#!/usr/bin/env python3
import argparse
import io
import random
import socket
import tempfile
import time

import boto3
from base.tgen_common import (
    TgenBase,
    config_logger,
    read_json_yaml,
    timing_decorator,
)
from base.zip_utils import create_random_encrypted_zip_in_memory, rand_name
from botocore.config import Config

MAX_ATTEMPTS = 10


class MinioTgen(TgenBase):

    def __init__(
        self,
        markov_model: dict,
        action_model: dict,
        minio_username,
        minio_password,
        minio_hostname,
        minio_port,
        ca_bundle,
        minio_client_cert,
        minio_client_key,
        minio_bucket_root,
        max_zip_depth,
        max_zip_dirs,
        max_zip_files,
        min_internal_file_size,
        max_internal_file_size,
        max_files_per_dir,
        max_filesystem_depth,
        max_dirs_per_dir_level,
        parameters: dict | None = None,
    ):
        self.minio = None
        fn_map = {
            "browse_list": self.list_remote_bucket,
            "browse_cd": self.change_to_random_directory,
            "browse_stat": self.stat_remote_bucket,
            "browse_noop": super().wait,
            "upload_store": self.upload_file,
            "upload_appe": self.append_to_remote_file,
            "upload_noop": super().wait,
            "download_retr": self.download_file,
            "download_noop": super().wait,
            "wait": super().wait,
            "monitor_upload": self.monitor_upload,
            "monitor_download": self.monitor_download,
        }
        super().__init__(markov_model, action_model, parameters, fn_map)
        self.minio_username = minio_username
        self.minio_password = minio_password
        self.minio_hostname = minio_hostname
        self.minio_port = minio_port
        self.ca_bundle = ca_bundle
        self.minio_client_cert = minio_client_cert
        self.minio_client_key = minio_client_key
        self.minio_bucket_root = minio_bucket_root
        self.max_zip_depth = max_zip_depth
        self.max_zip_dirs = max_zip_dirs
        self.max_zip_files = max_zip_files
        self.min_internal_file_size = min_internal_file_size
        self.max_internal_file_size = max_internal_file_size
        self.max_files_per_dir = max_files_per_dir
        self.max_filesystem_depth = max_filesystem_depth
        self.max_dirs_per_dir_level = max_dirs_per_dir_level
        self.monitor_zip_remote = None

    def _get_minio_connection(self):
        """
        Create and return MinIO S3 connection.
        """
        try:
            tls_config = Config(
                s3={"addressing_style": "path"},
                inject_host_prefix=False,
                client_cert=(self.minio_client_cert, self.minio_client_key),
            )
            self.minio = boto3.resource(
                service_name="s3",
                endpoint_url=(
                    f"https://{self.minio_hostname}:{self.minio_port}/"
                ),
                aws_access_key_id=self.minio_username,
                aws_secret_access_key=self.minio_password,
                verify=self.ca_bundle,
                config=tls_config,
            )

        except Exception as e:
            raise ConnectionError(f"Failed to connect to MinIO: {e}") from e

    def _health_check_minio_connection(self):
        """
        Verify MinIO connection is alive.
        Reconnect if the check fails.
        """
        if self.minio is None:
            self._get_minio_connection()

        try:
            # Lightweight call to validate connection
            list(self.minio.buckets.limit(1))

        except Exception:
            try:
                self.minio = None
            except Exception:
                pass

            self._get_minio_connection()

    def __select_a_random_file(self, remote_dir=None):
        self._health_check_minio_connection()
        if not remote_dir or remote_dir == ".":
            bucket_name = self.minio_bucket_root
            prefix = ""
        else:
            bucket_name, *prefix_parts = remote_dir.split("/", 1)
            prefix = prefix_parts[0] if prefix_parts else ""

        objects = list(
            self.minio.Bucket(bucket_name).objects.filter(Prefix=prefix)
        )

        files = [obj.key for obj in objects if not obj.key.endswith("/")]

        if not files:
            raise ValueError("No files found in directory")

        return bucket_name + "/" + random.choice(files)

    @timing_decorator
    def download_file(
        self, remote_filename=None, local_filename=".", to_temp=True, **kwargs
    ):
        self._health_check_minio_connection()

        if remote_filename is None:
            remote_filename = self.__select_a_random_file()

        bucket_name, *key_parts = remote_filename.split("/", 1)

        if not key_parts:
            raise ValueError(
                "remote_filename must include bucket and object key"
            )

        object_key = key_parts[0]

        if to_temp:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                self.minio.Bucket(bucket_name).download_fileobj(
                    object_key,
                    tmp,
                )
                tmp.flush()
                return tmp.name

        else:
            with open(local_filename, "wb") as f:
                self.minio.Bucket(bucket_name).download_fileobj(
                    object_key,
                    f,
                )

            return local_filename

    @timing_decorator
    def list_remote_bucket(self, remote_dir=None, **kwargs):
        self._health_check_minio_connection()

        if not remote_dir or remote_dir == ".":
            bucket_name = self.minio_bucket_root
            prefix = ""
        else:
            bucket_name, *prefix_parts = remote_dir.split("/", 1)
            prefix = prefix_parts[0] if prefix_parts else ""

        return list(
            self.minio.Bucket(bucket_name).objects.filter(Prefix=prefix)
        )

    @timing_decorator
    def stat_remote_bucket(self, remote_dir=None, **kwargs):
        self._health_check_minio_connection()

        if not remote_dir or remote_dir == ".":
            bucket_name = self.minio_bucket_root
            prefix = ""
        else:
            bucket_name, *prefix_parts = remote_dir.split("/", 1)
            prefix = prefix_parts[0] if prefix_parts else ""

        return [
            {
                "key": obj.key,
                "size": obj.size,
                "last_modified": obj.last_modified,
            }
            for obj in self.minio.Bucket(bucket_name).objects.filter(
                Prefix=prefix,
            )
        ]

    @timing_decorator
    def change_to_random_directory(self, start_dir=None, **kwargs):
        self._health_check_minio_connection()

        if not start_dir or start_dir == ".":
            bucket_name = self.minio_bucket_root
            prefix = ""
        else:
            bucket_name, *prefix_parts = start_dir.split("/", 1)
            prefix = prefix_parts[0] if prefix_parts else ""

        prefixes = set()

        for obj in self.minio.Bucket(bucket_name).objects.filter(
            Prefix=prefix
        ):
            prefix_len = len(prefix)
            remaining = obj.key[prefix_len:].lstrip("/")

            if "/" in remaining:
                next_dir = remaining.split("/", 1)[0]
                prefixes.add(f"{prefix}/{next_dir}".strip("/"))

        if not prefixes:
            return None

        return f"{bucket_name}/{random.choice(list(prefixes))}"

    @timing_decorator
    def upload_file(self, remote_filename=None, **kwargs):

        if not remote_filename:
            remote_filename = rand_name()

        zip_buffer = create_random_encrypted_zip_in_memory(
            self.max_zip_depth,
            self.max_zip_dirs,
            self.max_zip_files,
            self.min_internal_file_size,
            self.max_internal_file_size,
        )
        self._health_check_minio_connection()

        self.minio.Bucket(self.minio_bucket_root).upload_fileobj(
            io.BytesIO(zip_buffer),
            remote_filename,
        )

    @timing_decorator
    def append_to_remote_file(self, **kwargs):
        try:
            remote_filename = self.__select_a_random_file()
        except ValueError:
            logger.info("No remote files found, generating a fresh name")
            remote_filename = rand_name()

        logger.info("Appending to remote file: %s", remote_filename)

        zip_buffer = create_random_encrypted_zip_in_memory(
            self.max_zip_depth,
            self.max_zip_dirs,
            self.max_zip_files,
            self.min_internal_file_size,
            self.max_internal_file_size,
        )

        self._health_check_minio_connection()

        bucket_name, *key_parts = remote_filename.split("/", 1)

        if not key_parts:
            raise ValueError(
                "remote_filename must include bucket and object key"
            )

        object_key = key_parts[0]

        bucket = self.minio.Bucket(bucket_name)

        existing_data = b""

        try:
            obj = bucket.Object(object_key)
            existing_data = obj.get()["Body"].read()
        except Exception:
            pass

        combined_data = existing_data + zip_buffer

        bucket.upload_fileobj(
            io.BytesIO(combined_data),
            object_key,
        )

    @timing_decorator
    def delete_remote_file(self, remote_filename, **kwargs):
        self._health_check_minio_connection()

        bucket_name, *key_parts = remote_filename.split("/", 1)

        if not key_parts:
            raise ValueError(
                "remote_filename must include bucket and object key"
            )

        object_key = key_parts[0]

        self.minio.Object(bucket_name, object_key).delete()

    @timing_decorator
    def browse_filesystem(self, steps=10, start_dir=".", **kwargs):
        self._health_check_minio_connection()

        current_dir = start_dir

        for _ in range(steps):
            try:
                bucket_name, *prefix_parts = current_dir.split("/", 1)
                prefix = prefix_parts[0] if prefix_parts else ""

                directories = set()

                for obj in self.minio.Bucket(bucket_name).objects.filter(
                    Prefix=prefix
                ):
                    prefix_len = len(prefix)
                    remaining = obj.key[prefix_len:].lstrip("/")

                    if "/" in remaining:
                        next_dir = remaining.split("/", 1)[0]
                        directories.add(next_dir)

                possible_moves = list(directories)

                if not possible_moves:
                    break

                next_dir = random.choice(possible_moves)

                current_dir = f"{bucket_name}/{prefix}/{next_dir}".replace(
                    "//",
                    "/",
                )

                time.sleep(random.uniform(0.1, 0.75))

            except Exception:
                break

        return current_dir

    @timing_decorator
    def monitor_upload(self, remote_filename=None, **kwargs):

        if not remote_filename:
            remote_filename = rand_name()

        zip_buffer = create_random_encrypted_zip_in_memory(
            self.max_zip_depth,
            self.max_zip_dirs,
            self.max_zip_files,
            self.min_internal_file_size,
            self.max_internal_file_size,
        )

        self.monitor_zip_remote = remote_filename
        self._health_check_minio_connection()

        logger.info(
            "Uploading monitor file %s with length %s",
            remote_filename,
            len(zip_buffer),
        )

        self.minio.Bucket(self.minio_bucket_root).upload_fileobj(
            io.BytesIO(zip_buffer),
            remote_filename,
        )

    @timing_decorator
    def monitor_download(self, local_filename=".", to_temp=True, **kwargs):
        self._health_check_minio_connection()

        logger.info("Downloading monitor file %s", self.monitor_zip_remote)

        if to_temp:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                self.minio.Bucket(self.minio_bucket_root).download_fileobj(
                    self.monitor_zip_remote,
                    tmp,
                )
                tmp.flush()
                return tmp.name

        else:
            with open(local_filename, "wb") as f:
                self.minio.Bucket(self.minio_bucket_root).download_fileobj(
                    self.monitor_zip_remote,
                    f,
                )

            return local_filename


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minio client tgen")
    parser.add_argument(
        "-c", dest="config", help="path to configfile", default="./config.json"
    )
    parser.add_argument(
        "--minio-hostname",
        type=str,
        default="minio.pwnd.com",
        help="URL for the minio server (default: minio.pwnd.com)",
    )

    parser.add_argument(
        "--minio-port",
        type=int,
        default=9000,
        help="URL for the minio server (default: 9000)",
    )

    parser.add_argument(
        "--ca-bundle",
        type=str,
        default="./certs/ca.badlands.minio.crt",
        help="CA Bundle",
    )

    parser.add_argument(
        "--minio-client-cert",
        type=str,
        default="./certs/client.badlands.minio.crt",
        help="Client Cert",
    )

    parser.add_argument(
        "--minio-client-key",
        type=str,
        default="./certs/client.badlands.minio.key",
        help="Client Cert Key",
    )

    parser.add_argument(
        "--minio-username",
        type=str,
        default="admin",
        help="The username to connect to the bucket (default: admin)",
    )

    parser.add_argument(
        "--minio-password",
        type=str,
        default="admin123",
        help="Password for the minio username (default: admin123)",
    )

    parser.add_argument(
        "--minio-bucket-root",
        type=str,
        default="tgen",
        help="Root of the minio bucket (default: tgen)",
    )

    parser.add_argument(
        "--max-zip-depth",
        type=int,
        default=3,
        help="Maximum nested ZIP depth (default: 3)",
    )

    parser.add_argument(
        "--max-zip-dirs",
        type=int,
        default=3,
        help="Maximum number of directories inside ZIPs (default: 3)",
    )

    parser.add_argument(
        "--max-zip-files",
        type=int,
        default=5,
        help="Maximum number of files inside ZIPs (default: 5)",
    )

    parser.add_argument(
        "--min-internal-file-size",
        type=int,
        default=1,
        help="Minimum internal file size in bytes (default: 1)",
    )

    parser.add_argument(
        "--max-internal-file-size",
        type=int,
        default=1048,
        help="Maximum internal file size in bytes (default: 1048)",
    )

    parser.add_argument(
        "--max-files-per-dir",
        type=int,
        default=3,
        help="Maximum internal file size in bytes (default: 3)",
    )
    parser.add_argument(
        "--max-filesystem-depth",
        type=int,
        default=3,
        help="Maximum internal file size in bytes (default: 3)",
    )
    parser.add_argument(
        "--max-dirs-per-dir-level",
        type=int,
        default=3,
        help="Maximum internal file size in bytes (default: 3)",
    )

    args = parser.parse_args()
    conf = read_json_yaml(args.config)
    node_id = socket.gethostname().split("_")[-1]
    logger = config_logger()

    minio_username = args.minio_username
    minio_password = args.minio_password
    minio_hostname = args.minio_hostname
    minio_port = args.minio_port
    ca_bundle = args.ca_bundle
    minio_client_cert = args.minio_client_cert
    minio_client_key = args.minio_client_key
    minio_bucket_root = args.minio_bucket_root
    max_zip_depth = args.max_zip_depth
    max_zip_dirs = args.max_zip_dirs
    max_zip_files = args.max_zip_files
    min_internal_file_size = args.min_internal_file_size
    max_internal_file_size = args.max_internal_file_size
    max_files_per_dir = args.max_files_per_dir
    max_filesystem_depth = args.max_filesystem_depth
    max_dirs_per_dir_level = args.max_dirs_per_dir_level

    states = conf.get("states")
    if not states:
        states = conf.get("actions")

    minio_client = MinioTgen(
        conf.get("markov"),
        states,
        minio_username,
        minio_password,
        minio_hostname,
        minio_port,
        ca_bundle,
        minio_client_cert,
        minio_client_key,
        minio_bucket_root,
        max_zip_depth,
        max_zip_dirs,
        max_zip_files,
        min_internal_file_size,
        max_internal_file_size,
        max_files_per_dir,
        max_filesystem_depth,
        max_dirs_per_dir_level,
        parameters=conf.get("parameters"),
    )
    summary = minio_client.start_model()
    logger.info(summary)
