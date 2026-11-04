# 영상 스타일 manifest (`studio/styles/<id>.json`)

Lecture Studio 5단계(장면)에서 고를 수 있는 "영상 생성 스킬" 하나를 설명하는 파일이다.
스킬 본체(SKILL.md·scripts·references)는 `video-skills/<폴더>/`(git 제외)에, 이 manifest 는 git 에 둔다.

```json
{
  "id": "paper-cutout",                 // 파일 이름과 같게, 영문 소문자·숫자·-
  "name": "종이 콜라주 스토리",           // 화면에 보일 이름
  "category": "story",                  // "lecture"(강의 동영상) | "story"(스토리 애니메이션) | "promo"(홍보·짧은 클립)
  "kind": "스토리북 · 35~50초",           // 짧은 부가 설명 (형식·길이)
  "summary": "한두 문장 설명",
  "skill_dir": "video-skills/bs-paper-cutout-story-video",   // ROOT 기준 상대 경로
  "engine": "skill",                    // "edu-video"(내장 HyperFrames 강의) | "skill"(스킬 자체 스크립트)
  "narration": "overlay",               // "sync"  나레이션 길이가 장면 타이밍을 정함
                                        // "overlay" 장면 길이를 나레이션에 맞추고 렌더 때 음성을 얹음
                                        // "none"  나레이션을 쓰지 않음 (음악만 / 무음)
  "fit": ["어린이 교육", "이야기 요약"],    // 잘 맞는 용도 태그
  "cautions": ["주의할 점"],             // 화면에 경고로 표시
  "options": [                          // 5단계에서 고르는 옵션 (SKILL.md 의 기본 기능)
    { "key": "theme", "label": "배경 세계", "type": "select", "default": "meadow",
      "choices": [["meadow", "초록 들판 (기본)"], ["snow", "겨울 눈"]], "help": "설명(선택)" },
    { "key": "product_url", "label": "제품 URL", "type": "text", "required": true },
    { "key": "accent", "label": "강조색", "type": "color", "default": "#1F6FEB", "show_if": {"theme": "brand"} },
    { "key": "slots", "label": "문구", "type": "textarea" }
  ],
  "prompt": "Claude 에게 줄 제작 지시 (아래 치환자 사용)",
  "bash": ["node {skill}/scripts/*", "ffprobe *"],      // Claude 가 실행해도 되는 명령 (Bash(...) 규칙)
  "qa":     ["node", "{skill}/scripts/qa.mjs", "{work}/film", "--out", "{work}/qa", "--per-scene", "2"],
  "qa_images": "qa/sheet-*.png",                       // {work} 기준, 5단계에 미리보기로 표시
  "render": ["node", "{skill}/scripts/render.mjs", "{work}/film", "--out", "{out}", "--resolution", "{opt.resolution}"],
  "render_audio": ["--audio", "{audio}"]               // 오디오가 있을 때 render 뒤에 붙임. 없으면 렌더 후 ffmpeg 로 합침
}
```

## plan — 장면 구성표 (5단계 ③)

스타일의 **기본 화면 구성**을 장면마다 미리 채운 표. 사용자는 렌더될 화면을 예상하며 칸을 고치고,
고친 칸(★)은 그대로, 나머지는 기본안으로 Claude 에게 전달된다. 마지막 제작 이후 바뀐 행만 다시 반영할 수도 있다.

```json
"plan": {
  "rows": "scenes",                 // "scenes" = 대본(scenes.json) 장면마다 한 행 (시간은 나레이션 manifest)
                                    // "fixed"  = fixed_rows 의 고정 구간 (고정 안무·템플릿 슬롯)
  "note": "표 위에 보일 설명",
  "no_note": false,                 // true 면 '수정 요청' 열을 붙이지 않음
  "columns": [
    { "key": "type", "label": "화면 구성", "type": "select", "choices": [["paper", "종이 배경"], ["world", "풍경"]],
      "default": { "first": "paper", "last": "end", "cycle": ["world", "paper", "steps"] } },   // 위치별 순서
    { "key": "transition", "label": "전환", "type": "select", "choices": [["cut", "컷"]],
      "default": { "first": "cut", "from": "type", "map": { "world": "cut", "paper": "push" } } },  // 다른 열 값에서 유도
    { "key": "text", "label": "화면 글자", "type": "text", "default": "scene.on_screen" },      // 대본 장면 필드
    { "key": "accent", "label": "색", "type": "text", "default": "opt.accent" },               // 고른 옵션 값
    { "key": "copy", "label": "문구", "type": "text", "default": "", "placeholder": "(자동)" }  // 빈 값 = Claude 가 채움
  ],
  "fixed_rows": [ { "id": "brand", "label": "브랜드", "time": "5–9초", "limit": 24, "hint": "예시·제한",
                    "values": { "copy": "기본 문구" } } ]
}
```

## 치환자

| 치환자 | 값 |
|---|---|
| `{skill}` | 스킬 폴더 절대 경로 |
| `{work}` | 이 강의의 스타일 작업 폴더 `lectures/<slug>/style-<id>/` 절대 경로 (Claude 의 작업 위치) |
| `{lecture}` | 강의 폴더 절대 경로 (source/source.md, scenes.json, build/audio/manifest.json) |
| `{slug}` `{title}` | 강의 이름·제목 |
| `{out}` | 렌더 결과 mp4 경로 (Studio 가 정함) |
| `{audio}` | 나레이션(+음악) 합친 wav 경로 |
| `{opt.<key>}` | 고른 옵션 값 |
| `{tools}` | my-video/tools 절대 경로 (예: `{image_python} {tools}/sticker_local.py`) |
| `{image_python}` | 로컬 이미지 생성 Python (이 PC 설정) |
| `{ref}` | 참고 스타일 폴더 `lectures/<slug>/style-ref/` (brief.md) |

## 규칙

- `render` 가 없으면 장면 제작 단계에서 Claude 가 `{work}/output.mp4` 를 만들어야 하고, 6단계는 그 파일을 버전으로 등록한다.
- 유료 API(FAL, ElevenLabs 등)는 Studio 에서 호출하지 않는다. 이야기 캐릭터·이미지는 `tools/sticker_local.py`(로컬 FLUX, 무료)로 만든다. 음악은 "없음" 또는 사용자가 가진 음원 파일만.
- 내용(문구·장면)은 항상 강의의 원문·기획·대본에서 온다. 스킬 예시의 문구를 그대로 쓰지 않는다.
