"""Headless UI test of demo/app.py with Streamlit's AppTest (needs JAVA_HOME etc., see scripts/local_env.sh)."""
import os
import sys

from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
at = AppTest.from_file(os.path.join(ROOT, "demo", "app.py"), default_timeout=600)
at.run()
assert not at.exception, at.exception
fmts = sys.argv[1:] or ["delta", "iceberg"]
at.sidebar.multiselect[0].set_value(fmts).run()
at.sidebar.button[0].click().run()                       # start
assert not at.exception, at.exception


def button(prefix):
    labels = [b.label for b in at.button]
    found = [b for b in at.button if b.label.startswith(prefix)]
    assert found, f"no button {prefix!r} in {labels}; errors={[e.value for e in at.error]}"
    return found[0]


for _ in range(4):
    button("Ghi batch").click().run()
    assert not at.exception, at.exception
button("Xóa trạm").click().run()
assert not at.exception, at.exception
print([m.value for m in at.success] or [m.value for m in at.warning])
button("Compaction").click().run()
assert not at.exception, at.exception
print(at.dataframe[0].value)
print("selectboxes:", [(s.label, s.value) for s in at.selectbox], "slider:", [s.value for s in at.select_slider])
station = next(s for s in at.selectbox if s.label == "Trạm")
station.set_value("st0").run()                            # deleted station -> time travel shows it
at.select_slider[0].set_value(2).run()                    # a version from before the delete
assert not at.exception, at.exception
print("infos:", [m.value[:90] for m in at.info])
assert not at.exception, at.exception
print("warnings:", [m.value[:80] for m in at.warning])
print("captions:", [c.value[:120] for c in at.caption][-1:])
at.sidebar.button[1].click().run()                       # stop Spark
print("OK")
