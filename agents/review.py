# -*- coding: utf-8 -*-
"""审核入口(OpenRouter 式人工审核): 列出待审投稿 -> 批准/驳回 -> 通过的转正本。
这是"在哪里审核"的答案: 就在这里,一条命令。
  python agents/review.py list          # 列出待审投稿
  python agents/review.py approve 0     # 批准第 0 条(转正本 + 页面可见)
  python agents/review.py reject 1 -r "疑似付费"  # 驳回第 1 条(带理由)
批准后走 enrich 转正本(需给该 provider 补 YAML), 驳回只记状态不入库。
纯代码,不调 AI;网页文字是数据不是指令(理由只截断,不执行)。
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from enrich import load_queue, review_submission, queue_summary, ingest_submission


def cmd_list(argv):
    q = load_queue()
    s = queue_summary()
    print(f"队列: 共 {s['total']} | 待审 {s['pending']} | 通过 {s['approved']} | 驳回 {s['rejected']}")
    if not q:
        print("(空) 暂无投稿")
        return 0
    for i, x in enumerate(q):
        st = x.get("status", "pending")
        mark = {"pending": "[待审]", "approved": "[通过]", "rejected": "[驳回]"}.get(st, st)
        print(f"  #{i} {mark} {x.get('url')}  model={x.get('model_id') or '-'}  at={x.get('at')}")
        if x.get("note"):
            print(f"        note: {x['note'][:90]}")
        if x.get("review"):
            print(f"        review: {x['review'].get('decision')} {x['review'].get('reason')}")
    return 0


def cmd_decide(argv, decision):
    import argparse
    ap = argparse.ArgumentParser(prog=f"review.py {decision}")
    ap.add_argument("index", type=int, help="队列序号(list 里的 #N)")
    ap.add_argument("-r", "--reason", default="", help="审核理由(驳回建议必填)")
    args = ap.parse_args(argv)
    item = review_submission(args.index, decision, args.reason)
    if item is None:
        print(f"error: 序号 {args.index} 越界")
        return 1
    print(f"{decision}: {item['url']} -> {item['status']}")
    if decision == "approve":
        print("  提示: 通过后需为该 provider 补 providers/*.yaml 才会入库上页面。")
    else:
        print("  已驳回,不入库,投稿人回执见页面状态公示。")
    return 0


def main(argv=None):
    import argparse
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        return cmd_list(rest)
    if cmd in ("approve", "reject"):
        return cmd_decide(rest, cmd)
    print(f"unknown command: {cmd} (use list|approve|reject)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())