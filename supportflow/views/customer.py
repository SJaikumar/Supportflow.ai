"""Customer-facing screens: accessible, simple and persistent."""
from __future__ import annotations
from datetime import datetime
import streamlit as st
from supportflow import services as svc
from supportflow.ui import badge,card,chat_bubble,go,goto_ticket,header,kpi,page_note,status_tone,list_item_text
from supportflow.utils import display_time,label_status,money,safe


def actor():
    return st.session_state.current_user


def home():
    """Customer home: fewer competing sections, denser content, clear next step."""
    u = actor()
    orders = svc.orders_for_customer(u)
    tickets = svc.visible_tickets(u)
    open_records = [r for r in tickets if r['ticket'].status not in {'RESOLVED', 'CLOSED'}]
    sorted_tickets = sorted(tickets, key=lambda r: r['ticket'].updated_at, reverse=True)

    header(f'Hello, {u.name.split()[0]} 👋',
           'Here is what is happening with your orders and support requests.',
           'CUSTOMER PORTAL')

    with st.container(key="sf_home_hero"):
        a, b = st.columns([4.5, 1.55], gap='medium', vertical_alignment='center')
        with a:
            st.markdown(
                '<div class="sf-hero-title">Need help with an order? We are here for you.</div>'
                '<div class="sf-muted">Report a delivery, product or payment issue in a few steps.</div>',
                unsafe_allow_html=True,
            )
        with b:
            if st.button('New request', icon=':material/add_circle:',
                         key='customer_new_request', type='primary', use_container_width=True):
                go('New request')

    stats = st.columns(4, gap='small')
    labels = ['My orders', 'Open tickets', 'Under review', 'Resolved']
    values = [len(orders), len(open_records),
              sum(r['ticket'].status in {'IN_REVIEW', 'AWAITING_APPROVAL'} for r in tickets),
              sum(r['ticket'].status == 'RESOLVED' for r in tickets)]
    subtitles = ['Purchases', 'Needs a response', 'Support is investigating', 'Completed requests']
    symbols = ['▣', '◫', '◷', '✓']
    for col, title, val, foot, symbol in zip(stats, labels, values, subtitles, symbols):
        with col:
            kpi(title, str(val), foot, symbol)

    left, right = st.columns([1.48, 1], gap='medium')
    with left:
        st.markdown('<div class="sf-dividerlabel">What do you need help with?</div>',
                    unsafe_allow_html=True)
        action_rows = [
            [(':material/local_shipping:', 'Track delivery', 'Delivery', 'quick_track_delivery'),
             (':material/currency_exchange:', 'Return or refund', 'Refund', 'quick_return_refund')],
            [(':material/package_2:', 'Report damage', 'Product quality', 'quick_report_damage'),
             (':material/support_agent:', 'Other support', 'Other', 'quick_other_support')],
        ]
        for row in action_rows:
            cols = st.columns(2, gap='small')
            for col, (icon, label, category, key) in zip(cols, row):
                with col:
                    if st.button(label, icon=icon, key=key, use_container_width=True):
                        st.session_state.request_category = category
                        go('New request')

        st.markdown('<div class="sf-dividerlabel">Recent support requests</div>',
                    unsafe_allow_html=True)
        if not tickets:
            page_note('No requests yet. Select one of the actions above to get started.')
        with st.container(key='sf_zebra_list_customer_home', gap=None):
            for index, rec in enumerate(sorted_tickets[:4]):
                t = rec['ticket']
                with st.container(key=f'sf_zebra_row_{index % 2}_customer_home_{t.id}', border=False, gap=None):
                    info, action = st.columns([4.3, 1], gap='small', vertical_alignment='center')
                    with info:
                        st.markdown(
                            list_item_text(t.title, f'{t.id} · {display_time(t.updated_at)}',
                                           badge(label_status(t.status), status_tone(t.status))),
                            unsafe_allow_html=True,
                        )
                    with action:
                        if st.button('View', key='customer_home_'+t.id,
                                     icon=':material/arrow_forward:', use_container_width=True):
                            goto_ticket(t.id)

    with right:
        st.markdown('<div class="sf-dividerlabel">Latest support update</div>',
                    unsafe_allow_html=True)
        if sorted_tickets:
            t = next((r['ticket'] for r in sorted_tickets
                      if r['ticket'].status not in {'RESOLVED', 'CLOSED'}),
                     sorted_tickets[0]['ticket'])
            is_complete = t.status in {'RESOLVED', 'CLOSED'}
            is_approval = t.status in {'AWAITING_APPROVAL', 'ACTION_PENDING'}
            stage = 3 if is_complete else (2 if is_approval else 1)
            steps = [('1', 'Received'), ('2', 'In review'),
                     ('3', 'Decision'), ('✓', 'Completed')]
            progress = ''.join(
                '<div class="sf-step ' + ('done' if i < stage else 'current' if i == stage else '') + '">'
                '<div class="sf-step-circle">' + marker + '</div>' + label + '</div>'
                for i, (marker, label) in enumerate(steps)
            )
            st.markdown(
                '<div class="sf-card">'
                f'<div class="sf-small">{safe(t.id)}</div>'
                f'<div class="sf-card-title">{safe(t.title)} &nbsp;'
                + badge(label_status(t.status), status_tone(t.status)) + '</div>'
                '<div class="sf-muted">Follow the status of your request without contacting support again.</div>'
                '<div class="sf-progress">' + progress + '</div>'
                '</div>', unsafe_allow_html=True,
            )
            if st.button('View ticket updates', key='home_latest_ticket',
                         icon=':material/arrow_forward:', use_container_width=True):
                goto_ticket(t.id)
        else:
            page_note('Your latest support update will appear here.')

        if orders:
            o = orders[0]['order']; item = orders[0]['item']
            st.markdown('<div class="sf-dividerlabel">Your latest order</div>',
                        unsafe_allow_html=True)
            st.markdown(
                '<div class="sf-card">'
                f'<div class="sf-small">{safe(o.id)}</div>'
                f'<div class="sf-card-title">{safe(item.product_name)}</div>'
                f'<div class="sf-muted">{money(o.total_cents)} &nbsp;'
                + badge(label_status(o.status), status_tone(o.status)) + '</div>'
                f'<div class="sf-small" style="margin-top:8px">Promised delivery: '
                f'{safe(display_time(o.promised_at))}</div></div>',
                unsafe_allow_html=True,
            )
            if st.button('View my orders', key='home_orders',
                         icon=':material/arrow_forward:', use_container_width=True):
                go('My orders')


