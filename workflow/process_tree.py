"""Bound verifier descendants to a POSIX process group or a Windows Job Object."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class WindowsJob:
    def __init__(self, name=None):
        import ctypes as c
        from ctypes import wintypes as w

        class Limits(c.Structure):
            _fields_ = [("process_time", c.c_int64), ("job_time", c.c_int64),
                        ("flags", w.DWORD), ("min_working", c.c_size_t),
                        ("max_working", c.c_size_t), ("active_limit", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]

        class Extended(c.Structure):
            _fields_ = [("basic", Limits), ("io", c.c_uint64 * 6),
                        ("process_memory", c.c_size_t), ("job_memory", c.c_size_t),
                        ("peak_process", c.c_size_t), ("peak_job", c.c_size_t)]

        class Accounting(c.Structure):
            _fields_ = [("times", c.c_int64 * 4), ("faults", w.DWORD),
                        ("total", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]

        self.c, self.accounting = c, Accounting
        self.api = c.WinDLL("kernel32", use_last_error=True)
        for function_name, args, result in [
            ("CreateJobObjectW", [c.c_void_p, w.LPCWSTR], w.HANDLE),
            ("SetInformationJobObject", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            ("QueryInformationJobObject", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
            ("AssignProcessToJobObject", [w.HANDLE, w.HANDLE], w.BOOL),
            ("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
            ("OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            ("CloseHandle", [w.HANDLE], w.BOOL),
        ]:
            function = getattr(self.api, function_name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, name)
        self._check(self.handle)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            self._check(self.api.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)))
        except OSError:
            self.close()
            raise

    def _check(self, value):
        if not value:
            raise self.c.WinError(self.c.get_last_error())

    def bind(self, pid):
        process = self.api.OpenProcess(0x0101, False, pid)
        self._check(process)
        try:
            self._check(self.api.AssignProcessToJobObject(self.handle, process))
        finally:
            self.api.CloseHandle(process)

    def alive(self):
        info = self.accounting()
        self._check(self.api.QueryInformationJobObject(
            self.handle, 1, self.c.byref(info), self.c.sizeof(info), None))
        return info.active > 0

    def kill(self):
        self._check(self.api.TerminateJobObject(self.handle, 125))

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class ProcessTree:
    def __init__(self, argv, on_start=None, **options):
        job_name = "Local\\Cosmos-" + __import__("uuid").uuid4().hex if on_start and os.name == "nt" else None
        self.job = WindowsJob(job_name) if os.name == "nt" else None
        self.process = None
        try:
            if self.job or on_start:
                self.process = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve())]
                    + (["--run-owned", str(os.getpid())] if on_start and os.name != "nt" else ["--run"]) + list(argv),
                    stdin=subprocess.PIPE,
                    **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if self.job else {"start_new_session": True}),
                    **options)
                if self.job:
                    self.job.bind(self.process.pid)
                if on_start:
                    on_start({"pid": self.process.pid, "platform": os.name, "job_name": job_name})
                self.process.stdin.write(b"1")
                self.process.stdin.close()
            else:
                self.process = subprocess.Popen(list(argv), start_new_session=True, **options)
        except BaseException:
            if self.process is not None:
                self.process.kill()
                self.process.wait()
            self.close()
            raise

    def alive(self):
        if self.job:
            return self.job.alive()
        try:
            os.killpg(self.process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass  # Darwin can deny signal probes for a group containing only zombies.
        # Orphan zombies cannot write; some hosts defer reaping them indefinitely.
        # An unavailable zombie probe cannot prove that a live group is terminal.
        try:
            result = subprocess.run(["ps", "-eo", "pgid=,stat="], capture_output=True, text=True, timeout=5, check=True)
        except (FileNotFoundError, subprocess.SubprocessError):
            return True
        return any(parts[0] == str(self.process.pid) and not parts[1].startswith("Z")
                   for line in result.stdout.splitlines() if len(parts := line.split()) >= 2)

    def stop(self, grace):
        if self.job:
            self.job.kill()
            method = "job-terminate"
        else:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                self.process.wait(timeout=5)
                return "none"
            method = "sigterm"
            deadline = time.monotonic() + grace
            while self.alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            if self.alive():
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                method += "+sigkill"
        self.process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while self.alive():
            if time.monotonic() >= deadline:
                raise OSError("verifier process group is still active; do not release its resources")
            time.sleep(0.01)
        return method

    def close(self):
        if self.job:
            self.job.close()


def observed_terminal(identity):
    if identity["platform"] != os.name:
        raise ValueError("process terminal observation must run on its original platform")
    if os.name != "nt":
        try:
            os.killpg(identity["pid"], 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        try:
            result = subprocess.run(["ps", "-eo", "pgid=,stat="], capture_output=True, text=True, timeout=5, check=True)
        except (OSError, subprocess.SubprocessError):
            return False
        return not any(parts[0] == str(identity["pid"]) and not parts[1].startswith("Z")
                       for line in result.stdout.splitlines() if len(parts := line.split()) >= 2)
    import ctypes as c
    from ctypes import wintypes as w
    api = c.WinDLL("kernel32", use_last_error=True)
    api.OpenJobObjectW.argtypes, api.OpenJobObjectW.restype = [w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE
    api.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
    api.QueryInformationJobObject.restype = w.BOOL
    api.CloseHandle.argtypes = [w.HANDLE]
    handle = api.OpenJobObjectW(4, False, identity["job_name"])
    if not handle:
        if c.get_last_error() == 2:
            return True
        raise c.WinError(c.get_last_error())
    class Accounting(c.Structure):
        _fields_ = [("times", c.c_int64 * 4), ("faults", w.DWORD),
                    ("total", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]
    try:
        info = Accounting()
        if not api.QueryInformationJobObject(handle, 1, c.byref(info), c.sizeof(info), None):
            raise c.WinError(c.get_last_error())
        return info.active == 0
    finally:
        api.CloseHandle(handle)


if __name__ == "__main__":
    # The target cannot start until its waiting launcher belongs to the Job.
    if sys.argv[1:2] not in (["--run"], ["--run-owned"]) or sys.stdin.buffer.read(1) != b"1":
        raise SystemExit(125)
    arguments = sys.argv[2:]
    if sys.argv[1] == "--run-owned":
        import threading
        signal.signal(signal.SIGTERM, lambda signum, frame: None)
        owner = int(arguments.pop(0))
        def watch_owner():
            while os.getppid() == owner:
                time.sleep(0.1)
            os.killpg(os.getpgrp(), signal.SIGKILL)
        threading.Thread(target=watch_owner, daemon=True).start()
    try:
        result = subprocess.call(arguments)
        if sys.argv[1] == "--run-owned":
            try:
                probe = subprocess.Popen(["ps", "-eo", "pgid=,pid=,stat="], stdout=subprocess.PIPE, text=True)
                output, _ = probe.communicate(timeout=5)
                remaining = probe.returncode != 0 or any(
                    parts[0] == str(os.getpgrp()) and parts[1] not in (str(os.getpid()), str(probe.pid)) and not parts[2].startswith("Z")
                    for line in output.splitlines() if len(parts := line.split()) >= 3)
            except (OSError, subprocess.SubprocessError):
                remaining = True
            if remaining:
                os.killpg(os.getpgrp(), signal.SIGKILL)
        raise SystemExit(result)
    except OSError as exc:
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        raise SystemExit(125)
