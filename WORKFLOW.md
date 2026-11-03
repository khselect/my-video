# WORKFLOW — 문서로 진행자 없는 애니메이션 강의 만들기

PDF·HTML·Markdown 문서 한 건을 **내레이션 + 모션그래픽 강의 영상**으로 만드는 전체 절차입니다.
원칙은 두 가지입니다.

1. **나레이션을 먼저 만들고, 영상을 그 길이에 맞춘다.** 장면 길이는 `build/audio/manifest.json`이 정한다.
2. **단계마다 사람이 승인한다.** 앞 단계를 고치면 뒤 단계 승인은 자동으로 무효(stale)가 된다.

```
문서 분석 → 장면 스크립트 → 나레이션 → 모션그래픽 → 렌더 → 합성·게시
 [1 원문]    [2 기획][3 대본]  [4 나레이션]  [5 장면]    [6 렌더]  [7 게시]
   ✋           ✋      ✋          ✋           ✋          ✋        ✋   ← 사람 승인 지점
```

가장 쉬운 진행 방법은 **Lecture Studio**(6장)입니다. 같은 일을 명령어로 하려면 4장을 따르세요.

---

## 1. 필요한 API

**필수 키는 없습니다.** 로컬 Qwen3-TTS로 나레이션을, HyperFrames·Remotion으로 렌더를 하면 키 없이 끝까지 갑니다.
키는 `.env`에 넣습니다(git 제외). 아래는 품질을 올리고 싶을 때 쓰는 선택 항목입니다.

| 용도 | 환경변수 | 비용 | 메모 |
|---|---|---|---|
| 스톡 영상·사진 | `PEXELS_API_KEY`, `PIXABAY_API_KEY` | 무료 | 권장. OpenMontage도 같은 키를 씀 |
| 나레이션·이미지 (키 하나로) | `GOOGLE_API_KEY` | 무료 할당량 | Gemini TTS + 이미지 생성 |
| 나레이션 품질 업그레이드 | `ELEVENLABS_API_KEY` 또는 `OPENAI_API_KEY` | 유료 | 한국어 자연스러움은 ElevenLabs가 가장 좋음 |
| 단어 단위 자막 | `DASHSCOPE_API_KEY` | 유료 | 로컬 대안: `npx hyperframes transcribe` (whisper) |
| 배경음악 | `SUNO_API_KEY` | 유료 | 무료 대안: Pixabay Music |
| 스크립트 작성 | (없음) | — | Claude Code가 직접 씀. Anthropic API 키 불필요 |

---

## 2. 폴더 구조와 기기 간 동기화 (Windows PC ↔ MacBook)

```
video-tools/                    ← 저장소 아님. 세 폴더를 나란히 둔다
├─ my-video/                    ← git 저장소 khselect/my-video (이 파일)
│  ├─ WORKFLOW.md               ← 이 문서
│  ├─ scenes.example.json       ← 장면 스크립트 형식 예시
│  ├─ sources/                  ← 원문 문서 (PDF·HTML·MD는 커밋, 영상·음성은 제외)
│  ├─ lectures/<강의>/           ← 강의 1편 = HyperFrames 프로젝트 1개
│  │  ├─ lecture.json           ← 승인 기록 (Studio가 관리)
│  │  ├─ scenes.json            ← 장면 스크립트 (커밋)
│  │  ├─ index.html, compositions/  ← 모션그래픽 소스 (커밋)
│  │  ├─ build/audio/           ← 나레이션 wav + manifest.json (재생성 가능, 제외)
│  │  └─ renders/               ← vNNN 영상 (제외) + manifest.json (커밋)
│  ├─ tools/                    ← narrate.py, voice_clone.py, render_version.py, new_lecture.py, extract_source.py
│  ├─ studio/                   ← Lecture Studio (HITL 앱)
│  ├─ src/                      ← Remotion 템플릿 (여러 강의에 재사용)
│  └─ .claude/skills/           ← edu-video 스킬 + Remotion 공식 스킬
├─ OpenMontage/                 ← 원본 clone (커밋 안 함, 필요하면 다시 clone)
└─ qwen-tts-env/                ← Python 가상환경 (커밋 안 함, 기기마다 새로 설치)
```

**커밋하는 것**: 내가 만든 소스(대본, 장면 HTML, 설정, 도구)와 버전 기록.
**커밋하지 않는 것**: 영상·음성 파일, 가상환경, node_modules, 폰트·GSAP(npm에서 다시 받음), 목소리 녹음과 클론 프로필, `.env`.

### MacBook에서 이어서 작업하기 (처음 한 번)

