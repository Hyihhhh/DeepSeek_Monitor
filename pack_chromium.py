"""
打包 Playwright Chromium 为 GitHub Releases 离线包。

用法:
    python pack_chromium.py            # 打包单个 zip
    python pack_chromium.py --split    # 分割为 25MB 分片（网页上传备选）

上传方式（二选一）:
    1. gh CLI（推荐，支持大文件）: gh release upload chromium-bundle chromium-win.zip
    2. 网页上传: 用 --split 分包，每片 <25MB
"""
import os
import sys
import zipfile
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def find_chromium_dir():
    """通过 Playwright API 找到已安装的 Chromium 目录。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright 未安装，请先运行: pip install playwright")
        sys.exit(1)

    with sync_playwright() as p:
        exe = p.chromium.executable_path
        if not exe or not os.path.isfile(exe):
            logger.error(
                "未找到 Playwright Chromium，请先运行: playwright install chromium"
            )
            sys.exit(1)

        # exe 路径如: ...\ms-playwright\chromium-1200\chrome-win\chrome.exe
        chrome_dir = os.path.dirname(exe)  # chrome-win/
        revision = os.path.basename(os.path.dirname(chrome_dir))  # chromium-1200
        logger.info(f"找到 Chromium: {exe}")
        logger.info(f"版本: {revision}")
        return chrome_dir, revision


def pack_chromium(chrome_dir, output_name="chromium-win.zip"):
    """将 chrome-win/ 目录打包为 zip 文件。"""
    project_root = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(project_root, output_name)

    logger.info(f"正在打包 {chrome_dir} → {output_path} ...")

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(chrome_dir):
            for fname in files:
                file_path = os.path.join(root, fname)
                # zip 内的路径：chrome-win/xxx/yyy
                arcname = os.path.join(
                    os.path.basename(chrome_dir),
                    os.path.relpath(file_path, chrome_dir),
                )
                zf.write(file_path, arcname)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"打包完成: {output_path} ({size_mb:.1f} MB)")
    return output_path


def split_zip(zip_path, chunk_size=25 * 1024 * 1024):
    """将大 zip 分割为 25MB 分片，绕过 GitHub 网页上传限制。"""
    chunk_dir = zip_path + ".parts"
    os.makedirs(chunk_dir, exist_ok=True)
    total_size = os.path.getsize(zip_path)
    total_chunks = (total_size + chunk_size - 1) // chunk_size

    logger.info(f"正在分割 {total_size / (1024*1024):.0f} MB → {total_chunks} 个分片 ...")

    with open(zip_path, "rb") as f:
        for i in range(total_chunks):
            chunk_data = f.read(chunk_size)
            chunk_name = f"chromium-win.part{i+1:03d}.zip"
            chunk_path = os.path.join(chunk_dir, chunk_name)
            with open(chunk_path, "wb") as cf:
                cf.write(chunk_data)
            logger.info(f"  [{i+1}/{total_chunks}] {chunk_name} "
                        f"({len(chunk_data) / (1024*1024):.1f} MB)")

    logger.info(f"分片完成 → {chunk_dir}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="打包 Playwright Chromium")
    parser.add_argument("--split", action="store_true",
                        help="分割为 25MB 分片，用于 GitHub 网页上传")
    args = parser.parse_args()

    logger.info("=== Playwright Chromium 打包工具 ===")
    chrome_dir, revision = find_chromium_dir()
    output = pack_chromium(chrome_dir)

    if args.split:
        split_zip(output)
        os.remove(output)

    print()
    print("✅ 打包完成！")
    print()

    if args.split:
        chunk_dir = output + ".parts"
        print(f"   分片目录: {chunk_dir}")
        print(f"   分片数量: {len(os.listdir(chunk_dir))} 个")
        print()
        print("下一步（网页上传）：")
        print("  1. 前往 https://github.com/Hyihhhh/DeepSeek_Monitor/releases")
        print('  2. 创建/编辑 Release，tag 填: chromium-bundle')
        print(f"  3. 把目录下所有 .part001.zip .part002.zip ... 分片上传为附件")
        print("  4. 发布 Release")
    else:
        print(f"   文件: {output}")
        print()
        print("下一步（推荐用 gh CLI 上传，支持大文件）：")
        print('  gh release create chromium-bundle chromium-win.zip \\')
        print('    --title "Chromium 离线包" --notes "Playwright Chromium 离线包"')
        print()
        print("  或者更新已有的 Release：")
        print('  gh release upload chromium-bundle chromium-win.zip --clobber')
        print()
        print("  如果没有安装 gh CLI：")
        print("    winget install GitHub.cli")
        print("  或者用网页上传（需分包）：")
        print("    python pack_chromium.py --split")


if __name__ == "__main__":
    main()
