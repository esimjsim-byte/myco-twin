#!/usr/bin/env python3
"""
load_jsonl_to_db.py — extracted.jsonl → SQLite 로더

정찰(inspect_jsonl.py) 결과 기반으로 작성:
- UTF-8 BOM 자동 처리 (utf-8-sig)
- 7개 테이블 정규화: papers, study_metadata, analysis_notes,
  experiments, conditions, beta_glucan, outcomes(EAV 1:N)
- PMID 중복 자동 dedup (첫 출현 유지)

사용:
    uv run python scripts\\load_jsonl_to_db.py
"""

import json
import sqlite3
from pathlib import Path

JSONL_PATH = Path("data/processed/extracted.jsonl")
SCHEMA_PATH = Path("scripts/schema.sql")
DB_PATH = Path("data/processed/mycelium.db")


def load_jsonl(path: Path):
    """JSONL을 읽어 (records, dedup_log, parse_errors) 반환. BOM 자동 처리."""
    seen_pmids = set()
    records = []
    duplicates = []
    parse_errors = []

    with path.open(encoding="utf-8-sig") as f:  # ← BOM 자동 제거
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                parse_errors.append((line_no, str(e)))
                continue

            pmid = rec.get("pmid")
            if not pmid:
                parse_errors.append((line_no, "no pmid"))
                continue

            if pmid in seen_pmids:
                duplicates.append((line_no, pmid))
                continue

            seen_pmids.add(pmid)
            records.append(rec)

    return records, duplicates, parse_errors


def insert_paper(conn, rec):
    source = rec.get("source", {}) or {}
    conn.execute("""
        INSERT INTO papers (
            pmid, extraction_status, relevance_score, relevance_reason,
            extractor_model, extracted_at, input_tokens, output_tokens,
            estimated_cost_usd, section_used, warnings
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rec.get("pmid"),
        rec.get("extraction_status"),
        rec.get("relevance_score"),
        rec.get("relevance_reason"),
        source.get("extractor_model"),
        source.get("extracted_at"),
        source.get("input_tokens"),
        source.get("output_tokens"),
        source.get("estimated_cost_usd"),
        json.dumps(source.get("section_used", []), ensure_ascii=False),
        json.dumps(source.get("warnings", []), ensure_ascii=False),
    ))


def insert_study_metadata(conn, pmid, sm):
    if not sm:
        return
    conn.execute("""
        INSERT INTO study_metadata (
            pmid, strain, strain_notes, culture_mode, reactor_scale,
            reactor_volume_ml, optimization_method
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        pmid,
        sm.get("strain"),
        sm.get("strain_notes"),
        sm.get("culture_mode"),
        sm.get("reactor_scale"),
        sm.get("reactor_volume_ml"),
        sm.get("optimization_method"),
    ))


def insert_analysis_notes(conn, pmid, an):
    if not an:
        return
    conn.execute("""
        INSERT INTO analysis_notes (
            pmid, beta_glucan_analysis_method, statistical_design,
            polysaccharide_extraction, key_findings, notes
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        pmid,
        an.get("beta_glucan_analysis_method"),
        an.get("statistical_design"),
        an.get("polysaccharide_extraction"),
        an.get("key_findings"),
        an.get("notes"),
    ))


def insert_experiment(conn, pmid, exp):
    """experiments + conditions + beta_glucan + outcomes (1:N) 동시 삽입.
    experiment_pk 반환."""
    cur = conn.execute("""
        INSERT INTO experiments (pmid, experiment_id, description)
        VALUES (?, ?, ?)
    """, (
        pmid,
        exp.get("experiment_id"),
        exp.get("description"),
    ))
    exp_pk = cur.lastrowid

    # conditions (1:1)
    cond = exp.get("conditions")
    if cond:
        conn.execute("""
            INSERT INTO conditions (
                experiment_pk, carbon_source, carbon_concentration_g_L,
                nitrogen_source, nitrogen_concentration_g_L, cn_ratio,
                initial_pH, temperature_C, duration_days, agitation_rpm,
                inoculum_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exp_pk,
            cond.get("carbon_source"),
            cond.get("carbon_concentration_g_L"),
            cond.get("nitrogen_source"),
            cond.get("nitrogen_concentration_g_L"),
            cond.get("cn_ratio"),
            cond.get("initial_pH"),
            cond.get("temperature_C"),
            cond.get("duration_days"),
            cond.get("agitation_rpm"),
            cond.get("inoculum_percent"),
        ))

    # beta_glucan (1:1)
    bg = exp.get("beta_glucan")
    if bg:
        conn.execute("""
            INSERT INTO beta_glucan (
                experiment_pk, reported, total_value, total_unit,
                total_value_pct_dw, beta_1_3_value, beta_1_3_unit,
                beta_1_6_value, beta_1_6_unit, ratio_1_3_to_1_6,
                molecular_weight_kDa, is_lentinan_specific, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            exp_pk,
            1 if bg.get("reported") else 0,
            bg.get("total_value"),
            bg.get("total_unit"),
            bg.get("total_value_pct_dw"),
            bg.get("beta_1_3_value"),
            bg.get("beta_1_3_unit"),
            bg.get("beta_1_6_value"),
            bg.get("beta_1_6_unit"),
            bg.get("ratio_1_3_to_1_6"),
            bg.get("molecular_weight_kDa"),
            1 if bg.get("is_lentinan_specific") else 0,
            bg.get("notes"),
        ))

    # outcomes (1:N — EAV)
    outcomes = exp.get("outcomes") or []
    for out in outcomes:
        conn.execute("""
            INSERT INTO outcomes (
                experiment_pk, metric, metric_type, value, unit, value_g_L
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            exp_pk,
            out.get("metric"),
            out.get("metric_type"),
            out.get("value"),
            out.get("unit"),
            out.get("value_g_L"),
        ))

    return exp_pk