def orders():
    header('My orders','Select an order to get help quickly.','CUSTOMER PORTAL')
    rows=svc.orders_for_customer(actor())
    if not rows:page_note('No orders found.');return
    with st.container(key='sf_zebra_list_orders', gap=None):
        for index, rec in enumerate(rows):
            o=rec['order'];item=rec['item']
            with st.container(key=f'sf_zebra_row_{index % 2}_orders_{o.id}', border=False, gap=None):
                cols=st.columns([3.1,1.5,1.2],vertical_alignment='center')
                with cols[0]:
                    st.markdown(list_item_text('📦 ' + item.product_name,
                               f'{o.id} · Purchased {display_time(o.placed_at)}'),
                               unsafe_allow_html=True)
                with cols[1]:
                    st.markdown('<div class="sf-row-label"><div class="sf-row-primary">'
                                + badge(label_status(o.status),status_tone(o.status))
                                + '</div><div class="sf-row-secondary">'
                                + safe(money(o.total_cents)) + '</div></div>',
                                unsafe_allow_html=True)
                with cols[2]:
                    if st.button('Get help',key='order_help_'+o.id,use_container_width=True):
                        st.session_state.request_order_id=o.id
                        go('New request')


def tickets():
    header('My support requests','Track your updates or continue a conversation.','CUSTOMER PORTAL')
    records=svc.visible_tickets(actor())
    status_filter=st.segmented_control('Filter tickets',['All','Open','Resolved'],default='All',label_visibility='collapsed')
    if status_filter=='Open':records=[r for r in records if r['ticket'].status not in ('RESOLVED','CLOSED')]
    if status_filter=='Resolved':records=[r for r in records if r['ticket'].status in ('RESOLVED','CLOSED')]
    if not records:page_note('No tickets in this category.');return
    with st.container(key='sf_zebra_list_tickets', gap=None):
        for index, rec in enumerate(records):
            t=rec['ticket']
            with st.container(key=f'sf_zebra_row_{index % 2}_tickets_{t.id}', border=False, gap=None):
                a,b,c=st.columns([3,1.6,1],vertical_alignment='center')
                with a:
                    st.markdown(list_item_text(t.title,
                              f'{t.id} · {t.category} · {t.order_id or "No order"}'),
                              unsafe_allow_html=True)
                with b:
                    st.markdown('<div class="sf-row-label"><div class="sf-row-primary">'
                                + badge(label_status(t.status),status_tone(t.status))
                                + '</div><div class="sf-row-secondary">'
                                + safe(rec['sla']['remaining']) + '</div></div>',
                                unsafe_allow_html=True)
                with c:
                    if st.button('Open →',key='cust_ticket_'+t.id,use_container_width=True):goto_ticket(t.id)


