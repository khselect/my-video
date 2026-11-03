# my-video — 문서 → 애니메이션 강의 영상

진행자 없는 교육 영상을 만드는 작업 공간입니다. **전체 절차는 [WORKFLOW.md](WORKFLOW.md)** 를 보세요.

| 하고 싶은 것 | 명령 |
|---|---|
| 승인 단계를 따라가며 만들기 (권장) | `python studio/app.py` → http://127.0.0.1:8765 |
| 새 강의 만들기 | `python tools/new_lecture.py <이름> --title "제목"` |
| 나레이션 만들기 | `python tools/narrate.py lectures/<이름>/scenes.json --out lectures/<이름>/build/audio` |
| 버전 붙여 렌더 | `python tools/render_version.py render lectures/<이름> --note "메모"` |
| 다른 기기에서 받은 뒤 | `npm install` + `python tools/new_lecture.py <이름> --restore-assets` |

같은 폴더 레벨의 `../OpenMontage`, `../qwen-tts-env` 는 이 저장소에 포함하지 않습니다 (WORKFLOW.md 2장).

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
