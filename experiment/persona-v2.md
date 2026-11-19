# GPU: 발화 정렬과 persona graph 파일럿

개인 저장소에서 진행하는 **MCCCD-inspired 자료 정렬 + ThinkPersona-inspired 추론 실험**입니다.
MCCCD 전체 수집 파이프라인이나 ThinkPersona의 QRA 파인튜닝을 재현한 결과가 아닙니다.
팀명: **GPU (Girls Processing Unit)**.

## 기준과 격리

- 개인 코드 기준: `86a42f87134f18ef7e8f475e8b41cf3552fec543` (기존 PR #4).
- 새 브랜치: `feat/gpu-aligned-persona-v2`. PR #4 위의 후속 실험이며 기존 파일럿을 덮어쓰지 않습니다.
- 확인한 팀 main: `56b1868fac897fda18b258e79d70dd55c152c540`.
- 팀 저장소, 기존 TTS/아바타, 기본 Q&A 경로는 변경하지 않았습니다.
- 조사일: 2026-11-19. 시연 기기의 실시간 지연을 이 환경에서 측정하지 않았습니다.

## 구현

`persona_v2.py`: 출처 9개 anchor / 관계 27개. 출처가 말한 내용의 요약 18개와
연구자가 해석한 원칙 9개를 타입으로 구분합니다. 기존 A1 관계의 모호한 `qualified`
표현을 바꿔, **시험으로 위험을 줄였고 맹목적 베팅이라는 설명에는 반대했다**는
원문의 방향을 보존합니다. 새로운 상황에 적용한 조언은 실제 과거 발언과 구분합니다.

질문 정책은 뉴스·사생활·프로젝트 자료 필요 여부를 먼저 확인합니다. 해당하면
과거 경험 그래프를 반환하지 않습니다. 이는 보수적인 키워드 기반 연구용 분류이며
실시간 웹 검색이나 일반적인 사실 검증기가 아닙니다. 표현이 달라지면 누락될 수 있고
`today` 같은 표현이 포함된 일반 조언도 과도하게 보류할 수 있습니다.

선택된 동일한 관계·출처 요약·한정 조건을 flat 목록과 adjacency graph로 직렬화합니다.
답안 기준은 프롬프트에 포함하지 않습니다. 생성 순서는 번갈아 바꾸며 모델명,
생성 옵션, 입력 해시, 토큰 사용량(서버 제공 시), 응답 시간, 원문 출력을 저장합니다.
출처 ID/JSON 검사 통과는 의미 충실성 점수가 아닙니다. 출력은 자동 발화되지 않습니다.

`aligned_manifest.py`: 기존 영상 4개 caption excerpt를 `turn_id → evidence_id → graph anchor`
로 연결하고 source-clock offset, 파일 해시, 검수 상태를 남깁니다. WAV/MP4/TXT 실제 바이트와
검수자의 확인 기록이 모두 있어야 멀티모달 학습 후보로 표시합니다. 얼굴 특징 추적이나
자동 active-speaker detection/강제 정렬 모델은 이 모듈에 포함되어 있지 않습니다.
시작/중간/끝 프레임 추출은 검수 보조이며 전체 구간의 발화 얼굴 확인을 대체하지 않습니다.

## 실행

Python 3.12의 표준 라이브러리만으로 준비·테스트를 실행할 수 있습니다.
미디어 추출/프레임 내보내기에는 FFmpeg가 별도로 필요합니다.

```bash
python -m unittest discover -s tests -v
python experiment/persona_v2.py --out local-runs/preparation-01
python experiment/aligned_manifest.py --out local-runs/media-inventory-01.json
```

아래는 **실제 모델 서버를 먼저 실행한 뒤** 사용하는 생성 명령입니다. 서버가 돌고 있다는
뜻이 아니며, 모델 ID는 `/v1/models`에서 확인한 실제 값으로 바꿔야 합니다.

```bash
python experiment/persona_v2.py --out local-runs/qwen3-paired-01 \
  --base-url http://127.0.0.1:8000/v1 --model YOUR_SERVED_MODEL_ID
```

명시한 HTTPS OpenAI-compatible endpoint도 지원합니다. 필요한 인증은 `PERSONA_API_KEY`
환경변수로만 전달합니다. 키를 코드/명령 인수/결과 파일에 넣지 않습니다. Thinking mode와
채팅 템플릿은 사용 서버에서 양 조건에 동일하게 설정하고 실행 기록에 추가해야 합니다.
중간 응답은 JSONL에 즉시 저장합니다. 실패한 run은 보존하고 새 출력 폴더로 재실행합니다.

기존 미디어는 `extract_turns.py --video ORIGINAL.mp4 --vtt ORIGINAL.vtt --out LOCAL_TURNS`
로 생성합니다. 입력 해시는 기존 등록값과 같아야 합니다. 원본이나 전체 전사를 공개 Git에
추가하지 않습니다. 추출 후 아래로 실제 파일과 검수 상태를 확인합니다.

```bash
python experiment/aligned_manifest.py --assets LOCAL_TURNS \
  --out local-runs/media-verified-01.json --frames local-runs/review-frames-01
```

검수 JSON은 turn_id를 키로, `speaker_verified`, `visible_speaking_face_verified`,
`acoustic_alignment_verified`, `reviewer`, `reviewed_at`, `notes`, `video_sha256`,
`wav_sha256`를 기록합니다. 실제 구간 전체를 듣고 보지 않았다면 플래그는 false로 둡니다.
`--review REVIEW.json`을 더해 검수 기록을 결합합니다. 현재 manifest의 판정은 파일 무결성과
명시적 검수 기록에 기반하며, 검수자의 판단 자체를 자동 입증하지 않습니다.

## 실제 확인 결과와 제한

- 단위/회귀 테스트: 30개 통과(기존 16개 + 신규 14개).
- 새 개발용 29문항: 분기 29/29, persona 문항의 기대 출처 포함 14/14.
  작성한 키워드와 가까운 개발 문항이며 독립적인 holdout 정확도나 답변 성능이 아닙니다.
  초기 26문항 확인 후 발견한 시간 표현 누락 3건을 회귀 문항으로 추가했습니다.
  기대 출처 포함률은 추가로 검색된 출처의 적합성까지 평가한 precision이 아닙니다.
- 새 LLM 생성: **0회**. 로컬 서버가 없고 모델 호스트 연결이 시간 초과되어 실행하지 못했습니다.
- 기존 LLM 파일럿: Qwen2.5-1.5B, 10문항/20응답. 기대 출처 태그 4/8 → 7/8이지만
  양 조건에서 검증/확신의 의미 역전과 근거 없는 회사 설립 정보가 발견되었습니다.
  신규 코드가 이 생성 문제를 해결했다는 결과는 아직 없습니다.
- 기존 추출 receipt: 1개 행사, 2개 anchor에 연결한 4구간, 합계 22.189초.
  이번 환경에서 해당 원본/추출 바이트를 복구하지 못했으며 얼굴·음성 정렬 검수도 미완료입니다.
  따라서 현재 `training_eligible_count=0`입니다. 기존 추출 기록이 없었다는 뜻은 아닙니다.

## 팀 통합 조건

현재 판정은 **보류**입니다. 다음을 충족한 후 팀의 새 PR로 필요한 모듈만 옮깁니다.

1. 같은 모델/추론 설정/출처/토큰 상한으로 flat/graph 응답을 모두 생성합니다.
2. 두 사람이 조건을 가린 채 출처 의미 보존, 질문 적합성, 경험→원칙→새 상황 적용,
   근거 없는 사실/감정 생성, 과도한 보류를 평가합니다. 출처 태그 적중만으로 통과시키지 않습니다.
3. 대조 문항에서 중대한 의미 역전·사생활/최신 사실 날조가 관찰되면 보류합니다.
   graph의 중대한 오류가 baseline보다 늘지 않고, 유용한 적용 개선이 사례로 확인되어야 합니다.
4. 팀 실제 모델에서 첫 음성 지연·문장 사이 공백·답변 길이를 함께 측정합니다.
5. 팀의 temporal/event 필터를 거친 **실제 packed evidence IDs**만 `allowed_evidence_ids`에 넣습니다.
   기존 RAG/source-budget/persona binding/SegmentCommitter 검사를 대체하지 않습니다.
   현재 팀 영어 스트리밍 경로의 발화 전 의미 검증까지 구현했다고 주장하지 않습니다.

자료가 검수되면 필요한 발화·음성·얼굴 구간을 확장하고, 이후 QRA 학습 데이터 작성과
별도의 학습/검증 행사 분할을 고려합니다. 같은 원문 행사에서 잘라낸 클립을 train/test로
나눠 인물 일반화 성능이라고 보고하지 않습니다.

## 근거

- ThinkPersona: https://aclanthology.org/2026.acl-long.449/ (persona graph + QRA fine-tuning).
- MCCCD: Creating Multimodal Interactive Digital Twin Characters From Videos: A Dataset and Baseline,
  DOI: 10.1109/TPAMI.2025.3603653. 본 구현은 그 발화 단위 연결 원칙을 제한적으로 차용합니다.
- 각 인물 근거 URL/locator: `data/persona-v2/graph.json`.
- 이전 결과 원문: `results/matched-tags/answers.jsonl` 및 `metrics.json`.