def new_request():
    header('How can we help?','Describe the issue in your own words. You can add photos if something arrived damaged.','NEW SUPPORT REQUEST')
    orders=svc.orders_for_customer(actor())
    opt={'General question (no order)':None}
    for r in orders:
        order=r['order'];item=r['item']
        opt[f'{order.id} · {item.product_name}']=order.id
    preferred=st.session_state.pop('request_order_id',None)
    opts=list(opt)
    index=next((i for i,label in enumerate(opts) if opt[label]==preferred),1 if len(opts)>1 else 0)
    cat=st.session_state.pop('request_category','Delivery')
    with st.form('new_ticket_form',clear_on_submit=False):
        a,b=st.columns(2,gap='small')
        with a: order_key=st.selectbox('Related order',opts,index=index)
        with b: category=st.selectbox('Issue category',svc.CATEGORIES,index=svc.CATEGORIES.index(cat) if cat in svc.CATEGORIES else 0)
        title=st.text_input('Short issue title',placeholder='Example: My delivery has not arrived',max_chars=180)
        description=st.text_area('What happened?',placeholder='Tell us what went wrong, when it happened, and what you need help with...',height=125,max_chars=4000)
        photos=st.file_uploader('Optional product photos (up to 3, JPEG/PNG, 5 MB each)',type=['jpg','jpeg','png'],accept_multiple_files=True)
        photo_consent=st.checkbox('I agree that my uploaded product photos may be sent to an AI service for visual description (optional).',value=False)
        st.caption('AI photo analysis is optional and requires permission. It cannot determine fault or approve a refund. Support staff review all findings.')
        submitted=st.form_submit_button('Create support request',type='primary',use_container_width=True)
    if submitted:
        try:
            uploads=[(f.name,f.getvalue()) for f in photos]
            tid=svc.create_ticket(actor(),order_id=opt[order_key],category=category,title=title,complaint=description,uploads=uploads,consent_photo_ai=photo_consent)
            st.session_state.selected_ticket_id=tid
            st.session_state['ticket_created_notice'] = tid
            go('Ticket conversation')
        except svc.SupportError as ex:st.error(str(ex))


def inbox():
    header('Messages & notifications','All updates from our support team in one place.','CUSTOMER PORTAL')
    notices=svc.notifications_for_customer(actor())
    if not notices:page_note('No notifications yet.');return
    with st.container(key='sf_zebra_list_inbox', gap=None):
        for index, n in enumerate(notices):
            with st.container(key=f'sf_zebra_row_{index % 2}_inbox_{n.id}', border=False, gap=None):
                a,b=st.columns([5,1.1],vertical_alignment='center')
                with a:
                    st.markdown(list_item_text(('● ' if not n.read_at else '') + n.title,
                                           display_time(n.created_at), body=n.body),
                                unsafe_allow_html=True)
                with b:
                    if n.ticket_id and st.button('View ticket',key='note_ticket_'+str(n.id),use_container_width=True):
                        svc.mark_notification_read(actor(),n.id)
                        goto_ticket(n.ticket_id)
                    if not n.read_at and st.button('Mark read',key='read_'+str(n.id),use_container_width=True):
                        svc.mark_notification_read(actor(),n.id);st.rerun()


