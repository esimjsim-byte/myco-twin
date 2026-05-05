-- ============================================================================
-- mycelium-db SQLite Schema v2 (Step 3, 정찰 결과 반영)
-- 2026-04-22 · 실제 extracted.jsonl 구조에 맞춰 재설계
--
-- 7-테이블 정규화:
--   papers · study_metadata · analysis_notes
--   experiments · conditions · beta_glucan · outcomes(1:N, EAV)
--
-- 사용:
--   sqlite3 data\processed\mycelium.db < scripts\schema.sql
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ============================================================================
-- Table 1: papers — 논문 메타 + 추출 메타
-- ============================================================================
CREATE TABLE IF NOT EXISTS papers (
    pmid                TEXT PRIMARY KEY,

    extraction_status   TEXT NOT NULL CHECK (
        extraction_status IN ('success', 'partial', 'failed', 'not_relevant')
    ),
    relevance_score     REAL CHECK (relevance_score >= 0 AND relevance_score <= 1),
    relevance_reason    TEXT,

    -- source 객체 평탄화
    extractor_model     TEXT,
    extracted_at        TEXT,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    estimated_cost_usd  REAL,
    section_used        TEXT,                    -- JSON array
    warnings            TEXT                     -- JSON array
);

CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(extraction_status);


-- ============================================================================
-- Table 2: study_metadata — 1:1 with papers
-- ============================================================================
CREATE TABLE IF NOT EXISTS study_metadata (
    pmid                TEXT PRIMARY KEY,
    strain              TEXT,
    strain_notes        TEXT,
    culture_mode        TEXT,
    reactor_scale       TEXT,
    reactor_volume_ml   REAL,
    optimization_method TEXT,

    FOREIGN KEY (pmid) REFERENCES papers(pmid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_smeta_culture ON study_metadata(culture_mode);
CREATE INDEX IF NOT EXISTS idx_smeta_optim ON study_metadata(optimization_method);


-- ============================================================================
-- Table 3: analysis_notes — 1:1 with papers
-- ============================================================================
CREATE TABLE IF NOT EXISTS analysis_notes (
    pmid                            TEXT PRIMARY KEY,
    beta_glucan_analysis_method     TEXT,
    statistical_design              TEXT,
    polysaccharide_extraction       TEXT,
    key_findings                    TEXT,
    notes                           TEXT,

    FOREIGN KEY (pmid) REFERENCES papers(pmid) ON DELETE CASCADE
);


-- ============================================================================
-- Table 4: experiments — 1 paper → N experiments
-- ============================================================================
CREATE TABLE IF NOT EXISTS experiments (
    experiment_pk       INTEGER PRIMARY KEY AUTOINCREMENT,
    pmid                TEXT NOT NULL,
    experiment_id       TEXT,
    description         TEXT,

    FOREIGN KEY (pmid) REFERENCES papers(pmid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_exp_pmid ON experiments(pmid);


-- ============================================================================
-- Table 5: conditions — 1:1 with experiments
-- ============================================================================
CREATE TABLE IF NOT EXISTS conditions (
    experiment_pk               INTEGER PRIMARY KEY,
    carbon_source               TEXT,
    carbon_concentration_g_L    REAL,
    nitrogen_source             TEXT,
    nitrogen_concentration_g_L  REAL,
    cn_ratio                    REAL,
    initial_pH                  REAL CHECK (initial_pH IS NULL OR (initial_pH > 0 AND initial_pH < 14)),
    temperature_C               REAL,
    duration_days               REAL,
    agitation_rpm               REAL,
    inoculum_percent            REAL,

    FOREIGN KEY (experiment_pk) REFERENCES experiments(experiment_pk) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cond_carbon ON conditions(carbon_source);
CREATE INDEX IF NOT EXISTS idx_cond_nitrogen ON conditions(nitrogen_source);


-- ============================================================================
-- Table 6: beta_glucan — 1:1 with experiments (β-glucan 전용)
-- ============================================================================
CREATE TABLE IF NOT EXISTS beta_glucan (
    experiment_pk           INTEGER PRIMARY KEY,
    reported                INTEGER NOT NULL DEFAULT 0 CHECK (reported IN (0, 1)),
    total_value             REAL,
    total_unit              TEXT,
    total_value_pct_dw      REAL,
    beta_1_3_value          REAL,
    beta_1_3_unit           TEXT,
    beta_1_6_value          REAL,
    beta_1_6_unit           TEXT,
    ratio_1_3_to_1_6        REAL,
    molecular_weight_kDa    REAL,
    is_lentinan_specific    INTEGER NOT NULL DEFAULT 0 CHECK (is_lentinan_specific IN (0, 1)),
    notes                   TEXT,

    FOREIGN KEY (experiment_pk) REFERENCES experiments(experiment_pk) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bg_reported ON beta_glucan(reported);


-- ============================================================================
-- Table 7: outcomes — 1:N with experiments (EAV 패턴)
-- ============================================================================
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_pk   INTEGER NOT NULL,
    metric          TEXT NOT NULL,
    metric_type     TEXT,
    value           REAL,
    unit            TEXT,
    value_g_L       REAL,

    FOREIGN KEY (experiment_pk) REFERENCES experiments(experiment_pk) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_outcomes_exp ON outcomes(experiment_pk);
CREATE INDEX IF NOT EXISTS idx_outcomes_metric ON outcomes(metric);
CREATE INDEX IF NOT EXISTS idx_outcomes_type ON outcomes(metric_type);


-- ============================================================================
-- View 1: 분석용 핵심 view (success + partial, conditions + beta_glucan)
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_useful_experiments AS
SELECT
    p.pmid,
    p.extraction_status,
    p.relevance_score,
    sm.strain,
    sm.culture_mode,
    sm.reactor_scale,
    sm.optimization_method,
    e.experiment_pk,
    e.experiment_id,
    e.description,
    c.carbon_source,
    c.carbon_concentration_g_L,
    c.nitrogen_source,
    c.nitrogen_concentration_g_L,
    c.cn_ratio,
    c.initial_pH,
    c.temperature_C,
    c.duration_days,
    c.agitation_rpm,
    c.inoculum_percent,
    bg.reported AS bg_reported,
    bg.total_value AS bg_total_value,
    bg.total_unit AS bg_total_unit,
    bg.total_value_pct_dw AS bg_pct_dw,
    bg.beta_1_3_value,
    bg.beta_1_6_value,
    bg.ratio_1_3_to_1_6,
    bg.molecular_weight_kDa AS bg_mw_kDa,
    bg.is_lentinan_specific
FROM papers p
LEFT JOIN study_metadata sm ON p.pmid = sm.pmid
JOIN experiments e ON p.pmid = e.pmid
LEFT JOIN conditions c ON e.experiment_pk = c.experiment_pk
LEFT JOIN beta_glucan bg ON e.experiment_pk = bg.experiment_pk
WHERE p.extraction_status IN ('success', 'partial');


-- ============================================================================
-- View 2: CSL 기반 실험만
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_csl_experiments AS
SELECT * FROM v_useful_experiments
WHERE
    LOWER(nitrogen_source) LIKE '%csl%'
 OR LOWER(nitrogen_source) LIKE '%corn steep%'
 OR LOWER(nitrogen_source) LIKE '%steep liquor%';


-- ============================================================================
-- View 3: β-glucan 측정된 실험만
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_beta_glucan_experiments AS
SELECT * FROM v_useful_experiments
WHERE bg_reported = 1;


-- ============================================================================
-- View 4: biomass 측정된 실험만 (outcomes 테이블 활용)
-- ============================================================================
CREATE VIEW IF NOT EXISTS v_biomass_experiments AS
SELECT
    ue.*,
    o.value AS biomass_value,
    o.unit AS biomass_unit,
    o.value_g_L AS biomass_g_L
FROM v_useful_experiments ue
JOIN outcomes o ON ue.experiment_pk = o.experiment_pk
WHERE LOWER(o.metric) LIKE '%biomass%' OR o.metric_type = 'biomass';
