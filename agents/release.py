# -*- coding: utf-8 -*-
"""发布员(新增免费模型 -> GitHub Release): 对比本轮与上一轮 free-models.json,
有新增免费模型就打一个 tag + Release(带新模型清单), 触发 GitHub Watch→Releases 通知。
没有新增就跳过(不发空 Release)。纯代码,不调 AI,不碰密钥(用 Actions 内置 GITHUB_TOKEN)。
用法: python agents/release.py --baseline <上一轮json>  (默认比 docs/free-models.baseline.json)
"""
import json, pathlib, sys, time, os

ROOT = pathlib.Path(__file__).resolve().parents[1]
CUR = ROOT / "docs" / "free-models.json"


def _ids(data):
    """一组免费模型的 (provider,id) 集合(以 id 为主)。"""
    return {m.get("id") for m in (data or {}).get("models", []) if m.get("free")}


def diff_new(baseline_path, cur_path=CUR):
    """本轮比基线多出的免费模型(按 id)。基线缺失=首轮,全部算新增(但首轮不发,见 main)。"""
    def load(p):
        try:
            return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        except Exception:
            return None
    base = load(baseline_path)
    cur = load(cur_path)
    if cur is None:
        return None, [], True          # 本轮没数据 -> 跳过
    if base is None:
        return None, [], True          # 首轮无基线 -> 跳过(不为存量发一堆 Release)
    new = sorted(_ids(cur) - _ids(base))
    return cur, new, False


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="新增免费模型 -> GitHub Release")
    ap.add_argument("--baseline", default=str(ROOT / "docs" / "free-models.baseline.json"),
                    help="上一轮 free-models.json 路径")
    ap.add_argument("--force", action="store_true", help="强制发(忽略 diff,调试用)")
    args = ap.parse_args(argv)

    if not CUR.exists():
        print("release: no current free-models.json, skip")
        return 0
    cur, new, skip = diff_new(args.baseline)
    if skip:
        print("release: no baseline/cur, skip (first run or missing)")
        return 0
    if not new and not args.force:
        print("release: no new free models (%d total), skip" % len(_ids(cur)))
        return 0

    # tag: vYYYYMMDDHHMM 同秒重跑加后缀
    tag = "v" + time.strftime("%Y%m%d%H%M", time.gmtime())
    total = len(_ids(cur))
    title = f"免费模型 +%d 新增 (现共 %d)" % (len(new), total)
    # Release body: 新增清单
    lines = [f"新增 **{len(new)}** 个免费模型, 现共 **{total}** 个。", ""]
    lines += [f"- `{i}`" for i in new[:60]]
    if len(new) > 60:
        lines.append(f"- ...另 {len(new)-60} 个")
    lines += ["", f"页面: https://vbk-ai-agent-gateway.github.io/free-ai-radar/"]
    body = "\n".join(lines)

    # 交给 gh CLI(Actions 内置)。GITHUB_TOKEN 由 env 提供。
    import subprocess
    env = dict(os.environ)
    gh = _which_gh()
    if not gh:
        print("release: gh CLI not found, fallback to API")
        return _api_release(tag, title, body)
    r = subprocess.run([gh, "release", "create", tag,
                        "--title", title, "--notes", body,
                        "--latest"],
                       capture_output=True, text=True, env=env,
                       cwd=str(ROOT))
    if r.returncode == 0:
        print(f"release: created {tag} (+{len(new)} models)")
        return 0
    print(f"release: gh failed ({r.returncode}): {(r.stderr or r.stdout)[:300]}")
    # tag 可能已存在(同分钟重跑) -> API 兜底
    return _api_release(tag, title, body)


def _which_gh():
    import shutil
    return shutil.which("gh")


def _api_release(tag, title, body):
    """gh 失败时用 REST API 发 release(需 GITHUB_TOKEN + repo)。"""
    tok = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        print("release: no GITHUB_TOKEN/REPO, cannot fallback")
        return 1
    import urllib.request, urllib.error
    payload = {"tag_name": tag, "name": title, "body": body, "draft": False, "prerelease": False}
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {tok}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "free-ai-radar"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"release: created {tag} via API ({resp.status})")
            return 0
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:200]
        if e.code == 422 and "already_exists" in err:
            print("release: tag exists, skip")
            return 0
        print(f"release: API fail {e.code}: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())