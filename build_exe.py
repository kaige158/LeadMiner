#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包脚本 - 将GUI程序打包为独立 .exe 文件

使用方法：
    python build_exe.py

或直接用命令行：
    pip install pyinstaller
    pyinstaller --onefile --windowed --name "客户号码查找" number_finder_gui.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def build_onefile():
    """打包为单个exe文件"""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "客户号码查找工具",
        "--clean",
        "--noconfirm",
        # 添加数据文件
        "--add-data", f"{SCRIPT_DIR / 'number_finder.py'}{';.' if sys.platform == 'win32' else ':.'}",
        # 排除不需要的模块减小体积
        "--exclude-module", "matplotlib",
        "--exclude-module", "numpy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL",
        "--exclude-module", "tkinter.test",
        # 图标（如果有的话）
        # "--icon", str(SCRIPT_DIR / "icon.ico"),
        # 入口文件
        str(SCRIPT_DIR / "number_finder_gui.py"),
    ]

    print("=" * 60)
    print("  打包中...")
    print(f"  命令: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if result.returncode == 0:
        exe_path = SCRIPT_DIR / "dist" / "客户号码查找工具.exe"
        print(f"\n[OK] 打包成功！")
        print(f"  输出文件: {exe_path}")
        print(f"  文件大小: {exe_path.stat().st_size / 1024 / 1024:.1f} MB" if exe_path.exists() else "")
    else:
        print(f"\n[!!] 打包失败，返回码: {result.returncode}")
        sys.exit(result.returncode)


def build_folder():
    """打包为文件夹（启动更快，适合调试）"""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--name", "客户号码查找工具",
        "--clean",
        "--noconfirm",
        "--add-data", f"{SCRIPT_DIR / 'number_finder.py'}{';.' if sys.platform == 'win32' else ':.'}",
        str(SCRIPT_DIR / "number_finder_gui.py"),
    ]

    print("[*] 打包为文件夹（启动更快）...")
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    if result.returncode == 0:
        print(f"\n[OK] 打包成功！输出目录: {SCRIPT_DIR / 'dist' / '客户号码查找工具'}")
    else:
        print(f"\n[!!] 打包失败")
        sys.exit(result.returncode)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="打包GUI程序")
    parser.add_argument("--folder", action="store_true", help="打包为文件夹（启动更快）")
    args = parser.parse_args()

    if args.folder:
        build_folder()
    else:
        build_onefile()
