#!/usr/bin/env python3
"""inspect_jsonl.py — extracted.jsonl 구조 정찰"""

import json
from collections import Counter, defaultdict
from pathlib import Path

JSONL_PATH = Path("data/processed/extracted.jsonl")
REPORT_PATH = Path("data/processed/inspect_report.json")


def get_paths(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_prefix = f"{prefix}.{k}" if prefix else k
            yield new_prefix
            yield from get_paths(v, new_prefix)
    elif isinstance(obj, list) and obj:
        yield from get_paths(obj[0], prefix + "[]")


def main():
    if not JSONL_PATH.exists():
        print(f"ERROR: {JSONL_PATH} 파일이 없습니다.")
        return 1

    records = []
    parse_errors = 0
    with JSONL_PATH.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                parse_errors += 1
                print(f"  [WARN] line {line_no} 파싱 실패: {e}")

    n = len(records)
    print(f"\n{'='*70}")
    print(f" extracted.jsonl 정찰 리포트")
    print(f"{'='*70}\n")
    print(f"총 레코드: {n}편")
    print(f"파싱 실패: {parse_errors}편")

    status_counts = Counter(r.get("extraction_status", "<missing>") for r in records)
    print(f"\n[1] extraction_status 분포")
    for status, count in status_counts.most_common():
        print(f"    {status:15s}: {count}편")

    pmids = [r.get("pmid") for r in records if r.get("pmid")]
    pmid_counts = Counter(pmids)
    duplicates = {p: c for p, c in pmid_counts.items() if c > 1}
    print(f"\n[2] PMID 중복")
    if duplicates:
        for pmid, count in duplicates.items():
            print(f"    {pmid}: {count}회 출현")
    else:
        print(f"    없음")

    exp_counts = [len(r.get("experiments", [])) for r in records]
    print(f"\n[3] 실험 수 분포")
    print(f"    총합: {sum(exp_counts)}개")
    print(f"    편당 평균: {sum(exp_counts) / max(n, 1):.2f}")
    print(f"    최대: {max(exp_counts) if exp_counts else 0}")
    by_count = Counter(exp_counts)
    for k in sorted(by_count.keys()):
        print(f"    {k}개 실험: {by_count[k]}편")

    all_paths = set()
    path_freq = defaultdict(int)
    for r in records:
        seen = set()
        for p in get_paths(r):
            all_paths.add(p)
            seen.add(p)
        for p in seen:
            path_freq[p] += 1

    print(f"\n[4] 발견된 필드 경로 ({len(all_paths)}개)")
    print(f"    (괄호: 해당 필드 보유 레코드 수 / 전체 {n})")
    for p in sorted(all_paths):
        depth = p.count(".") + p.count("[]")
        indent = "  " * min(depth, 5)
        print(f"    {indent}{p:55s} ({path_freq[p]}/{n})")

    success_records = [r for r in records if r.get("extraction_status") == "success"]
    if success_records:
        sample = success_records[0]
        print(f"\n[5] Success 샘플 (PMID {sample.get('pmid')})")
        if sample.get("experiments"):
            exp0 = sample["experiments"][0]
            print(f"    첫 실험 키 구조:")
            for path in sorted(get_paths(exp0, "exp")):
                print(f"      {path}")

    failed = [r for r in records if r.get("extraction_status") == "failed"]
    if failed:
        print(f"\n[6] FAILED: {len(failed)}편")
        for r in failed:
            print(f"    PMID {r.get('pmid')}")
    else:
        print(f"\n[6] FAILED: 없음")

    report = {
        "total_records": n,
        "parse_errors": parse_errors,
        "status_counts": dict(status_counts),
        "duplicates": duplicates,
        "experiment_counts": {
            "total": sum(exp_counts),
            "mean": sum(exp_counts) / max(n, 1),
            "max": max(exp_counts) if exp_counts else 0,
            "distribution": dict(by_count),
        },
        "field_paths": sorted(all_paths),
        "field_frequency": {p: path_freq[p] for p in sorted(all_paths)},
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*70}")
    print(f" 리포트 저장: {REPORT_PATH}")
    print(f"{'='*70}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())