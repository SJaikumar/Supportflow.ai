"""Reusable compact UI components for the light-first SupportFlow design."""
from __future__ import annotations
import streamlit as st
from .utils import safe, display_time, money, label_status


def apply_styles():
    '''Stage 1.2: compact queues, nonoverlapping nav, and icon-rail sidebar.

    The custom navigation and compact mode are real Streamlit widgets, not a
    screenshot-only CSS trick. Small selectors target Streamlit 1.48+ markup.
    '''
    dark=bool(st.session_state.get('dark_mode',False))
    compact=bool(st.session_state.get('compact_sidebar',False))
    theme = {
        'bg':'#101629' if dark else '#F7F8FD',
        'surface':'#1B2438' if dark else '#FFFFFF',
        'surface2':'#242E44' if dark else '#F6F7FC',
        'text':'#F3F6FF' if dark else '#172343',
        'muted':'#A7B3CC' if dark else '#78849C',
        'border':'#34405C' if dark else '#E8EBF5',
        'soft':'#30305D' if dark else '#EFEDFF',
        'accent':'#ACA6FF' if dark else '#615BF3',
        'shadow':'rgba(0,0,0,.16)' if dark else 'rgba(31,49,98,.045)',
    }
    v=';'.join('--sf-'+k+':'+value for k,value in theme.items())
    sw='78px' if compact else '252px'
    compact_css=r'''
        [data-testid="stSidebar"] [data-testid="stPageLink"] p {display:none !important;}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a,
        [data-testid="stSidebar"] [data-testid="stPageLink"] a > div {
            justify-content:center !important; gap:0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stPageLink"] a {
            padding:9px !important; min-height:42px !important;
        }
        [data-testid="stSidebar"] [data-testid="stPageLink"] span[data-testid="stIconMaterial"],
        [data-testid="stSidebar"] [data-testid="stPageLink"] span.material-symbols-rounded {
            font-size:23px !important;
        }
        [data-testid="stSidebar"] [data-testid="stButton"] button p {display:none !important;}
        [data-testid="stSidebar"] [data-testid="stButton"] button {padding:8px !important;}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:.40rem !important;}
        [data-testid="stSidebar"] .sf-sidebar-section {display:none;}
        [data-testid="stSidebar"] .sf-sidebar-avatar {margin:2px auto 6px;}
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {display:none;}
    ''' if compact else ''
    dark_css=r'''
        [data-testid="stApp"] [data-testid="stTextInput"] input,
        [data-testid="stApp"] textarea,
        [data-testid="stApp"] [data-baseweb="select"] > div {
            background:#242E44 !important; color:#F3F6FF !important;
            border-color:#3B4761 !important;
        }
    ''' if dark else ''
    st.markdown(f'''<style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
        :root{{{v}}}
        html,body,[data-testid="stApp"],button,input,textarea,label{{
            font-family:'Inter',system-ui,'Segoe UI',sans-serif !important;
        }}
        html,body{{font-size:14px;}}
        [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
            background:var(--sf-bg) !important;color:var(--sf-text) !important;
        }}
        /* Leave room for Streamlit's own upper-right controls. Deploy is disabled
           through [client] toolbarMode = "viewer" in config.toml. */
        [data-testid="stMainBlockContainer"], .block-container {{
            max-width:1560px !important; min-width:0 !important;
            padding-top:2.35rem !important; padding-left:1.35rem !important;
            padding-right:1.35rem !important; padding-bottom:1.1rem !important;
        }}
        [data-testid="stHorizontalBlock"]{{align-items:stretch; min-width:0;}}
        [data-testid="column"], [data-testid="stColumn"]{{min-width:0;}}
        [data-testid="stSidebar"]{{
            background:var(--sf-surface) !important;
            border-right:1px solid var(--sf-border) !important;
            width:{sw} !important;min-width:{sw} !important;
            max-width:{sw} !important;flex:0 0 {sw} !important;
            transition:width .18s ease, min-width .18s ease;
        }}
        [data-testid="stSidebar"] > div:first-child {{padding-top:.45rem;}}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"]{{gap:.55rem;}}
        [data-testid="stVerticalBlock"]{{gap:.67rem;}}
        [data-testid="stSidebar"] [data-testid="stPageLink"]{{margin:.06rem 0;}}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a{{
            border-radius:11px !important;padding:.50rem .72rem !important;
            color:var(--sf-muted) !important;font-weight:600 !important;
            font-size:.86rem !important;text-decoration:none !important;
            transition:background .15s ease,color .15s ease;
        }}
        /* Stable one-line nav rows. Expanded links have no hover help tooltip. */
        [data-testid="stSidebar"] [data-testid="stPageLink"] a{{
            display:flex !important;align-items:center !important;min-height:42px !important;
            overflow:hidden !important;white-space:nowrap !important;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a > div{{
            display:flex !important;align-items:center !important;
            gap:.60rem !important;min-width:0 !important;overflow:hidden !important;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a p{{
            white-space:nowrap !important;overflow:hidden !important;
            text-overflow:ellipsis !important;margin:0 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover{{background:var(--sf-surface2) !important;color:var(--sf-accent) !important;}}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"],
        [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="true"]{{
            background:var(--sf-soft) !important;color:var(--sf-accent) !important;
            font-weight:750 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] [data-testid="stIconMaterial"]{{color:inherit !important;}}
        /* Maintain a visible separation between the section label and first nav row.
           Padding (not just margin) reserves space inside Streamlit markdown blocks. */
        .sf-sidebar-section{{display:block;font-size:.67rem;font-weight:750;
            letter-spacing:.09em;line-height:1.35;text-transform:uppercase;
            color:var(--sf-muted);margin:.75rem 0 0;padding-bottom:14px;}}
        .sf-sidebar-profile{{background:var(--sf-surface2);border:1px solid var(--sf-border);
            border-radius:12px;padding:9px 10px;overflow-wrap:anywhere;}}
        .sf-sidebar-avatar{{display:grid;place-items:center;width:38px;height:38px;
            border-radius:13px;color:#5854E7;background:#E9E8FF;font-weight:800;
            font-family:'Plus Jakarta Sans',sans-serif;font-size:12px;}}
        .sf-sidebar-name{{font-size:.80rem;font-weight:750;color:var(--sf-text);}}
        .sf-sidebar-email{{font-size:.69rem;color:var(--sf-muted);overflow-wrap:anywhere;}}
        .sf-sidebar-sub{{font-size:.66rem;color:var(--sf-muted);}}
        [data-testid="stMetric"]{{background:var(--sf-surface);border:1px solid var(--sf-border);
            border-radius:14px;padding:11px 13px;}}
        [data-testid="stMetricValue"]{{font-size:1.45rem;line-height:1.4;font-weight:800;color:var(--sf-text);}}
        [data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"] > div{{border-color:var(--sf-border) !important;border-radius:13px;}}
        div[data-testid="stButton"] button{{min-height:38px;border-radius:10px;font-weight:650;
            font-size:.84rem;transition:background .16s ease,border-color .16s ease,transform .16s ease;}}
        button[kind="primary"]{{background:linear-gradient(115deg,#6964F6,#5389F8) !important;
            border:0 !important;color:white !important;box-shadow:0 4px 12px rgba(90,91,236,.13);}}
        button[kind="secondary"]{{background:var(--sf-surface) !important;color:var(--sf-text) !important;
            border:1px solid var(--sf-border) !important;}}
        button[kind="secondary"]:hover{{border-color:#B7B3FC !important;background:var(--sf-soft) !important;}}
        .st-key-quick_track_delivery button{{background:{'#253F66' if dark else '#EDF4FF'} !important;border-color:{'#365987' if dark else '#CFE2FF'} !important;color:{'#DDEAFF' if dark else '#245FAE'} !important;}}
        .st-key-quick_return_refund button{{background:{'#332951' if dark else '#F0ECFF'} !important;border-color:{'#4B4070' if dark else '#DDD3FF'} !important;color:{'#D9D0FF' if dark else '#5C49BD'} !important;}}
        .st-key-quick_report_damage button{{background:{'#493623' if dark else '#FFF4E9'} !important;border-color:{'#715037' if dark else '#FFE2C3'} !important;color:{'#FFD9AF' if dark else '#9D5C1A'} !important;}}
        .st-key-quick_other_support button{{background:{'#1E463D' if dark else '#EAF8F2'} !important;border-color:{'#346456' if dark else '#D0EEE0'} !important;color:{'#B2F4D9' if dark else '#167B57'} !important;}}
        .st-key-quick_track_delivery button,.st-key-quick_return_refund button,
        .st-key-quick_report_damage button,.st-key-quick_other_support button{{
            justify-content:flex-start !important;min-height:45px !important;padding-left:13px !important;
        }}
        [data-testid="stForm"]{{border:1px solid var(--sf-border) !important;border-radius:14px;padding:.82rem 1rem;}}
        [data-testid="stAlert"]{{border-radius:11px;}}
        [data-testid="stDataFrame"]{{border-radius:12px;overflow:hidden;}}
        h1,h2,h3,h4,.sf-title,.sf-brand,.sf-kpi-value,.sf-card-title{{
            font-family:'Plus Jakarta Sans','Inter',system-ui,sans-serif !important;
            letter-spacing:-.035em !important;color:var(--sf-text) !important;
        }}
        p,span,label{{line-height:1.42;}}
        [data-testid="stMarkdownContainer"] p{{margin-bottom:.16rem;}}
        [data-testid="stCaptionContainer"] p{{font-size:.71rem;color:var(--sf-muted);}}
        .sf-head{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0;}}
        .sf-title{{font-weight:800;font-size:1.51rem;line-height:1.22;overflow-wrap:anywhere;}}
        .sf-sub{{color:var(--sf-muted);font-size:.81rem;margin-top:5px;}}
        .sf-eyebrow{{font-size:.64rem;font-weight:750;text-transform:uppercase;letter-spacing:.10em;
            color:var(--sf-muted);margin-bottom:4px;}}
        .sf-brand{{font-size:1rem;font-weight:800;display:flex;align-items:center;gap:8px;
            white-space:nowrap;letter-spacing:-.05em !important;}}
        .sf-logo{{display:inline-grid;flex-shrink:0;place-items:center;border-radius:11px;width:34px;height:34px;
            color:white;font-size:20px;background:linear-gradient(135deg,#438AFF,#7566F4);
            box-shadow:0 7px 16px rgba(83,106,245,.17);}}
        .sf-ai{{color:#625CF5;background:#EAE9FF;padding:2px 5px;border-radius:5px;
            font-size:.61rem;letter-spacing:0;}}
        .sf-card{{background:var(--sf-surface);border:1px solid var(--sf-border);
            border-radius:14px;padding:12px 14px;box-shadow:0 5px 18px var(--sf-shadow);}}
        .sf-card-title{{font-size:.83rem;font-weight:750;margin:0 0 5px;}}
        .sf-muted{{font-size:.78rem;color:var(--sf-muted);line-height:1.48;}}
        .sf-small{{font-size:.68rem;color:var(--sf-muted);}}
        .sf-hero{{background:linear-gradient(115deg, {'#292850,#1A344A' if dark else '#EEECFF,#EDF5FF'});
            border:1px solid var(--sf-border);border-radius:15px;padding:14px 17px;}}
        .st-key-sf_home_hero{{
            background:linear-gradient(112deg, {'#2A294F,#1E334D' if dark else '#EEEDFF,#EDF5FF'});
            border:1px solid var(--sf-border);border-radius:15px;
            padding:12px 16px;margin:1px 0 3px;
        }}
        .st-key-sf_sidebar_collapse button p{{display:none !important;}}
        .st-key-sf_sidebar_collapse button{{padding:6px !important;min-height:36px !important;}}
        .sf-hero-title{{font-family:'Plus Jakarta Sans',sans-serif;font-size:1rem;font-weight:800;
            color:var(--sf-text);}}
        .sf-kpi{{background:var(--sf-surface);border:1px solid var(--sf-border);
            border-radius:14px;padding:12px 14px;min-height:94px;
            box-shadow:0 5px 17px var(--sf-shadow);}}
        .sf-kpi-top{{display:flex;align-items:center;justify-content:space-between;
            font-size:.75rem;color:var(--sf-muted);}}
        .sf-kpi-icon{{display:grid;place-items:center;width:27px;height:27px;border-radius:9px;
            color:var(--sf-accent);background:var(--sf-soft);font-size:15px;line-height:1;}}
        .sf-kpi-value{{font-size:1.48rem;font-weight:800;color:var(--sf-text);margin:3px 0 0;}}
        .sf-kpi-foot{{font-size:.69rem;color:var(--sf-muted);}}
        .sf-badge{{display:inline-block;padding:4px 8px;border-radius:7px;font-size:.69rem;font-weight:750;white-space:nowrap;}}
        .sf-success{{color:#187F50;background:#E5F7ED;}}.sf-warning{{color:#946115;background:#FFF1D8;}}
        .sf-danger{{color:#BA344C;background:#FFECEF;}}.sf-info{{color:#346ECC;background:#E9F1FF;}}
        .sf-neutral{{color:#626F89;background:#EFF1F6;}}
        .sf-line{{border:0;border-top:1px solid var(--sf-border);margin:9px 0;}}
        .sf-chat{{border-radius:13px;padding:10px 12px;margin:6px 0;max-width:96%;
            background:var(--sf-surface2);border:1px solid var(--sf-border);}}
        .sf-chat.customer{{background:var(--sf-soft);margin-left:auto;}}
        .sf-chat-meta{{font-size:.67rem;color:var(--sf-muted);margin:0 0 4px;font-weight:700;}}
        .sf-chat-body{{font-size:.82rem;color:var(--sf-text);white-space:pre-wrap;overflow-wrap:anywhere;}}
        .sf-note{{border-radius:11px;border:1px solid var(--sf-border);padding:10px 12px;
            background:var(--sf-surface2);font-size:.77rem;color:var(--sf-text);}}
        /* Section titles reserve their own breathing room inside the Markdown
           element; an external margin alone can collapse in Streamlit blocks. */
        .sf-dividerlabel{{display:block;font-family:'Plus Jakarta Sans',sans-serif;
            font-weight:750;font-size:.89rem;line-height:1.35;
            color:var(--sf-text);margin:11px 0 0;padding:0 0 12px;}}
        .sf-queue-heading{{margin-top:10px !important;padding-bottom:13px !important;}}
        /* Unbordered, alternating list rows on customer and support pages.
           Only keyed lists are affected: cards/forms/expanders retain structure. */
        [class*="st-key-sf_zebra_list_"] [data-testid="stVerticalBlock"]{{
            gap:0 !important;
        }}
        [class*="st-key-sf_zebra_row_0_"]{{
            background:{'#262F45' if dark else '#EFF2F9'} !important;
        }}
        [class*="st-key-sf_zebra_row_1_"]{{
            background:{'#1B2438' if dark else '#FFFFFF'} !important;
        }}
        [class*="st-key-sf_zebra_row_0_"], [class*="st-key-sf_zebra_row_1_"]{{
            border:0 !important;border-radius:0 !important;box-shadow:none !important;
            padding:9px 13px !important;margin:0 !important;min-width:0 !important;
        }}
        [class*="st-key-sf_zebra_row_"] [data-testid="stVerticalBlock"]{{
            gap:1px !important;
        }}
        [class*="st-key-sf_zebra_row_"] button[kind="secondary"]{{
            border:0 !important;background:transparent !important;
            color:var(--sf-accent) !important;box-shadow:none !important;
            min-height:32px !important;
        }}
        [class*="st-key-sf_zebra_row_"] button[kind="secondary"]:hover{{
            background:var(--sf-soft) !important;
        }}
        .sf-snapshot{{background:var(--sf-surface2);border:0;border-radius:12px;
            padding:13px 15px 14px;margin:1px 0 12px;box-shadow:none;}}
        .sf-snapshot-title{{font-family:'Plus Jakarta Sans',sans-serif;font-weight:800;
            font-size:.86rem;color:var(--sf-text);}}
        .sf-snapshot-detail{{color:var(--sf-muted);font-size:.77rem;margin-top:5px;}}
        .sf-snapshot-meta{{font-size:.71rem;color:var(--sf-muted);margin-top:11px;
            line-height:1.5;}}
        .sf-snapshot-alert{{font-size:.71rem;color:var(--sf-text);margin-top:5px;}}
        .sf-person{{font-size:.82rem;color:var(--sf-text);font-weight:700;}}
        .sf-login-blurb{{padding:13px 0;}}
        .sf-login-blurb strong{{font-family:'Plus Jakarta Sans',sans-serif;font-size:1.9rem;
            font-weight:800;letter-spacing:-.06em;line-height:1.16;display:block;color:var(--sf-text);}}
        .sf-login-blurb p{{font-size:.89rem;color:var(--sf-muted);margin-top:9px;max-width:355px;}}
        .sf-ticket-row{{display:flex;align-items:center;justify-content:space-between;gap:10px;
            background:var(--sf-surface);border:1px solid var(--sf-border);border-radius:11px;
            padding:8px 12px;margin-bottom:6px;min-width:0;}}
        /* All zebra rows use one HTML text block with explicit two-line layout.
           Streamlit markdown + caption as separate zero-gap elements overlapped
           at narrow widths. A single block fixes the title/subtitle baseline. */
        .sf-row-label{{display:flex;flex-direction:column;justify-content:center;
            gap:5px;min-height:43px;min-width:0;padding:2px 0;}}
        .sf-row-primary{{display:flex;align-items:center;flex-wrap:wrap;gap:7px;
            min-width:0;line-height:1.40;}}
        .sf-row-heading{{font-family:'Plus Jakarta Sans','Inter',sans-serif;
            font-size:.85rem;font-weight:750;color:var(--sf-text);
            line-height:1.42;overflow-wrap:anywhere;}}
        .sf-row-secondary{{display:block;font-size:.70rem;line-height:1.45;
            color:var(--sf-muted);margin:0;overflow-wrap:anywhere;}}
        .sf-row-body{{display:block;margin-top:6px;color:var(--sf-text);
            font-size:.79rem;line-height:1.5;overflow-wrap:anywhere;}}
        .sf-ticket-row-title{{font-weight:700;font-size:.82rem;color:var(--sf-text);
            overflow-wrap:anywhere;}}
        .sf-ticket-row-meta{{font-size:.68rem;color:var(--sf-muted);margin-top:3px;}}
        /* Stage 1.2: one continuous zebra list instead of separated ticket cards. */
        [class*="st-key-sf_queue_list_"] [data-testid="stVerticalBlock"]{{
            gap:0 !important;
        }}
        [class*="st-key-sf_queue_row_0_"]{{
            background:{'#242E44' if dark else '#F0F2F8'} !important;
        }}
        [class*="st-key-sf_queue_row_1_"]{{
            background:{'#1B2438' if dark else '#FFFFFF'} !important;
        }}
        [class*="st-key-sf_queue_row_0_"], [class*="st-key-sf_queue_row_1_"]{{
            padding:9px 13px !important;margin:0 !important;
            border:0 !important;border-radius:0 !important;
            box-shadow:none !important;min-width:0 !important;
        }}
        [class*="st-key-sf_queue_row_"] [data-testid="stVerticalBlock"]{{
            gap:0 !important;
        }}
        .sf-queue-title{{font-family:'Plus Jakarta Sans','Inter',sans-serif;
            font-size:.82rem;font-weight:750;line-height:1.35;color:var(--sf-text);
            overflow-wrap:anywhere;}}
        .sf-queue-meta{{font-size:.68rem;line-height:1.35;
            color:var(--sf-muted);margin-top:3px;}}
        .sf-queue-flags{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;}}
        .sf-queue-sla{{display:flex;flex-direction:column;align-items:flex-start;gap:1px;}}
        /* Queue headings use the common section spacing above. */
        [class*="st-key-sf_queue_open_"] button{{
            background:transparent !important;border:0 !important;
            color:var(--sf-accent) !important;box-shadow:none !important;
            min-height:34px !important;font-size:.78rem !important;
            padding:5px 6px !important;white-space:nowrap !important;
        }}
        [class*="st-key-sf_queue_open_"] button:hover{{
            background:var(--sf-soft) !important;color:var(--sf-accent) !important;
        }}
        [class*="st-key-sf_queue_open_"] button:focus-visible{{
            outline:2px solid var(--sf-accent) !important;outline-offset:1px;
        }}
        .sf-progress{{display:flex;align-items:center;gap:6px;justify-content:space-between;
            margin:10px 0 3px;}}
        .sf-step{{display:flex;flex-direction:column;align-items:center;justify-content:center;
            flex:1;gap:5px;text-align:center;min-width:0;color:var(--sf-muted);font-size:.63rem;}}
        .sf-step-circle{{display:grid;place-items:center;width:28px;height:28px;
            border-radius:50%;background:var(--sf-surface2);border:1px solid var(--sf-border);
            font-size:.77rem;font-weight:750;}}
        .sf-step.done .sf-step-circle{{background:#E1F5EB;color:#168052;border-color:#C6EAD7;}}
        .sf-step.current .sf-step-circle{{background:#625CF5;color:white;border-color:#625CF5;}}
        {compact_css}
        {dark_css}
        @media (min-width:901px) {{
            [data-testid="stSidebarCollapseButton"]{{display:none !important;}}
        }}
        @media(max-width:960px){{
            [data-testid="stMainBlockContainer"],.block-container{{
                padding-left:1rem !important;padding-right:1rem !important;
            }}
        }}
        @media(max-width:800px){{
            [data-testid="stMainBlockContainer"],.block-container{{
                padding:2.3rem .75rem .9rem !important;
            }}
            [data-testid="stSidebar"]{{width:{'78px' if compact else 'min(80vw,252px)'} !important;
                min-width:{'78px' if compact else 'min(80vw,252px)'} !important;
                max-width:{'78px' if compact else 'min(80vw,252px)'} !important;}}
            .sf-title{{font-size:1.32rem;}}.sf-hero{{padding:12px;}}
            .sf-kpi{{min-height:84px;}}
        }}
    </style>''',unsafe_allow_html=True)


