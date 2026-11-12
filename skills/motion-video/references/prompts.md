# 검증된 프롬프트 패턴

출처: 디자인하는AI 「코드 기반 모션그래픽」 실험 영상(2026-11-09)과 공유 프롬프트 모음. 원문은 작성자의 것이라 **구조와 요구 사항만** 정리했다 (규칙형 스타일의 짧은 한 줄은 출처 표시 후 인용).
실험 조건: Claude Opus, 추론 '높음' 이상 — 낮추면 결과도 낮아졌다. 프로젝트 폴더를 지정하면 결과(HTML·MP4)가 거기 남는다.

## 목차
1. 싱글 프롬프트 쇼릴 · 2. 음악 BPM 맞춤 · 3. 상세 프롬프트 재사용 · 4. 규칙형 스타일 6종 · 5. 레퍼런스 분석 · 6. 분석 → 설명 영상 + TTS · 7. 카메라 피드백 · 8. 스타일을 스킬로 · 9. 이미지 + 코드 4단계 · 10. 실제 비용

## 1. 싱글 프롬프트 쇼릴 (약 20분)
구성: "뛰어난 모션 디자이너의 포트폴리오 쇼릴, 15초, 역동적" + **콘텐츠는 [대상]을 웹에서 리서치해 채울 것** + "가능한 기술·아이디어 총동원".
결과: 깔끔하지만 텍스트·그래픽 위주로 단조롭고 음악도 단조로움 → 기본값의 한계. 리서치 대상을 비우면 무관한 내용이 나온다.

## 2. 음악 BPM 맞춤
구성: 음원 첨부 + "**먼저** BPM·박자·강조 타이밍(스톰프·클랩)을 분석하고, 모든 화면 전환과 텍스트 등장을 비트에 맞춰라. 길이 = 음원 길이, 1920×1080 MP4".
결과: 박자감·키네틱 느낌은 올라가지만 전체 품질은 크게 변하지 않음. → 이 스킬에서는 `scripts/beats.py analyze` 로 숫자를 먼저 뽑아 지시에 넣고, `check` 로 검수한다.

## 3. 잘 쓴 상세 프롬프트 재사용
모션 프롬프트 모음 사이트(prompt-motion.com)의 카드 프롬프트 전문 + "이 프롬프트로 만들어줘". 이징·카메라 무빙·타이밍·컬러가 지정돼 있어 품질이 크게 오른다(UI 모핑 예: 부드러운 감속 이징, 클릭 반응 마이크로 애니메이션, 음악에 맞는 리듬, 움직이는 중에도 또렷한 글자).
한계: 연출·구성이 원본을 따라간다 → 내 정보를 덧붙이는 용도로. 같은 프롬프트로 다른 모델은 이징이 빠져 뻣뻣했다 — 모델 차이는 줄지만 사라지지 않는다.
교훈: **좋은 프롬프트 = 디자이너가 정할 요소(이징·카메라·타이밍·색)를 하나씩 쓴 것.** 용어를 모르면 [motion-rules.md](motion-rules.md) 1·2절의 이름을 그대로 쓴다.

## 4. 코드가 잘 만드는 규칙형 스타일 6종
출처: @janustiu (Instagram carousel). 구조: **길이 · 매체 · 변형 순서(→ 마지막에 단어) · 질감 · 사운드**를 한 문장에. 끝에 `Color palette: #...` 한 줄로 색 지정.

| 스타일 | 팔레트 | 한 줄 (원문 인용) |
|---|---|---|
| ASCII Art | `#000000 #33FF66` | "Create an 8-second ASCII animation. A rotating torus morphs into a 3D head, glitches, then forms MOTION. Green monospace on black. CRT texture, minimal techno." |
| Pixel Art | `#0F380F #306230 #8BAC0F #9BBC0F` | "Create an 8-second Game Boy-style animation. A pixel ball bounces through a scrolling landscape, then reforms as MOTION. Four greens, dithering, chunky movement, 8-bit chiptune." |
| One-line Drawing | `#F4F1EA #DAD5CA #2F5BFF` | "Create an 8-second animation with one unbroken blue line. A graph becomes a hand, a play button, a soundwave, then handwritten motion. Graph paper, ink wobble, marimba." |
| Risograph Stop Motion | `#F3EFE6 #FF48B0 #00838A` | "Create a 9-second risograph cutout animation. Paper shapes build a computer, unfold into a film strip, then spell MOTION. Pink and teal ink, grain, misregistration, handmade jitter, toy piano." |
| Da Vinci Sketch | `#E9D9B5 #5A3A1E #A4452C` | "Create a 9-second inventor's notebook animation. Draw an original flying machine, animate its gears and wings, then let it fly off the page. Parchment, sepia cross-hatching, red chalk, quill sounds." |
| Ink Bloom | `#FAFAFA #1B1F6B #C2185B` | "Create a 9-second ink-in-water animation. Indigo and magenta clouds curl, bloom, gather into MOTION, then dissolve. Soft particle motion, white background." |

새 주제에 쓸 때는 변형 순서의 대상과 마지막 단어를 주제로 바꾼다.

