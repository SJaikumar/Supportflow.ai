"""Static UI-contract checks that run even when Streamlit is not installed.

These checks cover the Stage 1.1 refactor's configuration and navigation
wiring; actual browser rendering still needs a local Streamlit installation.
"""
from pathlib import Path
import ast
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_deploy_toolbar_disabled_for_local_demo():
    config = tomllib.loads((ROOT/'.streamlit/config.toml').read_text())
    assert config['client']['toolbarMode'] == 'viewer'


def test_custom_navigation_uses_supported_streamlit_apis():
    source = (ROOT/'app.py').read_text()
    ast.parse(source)
    assert "position='hidden'" in source
    assert 'st.page_link(' in source
    assert 'compact_sidebar' in source
    assert 'sf_sidebar_collapse' in source
    assert 'sf_sidebar_expand' in source


def test_refined_design_has_colored_actions_and_responsive_rules():
    source = (ROOT/'supportflow/ui.py').read_text()
    ast.parse(source)
    for token in ('quick_track_delivery','quick_return_refund',
                  'quick_report_damage','quick_other_support',
                  'Plus Jakarta Sans','@media(max-width:800px)'):
        assert token in source