def brand(compact: bool=False):
    if compact:
        st.markdown('<div class="sf-logo" title="SupportFlow AI" style="margin:1px auto 8px">✦</div>',unsafe_allow_html=True)
    else:
        st.markdown('<div class="sf-brand"><span class="sf-logo">✦</span>'
            '<span>SupportFlow <span class="sf-ai">AI</span></span></div>',unsafe_allow_html=True)


def header(title: str, subtitle: str='', eyebrow: str='WORKSPACE'):
    st.markdown(f'<div class="sf-eyebrow">{safe(eyebrow)}</div><div class="sf-title">{safe(title)}</div>'+(
        f'<div class="sf-sub">{safe(subtitle)}</div>' if subtitle else ''),unsafe_allow_html=True)


def card(title: str, body: str, *, eyebrow: str='', badge_text: str='', tone: str='neutral'):
    tag = badge(badge_text,tone) if badge_text else ''
    st.markdown('<div class="sf-card">'+(f'<div class="sf-small">{safe(eyebrow)}</div>' if eyebrow else '')+
        f'<div class="sf-card-title">{safe(title)} &nbsp;{tag}</div><div class="sf-muted">{safe(body)}</div></div>',unsafe_allow_html=True)


def badge(text: str, tone: str='neutral') -> str:
    return f'<span class="sf-badge sf-{tone}">{safe(text)}</span>'


