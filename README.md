# yaicon-persona-avatar

젠슨 황의 공개 인터뷰·연설에서 질문과 관련된 발언을 찾고, 원문에서 어느 대목을 확인할지 알려주는 Python 도구다. 공개 자료 4개에서 정리한 카드 8개가 들어 있으며, 그중 2개에는 출판된 전사의 영어 문답이 포함되어 있다. 영상 수집 담당자가 검수한 문답도 같은 형식으로 추가할 수 있다.

## 실행

Python 3.10 이상과 FTS5를 지원하는 표준 sqlite3 모듈이 필요하다. API 키 없이 실행한다.

```bash
python build_cards.py -o build/cards.jsonl
python search_cards.py --cards build/cards.jsonl "엔비디아에서 미션은 무슨 뜻인가요?" --limit 1
python search_cards.py "공감 관대함" --limit 1
python -m unittest discover -s tests -v
```

첫 번째 검색 결과는 `ACQ-04`다. Acquired 진행자가 사내 미션의 뜻을 물었을 때 나온 답변 “Build Hopper.”와 원문 링크를 돌려준다. 두 번째 결과 `LEX-01`에는 Lex Fridman 전사의 02:15:55 위치가 있다. 검색은 SQLite FTS5의 BM25를 이용하며 일치하는 키워드가 없으면 빈 목록을 돌려준다.

## 수집한 발화 추가

1. `data/sources.json`에 출처, 게시일, 원본 URL, 행사 ID 및 데이터 분할을 기록한다. 같은 행사에서 나온 영상·전사·재편집본은 동일한 `source_event_id`와 분할을 사용한다.
2. `data/turns.jsonl`에 고유한 `evidence_id`, 출처 ID, 원문 위치와 주제 태그를 입력한다. 실제 문답은 `exchange`의 질문자·답변자·질문·답변으로 저장한다. 발췌했다면 `extent`를 `excerpt`로 두고 생략 범위를 적는다. 한국어 요약은 `claim_ko`, 답변 전개에 대한 관찰은 `response_pattern_ko`에 저장한다.
3. 원문을 대조한 자료는 `review_status`를 `reviewed`로 표시한다. 검색과 팀 앱용 내보내기에는 검토가 끝난 학습용 자료만 들어간다. 예시 4개 행사는 모두 개발에 사용했으며, 평가는 별도 행사에서 수행한다.
4. 출판된 전사의 표시 시각은 `published_anchor_s`에 입력한다. 이후 영상·음성을 수집할 때 같은 근거 ID에 클립을 연결하고, 실제 WAV의 발화 시작·끝과 화자·화면에 보이는 사람을 별도로 확인한다.

## 팀 앱에 연결

```bash
python build_cards.py --format studio -o build/studio-evidence.jsonl
```

이 명령은 팀 앱 [who-is-your-bias](https://github.com/Dindb-dong/who-is-your-bias)의 `Evidence` 형식으로 사실 검색용 JSONL을 만든다. 원문 문답과 발화 패턴은 이 저장소의 카드에 보존한다. 팀 앱의 젠슨 황 프로필을 사용하는 별도 코퍼스 폴더에 `data/sources.json`과 내보낸 `evidence.jsonl`을 놓으면 로더에서 읽을 수 있다. 두 저장소의 기존 코퍼스를 합칠 때는 겹치는 출처 ID와 원본 행사를 먼저 대응시킨다.

이 PR은 MCCCD식 수집의 텍스트 단계에 쓰는 도구다. 영상에서 자동으로 얼굴·음성을 분리하는 기능, 답변 생성, 음성/얼굴 합성 및 ThinkPersona 그래프는 후속 실험 범위다.