def ticket_conversation():
    tid=st.session_state.get('selected_ticket_id')
    if not tid:
        rows=svc.visible_tickets(actor())
        if not rows:st.info('No support requests yet.');return
        tid=rows[0]['ticket'].id
    try:record=svc.ticket_detail(actor(),tid)
    except svc.SupportError as e:st.error(str(e));return
    t=record['ticket'];status=label_status(t.status)
    header(t.title,f'{t.id} · {t.order_id or "General request"}','TICKET CONVERSATION')
    if st.session_state.pop('ticket_created_notice', None) == t.id:
        st.success('Your request has been submitted. Our team will keep you updated here.')
    a,b=st.columns([1.65,1],gap='medium')
    with a:
        st.markdown(badge(status,status_tone(t.status))+' &nbsp; '+badge('Priority '+t.priority,'warning' if t.priority=='P2' else 'neutral'),unsafe_allow_html=True)
        st.markdown('<div class="sf-dividerlabel">Conversation</div>',unsafe_allow_html=True)
        for m in record['messages']:
            sender='You' if m.sender_kind=='customer' else ('Support team' if m.sender_kind=='agent' else 'System')
            chat_bubble(sender,m.body,display_time(m.created_at),m.sender_kind=='customer')
        with st.form('cust_reply_'+t.id,clear_on_submit=True):
            reply=st.text_area('Reply to support',placeholder='Write a message to the support team...',height=85)
            sent=st.form_submit_button('Send message',type='primary')
        if sent:
            try:svc.post_ticket_message(actor(),t.id,reply);st.rerun()
            except svc.SupportError as ex:st.error(str(ex))
    with b:
        with st.container(border=True):
            st.markdown('**Request progress**')
            st.caption('Created → Review → Action → Completed')
            if t.status == 'CLOSED':st.success('This ticket is closed. Reply below to reopen it.')
            elif t.status == 'RESOLVED':st.success('Your support request was marked resolved. Reply below if the issue persists.')
            elif t.status=='AWAITING_APPROVAL':st.warning('Awaiting a human decision.')
            elif t.status=='ACTION_PENDING':st.info('Approved action is being processed.')
            else:st.info('Your request is being reviewed.')
            st.caption('Next target: '+record['sla']['label']+' · '+record['sla']['remaining'])
        if record['order']:
            o=record['order']
            with st.container(border=True):
                st.markdown('**Linked order**')
                st.write(record['item'].product_name if record['item'] else o.id)
                st.caption(o.id+' · '+money(o.total_cents))
                st.markdown(badge(label_status(o.status),status_tone(o.status)),unsafe_allow_html=True)
        if record['commitments']:
            with st.container(border=True):
                st.markdown('**Promised updates**')
                for promise in record['commitments']:
                    st.markdown(f'**{safe(promise.description)}**')
                    st.caption(f'Due {display_time(promise.due_at)} · '+
                               ('Completed' if promise.completed_at else 'Pending'))
        if record['refunds']:
            with st.container(border=True):
                st.markdown('**Refund tracking**')
                for r in record['refunds']:
                    st.markdown(f'{badge(label_status(r.status),status_tone(r.status))} &nbsp; {money(r.amount_cents)}',unsafe_allow_html=True)
                    if r.status=='COMPLETED':st.caption('Marked complete in demo; no real payment.')
        if record['attachments']:
            from supportflow.photo import photo_details, grant_photo_consent, revoke_photo_consent
            with st.expander(f'Attached images ({len(record["attachments"])})'):
                for photo in photo_details(actor(), t.id):
                    attachment=photo['attachment']
                    st.image(svc.read_attachment(actor(),attachment.id),caption=attachment.original_filename,width=280)
                    if photo['consented']:
                        st.caption('AI visual inspection permitted. A support agent may request it.')
                        if st.button('Withdraw AI photo permission',key=f'photo_revoke_{attachment.id}'):
                            try:
                                revoke_photo_consent(actor(), attachment.id)
                                st.rerun()
                            except svc.SupportError as ex:st.error(str(ex))
                    elif st.button('Allow optional AI image description',key=f'photo_optin_{attachment.id}'):
                        try:
                            grant_photo_consent(actor(), attachment.id)
                            st.rerun()
                        except svc.SupportError as ex:st.error(str(ex))
                    else:
                        st.caption('AI inspection is disabled until you opt in. Images remain available to support staff.')
    if st.button('← Back to my requests'):go('My tickets')
