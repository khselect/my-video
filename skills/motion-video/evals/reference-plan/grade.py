import json, re, sys
from pathlib import Path
d = Path(sys.argv[1]); res = json.loads(Path(sys.argv[2]).read_text()) if Path(sys.argv[2]).exists() else {}
final = res.get("result", "") if isinstance(res, dict) else ""
docs = [p for p in d.rglob("*.md")]
text = "\n".join(p.read_text(errors="ignore") for p in docs) + "\n" + final
measured = list(d.rglob("spec.json"))
cams = ["push", "pull", "pan", "tilt", "zoom", "parallax", "focus", "밀어", "당겨", "패닝", "틸트", "줌", "시차", "초점", "돌리", "dolly", "truck"]
cam_kinds = {c for c in cams if c.lower() in text.lower()}
made = [p for p in d.rglob("*") if p.suffix.lower() in (".mp4", ".html", ".webm") and p.name != "ref.mp4"]
checks = [
 ("레퍼런스를 숫자로 측정했다 (spec.json 등 측정 결과 파일)", bool(measured), [str(p) for p in measured][:2]),
 ("효과 사양표: 근거와 파라미터 열이 있는 표", bool(re.search(r"\|[^\n]*근거[^\n]*\|[^\n]*(파라미터|초기값)", text)), ""),
 ("측정값 인용: 실효 12fps", bool(re.search(r"12\s*fps|ANIM_FPS\s*=\s*12|실효\s*12", text, re.I)), ""),
 ("측정값 인용: 분당 전환 15 또는 샷 약 3초", bool(re.search(r"분당[^\n]{0,12}15|15\.0|샷[^\n]{0,20}3(\.0)?\s*초|3\.02", text)), ""),
 ("관통 요소가 계획에 있다", "관통" in text or "through-line" in text.lower() or "연결 요소" in text, ""),
 ("카메라 움직임 4종 이상 언급", len(cam_kinds) >= 4, sorted(cam_kinds)),
 ("합격 조건에 ±20% 수치 기준", bool(re.search(r"±\s*20\s*%|20%\s*이내|허용[^\n]{0,20}20", text)), ""),
 ("승인 전에 멈춤: 영상·HTML 파일을 만들지 않음", not made, [str(p) for p in made][:3]),
]
out = [{"text": t, "passed": bool(ok), "evidence": str(ev)} for t, ok, ev in checks]
print(json.dumps({"files": [str(p.relative_to(d)) for p in d.rglob('*') if p.is_file()][:30], "expectations": out}, ensure_ascii=False, indent=1))
