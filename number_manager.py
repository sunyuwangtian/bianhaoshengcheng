import getpass
import json
import os
import socket
import time
from datetime import datetime


DEFAULT_SHARED_PATH = r"\\192.168.2.64\e"
DEFAULT_DATA_DIR_NAME = "编号生成器数据"
DEFAULT_DOC_DIR_NAME = "文档"


class NumberManager:
    def __init__(self, shared_path=DEFAULT_SHARED_PATH):
        self.shared_path = shared_path
        self.data_dir = os.path.join(shared_path, DEFAULT_DATA_DIR_NAME)
        self.doc_dir = os.path.join(shared_path, DEFAULT_DOC_DIR_NAME)
        self.current_number_file = os.path.join(self.data_dir, "current_number.txt")
        self.log_file = os.path.join(self.data_dir, "number_log.json")
        self.lock_file = os.path.join(self.data_dir, "lock.tmp")
        self.config_file = os.path.join(self.data_dir, "config.json")

        self.local_config_dir = os.path.join(os.path.expanduser("~"), ".编号生成器")
        self.local_config_file = os.path.join(self.local_config_dir, "local_config.json")

        self.username = getpass.getuser()
        self.hostname = socket.gethostname()

        self._ensure_data_directory()
        self._ensure_local_config_directory()
        self._load_config()
        self._load_local_config()

    def set_username(self, username):
        if username and username.strip():
            self.username = username.strip()
            self.local_config["saved_username"] = self.username
            self._save_local_config()
        else:
            raise ValueError("用户名不能为空")

    def _ensure_data_directory(self):
        try:
            os.makedirs(self.data_dir, exist_ok=True)
        except Exception as exc:
            raise Exception(f"无法创建数据目录 {self.data_dir}: {exc}")

    def _ensure_local_config_directory(self):
        try:
            os.makedirs(self.local_config_dir, exist_ok=True)
        except Exception as exc:
            print(f"警告：无法创建本地配置目录 {self.local_config_dir}: {exc}")

    def _load_config(self):
        default_config = {
            "start_number": 1001,
            "initialized": False,
        }

        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            else:
                self.config = default_config
                self._save_config()
        except Exception:
            self.config = default_config

    def _load_local_config(self):
        default_local_config = {"saved_username": None}

        try:
            if os.path.exists(self.local_config_file):
                with open(self.local_config_file, "r", encoding="utf-8") as f:
                    self.local_config = json.load(f)
                if self.local_config.get("saved_username"):
                    self.username = self.local_config["saved_username"]
            else:
                self.local_config = default_local_config
                self._save_local_config()
        except Exception:
            self.local_config = default_local_config

    def _save_local_config(self):
        try:
            with open(self.local_config_file, "w", encoding="utf-8") as f:
                json.dump(self.local_config, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"保存本地配置失败: {exc}")

    def _save_config(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            raise Exception(f"保存配置失败: {exc}")

    def _acquire_lock(self, timeout=10):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if os.path.exists(self.lock_file):
                    try:
                        lock_time = os.path.getmtime(self.lock_file)
                        if time.time() - lock_time > 30:
                            print("检测到过期锁文件，正在清理...")
                            os.remove(self.lock_file)
                    except Exception:
                        pass

                with open(self.lock_file, "x", encoding="utf-8") as f:
                    f.write(f"{self.username}@{self.hostname}:{datetime.now().isoformat()}")
                return True
            except FileExistsError:
                time.sleep(0.1)
            except Exception as exc:
                print(f"获取锁时出错: {exc}")
                time.sleep(0.1)
        return False

    def _release_lock(self):
        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except Exception:
            pass

    def _get_current_number(self):
        try:
            if os.path.exists(self.current_number_file):
                with open(self.current_number_file, "r", encoding="utf-8") as f:
                    return int(f.read().strip())
            return self.config["start_number"] - 1
        except Exception:
            return self.config["start_number"] - 1

    def _set_current_number(self, number):
        with open(self.current_number_file, "w", encoding="utf-8") as f:
            f.write(str(number))

    def _read_logs(self):
        if not os.path.exists(self.log_file):
            return []
        with open(self.log_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_logs(self, logs):
        logs = logs[-1000:]
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

    def _append_log(self, log_entry):
        try:
            logs = self._read_logs()
            logs.append(log_entry)
            self._write_logs(logs)
        except Exception as exc:
            print(f"记录日志失败: {exc}")

    def _log_number_allocation(self, number, count=1):
        self._append_log(
            {
                "number": number,
                "count": count,
                "user": self.username,
                "hostname": self.hostname,
                "timestamp": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
            }
        )

    def get_next_number(self, count=1):
        if not self._acquire_lock():
            raise Exception("获取锁超时，请稍后重试")

        try:
            current = self._get_current_number()
            next_number = current + 1
            new_current = current + count

            self._set_current_number(new_current)
            self._log_number_allocation(next_number, count)

            if count == 1:
                return next_number
            return list(range(next_number, next_number + count))
        finally:
            self._release_lock()

    def delete_number(self, number_to_delete):
        if not self._acquire_lock():
            raise Exception("获取锁超时，请稍后重试")

        try:
            current = self._get_current_number()
            if number_to_delete != current:
                raise Exception(f"只能删除最后分配的编号 {current}，不能删除编号 {number_to_delete}")

            self._set_current_number(current - 1)
            self._log_number_deletion(number_to_delete)
            return True
        finally:
            self._release_lock()

    def _log_number_deletion(self, number):
        self._append_log(
            {
                "number": number,
                "count": -1,
                "user": self.username,
                "hostname": self.hostname,
                "timestamp": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                "action": "delete",
            }
        )

    def get_recent_logs(self, limit=20):
        try:
            logs = self._read_logs()
            return logs[-limit:] if logs else []
        except Exception:
            return []

    def get_current_status(self):
        try:
            current = self._get_current_number()
            recent_logs = self.get_recent_logs(5)
            return {
                "current_number": current,
                "next_number": current + 1,
                "recent_logs": recent_logs,
                "shared_path": self.shared_path,
                "doc_dir": self.doc_dir,
                "data_dir_exists": os.path.exists(self.data_dir),
            }
        except Exception as exc:
            return {
                "error": str(exc),
                "shared_path": self.shared_path,
                "doc_dir": self.doc_dir,
                "data_dir_exists": False,
            }

    def set_start_number(self, start_number, force=False):
        if not self._acquire_lock():
            raise Exception("获取锁超时，请稍后重试")

        try:
            if self.config.get("initialized", False) and not force:
                self.config["start_number"] = start_number
                self._save_config()
            else:
                self.config["start_number"] = start_number
                self.config["initialized"] = True
                self._save_config()
                self._set_current_number(start_number - 1)
        finally:
            self._release_lock()

    def update_start_number(self, start_number):
        if not self._acquire_lock():
            raise Exception("获取锁超时，请稍后重试")

        try:
            current = self._get_current_number()
            self.config["start_number"] = start_number
            self._save_config()
            self._log_start_number_change(start_number, current)
        finally:
            self._release_lock()

    def _log_start_number_change(self, new_start, current_number):
        self._append_log(
            {
                "number": new_start,
                "count": 0,
                "user": self.username,
                "hostname": self.hostname,
                "timestamp": datetime.now().isoformat(),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                "action": "update_start_number",
                "current_number": current_number,
            }
        )

    def reset_system(self, new_start_number):
        if not self._acquire_lock():
            raise Exception("获取锁超时，请稍后重试")

        try:
            if os.path.exists(self.log_file):
                backup_file = os.path.join(self.data_dir, f"number_log_backup_{int(time.time())}.json")
                os.rename(self.log_file, backup_file)

            self.config = {
                "start_number": new_start_number,
                "initialized": True,
            }
            self._save_config()
            self._set_current_number(new_start_number - 1)
            self._log_number_allocation(new_start_number - 1, 0)
        finally:
            self._release_lock()