```bash
cd ~/Developments/video-tools
git clone https://github.com/khselect/my-video.git
cd my-video && npm install
python3 tools/new_lecture.py <강의이름> --restore-assets      # 강의마다: 폰트·GSAP 다시 받기
bash tools/setup_qwen_tts.sh 1.7B                               # Apple Silicon 16GB+ 권장, 아니면 0.6B
```
그리고 Studio의 "이 PC 설정"에서 qwen-tts Python 경로를 맥 경로로 저장합니다 (`~/.edu-video/qwen-venv/bin/python`).
목소리 클론 프로필(`~/.edu-video/voices/`)은 git으로 옮기지 말고, 맥에서 다시 `enroll` 하거나 개인 드라이브로 직접 복사합니다.

### 매일 작업 흐름

```bash
git pull                       # 시작할 때
# … 작업 …
git add -A && git commit -m "s03 도식 수정"   # 렌더 전에 커밋하면 그 버전을 언제든 다시 만들 수 있음
git push                       # 끝날 때
```

---

## 3. 장면 스크립트 형식 (`scenes.json`)

`scenes.example.json`을 보세요. 최상위에 `language`, `speaker`(CustomVoice 화자), `voice`(내 목소리 프로필)를 두고, 장면마다:

| 필드 | 필수 | 뜻 |
|---|---|---|
| `id` | ✓ | `s01`, `s02` … (파일 이름이 됨, 중복 금지) |
| `narration` | ✓ | 읽을 문장. 장면당 40~55자(약 4~9초). 영어 이름·숫자는 읽는 형태로 ("리모션", "이십이") |
| `shape` | ✓ | 화면 구성: transform, cycle, checklist-terminal, stack, axis, converge, source-figure |
| `on_screen` | | 화면에 띄울 짧은 문구 (내레이션을 그대로 옮기지 않음) |
| `visual` | | 그림 설명 — 모션그래픽을 만들 때 지시문 |
| `instruct` | | CustomVoice 말투 지시 (예: "호기심을 끄는 밝은 톤으로") |
| `pause_after` | | 장면 끝 여백(초), 기본 0.5 |
| `source_ref` | | 원문 위치 (예: p.2) — 사실 확인용 |

---

## 4. 단계별 작업

각 단계: **무엇을 하나 → 명령 → ✋ 사람이 확인할 것 → 산출물**

### 단계 1. 원문 (source)

원문을 `sources/`에 넣고 텍스트를 뽑습니다.
```bash
python tools/new_lecture.py oss-video-tools --title "클로드로 영상 만드는 오픈소스 3개"
python tools/extract_source.py sources/설치가이드.pdf lectures/oss-video-tools
```
✋ 표·목록이 깨지지 않았는지, 빠진 페이지가 없는지 `source/source.md`를 훑어봅니다.
→ `source/source.md`, `source/pages/page-N.png`(원문 도표를 화면에 쓸 때)

### 단계 2. 기획 (brief)

✋ 클로드가 쓰기 전에 사람이 정합니다: **핵심 아이디어 한 문장**, 대상, 강조할 관점(또는 뺄 내용), 목표 길이, 화자.
→ `lecture.json`의 `brief`

### 단계 3. 대본 (script)

Claude Code가 `source.md`와 brief로 `scenes.json`을 씁니다 (Studio의 "Claude로 초안 생성", 또는 Claude Code에 "lectures/oss-video-tools 대본 써줘").
✋ 확인할 것: 한 영상 = 한 아이디어 / 질문으로 시작 → 개념 → 예시 하나를 끝까지 → 정리 한 줄 / 원문에 없는 숫자 없음 / 장면마다 다른 shape.
→ `scenes.json`

### 단계 4. 나레이션 (narration) — `tools/narrate.py`

* **입력**: 장면 스크립트 JSON (`scenes.example.json` 형식)
* **출력**: `build/audio/`에 장면별 `<id>.wav`, 이어 붙인 `narration.wav`, 장면별 `start`/`duration`이 담긴 `manifest.json`. **영상 길이는 이 manifest에 맞춰 싱크를 잡습니다.**
* **캐시**: 이미 만든 장면은 건너뜁니다. 문장을 고친 장면은 자동으로 다시 만들고, 그대로인데 다시 듣고 싶은 장면은 `--force s02`로 지정합니다. `--force`만 쓰면 전부 다시 만듭니다.
* **백엔드**: `customvoice`(기본, 내장 화자 `sohee` 등) · `clone`(내 목소리, 8장) · `silent`(모델 없이 길이만 — GPU 없는 기기에서 화면 작업용)
* **속도 참고**: 이전 버전 테스트에서 `sohee` 화자로 2개 장면(14.2초 분량)에 장면당 약 50초 걸렸습니다(Windows PC GPU).

