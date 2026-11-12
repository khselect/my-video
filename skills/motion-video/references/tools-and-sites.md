# 도구·사이트·측정 지표

## 렌더 엔진
| 도구 | 쓰는 때 | 설치 |
|---|---|---|
| HyperFrames (HTML + GSAP → MP4) | 기본. 장면 = HTML 파일, 레이어별 수정 | `npx skills add heygen-com/hyperframes` 또는 `npx hyperframes init` |
| Remotion (React → MP4) | React 프로젝트, 컴포넌트 재사용 | `npx skills add remotion-dev/skills` · 4인 이상 회사는 유료 라이선스 |
| lemo-opuscar (github.com/lemomo-ai/lemo-opuscar) | 영화형 단편, 스타일 66개, 코드만으로 (Canvas/WebGL 프레임 렌더). 연출 가이드(DIRECTOR.md)가 훌륭함 | `claude plugin marketplace add lemomo-ai/lemo-opuscar` → `claude plugin install lemo-opuscar@lemolab` · ffmpeg 7+ |

## 에셋·음성·음악
| 용도 | 선택지 | 메모 |
|---|---|---|
| 이미지 에셋 | GPT Image 계열, Nano Banana (Higgsfield·Newtake 등 MCP), 로컬 FLUX.1-schnell(무료) | 참조 이미지로 인물·질감 통일. 이미지 안에 글자 넣지 않기 |
| 영상 클립 | Seedance, MiniMax, Kling (MCP) | 한글 글자는 뭉개짐 — 글자는 코드로 위에 얹는다 |
| 나레이션 | Gemini TTS(무료 할당량), Qwen3-TTS(로컬), ElevenLabs·Fish Audio(유료, 내 목소리) | 숫자는 TTS 문장에선 한글로 풀어 쓰고 자막엔 숫자로 |
| 배경 음악 | Pixabay Music(무료, 라이선스 확인), ElevenLabs Music | `beats.py analyze` 로 박 분석 |
| 다시 듣기(STT) | faster-whisper, whisper.cpp(`npx hyperframes transcribe`) | 첫 실행에 모델 다운로드(small ≈ 460MB) |

## 레퍼런스·프롬프트
| 사이트 | 용도 |
|---|---|
| prompt-motion.com | Claude 로 만든 모션그래픽과 상세 프롬프트 모음 (카드 → 프롬프트 전문) |
| Pinterest | 스타일 레퍼런스 검색 (페이퍼 콜라주 등) |
| YouTube (예: Matics Media) | 모션 레퍼런스 영상 — 파일로 받아 `ref_measure.py` 로 측정 |
| X @charliejhills 게시물 | 모션그래픽 용어(이징·효과) 정리 |
| Google AI Studio (aistudio.google.com) | Gemini TTS API 키 |

## 측정 지표 — 뜻과 임계값 (`scripts/`)
| 지표 | 도구 | 계산 | 기준 |
|---|---|---|---|
| 빈 화면 | qa_render | 192×108 회색, 경계 에너지 < 0.6 이고 분산 < 12. 후보는 480×270 에서 다시 보고 배경과 50 넘게 다른 픽셀이 12개 이상이면 '작은 요소만'(관통 요소 등, 빈 화면 아님) | 0.3초↑ 확인, 1초↑ 문제, 0초 프레임 비면 확인 |
| 멈춤 | qa_render | 연속 프레임 평균 차이 < 0.15 | 4초↑ 확인 |
| 음량 | qa_render | loudnorm 측정 | −14±1 LUFS, 피크 ≤ −1 dBTP. `--normalize` 는 증폭 + 4배 샘플레이트 리미터 |
| 읽기 시간 | qa_render (`--lecture`) | 장면 화면 글자 수 vs 장면 길이 | 글자 수÷5+1.5초 (한국어 시작값) |
| 전환 | ref_measure | RGB 프레임 차이 급증(≥6, 주변 중앙값 4배) / 0.25초 누적 차이(2.2배·+4) | 컷·점진(추정)·검은 페이드·플래시 |
| 실효 fps | ref_measure | 움직이는 동안 그림이 유지되는 프레임 수(노이즈 바닥 위 변화만) | 24fps 2s 홀드 = 12fps |
| 움직임 양 | ref_measure | 96×54 초당 평균 프레임 차이, **절대값** | 대조 ±20% |
| 그레인 | ref_measure | 480×270 에서 매 프레임 2단계 넘게 바뀌는 픽셀 비율 | 0.1 초과 = 살아 있는 그레인 |
| 팔레트 | ref_measure | 1fps·64×36 k-means 8색 | 대조: RGB 거리 40 이하 |
| 박 | beats | 스펙트럼 플럭스 + 저음, 템포 후보 T·2T·T÷2 중 박/반박 대비 최대, DP 추적 | 전환의 80% 가 ±max(1프레임, 50ms) |
| 나레이션 오독 | stt_check | 1 − 글자 오류율(공백·문장부호 제거, 숫자 한자어 읽기), 핵심어(화면 글자·숫자·영문·반복 어간) | 일치 ≥92%, 확인 ≥80%, 핵심어 오독은 확인 |

`stt_check.py` 는 `<project>/scenes.json`(장면 `narration`) + `build/audio/manifest.json`(장면 `file`·`hash`) 구조를 읽는다 (my-video 의 narrate.py 출력). 다른 구조면 장면 음성과 대본을 그 형식으로 맞춘다.