def status_tone(status: str) -> str:
    return {'RESOLVED':'success','CLOSED':'success','COMPLETED':'success','APPROVED':'success',
            'AWAITING_APPROVAL':'warning','ACTION_PENDING':'warning','DELIVERY_DELAYED':'warning',
            'PENDING':'warning','PROCESSING':'info','P1':'danger','P2':'warning',
            'IN_REVIEW':'info','WAITING_CUSTOMER':'info','REOPENED':'warning','NEW':'info',
            'REJECTED':'danger'}.get(status,'neutral')


def kpi(title: str,value: str,foot: str,icon: str='◈'):
    st.markdown(f'<div class="sf-kpi"><div class="sf-kpi-top"><span>{safe(title)}</span>'
        f'<span class="sf-kpi-icon">{safe(icon)}</span></div>'
        f'<div class="sf-kpi-value">{safe(value)}</div><div class="sf-kpi-foot">{safe(foot)}</div></div>',
        unsafe_allow_html=True)


def page_note(text: str):
    st.markdown(f'<div class="sf-note">{safe(text)}</div>',unsafe_allow_html=True)


def chat_bubble(sender: str,body: str,when: str,customer: bool=False):
    cls=' customer' if customer else ''
    st.markdown(f'<div class="sf-chat{cls}"><div class="sf-chat-meta">{safe(sender)} · {safe(when)}</div>'+
        f'<div class="sf-chat-body">{safe(body)}</div></div>',unsafe_allow_html=True)


def go(name: str):
    pages=st.session_state.get('page_lookup',{})
    if name not in pages:
        st.error('This page is not available to the current role.')
        return
    st.switch_page(pages[name])


def goto_ticket(ticket_id: str):
    st.session_state.selected_ticket_id=ticket_id
    go('Ticket conversation')


def goto_customer(customer_id: int):
    st.session_state.selected_customer_id=customer_id
    go('Customer 360°')


def list_item_text(title: str, meta: str, badge_html: str = '', *, body: str = '') -> str:
    """A single aligned title/subtitle block for dense, accessible Streamlit lists.

    Avoids independent st.markdown + st.caption elements whose baseline can
    overlap when gap=None is applied to Streamlit container layouts.
    All user/data-provided text is HTML-escaped. ``badge_html`` is generated
    using our own badge() helper only.
    """
    return (
        '<div class="sf-row-label">'
        '<div class="sf-row-primary"><span class="sf-row-heading">' + safe(title)
        + '</span>' + badge_html + '</div>'
        + '<div class="sf-row-secondary">' + safe(meta) + '</div>'
        + ('<div class="sf-row-body">' + safe(body) + '</div>' if body else '')
        + '</div>'
    )
