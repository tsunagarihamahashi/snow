"""
Local deploy to Xserver over FTPS, using credentials from .env (same names as the GitHub Secrets).

    python tools/deploy_xserver.py --check   # ログインとディレクトリの確認だけ（何もアップロードしない）
    python tools/deploy_xserver.py           # build.py を実行して公開ファイルをアップロード

普段は GitHub Actions が自動でアップロードするので、このスクリプトは接続確認や初回投入用。
"""
import argparse
import ftplib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_FILES = ["index.html", "snow_data.json"]
UPLOAD_GLOBS = ["lp_prototype_*.html"]
UPLOAD_DIRS = ["assets"]


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        sys.exit(f".env が見つかりません。{path.parent / '.env.example'} をコピーして .env を作成してください。")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    missing = [k for k in ("XSERVER_FTP_HOST", "XSERVER_FTP_USER", "XSERVER_FTP_PASSWORD") if not env.get(k)]
    if missing:
        sys.exit(f".env に未設定の項目があります: {', '.join(missing)}")
    env.setdefault("XSERVER_REMOTE_DIR", "/")
    return env


def connect(env: dict) -> ftplib.FTP_TLS:
    ftp = ftplib.FTP_TLS(timeout=30)
    ftp.connect(env["XSERVER_FTP_HOST"], 21)
    ftp.login(env["XSERVER_FTP_USER"], env["XSERVER_FTP_PASSWORD"])
    ftp.prot_p()  # データ接続も暗号化
    ftp.encoding = "utf-8"
    return ftp


def ensure_dir(ftp: ftplib.FTP_TLS, remote: str):
    parts = [p for p in remote.strip("/").split("/") if p]
    ftp.cwd("/")
    for p in parts:
        try:
            ftp.cwd(p)
        except ftplib.error_perm:
            ftp.mkd(p)
            ftp.cwd(p)


def upload_file(ftp: ftplib.FTP_TLS, local: Path, remote_name: str):
    with local.open("rb") as f:
        ftp.storbinary(f"STOR {remote_name}", f)
    print("  up", remote_name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="接続とディレクトリの確認のみ")
    args = ap.parse_args()

    env = load_env(ROOT / ".env")
    remote_dir = env["XSERVER_REMOTE_DIR"]

    print(f"connecting to {env['XSERVER_FTP_HOST']} as {env['XSERVER_FTP_USER']} ...")
    ftp = connect(env)
    print("login ok:", ftp.getwelcome().splitlines()[0])
    ensure_dir(ftp, remote_dir)
    print("remote dir:", ftp.pwd())
    if args.check:
        names = ftp.nlst()
        print(f"{len(names)} entries:", ", ".join(sorted(names)[:15]))
        ftp.quit()
        return

    print("building pages ...")
    subprocess.run([sys.executable, str(ROOT / "build.py")], check=True, cwd=ROOT)

    files = [ROOT / f for f in UPLOAD_FILES]
    for g in UPLOAD_GLOBS:
        files += sorted(ROOT.glob(g))
    for f in files:
        upload_file(ftp, f, f.name)
    for d in UPLOAD_DIRS:
        ensure_dir(ftp, remote_dir.rstrip("/") + "/" + d)
        for f in sorted((ROOT / d).iterdir()):
            if f.is_file():
                upload_file(ftp, f, f.name)
        ensure_dir(ftp, remote_dir)
    ftp.quit()
    print("done:", len(files), "files +", ", ".join(UPLOAD_DIRS))


if __name__ == "__main__":
    main()
