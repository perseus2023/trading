"""将 index.html 的远程图片引用本地化，清理 optimized 中未引用的 PNG。

运行：python localize_images.py
预览：python localize_images.py --dry-run
仅以 index.html 为引用依据；不递归清理子目录，不处理其他 HTML 页面。
"""

import argparse
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


DEFAULT_INPUT_DIR = r"Y:\codex_projects\web_codex\ref_trading_hs300_factor"


class ReferenceParser(HTMLParser):
    """收集 HTML 属性中对本地 optimized 目录的直接文件引用。"""

    def __init__(self, input_dir):
        super().__init__(convert_charrefs=True)
        self.input_dir = input_dir
        self.references = set()

    def handle_starttag(self, tag, attrs):
        for _, value in attrs:
            if not value:
                continue
            url = urlsplit(value.strip())
            if url.scheme or url.netloc or not url.path:
                continue
            path = (self.input_dir / unquote(url.path)).resolve()
            if path.parent == self.input_dir / "optimized" and path.suffix.lower() == ".png":
                self.references.add(path)


def localize_images(input_dir=DEFAULT_INPUT_DIR, *, dry_run=False):
    """替换远程目录前缀并删除未引用 PNG；dry_run=True 时不修改文件。

    输入 HTML 必须使用 UTF-8。引用识别支持中文、空格、URL 百分号编码、
    HTML 实体以及查询参数；以 HTML 属性中的单个文件 URL 为依据。
    首次修改前保存 index.html.bak；缺少引用文件或未识别到图片时停止。
    返回替换次数、保留文件数和待删除文件名，便于其他脚本调用。
    """
    input_dir = Path(input_dir).resolve(strict=True)
    index_path = input_dir / "index.html"
    optimized_dir = input_dir / "optimized"
    if not optimized_dir.is_dir():
        raise FileNotFoundError(f"图片目录不存在：{optimized_dir}")
    if optimized_dir.resolve() != optimized_dir:
        raise ValueError("optimized 不能是指向其他目录的链接。")

    original = index_path.read_bytes()
    # 使用 bytes 读写，保留原始换行符和可能存在的 UTF-8 BOM。
    html = original.decode("utf-8")
    remote_prefix = re.compile(
        r"https?://www\.deeperquant\.com:8888/+[^/]+/optimized/",
        re.IGNORECASE,
    )
    updated_html, replacements = remote_prefix.subn("optimized/", html)
    parser = ReferenceParser(input_dir)
    parser.feed(updated_html)
    parser.close()
    references = parser.references
    if not references:
        raise ValueError("未识别到 optimized 中的 PNG 引用，已停止，未修改任何文件。")
    missing = sorted(str(path) for path in references if not path.is_file())
    if missing:
        raise FileNotFoundError("引用的图片不存在，未修改任何文件：\n" + "\n".join(missing))

    unused = sorted(
        path for path in optimized_dir.iterdir()
        if path.is_file() and not path.is_symlink()
        and path.suffix.lower() == ".png" and path.resolve() not in references
    )
    result = {
        "replacements": replacements,
        "referenced_pngs": len(references),
        "unused_pngs": [path.name for path in unused],
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    if updated_html != html:
        backup_path = index_path.with_name("index.html.bak")
        # 不覆盖已有备份，保留首次执行前的内容。
        try:
            with backup_path.open("xb") as backup:
                backup.write(original)
        except FileExistsError:
            pass
        # 先完整保存 HTML，再删除图片，避免写入失败造成引用与文件不一致。
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=input_dir, delete=False) as temp:
                temp_path = Path(temp.name)
                temp.write(updated_html.encode("utf-8"))
            os.replace(temp_path, index_path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    for path in unused:
        path.unlink()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR, help="index.html 所在目录")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改 HTML、不删除图片")
    args = parser.parse_args()
    try:
        result = localize_images(args.input_dir, dry_run=args.dry_run)
    except (OSError, ValueError) as error:
        parser.exit(1, f"错误：{error}\n")
    print("预览（未修改文件）" if args.dry_run else "处理完成")
    print(f"远程目录前缀替换：{result['replacements']} 处（包括 HTML 内的源码注释）")
    print(f"保留引用图片：{result['referenced_pngs']} 张")
    print(f"{'待删除' if args.dry_run else '已删除'} PNG：{len(result['unused_pngs'])} 张")
    for name in result["unused_pngs"]:
        print(f"  {name}")


if __name__ == "__main__":
    main()
