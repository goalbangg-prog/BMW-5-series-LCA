"""results.json에서 웹에 필요한 부분만 골라 템플릿에 넣어 index.html을 만든다."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
r = json.loads((ROOT / "outputs" / "results.json").read_text(encoding="utf-8"))
mc = r["monte_carlo"]
data = {
    "factors": r["factors"],
    "meta": r["meta"],
    "vehicles": r["vehicles"],
    "sensitivity": r["sensitivity"],
    "monte_carlo": {"n": mc["n"], "prob": mc["prob"], "hist_edges": mc["hist_edges"], "hist": mc["hist"],
                     "pct": {k: {str(q): v for q, v in d.items()} for k, d in mc["pct"].items()}, "avoided_pct": mc["avoided_pct"]},
    "validation": r["validation"],
    "reference_flows": r["reference_flows"],
    "datasets": r["datasets"],
    "scope3": r["scope3"],
    "avoided": r["avoided"],
    "recycling": r["recycling_example"],
    "grid_bottom_up": r["grid_bottom_up"],
    "breakeven": r["breakeven"],
}


def clean(o):
    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


tpl = (ROOT / "web" / "index.template.html").read_text(encoding="utf-8")
html = tpl.replace("/*__DATA__*/", json.dumps(clean(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False))
# 단독 HTML 문서로 감싸기 (GitHub Pages용): <header> 앞은 head, 나머지는 body
cut = html.index('<header class="top')
html = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + html[:cut] + '</head>\n<body>\n' + html[cut:] + '\n</body>\n</html>\n')
(ROOT / "index.html").write_text(html, encoding="utf-8")
print("index.html", len(html.encode()), "bytes")
