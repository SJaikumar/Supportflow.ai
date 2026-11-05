"""Stage 1.2 static layout regressions; browser appearance requires local verification."""
from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]


def test_queue_uses_unbordered_keyed_zebra_rows():
    src = (ROOT/'supportflow/views/agent.py').read_text(encoding='utf-8')
    ast.parse(src)
    assert "st.container(key=f'sf_queue_row_{index % 2}_{prefix}_{index}', border=False, gap=None)" in src
    assert "with st.container(border=True):" not in src.split('def _queue_rows(')[1].split('def dashboard(')[0]
    assert 'sf-queue-heading' in src
    css = (ROOT/'supportflow/ui.py').read_text(encoding='utf-8')
    for marker in ('st-key-sf_queue_row_0_', 'st-key-sf_queue_row_1_',
                   '.sf-queue-flags', '.sf-queue-heading', 'st-key-sf_queue_open_'):
        assert marker in css


def test_sidebar_tooltips_only_in_compact_mode():
    app = (ROOT/'app.py').read_text(encoding='utf-8')
    ast.parse(app)
    assert 'help=page.title if compact else None' in app
    css = (ROOT/'supportflow/ui.py').read_text(encoding='utf-8')
    assert 'text-overflow:ellipsis' in css
