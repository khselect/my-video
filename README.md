# my-video — 문서 → 애니메이션 영상 (강의·스토리·홍보)

진행자 없는 영상을 문서 한 편에서 만드는 작업 공간입니다. **전체 절차는 [WORKFLOW.md](WORKFLOW.md)**, 지금까지의 작업 기록은 **[docs/DEVLOG.md](docs/DEVLOG.md)**, 작업 원칙과 모션그래픽 참고 영상 분석·개선 우선순위는 **[CLAUDE.md](CLAUDE.md)** ([조사 자료](docs/research/motion-graphics-prompts.md))를 보세요.

| 하고 싶은 것 | 방법 |
|---|---|
| 승인 단계를 따라가며 만들기 (권장) | `python3 studio/app.py` → http://127.0.0.1:8765 (Lecture Studio) |
| 새 프로젝트 만들기 | Studio 왼쪽 '새 프로젝트' 또는 `python tools/new_lecture.py <이름> --title "제목"` |
| 나레이션 (Qwen 로컬) | `python tools/narrate.py lectures/<이름>/scenes.json --out lectures/<이름>/build/audio` |
| 나레이션 (Fish Audio 내 목소리) | Studio 4단계 '내 목소리 화자' → 백엔드 `fish` (`tools/fish_audio.py`) |
| 장면마다 다른 화자 | Studio 4단계 장면 표의 '화자' 선택, 또는 `narrate.py … --scene-speaker s02=ryan` (기본 화자 = 이 PC 설정) |
| 나레이션 다시 듣기 (음성 인식 대조) | Studio 4단계 '다시 듣기 검사' 또는 `python tools/stt_check.py lectures/<이름>` — 이름·숫자·영어 오독, 빠진 말 |
| 레퍼런스 영상 측정 | Studio 5단계 ② 참고 영상 업로드 → '측정하기', 또는 `python tools/ref_measure.py measure <영상> [--range 0:30-1:30]` |
| 음악 비트 분석 | Studio 5단계 ② '음악·비트', 또는 `python tools/beats.py analyze <음원>` |
| 렌더 자동 검사 | 렌더할 때 자동 (빈 화면·멈춤·음량 −14 LUFS·읽기 시간·레퍼런스 대조·박자), 따로 돌리면 `python tools/qa_render.py <영상> --lecture lectures/<이름>` |
| 영상 형태·스타일 고르기 | Studio 5단계 — 강의 / 스토리 애니메이션 / 홍보·짧은 클립 ([스타일 형식](studio/styles/SCHEMA.md)) |
| 장면 그림 생성 | 로컬 FLUX `tools/sticker_local.py` (무료) 또는 Higgsfield (유료, 'AI 일러스트 모션' 스타일) |
| 버전 붙여 렌더 | `python tools/render_version.py render lectures/<이름> --note "메모"` |
| 영상 제작 전역 스킬 설치 (다른 프로젝트에서도) | `sh tools/install_global_skill.sh` → `~/.claude/skills/motion-video` ([skills/motion-video](skills/motion-video/SKILL.md)) |
| 다른 기기에서 받은 뒤 | `npm install` + `python tools/new_lecture.py <이름> --restore-assets` (+ WORKFLOW 2장 기기 설정) |

### Studio 7단계

`1 원문 → 2 기획 → 3 대본 → 4 나레이션 → 5 장면 → 6 렌더 → 7 게시` — 단계마다 사람이 승인하고, 앞 단계를 고치면 뒤 승인은 무효가 됩니다.
**화면 캡처와 단계별 사용법은 [docs/USAGE.md](docs/USAGE.md)** 에 있습니다.

<a href="docs/USAGE.md"><img src="docs/images/studio/4-narration.png" width="640" alt="Lecture Studio 4단계 나레이션 화면"></a>
긴 작업은 진행률 팝업(%·남은 시간)으로 보입니다.

2026-11-12에 참고 영상(코드 모션그래픽 vs 영상 생성 AI) 분석을 바탕으로 다음을 더했습니다 (자세한 내용은 DEVLOG 12~18장).

