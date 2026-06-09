import os
import subprocess

import customtkinter


def build():
    script_name = "紧凑版界面_dev.py"
    exe_name = "协作编号管理器_Dev"

    ctk_path = os.path.dirname(customtkinter.__file__)

    print("正在准备打包...")
    print(f"脚本文件: {script_name}")
    print(f"CustomTkinter 路径: {ctk_path}")
    print("\n" + "!" * 50)
    print("注意：正在进行模块分析，通常需要 2-3 分钟。")
    print("期间可能暂时没有输出，请耐心等待，不要按 Ctrl+C。")
    print("!" * 50 + "\n")

    separator = ";" if os.name == "nt" else ":"
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        exe_name,
        "--add-data",
        f"{ctk_path}{separator}customtkinter/",
        "--hidden-import",
        "customtkinter",
        "--hidden-import",
        "docx",
        "--hidden-import",
        "PIL",
        "--clean",
        script_name,
    ]

    print(f"执行命令: {' '.join(cmd)}")

    try:
        subprocess.check_call(cmd)
        print("\n" + "=" * 50)
        print("打包成功")
        print(f"生成的 EXE 文件位于 dist 目录: {exe_name}.exe")
        print("=" * 50)
    except subprocess.CalledProcessError as exc:
        print(f"打包失败: {exc}")
    except Exception as exc:
        print(f"发生错误: {exc}")


if __name__ == "__main__":
    build()
