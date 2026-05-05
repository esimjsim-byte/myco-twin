# 다음 세션 계획 (2026-05-04 마지막 업데이트)

## 오늘 완료 (이번 세션)
- 가상환경 재생성 (PATH 꼬임 해결)
- 패키지 깔끔하게 설치 (streamlit, plotly, pandas, anthropic, biopython, requests, pyngrok)
- ngrok 작동 확인 (가입 + 토큰 + 실제 터널)
- 코퍼스 진단: 4가지 근본 원인 식별
- 새 쿼리 v2 초안 2개 작성: data/queries/draft_v2.txt

## 핵심 발견 — KEEP=1편 원인
1. query3 (solid-state) 전체가 처음부터 DROP 대상 (38% 낭비)
2. β-glucan-specific 분석법 미강제 (24편 중 1편만, 4%)
3. fruiting body NOT 절 없음
4. query1 너무 광범위

## 다음 세션 첫 일 (명확)
1. cd C:\dev\myco-twin\mycelium-db
2. .venv\Scripts\Activate.ps1
3. data/queries/draft_v2.txt 열어서 v2_1 쿼리 확인
4. PubMed (https://pubmed.ncbi.nlm.nih.gov/)에 v2_1 그대로 붙여넣기
5. 결과 PMID 수 확인:
   - 10~40편이면 → 다음 단계 (제목 검토 + 추출)
   - <10편이면 → NOT 절 완화
   - >40편이면 → method/NMR 같은 강제 키워드 추가
6. v2_2도 같은 절차

## 다음 세션 두 번째 일 (선택)
- 추출 비용 ($30~50 예상) 발생 전 결정 필요
- 본인이 새 데이터 추출까지 갈지, 아니면 PMID 리스트만 받고 멈출지

## 회의 공유 시
NEXT_SESSION.md에 ngrok 사용 절차 이미 있음:
1. PowerShell 1: streamlit run app.py
2. PowerShell 2: ngrok http 8501
3. Forwarding URL 동료에게 공유
4. 회의 끝나면 둘 다 Ctrl+C
