"""Stage 4.3 row-density/layout regressions (static checks; browser check remains necessary)."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_consistent_section_heading_padding_and_zebra_styling():
    source = (ROOT / 'supportflow/ui.py').read_text(encoding='utf-8')
    ast.parse(source)
    for fragment in (
        'padding:0 0 12px',
        'st-key-sf_zebra_row_0_',
        'st-key-sf_zebra_row_1_',
        'border:0 !important;border-radius:0 !important',
        '.sf-snapshot',
        'padding-bottom:14px',  # previous sidebar-section spacing fix retained
    ):
        assert fragment in source


def test_customer_and_agent_lists_use_unbordered_keyed_rows():
    customer = (ROOT / 'supportflow/views/customer.py').read_text(encoding='utf-8')
    agent = (ROOT / 'supportflow/views/agent.py').read_text(encoding='utf-8')
    ast.parse(customer)
    ast.parse(agent)
    for fragment in (
        'sf_zebra_list_customer_home',
        'sf_zebra_list_orders',
        'sf_zebra_list_tickets',
        'sf_zebra_list_inbox',
        'sf_zebra_row_{index % 2}',
    ):
        assert fragment in customer
    for fragment in (
        'sf_zebra_list_dashboard_approvals',
        'sf_zebra_list_customer_history',
        'sf_zebra_list_alerts_',
        'sf-snapshot-meta',
    ):
        assert fragment in agent
