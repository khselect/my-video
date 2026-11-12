# 개발 로그 — Lecture Studio · 영상 도구 (기능별)

`video-tools/` 작업 공간에서 진행한 주요 작업을 **기능별로** 정리한다. 날짜는 작업일, 상세 사용법은 [WORKFLOW.md](../WORKFLOW.md).
코드 위치는 모두 `my-video/` 기준.

| 기능 | 상태 | 핵심 파일 |
|---|---|---|
| [1. 설치·환경](#1-설치환경-2026-11-04) | 완료 | `tools/setup_qwen_tts.sh`, `tools/setup_image_gen.sh` |
| [2. Studio 기본 화면](#2-studio-기본-화면-2026-11-04) | 완료 | `studio/app.py`, `studio/index.html` |
| [3. 진행률 팝업](#3-진행률-팝업-2026-11-04) | 완료 | `app.py` `job_progress()` |
| [4. 영상 스타일(스킬) 선택](#4-영상-스타일스킬-선택-2026-11-04) | 완료 | `studio/styles/*.json`, `SCHEMA.md` |
| [5. 장면 구성표](#5-장면-구성표-2026-11-04) | 완료 | `app.py` `plan_view()` |
| [6. 참고 스타일 메모](#6-참고-스타일-메모-2026-11-04) | 완료 | `app.py` `make_brief` |
| [7. 로컬 캐릭터·이미지 생성](#7-로컬-캐릭터이미지-생성-2026-11-04) | 완료 (Studio 전체 제작은 미검증) | `tools/sticker_local.py`, `tools/cutout.py` |
| [8. 프로젝트 이름·삭제](#8-프로젝트-이름삭제-2026-11-04) | 완료 | `app.py` `delete_lecture()` |
| [9. AI 일러스트 모션 (Higgsfield)](#9-ai-일러스트-모션-higgsfield-2026-11-06) | 구현 · 유료 실행 미검증 | `studio/styles/ai-motion.json` |
| [10. 내 목소리 화자 (Fish Audio · Qwen)](#10-내-목소리-화자-fish-audio--qwen-2026-11-06) | 구현 · 유료 실행 미검증 | `tools/fish_audio.py`, `tools/narrate.py` |
| [12. 모션 연출 규칙 (P0-1)](#12-모션-연출-규칙-p0-1-2026-11-12) | 구현 · 실제 제작 미검증 | `.claude/skills/edu-video/references/motion-rules.md`, `app.py` `motion_hint()` |
| [13. 렌더 후 자동 검사 (P0-2)](#13-렌더-후-자동-검사-p0-2-2026-11-12) | 완료 (합성·실제 렌더로 검증) | `tools/qa_render.py`, `render_version.py` `finalize()` |
| [14. 레퍼런스 영상 측정 (P1-1)](#14-레퍼런스-영상-측정-p1-1-2026-11-12) | 완료 (합성 정답 영상·실제 렌더로 검증) | `tools/ref_measure.py` |
| [11. 교훈·문제 해결](#11-교훈문제-해결) | — | — |

---

## 1. 설치·환경 (2026-11-04)

- `khselect/my-video` 를 `video-tools/my-video` 에 clone, `npm install`, `new_lecture.py --restore-assets` 로 폰트·GSAP 복원.
- **Qwen3-TTS 1.7B**: 가상환경 `video-tools/qwen-tts-env` (`QWEN_VENV` 로 위치 지정), 모델은 `~/.edu-video/models/` 에 로컬 저장.
  - `huggingface_hub` 2.x 가 transformers 를 깨뜨려 **`huggingface_hub>=0.34,<1.0` 고정** (setup 스크립트에도 반영).
  - `narrate.py`·`voice_clone.py` 는 로컬 모델 폴더를 먼저 쓰도록 수정 (매번 재다운로드 방지).
- `video-tools/OpenMontage` clone (선택, 저장소 미포함).
- **로컬 이미지 생성 환경**: `video-tools/image-env` (mflux 0.24 + rembg), 모델 `~/.edu-video/models/FLUX.1-schnell-mflux-4bit` (9.0GB, Apache-2.0, HF 로그인 불필요). 설치: `IMAGE_VENV=… bash tools/setup_image_gen.sh` (Apple Silicon 전용).
- 기기별 설정은 `studio/config.local.json` (git 제외): `qwen_python`, `image_python`, 기본 화자 등.

## 2. Studio 기본 화면 (2026-11-04)

- 기본 문구를 Lecture Studio 에 맞게 교체 (샘플 강의 제목 하드코딩 제거).
- **원문 선택**: `sources/` 목록 대신 파일 선택/드래그 업로드 (PDF·HTML·MD·TXT, 200MB) → `build/upload/` 경유 `extract_source.py`.
- **화자**: 기본 `uncle_fu`(남성). 한국어 원어민 화자는 `sohee`(여성) 하나뿐이라 남성 화자는 억양이 섞임 → 화자 드롭다운에 설명 표시. 내 목소리는 Qwen clone(로컬) 또는 Fish Audio(10장).
- **오른쪽 화면**: 처음부터 마지막으로 연 프로젝트(없으면 첫 프로젝트)를 자동으로 연다 (`localStorage.studio_last_lecture`).

## 3. 진행률 팝업 (2026-11-04)

- 작업 팝업에 진행 막대·%·경과·남은 시간(10% 이후). 작업 로그를 해석해 계산:
  - 나레이션: 장면별 `made/skip` 줄 (Fish 는 5–85% 음성 받기 → 85–100% 변환)
  - 렌더: HyperFrames `@hf-progress` JSON → 인코딩/캡처 프레임 수
  - 규칙 검사: 단계별 고정 구간(samples/craft/overlap/analyze) — 막대가 뒤로 가지 않게
  - Claude 장면 제작: 새로 쓴 `compositions/*.html` 수, 생성 이미지 수
- 반쯤 쓰인 줄("159/23")을 읽어 424% 가 되던 문제 → 완결된 줄만 해석, 실행 중 최대 99%.
- `claude -p` 가 stdin 을 기다리던 경고 → `stdin=DEVNULL`.

## 4. 영상 스타일(스킬) 선택 (2026-11-04)

- skillry.dev 에서 받은 스킬 3개를 분석해 **영상 형태 3분류**로 정리:
  - 강의 동영상: `edu-video` (기본, HyperFrames, 나레이션 동기화)
  - 스토리 애니메이션: `paper-cutout` (종이 콜라주, 대본 내용으로 장면 구성)
  - 홍보·짧은 클립: `plush-crew`(제품 캐릭터 고정 안무), `ink-crumble`(17슬롯 문구 템플릿) — 대본 이야기를 그릴 수 없어 promo 로 분리
- 스타일 = `studio/styles/<id>.json` manifest (옵션·제작 지시·허용 명령·QA·렌더). 형식은 [`studio/styles/SCHEMA.md`](../studio/styles/SCHEMA.md).
- **스타일 추가**: 5단계 ①카드 "+ 스타일 추가" → 스킬 폴더 선택 → `video-skills/`(git 제외)에 복사 → 기본 manifest → "Claude로 옵션 분석"이 SKILL.md 를 읽어 옵션·구성표 작성(실패 시 백업 복원).
- 스킬 스크립트가 읽는 API 키(FAL·ElevenLabs)는 Studio 작업에서 환경변수를 지우고 실행.
- `render_style.py`: 나레이션 + 음악(볼륨 0.13)을 섞어 스킬 렌더에 붙이고 버전 등록.

## 5. 장면 구성표 (2026-11-04)

- 모호했던 "프롬프트 복사"·장면별 피드백 칸 대신, **고른 스타일의 기본 화면 구성을 장면마다 미리 채운 표**를 보여 주고 사용자가 고친다.
- manifest `plan.columns` 의 기본값: `scene.<필드>`, `opt.<옵션>`, 위치별 순서(`first/last/cycle`), 다른 열에서 유도(`from/map`).
- 사용자가 고친 칸은 ★ 로 Claude 에게 전달, "바뀐 행만 반영"은 마지막 제작 이후 달라진 행만 다시 만든다.
- "Claude에게 보낼 제작 지시 보기"로 실제 프롬프트 확인·복사.

## 6. 참고 스타일 메모 (2026-11-04)

- 5단계 ②에 참고 링크 + 스크린샷 → "스타일 메모 만들기" → `lectures/<p>/style-ref/brief.md` (색 hex·형태·인물·배치·모션, 마지막 줄 `IMAGE_STYLE:`). 모든 스타일의 제작 지시에 자동 포함.
- ted.com 등은 JS 로 그려져 링크만으로는 내용을 못 읽음 → 첫 메모가 "흔한 관례"로 채워짐 → **근거 없으면 "근거 부족"으로 쓰도록 규칙 추가. 스크린샷 2~3장 필수.**
- TED 영상은 CC BY-NC-ND: 프레임·캐릭터는 쓰지 않고 스타일 특징만 메모. 스크린샷은 git 제외.

## 7. 로컬 캐릭터·이미지 생성 (2026-11-04)

- 종이 콜라주 스토리가 대본과 무관한 기본 소품(사람·문·꽃)만 재사용하던 문제: Studio 지시가 이미지 생성을 막고 주인공을 그리라는 지시가 없었음.
- `.env` 에 이미지 API 키 없음 → **로컬 FLUX(무료)** 로 결정.
- `tools/sticker_local.py`: 종이 질감 프롬프트 → FLUX.1-schnell 4-bit → rembg 배경 제거 → 피사체만 잘라 투명 PNG. 장당 약 30~40초. 배치(`--batch`)·캐시(`<out>.json`), `--plain --width --height` 로 장면 전체 그림도 생성.
- **일관성 실험 결과**: img2img(참조 이미지)는 strength 0.3 에서도 **포즈가 고정**됨 → 규칙: *같은 외형 문장 + 같은 seed, 동작이 바뀌면 참조 없이 생성*, 참조는 표정 변화에만.
- 남는 한계: 얼굴 비율이 조금씩 다르고 맨발 등 작은 결함 → Claude 가 PNG 를 보고 어긋난 것만 다시 그림.
- paper-cutout 옵션: 캐릭터·이미지(로컬/SVG/내장 소품), 등장인물, 구성표 "인물·동작" 열, 5단계 "캐릭터·이미지" 갤러리.
- `tools/cutout.py`: 그림에서 인물만 떼어 같은 크기·위치로 저장 (패럴랙스 전경 층).

## 8. 프로젝트 이름·삭제 (2026-11-04)

- 왼쪽 목록 "강의" → **"프로젝트"** (영상 형태가 강의·스토리·홍보로 넓어짐). 내부 폴더명 `lectures/`·API 경로는 호환 위해 유지.
- 프로젝트 ✕ → 확인 → **macOS 휴지통으로 이동**(되살리기 가능, 같은 이름이면 날짜 붙임). 작업 중인 프로젝트는 삭제 불가.

## 9. AI 일러스트 모션 (Higgsfield) (2026-11-06)

- 새 스타일 `ai-motion` (스토리 애니메이션, engine `edu-video` + 자체 prompt): 원문·대본에 맞는 장면 일러스트 → HyperFrames 모션그래픽, 나레이션 동기화.
- 그림 만들기: **Higgsfield**(claude.ai 커넥터 MCP, 유료) / 로컬 FLUX(무료) / 없음.
  - Higgsfield: 잔액 확인 → 주인공이 잘 보이는 1장 먼저 → 나머지는 첫 장 job_id 를 참조 이미지로 넣어 인물 유지 → `jobs_wait` → curl 로 `assets/images/` 저장 → `credits.json` 기록. 잔액 부족분은 로컬 FLUX 로.
  - 모델: `nano_banana`(기본, 참조 이미지 지원) / `seedream_v4_5`.
- 모션(무료, 코드): 밀기·당기기·패닝·패럴랙스(인물 분리 두 겹)·드러내기. 구성표에서 장면별 "그림 내용"·"모션" 지정.
- 영상 클립(이미지→영상)은 핵심 장면 1개 옵션, 기본 꺼짐.
- **유료 안전장치**: manifest `paid`(확인 창 문구) + `mcp_tools`(조건 맞을 때만 `--allowedTools` 에 추가). 확인 없이 제작 요청하면 서버가 거절(`paid_ok`).
- 2026-11-06 기준 비용(get_cost 확인): 이미지 1크레딧/장, 5초 영상 35크레딧. 잔액 10크레딧(무료 플랜) → 영상 클립 불가.
- 검증: 옵션·제작 지시 치환, 유료 도구 조건부 허용, 헤드리스 `claude -p` 에서 Higgsfield 호출 가능(balance). **실제 이미지 생성 제작은 미실행.**

## 10. 내 목소리 화자 (Fish Audio · Qwen) (2026-11-06)

- 4단계 "내 목소리 화자" 카드: 녹음(15~60초) 업로드 → 본인 동의 체크 →
  - **Fish Audio 화자**: `tools/fish_audio.py clone` — 녹음 정리(ffmpeg) → 범위를 좁힌 `claude -p` 가 `get_upload_url` → curl PUT → `create_voice_clone`(비공개). 본인 확인이 필요하면 읽을 문장을 화면에 표시 → `verify`. 결과 `~/.edu-video/voices/fish.json`.
  - **로컬 Qwen 프로필**: `voice_clone.py prep` + `enroll` (무료, 문장 입력 시 정확도 향상).
- 나레이션 백엔드 `fish` 추가: `fish_audio.py narrate` 가 바뀐 장면만 골라 `text_to_speech`(s2.1-pro) → `build/audio/fish/<id>-<hash>.mp3` → `narrate.py --backend fish` 가 변환·타이밍·manifest (기존 캐시·`--force` 그대로).
  - 잔액 먼저 확인, 부족하면 생성하지 않고 멈춤. 1회 한도 500바이트(한글 약 160자)/장면.
- 비용: 텍스트 1바이트 ≈ 1크레딧(한글 1자 ≈ 3). 잔액 8,000크레딧(무료 플랜). 업로드 원본은 Fish 서버에서 7일 뒤 자동 삭제.
- 검증: 받아 둔 mp3 → 변환·manifest 정상(16.5초), 빠진 장면 → Claude 경로·크레딧 부족 오류 처리, 무료 호출(잔액·업로드 링크·dry_run 견적). **실제 복제·합성은 미실행.**

## 11. 교훈·문제 해결

| 상황 | 원인 / 해결 |
|---|---|
| transformers 임포트 오류 | huggingface_hub 2.x → `<1.0` 고정 |
| 진행률 424% | 반쯤 쓰인 로그 줄 해석 → 완결된 줄만 |
| Chrome 확장으로 localhost 확인 불가 | 확장이 localhost 차단 → playwright-core 헤드리스로 확인 |
| `git push` 가 멈춤 | 샌드박스에서 macOS 키체인 자격증명 조회가 막힘 → 샌드박스 밖에서 실행 |
| 참고 링크만으로 엉뚱한 메모 | JS 렌더 페이지는 내용 없음 → 스크린샷 필수, 근거 없으면 "근거 부족" |
| img2img 로 포즈가 안 바뀜 | 참조는 포즈를 고정 → 동작 변화는 참조 없이 같은 seed |
| 스킬 예시 소품만 재사용 | 지시에 "주인공을 대본에서 정해 그린다"가 없었음 → 캐스팅 절차 추가 |
| 유료 MCP 오남용 우려 | 조건부 `--allowedTools` + 확인 창 + 서버 `paid_ok` 검사 + 잔액 선확인 |

### 남은 일

- Studio 에서 실제 제작 1회: 종이 콜라주(로컬 스티커), AI 일러스트 모션(Higgsfield, 최대 4장 권장), Fish 화자 복제·나레이션.
- 맥북: `video-skills/` 다시 가져오기, `image-env`·FLUX 설치, 이 PC 설정 입력.
- 작업 브랜치 `claude/my-video-git-pull-49kwdy` → `main` 병합 여부 결정.

## 12. 모션 연출 규칙 (P0-1) (2026-11-12)

- 배경: 참고 영상 분석([CLAUDE.md](../CLAUDE.md), [조사](research/motion-graphics-prompts.md)) — 품질은 프롬프트 구체성(이징·카메라·타이밍)이 가르고, 기본 결과의 약점은 "카메라 정지 + 장면 연결 없음 = 슬라이드 넘기기".
- 기존 제작 지시(`prompt_visuals`)와 `style-guide.md` 에는 이징 몇 개만 있고 카메라·연결·읽기 시간 규칙이 없었음. 데모 템플릿은 장면마다 opacity 0 으로 완전히 사라져 전환에 빈 화면이 생김.
- `references/motion-rules.md` (모든 스타일 공통): 이징 곡선표(용도·길이), 카메라(장면당 1개·전체 4종 이상·`#<id>-cam`·overscan 10%), 장면 연결(관통 요소·매치 컷·빈 프레임 금지·리듬), 글자 유지(한국어 글자 수÷5+1.5초 시작값, 자막 1.8초·타이틀 4초), 이미지 에셋(불규칙 가장자리·overscan), 체크리스트.
- `app.py` `motion_hint()` 를 edu-video 엔진(`prompt_visuals`)과 스킬 엔진(`prompt_style`) 제작 지시에 추가. 스킬 엔진은 "SKILL.md 가 고정한 안무 우선" 단서, 작업 폴더에서 실행되므로 규칙 파일은 절대 경로 + `--add-dir` 로 읽기 허용.
- `style-guide.md` 모션 규칙·`SKILL.md` 4장에서 motion-rules 참조, 장면 끝 페이드는 다음 장면과 겹치게. `ai-motion` 은 overscan·관통 요소 전환으로 수정.
- 검증: 4개 스타일(edu-video·ai-motion·paper-cutout·plush-crew)의 제작 지시에 규칙이 1번씩 들어가는 것 확인. **실제 `claude -p` 제작·렌더는 미실행** — 렌더 결과 수치 확인은 P0-2(렌더 후 자동 검사)에서.

## 13. 렌더 후 자동 검사 (P0-2) (2026-11-12)

- `tools/qa_render.py <영상> [--lecture 폴더] [--normalize]` → `<영상>.qa.json`. 검사마다 통과/확인/문제와 수치.
  - **빈 화면**: 10fps·192×108 회색 프레임의 경계 에너지(평균 |dx|+|dy|) < 0.6 이고 픽셀 분산 < 12. 0.3초 이상 확인, 1초 이상 문제, 0초 프레임이 비면 확인(썸네일). 검은 화면은 평균 밝기 < 10 으로 구분.
  - **멈춤**: 연속 프레임 평균 차이 < 0.15 가 4초 이상.
  - **음량**: loudnorm 측정, 목표 −14±1 LUFS·피크 ≤ −1 dBTP. `--normalize` 는 2패스 loudnorm 으로 오디오만 다시 인코딩(영상 복사).
  - **읽기 시간**: scenes.json `on_screen` 글자 수 vs 나레이션 manifest 장면 길이, 글자 수÷5+1.5초 (장면 단위 근사).
  - **소요시간**: `build/logs/<시작시각>-<작업>.log` 의 시작~수정 시각으로 작업별 최근 소요시간.
  - 초당 움직임 양(`motion_per_second`)도 저장 — P1-1 레퍼런스 측정에서 재사용.
- `render_version.py` 의 `render`·`add`(스킬 스타일 렌더도 `render_style.py` → `add` 경유) 가 새 버전마다 −14 LUFS 정규화 → 검사 → `renders/<파일>.qa.json` + manifest `qa` 요약. `--no-loudnorm`·`--no-qa` 로 끔. numpy 가 없으면 렌더는 남기고 검사만 건너뜀.
- Studio 6단계: 최신 버전 아래 검사 결과 상자(문제·확인이면 펼쳐서 "승인 전에 확인"), 버전 표에 검사 배지(통과 초록 / 확인 주황 / 문제 빨강).
- 보정: 처음 분산 기준 6 은 어두운 방사형 그라데이션 배경(분산 6.15)을 놓침 → 12 로. 경계 에너지는 글자 있는 화면 5.4 vs 빈 배경 0.2 로 확실히 갈림.
- 검증:
  - 합성 영상(빈 그라데이션 0.5초·검은 화면 1.2초·멈춤 4.8초·큰 음량)에서 4가지 모두 검출, 정상 영상은 통과. −22.7 → −14.0 LUFS 정규화 후 영상 스트림 그대로.
  - **실제 렌더(sample-30s, HyperFrames 0.9.7, 무음 대신 사인파 자리표시 음성)**: 장면 경계 4곳에서 0.3~0.4초 빈 화면 (6.5·12.6·20.0·29.4초) — 템플릿의 "장면 끝 opacity 0" 때문. 24.4~29.2초 4.8초 멈춤. 프레임을 직접 보고 모두 실제 문제임을 확인 → P0-1 규칙(겹치는 전환·관통 요소)의 필요성 확인.

## 14. 레퍼런스 영상 측정 (P1-1) (2026-11-12)

4단계 워크플로의 "측정 먼저, 추정 금지"를 도구로. 같은 코드로 결과물도 재서 대조한다.

- `tools/ref_measure.py measure <영상> [--range 0:30-1:30]` → `<영상>.measure/` 에 `spec.json`(수치), `spec.md`(레퍼런스 스펙 시트), `contact.jpg`(약 24칸 컨택트 시트), `cuts.jpg`(앞쪽 전환 8개의 직전·직후 프레임).
- `tools/ref_measure.py compare <레퍼런스> <결과>` → `compare.md/json`: 항목별 레퍼런스·결과·차이·판정(±20%, 절대값), 시간 10등분 움직임 양, 팔레트 거리(RGB 40 이하 통과).
- 측정 (원본 fps, 96×54):
  - **전환**: 컷·플래시·페이드는 RGB 프레임 차이 급증(≥6 이고 주변 중앙값의 4배), 디졸브·와이프는 0.25초 간격 누적 차이(주변의 2.2배 이상 + 4). 방식은 컷 / 점진(추정) / 검은 페이드 / 플래시. 쪼개진 전환은 합침.
  - **실효 fps**: 움직이는 동안 그림이 몇 프레임씩 유지되는지(홀드 패턴). 노이즈 바닥(하위 20% 차이의 2배)보다 큰 변화만 새 그림으로 셈.
  - **움직임 양**: 초당 평균 프레임 차이(절대값), 샷별, 마지막 2초.
  - **그레인·보일링**: 480×270 에서 매 프레임 2단계 넘게 바뀌는 픽셀 비율(3구간 중앙값). 0.1 초과면 살아 있는 그레인.
  - **색**: 1fps·64×36 k-means 8색 팔레트(HEX·비율), 평균 채도·명도, 흰색·어두운 비율.
  - 재지 않음: 사운드(BPM — P2-1), 카메라 방향·이징·질감 → spec.md 에 "눈으로 채울 항목(추정)"으로 남김.
- qa_render.py 의 `grey_frames()` 를 크기·컬러·원본 fps 를 받도록 넓혀 공유.
- 보정 과정 (합성 정답 영상: 24fps 2프레임 유지 = 실효 12fps, 3.0초 컷 · 6.0초 0.5초 디졸브 · 9.0초 검은 페이드, 그레인, 리소그래프 팔레트):
  1. 회색 차이만 보면 밝기가 같은 두 장면 사이 컷을 놓침 → RGB 차이로.
  2. 디졸브는 프레임당 변화가 작아 놓침 → 0.25초 누적 차이 + 별도 기준(2.2배·+4).
  3. 그레인이 있으면 매 프레임이 "변화"로 잡혀 홀드 패턴 실패 → 노이즈 바닥 기반 임계값.
  4. 어두운 배경의 검은 페이드가 점진+페이드 둘로 쪼개짐 → 가까운 전환 합치기(페이드·플래시 우선).
  5. 96×54 에선 그레인이 평균에 묻혀 작은 도형 움직임과 구분 불가 → 480×270 픽셀 비율(그레인 0.345 vs 없음 ≤0.012).
- 검증: 정답 영상에서 전환 3개(시각·방식)·실효 12fps·그레인·팔레트(`#F1EEE5` `#E3EFEB` `#047E84` …) 모두 맞음. 일부러 다르게 만든 결과물(30fps 매 프레임·어두운 고채도·그레인 없음)과 대조 시 fps·움직임·그레인·색 차이를 모두 ❌, 같은 전환 구조는 ✅. 같은 영상끼리 대조는 0개 초과. 실제 렌더(sample-30s): 장면 경계 4곳 + 장면 안 전환 1곳, cuts.jpg 에서 빈 화면 확인(P0-2 결과와 일치).
- 한계: 점진 전환의 종류(디졸브/와이프/줌)는 구분하지 않음(추정 표시), YouTube 링크는 직접 못 읽음(파일을 받아서), 5분 원본 fps 분석은 수십 초~1분.