def main():
    if not JSONL_PATH.exists():
        print(f"ERROR: {JSONL_PATH} 파일이 없습니다.")
        return 1
    if not SCHEMA_PATH.exists():
        print(f"ERROR: {SCHEMA_PATH} 파일이 없습니다.")
        return 1

    # 1. JSONL 읽기
    print(f"[1/4] JSONL 읽기: {JSONL_PATH}")
    records, duplicates, parse_errors = load_jsonl(JSONL_PATH)
    print(f"      유효 레코드: {len(records)}편")
    if duplicates:
        print(f"      중복 PMID 제거: {len(duplicates)}건")
        for line_no, pmid in duplicates:
            print(f"        - line {line_no}: PMID {pmid}")
    if parse_errors:
        print(f"      파싱 오류: {len(parse_errors)}건")
        for line_no, msg in parse_errors:
            print(f"        - line {line_no}: {msg}")

    # 2. DB 초기화
    print(f"\n[2/4] DB 초기화: {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    print(f"      스키마 적용 완료")

    # 3. 데이터 삽입
    print(f"\n[3/4] 데이터 삽입")
    n_papers = 0
    n_experiments = 0
    n_outcomes_total = 0

    for rec in records:
        pmid = rec["pmid"]
        try:
            insert_paper(conn, rec)
            insert_study_metadata(conn, pmid, rec.get("study_metadata"))
            insert_analysis_notes(conn, pmid, rec.get("analysis_notes"))

            for exp in rec.get("experiments", []):
                insert_experiment(conn, pmid, exp)
                n_experiments += 1
                n_outcomes_total += len(exp.get("outcomes") or [])
        except Exception as e:
            print(f"      [ERROR] PMID {pmid}: {e}")
            raise

        n_papers += 1

    conn.commit()
    print(f"      papers       : {n_papers}")
    print(f"      experiments  : {n_experiments}")
    print(f"      outcomes(EAV): {n_outcomes_total}")

    # 4. 검증 쿼리
    print(f"\n[4/4] 검증")

    counts = conn.execute("""
        SELECT extraction_status, COUNT(*) FROM papers GROUP BY extraction_status
        ORDER BY COUNT(*) DESC
    """).fetchall()
    print(f"  status 분포:")
    for status, n in counts:
        print(f"    {status:15s}: {n}편")

    n_useful = conn.execute("SELECT COUNT(*) FROM v_useful_experiments").fetchone()[0]
    n_csl = conn.execute("SELECT COUNT(*) FROM v_csl_experiments").fetchone()[0]
    n_bg = conn.execute("SELECT COUNT(*) FROM v_beta_glucan_experiments").fetchone()[0]
    n_biomass = conn.execute("SELECT COUNT(*) FROM v_biomass_experiments").fetchone()[0]
    print(f"\n  view 결과:")
    print(f"    v_useful_experiments     : {n_useful}개 실험")
    print(f"    v_csl_experiments        : {n_csl}개 실험")
    print(f"    v_beta_glucan_experiments: {n_bg}개 실험")
    print(f"    v_biomass_experiments    : {n_biomass}개 (outcomes JOIN)")

    # 외래키 무결성 검증
    fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_issues:
        print(f"\n  [ERROR] 외래키 무결성 문제: {len(fk_issues)}건")
        for row in fk_issues[:5]:
            print(f"    {row}")
    else:
        print(f"\n  외래키 무결성: OK")

    conn.close()
    print(f"\n{'='*60}")
    print(f" DB 저장 완료: {DB_PATH}")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
