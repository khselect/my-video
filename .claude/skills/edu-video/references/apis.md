# 필요한 API — 진행자 없는 애니메이션 강의 기준

진행자(아바타)가 없으므로 **꼭 필요한 유료 API는 TTS 하나**다. 나머지는 품질을 높이는 선택 사항이다.
대본 작성·장면 코딩은 클로드 코드가 직접 하므로 별도 LLM API는 필요 없다(자동화 서버로 돌릴 때만 Anthropic API).

## 필수: 음성 합성(TTS) — 하나만 고르면 됨

| 서비스 | 환경변수 | 한국어 품질 | 비고 |
|---|---|---|---|
| **Google Cloud TTS** (추천 시작점) | `GOOGLE_TTS_API_KEY` | 좋음 (Chirp3-HD, Neural2) | 월 무료 할당량 있음. Cloud 콘솔에서 Text-to-Speech API 활성화 → API 키 발급 |
| **ElevenLabs** | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | 가장 자연스러움 | 유료 플랜 권장. 내 목소리 복제 가능 |
| **OpenAI TTS** | `OPENAI_API_KEY` | 보통~좋음 | `gpt-4o-mini-tts`, 말투를 지시문으로 조절 |
| **Azure Speech** | `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | 좋음 (SunHi, InJoon) | 무료 티어 월 50만 자. 단어 경계 타임스탬프 제공 |
| **Qwen3-TTS 로컬 (내 목소리)** | 없음 (`QWEN_TTS_MODEL`) | 좋음, 보이스 클론 | 무료·오프라인. GPU 권장. `references/my-voice.md` |
| HeyGen (HyperFrames 내장) | `npx hyperframes auth login` | 좋음 | 로그인만으로 Voice Turbo·음악 카탈로그 사용 |

`scripts/tts.py --provider google|elevenlabs|openai|azure` 로 바꿔 끼운다. 키는 프로젝트의 `.env`에 넣는다(커밋 금지).

## 선택: 품질을 올리는 API

| 용도 | 서비스 | 환경변수 | 언제 |
|---|---|---|---|
| 단어별 자막 타이밍 | 로컬 whisper.cpp(무료) / OpenAI Whisper API | `OPENAI_API_KEY` | 단어가 말해지는 순간 강조할 때 |
| 배경음악 | Pixabay Music(무료), HeyGen 카탈로그, ElevenLabs Music | `PIXABAY_API_KEY` | 15초 넘는 영상은 음악을 깔 것을 권장 |
| 스톡 영상·사진 | Pexels, Pixabay (무료) | `PEXELS_API_KEY`, `PIXABAY_API_KEY` | 실사 장면이 필요할 때. OpenMontage `.env`와 같은 키 |
| 생성 이미지 | OpenAI gpt-image, Google Imagen, Higgsfield(MCP 연결됨) | 각 서비스 키 | 원문에 그림이 없고 그려야 할 때 |
| 클라우드 렌더 | HeyGen cloud / AWS Lambda / Cloud Run | 각 계정 | 긴 영상을 PC 없이 뽑을 때 |

## 키 없이 되는 것
- PDF·HTML 추출, 장면 제작, 렌더링(HyperFrames·Remotion 모두 로컬)
- `tts.py --provider none`: 무음 + 화면 텍스트 중심 강의(데모 영상이 이 방식)
