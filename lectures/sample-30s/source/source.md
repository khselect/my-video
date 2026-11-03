## [p.1]

[에이나우] 클로드로 영상 만드는 무료
오픈소스 3개 — 설치 가이드북
신영선의 AI탐구 293화 · 2026-10-03 기준 (별 개수·라이선스는 이날 GitHub에서 직접 확인)
한 줄 요약 — 영상을 편집 프로그램이 아니라 코드로 만들면, 클로드가 직접 고치고 다시
뽑아줍니다. 아래 3개가 그 도구입니다.

도구                   역할                  GitHub 별            사용 조건

Remotion             엔진 — 영상을            61,607              개인·3인 이하 회사
                     코드로 만든다                                 무료

HyperFrames          그래픽 — 촬영본           55,979              무료 (회사·상업
                     위에 자막·그래픽을                              이용도 가능)
                     얹는다

OpenMontage          확장 —                62,501              무료
                     스톡·음악·자막까지
                     한 번에

시작 전에 준비할 것 (셋 다 공통)
 ●​ 클로드 코드 (또는 Codex) — 클로드한테 시키는 창
 ●​ Node.js 22 이상 — nodejs.org에서 LTS 버전 설치 (HyperFrames가 22 이상을
    요구합니다)
 ●​ ffmpeg — 영상·소리 처리 도구 (Mac: brew install ffmpeg / Windows: ffmpeg.org)
 ●​ Python 3.10 이상 — OpenMontage에 필요 (python.org)

✔ 제일 쉬운 방법: 아래 설치 명령을 몰라도 됩니다. 클로드 코드에 「이 저장소 설치해줘:
(GitHub 주소)」라고 붙여 넣으면 클로드가 알아서 깝니다.

1. Remotion — 영상을 코드로 만드는 엔진
한 줄 요약: 영상의 글자·움직임·타이밍을 전부 코드로 적어 두는 도구입니다. 코드라서
클로드가 읽고, 고치고, 다시 렌더링할 수 있습니다.

이럴 때 쓰세요
 ●​ 대사 단어마다 화면이 딱딱 맞춰 움직이는 쇼츠를 만들 때
 ●​ 한 번 만든 디자인을 다른 주제에 그대로 다시 쓰고 싶을 때
 ●​ 「여기 글자 좀 크게」 같은 수정을 말로만 시키고 싶을 때

## [p.2]

설치
① 새 영상 프로젝트 만들기
npx create-video@latest
② Remotion 공식 스킬 12개 깔기 (클로드가 Remotion을 제대로 쓰게 하는 규칙 모음)
npx skills add remotion-dev/skills
③ 미리보기 화면 열기 (프로젝트 폴더 안에서)
npm run dev

바로 써보기 — 클로드 코드에 이렇게 말하세요
/remotion-create 내 릴스 대본으로 9:16 세로 쇼츠를 만들어줘. 검은 배경에 흰 글자, 대사가
나올 때마다 핵심 단어가 튀어나오게.

⚠️●​주의개인·3인 이하 회사는 무료, 4인 이상 회사는 유료 라이선스가 필요합니다
      (remotion.dev/license).
  ●​ 처음 렌더링할 때 브라우저 엔진을 내려받느라 몇 분 걸립니다. 정상입니다.
▶ GitHub: github.com/remotion-dev/remotion · 공식 스킬: github.com/remotion-dev/skills

2. HyperFrames — 촬영본 위에 자막·그래픽을 얹어
영상으로 뽑는 도구
한 줄 요약: 웹페이지를 만들 때 쓰는 HTML·CSS로 화면을 짜면, 그대로 MP4 영상으로 뽑아
주는 도구입니다. AI 아바타 회사 헤이젠(HeyGen)이 공개했고, 클로드가 쓰는 방법(스킬
21종)이 같이 들어 있습니다.

이럴 때 쓰세요
 ●​ 찍어 둔 영상 위에 자막·숫자 강조·그래픽을 얹고 싶을 때
 ●​ 10초 안팎의 도식이나 움직이는 글자 같은 짧은 모션 그래픽이 필요할 때
 ●​ 글만 주고 얼굴 없는 설명 영상을 만들고 싶을 때

설치
① 클로드 코드에 플러그인으로 깔기 (가장 쉬움)
claude plugin marketplace add heygen-com/hyperframes
claude plugin install hyperframes@hyperframes
② 또는 스킬만 깔기
npx skills add heygen-com/hyperframes
③ 잘 깔렸는지 점검하기 (선택)
npx hyperframes doctor

## [p.3]

바로 써보기 — 클로드 코드에 이렇게 말하세요
/hyperframes 로 10초짜리 세로 인트로를 만들어줘. 검은 배경에 흰 글자로, 제목이 한 줄씩
떠오르게.

⚠️●​주의Node.js 22 이상이 필요합니다. 명령 창에 node -v 를 쳐서 버전을 확인하세요.
  ●​ 플러그인으로 깔았으면 /hyperframes:hyperframes, 스킬로 깔았으면 /hyperframes 로
     부릅니다.
  ●​ Apache-2.0 라이선스 — 회사 영상·유료 강의·고객 작업에도 무료로 쓸 수 있습니다.

▶ GitHub: github.com/heygen-com/hyperframes · 설명서: hyperframes.heygen.com

3. OpenMontage — 스톡·음악·자막까지 한 번에 하는
영상 제작 공장
한 줄 요약: 제작 파이프라인 12종과 도구 100개 이상이 들어 있는 영상 제작 시스템입니다.
주제만 말하면 조사 → 대본 → 내레이션 → 배경음악 → 자막 → 렌더링 → 품질 검사까지
이어서 돌립니다.

이럴 때 쓰세요
 ●​ 쇼츠 말고 설명 영상·광고 영상 같은 다른 형식으로 넓히고 싶을 때
 ●​ 무료 스톡 영상과 저작권 걱정 없는 배경음악을 자동으로 찾아 붙이고 싶을 때
 ●​ 완성본을 내보내기 전에 자동으로 품질 검사(소리 크기·자막·프레임)를 받고 싶을 때

설치
① 내려받기
git clone https://github.com/calesthio/OpenMontage.git
cd OpenMontage
② 한 번에 설치
make setup
③ 클로드 코드로 이 폴더를 열고 만들고 싶은 영상을 말하기
뉴럴 네트워크가 배우는 원리를 60초 애니메이션 설명 영상으로 만들어줘

⚠️●​주의스톡 영상·음악 기능은 Pexels·Pixabay 무료 API 키를 .env 파일에 넣어야 켜집니다.
  ●​ Windows에서 make가 없으면 클로드에게 「make 없이 설치해줘」라고 하면 됩니다.
  ●​ AGPL 라이선스 — 그냥 쓰는 건 자유지만, 고쳐서 외부 서비스로 내놓으면 고친 소스를
      공개해야 합니다.
▶ GitHub: github.com/calesthio/OpenMontage

◆ 셋을 이으면

## [p.4]

Remotion으로 영상을 코드로 만들고, HyperFrames로 촬영본 위에 자막·그래픽을 얹고,
OpenMontage로 스톡 영상·배경음악까지 붙이면 — 편집 프로그램을 열지 않고 클로드에게
말로 시켜서 쇼츠를 뽑는 흐름이 완성됩니다.

▶ 더 많은 AI 활용법은 신영선의 AI탐구(@ai.yeongseon)에서 받아보세요.
