"""setup_extra_views.py — 추가 view 생성 + 데이터 풍경 확인."""
import sqlite3
from pathlib import Path

DB = Path("data/processed/mycelium.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ============ 추가 view 생성 ============
conn.executescript("""
DROP VIEW IF EXISTS v_dry_weight;
CREATE VIEW v_dry_weight AS
SELECT
    ue.pmid, ue.experiment_pk, ue.experiment_id,
    ue.strain, ue.culture_mode,
    ue.carbon_source, ue.carbon_concentration_g_L,
    ue.nitrogen_source, ue.nitrogen_concentration_g_L,
    ue.cn_ratio, ue.initial_pH, ue.temperature_C,
    ue.duration_days, ue.agitation_rpm, ue.inoculum_percent,
    o.metric, o.value, o.unit, o.value_g_L
FROM v_useful_experiments ue
JOIN outcomes o ON ue.experiment_pk = o.experiment_pk
WHERE o.metric_type = 'mycelial_dry_weight';

DROP VIEW IF EXISTS v_protein;
CREATE VIEW v_protein AS
SELECT
    ue.pmid, ue.experiment_pk,
    ue.carbon_source, ue.nitrogen_source,
    o.metric, o.value, o.unit
FROM v_useful_experiments ue
JOIN outcomes o ON ue.experiment_pk = o.experiment_pk
WHERE o.metric_type = 'protein_content';

DROP VIEW IF EXISTS v_polysaccharide;
CREATE VIEW v_polysaccharide AS
SELECT
    ue.pmid, ue.experiment_pk,
    ue.carbon_source, ue.nitrogen_source,
    o.metric, o.metric_type, o.value, o.unit, o.value_g_L
FROM v_useful_experiments ue
JOIN outcomes o ON ue.experiment_pk = o.experiment_pk
WHERE o.metric_type IN ('total_polysaccharide', 'intracellular_polysaccharide', 'extracellular_polysaccharide');
""")
conn.commit()


# ============ 데이터 풍경 출력 ============
def show(title, sql):
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("(빈 결과)")
        return
    keys = rows[0].keys()
    print(" | ".join(keys))
    print("-" * 70)
    for r in rows:
        vals = []
        for k in keys:
            v = r[k]
            if v is None:
                vals.append("NULL")
            elif isinstance(v, float):
                vals.append(f"{v:.2f}")
            elif isinstance(v, str) and len(v) > 30:
                vals.append(v[:27] + "...")
            else:
                vals.append(str(v))
        print(" | ".join(vals))
    print(f"\n총 {len(rows)}행")


# 1. 새 view 행 수 확인
print("\n=== 추가 view 행 수 ===")
for v in ["v_dry_weight", "v_protein", "v_polysaccharide"]:
    n = conn.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
    print(f"  {v}: {n} rows")

# 2. dry_weight 데이터 (32개 예상)
show(
    "[1] mycelial_dry_weight 측정값 (정확하게)",
    """
    SELECT pmid, metric, value, unit, value_g_L,
           agitation_rpm, temperature_C
    FROM v_dry_weight
    ORDER BY pmid, value_g_L DESC NULLS LAST
    """
)

# 3. culture_mode 분포
show(
    "[2] culture_mode 분포 (55편)",
    """
    SELECT culture_mode, COUNT(*) AS n
    FROM study_metadata
    GROUP BY culture_mode
    ORDER BY n DESC
    """
)

# 4. optimization_method 분포
show(
    "[3] optimization_method 분포",
    """
    SELECT optimization_method, COUNT(*) AS n
    FROM study_metadata
    GROUP BY optimization_method
    ORDER BY n DESC
    """
)

# 5. 가장 다채로운 논문 top 5
show(
    "[4] 실험 수 상위 5개 논문",
    """
    SELECT p.pmid, COUNT(e.experiment_pk) AS n_exp, p.relevance_score
    FROM papers p
    JOIN experiments e ON p.pmid = e.pmid
    GROUP BY p.pmid
    ORDER BY n_exp DESC
    LIMIT 5
    """
)

conn.close()