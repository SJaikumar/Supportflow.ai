"""Regression guards for Stage 4.4 login/privacy and row/text UI fixes.

These tests validate source structure; visually verify Streamlit in a browser.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def source(rel):
    s = (ROOT / rel).read_text(encoding="utf-8")
    ast.parse(s)
    return s

def test_no_demo_credential_listing_or_prefilled_login():
    app = source('app.py')
    assert "with st.expander('Demo accounts and password'" not in app
    assert "value='priya@demo.com'" not in app
    assert "All accounts use **Demo123!**" not in app
    assert "st.text_input('Email', placeholder=" in app
    assert "from supportflow.seed import DEMO_ACCOUNTS" not in app

def test_single_block_two_line_layout_used_for_rows():
    ui = source('supportflow/ui.py')
    assert 'def list_item_text(' in ui
    assert '.sf-row-label{{display:flex;flex-direction:column;' in ui
    assert 'gap:5px;min-height:43px' in ui
    customer = source('supportflow/views/customer.py')
    staff = source('supportflow/views/agent.py')
    for page in (customer, staff):
        assert 'list_item_text(' in page
    assert "list_item_text('📦 ' + item.product_name," in customer
    assert 'body=n.body' in customer
    assert 'list_item_text(a.title, a.details,' in staff

def test_ai_draft_notice_is_inline_not_cropped_toast():
    staff = source('supportflow/views/agent.py')
    assert "st.toast('Draft loaded." not in staff
    assert "st.session_state['ai_draft_notice_ticket'] = ticket.id" in staff
    assert "st.success('AI draft added to your reply composer." in staff
