# 젠슨 황의 경험·가치관을 반영하는 영문 답변 실험

같은 출처와 관계를 일반 문장 목록으로 제공할 때와 방향이 있는 그래프로 제공할 때 Qwen의 답변이 어떻게 달라지는지 시험했다. 예를 들어 학교 청소와 식당 일은 각각 자신이 맡은 일을 자랑스럽게 여기는 태도와 연결되고, 이 태도는 일의 크기에 관계없이 최선을 다한다는 판단으로 이어진다. 영어 관계 표기는 공개 발언을 읽고 작성한 연구용 주석이다.

## 구성

- **공통 검색** — 동욱님의 [PR #17](https://github.com/Dindb-dong/who-is-your-bias/pull/17)이 병합된 커밋 `3038629f3c4aeefff568684a6a7ba10df2b61db8`에서 `bias.corpus.Corpus`와 `bias.retrieval.Retriever`를 직접 호출한다. 원저장소의 젠슨 황 자료 32건 전체를 검색해 상위 3개까지 반환한다. 그중 관계를 주석한 발언만 두 조건에 공통으로 전달한다. 타인의 소스 파일이나 전체 전사를 이 저장소에 재배포하지 않는다.
- **수집과 연결** — Stripe Sessions 2024 원본 MP4와 공식 WebVTT에서 답변 2개의 발화 4구간을 추출했다. 자막 경계로 자른 16 kHz 단일 채널 WAV, 360p 영상, 해당 자막 텍스트가 동일한 `turn_id`를 가진다. 길이 합계는 **22.189초**다. 화자는 출판사 전사로 대응했고, 음향 경계와 화면의 실제 발화 얼굴은 미검수다. 공개 저장소에는 [선택 시각과 원본 링크](data/media-selections.json), [실제 프레임·샘플 수와 해시](results/media-receipt.json)를 둔다. 이 자료의 태그 S1·S2가 텍스트 실험의 동일한 발언을 가리킨다. 다른 영역의 관계는 출판사 전사에 근거했다.
- **그래프** — [7개 발언, 23개 노드, 15개 관계](data/persona-graph.json). 노드는 경험·태도·판단 기준이며, 각 방향 관계는 근거 태그를 가진다. 등록한 관계를 두 조건에서 전부 유지한다. 평문은 관계마다 주어를 반복한 문장, 그래프는 시작 노드별로 나가는 관계를 묶은 인접 목록이다. 검색되는 발언 자체나 음성·얼굴 입력의 효과는 실험 변수에 포함하지 않았다.
- **생성** — Qwen2.5-1.5B-Instruct Q4_K_M, llama.cpp b12318, CPU 6스레드, temperature 0, seed 23. 두 조건은 같은 질문·시스템 지침·사실 묶음·최대 출력 96토큰을 사용했다. 사실 묶음의 해시를 조건별로 저장했다. 인용 태그의 위치도 각 관계 끝으로 통일했다. 같은 1,024토큰 입력 상한 안에서 실제 프롬프트 길이는 평문 121–230토큰, 그래프 121–254토큰이었다. 출력의 순서 효과를 줄이기 위해 질문별 호출 순서를 교대로 바꿨다. 모델 가중치는 고정했다.

## 실행 결과

[주 비교의 전체 답변 20개](results/matched-tags/answers.jsonl) · [집계](results/matched-tags/metrics.json) · [블라인드 평가지](results/matched-tags/blind-review.csv)

| 10개 질문에 대한 지표 | 평문 근거 | 그래프 근거 |
|---|---:|---:|
| 기대 출처가 있는 8문항 중 해당 출처가 모델 입력까지 도달 | 7/8 | 7/8 |
| 해당 출처 태그가 실제 답변에 포함 | 4/8 | 7/8 |
| 입력에 없는 태그를 쓴 답변 | 1/10 | 0/10 |
| 블라인드 사람 평가에 의한 가치관 충실도 | 미평가 | 미평가 |

관리자마다 직속 보고자를 60명씩 두어야 하느냐는 질문(`reports`)에서 평문 조건은 찬성했고 그래프 조건은 반대했다. Stripe 원문에서 황은 직급·역할별 감독 필요가 다르다고 설명했다. 두 답 모두 [S2]를 붙였으므로 태그만 검사하면 오답까지 통과한다. 반대로 칩을 검증하지 않고 회사 전체를 거느냐는 질문(`risk`)에는 두 조건 모두 찬성했다. 근거는 제조에 앞서 에뮬레이션으로 칩과 소프트웨어를 검증한 경험이다. 법무법인 질문에서도 입력 근거가 비자 두 조건 모두 실제 경험에 관해 근거 없는 답을 했다.

[질문 10개](data/questions.json)는 개발 질문 7개, 별도 Stanford SIEPR 행사 주제를 바꿔 쓴 질문 1개, 별도 Stanford eCorner 강연에만 답이 있는 근거 밖 사실을 묻는 대조 질문 1개, 사적인 정보 대조 질문 1개다. 두 Stanford 행사의 참고답·링크는 모델에 보내지 않았다. 데이터 분리는 모델의 사전학습 노출까지 통제하지 않는다. 초기 형식 점검에도 같은 질문을 사용했으므로 이 결과는 소규모 개발 파일럿이다.

첫 [형식 점검 결과](results/pilot-01/metrics.json)에서는 평문 태그가 문장 앞, 그래프 태그가 뒤에 있었다. 주 비교를 위해 평문 태그를 같은 위치로 옮기고 20회 모두 다시 실행했다. 두 실행을 독립 반복으로 합산하지 않는다. 평가는 문항별로 두 답을 읽어 경험·가치관 충실도, 근거 없는 주장, 선호도를 기록하도록 작성했다. 평가자에게는 CSV만 전달하고 [조건 키](results/matched-tags/review-key.json)는 평가가 끝난 뒤 연다. 같은 행사의 다른 클립이 평가·개발 양쪽에 들어가지 않도록 다음 평가에는 별도의 새 인터뷰를 남겨 둔다.

## 재현

Python 3.11 이상, Git, pydantic 2가 필요하다. 아래 명령은 이 저장소의 루트에서 실행한다. 모델이나 동욱님의 저장소를 올릴 필요 없이 로컬에서 실행할 수 있다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install 'pydantic>=2.9,<3'
git clone --filter=blob:none --sparse https://github.com/Dindb-dong/who-is-your-bias.git ../bias-pr17
git -C ../bias-pr17 sparse-checkout set src/bias data/personas/jensen-huang
git -C ../bias-pr17 checkout --detach 3038629f3c4aeefff568684a6a7ba10df2b61db8
```

[llama.cpp b12318](https://github.com/ggml-org/llama.cpp/releases/tag/b12318)의 운영체제별 바이너리와 [공식 Qwen GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/blob/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf)를 준비한다. 파일명은 `qwen2.5-1.5b-instruct-q4_k_m.gguf`이며 SHA-256은 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`다. 아래 명령의 모델 경로는 다운로드한 위치에 맞춘다.

```bash
llama-server -m qwen2.5-1.5b-instruct-q4_k_m.gguf --alias qwen2.5-1.5b-instruct-q4_k_m --host 127.0.0.1 --port 18731 -ngl 0 -t 6 -c 4096 -np 1 --no-warmup
```

서버를 켠 상태에서 두 번째 터미널에서 실행한다. 결과는 새 디렉터리에 기록한다.

```bash
python experiment/graph_pilot.py --upstream ../bias-pr17 --out build/paired-run
python experiment/graph_pilot.py --upstream ../bias-pr17 --question "Should a new manager copy a CEO's direct reports?" --out build/my-question
python -m unittest discover -s tests -v
```

영상 추출에는 FFmpeg와 ffprobe가 추가로 필요하다. [선택 파일](data/media-selections.json)의 `video_url`, `vtt_url`에서 받은 두 원본을 사용한다. 추출기는 원본의 해시와 지정된 자막 경계를 확인한 뒤 결과를 만든다.

```bash
python experiment/extract_turns.py --video stripe.mp4 --vtt stripe.vtt --out data/private/stripe-turns
```

### 자료와 방법의 출처

- Stripe S1–S3. [Stripe Sessions 출판사 전사](https://stripe.com/gb/sessions/2024/a-conversation-with-nvidias-jensen-huang). 성장 과정과 식당 일, 직속 보고자의 범위, CEO가 참석하는 회의에 대한 연속 문답.
- Lex L1–L2. [Lex Fridman Podcast #494 전사](https://lexfridman.com/jensen-huang-transcript/). 00:17:14의 호기심·확신, 02:03:43의 지시를 얼마나 구체화할지에 관한 발언.
- Acquired A1–A2. [Acquired 출판사 전사](https://www.acquired.fm/episodes/jensen-huang#transcript). 제조 전에 검증한 경험과 다시 창업하겠느냐는 마지막 질문.
- [MCCCD 논문](https://doi.org/10.1109/TPAMI.2025.3603653)에서 발화 단위의 영상·음성·텍스트 정렬을 참고했다. 이 파일럿은 출판사가 제공한 자막과 화자 정보를 이용한다. 자동 화자·얼굴 검증과 인물별 VITS·3D talking head 학습은 수행하지 않았다.
- [ThinkPersona](https://aclanthology.org/2026.acl-long.449/)의 사건과 가치관 간 연결을 참고했다. 이번 비교는 추론 시 입력 표현을 바꾸는 실험이다. 원 논문처럼 QRA 학습자료를 생성해 LoRA로 모델을 훈련하는 단계는 수행하지 않았다.
