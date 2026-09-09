"""Bound verifier descendants to a POSIX process group or a Windows Job Object."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


class WindowsJob:
    def __init__(self):
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
        for name, args, result in [
            ("CreateJobObjectW", [c.c_void_p, w.LPCWSTR], w.HANDLE),
            ("SetInformationJobObject", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            ("QueryInformationJobObject", [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
            ("AssignProcessToJobObject", [w.HANDLE, w.HANDLE], w.BOOL),
            ("TerminateJobObject", [w.HANDLE, w.UINT], w.BOOL),
            ("OpenProcess", [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            ("CloseHandle", [w.HANDLE], w.BOOL),
        ]:
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
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
    def __init__(self, argv, **options):
        self.job = WindowsJob() if os.name == "nt" else None
        self.process = None
        try:
            if self.job:
                self.process = subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--run"] + list(argv),
                    stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    **options)
                self.job.bind(self.process.pid)
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
        result = subprocess.run(["ps", "-eo", "pgid=,stat="], capture_output=True, text=True, timeout=5, check=True)
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


if __name__ == "__main__":
    # The target cannot start until its waiting launcher belongs to the Job.
    if sys.argv[1:2] != ["--run"] or sys.stdin.buffer.read(1) != b"1":
        raise SystemExit(125)
    try:
        raise SystemExit(subprocess.call(sys.argv[2:]))
    except OSError as exc:
        print("%s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        raise SystemExit(125)
