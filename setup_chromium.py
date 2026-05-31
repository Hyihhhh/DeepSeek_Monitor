"""
Chromium 浏览器离线包安装脚本（国内用户一键安装）

从 GitHub Releases 下载预打包的 Chromium，解压到项目 browser/ 目录。
支持单个 zip 和分片下载（当单文件 >25MB 时自动使用分片模式）。

用法:
    python setup_chromium.py

手动下载（如果脚本下载失败）:
    访问 https://github.com/Hyihhhh/DeepSeek_Monitor/releases
    找到 chromium-bundle 标签，下载所有 chromium-win.part001.zip, .part002.zip ... 分片
    放到项目根目录，然后运行 python setup_chromium.py --local
"""
import os
import sys
import zipfile
import logging
import urllib.request
import urllib.error
import shutil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# GitHub Releases 下载地址基础路径
BASE_URL = (
    "https://github.com/Hyihhhh/DeepSeek_Monitor/releases/download/"
    "chromium-bundle"
)
SINGLE_ZIP_URL = f"{BASE_URL}/chromium-win.zip"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BROWSER_DIR = os.path.join(PROJECT_DIR, "browser")
CHROME_EXE = os.path.join(BROWSER_DIR, "chrome-win", "chrome.exe")


def is_installed():
    """检查 Chromium 是否已安装（文件存在且大小合理）。"""
    if os.path.isfile(CHROME_EXE):
        size_mb = os.path.getsize(CHROME_EXE) / (1024 * 1024)
        if size_mb > 50:
            logger.info(f"Chromium 已安装: {CHROME_EXE} ({size_mb:.0f} MB)")
            return True
        else:
            logger.warning(f"检测到损坏的文件（{size_mb:.0f} MB），将重新下载")
            shutil.rmtree(BROWSER_DIR, ignore_errors=True)
    return False


def _download_file(url, dest):
    """下载单个文件，返回 True/False。"""
    try:
        urllib.request.urlretrieve(url, dest)
        return True
    except Exception:
        return False


def download_with_progress(url, dest, label=""):
    """带进度条的单文件下载。"""
    logger.info(f"下载{' ' + label if label else ''}: {os.path.basename(dest)}")

    def _progress(block_count, block_size, total_size):
        downloaded = block_count * block_size
        if total_size > 0:
            percent = min(100, downloaded * 100 / total_size)
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            bar_len = 30
            filled = int(bar_len * percent / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\r  [{bar}] {percent:5.1f}%  {downloaded_mb:5.1f}/{total_mb:.1f} MB",
                  end="", flush=True)

    try:
        urllib.request.urlretrieve(url, dest, _progress)
        print()
        return True
    except Exception as e:
        print()
        logger.error(f"下载失败: {e}")
        return False