Windows (PowerShell):
```powershell
$env:PYTHONUTF8="1"
C:\Developments\qwen-tts-env\Scripts\python.exe tools\narrate.py lectures\oss-video-tools\scenes.json --out lectures\oss-video-tools\build\audio
C:\Developments\qwen-tts-env\Scripts\python.exe tools\narrate.py lectures\oss-video-tools\scenes.json --out lectures\oss-video-tools\build\audio --force s02
```
macOS:
```bash
~/.edu-video/qwen-venv/bin/python tools/narrate.py lectures/oss-video-tools/scenes.json --out lectures/oss-video-tools/build/audio
```
`manifest.json` 예:
```json
{ "backend": "customvoice", "speaker": "sohee", "total_duration": 10.2,
  "scenes": [ { "id": "s01", "start": 0.0, "duration": 4.8, "voice_start": 0.3, "voice_seconds": 4.0, "file": "s01.wav" } ] }
```
✋ 장면마다 들어봅니다: 영어·숫자 발음, 문장 끝 억양, 장면 간 톤 차이. 어색한 장면만 문장을 고치거나 `--force`로 다시 만듭니다.
발음이 계속 어색하면 다른 화자(`--speaker`)나 Gemini·ElevenLabs(`tools/tts.py`)로 바꿉니다.
→ `build/audio/*` (Studio는 `assets/voice/narration.wav`로도 복사)

### 단계 5. 장면 (visuals)

Claude Code가 `scenes.json`(무엇을)과 `manifest.json`(언제)으로 `compositions/<id>.html`을 만들고, 루트 `index.html`에 `narration.wav`를 넣습니다.
```bash
cd lectures/oss-video-tools
npx hyperframes check            # 규칙 위반 0개까지
npx hyperframes snapshot --review
npx hyperframes preview          # 브라우저에서 미리보기 (수정도 가능)
```
✋ 스냅샷을 보고 장면별로 피드백합니다 ("s03 제목을 더 크게", "화살표 대신 선이 그려지게"). 피드백한 장면만 다시 만듭니다.
확인 기준: 0초 프레임에 제목이 보임(썸네일) / 글자 28px 이상 / 화면 문구 ≠ 내레이션 그대로 / 요소가 말하는 순간 등장.
→ `index.html`, `compositions/*.html`

### 단계 6. 렌더 (render) — 버전 관리

```bash
git add -A && git commit -m "s03 피드백 반영"
python tools/render_version.py render lectures/oss-video-tools --note "s03 피드백 반영"
python tools/render_version.py list lectures/oss-video-tools
```
→ `renders/v003_2026-11-04_e4f5g6h.mp4` + `renders/manifest.json`(버전·날짜·커밋·길이·sha256·메모).
파일명 끝 `-dirty` = 커밋 안 된 상태로 렌더 → 그 영상은 다시 만들 수 없으니 먼저 커밋하세요.
옛 버전을 다시 만들려면 `render_version.py show v002`가 알려주는 커밋으로 돌아가 렌더합니다.
✋ 처음부터 끝까지 한 번 봅니다: 소리와 화면 싱크, 끊김, 오탈자.

이미 렌더한 영상에 나레이션만 바꿔 입힐 때(다시 렌더 없이):
```bash
python tools/voice_clone.py mux lectures/x/renders/v003_….mp4 lectures/x/build/audio/manifest.json -o out/voiced.mp4 --music bgm.mp3
python tools/render_version.py add out/voiced.mp4 lectures/x --from v003 --kind voiced --note "내 목소리"
```

### 단계 7. 게시 (publish)

✋ 체크리스트를 모두 확인한 뒤 게시합니다.
- [ ] 업로드 화면에서 **AI 합성 음성/영상 표시**를 체크했다 (YouTube는 사실적인 합성 콘텐츠에 표시를 요구)
- [ ] 화면의 숫자·사실을 원문과 대조했다
- [ ] 도구 라이선스: Remotion은 4인 이상 회사면 유료, OpenMontage는 AGPL(고쳐서 서비스하면 소스 공개), HyperFrames는 Apache-2.0
- [ ] 클론한 목소리는 본인 목소리다 (타인은 서면 동의)
- [ ] 제목·설명·썸네일(0초 프레임)

→ `lecture.json`의 `publish`(게시 버전, URL, 날짜)

---

## 5. 엔진 선택

| 상황 | 엔진 | 이유 |
|---|---|---|
| 장면별 도식·타이포 (기본) | **HyperFrames** | HTML/CSS로 장면마다 자유롭게, 클로드가 고치기 쉬움 |
| 여러 강의에 재사용할 템플릿 (인트로, 자막 바, 엔딩) | **Remotion** (`src/`) | React 컴포넌트로 한 번 만들어 props만 바꿔 재사용 |
| 스톡 영상·BGM·품질검사까지 자동화 | **OpenMontage** (`../OpenMontage`) | 파이프라인 12종, Pexels·Pixabay 키 필요 |

