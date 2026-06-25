#!/usr/bin/env python3
import argparse
import io
import random
import socket
import tempfile
import time
from ftplib import FTP, all_errors, error_perm

from base.tgen_common import (
    TgenBase,
    config_logger,
    read_json_yaml,
    timing_decorator,
)
from base.zip_utils import create_random_encrypted_zip_in_memory, rand_name


class FtpTgen(TgenBase):
    """
    Rewrite of FTPTgen using new structure
    """

    def __init__(
        self,
        markov_model: dict,
        action_model: dict,
        server_ip: str,
        server_port: str,
        parameters: dict | None = None,
    ):
        self.ftp = None
        fn_map = {
            "browse_list": self.list_remote_filesystem,
            "browse_cd": self.change_to_random_directory,
            "browse_stat": self.stat_remote_filesystem,
            "browse_noop": super().wait,
            "upload_store": self.upload_file,
            "upload_appe": self.append_to_remote_file,
            "upload_noop": super().wait,
            "download_retr": self.download_file,
            "download_noop": super().wait,
            "wait": super().wait,
        }
        super().__init__(markov_model, action_model, parameters, fn_map)
        self.server_addr = server_ip
        self.server_port = server_port
        self.username = (
            self.parameters.get("username")
            if "username" in self.parameters
            else "user"
        )
        self.password = (
            self.parameters.get("password")
            if "password" in self.parameters
            else "pass"
        )
        self.to_temp = (
            bool(self.parameters.get("to_temp"))
            if "to_temp" in self.parameters
            else True
        )
        self.local_dir = (
            self.parameters.get("local_dir")
            if "local_dir" in self.parameters
            else "."
        )
        self.max_zip_depth = (
            int(self.parameters.get("max_zip_depth"))
            if "max_zip_depth" in self.parameters
            else "10"
        )
        self.max_zip_dirs = (
            int(self.parameters.get("max_zip_dirs"))
            if "max_zip_dirs" in self.parameters
            else "10"
        )
        self.max_zip_files = (
            int(self.parameters.get("max_zip_files"))
            if "max_zip_files" in self.parameters
            else "10"
        )
        self.min_file_size = (
            int(self.parameters.get("min_file_size"))
            if "min_file_size" in self.parameters
            else "10"
        )
        self.max_file_size = (
            int(self.parameters.get("max_file_size"))
            if "max_file_size" in self.parameters
            else "10"
        )

    def __create_ftp_connection(self):
        self.ftp = FTP()
        self.ftp.connect(
            host=self.server_addr, port=self.server_port, timeout=60
        )
        self.ftp.login(user=self.username, passwd=self.password)

    def __health_check_ftp_connection(self):
        """
        Attempt to send a command to ftp server.
        If it fails, attempt to close ftp connection, then reopen it
        """
        if self.ftp is None:
            self.__create_ftp_connection()
        try:
            self.ftp.voidcmd("NOOP")
        except (all_errors, OSError, socket.error):
            try:
                self.ftp.close()
            except Exception:
                pass
            self.__create_ftp_connection()

    def __select_a_random_file(self, remote_dir="."):
        self.__health_check_ftp_connection()
        if remote_dir != ".":
            self.ftp.cwd(remote_dir)

        # Get list of files
        file_obj = tuple([remote_dir, {"type": "dir"}])
        filename = ""
        while filename == "" and file_obj[1]["type"] == "dir":
            files = self.ftp.mlsd(remote_dir)
            if not files:
                raise ValueError("No files found in directory")
            # Pick a random file
            file_obj = random.choice(list(files))
            print(f"file_obj: {file_obj}")
            if file_obj[1]["type"] == "file":
                filename = file_obj[0]
            elif file_obj[1]["type"] == "dir":
                remote_dir += "/" + file_obj[0]
            else:
                print(f"unkown type: {file_obj[1]['type']}")
                exit(1)
        return remote_dir + "/" + filename

    @timing_decorator
    def download_file(
        self, remote_filename=None, local_filename=".", to_temp=True, **kwargs
    ):
        self.__health_check_ftp_connection()
        if remote_filename is None:
            remote_filename = self.__select_a_random_file()
        if to_temp:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                self.ftp.retrbinary(f"RETR {remote_filename}", tmp.write)
                tmp.flush()
        else:
            with open(local_filename, "wb") as f:
                self.ftp.retrbinary(f"RETR {remote_filename}", f.write)

    @timing_decorator
    def list_remote_filesystem(self, remote_dir=".", **kwargs):
        self.__health_check_ftp_connection()
        self.ftp.mlsd(remote_dir, facts=[])

    @timing_decorator
    def stat_remote_filesystem(self, remote_dir=".", **kwargs):
        self.__health_check_ftp_connection()
        self.ftp.mlsd(remote_dir)

    @timing_decorator
    def change_to_random_directory(self, start_dir=".", **kwargs):
        original_dir = self.ftp.pwd()
        try:
            self.ftp.cwd(start_dir)
            directories = []
            for name, facts in self.ftp.mlsd(facts=["type"]):
                if name in (".", ".."):
                    continue
                if facts.get("type") == "dir":
                    directories.append(name)
            if original_dir not in ("/", ""):
                directories.append("..")
            if not directories:
                self.ftp.cwd(original_dir)
                return None

            selected = random.choice(directories)
            self.ftp.cwd(selected)

        except error_perm:
            return None

    @timing_decorator
    def upload_file(self, remote_filename=rand_name(), **kwargs):
        zip_buffer = create_random_encrypted_zip_in_memory(
            self.max_zip_depth,
            self.max_zip_dirs,
            self.max_zip_files,
            self.min_file_size,
            self.max_file_size,
        )
        self.__health_check_ftp_connection()
        self.ftp.storbinary(f"STOR {remote_filename}", io.BytesIO(zip_buffer))

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
            self.min_file_size,
            self.max_file_size,
        )
        self.__health_check_ftp_connection()
        self.ftp.storbinary(f"APPE {remote_filename}", io.BytesIO(zip_buffer))

    @timing_decorator
    def delete_remote_file(self, remote_filename, **kwargs):
        self.__health_check_ftp_connection()
        self.ftp.delete(remote_filename)

    @timing_decorator
    def browse_filesystem(self, steps=10, start_dir=".", **kwargs):
        self.__health_check_ftp_connection()

        self.ftp.cwd(start_dir)
        for _ in range(steps):
            current_dir = self.ftp.pwd()
            try:
                entries = []
                self.ftp.retrlines("LIST", lambda line: entries.append(line))
                directories = []
                for entry in entries:
                    parts = entry.split(maxsplit=8)
                    if len(parts) < 9:
                        continue
                    permissions = parts[0]
                    name = parts[8]

                    # Skip current/parent references
                    if name in (".", ".."):
                        continue
                    if permissions.startswith("d"):
                        directories.append(name)
                possible_moves = directories.copy()

                # Randomly allow going up
                if current_dir not in ("/", ""):
                    possible_moves.append("..")
                if not possible_moves:
                    break

                next_dir = random.choice(possible_moves)
                self.ftp.cwd(next_dir)
                time.sleep(random.uniform(0.1, 0.75))
            except error_perm:
                # Permission denied or invalid dir
                continue
            except Exception:
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FTP client tgen")
    parser.add_argument(
        "-c", dest="config", help="path to configfile", default="./config.json"
    )
    parser.add_argument("-s", dest="server_ip", help="server ip")
    parser.add_argument(
        "-p", dest="server_port", help="server port", default=2121
    )
    args = parser.parse_args()
    conf = read_json_yaml(args.config)
    node_id = socket.gethostname().split("_")[-1]
    logger = config_logger()
    ftp_client = FtpTgen(
        conf.get("markov"),
        conf.get("states"),
        parameters=conf.get("parameters"),
        server_ip=args.server_ip,
        server_port=int(args.server_port),
    )
    summary = ftp_client.start_model()
    logger.info(summary)
