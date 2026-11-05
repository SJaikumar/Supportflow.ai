"""Support agent, approver and administrator screens."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import streamlit as st
from supportflow import services as svc
from supportflow import operations as ops
from supportflow.photo import photo_details, inspect_photo
from supportflow.ai import services as ai_svc
import json
from supportflow.config import ROOT
from supportflow.security import may_review
from supportflow.ui import badge,card,chat_bubble,go,goto_customer,goto_ticket,header,kpi,page_note,status_tone,list_item_text
from supportflow.utils import ACTIVE_STATUSES, display_time,label_status,money,safe


def actor():return st.session_state.current_user


def _queue_rows(rows, prefix='q', limit=None):
    """Render a dense zebra-striped queue with real Streamlit actions.

    A keyed container per row allows predictable CSS striping while retaining
    accessible native buttons. The same list is shared by tickets, the agent
    dashboard and the SLA monitor.
    """
    if limit is not None:
        rows = rows[:limit]
    if not rows:
        page_note('Nothing in this queue.')
        return
    with st.container(key=f'sf_queue_list_{prefix}', gap=None):
        for index, row in enumerate(rows):
            ticket, sla = row['ticket'], row['sla']
            with st.container(key=f'sf_queue_row_{index % 2}_{prefix}_{index}', border=False, gap=None):
                info, flags, deadline, action = st.columns(
                    [4.1, 2.4, 1.8, .86], gap='small', vertical_alignment='center'
                )
                with info:
                    st.markdown(
                        f'<div class="sf-queue-title">{safe(ticket.title)}</div>'
                        f'<div class="sf-queue-meta">{safe(ticket.id)} · '
                        f'{safe(row["customer_name"])} · {safe(ticket.category)}</div>',
                        unsafe_allow_html=True,
                    )
                with flags:
                    tone = 'danger' if ticket.priority == 'P1' else (
                        'warning' if ticket.priority == 'P2' else 'neutral'
                    )
                    st.markdown(
                        '<div class="sf-queue-flags">'
                        + badge(ticket.priority, tone)
                        + badge('Escalated' if ticket.escalated else label_status(ticket.status),
                                'warning' if ticket.escalated else status_tone(ticket.status))
                        + '</div>', unsafe_allow_html=True,
                    )
                with deadline:
                    st.markdown(
                        '<div class="sf-queue-sla">'
                        + badge(sla['remaining'], sla['tone'])
                        + f'<div class="sf-queue-meta">{safe(sla["label"])}</div>'
                        + '</div>', unsafe_allow_html=True,
                    )
                with action:
                    if st.button(
                        'Open', icon=':material/arrow_forward:',
                        key=f'sf_queue_open_{prefix}_{index}',
                        help='Open ticket details', use_container_width=True,
                    ):
                        goto_ticket(ticket.id)



def _render_staff_alerts(*, limit: int = 20, key_prefix: str = 'staff'):
    alerts=ops.staff_alerts(actor())
    active=[a for a in alerts if a.acknowledged_at is None]
    if not active:
        st.caption('No unacknowledged operational alerts.')
        return
    with st.container(key=f'sf_zebra_list_alerts_{key_prefix}', gap=None):
        for index, a in enumerate(active[:limit]):
            severity_tone='danger' if a.severity=='CRITICAL' else ('warning' if a.severity=='HIGH' else 'info')
            with st.container(key=f'sf_zebra_row_{index % 2}_alert_{key_prefix}_{a.id}', border=False, gap=None):
                one,two,three=st.columns([4.2, 1.1, 1],gap='small',vertical_alignment='center')
                with one:
                    st.markdown(list_item_text(a.title, a.details,
                                               badge(a.severity,severity_tone)),
                                unsafe_allow_html=True)
                with two:
                    if st.button('Open ticket',key=f'{key_prefix}_ticket_{a.id}'):
                        goto_ticket(a.ticket_id)
                with three:
                    if st.button('Acknowledge',key=f'{key_prefix}_ack_{a.id}'):
                        ops.acknowledge_alert(actor(), a.id)
                        st.rerun()




def _ticket_escalation_controls(ticket):
    """Internal handoff: separate from approval, messaging, and ticket closure."""
    st.markdown('**Escalation & assignment**')
    history = svc.escalation_history(actor(), ticket.id)
    active = next((item for item in history if item['record'].status in ('OPEN', 'ACKNOWLEDGED')), None)
    if active:
        record = active['record']
        assignee = active['assignee']
        st.markdown(badge('Human escalation · ' + record.status.title(), 'warning'),
                    unsafe_allow_html=True)
        st.caption(f'Assigned to {assignee.name if assignee else "Unknown"} · '
                   f'{display_time(record.created_at)}')
        st.write(record.reason)
        can_handle = actor().role == 'admin' or actor().id == record.assigned_to
        if can_handle:
            if record.status == 'OPEN' and st.button('Acknowledge escalation',
                    key=f'esc_ack_{record.id}', use_container_width=True):
                try:
                    svc.acknowledge_escalation(actor(), record.id)
                    st.rerun()
                except svc.SupportError as ex:
                    st.error(str(ex))
            with st.expander('Record escalation outcome'):
                with st.form(f'esc_complete_{record.id}'):
                    outcome = st.text_area('Outcome / next step', height=90,
                                           placeholder='Document what was investigated and decided.')
                    completed = st.form_submit_button('Complete escalation', use_container_width=True)
                if completed:
                    try:
                        svc.complete_escalation(actor(), record.id, outcome)
                        st.rerun()
                    except svc.SupportError as ex:
                        st.error(str(ex))
            candidates = svc.escalation_targets(actor())
            if candidates:
                with st.expander('Reassign to another person'):
                    targets={f'{u.name} · {u.role.title()}':u.id for u in candidates}
                    with st.form(f'esc_reassign_{record.id}'):
                        selected=st.selectbox('New assignee', list(targets))
                        reason=st.text_area('Reason for reassignment', height=75)
                        submitted=st.form_submit_button('Reassign', use_container_width=True)
                    if submitted:
                        try:
                            svc.reassign_escalation(actor(), record.id, targets[selected], reason)
                            st.rerun()
                        except svc.SupportError as ex:
                            st.error(str(ex))
        else:
            st.info('This case is assigned for human review. The assignee or Admin may acknowledge or reroute it.')
    elif ticket.status in ACTIVE_STATUSES:
        if ticket.escalated:
            st.info('Flagged for human review but not yet assigned. Route this case to a responsible person.')
        candidates=svc.escalation_targets(actor())
        if candidates:
            with st.expander('Escalate / assign ticket', expanded=bool(ticket.escalated)):
                choices={f'{u.name} · {u.role.title()}':u.id for u in candidates}
                with st.form(f'esc_assign_{ticket.id}'):
                    recipient=st.selectbox('Assign to', list(choices))
                    reason=st.text_area('Escalation reason', height=100,
                        placeholder='Describe why human escalation is needed and the requested next action.')
                    submitted=st.form_submit_button('Escalate & assign', type='primary',
                        use_container_width=True)
                if submitted:
                    try:
                        svc.escalate_ticket(actor(), ticket.id, choices[recipient], reason)
                        st.rerun()
                    except svc.SupportError as ex:
                        st.error(str(ex))
    if history:
        with st.expander(f'Escalation history ({len(history)})'):
            for item in history[:10]:
                esc=item['record']
                assigned=item['assignee']
                st.markdown(f'**{safe(esc.status.title())} · {safe(assigned.name if assigned else "Unassigned")}**')
                st.caption(f'{display_time(esc.created_at)} · {esc.reason}')
                if esc.completion_note:
                    st.caption(f'Outcome: {esc.completion_note}')
    st.caption('Escalation assigns human responsibility. Refund authorization is a separate approval decision.')


def escalations():
    """Staff-facing actionable escalation inbox, including unassigned AI flags."""
    header('Escalations', 'Review assigned human cases and route AI-flagged requests.', 'SUPPORT OPERATIONS')
    rows = svc.escalation_queue(actor())
    mine = [r for r in rows if r['assignment'] is not None
            and r['assignment'].assigned_to == actor().id]
    open_rows = [r for r in rows if r['assignment'] is not None]
    unassigned = [r for r in rows if r['assignment'] is None]
    c1,c2,c3=st.columns(3, gap='small')
    with c1:kpi('My escalations', str(len(mine)), 'Assigned to you', '!')
    with c2:kpi('Human handoffs', str(len(open_rows)), 'Acknowledgment and action', '◷')
    with c3:kpi('Needs routing', str(len(unassigned)), 'AI-flagged without assignee', '↗')
    one,two,three=st.tabs(['Assigned to me', 'All active', 'Needs assignment'])
    for container, chosen, prefix in ((one,mine,'mine'), (two,open_rows,'all'),
                                       (three,unassigned,'unassigned')):
        with container:
            if not chosen:
                page_note('No cases in this view.')
            else:
                with st.container(key=f'sf_zebra_list_escalations_{prefix}', gap=None):
                    for i, row in enumerate(chosen):
                        ticket=row['ticket']
                        if ticket is None:continue
                        record=row['assignment']
                        who=row['assignee']
                        with st.container(key=f'sf_zebra_row_{i%2}_escalations_{prefix}_{ticket.id}',
                                          gap=None, border=False):
                            left,right=st.columns([4,1], gap='small', vertical_alignment='center')
                            with left:
                                sub=(f'{ticket.id} · {ticket.priority} · '
                                     + (f'{who.name} · {record.status.title()}' if record else 'Not yet assigned'))
                                st.markdown(list_item_text(ticket.title, sub,
                                    badge('Needs routing' if record is None else record.status.title(),
                                          'warning' if record is None else 'info')),
                                    unsafe_allow_html=True)
                            with right:
                                if st.button('Open', key=f'esc_open_{prefix}_{ticket.id}',
                                             use_container_width=True):
                                    goto_ticket(ticket.id)
    st.caption('AI-detected escalation creates a review flag; a human assigns a named owner here. '
               'Refunds still require separate authorization in Approvals.')

def dashboard():
    """Action-first, compact agent dashboard with a less cluttered right rail."""
    rows = svc.visible_tickets(actor())
    active = [r for r in rows if r['ticket'].status in ACTIVE_STATUSES]
    critical = sum(r['ticket'].priority == 'P1' for r in active)
    breached = sum(r['sla']['seconds'] is not None and r['sla']['seconds'] < 0 for r in active)
    at_risk = sum(r['sla']['seconds'] is not None and
                  0 <= r['sla']['seconds'] <= 3600 for r in active)
    escalation_rows = svc.escalation_queue(actor())
    approval_rows = svc.approvals_list(actor())
    pending_approvals = [r for r in approval_rows if r['approval'].status == 'PENDING']

    header('Agent dashboard', 'Act on the cases that matter most today.', 'SUPPORT OPERATIONS')
    cols = st.columns(4, gap='small')
    for col, title, val, foot, icon in zip(
        cols,
        ['Critical tickets', 'SLA at risk', 'Pending approvals', 'Overdue'],
        [critical, at_risk, len(pending_approvals), breached],
        ['P1 issues', 'Within 60 minutes', 'Awaiting human decision', 'Deadline breached'],
        ['!', '◷', '✓', '⏱'],
    ):
        with col:
            kpi(title, str(val), foot, icon)

    main, side = st.columns([2.65, 1], gap='medium')
    with main:
        st.markdown('<div class="sf-dividerlabel">Requires immediate attention</div>',
                    unsafe_allow_html=True)
        tab1, tab2, tab3 = st.tabs(['Act now', 'Awaiting approval', 'All open'])
        with tab1:
            focus = [r for r in active if r['ticket'].priority in ('P1', 'P2')
                     or r['sla']['tone'] in ('danger', 'warning')]
            _queue_rows(focus, 'focus', 7)
        with tab2:
            with st.container(key='sf_zebra_list_dashboard_approvals', gap=None):
                for index, r in enumerate(pending_approvals[:6]):
                    ap = r['approval']; t = r['ticket']
                    with st.container(key=f'sf_zebra_row_{index % 2}_dashboard_approval_{ap.id}', border=False, gap=None):
                        info, action = st.columns([3.4, 1], gap='small', vertical_alignment='center')
                        with info:
                            st.markdown(list_item_text(t.title,
                                        f'{t.id} · {r["customer_name"]} · '
                                        + money(ap.proposed_amount_cents),
                                        badge('Pending decision', 'warning')),
                                        unsafe_allow_html=True)
                        with action:
                            if st.button('Review', icon=':material/arrow_forward:',
                                         key='dash_app_'+str(ap.id), use_container_width=True):
                                st.session_state.selected_approval_id = ap.id
                                go('Approvals')
            if not pending_approvals:
                page_note('No approvals pending.')
        with tab3:
            _queue_rows(active, 'allactive', 8)
        with st.expander('SLA and missed-promise alerts', expanded=False):
            _render_staff_alerts(limit=8, key_prefix='home')
    with side:
        st.markdown('<div class="sf-dividerlabel">Next actions</div>',
                    unsafe_allow_html=True)
        if st.button(f'Review escalations ({len(escalation_rows)})', icon=':material/priority_high:',
                     key='dashboard_escalations', use_container_width=True):
            go('Escalations')
        if st.button('Review approvals', icon=':material/approval:',
                     key='dashboard_review', use_container_width=True, type='primary'):
            go('Approvals')
        if st.button('All support tickets', icon=':material/confirmation_number:',
                     key='dashboard_tickets', use_container_width=True):
            go('All tickets')
        if st.button('Customer history', icon=':material/groups:',
                     key='dashboard_customer', use_container_width=True):
            go('Customer 360°')
        st.markdown('<div class="sf-dividerlabel">Queue snapshot</div>',
                    unsafe_allow_html=True)
        health = ops.worker_health(actor())
        latest = health['last_run']
        worker_status = (
            f'Background worker: {safe(latest.status.lower())} · '
            f'last run {safe(display_time(latest.finished_at or latest.started_at))}'
            if latest else 'SLA worker has not run yet. Start it in a second terminal.'
        )
        alert_note = (
            f'<div class="sf-snapshot-alert">{health["unacknowledged"]} staff alerts need review.</div>'
            if health['unacknowledged'] else ''
        )
        st.markdown(
            '<div class="sf-snapshot">'
            f'<div class="sf-snapshot-title">{len(active)} active tickets</div>'
            f'<div class="sf-snapshot-detail">{critical} critical · '
            f'{len(pending_approvals)} pending approvals · {breached} overdue</div>'
            f'<div class="sf-snapshot-meta">{worker_status}</div>'
            f'{alert_note}'
            '</div>', unsafe_allow_html=True,
        )


def all_tickets():
    header('Support tickets','Prioritized by deadline and urgency. Open a ticket to take action.','SUPPORT WORKSPACE')
    rows=svc.visible_tickets(actor())
    a,b=st.columns(2,gap='small')
    with a: status=st.selectbox('Status',['All','Active','Escalated','Resolved'])
    with b: category=st.selectbox('Category',['All']+svc.CATEGORIES)
    if status=='Active':rows=[r for r in rows if r['ticket'].status in ACTIVE_STATUSES]
    elif status=='Escalated':rows=[r for r in rows if r['ticket'].escalated and r['ticket'].status in ACTIVE_STATUSES]
    elif status=='Resolved':rows=[r for r in rows if r['ticket'].status in ('RESOLVED','CLOSED')]
    if category!='All':rows=[r for r in rows if r['ticket'].category==category]
    _queue_rows(rows,'list')
    if rows:
        d=[]
        ai_latest=ai_svc.batch_latest(actor(),[r['ticket'].id for r in rows])
        for r in rows:
            t=r['ticket']
            analysis=ai_latest.get(t.id)
            classification=json.loads(analysis.classification_json) if analysis and analysis.status=='SUCCEEDED' else {}
            evidence=json.loads(analysis.citations_json) if analysis and analysis.status=='SUCCEEDED' else []
            d.append({'ticket_id':t.id,'timestamp_utc':t.created_at.isoformat(), 'customer':r['customer_name'],
                 'order_id':t.order_id or '', 'complaint':t.complaint,'category':t.category,'urgency':t.priority,
                 'sentiment':classification.get('sentiment','Not analyzed'),
                 'kb_sources':'; '.join(src['citation'] for src in evidence),
                 'response':analysis.draft_response if analysis and analysis.status=='SUCCEEDED' else 'No AI draft yet',
                 'status':'Escalated' if t.escalated else label_status(t.status),
                 'escalation_reason':'; '.join(json.loads(analysis.escalation_reasons_json)) if analysis and analysis.status=='SUCCEEDED' else ''})
        csv=pd.DataFrame(d).to_csv(index=False).encode('utf-8-sig')
        st.download_button('↓ Export ticket log (CSV)',data=csv,file_name='supportflow_tickets.csv',mime='text/csv')


def ai_assistant_panel(ticket):
    """Staff-only, persisted AI draft and exact citations from local knowledge files."""
    st.markdown('**Four-agent AutoGen analysis**')
    st.caption('Query → Knowledge → Resolution → Log. AI drafts are not sent to customers automatically.')
    if st.session_state.get('ai_draft_notice_ticket') == ticket.id:
        st.success('AI draft added to your reply composer. Open Conversation to edit and send it.')
    if not ai_svc.configured():
        st.info('To enable AutoGen, copy .env.example to .env, set OPENAI_API_KEY, and restart Streamlit. The rest of the app works without a key.')
    photo_items = photo_details(actor(), ticket.id)
    if photo_items:
        total = len(photo_items)
        inspected = sum(any(x.status == 'SUCCEEDED' for x in item['inspections'])
                        for item in photo_items if item['consented'])
        st.info(f'{total} image(s) already attached to this ticket; '
                f'{inspected} inspected with customer consent. '
                'No re-upload is needed.')
        inspect_first = st.checkbox('Inspect consented photos before generating the reply',
                                    value=True, key='photo_first_'+ticket.id)
    else:
        inspect_first = False
    if st.button('Run AI analysis', icon=':material/auto_awesome:', type='primary',
                 disabled=not ai_svc.configured(), key='run_ai_'+ticket.id):
        with st.status('Running four AutoGen agents and retrieving policies…',expanded=True) as status:
            st.write('Building verified order context and policy evidence…')
            try:
                done=[]
                def report_agent_step(source):
                    done.append(source)
                    st.write(f'✓ {len(done)}/4 · {source.replace("_", " ").title()} completed')
                if inspect_first:
                    for item in photo_items:
                        if not item['consented']:
                            continue
                        if any(run.status == 'SUCCEEDED' for run in item['inspections']):
                            continue
                        st.write('Inspecting existing attached image…')
                        inspect_photo(actor(), item['attachment'].id)
                ai_svc.analyze_ticket(actor(), ticket.id,on_step=report_agent_step)
                st.write('Classification, citations, draft and log decision saved to SQLite.')
                status.update(label='AI analysis completed', state='complete')
                st.rerun()
            except svc.SupportError as exc:
                status.update(label='AI run failed',state='error')
                st.error(str(exc))
    recent=ai_svc.latest_analysis(actor(),ticket.id)
    if not recent:
        st.caption('No AI analysis for this ticket yet.')
        return
    run=recent['run']
    if run.status=='FAILED':
        st.error(run.error or 'AI run failed.')
        return
    if run.status!='SUCCEEDED':
        st.warning('An AI analysis was started but has not finished.')
        return
    left,right=st.columns([1.15,1],gap='small')
    with left:
        label='Human review needed' if run.escalated else 'Informational draft'
        tone='warning' if run.escalated else 'success'
        st.markdown(badge(label,tone)+' &nbsp; '+badge(run.confidence+' confidence'),unsafe_allow_html=True)
    with right:st.caption('Policy search: '+run.retrieval_mode)
    classification=recent['classification']
    st.caption('Issue: '+str(classification.get('category','unknown'))+' · Urgency: '+str(classification.get('urgency','unknown'))+' · Sentiment: '+str(classification.get('sentiment','unknown')))
    st.markdown('**Proposed customer response — review before sending**')
    st.text_area('AI draft',value=run.draft_response,height=175,disabled=True,
                 key='ai_readonly_'+run.id)
    if st.button('Use AI Draft in reply', icon=':material/edit_note:',
                 key='use_ai_draft_'+run.id, type='primary'):
        st.session_state['pending_ai_draft'] = {
            'ticket_id': ticket.id, 'run_id': run.id,
            'body': run.draft_response, 'needs_approval': bool(run.escalated),
        }
        st.session_state['ai_draft_notice_ticket'] = ticket.id
        st.rerun()
    if run.escalated:
        st.info('This ticket needs further human handling, but you can send a reviewed customer update now. '
                'An actual refund, payment, or replacement decision still requires separate authorization.')
        st.caption('Review reasons: '+'; '.join(recent['escalation_reasons']))
    st.caption('Select Use AI Draft in reply, edit as needed, confirm your review and send the update. '
               'The system does not issue payments or automatically resolve the case.')
    st.markdown('**Verified policy citations**')
    if not recent['sources']:st.caption('No usable policy passages verified. Escalation required.')
    for source in recent['sources']:
        with st.expander(source['citation']):
            st.write(source['passage'])
    with st.expander('View all four agent outputs and audit trace'):
        for step in recent['steps']:
            st.markdown(f'**{step.step_number}. {step.agent_name.replace("_"," ").title()}**')
            st.json(json.loads(step.output_json))
    st.caption(f'Run ID: {run.id} · Completed: {display_time(run.completed_at)}')


def ticket_conversation():
    tid=st.session_state.get('selected_ticket_id')
    if not tid:
        rows=svc.visible_tickets(actor())
        if not rows:page_note('No tickets found.');return
        tid=rows[0]['ticket'].id
    try:record=svc.ticket_detail(actor(),tid)
    except svc.SupportError as ex:st.error(str(ex));return
    t=record['ticket'];c=record['customer'];person=record['user']
    draft_key='staff_reply_'+t.id
    if st.session_state.get('clear_reply_ticket')==t.id:
        st.session_state[draft_key]=''
        st.session_state.pop('clear_reply_ticket',None)
    pending=st.session_state.get('pending_ai_draft')
    if pending and pending['ticket_id']==t.id:
        st.session_state[draft_key]=pending['body']
        st.session_state['ai_draft_origin_'+t.id]=pending
        del st.session_state['pending_ai_draft']
    header(t.title,f'{t.id} · {person.name} · {t.order_id or "General inquiry"}','TICKET WORKSPACE')
    st.markdown(badge(label_status(t.status),status_tone(t.status))+' &nbsp; '+
                (badge('Escalated to human','warning')+' &nbsp; ' if t.escalated else '')+
                badge('Priority '+t.priority,'danger' if t.priority=='P1' else 'warning')+' &nbsp; '+
                badge(record['sla']['remaining'],record['sla']['tone']),unsafe_allow_html=True)
    left,right=st.columns([1.7,1],gap='medium')
    with left:
        chat_tab,ai_tab,activity_tab=st.tabs(['Conversation','AI assistant','Audit history'])
        with chat_tab:
            for m in record['messages']:
                sender=person.name if m.sender_kind=='customer' else ('Support team' if m.sender_kind=='agent' else 'System')
                chat_bubble(sender,m.body,display_time(m.created_at),m.sender_kind=='customer')
            ai_origin=st.session_state.get('ai_draft_origin_'+t.id)
            if ai_origin:
                st.success('AI draft is ready in the response composer below. Review the wording before sending.')
                st.caption('AI draft loaded. Alex (or another authorized support agent) may edit and '
                           'send an informational customer update.')
                if ai_origin['needs_approval']:
                    st.info('The underlying case remains escalated. Sending a customer update does NOT '
                            'approve a refund, replace an item, or resolve the complaint. '
                            'Submit restricted actions to an authorized approver.')
            with st.form('agent_reply_'+t.id):
                reply=st.text_area('Send a customer-visible response',
                    placeholder='Write an update to the customer...',height=135,key=draft_key)
                reviewed=(st.checkbox(
                    'I reviewed this AI draft and confirm it is an informational update, '
                    'not an approval or payment promise.',key='review_ai_'+t.id)
                    if ai_origin else False)
                sent=st.form_submit_button('Send reviewed response' if ai_origin else 'Send response',
                                           type='primary')
            if sent:
                try:
                    if ai_origin:
                        ai_svc.send_reviewed_ai_draft(actor(), t.id,ai_origin['run_id'],reply,
                                                      human_reviewed=reviewed)
                        st.session_state.pop('ai_draft_origin_'+t.id,None)
                        st.session_state.pop('ai_draft_notice_ticket',None)
                    else:
                        svc.post_ticket_message(actor(),t.id,reply)
                    st.session_state['clear_reply_ticket']=t.id
                    st.rerun()
                except svc.SupportError as ex:st.error(str(ex))
            if ai_origin and st.button('Discard AI draft and write a manual update',
                                      key='discard_ai_'+t.id):
                st.session_state.pop('ai_draft_origin_'+t.id,None)
                st.session_state.pop('ai_draft_notice_ticket',None)
                st.session_state['clear_reply_ticket']=t.id
                st.rerun()
        with ai_tab:
            ai_assistant_panel(t)
        with activity_tab:
            for event in svc.audit_for_ticket(actor(),t.id):
                st.markdown(f'**{safe(event.event_type.replace("_"," ").title())}**')
                st.caption(f'{display_time(event.created_at)} · {event.details}')
            if not svc.audit_for_ticket(actor(),t.id):st.caption('No audit events for this ticket yet.')
    with right:
        _ticket_escalation_controls(t)
        # Stage 4.5: explicit ticket lifecycle controls, always visible to staff.
        st.markdown('**Ticket management**')
        blockers = svc.ticket_action_blockers(actor(), t.id)
        if blockers:
            st.warning('Actions pending: ' + ' '.join(blockers))
        if t.status in ACTIVE_STATUSES:
            with st.form('resolve_ticket_' + t.id):
                note = st.text_area('Resolution summary for customer',
                    placeholder='Explain what was actually resolved (not simply that a reply was sent).',
                    height=90, max_chars=1000)
                submit_resolve = st.form_submit_button('Mark resolved', type='primary',
                    disabled=bool(blockers), use_container_width=True)
            if submit_resolve:
                try:
                    svc.resolve_ticket(actor(), t.id, note)
                    st.rerun()
                except svc.SupportError as ex:
                    st.error(str(ex))
        elif t.status == 'RESOLVED':
            st.success('The underlying issue is marked resolved.')
            with st.form('close_ticket_' + t.id):
                confirmed = st.checkbox('I confirm this case is ready to close.')
                submit_close = st.form_submit_button('Close ticket', type='primary',
                    disabled=bool(blockers), use_container_width=True)
            if submit_close:
                if not confirmed:
                    st.error('Confirm that this resolved case is ready to close.')
                else:
                    try:
                        svc.close_ticket(actor(), t.id)
                        st.rerun()
                    except svc.SupportError as ex:
                        st.error(str(ex))
        else:
            st.info('Ticket closed. The customer can reply to reopen it.')
        if t.status in {'RESOLVED', 'CLOSED'}:
            with st.expander('Reopen ticket'):
                with st.form('reopen_ticket_' + t.id):
                    reason = st.text_area('Reason for reopening', height=85, max_chars=1000)
                    submit_reopen = st.form_submit_button('Reopen ticket')
                if submit_reopen:
                    try:
                        svc.reopen_ticket(actor(), t.id, reason)
                        st.rerun()
                    except svc.SupportError as ex:
                        st.error(str(ex))
        st.caption('Closure decisions are recorded in the audit history and customer inbox.')
        with st.expander('Customer and order history', expanded=False):
            historic=svc.customer_detail(actor(), c.id)
            insights=historic['insights']
            st.caption(f"{insights['tickets_raised']} prior and current support requests · "
                       f"{insights['refund_orders']} orders with refund requests")
            for previous in historic['tickets'][:5]:
                if previous.id != t.id:
                    st.caption(f'{previous.id} · {previous.title} · {label_status(previous.status)}')
            if record['order_events']:
                st.markdown('**Order events**')
                for event in record['order_events'][:5]:
                    st.caption(f'{display_time(event.occurred_at)} · {event.description}')
            linked=svc.related_tickets(actor(),t.id)
            if linked:
                st.markdown('**Related cases for this order**')
                for case in linked:
                    if st.button(f'{case.id} · {case.title}',key=f'related_{t.id}_{case.id}'):
                        goto_ticket(case.id)
        with st.expander('Customer promises / follow-ups', expanded=False):
            for promise in record['commitments']:
                status='Completed' if promise.completed_at else ('Overdue' if promise.due_at<datetime.now(timezone.utc).replace(tzinfo=None) else 'Open')
                st.markdown(f'**{safe(promise.description)}**')
                st.caption(f'Due: {display_time(promise.due_at)} · {status}')
                if not promise.completed_at and st.button('Mark completed',key=f'commit_done_{promise.id}'):
                    try:svc.complete_commitment(actor(),promise.id);st.rerun()
                    except svc.SupportError as e:st.error(str(e))
            with st.form('new_commitment_'+t.id):
                desc=st.text_input('Next promised action',placeholder='Provide an order status update')
                hours=st.number_input('Due in hours (24×7)',min_value=1,max_value=720,value=4)
                public=st.checkbox('Show promise to customer',value=True)
                if st.form_submit_button('Save commitment'):
                    try:
                        svc.create_commitment(actor(),t.id,desc,datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(hours=int(hours)),
                                              customer_visible=public)
                        st.rerun()
                    except svc.SupportError as e:st.error(str(e))
        with st.container(border=True):
            st.markdown('**Customer 360°**')
            st.write(person.name)
            st.caption(c.code+' · Linked customer history')
            if st.button('Open full customer profile',use_container_width=True):goto_customer(c.id)
        if record['order']:
            with st.container(border=True):
                st.markdown('**Order details**')
                o=record['order']
                st.write(record['item'].product_name if record['item'] else o.id)
                st.caption(f'{o.id} · {money(o.total_cents)}')
                st.markdown(badge(label_status(o.status),status_tone(o.status)),unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('**Approvals and refunds**')
            for ap in record['approvals']:
                st.markdown(badge(label_status(ap.status),status_tone(ap.status))+' &nbsp; '+money(ap.proposed_amount_cents),unsafe_allow_html=True)
            for ref in record['refunds']:
                st.caption(f'Refund #{ref.id}: {label_status(ref.status)}')
            if record['approvals']:
                if st.button('View approval queue',key='ticket_approvals',use_container_width=True):
                    st.session_state.selected_approval_id=record['approvals'][0].id
                    go('Approvals')
        if record['attachments']:
            with st.expander(f'Product photos & AI inspection ({len(record["attachments"])})'):
                st.caption('Visual observations only. AI cannot authorize a refund or determine damage cause.')
                for detail in photo_details(actor(), t.id):
                    photo=detail['attachment']
                    st.image(svc.read_attachment(actor(),photo.id),caption=photo.original_filename,width=280)
                    if not detail['consented']:
                        st.warning('Customer has not opted in to AI photo inspection. Manual review only.')
                    else:
                        if st.button('Inspect with AI',key=f'inspect_ai_{photo.id}',
                                     disabled=not ai_svc.configured()):
                            try:
                                with st.spinner('Describing observable features…'):
                                    inspect_photo(actor(),photo.id)
                                st.rerun()
                            except svc.SupportError as e:st.error(str(e))
                    for run in detail['inspections'][:2]:
                        if run.status=='SUCCEEDED':
                            output=json.loads(run.observations_json)
                            st.markdown('**AI visual observations**')
                            st.write(output.get('summary',''))
                            for sign in output.get('visible_signs',[]):st.caption('• '+sign)
                            st.caption('Uncertainty: '+output.get('uncertainties',''))
                            st.info('Requires human review; no automated refund decision.')
                        elif run.status=='FAILED':
                            st.warning('Inspection attempt failed. Photo is still available for manual review.')
        if t.order_id and not any(ap.status=='PENDING' for ap in record['approvals']):
            with st.expander('Create a human refund approval request'):
                with st.form('request_approval_'+t.id):
                    amount=st.number_input('Proposed refund amount (INR)',min_value=1.0,
                        max_value=record['order'].total_cents/100, value=min(1000.0,record['order'].total_cents/100),step=1.0)
                    previous_ai=ai_svc.latest_analysis(actor(),t.id)
                    ai_default=(previous_ai['run'].draft_response if previous_ai and previous_ai['run'].status=='SUCCEEDED'
                                else 'Your refund request has been reviewed. If approved, we will process a simulated refund and send a confirmation.')
                    chosen=st.session_state.get('ai_draft_origin_'+t.id)
                    if chosen:
                        ai_default=st.session_state.get(draft_key,chosen['body'])
                    draft=st.text_area('Proposed customer message',value=ai_default)
                    if st.form_submit_button('Submit for human approval',type='primary'):
                        try:
                            svc.request_approval(actor(),t.id,int(round(amount*100)),draft)
                            st.success('Approval submitted.');st.rerun()
                        except svc.SupportError as ex:st.error(str(ex))
        page_note('AI drafts are internal until reviewed. Refund approvals require a separate human authorization; no real payments are made.')
    if st.button('← Back to ticket queue'):go('All tickets')


def approvals():
    header('Human approval desk','Review evidence, edit the customer response and record a decision.','HUMAN-IN-THE-LOOP')
    rows=svc.approvals_list(actor())
    if not rows:page_note('No approval requests.');return
    pending=[r for r in rows if r['approval'].status=='PENDING']
    done=[r for r in rows if r['approval'].status!='PENDING']
    st.caption(f'{len(pending)} pending · {len(done)} decided · Only Approver and Admin accounts can authorize decisions.')
    options={f'#{r["approval"].id} · {r["ticket"].id} · {r["customer_name"]} · {label_status(r["approval"].status)}':r['approval'].id for r in rows}
    keys=list(options)
    selected=st.session_state.pop('selected_approval_id',None)
    idx=next((i for i,key in enumerate(keys) if options[key]==selected),0)
    chosen=st.selectbox('Choose approval request',keys,index=idx)
    target=next(r for r in rows if r['approval'].id==options[chosen])
    ap=target['approval'];t=target['ticket']
    details=svc.ticket_detail(actor(),t.id)
    left,right=st.columns([1,1.3],gap='medium')
    with left:
        with st.container(border=True):
            st.markdown(f'**{safe(t.title)}**')
            st.caption(f'{t.id} · {target["customer_name"]}')
            st.markdown(badge(label_status(ap.status),status_tone(ap.status))+' &nbsp; '+badge(t.priority,'danger' if t.priority=='P1' else 'warning'),unsafe_allow_html=True)
            st.write('**Proposed refund:** '+money(ap.proposed_amount_cents))
            st.write('**Customer complaint**')
            st.write(t.complaint)
            if details['order']:
                st.caption(f'Order {details["order"].id} · Total {money(details["order"].total_cents)}')
            if st.button('View customer history',key='app_hist'):goto_customer(details['customer'].id)
        with st.expander('Policy note and audit'):
            st.caption('Approvals are explicit human decisions; AI-generated drafts never authorize a refund or payment.')
            latest=ai_svc.latest_analysis(actor(),t.id)
            if latest and latest['run'].status=='SUCCEEDED':
                st.caption('Most recent AI analysis: '+latest['run'].retrieval_mode)
                for source in latest['sources']:
                    st.markdown('**'+safe(source['citation'])+'**')
                    st.caption(source['passage'][:500])
            else:
                st.caption('No completed AutoGen analysis for this ticket. You can run it from the ticket detail.')
            st.caption('Approval decisions are restricted, recorded and persistent in SQLite.')
    with right:
        if ap.status=='PENDING':
            if not may_review(actor().role):
                st.info('Read-only. Sign in as Maya (Approver) or Admin to approve or reject this request.')
                card('Proposed message',ap.draft_response)
            else:
                with st.form('approval_decision_'+str(ap.id)):
                    st.markdown('**Edit the approved customer response**')
                    proposed=st.text_area('Customer message after approval',value=ap.draft_response,height=145)
                    st.markdown('**If rejecting, provide a reason and a different customer message**')
                    reason=st.text_input('Internal rejection reason',placeholder='Explain the reason for rejecting this action')
                    rejection=st.text_area('Customer response after rejection',value='After reviewing your request, we cannot approve the refund at this stage. Please share any additional evidence, and our team will review it again.',height=105)
                    approve_col,reject_col=st.columns(2)
                    with approve_col: approve=st.form_submit_button('✓ Approve & notify',type='primary',use_container_width=True)
                    with reject_col: reject=st.form_submit_button('✕ Reject & notify',use_container_width=True)
                if approve or reject:
                    try:
                        svc.decide_approval(actor(),ap.id,approve=bool(approve),
                            edited_message=proposed if approve else rejection,reason=reason)
                        st.success('Decision stored and customer notified in the portal.')
                        st.rerun()
                    except svc.SupportError as ex:st.error(str(ex))
        else:
            st.markdown(badge(label_status(ap.status),status_tone(ap.status)),unsafe_allow_html=True)
            card('Message delivered to customer',ap.approved_message or ap.draft_response)
            st.caption('Decision recorded '+display_time(ap.reviewed_at)+' · '+(ap.reviewer_reason or 'No note'))
            if ap.status=='APPROVED' and may_review(actor().role):
                processing=[r for r in details['refunds'] if r.status=='PROCESSING']
                for r in processing:
                    st.warning('Simulated refund is processing. No real payment will occur.')
                    if st.button('Complete demo refund',key='complete_'+str(r.id),type='primary'):
                        try:svc.complete_simulated_refund(actor(),r.id);st.success('Simulated refund completed.');st.rerun()
                        except svc.SupportError as ex:st.error(str(ex))
    st.markdown('<div class="sf-dividerlabel">How to test the full loop</div>',unsafe_allow_html=True)
    page_note('1. Log in as Maya (Approver). 2. Approve and edit a response. 3. Log out and sign in as the corresponding customer. 4. Open Messages to see the persisted notification and response. 5. Return as Maya to complete the simulated refund.')


def customer_360():
    header('Customer 360°','Order, complaint and refund history in one factual view.','CUSTOMER INSIGHTS')
    customers=svc.customers_list(actor())
    if not customers:page_note('No customers.');return
    opts={f'{r["user"].name} · {r["customer"].code}':r['customer'].id for r in customers}
    preferred=st.session_state.pop('selected_customer_id',None)
    keys=list(opts)
    idx=next((i for i,key in enumerate(keys) if opts[key]==preferred),0)
    selection=st.selectbox('Customer',keys,index=idx)
    info=svc.customer_detail(actor(),opts[selection]);customer=info['customer'];user=info['user']
    st.markdown(f'<div class="sf-card"><div class="sf-card-title">👤 {safe(user.name)} &nbsp; {badge(customer.code)}</div>'+
        f'<div class="sf-muted">Customer since {display_time(customer.joined_at,False)} · {safe(user.email)}</div></div>',unsafe_allow_html=True)
    insights=info['insights']
    refund_orders=insights['refund_orders']
    cols=st.columns(4,gap='small')
    vals=[insights['orders_placed'],insights['tickets_raised'],refund_orders,insights['refunds_completed']]
    for col,label,val in zip(cols,['Orders','Support requests','Orders with refund requests','Refunds completed'],vals):
        with col:kpi(label,str(val),'From stored records')
    eligible=insights['eligible_delivered_orders']
    rate=insights['refund_request_rate_pct']
    page_note(f'{insights["eligible_orders_with_refund_requests"]} eligible delivered orders have refund requests '
        +f'out of {eligible} eligible delivered orders. '
        +(f'Request rate: {rate:.1f}%.' if rate is not None else 'Request rate not available.')+
        ' Descriptive customer service context only; not a fraud determination.')
    a,b,c,d,e=st.tabs(['Support history','Orders','Refunds','Insights & notes','Promises'])
    with a:
        if not info['tickets']:st.caption('No previous tickets.')
        with st.container(key='sf_zebra_list_customer_history', gap=None):
            for index, t in enumerate(info['tickets']):
                with st.container(key=f'sf_zebra_row_{index % 2}_customer_history_{t.id}', border=False, gap=None):
                    one,two=st.columns([4,1],vertical_alignment='center')
                    with one:
                        st.markdown(list_item_text(t.title,
                                   f'{t.id} · {display_time(t.created_at)} · {t.category}',
                                   badge(label_status(t.status),status_tone(t.status))),
                                   unsafe_allow_html=True)
                    with two:
                        if st.button('Open →',key='hist_'+t.id,use_container_width=True):goto_ticket(t.id)
    with b:
        dataframe=pd.DataFrame([{'Order':o.id,'Placed':display_time(o.placed_at),'Status':label_status(o.status),
                                 'Amount':money(o.total_cents)} for o in info['orders']])
        st.dataframe(dataframe,use_container_width=True,hide_index=True)
    with c:
        if not info['refunds']:st.caption('No refund requests.')
        else:
            st.dataframe(pd.DataFrame([{'Ticket':r.ticket_id,'Order':r.order_id,'Amount':money(r.amount_cents),
                 'Status':label_status(r.status)} for r in info['refunds']]),use_container_width=True,hide_index=True)
    with d:
        st.markdown('**Repeat contacts on the same order**')
        groups=insights['repeat_order_ticket_ids']
        if groups:
            for order_id,ids in groups.items():
                st.caption(f'{order_id}: {", ".join(ids)}')
        else:
            st.caption('No repeated order-linked tickets in current history.')
        st.markdown('**Internal support notes**')
        st.caption('Notes are visible to authorized support staff only, never to customers.')
        for note in info['notes']:
            st.markdown(safe(note.text))
            st.caption(display_time(note.created_at))
        with st.form('add_customer_note_'+str(customer.id),clear_on_submit=True):
            note_text=st.text_area('Add an internal note',height=80,
                placeholder='Record objective observations from past contacts.')
            if st.form_submit_button('Save internal note'):
                try:svc.add_customer_note(actor(),customer.id,note_text);st.rerun()
                except svc.SupportError as ex:st.error(str(ex))
    with e:
        if not info['commitments']:st.caption('No tracked customer promises yet.')
        for promise in info['commitments']:
            state='Completed' if promise.completed_at else ('Overdue' if promise.due_at<datetime.now(timezone.utc).replace(tzinfo=None) else 'Open')
            st.markdown(f'**{safe(promise.description)}** · {badge(state,"success" if promise.completed_at else "warning")} ',unsafe_allow_html=True)
            st.caption(f'{promise.ticket_id} · Due {display_time(promise.due_at)}')


def sla_monitor():
    header('SLA monitor','24×7 clocks calculated from persisted UTC deadlines.','SERVICE PERFORMANCE')
    rows=svc.visible_tickets(actor());active=[r for r in rows if r['ticket'].status in ACTIVE_STATUSES]
    overdue=[r for r in active if r['sla']['tone']=='danger']
    risk=[r for r in active if r['sla']['tone']=='warning']
    c1,c2,c3=st.columns(3,gap='small')
    with c1:kpi('Active',str(len(active)),'Open service obligations')
    with c2:kpi('At risk',str(len(risk)),'Under 60 minutes')
    with c3:kpi('Breached',str(len(overdue)),'Immediate action required')
    st.markdown('<div class="sf-dividerlabel">Service level rules</div>',unsafe_allow_html=True)
    st.dataframe(pd.DataFrame([{'Priority':p.priority,'First response':f'{p.first_response_minutes} min',
        'Resolution':f'{p.resolution_minutes//60} hours'} for p in svc.sla_policies()]),
        use_container_width=True,hide_index=True)
    if actor().role=='admin':
        with st.expander('Configure SLA rules (administrator)'):
            with st.form('sla_rules_admin'):
                chosen=st.selectbox('Priority',['P1','P2','P3','P4'])
                response=st.number_input('First response (minutes)',min_value=1,value=60)
                resolution=st.number_input('Resolution (minutes)',min_value=1,value=480)
                st.caption('Updates affect new tickets only. Existing ticket deadlines are retained.')
                if st.form_submit_button('Save SLA policy'):
                    try:svc.update_sla_policy(actor(),chosen,int(response),int(resolution));st.rerun()
                    except svc.SupportError as e:st.error(str(e))
    st.markdown('<div class="sf-dividerlabel">Background monitoring</div>',unsafe_allow_html=True)
    health=ops.worker_health(actor())
    last=health['last_run']
    if last:
        st.caption(f'Latest worker sweep: {display_time(last.finished_at or last.started_at)} · '
                   f'{last.status} · {last.event_count} new events')
    else:
        st.warning('Worker is not running or has not completed a sweep yet. Start python -m supportflow.worker --interval 60 in a separate terminal.')
    if st.button('Run one SLA check now',key='sla_one_tick'):
        try:
            outcome=ops.run_tick()
            st.success(f'Check completed: {outcome["events"]} new records')
            st.rerun()
        except Exception as ex:
            st.error(f'Worker check failed ({type(ex).__name__}). Check server logs.')
    st.markdown('<div class="sf-dividerlabel">Unacknowledged SLA & promise alerts</div>',unsafe_allow_html=True)
    _render_staff_alerts(limit=30,key_prefix='sla')
    st.markdown('<div class="sf-dividerlabel sf-queue-heading">Current deadlines</div>',unsafe_allow_html=True)
    _queue_rows(active,'sla')
    page_note('24×7 checks require the separate worker process. Portal alerts persist across restarts; simulated payments are never real.')


def analytics():
    header('Support analytics','Service trends and workload by category.','OPERATIONS REPORTING')
    rows=svc.visible_tickets(actor());tickets=[r['ticket'] for r in rows]
    categories=Counter(t.category for t in tickets)
    col1,col2,col3=st.columns(3,gap='small')
    with col1:kpi('Total tickets',str(len(tickets)),'Seeded + new requests')
    with col2:kpi('Resolved',str(sum(t.status=='RESOLVED' for t in tickets)),'Marked complete')
    with col3:kpi('Escalated',str(sum(bool(t.escalated) for t in tickets)),'Need human attention')
    st.markdown('<div class="sf-dividerlabel">Tickets by category</div>',unsafe_allow_html=True)
    chart=pd.DataFrame({'Category':list(categories.keys()),'Tickets':list(categories.values())}).set_index('Category')
    if not chart.empty:st.bar_chart(chart,color='#6C68F7',height=265)
    page_note('These counts come from SQLite, not an LLM. Advanced resolution-time trends and SLA history charts are planned for later stages.')


def knowledge_base():
    header('Knowledge base','Search verified local policies with citations and inspect AI retrieval.','SUPPORT OPERATIONS')
    docs=[('Shipping policy','shipping_policy.md'),('Refund policy','refund_policy.md'),
          ('Account & login','account_and_login.md'),('Product FAQs','product_faq.md')]
    st.caption('BM25 search is available offline. FAISS semantic search uses OpenAI embeddings when an API key is configured.')
    with st.form('kb_search_form'):
        query=st.text_input('Try a policy question',placeholder='Example: Can I return a damaged blender after 10 days?')
        use_hybrid=st.checkbox('Include semantic FAISS results',value=ai_svc.configured(),disabled=not ai_svc.configured())
        run_search=st.form_submit_button('Search policies',type='primary')
    if run_search:
        try:
            result=ai_svc.preview_policy_search(actor(),query,online=use_hybrid)
            st.success(f"Search method: {result['mode']} · {len(result['passages'])} passages")
            if result.get('warning'):st.warning(result['warning'])
            for passage in result['passages']:
                with st.expander(passage['citation'],expanded=True):
                    st.write(passage['passage'])
                    st.caption('BM25 score: '+str(passage.get('bm25_score',0)))
            if not result['passages']:st.warning('No matching company policy found. The AI must escalate rather than invent an answer.')
        except (svc.SupportError,Exception) as exc:
            st.error('Search was unsuccessful ('+type(exc).__name__+').')
    for title,filename in docs:
        with st.expander(f'📄 {title} · {filename}'):
            st.markdown((ROOT/'knowledge_base'/filename).read_text(encoding='utf-8'))