def download_chunks():
    """尝试下载分片文件，返回合并后的 zip 路径或 None。"""
    zip_path = os.path.join(PROJECT_DIR, "chromium-win.zip")
    chunks_dir = os.path.join(PROJECT_DIR, "chromium-chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    logger.info("尝试分片下载模式...")
    chunks = []
    for i in range(100):  # 最多 100 个分片
        chunk_name = f"chromium-win.part{i+1:03d}.zip"
        chunk_url = f"{BASE_URL}/{chunk_name}"
        chunk_path = os.path.join(chunks_dir, chunk_name)

        if i == 0:
            logger.info(f"正在下载分片 {i+1}...")

        if not _download_file(chunk_url, chunk_path):
            if i == 0:
                logger.error("未找到任何分片文件")
                shutil.rmtree(chunks_dir, ignore_errors=True)
                return None
            break

        size_kb = os.path.getsize(chunk_path) / 1024
        print(f"\r  分片 {i+1}: {size_kb:.0f} KB ✓")
        chunks.append(chunk_path)
    else:
        logger.error("分片数量异常（>100），终止")
        return None

    logger.info(f"共下载 {len(chunks)} 个分片，正在合并...")

    # 合并分片
    with open(zip_path, "wb") as outf:
        for i, chunk_path in enumerate(chunks):
            with open(chunk_path, "rb") as inf:
                outf.write(inf.read())
            os.remove(chunk_path)  # 逐个清理分片

    shutil.rmtree(chunks_dir, ignore_errors=True)

    total_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info(f"合并完成: {total_mb:.1f} MB")
    return zip_path


def download_single():
    """尝试下载单个 zip 文件，返回路径或 None。"""
    zip_path = os.path.join(PROJECT_DIR, "chromium-win.zip")
    logger.info("尝试单文件下载模式...")
    if download_with_progress(SINGLE_ZIP_URL, zip_path):
        total_mb = os.path.getsize(zip_path) / (1024 * 1024)
        logger.info(f"下载完成: {total_mb:.1f} MB")
        return zip_path
    return None


def extract_chromium(zip_path):
    """解压 Chromium zip 到 browser/ 目录。"""
    logger.info(f"正在解压到 {BROWSER_DIR} ...")
    os.makedirs(BROWSER_DIR, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        total = len(zf.namelist())
        for i, member in enumerate(zf.namelist(), 1):
            zf.extract(member, BROWSER_DIR)
            if i % 200 == 0 or i == total:
                print(f"\r  解压中... {i}/{total} ({i*100//total}%)",
                      end="", flush=True)
        print()


def try_local_chunks():
    """尝试使用本地已有的分片文件合并。"""
    zip_path = os.path.join(PROJECT_DIR, "chromium-win.zip")

    # 查找项目根目录下的分片文件
    chunks = []
    for i in range(100):
        chunk_name = f"chromium-win.part{i+1:03d}.zip"
        chunk_path = os.path.join(PROJECT_DIR, chunk_name)
        if os.path.isfile(chunk_path):
            chunks.append(chunk_path)
        else:
            break

    if not chunks:
        logger.error("未在项目根目录找到分片文件 (chromium-win.part001.zip, ...)")
        return None

    logger.info(f"找到 {len(chunks)} 个本地分片，正在合并...")
    with open(zip_path, "wb") as outf:
        for chunk_path in chunks:
            with open(chunk_path, "rb") as inf:
                outf.write(inf.read())

    total_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info(f"合并完成: {total_mb:.1f} MB")
    return zip_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Chromium 浏览器离线包安装")
    parser.add_argument("--local", action="store_true",
                        help="使用本地已有的分片文件，不联网下载")
    args = parser.parse_args()

    print("=" * 55)
    print("  DeepSeek Monitor — Chromium 浏览器离线包安装")
    print("=" * 55)
    print()

    # 检查平台
    if sys.platform != "win32":
        logger.warning("当前仅支持 Windows 离线包。")
        logger.info("macOS/Linux 请使用系统浏览器: 设置 CHROMIUM_PATH 环境变量")
        logger.info("或运行: playwright install chromium")
        return

    # 已安装则跳过
    if is_installed():
        print()
        print("✅ Chromium 已就绪，可以直接启动:")
        print("   python desktop.py")
        return

    # 下载 / 合并
    zip_path = None

    if args.local:
        zip_path = try_local_chunks()
    else:
        # 策略：先尝试单文件，失败则尝试分片
        zip_path = download_single()
        if not zip_path:
            print()
            logger.info("单文件下载失败，切换到分片模式...")
            zip_path = download_chunks()

    if not zip_path:
        print()
        print("❌ 自动下载失败，请尝试手动安装：")
        print("   1. 浏览器打开: https://github.com/Hyihhhh/DeepSeek_Monitor/releases")
        print("   2. 找到 chromium-bundle 标签")
        print("   3. 下载所有 chromium-win.part001.zip, .part002.zip ... 分片文件")
        print(f"   4. 把分片文件放到项目根目录: {PROJECT_DIR}")
        print("   5. 运行: python setup_chromium.py --local")
        return

    # 解压
    try:
        extract_chromium(zip_path)
    except Exception as e:
        logger.error(f"解压失败: {e}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return

    # 清理 zip
    os.remove(zip_path)
    logger.info("已清理临时文件")

    # 验证
    if is_installed():
        print()
        print("✅ 安装完成！Chromium 已就绪。")
        print()
        print("现在可以启动应用：")
        print("   python desktop.py")
    else:
        print()
        print("❌ 安装验证失败，请检查 browser/chrome-win/chrome.exe 是否存在")
        print("   如果问题持续，请尝试手动安装（见上方说明）")


if __name__ == "__main__":
    main()
