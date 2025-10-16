import os
import json

BASE_BUILD_PATH = "builds/logs"

def get_build_path(job_name, build_number):
    return os.path.join(BASE_BUILD_PATH, str(job_name), str(build_number))

def get_full_log_path(job_name, build_number):
    return os.path.join(get_build_path(job_name, build_number), "full.log")

def get_meta_path(job_name, build_number):
    return os.path.join(get_build_path(job_name, build_number), "meta.json")

def ensure_build_dir(job_name, build_number):
    path = get_build_path(job_name, build_number)
    os.makedirs(path, exist_ok=True)
    return path

def append_to_log(job_name, build_number, content):
    ensure_build_dir(job_name, build_number)
    with open(get_full_log_path(job_name, build_number), "a", encoding="utf-8") as f:
        f.write(content)

def read_log(job_name, build_number, tail_lines=None):
    try:
        path = get_full_log_path(job_name, build_number)
        with open(path, "r", encoding="utf-8") as f:
            if tail_lines:
                lines = f.readlines()
                return "".join(lines[-tail_lines:])
            return f.read()
    except FileNotFoundError:
        return None

def read_logs(file_path, last_lines=1000):
    """Read last N lines of a log file efficiently"""
    try:
        with open(file_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            buffer = bytearray()
            pointer = f.tell()
            lines_found = 0
            while pointer >= 0 and lines_found < last_lines:
                f.seek(pointer)
                byte = f.read(1)
                if byte == b"\n":
                    lines_found += 1
                    if lines_found > last_lines:
                        break
                buffer.extend(byte)
                pointer -= 1
            return bytes(reversed(buffer)).decode(errors="replace")
    except Exception as e:
        return f"Error reading logs: {e}"

def save_meta(job_name, build_number, meta_dict):
    ensure_build_dir(job_name, build_number)
    with open(get_meta_path(job_name, build_number), "w", encoding="utf-8") as f:
        json.dump(meta_dict, f)

def read_meta(job_name, build_number):
    try:
        with open(get_meta_path(job_name, build_number), "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