---

## 6. Lecture Studio — 승인 지점을 묻는 로컬 앱

```bash
python studio/app.py          # Windows: python, macOS: python3
```
브라우저에서 http://127.0.0.1:8765 를 엽니다 (이 컴퓨터에서만 접속됨).

- 왼쪽에서 강의를 만들거나 고르면, 아직 승인되지 않은 첫 단계가 열립니다.
- 각 단계 화면 아래 **"이 단계 승인 →"** 을 눌러야 다음 단계로 넘어갑니다. 앞 단계가 승인되지 않았으면 거절됩니다.
- 대본·장면 단계의 **"Claude로 … "** 버튼은 `claude -p`(Claude Code 헤드리스)를 실행합니다. Claude Code가 설치·로그인되어 있어야 합니다. 직접 하고 싶으면 **"프롬프트 복사"** 후 Claude Code에 붙여넣으세요.
- 나레이션 단계는 장면별 플레이어와 **좋음/다시** 판단이 있고, '다시'만 골라 재생성합니다. 모두 '좋음'이어야 승인됩니다.
- 긴 작업은 오른쪽 아래 로그 창에 진행 상황이 보이고, 로그는 `lectures/<강의>/build/logs/`에 남습니다.
- **이 PC 설정**: qwen-tts Python 경로, 기본 백엔드·화자는 기기마다 다르므로 `studio/config.local.json`(git 제외)에 저장됩니다.
  - Windows: `C:\Developments\qwen-tts-env\Scripts\python.exe`
  - macOS: `~/.edu-video/qwen-venv/bin/python` (절대경로로)

---

## 7. 렌더 버전 관리 요약

| 명령 | 하는 일 |
|---|---|
| `render_version.py render <강의> --note "…"` | 새 버전 렌더 (엔진 자동 판별: HyperFrames / Remotion) |
| `render_version.py render . --composition HelloWorld` | Remotion 템플릿(`src/`) 렌더 |
| `render_version.py add <파일> <강의> --from v003 --kind voiced` | 밖에서 만든 영상(목소리 합성본 등)을 버전으로 등록 |
| `render_version.py list <강의>` / `show v003 <강의>` | 목록 / 상세 + 다시 만드는 방법 |

---

## 8. 내 목소리로 (Qwen3-TTS 보이스 클론)

자세한 녹음 요령은 `.claude/skills/edu-video/references/my-voice.md`.
```bash
python tools/voice_clone.py prep 녹음.m4a -o ~/.edu-video/voices/me.wav          # 10~15초, 조용한 곳
python tools/voice_clone.py enroll ~/.edu-video/voices/me.wav --name me --text "녹음에서 읽은 문장 그대로" --test "제 목소리 같나요?"
python tools/narrate.py lectures/x/scenes.json --out lectures/x/build/audio --backend clone --voice me
```
목소리 파일과 프로필은 `~/.edu-video/voices/`에만 두고 커밋하지 않습니다.

---

## 9. 문제 해결

| 증상 | 해결 |
|---|---|
| Windows에서 한글이 깨짐 / UnicodeError | `$env:PYTHONUTF8="1"` 후 실행 (Studio는 자동 설정) |
| `qwen_tts` 를 찾을 수 없음 | 나레이션은 qwen-tts 가상환경의 Python으로 실행 (Studio 설정 확인) |
| 렌더 시 폰트·GSAP 없음 | `python tools/new_lecture.py <강의> --restore-assets` |
| 렌더가 장면마다 45초씩 멈춤 | 장면 호스트 id = composition id = timeline 키가 같은지 확인 |
| 나레이션이 장면보다 김 | 문장을 줄이거나 narrate를 다시 돌려 manifest 길이로 장면을 다시 맞춤 |
| `claude` 명령 없음 | Claude Code 설치 후 로그인, 또는 "프롬프트 복사"로 직접 실행 |

---

## 10. 아직 정하지 않은 것

- **참고 영상 스타일**: 참고하려던 YouTube 영상과 skillry 페이지를 아직 보지 못했습니다. 지금 스타일 가이드는 데모 기준(남색 바탕, 앰버·청록·코랄 강조, Pretendard)입니다. 영상의 특징(색, 폰트, 전환, 자막 방식)을 정하면 `.claude/skills/edu-video/references/style-guide.md`에 반영합니다.
- **발음 확인**: 한국어 발음은 `build/audio/s01.wav`를 직접 들어보고, 어색하면 다른 화자나 Gemini/ElevenLabs로 바꿉니다.
- **다음 단계**: PDF 한 건으로 30초 샘플을 1~7단계 끝까지 만들어 보는 것이 가장 빠릅니다.
