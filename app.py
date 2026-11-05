"""SupportFlow AI — Stage 4: SLA operations, image support, AutoGen and hybrid RAG.

Launch: python -m streamlit run app.py
The navigation rail is implemented with Streamlit's supported st.navigation
(position='hidden') and st.page_link APIs so it keeps working when collapsed.
"""
from __future__ import annotations
import streamlit as st

from supportflow.seed import seed_if_empty, seed_stage2_examples_if_missing
from supportflow import services as svc
from supportflow.ui import apply_styles, brand
from supportflow.views import customer, agent
from supportflow.config import ROLE_NAMES
from supportflow.utils import safe

st.set_page_config(
    page_title='SupportFlow AI · Customer support', page_icon='🎧',
    layout='wide', initial_sidebar_state='expanded',
)
seed_if_empty()
seed_stage2_examples_if_missing()
st.session_state.setdefault('dark_mode', False)
st.session_state.setdefault('compact_sidebar', False)
apply_styles()


def login():
    left, right = st.columns([1, 1], gap='large')
    with left:
        brand()
        st.markdown(
            '<div class="sf-login-blurb"><strong>Support that moves<br>things forward.</strong>'
            '<p>One place for customer requests, real order context, and human-approved '
            'resolutions. Important promises stay visible.</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="sf-note">✓ Customer-first experience &nbsp;&nbsp; '
            '✓ Case history and tracking<br>✓ Human approval &nbsp;&nbsp; '
            '✓ Role-based workspaces</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<div class="sf-eyebrow">WELCOME BACK</div>', unsafe_allow_html=True)
        st.markdown('### Sign in to your workspace')
        st.caption('Sign in to access your support workspace.')
        with st.form('login_form'):
            email = st.text_input('Email', placeholder='name@example.com')
            password = st.text_input('Password', type='password', placeholder='Enter your password')
            submitted = st.form_submit_button('Sign in', type='primary', use_container_width=True)
        if submitted:
            person = svc.authenticate(email, password)
            if person:
                st.session_state.user_id = person.id
                st.rerun()
            else:
                st.error('Incorrect email or password.')
    with st.sidebar:
        brand()
        st.toggle('Dark mode', key='dark_mode')
        st.caption('AI-powered support · Human oversight')


def build_nav(user):
    """The route registry is role scoped. Services also enforce permissions."""
    if user.role == 'customer':
        pages = {
            'Dashboard': st.Page(customer.home, title='Home', icon=':material/home:', url_path='home', default=True),
            'My orders': st.Page(customer.orders, title='My orders', icon=':material/package_2:', url_path='orders'),
            'My tickets': st.Page(customer.tickets, title='My tickets', icon=':material/confirmation_number:', url_path='tickets'),
            'New request': st.Page(customer.new_request, title='Create request', icon=':material/add_circle:', url_path='new'),
            'Inbox': st.Page(customer.inbox, title='Messages', icon=':material/notifications:', url_path='messages'),
            'Ticket conversation': st.Page(customer.ticket_conversation, title='Ticket conversation', icon=':material/forum:', url_path='conversation', visibility='hidden'),
        }
        visible = ['Dashboard', 'My orders', 'My tickets', 'New request', 'Inbox']
    else:
        pages = {
            'Dashboard': st.Page(agent.dashboard, title='Dashboard', icon=':material/dashboard:', url_path='dashboard', default=True),
            'All tickets': st.Page(agent.all_tickets, title='Tickets', icon=':material/confirmation_number:', url_path='tickets'),
            'Escalations': st.Page(agent.escalations, title='Escalations', icon=':material/priority_high:', url_path='escalations'),
            'Approvals': st.Page(agent.approvals, title='Approvals', icon=':material/approval:', url_path='approvals'),
            'Customer 360°': st.Page(agent.customer_360, title='Customer 360°', icon=':material/groups:', url_path='customers'),
            'SLA monitor': st.Page(agent.sla_monitor, title='SLA monitor', icon=':material/schedule:', url_path='sla'),
            'Analytics': st.Page(agent.analytics, title='Analytics', icon=':material/monitoring:', url_path='analytics'),
            'Knowledge base': st.Page(agent.knowledge_base, title='Knowledge base', icon=':material/menu_book:', url_path='knowledge'),
            'Ticket conversation': st.Page(agent.ticket_conversation, title='Ticket detail', icon=':material/forum:', url_path='ticket-detail', visibility='hidden'),
        }
        visible = ['Dashboard', 'All tickets', 'Escalations', 'Approvals', 'Customer 360°', 'SLA monitor', 'Analytics', 'Knowledge base']
    st.session_state.page_lookup = pages
    return st.navigation(list(pages.values()), position='hidden'), pages, visible


