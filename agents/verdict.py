# -*- coding: utf-8 -*-
"""核验员:按规则判定状态(五档),争议再探测。纯规则,不调 AI。
用法: python agents/verdict.py --provider openai --probe-status readable
      或不带参数跑全量过期清查。"""
import argparse, datetime, json, pathlib, sys, time
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"


def judge(probe_status, declared_ok, last_verified, ttl_days=7):
    """输入:实测状态、官方声明是否 ok、最后验证日期。
    输出: (status, reasons) —— 五档: verified/declared/reported/disputed/stale"""
    reasons = []
    today = datetime.date.today()
    stale = False
    if last_verified and last_verified != "unknown":
        try:
            age = (today - datetime.date.fromisoformat(str(last_verified))).days
            stale = age > (ttl_days or 7)
        except ValueError:
            stale = True
    if probe_status == "readable" and declared_ok:
        return "verified", ["probe ok + official ok"]
    if probe_status == "readable" and declared_ok is False:
        return "disputed", ["probe ok but official page says otherwise"]
    if probe_status in ("needs_key", "not_found") and declared_ok:
        s = "stale" if stale else "declared"
        return s, ["official only, no probe" + (" + past TTL" if stale else "")]
    if probe_status == "error" and declared_ok:
        s = "stale" if stale else "declared"
        return s, ["probe failed, official only" + (" + past TTL" if stale else "")]
    if declared_ok is None:
        return ("stale" if stale else "reported"), ["no official/probe evidence" + (" + past TTL" if stale else "")]
    if probe_status == "readable":
        s = "stale" if stale else "verified"
        return s, ["probe ok" + (" + past TTL" if stale else "")]
    return ("stale" if stale else "reported"), ["insufficient evidence"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="核验员")
    ap.add_argument("--provider")
    ap.add_argument("--probe-status", choices=["readable", "needs_key", "not_found", "error"])
    ap.add_argument("--major-quota-pct", type=int, help="额度下降百分比,判重大变化")
    args = ap.parse_args(argv)

    # 重大变化规则:额度大幅下调
    if args.major_quota_pct is not None:
        import yaml as _y
        with open(ROOT / "config/budgets.yaml", encoding="utf-8") as f:
            thr = _y.safe_load(f)["major_change"]["quota_drop_pct"]
        major = args.major_quota_pct >= thr
        print(json.dumps({"major_change": major, "threshold_pct": thr, "observed_pct": args.major_quota_pct}))
        return 0 if not major else 3  # 3 = 需要人工批准

    files = sorted(PROV.glob("*.yaml")) if not args.provider else [PROV / f"{args.provider}.yaml"]
    out = []
    for fp in files:
        if not fp.exists():
            print(f"missing {fp}", file=sys.stderr); return 2
        data = yaml.safe_load(fp.read_text(encoding="utf-8"))
        declared_ok = True if data.get("pricing_url") else None
        probe = args.probe_status  # 全量清查时没有新实测,沿用 unknown
        st, reasons = judge(probe, declared_ok, data.get("last_verified"))
        out.append({"provider": data["provider"], "status": st, "reasons": reasons})
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
