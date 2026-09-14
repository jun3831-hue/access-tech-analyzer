# -*- coding: utf-8 -*-
"""
===============================================================================
Script Name   : app_web.py
Location      : 5_DM AGENT/app_web.py
Description   : OPTis DM AI Web Viewer - Lightweight Standalone Dashboard
                - Zero-data deployment optimized for Streamlit Cloud & GitHub
                - Auto-creates runtime cache directories (No empty folder commit needed)
                - Multi-Source Session Loading:
                    1) Local output sessions
                    2) Direct ZIP / HTML / Excel Upload via Browser
                    3) Remote SFTP Server Sync
                - 100% Native 2D GIS Interactive Map Embedding
                - L3 BS Parameter Audit Matrix & Diff Viewer
                - Multi-Metric Time-Series Plotly Visualizer
                - Master Excel Download & Diagnosis Report Viewer
===============================================================================
"""

import os
import sys
import glob
import json
import re
import zipfile
import shutil
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

# =============================================================================
# Streamlit Page Configuration
# =============================================================================
st.set_page_config(
    page_title="DM Analyzer v0.1",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Full-Width Theme with Safe Margins
st.markdown("""
<style>
    /* Hide Streamlit default Deploy button, menu, footer */
    .stDeployButton { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    /* Main container padding - 3.2rem safe margin */
    .block-container {
        padding-top: 3.2rem !important;
        padding-bottom: 0px !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        max-width: 100% !important;
    }

    /* Map iframe styling - fits viewport cleanly */
    iframe {
        width: 100% !important;
        height: calc(100vh - 4.2rem) !important;
        border: none !important;
        border-radius: 8px;
    }

    /* Sidebar width & compact button styling */
    section[data-testid="stSidebar"] {
        width: 300px;
    }
    section[data-testid="stSidebar"] button {
        min-height: 28px !important;
        height: 28px !important;
        font-size: 11px !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* Compact Session Expander & Vertical spacing */
    div[data-testid="stExpander"] {
        border-radius: 6px !important;
        margin-bottom: 4px !important;
    }
    div[data-testid="stExpander"] details summary {
        padding: 4px 8px !important;
    }
    div[data-testid="stExpander"] details div[data-testid="stVerticalBlock"] {
        gap: 2px !important;
        padding: 4px 6px !important;
    }

    /* Modal / Dialog styling */
    div[data-modal-container="true"], div[role="dialog"] {
        background-color: #0f172a !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Path & Discovery Utilities (Runtime Auto-Creation)
# =============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DM_OUTPUT_DIR = os.path.join(CURRENT_DIR, "output")
LOCAL_SESSIONS_DIR = os.path.join(CURRENT_DIR, "cache", "sessions")

# Auto-create runtime directories if missing (Zero git footprint)
os.makedirs(LOCAL_SESSIONS_DIR, exist_ok=True)
os.makedirs(DM_OUTPUT_DIR, exist_ok=True)

DEFAULT_SFTP_CONFIG = {
    "host": "113.217.230.27",
    "port": 10022,
    "user": "skt2",
    "pass": "setup2",
    "remote_dir": "/Personal/전광용/DM Agent/sessions"
}

if HAS_PARAMIKO:
    try:
        import paramiko.util
        _orig_paramiko_u = paramiko.util.u
        def _safe_paramiko_u(s, encoding="utf8"):
            if isinstance(s, bytes):
                try:
                    return s.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        return s.decode("cp949")
                    except UnicodeDecodeError:
                        return s.decode("latin1", errors="replace")
            return _orig_paramiko_u(s, encoding)
        paramiko.util.u = _safe_paramiko_u
        if hasattr(paramiko, "message"):
            paramiko.message.u = _safe_paramiko_u
    except Exception:
        pass


def discover_sftp_sessions(sftp, base_dir: str, max_depth: int = 3) -> dict:
    """
    Recursively scans SFTP directories up to max_depth to find folders containing
    _Map.html or _Master.xlsx artifacts.
    Returns: { "path_key": { "user_id": ..., "date": ..., "session_name": ..., "remote_dir": ..., "files": [...] } }
    """
    import stat
    found = {}

    def _walk(curr_path: str, depth: int):
        if depth > max_depth:
            return
        try:
            items = sftp.listdir_attr(curr_path)
        except Exception:
            return

        subdirs = []
        session_files = []
        for it in items:
            if stat.S_ISDIR(it.st_mode):
                subdirs.append(it.filename)
            else:
                fn_lower = it.filename.lower()
                if fn_lower.endswith('.html') or fn_lower.endswith('.xlsx') or fn_lower.endswith('.txt') or fn_lower.endswith('.json'):
                    session_files.append(it.filename)

        has_map = any(f.lower().endswith('.html') for f in session_files)
        has_master = any(f.lower().endswith('.xlsx') for f in session_files)

        if has_map or has_master:
            sess_name = os.path.basename(curr_path.rstrip('/'))
            rel_parts = curr_path.replace(base_dir, '').strip('/').split('/')
            registrant = rel_parts[-3] if len(rel_parts) >= 3 else "-"
            raw_up_date = rel_parts[-2] if len(rel_parts) >= 2 else "-"

            # Standardize upload_date to YYYY-MM-DD
            if len(raw_up_date) == 6 and raw_up_date.isdigit():
                upload_date = f"20{raw_up_date[:2]}-{raw_up_date[2:4]}-{raw_up_date[4:6]}"
            else:
                m_up = re.search(r'(\d{4}[-/\.]\d{2}[-/\.]\d{2})', raw_up_date)
                upload_date = m_up.group(1).replace('.', '-').replace('/', '-') if m_up else raw_up_date

            measured_date = "-"
            meta_fn = next((f for f in session_files if f.lower().endswith('_meta.json')), None)
            if meta_fn:
                try:
                    with sftp.open(f"{curr_path.rstrip('/')}/{meta_fn}", 'r') as f_meta:
                        meta_obj = json.load(f_meta)
                        m_raw = meta_obj.get("measured_date") or meta_obj.get("measurement_date")
                        if m_raw and str(m_raw) != "-":
                            m_match = re.search(r'(\d{4}[-/\.]\d{2}[-/\.]\d{2})', str(m_raw))
                            measured_date = m_match.group(1).replace('.', '-').replace('/', '-') if m_match else str(m_raw)[:10]
                except Exception:
                    pass

            # Fallback 1: Extract date_str directly from _Map.html if meta has no date
            if measured_date == "-":
                map_fn = next((f for f in session_files if f.lower().endswith('.html')), None)
                if map_fn:
                    try:
                        with sftp.open(f"{curr_path.rstrip('/')}/{map_fn}", 'r') as f_map:
                            chunk = f_map.read(65536).decode('utf-8', errors='ignore')
                            m_d = re.search(r'date_str["\']?\s*:\s*["\']([^"\']+)["\']', chunk)
                            if not m_d:
                                m_d = re.search(r'측정 일시:\s*<b>(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})', chunk)
                            if m_d:
                                measured_date = m_d.group(1).replace('.', '-').replace('/', '-')
                    except Exception:
                        pass

            # Fallback 2: If still unextracted, use upload_date
            if measured_date == "-":
                measured_date = upload_date

            found[curr_path] = {
                "user_id": registrant,
                "upload_date": upload_date,
                "measured_date": measured_date,
                "session_name": sess_name,
                "remote_dir": curr_path,
                "files": session_files
            }

        for d in subdirs:
            next_p = f"{curr_path.rstrip('/')}/{d}"
            _walk(next_p, depth + 1)

    _walk(base_dir, 0)
    return found


@st.dialog("🌐 FTP 세션 선택", width="large")
def show_sftp_session_dialog():
    discovered = st.session_state.get("sftp_discovered_sessions", {})
    if not discovered:
        st.warning("원격 FTP 경로에서 탐색된 세션이 없습니다.")
        if st.button("닫기", use_container_width=True):
            st.session_state["show_sftp_dialog"] = False
            st.rerun()
        return

    st.markdown("##### 📁 다운로드할 세션을 선택하세요 (복수 선택 가능)")

    # 4-Column Search Filters
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        f_user = st.text_input("🔍 등록자 검색", key="dlg_filter_user", placeholder="예: skt1110018")
    with col_f2:
        f_up_date = st.text_input("🔍 업로드일", key="dlg_filter_up_date", placeholder="예: 2026-09-14")
    with col_f3:
        f_meas_date = st.text_input("🔍 측정일", key="dlg_filter_meas_date", placeholder="예: 2025-07-15")
    with col_f4:
        f_name = st.text_input("🔍 세션명 검색", key="dlg_filter_name", placeholder="예: 충주")

    rows = []
    filtered_path_keys = []
    for k, item in discovered.items():
        u = str(item.get("user_id", "-"))
        up_d = str(item.get("upload_date", "-"))
        m_d = str(item.get("measured_date", "-"))
        s = str(item.get("session_name", "-"))

        if f_user and f_user.strip().lower() not in u.lower():
            continue
        if f_up_date and f_up_date.strip().lower() not in up_d.lower():
            continue
        if f_meas_date and f_meas_date.strip().lower() not in m_d.lower():
            continue
        if f_name and f_name.strip().lower() not in s.lower():
            continue

        rows.append({
            "선택": False,
            "등록자": u,
            "업로드 날짜": up_d,
            "측정 날짜": m_d,
            "세션명": s
        })
        filtered_path_keys.append(k)

    st.caption(f"조회 결과: **{len(rows)}**개 / 전체 {len(discovered)}개")

    if not rows:
        st.info("ℹ️ 검색 조건과 일치하는 세션이 없습니다.")
        if st.button("닫기", use_container_width=True, key="btn_modal_close_empty"):
            st.session_state["show_sftp_dialog"] = False
            st.rerun()
        return

    df = pd.DataFrame(rows)
    df["_path_key"] = filtered_path_keys

    # 사번(오름차순) -> 업로드일(내림차순/최신순) -> 측정일(내림차순/최신순) -> 세션명(오름차순/가나다순)
    df = df.sort_values(
        by=["등록자", "업로드 날짜", "측정 날짜", "세션명"],
        ascending=[True, False, False, True]
    ).reset_index(drop=True)

    filtered_path_keys = df["_path_key"].tolist()
    df = df.drop(columns=["_path_key"])

    edited_df = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", default=False),
            "등록자": st.column_config.TextColumn("등록자", disabled=True),
            "업로드 날짜": st.column_config.TextColumn("업로드 날짜", disabled=True),
            "측정 날짜": st.column_config.TextColumn("측정 날짜", disabled=True),
            "세션명": st.column_config.TextColumn("세션명", disabled=True),
        },
        height=min(400, 50 + len(rows) * 35),
        key="sftp_session_data_editor"
    )

    selected_indices = edited_df[edited_df["선택"] == True].index.tolist()
    st.markdown("---")
    col_dl, col_close = st.columns([0.75, 0.25])

    with col_dl:
        btn_label = f"📥 선택한 세션 불러오기 ({len(selected_indices)}개)" if selected_indices else "📥 세션을 선택하세요"
        if st.button(btn_label, type="primary", disabled=(len(selected_indices) == 0), use_container_width=True, key="btn_modal_dl"):
            with st.spinner(f"선택한 {len(selected_indices)}개 세션 다운로드 중..."):
                try:
                    t = paramiko.Transport((DEFAULT_SFTP_CONFIG["host"], int(DEFAULT_SFTP_CONFIG["port"])))
                    t.connect(username=DEFAULT_SFTP_CONFIG["user"], password=DEFAULT_SFTP_CONFIG["pass"])
                    sftp = paramiko.SFTPClient.from_transport(t)

                    last_sname = None
                    for idx in selected_indices:
                        pk = filtered_path_keys[idx]
                        target_info = discovered[pk]
                        s_name = target_info["session_name"]
                        local_sess_dir = os.path.join(LOCAL_SESSIONS_DIR, s_name)
                        os.makedirs(local_sess_dir, exist_ok=True)

                        for fn in target_info["files"]:
                            rem_fp = f"{target_info['remote_dir'].rstrip('/')}/{fn}"
                            loc_fp = os.path.join(local_sess_dir, fn)
                            sftp.get(rem_fp, loc_fp)

                        st.session_state["loaded_sessions"][s_name] = local_sess_dir
                        last_sname = s_name

                    sftp.close()
                    t.close()

                    if last_sname:
                        st.session_state["selected_session_key"] = last_sname
                    st.session_state["show_sftp_dialog"] = False
                    st.rerun()
                except Exception as ex:
                    st.error(f"다운로드 실패: {ex}")

    with col_close:
        if st.button("닫기", use_container_width=True, key="btn_modal_close"):
            st.session_state["show_sftp_dialog"] = False
            st.rerun()


def discover_local_sessions():
    """
    Scans candidate directories and returns structured dictionary of sessions.
    Format: { "date_str": { "session_name": "/path/to/folder", ... }, ... }
    """
    sessions = {}
    search_roots = [DM_OUTPUT_DIR, LOCAL_SESSIONS_DIR]

    for root in search_roots:
        if not os.path.exists(root):
            continue

        # Pattern 1: root/{date}/{session_name}/ (Standard DM AGENT structure)
        for date_dir in sorted(os.listdir(root), reverse=True):
            dp = os.path.join(root, date_dir)
            if not os.path.isdir(dp):
                continue

            for sess_dir in sorted(os.listdir(dp)):
                sp = os.path.join(dp, sess_dir)
                if not os.path.isdir(sp):
                    continue

                files = os.listdir(sp)
                has_map = any(f.endswith('.html') for f in files)
                has_excel = any(f.endswith('.xlsx') for f in files)

                if has_map or has_excel:
                    if date_dir not in sessions:
                        sessions[date_dir] = {}
                    sessions[date_dir][sess_dir] = sp

        # Pattern 2: Direct session folder root/{session_name}/
        for item in os.listdir(root):
            sp = os.path.join(root, item)
            if os.path.isdir(sp):
                files = os.listdir(sp)
                has_map = any(f.endswith('.html') for f in files)
                has_excel = any(f.endswith('.xlsx') for f in files)
                if has_map or has_excel:
                    m_date = re.match(r'^(\d{6})', item)
                    date_key = m_date.group(1) if m_date else "기타"
                    if date_key not in sessions:
                        sessions[date_key] = {}
                    sessions[date_key][item] = sp

    return sessions


def load_session_artifacts(session_dir: str):
    """
    Loads session files and returns content / file paths.
    """
    artifacts = {
        "dir": session_dir,
        "map_file": None,
        "map_html": None,
        "excel_file": None,
        "report_file": None,
        "report_txt": None,
        "meta_file": None,
        "meta_data": None
    }

    if not os.path.exists(session_dir):
        return artifacts

    for f in os.listdir(session_dir):
        fp = os.path.join(session_dir, f)
        if not os.path.isfile(fp):
            continue

        if f.lower().endswith('.html') and ('map' in f.lower() or not artifacts["map_file"]):
            artifacts["map_file"] = fp
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as fm:
                    artifacts["map_html"] = fm.read()
            except Exception:
                pass

        elif f.lower().endswith('.xlsx') and ('master' in f.lower() or not artifacts["excel_file"]):
            artifacts["excel_file"] = fp

        elif f.lower().endswith('.txt') and ('report' in f.lower() or not artifacts["report_file"]):
            artifacts["report_file"] = fp
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as fr:
                    artifacts["report_txt"] = fr.read()
            except Exception:
                pass

        elif f.lower().endswith('.json') and 'meta' in f.lower():
            artifacts["meta_file"] = fp
            try:
                with open(fp, 'r', encoding='utf-8') as fjs:
                    artifacts["meta_data"] = json.load(fjs)
            except Exception:
                pass

    return artifacts


def extract_embedded_data_from_map(html_str: str):
    """
    Extracts embedded JSON data (allPortsData, paramStructData, paramScalarDiffData) from Map HTML.
    """
    extracted = {
        "ports_data": {},
        "param_struct": [],
        "param_scalar": [],
        "network_mode": "LTE"
    }
    if not html_str:
        return extracted

    try:
        # 1. allPortsData
        m_ports = re.search(r'const allPortsData\s*=\s*(\{.*?\});\s*const', html_str, re.DOTALL)
        if m_ports:
            extracted["ports_data"] = json.loads(m_ports.group(1))

        # 2. paramStructData
        m_struct = re.search(r'const paramStructData\s*=\s*(\[.*?\]);\s*const', html_str, re.DOTALL)
        if m_struct:
            extracted["param_struct"] = json.loads(m_struct.group(1))

        # 3. paramScalarDiffData
        m_scalar = re.search(r'const paramScalarDiffData\s*=\s*(\[.*?\]);\s*const', html_str, re.DOTALL)
        if m_scalar:
            extracted["param_scalar"] = json.loads(m_scalar.group(1))

        # 4. networkMode
        m_net = re.search(r'const networkMode\s*=\s*"([^"]+)";', html_str)
        if m_net:
            extracted["network_mode"] = m_net.group(1)

    except Exception:
        pass

    return extracted


# Initialize loaded sessions in session_state if not present
if "loaded_sessions" not in st.session_state:
    st.session_state["loaded_sessions"] = {}
    if os.path.exists(LOCAL_SESSIONS_DIR):
        for item in sorted(os.listdir(LOCAL_SESSIONS_DIR)):
            sp = os.path.join(LOCAL_SESSIONS_DIR, item)
            if os.path.isdir(sp):
                files = os.listdir(sp)
                if any(f.endswith('.html') or f.endswith('.xlsx') for f in files):
                    st.session_state["loaded_sessions"][item] = sp
    if os.path.exists(DM_OUTPUT_DIR):
        for d_dir in sorted(os.listdir(DM_OUTPUT_DIR), reverse=True):
            dp = os.path.join(DM_OUTPUT_DIR, d_dir)
            if os.path.isdir(dp):
                for s_dir in sorted(os.listdir(dp)):
                    sp = os.path.join(dp, s_dir)
                    if os.path.isdir(sp):
                        files = os.listdir(sp)
                        if any(f.endswith('.html') or f.endswith('.xlsx') for f in files):
                            st.session_state["loaded_sessions"][s_dir] = sp

# =============================================================================
# Sidebar: Direct SFTP Sync & Session File Downloader
# =============================================================================
with st.sidebar:
    st.markdown("### 📡 DM Analyzer v0.1")

    # 1. Single Primary Button: Query Remote FTP Sessions
    if st.button("🔄 FTP 세션 목록 조회", use_container_width=True, type="primary"):
        if not HAS_PARAMIKO:
            st.error("paramiko 모듈이 설치되어 있지 않습니다.")
        else:
            with st.spinner("FTP 세션 목록 조회 중..."):
                try:
                    t = paramiko.Transport((DEFAULT_SFTP_CONFIG["host"], int(DEFAULT_SFTP_CONFIG["port"])))
                    t.connect(username=DEFAULT_SFTP_CONFIG["user"], password=DEFAULT_SFTP_CONFIG["pass"])
                    sftp = paramiko.SFTPClient.from_transport(t)
                    discovered = discover_sftp_sessions(sftp, DEFAULT_SFTP_CONFIG["remote_dir"])
                    st.session_state["sftp_discovered_sessions"] = discovered
                    sftp.close()
                    t.close()

                    if discovered:
                        st.session_state["show_sftp_dialog"] = True
                        st.rerun()
                    else:
                        st.warning("원격 경로에서 세션을 찾을 수 없습니다.")
                except Exception as ex:
                    st.error(f"SFTP 접속 실패: {ex}")

    # Modal Dialog Trigger
    if st.session_state.get("show_sftp_dialog", False):
        show_sftp_session_dialog()

    # 3. Loaded Sessions (Sidebar Session Manager with 3-Artifact Download)
    loaded = st.session_state.get("loaded_sessions", {})
    if loaded:
        st.markdown("---")
        col_lh1, col_lh2 = st.columns([0.72, 0.28])
        with col_lh1:
            st.markdown("##### 📁 로컬 세션 보관함")
        with col_lh2:
            if st.button("비우기", key="btn_clear_loaded", use_container_width=True):
                st.session_state["loaded_sessions"] = {}
                st.session_state["selected_session_key"] = None
                st.rerun()

        loaded_keys = list(loaded.keys())
        current_k = st.session_state.get("selected_session_key")
        if current_k not in loaded_keys:
            current_k = loaded_keys[0]
            st.session_state["selected_session_key"] = current_k

        for sk in loaded_keys:
            safe_display_name = str(sk).replace('~', r'\~')
            is_cur = (sk == current_k)
            expander_title = f"{'🟢' if is_cur else '⚪'} {safe_display_name}"

            col_exp, col_del = st.columns([0.84, 0.16])
            with col_exp:
                with st.expander(expander_title, expanded=is_cur):
                    if not is_cur:
                        if st.button("🗺️ 이 세션 보기", key=f"btn_v_{sk}", use_container_width=True):
                            st.session_state["selected_session_key"] = sk
                            st.rerun()

                    sess_path = loaded[sk]
                    s_art = load_session_artifacts(sess_path)

                    # 3 Artifact Download Buttons (Meta.json excluded as requested)
                    if s_art["excel_file"] and os.path.exists(s_art["excel_file"]):
                        with open(s_art["excel_file"], "rb") as f_ex:
                            st.download_button(
                                label="📊 통합 마스터 엑셀 (.xlsx)",
                                data=f_ex.read(),
                                file_name=os.path.basename(s_art["excel_file"]),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_ex_{sk}",
                                use_container_width=True
                            )

                    if s_art["map_file"] and os.path.exists(s_art["map_file"]):
                        with open(s_art["map_file"], "rb") as f_mp:
                            st.download_button(
                                label="🗺️ 2D 대화형 맵 (.html)",
                                data=f_mp.read(),
                                file_name=os.path.basename(s_art["map_file"]),
                                mime="text/html",
                                key=f"dl_mp_{sk}",
                                use_container_width=True
                            )

                    if s_art["report_file"] and os.path.exists(s_art["report_file"]):
                        with open(s_art["report_file"], "rb") as f_rp:
                            st.download_button(
                                label="📋 종합 진단 리포트 (.txt)",
                                data=f_rp.read(),
                                file_name=os.path.basename(s_art["report_file"]),
                                mime="text/plain",
                                key=f"dl_rp_{sk}",
                                use_container_width=True
                            )

            with col_del:
                if st.button("✕", key=f"del_{sk}", use_container_width=True):
                    del st.session_state["loaded_sessions"][sk]
                    if st.session_state.get("selected_session_key") == sk:
                        rem_k = list(st.session_state["loaded_sessions"].keys())
                        st.session_state["selected_session_key"] = rem_k[0] if rem_k else None
                    st.rerun()

    st.markdown("---")
    if st.button("🔄 화면 새로고침", use_container_width=True):
        st.rerun()

# =============================================================================
# Main Content View
# =============================================================================
active_key = st.session_state.get("selected_session_key")
loaded_sessions = st.session_state.get("loaded_sessions", {})

if not active_key or active_key not in loaded_sessions or not os.path.exists(loaded_sessions[active_key]):
    st.info("👈 좌측 사이드바에서 [🔄 FTP 세션 목록 조회]를 눌러 분석할 세션을 불러와 주세요.")
    st.stop()

selected_session_path = loaded_sessions[active_key]
selected_session_name = active_key

# Load Artifacts
art = load_session_artifacts(selected_session_path)

if art["map_html"]:
    components.html(
        art["map_html"],
        height=940,
        scrolling=False
    )
else:
    st.warning("⚠️ 해당 세션에 Map HTML 산출물이 존재하지 않습니다.")
