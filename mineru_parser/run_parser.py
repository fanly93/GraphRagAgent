#!/usr/bin/env python3
"""
MinerU 文档解析 Pipeline 入口脚本。

用法：
    # 解析 input/ 目录中所有文件
    python run_parser.py

    # 解析指定文件
    python run_parser.py path/to/file.pdf path/to/file.xlsx

    # 解析后对每个结果执行验证检查
    python run_parser.py --verify

    # 使用临时 token（覆盖 .env）
    python run_parser.py --token YOUR_TOKEN

    # 仅扫描文件，不实际执行解析（dry-run）
    python run_parser.py --dry-run
"""

import argparse
import sys
from pathlib import Path

# 保证 run_parser.py 所在目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent))

import config
from pipeline import run_pipeline, scan_input_files, verify_result, route_file


def print_banner() -> None:
    print("=" * 60)
    print("  MinerU 文档解析 Pipeline")
    print("=" * 60)
    print(f"  input  目录: {config.INPUT_DIR}")
    print(f"  output 目录: {config.OUTPUT_DIR}")
    print(f"  API    地址: {config.MINERU_BASE_URL}")
    print(f"  模型   版本: {config.MODEL_VERSION}")
    print(f"  语言   设置: {config.LANGUAGE}")
    has_token = bool(config.MINERU_API_TOKEN)
    print(f"  Token  状态: {'已配置' if has_token else '未配置（Agent URL 模式除外）'}")
    print("=" * 60)


def print_file_routes(files: list[Path]) -> None:
    """打印文件格式路由预览。"""
    print(f"\n发现 {len(files)} 个可解析文件：\n")
    for f in files:
        api = route_file(f)
        api_label = {
            "precise": "精准解析 API  /api/v4/",
            "agent":   "Agent 轻量 API /api/v1/agent/",
        }.get(api.value if api else "", "不支持")
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:<35} {size_kb:>8.1f} KB   →  {api_label}")


def print_verify(results) -> None:
    """打印验证检查结果。"""
    print("\n" + "=" * 60)
    print("  验证检查结果")
    print("=" * 60)
    for result in results:
        checks = verify_result(result)
        print(f"\n{result.job.source_path.name}")
        for check_name, passed in checks.items():
            mark = "✓" if passed else "✗"
            print(f"  [{mark}] {check_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="MinerU 文档解析 Pipeline")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="指定要解析的文件路径（不填则解析 input/ 目录全部文件）",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="临时覆盖 .env 中的 MINERU_API_TOKEN",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="解析后对每个结果执行输出规范验证",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅扫描文件和路由，不实际调用 API",
    )
    args = parser.parse_args()

    print_banner()

    # 确定要处理的文件列表
    if args.files:
        files = [Path(f) for f in args.files]
        missing = [f for f in files if not f.exists()]
        if missing:
            print(f"\n[错误] 文件不存在: {[str(f) for f in missing]}")
            sys.exit(1)
    else:
        files = scan_input_files()

    if not files:
        print("\ninput/ 目录中没有可解析的文件。")
        print("请将以下格式的文件放入 input/ 目录：")
        print(f"  精准 API：{sorted(config.PRECISE_API_EXTENSIONS)}")
        print(f"  Agent API：{sorted(config.AGENT_API_EXTENSIONS)}")
        sys.exit(0)

    print_file_routes(files)

    if args.dry_run:
        print("\n[dry-run 模式] 仅路由预览，未实际调用 API。")
        sys.exit(0)

    # 检查 Token（Agent URL 模式不需要 token，但精准 API 需要）
    token = args.token or config.MINERU_API_TOKEN
    precise_files = [f for f in files if route_file(f) and route_file(f).value == "precise"]
    if precise_files and not token:
        print("\n[警告] 存在需要精准解析 API 的文件，但 MINERU_API_TOKEN 未配置。")
        print("请在 .env 文件中填写 MINERU_API_TOKEN，或使用 --token 参数传入。")
        sys.exit(1)

    print()

    # 执行解析
    results = run_pipeline(files=files, api_token=token)

    # 验证
    if args.verify and results:
        print_verify(results)

    # 退出码
    success_count = sum(1 for r in results if r.success)
    sys.exit(0 if success_count == len(results) else 1)


if __name__ == "__main__":
    main()
