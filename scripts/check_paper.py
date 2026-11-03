"""Static checks for paper/main.tex: citations, cross-references, figures, environments, approximate length."""
import os
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "paper", "main.tex")
s = open(path, encoding="utf-8").read()
cites = {c.strip() for g in re.findall(r"\\cite\{([^}]*)\}", s) for c in g.split(",")}
bibs = set(re.findall(r"\\bibitem\{([^}]*)\}", s))
labels = set(re.findall(r"\\label\{([^}]*)\}", s))
refs = set(re.findall(r"\\ref\{([^}]*)\}", s))
figs = re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]*)\}", s)
fig_dir = os.path.join(os.path.dirname(path), "figures")
envs = set(re.findall(r"\\begin\{(\w+\*?)\}", s))
unbalanced = {e: (s.count("\\begin{%s}" % e), s.count("\\end{%s}" % e)) for e in envs
              if s.count("\\begin{%s}" % e) != s.count("\\end{%s}" % e)}
body = s[s.index("\\begin{abstract}"):s.index("\\begin{thebibliography}")]
words = len(re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[a-zA-Z]+", " ", body)))

print("cited but no bibitem:", sorted(cites - bibs))
print("bibitem never cited:", sorted(bibs - cites))
print("\\ref without \\label:", sorted(refs - labels))
print("missing figure files:", [f for f in figs if not os.path.exists(os.path.join(fig_dir, f))])
print("unbalanced environments:", unbalanced)
print("placeholders \\res{}:", len(re.findall(r"\\res\{", s)) - 1)
print(f"approx. words in body: {words}  (IEEE two-column ~ 800-900 words/page of text)")
print(f"figures: {len(figs)}, tables: {s.count(chr(92) + 'begin{table')}")
