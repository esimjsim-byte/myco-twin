# Claude Code — extractor.py 개발 요청 프롬프트

아래 "프롬프트 전문" 섹션의 코드 블록 안 내용 전체를 Claude Code 웹 UI의
`claude/init-mycelium-db-yb9o9` 브랜치 세션에 새 메시지로 전달하세요.

---

## 프롬프트 전문

```
extractor.py를 개발해주세요. 스키마 명세는 docs/extractor_schema.md를 참고하세요
(같은 커밋에 포함). 이 작업은 Step 2 — 수집된 PubMed 논문에서 구조화 데이터를
Claude API로 추출하는 단계입니다.

=== 배경 ===

- 입력 데이터: data/raw/merged_unique.json (134편 중 PMC full-text 55편)
- 이번 작업 범위: PMC full-text가 있는 55편만 처리
- 사용 모델: claude-opus-4-7 (최고 정확도)
- 처리 방식: 순차 처리 (1편씩, 병렬/배치 X)
- 출력: data/processed/extracted.jsonl (JSONL 형식, 한 줄에 한 논문)

=== 요구사항 ===

1. CLI 인터페이스

   src/extractor.py 를 모듈로 실행:

     uv run python -m src.extractor \
       --input data/raw/merged_unique.json \
       --output data/processed/extracted.jsonl \
       --only-pmc              # PMC full-text 있는 것만
       --limit 5               # 테스트용: 처음 N편만
       --skip-existing         # 이미 처리된 PMID는 건너뜀 (이어하기)
       --dry-run               # API 호출 없이 프롬프트만 출력

2. 의존성 및 설정

   - anthropic 라이브러리 (이미 pyproject.toml에 있음)
   - .env에서 ANTHROPIC_API_KEY 로드 (fetcher.py와 같은 방식)
   - 모델명은 상수로 분리: MODEL_ID = "claude-opus-4-7"
   - max_tokens = 4096 (구조화 JSON 출력에 충분)

3. 핵심 함수 구조

   load_papers(input_path: Path, only_pmc: bool) -> list[dict]
     : merged_unique.json 로드, only_pmc=True면 pmcid 있는 것만 필터링

   build_prompt(paper: dict) -> tuple[str, str]
     : 시스템 프롬프트와 유저 프롬프트 생성
     : 본문은 abstract + fulltext.sections + fulltext.tables 를 적절히 포맷
     : Tables는 headers + rows 구조를 markdown 테이블로 변환
     : 토큰 제한 초과 방지: 전문이 매우 길면 sections 우선, tables 다음,
       마지막에 abstract 추가 순으로 포함 (상세는 아래 4번 참고)

   extract_one(client, paper: dict) -> dict
     : Claude API 호출, 응답에서 JSON 파싱
     : 응답이 JSON이 아니면 JSON 블록 추출 시도
     : 파싱 실패 시 extraction_status="failed" + warnings에 에러 기록
     : source.extractor_model, source.extracted_at 자동 채움

   validate_output(extracted: dict) -> list[str]
     : docs/extractor_schema.md 하단의 validation rules 7개 체크
     : 위반 내용을 warnings 리스트로 반환 (빈 리스트면 통과)

   main()
     : argparse, 이어하기 로직, 진행률 표시, 에러 핸들링

4. 토큰 관리

   PMC 전문이 매우 길 수 있습니다. input token이 150,000 초과 예상되면
   (= 약 450KB 텍스트) 다음 순서로 축약:

   a. 모든 sections, tables, abstract 포함 시도
   b. 150k 초과하면 introduction 섹션 제거
   c. 그래도 초과하면 discussion 섹션 중 결과 수치 없는 문단 제거
   d. 여전히 초과하면 tables 우선 보존하고 sections 중 methods + results만 유지
   e. 최후 수단: abstract + tables only

   tiktoken 불필요. 문자 수 기준 대략 추정 (1 토큰 ≈ 4 chars)으로 충분.

5. 프롬프트 설계

   시스템 프롬프트:
   - 역할: "You are a scientific data extractor for Lentinula edodes cultivation studies"
   - 스키마 설명: docs/extractor_schema.md 핵심 요약 + JSON complete example 포함
   - 중요 규칙:
     * null 허용. 값이 없으면 절대 지어내지 않음
     * 하나의 실험 = 하나의 distinct condition set.
       한 논문이 carbon source 5개 비교했으면 experiments에 5개 객체
     * Tables의 multi-row header 올바르게 해석. 예: headers가
       [[GeneID, Products, log2FC], [T1/T0, T2/T0, T2/T1]]이면
       log2FC 컬럼이 3개 하위 컬럼으로 span되는 구조
     * relevance_score < 0.3이면 experiments 비우고 extraction_status="not_relevant"
     * 응답은 JSON 객체 하나만. 설명, markdown 코드 펜스, 인사말 모두 금지

   유저 프롬프트 순서:
   1. "Extract structured data from this paper according to the schema."
   2. "--- PAPER METADATA ---" + PMID, title, authors, journal, year
   3. "--- ABSTRACT ---" + abstract 본문
   4. "--- FULLTEXT SECTIONS ---" + intro/methods/results/discussion 순
   5. "--- TABLES ---" + 각 table을 caption + markdown table
   6. "Return only the JSON object."

6. 에러 처리

   - API 호출 실패: exponential backoff 3회 재시도.
     최종 실패 시 extraction_status="failed"
   - JSON 파싱 실패: 응답에서 첫 '{'부터 마지막 '}'까지 추출 재시도.
     여전히 실패하면 extraction_status="failed"
   - 한 논문 실패가 전체 중단시키지 않음. 다음 논문으로 계속.

7. 진행률 표시

   tqdm 의존성을 pyproject.toml에 추가 후 사용.
   각 논문: PMID, 성공/실패, 경과 시간, 누적 비용 예상 표시
   예: [12/55] PMID 25868404 ✓ success | t=8.3s | est_cost=$0.15

8. 출력 형식

   JSONL (한 줄 = 한 논문의 JSON).
   이유: 이어하기 쉬움, 스트리밍 처리 가능, 실패 시 부분 결과 보존.

   별도로 data/processed/extracted_summary.json 생성:
   {
     "total_input": 55,
     "success": N, "partial": N, "failed": N, "not_relevant": N,
     "started_at": ISO, "completed_at": ISO,
     "model": "claude-opus-4-7",
     "total_estimated_cost_usd": float
   }

9. Mock 테스트 (API 호출 없이)

   tests/test_extractor.py에 추가:

   a. load_papers()가 only_pmc=True 시 pmcid 있는 레코드만 반환
   b. build_prompt()이 schema와 구조적으로 일치하는 프롬프트 생성
   c. validate_output()이 의도적으로 깨진 JSON에서 warnings 반환
   d. JSON 파싱 폴백: 응답에 markdown 펜스 있어도 추출 성공

   Claude API는 mocking. 실제 응답 형태(schema.md의 complete example)를 fixture로.

10. Dry-run 모드

   --dry-run 플래그:
   - 첫 3편에 대해 build_prompt() 결과를 stdout에 출력
   - API 호출 안 함
   - 토큰 수 추정치도 함께 출력

   목적: 크레딧 충전 전에 프롬프트 품질을 사람이 눈으로 검증

=== 작업 완료 조건 ===

- src/extractor.py 구현 완료
- tests/test_extractor.py 구현 완료, 모든 테스트 통과
- pyproject.toml에 tqdm 추가
- README 또는 docs/에 extractor 사용법 간단히 기록
- pytest tests/ 전체 통과 (기존 fetcher 테스트 포함)
- 브랜치 claude/init-mycelium-db-yb9o9 에 커밋 & 푸시

커밋 메시지: "Implement extractor.py with Claude Opus 4.7 (schema-driven, PMC full-text focus)"

=== 참고 데이터 ===

- 입력 JSON 구조: data/raw/merged_unique.json 의 records[0]
- tables 구조: records 중 fulltext.tables가 non-empty한 것
- fetcher 구현: src/fetcher.py 참고 (.env 로딩, 로깅 패턴)
- 스키마 전문: docs/extractor_schema.md

작업 전 질문 있으면 먼저 물어봐주세요.
```

---

## 전달 후 Kwon님이 하실 일

1. Claude Code가 질문하면 본인 판단으로 응답
2. 구현 완료 후 `git pull` + `uv sync`로 로컬 동기화
3. Mock 테스트 돌려보기: `uv run pytest tests/test_extractor.py -v`
4. dry-run으로 프롬프트 품질 검증:
```
   uv run python -m src.extractor --input data/raw/merged_unique.json --output /tmp/out.jsonl --only-pmc --limit 3 --dry-run
```
5. dry-run 출력의 프롬프트를 눈으로 확인
6. 크레딧 충전 후 실제 실행 (다음 세션)