def render_sidebar(person, pages, visible):
    compact = bool(st.session_state.compact_sidebar)
    with st.sidebar:
        if compact:
            brand(compact=True)
            if st.button('Expand menu', icon=':material/keyboard_double_arrow_right:',
                         help='Expand menu', use_container_width=True, key='sf_sidebar_expand'):
                st.session_state.compact_sidebar = False
                st.rerun()
        else:
            logo_col, toggle_col = st.columns([4, 1], gap='small', vertical_alignment='center')
            with logo_col:
                brand()
            with toggle_col:
                if st.button('Collapse menu', icon=':material/keyboard_double_arrow_left:',
                             help='Collapse menu to icons', use_container_width=True,
                             key='sf_sidebar_collapse'):
                    st.session_state.compact_sidebar = True
                    st.rerun()
            st.markdown(
                '<div class="sf-sidebar-section">'
                + ('Customer portal' if person.role == 'customer' else 'Support workspace')
                + '</div>', unsafe_allow_html=True,
            )

        # st.page_link keeps the current-page highlight and accessible link labels.
        # In compact mode the text is visually hidden but remains available to
        # assistive technologies; the icon and hover tooltip remain visible.
        for name in visible:
            page = pages[name]
            st.page_link(page, label=page.title, icon=page.icon, help=page.title if compact else None,
                         use_container_width=True)

        st.divider()
        initials = ''.join(part[:1] for part in person.name.split()[:2]).upper()
        if compact:
            st.markdown(
                f'<div class="sf-sidebar-avatar" title="{safe(person.name)}">'
                f'{safe(initials)}</div>', unsafe_allow_html=True,
            )
            if st.button('Toggle theme', icon=':material/contrast:',
                         help='Toggle light/dark theme', use_container_width=True,
                         key='sf_compact_theme'):
                st.session_state.dark_mode = not bool(st.session_state.dark_mode)
                st.rerun()
        else:
            st.markdown(
                '<div class="sf-sidebar-profile">'
                f'<div class="sf-sidebar-name">{safe(person.name)}</div>'
                f'<div class="sf-sidebar-sub">{safe(ROLE_NAMES.get(person.role, person.role))}</div>'
                f'<div class="sf-sidebar-email">{safe(person.email)}</div>'
                '</div>', unsafe_allow_html=True,
            )
            if person.role == 'customer':
                count = svc.unread_count(person)
                if count:
                    st.caption(f'🔔 {count} unread notification' + ('s' if count != 1 else ''))
            st.toggle('Dark mode', key='dark_mode')
        if st.button('Log out', icon=':material/logout:', help='Sign out',
                     use_container_width=True, key='sf_logout'):
            for key in ('user_id', 'current_user', 'selected_ticket_id', 'selected_customer_id',
                        'selected_approval_id', 'page_lookup'):
                st.session_state.pop(key, None)
            st.rerun()
        if not compact:
            st.caption('SUPPORTFLOW AI')


if 'user_id' not in st.session_state:
    login()
    st.stop()

person = svc.get_user(st.session_state.user_id)
if not person:
    st.session_state.pop('user_id', None)
    st.rerun()
st.session_state.current_user = person
page, pages, visible = build_nav(person)
render_sidebar(person, pages, visible)
page.run()