## 5. 레퍼런스 분석
- 기본: "[링크] 앞 5분을 보고, 이 모션 스타일을 다른 내용에 적용하려면?" (사람 나오는 부분 제외)
- **추천: 구간을 정해 프레임 단위로 상세 분석 → 가이드 문서로.** 캡처가 촘촘할수록 분석과 결과가 좋아진다. 결과: 디자인 시스템(컬러·타이포·카드·아이콘·배경), 타임라인 맵, 프레임별 모션.
- 이 스킬에서는 `scripts/ref_measure.py measure` 로 숫자부터 뽑고, 그 위에 눈 관찰을 "(추정)"으로 얹는다.

## 6. 분석한 스타일로 설명 영상 + TTS
같은 대화에서 요청하면 Claude 가 음성 여부·진행 방식(스토리보드 먼저/바로 완성)·화면비를 묻는다. 스크립트에 `[화면: …]` 장면 지시를 섞으면 그 부분을 연출한다. 나레이션은 Gemini 무료 TTS(Google AI Studio 키) 등. 키는 노출되지 않게, 작업 뒤 삭제.

## 7. 카메라 워킹 피드백 (한 번으로 개선됨)
첫 결과의 공통 약점: 카메라가 거의 안 움직이고 장면을 잇는 요소가 없어 슬라이드 같음.
피드백 구성: "전환, 중요한 부분으로 줌인·줌아웃, **특정 요소가 연속성을 가지며 이어지는 연출**이 아쉽다" → 팬·줌·장면 연결이 들어감. 이 스킬은 이걸 처음부터 규칙으로 넣는다(motion-rules 2·3절).

## 8. 마음에 드는 스타일을 스킬로
대화 끝에 "지금까지 맥락을 모두 확인해서 새 콘텐츠로도 이런 스타일을 만들 수 있게 전역 스킬로 등록해줘" → Skill Creator. 이후 디테일이 거슬릴 때마다 스킬을 고쳐 발전시킨다. 스킬에는 **불변 요소만**(색·타이포·모션 문법·전환·관통 요소), 이야기·장면은 넣지 않는다.

## 9. 이미지 에셋 + 코드 4단계 (가장 정교한 패턴)
입력: 레퍼런스(링크/파일), 새 주제, 길이, 해상도, **가져올 것**(예: 끊기는 스톱모션 리듬, 종이 질감·그림자) / **가져오지 않을 것**(로고, 브랜드 문구).
공통 원칙: 판단은 코드로 잰 수치와 프레임 번호로, 눈 판단은 "추정". 레퍼런스를 끝까지 훑고 **마지막 2초 엔딩**을 따로 본다. 측정 코드는 저장해 검수에 다시 쓴다.

1단계 분석·플랜 (여기서 멈추고 승인):
- 레퍼런스 스펙 시트 — 장면별 시간표, 피사체 위치·크기, 카메라 방향·속도, 전환 방식(연속 프레임 차분 급증 지점), 실제 애니메이션 fps(차분 0 인 홀드 패턴), 보간(이징/계단/반동), 모션 블러, 등장·퇴장 프레임 수, 구간별 움직임 양(저해상도 차분 평균의 절대값), 레이어 깊이·질감·테두리·색(HEX·채도·명도·흰색 비율)·그레인(매 프레임 변하는지)·정지 중 미세 움직임·후처리, 사운드(BPM·강박·효과음), 이 영상다움 3~5개.
- 효과 사양표: 근거 → 구현 → 코드 파라미터 초기값.
- 장면 대응표: 레퍼런스 장면·시간 → 새 소재 → 구현.
- 에셋 목록: 용도, 배경 묶음/투명 분리, 기준 이미지, 필요한 각도·포즈, 모델 설정·프롬프트 초안, 같은 기준 이미지 참조로 통일, 모델·해상도별 생성 건수 합계.
- 장면별 구현 계획, 사운드 계획, 검수 기준(움직임 양 ±20%). 레퍼런스 캡처와 함께 보여 주고 **생성 시작 전 멈춤**.

2단계 제작(승인 후 최종까지): 승인된 모델로만 생성, 중복 렌더 줄이기, 파라미터는 코드 한곳에, 전환 전후 피사체의 위치·방향·속도를 이어 시선이 끊기지 않게, 장면 전체 확대가 아니라 요소별 역할에 맞는 움직임. 검수는 결함(형태·위치 튐·전환 끊김·빈 화면) + 닮음(같은 측정 코드로 대조, 절대값, ±20% 초과는 원인 적고 재렌더, 장면별 나란히 비교).
납품: MP4, 에셋, 생성 프롬프트(모델·설정), 합성 코드, 스펙 시트·효과 사양표(최종 값·코드 위치)·대조표, 남은 차이.

## 10. 실제 소요시간·비용 (영상 속 보고, 참고용)
| 작업 | 시간 | 비용 |
|---|---|---|
| 싱글 프롬프트 쇼릴 15초 (코드) | 약 20분 | — |
| 영상 모델 키네틱 타이포 (MiniMax H3 / Seedance 2.5) | 약 5분 | 330 / 1,650 크레딧, 둘 다 한글 뭉개짐 |
| 이미지+코드 페이퍼 콜라주 15초 (이미지 17장 계획) | 약 2시간 | 약 670 크레딧 |
| 이미지+코드 1분 | 3시간 이상 | — (가장자리가 일자로 잘린 문제) |
| 영상 모델로 비슷한 수준 | 20~30분 | — |
→ 오래 걸리는 작업은 렌더 전에 스토리보드를 확인한다. 병렬로 다른 일을 할 게 아니면 영상 모델이 효율적일 수 있다.
