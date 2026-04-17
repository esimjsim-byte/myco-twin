# sample.json — 표고버섯(Lentinula edodes) 배양 논문 10편 샘플 데이터

## 목적

Claude Code 샌드박스에서 NCBI API 접근이 차단된 상황을 우회하기 위해,
extractor(Step 2) 개발을 선행할 수 있도록 준비한 샘플 데이터입니다.

이 파일의 역할은 **"fetcher.py가 실제로 돌아갔다면 나왔을 형식"의 예시**입니다.

## 파일 구조

```
{
  "query": 검색 쿼리 문자열,
  "query_date": 수집 날짜,
  "total_found": 10,
  "note": 데이터 성격 설명,
  "papers": [
    {
      "pmid": PubMed ID,
      "pmcid": PMC ID (없으면 null),
      "doi": DOI (없으면 null),
      "title": 논문 제목,
      "authors": [저자 리스트],
      "journal": 저널명,
      "year": 발행 연도,
      "publication_types": [Journal Article, Review 등],
      "mesh_terms": [MeSH 용어],
      "abstract": 초록 전문,
      "fulltext": null 또는 {
        "pmcid": PMC ID,
        "sections": {
          "introduction": 도입부 텍스트,
          "methods": 방법 섹션 텍스트,
          "results": 결과 섹션 텍스트,
          "discussion": 고찰 섹션 텍스트
        },
        "tables": [
          {
            "caption": 표 캡션,
            "rows": [[헤더], [데이터 행1], [데이터 행2], ...]
          },
          ...
        ]
      }
    },
    ...
  ]
}
```

## 데이터 성격 (중요)

- **메타데이터(PMID, 제목, 저자, 연도, 초록)**: 실제 PubMed에 등록된 논문에서 가져옴
- **본문/표 수치**: 실제 논문의 핵심 수치를 보존하되, PMC 전문 파싱이 여의치 않은 부분은
  재구성됨. 문헌의 결론은 바뀌지 않았지만 개별 행의 숫자가 원문과 소수점 수준에서
  다를 수 있음.
- 따라서 이 파일은 **extractor 프롬프트 엔지니어링과 파이프라인 검증용 fixture**로만
  사용하고, 최종 분석·보고서에는 반드시 fetcher.py로 직접 수집한 데이터로 교체해야 합니다.

## 구성 비율

- PMC 전문 4편 (40%): 섹션과 표 포함 → extractor의 본문·표 추출 로직 검증용
- 초록만 6편 (60%): extractor의 abstract-only 모드 검증용

이는 표고버섯 주제의 실제 PubMed Open Access 비율과 유사합니다.

## 사용법

```python
import json
with open('data/raw/sample.json') as f:
    data = json.load(f)

for paper in data['papers']:
    if paper['fulltext']:
        # PMC 전문 있음 → 본문 + 표 추출
        for table in paper['fulltext']['tables']:
            print(table['caption'])
            for row in table['rows']:
                print('  ', row)
    else:
        # 초록만 → abstract에서 추출
        print(paper['abstract'][:200])
```

## 포함된 논문 목록

| # | PMID | 연도 | 유형 | 핵심 내용 |
|---|------|------|------|-----------|
| 1 | 40067479 | 2025 | PMC | 리뷰: 탄소·질소 대사 경로 |
| 2 | 25868404 | 2015 | 초록 | RSM 최적화 (LeS 균주) |
| 3 | 30533854 | 2018 | PMC | 호두껍질 C/N 비 5~25 |
| 4 | 26675911 | 2015 | 초록 | 질소원 3종 + 유칼립투스 |
| 5 | 15859464 | 2005 | 초록 | 배지 조성과 렉틴 활성 |
| 6 | 19800423 | 2010 | 초록 | PBD/BBD 통계 최적화 |
| 7 | 40195441 | 2025 | PMC | 18균주 스크리닝 |
| 8 | 38644753 | 2024 | PMC | 질소원 + LED 조명 |
| 9 | 30904504 | 2019 | 초록 | 침지배양 β-glucan + MAPK |
| 10 | 36265546 | 2022 | 초록 | 리그노셀룰로스 고체발효 |

## 다음 단계

이 파일을 `mycelium-db/data/raw/sample.json` 경로에 저장한 뒤,
extractor.py가 이 파일을 읽어서 구조화된 실험 조건 데이터를 추출하도록 개발합니다.
