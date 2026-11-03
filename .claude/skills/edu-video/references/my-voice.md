# 내 목소리 내레이션 — 로컬 Qwen3-TTS 보이스 클론

클라우드 TTS 대신 **내 PC에서** 내 목소리로 대본을 읽힌다. 비용과 외부 전송이 없다.
엔진: [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) (Apache-2.0), PyPI `qwen-tts`. Base 모델이 3초 이상의 참조 음성으로 목소리를 복제한다. 한국어를 지원한다(`language="korean"`).

## 사양

| 모델 | 권장 하드웨어 | 비고 |
|---|---|---|
| `Qwen3-TTS-12Hz-1.7B-Base` (기본) | NVIDIA 6~8GB VRAM / Apple Silicon 16GB+ | 품질 우선 |
| `Qwen3-TTS-12Hz-0.6B-Base` | NVIDIA 4~6GB / CPU(느림) | 저사양 |

Python 3.12 권장, ffmpeg 필수, sox 권장.

## 1. 설치 (최초 1회)

```bash
bash tools/setup_qwen_tts.sh 1.7B
source ~/.edu-video/qwen-venv/bin/activate
export QWEN_TTS_MODEL=~/.edu-video/models/Qwen3-TTS-12Hz-1.7B-Base
```

## 2. 목소리 녹음 (품질의 80%가 여기서 결정)

- **10~15초**, 조용한 방, 입과 마이크 거리 한 뼘, 스마트폰 음성메모로 충분
- 강의할 때의 말투 그대로, 또박또박. 웃음·기침·배경음악 없이
- 읽을 문장을 미리 정하고 **그 문장을 정확히 기록**한다(ICL 모드에 필요)
- 예시 문장: "안녕하세요. 오늘은 영상을 코드로 만드는 방법을 알아보겠습니다. 어렵지 않으니 천천히 따라오세요."

```bash
python tools/voice_clone.py prep 녹음.m4a -o ~/.edu-video/voices/me.wav
```
(모노 24kHz, 저역 잡음 제거, 앞뒤 무음 제거, 음량 정규화)

## 3. 목소리 등록 (한 번만, 이후 재사용)

```bash
python tools/voice_clone.py enroll ~/.edu-video/voices/me.wav \
  --name me --text "안녕하세요. 오늘은 영상을 코드로 만드는 방법을 알아보겠습니다. 어렵지 않으니 천천히 따라오세요." \
  --test "이 목소리가 제 목소리처럼 들리나요?"
```
→ `~/.edu-video/voices/me.pt` (복제 프롬프트 캐시), `me.test.wav`를 들어보고 어색하면 다시 녹음.
대본을 모를 때는 `--xvector-only`(유사도는 낮아짐).

## 4. 대본 읽히기 → 영상에 입히기

**A. 이미 렌더한 영상에 그대로 입히기** (장면 길이 유지):
```bash
python .../voice_clone.py narrate <프로젝트>/script.json --voice me --keep-timing
python .../voice_clone.py mux out/lecture.mp4 <프로젝트>/script.json -o out/lecture-voiced.mp4 [--music bgm.mp3]
```
장면보다 긴 내레이션은 경고가 뜬다 → 문장을 줄이거나 B로.

**B. 목소리 길이에 맞춰 다시 렌더** (권장, 등장 타이밍이 말과 맞음):
```bash
python .../voice_clone.py narrate <프로젝트>/script.json --voice me
```
`script.json`의 start/duration이 갱신된다 → 루트 `index.html`의 장면 `data-start/data-duration`과
`<audio id="vo-<id>" src="assets/voice/<id>.wav" data-start=… data-volume="1">`를 맞추고 `npx hyperframes render`.

## 품질 조절

- 발음이 뭉개지거나 반복: `--temperature 0.7 --repetition-penalty 1.1`
- 문장마다 톤이 다름: 장면 대본을 비슷한 길이(40~55자)로, `--batch 1`로 한 문장씩
- 영어 용어(Remotion 등)가 어색: 대본에 한글 발음으로 적기 ("리모션")
- 숫자: "22 이상" → "이십이 이상"처럼 읽을 형태로

## 게시 전 확인

- 복제는 **본인 목소리만**(타인은 서면 동의).
- YouTube 등은 사실적인 합성 음성에 'AI 생성/변경 콘텐츠' 표시를 요구한다. 업로드 시 해당 항목을 체크한다.
- 참조 음성(`me.wav`, `me.pt`)은 생체정보에 가깝다. 저장소에 커밋하지 않는다(`~/.edu-video/`에만 둔다).