| 단계 | 추가된 것 |
|---|---|
| 4 나레이션 | 장면별 화자 선택 · 다시 듣기 검사(확인·다름 장면은 자동 '다시', 사람이 들어 보고 '맞게 들림') |
| 5 장면 | 모든 스타일 제작 지시에 [모션 연출 규칙](.claude/skills/edu-video/references/motion-rules.md)(이징·카메라·장면 연결) · 참고 영상 측정 → 효과 사양표 · 음악 비트 맞춤 · **스토리보드 승인 후 제작** |
| 6 렌더 | 음량 −14 LUFS 자동 정규화 · 자동 검사 배지(통과/확인/문제) · 레퍼런스와 같은 측정 코드로 대조(±20%) · 박자 검사 |

### 필요 환경

| 항목 | 조건 | 쓰는 곳 |
|---|---|---|
| ffmpeg / ffprobe | **5.1 이상** (도구가 `-fps_mode` 사용 — ffmpeg 8+에서 `-vsync` 가 삭제됨) | 측정·검사·비트 도구 전부 |
| numpy | Studio를 띄우는 Python에 설치 (`python3 -m pip install numpy`) | `qa_render` `ref_measure` `beats` |
| faster-whisper | qwen-tts 가상환경에 설치, **PyAV는 16 미만** (`pip install faster-whisper "av<16"` — PyAV 19에서는 오디오를 못 엶) | 다시 듣기 검사 |
| 이 PC 설정 | `studio/config.local.json` (git 제외)에 `"stt_python": "<qwen-tts-env>/bin/python"`, `"stt_engine": "faster-whisper"`, `"stt_model": "small"`(기본, 약 460MB) 또는 `"large-v3"`(약 3GB, 한국어 더 정확) | 다시 듣기 검사 |

Homebrew 기본 ffmpeg에는 `drawtext` 필터가 없어 측정 미리보기(contact.jpg·cuts.jpg)에 시간 표시가 빠집니다. 이미지와 수치는 정상으로 나옵니다.

### 유료 서비스 (선택)

| 서비스 | 쓰는 곳 | 비용 (2026-11-06) | 안전장치 |
|---|---|---|---|
| Higgsfield (claude.ai 커넥터) | 5단계 'AI 일러스트 모션' 그림 | 이미지 1크레딧/장, 5초 영상 약 35 | 제작 전 확인 창, 잔액 선확인, 부족분은 로컬 FLUX |
| Fish Audio (claude.ai 커넥터) | 4단계 내 목소리 화자·나레이션 | 텍스트 1바이트 ≈ 1크레딧 (한글 1자 ≈ 3) | 생성 전 확인 창, 잔액 부족 시 생성 안 함 |

그 외는 모두 로컬·무료입니다 (Qwen3-TTS, FLUX.1-schnell, rembg, HyperFrames).

같은 폴더 레벨의 `../OpenMontage`, `../qwen-tts-env`, `../image-env` 와 `video-skills/`(가져온 스킬)는 이 저장소에 포함하지 않습니다 (WORKFLOW.md 2장).

---

## Remotion 템플릿 (src/)

<p align="center">
  <a href="https://github.com/remotion-dev/logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-dark.apng">
      <img alt="Animated Remotion Logo" src="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-light.gif">
    </picture>
  </a>
</p>

Welcome to your Remotion project!

## Commands

**Install Dependencies**

```console
npm i --loglevel=error
```

**Start Preview**

```console
npm run dev
```

**Render video**

```console
npx remotion render
```

**Upgrade Remotion**

```console
npx remotion upgrade
```

## Docs

Get started with Remotion by reading the [fundamentals page](https://www.remotion.dev/docs/the-fundamentals).

## Help

We provide help on our [Discord server](https://discord.gg/6VzzNDwUwV).

## Issues

Found an issue with Remotion? [File an issue here](https://github.com/remotion-dev/remotion/issues/new).

## License

Note that for some entities a company license is needed. [Read the terms here](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md).
