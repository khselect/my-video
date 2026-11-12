---
name: edu-video
description: PDF·HTML·Markdown 문서를 진행자 없는 애니메이션 강의 영상(모션그래픽 + 내레이션 + 자막)으로 만드는 개인 워크플로. "이 PDF로 강의 영상 만들어줘", "문서를 설명 영상으로", "교육 콘텐츠 렌더링" 같은 요청에 사용. HyperFrames(HTML→MP4)를 렌더 엔진으로 쓴다.
---

# edu-video — 문서 → 애니메이션 강의 영상

입력: PDF / HTML / Markdown 문서 1개 (또는 URL을 저장한 HTML)
출력: 1920×1080 MP4 (진행자 없음) + 대본 `script.json` + HyperFrames 프로젝트 폴더

렌더 규칙(Contract)은 HyperFrames 스킬(`/hyperframes:hyperframes`)을 따른다. 이 스킬은 그 위에 얹는 **나만의 강의 제작 규칙**이다.

## 0. 준비 (최초 1회)

```bash
bash tools/new_project.sh <프로젝트폴더>
```
HyperFrames 프로젝트를 만들고 GSAP와 한글 폰트(Pretendard)를 `assets/`에 로컬로 넣는다. CDN이 막힌 환경에서도 렌더가 된다.
필요 조건: Node.js 22+, ffmpeg, Python 3.10+. API 키는 `references/apis.md` 참고.

## 1. 원문 추출

```bash
python3 tools/extract_source.py <문서> <프로젝트폴더>
```
→ `source/source.md`(페이지 구분 포함), PDF면 `source/pages/page-N.png`(원본 도식을 그대로 화면에 쓸 때).

## 2. 강의 설계 → `script.json`

`source.md`를 끝까지 읽고 `references/script-template.json` 형식으로 대본을 쓴다.

- **한 영상 = 한 가지 핵심 아이디어.** 끝날 때 시청자가 한 문장으로 말할 수 있어야 한다.
- 구조: 질문으로 시작(hook) → 개념 1개씩 → 구체 예시 1개를 끝까지 → 정리 한 줄.
- 장면당 내레이션 **약 19단어(한국어 약 40~55자)**, 4~9초. 30~90초 영상이면 6~10장면.
- 각 장면에 `shape`(아래 7가지 중 하나)를 먼저 고르고, 그다음 그림을 정한다. 비슷한 문장이 같은 그림이 되지 않게.
- 원문에 없는 숫자는 쓰지 않는다. 쓰면 `"illustrative": true`로 표시한다.
- 사용자에게 대본(장면 제목 + 내레이션)을 먼저 보여주고 승인받는다. 강조할 관점을 묻는다.

### 장면 shape 7가지 (references/style-guide.md에 예시 코드 위치)
| shape | 쓰는 때 | 데모 예시 |
|---|---|---|
| `transform` | A가 B로 바뀐다 (전→후) | hook: 타임라인 막대 → 코드 줄 |
| `cycle` | 반복 루프·프로세스 | loop: 말→코드→렌더→확인 |
| `checklist-terminal` | 준비물·명령 실행 | prep: 터미널에 ✓ |
| `stack` | 계층·구성요소가 쌓임 | stack: 3개 층 + 숫자 카운트업 |
| `axis` | 비교를 한 축 위에 배치 | license: 조건 있음 ↔ 완전 자유 |
| `converge` | 여러 개 → 하나의 결론 | outro: 칩 3개 → 한 줄 |
| `source-figure` | 원문 도표·페이지를 그대로 보여주고 동그라미 | `source/pages/*.png` 사용 |

## 3. 내레이션 생성

```bash
python3 tools/tts.py <프로젝트폴더>/script.json --provider google
```
→ `assets/voice/<scene-id>.mp3` + `script.json`에 각 장면 `duration` 기록(음성 길이 + 0.6초 여유).
키가 없거나 네트워크가 막히면 `--provider none`: 글자 수로 길이를 추정하고 무음으로 진행(화면 텍스트가 설명을 맡음).

**내 목소리로 (로컬, 무료):** Qwen3-TTS 보이스 클론 — `references/my-voice.md`.
```bash
python3 tools/voice_clone.py narrate <프로젝트폴더>/script.json --voice me
# 이미 렌더한 영상에 바로 입히기:
python3 tools/voice_clone.py narrate <프로젝트폴더>/script.json --voice me --keep-timing
python3 tools/voice_clone.py mux out/lecture.mp4 <프로젝트폴더>/script.json -o out/lecture-voiced.mp4
```

단어 단위 자막이 필요하면: `npx hyperframes transcribe assets/voice/<id>.mp3 --language ko`.

## 4. 장면 제작

- `templates/example-lecture/`가 기준 구현이다. 새 장면은 이 파일들을 복사해 고친다.
- 장면 1개 = `compositions/<id>.html` 1개. 호스트 id = composition id = timeline key (다르면 렌더가 45초씩 멈춘다).
- 장면 길이는 `script.json`의 `duration`을 그대로 쓰고, 내레이션이 그 요소를 **말하는 순간** 화면에 등장시킨다.
- 내레이션 `<audio id="vo-<id>" data-start=… data-volume="1">`는 루트 `index.html`에 둔다.
- 디자인 토큰·타이포·금지 패턴: `references/style-guide.md`.
- **이징·카메라·장면 연결·글자 유지 시간: `references/motion-rules.md`** (모든 장면에 적용, 끝에 6절 체크리스트로 확인).

## 5. 검수 → 렌더

```bash
cd <프로젝트폴더>
npx hyperframes check --json        # error 0개까지
npx hyperframes snapshot --review   # 장면별 프레임 확인 후 고칠 점 반영
npx hyperframes render -o out/lecture.mp4
```

**버전 관리 렌더 (권장):** 렌더마다 `renders/v003_<날짜>_<커밋>.mp4`로 저장하고 `renders/manifest.json`에 기록한다.
영상은 git에서 제외되고 manifest만 커밋된다. 수정 = 소스 커밋, 렌더 = 그 커밋의 결과물.
```bash
python3 tools/render_version.py render --note "자막 크기 키움"          # HyperFrames
python3 tools/render_version.py render --composition HelloWorld        # Remotion (id는 다음부터 기억)
python3 tools/render_version.py add out/lecture-voiced.mp4 --from v003 --kind voiced
python3 tools/render_version.py list
python3 tools/render_version.py show v003     # 그 버전을 다시 만드는 방법
```
미커밋 상태로 렌더하면 파일명에 `-dirty`가 붙는다. 다시 만들 수 있게 하려면 먼저 커밋하거나 `--require-clean`.
`check`에서 꼭 볼 것: `text_below_floor`(28px 미만), `first_frame_empty`(0초에 제목이 보여야 썸네일이 산다), 안전영역 밖 배치.

## 6. 마무리

- 영상과 `script.json`을 사용자에게 보낸다.
- 위키에 남길 가치가 있으면 `Wiki/learning/`에 summary 페이지로 등록 제안 (CLAUDE.md Ingest 규칙).
