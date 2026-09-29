"""Run a model in an isolated process with a bounded lifetime and durable logs."""
import multiprocessing
import os
import signal
import time
import traceback
import logging
import math
from pathlib import Path


def _worker(target, args, sender, log_dir):
    try:
        # SMC may spawn children. Give the entire run its own POSIX process group
        # so timeouts and Ctrl-C clean up those workers as well as this process.
        if os.name == "posix":
            os.setsid()
        if log_dir is not None:
            for fd, name in ((1, "stdout.log"), (2, "stderr.log")):
                with open(Path(log_dir) / name, "w") as stream:
                    os.dup2(stream.fileno(), fd)
            logging.basicConfig(filename=Path(log_dir) / "runner.log", force=True,
                                level=logging.INFO)
        result = target(*args)
        if log_dir is not None:
            # Maude can report load failures on native stderr without raising a
            # Python exception. Do not accept a partial model as a passing test.
            diagnostics = (Path(log_dir) / "stderr.log").read_text()
            for marker in ("unable to locate file:", "unpatchable errors", "no parse for term"):
                if marker in diagnostics.lower():
                    raise RuntimeError(f"Maude diagnostic: {marker}; see {log_dir}")
        sender.send((True, result))
    except BaseException:
        # Exceptions from native/library code are not necessarily picklable.
        sender.send((False, traceback.format_exc()))
    finally:
        sender.close()


def execute(target, args=(), timeout=300.0, log_dir=None):
    """Return a child's result, or fail promptly with its traceback/exit status."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive")
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_worker, args=(target, args, sender, log_dir))
    process.start()
    sender.close()  # Without this, a crashed child need not produce EOF.
    deadline = time.monotonic() + timeout
    try:
        while not receiver.poll(min(0.1, max(0, deadline - time.monotonic()))):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Model execution exceeded {timeout}s; logs: {log_dir}")
            if not process.is_alive():
                raise RuntimeError(f"Model worker exited with status {process.exitcode}; logs: {log_dir}")
        try:
            ok, result = receiver.recv()
        except EOFError as exc:
            process.join(timeout=1)
            raise RuntimeError(f"Model worker exited without a result (status {process.exitcode}); logs: {log_dir}") from exc
        process.join(timeout=max(0, deadline - time.monotonic()))
        if process.is_alive():
            raise TimeoutError(f"Model worker did not exit within {timeout}s; logs: {log_dir}")
        if not ok:
            raise RuntimeError(f"Model worker failed; logs: {log_dir}\n{result}")
        if process.exitcode != 0:
            raise RuntimeError(f"Model worker exited with status {process.exitcode}; logs: {log_dir}")
        return result
    finally:
        receiver.close()
        # Kill remaining descendants even if the immediate child already exited.
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        process.close()
