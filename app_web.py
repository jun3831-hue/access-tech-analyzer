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
    page_title="DM AI Web Analyzer",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Theme
st.markdown("""
<style>
    .main .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 100%;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 18px;
        font-weight: 700;
        font-size: 14px;
        border-radius: 6px;
    }
    .metric-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    .badge-blue {
        background: #2563eb;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: bold;
    }
    .badge-amber {
        background: #f59e0b;
        color: black;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: bold;
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


# =============================================================================
# Sidebar: Session Selection & Ingestion
# =============================================================================
with st.sidebar:
    st.markdown("### 📡 DM AI Web Analyzer")
    st.caption("초경량 세션 직결 대시보드 v1.0")

    data_source = st.radio("데이터 소스", ["📤 파일 직접 업로드", "🌐 원격 SFTP 서버"], index=0)

    selected_session_path = None
    selected_session_name = None

    if data_source == "📤 파일 직접 업로드":
        st.markdown("**세션 산출물 업로드 (ZIP 또는 개별 파일)**")
        uploaded_file = st.file_uploader("세션 ZIP 파일 업로드", type=["zip", "html", "xlsx"])
        if uploaded_file is not None:
            fname = uploaded_file.name
            base_sname = os.path.splitext(fname)[0].replace("_Map", "").replace("_Master", "")
            target_sess_dir = os.path.join(LOCAL_SESSIONS_DIR, base_sname)
            os.makedirs(target_sess_dir, exist_ok=True)

            if fname.lower().endswith('.zip'):
                zip_path = os.path.join(target_sess_dir, fname)
                with open(zip_path, "wb") as fz:
                    fz.write(uploaded_file.getbuffer())
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(target_sess_dir)
                    st.success(f"'{fname}' 압축 해제 완료!")
                except Exception as ex:
                    st.error(f"ZIP 해제 오류: {ex}")
            else:
                saved_path = os.path.join(target_sess_dir, fname)
                with open(saved_path, "wb") as f_save:
                    f_save.write(uploaded_file.getbuffer())
                st.success(f"'{fname}' 파일 저장 완료!")

            selected_session_path = target_sess_dir
            selected_session_name = base_sname

    else:
        st.markdown("**SFTP 접속 설정**")
        sftp_host = st.text_input("서버 IP", value=DEFAULT_SFTP_CONFIG["host"])
        sftp_port = st.number_input("포트", value=DEFAULT_SFTP_CONFIG["port"], step=1)
        sftp_user = st.text_input("계정 ID", value=DEFAULT_SFTP_CONFIG["user"])
        sftp_pass = st.text_input("비밀번호", value=DEFAULT_SFTP_CONFIG["pass"], type="password")
        sftp_base = st.text_input("원격 경로", value=DEFAULT_SFTP_CONFIG["remote_dir"])

        if st.button("🔄 원격 세션 목록 조회", use_container_width=True):
            if not HAS_PARAMIKO:
                st.error("paramiko 모듈이 설치되어 있지 않습니다.")
            else:
                try:
                    t = paramiko.Transport((sftp_host, int(sftp_port)))
                    t.connect(username=sftp_user, password=sftp_pass)
                    sftp = paramiko.SFTPClient.from_transport(t)
                    remote_items = sftp.listdir(sftp_base)
                    st.success(f"원격 항목 {len(remote_items)}개 발견됨")
                    sftp.close()
                    t.close()
                except Exception as ex:
                    st.error(f"SFTP 접속 실패: {ex}")

    st.markdown("---")
    if st.button("🔄 화면 새로고침", use_container_width=True):
        st.rerun()


# =============================================================================
# Main Content View
# =============================================================================
if not selected_session_path:
    st.info("👈 좌측 사이드바에서 분석할 세션을 선택하거나 산출물 파일을 업로드해 주세요.")
    st.stop()

# Load Artifacts
art = load_session_artifacts(selected_session_path)
extracted_meta = extract_embedded_data_from_map(art["map_html"])

# Top Status Header
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f"## 📁 {selected_session_name}")
    st.caption(f"경로: `{selected_session_path}` | 망 모드: `{extracted_meta.get('network_mode', 'LTE')}`")

with col_h2:
    st.markdown("<div style='text-align: right; padding-top: 10px;'>", unsafe_allow_html=True)
    if art["excel_file"] and os.path.exists(art["excel_file"]):
        with open(art["excel_file"], "rb") as fe:
            st.download_button(
                label="📥 Master Excel 다운로드",
                data=fe.read(),
                file_name=os.path.basename(art["excel_file"]),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    st.markdown("</div>", unsafe_allow_html=True)

# Tabs
tab_map, tab_params, tab_graph, tab_report = st.tabs([
    "🗺️ 지도 및 타임라인 분석",
    "⚙️ 측정 파라미터 비교",
    "📈 시계열 정밀 그래프",
    "📋 품질 진단 보고서 & 요약"
])


# -----------------------------------------------------------------------------
# TAB 1: Interactive 2D Map & Timeline
# -----------------------------------------------------------------------------
with tab_map:
    if art["map_html"]:
        components.html(art["map_html"], height=900, scrolling=True)
    else:
        st.warning("⚠️ 해당 세션에 Map HTML 산출물이 존재하지 않습니다.")


# -----------------------------------------------------------------------------
# TAB 2: BS Parameter Comparison
# -----------------------------------------------------------------------------
with tab_params:
    st.markdown("### ⚙️ 기지국 핵심 파라미터 및 설정 일치성 검사")
    st.caption("3GPP TS 38.331 / 36.331 L3 시그널링 기반 셀 파라미터 및 임계치 검증 결과")

    p_struct = extracted_meta.get("param_struct", [])
    p_scalar = extracted_meta.get("param_scalar", [])

    col_srch, col_filt = st.columns([2, 1])
    with col_srch:
        srch_query = st.text_input("🔍 파라미터 검색 (항목명, 메시지, 값)", "").strip().lower()

    st.markdown("#### 📋 기지국 핵심 복합 파라미터 / 임계치 비교 매트릭스")
    if p_struct:
        df_struct = pd.DataFrame(p_struct)
        rename_map = {
            "category": "메시지 분류",
            "param_name": "파라미터 / 항목 명",
            "rank1": "1위 정책군 (최빈값 / 점유율)",
            "rank2": "2위 정책군 (차순위 / 점유율)",
            "rank3_outliers": "3위/특이 설정값 (소수 기지국)"
        }
        df_struct = df_struct.rename(columns=rename_map)

        if srch_query:
            mask = df_struct.astype(str).apply(lambda row: row.str.lower().str.contains(srch_query).any(), axis=1)
            df_struct_filtered = df_struct[mask]
        else:
            df_struct_filtered = df_struct

        st.dataframe(df_struct_filtered, use_container_width=True, hide_index=True)
    else:
        st.info("검출된 구조체 파라미터 데이터가 없거나 Map 파일에서 로드되지 않았습니다.")

    st.markdown("---")
    st.markdown("#### ⚖️ 기지국 단일 스칼라 파라미터 불일치 분석")
    if p_scalar:
        df_scalar = pd.DataFrame(p_scalar)
        rename_scalar = {
            "param_name": "파라미터 명",
            "val_m1": "M1 (DL)",
            "val_m2": "M2 (UL)",
            "val_m3": "M3 (Voice)",
            "val_m4": "M4 (Voice)",
            "status": "일치 판정"
        }
        df_scalar = df_scalar.rename(columns=rename_scalar)

        if srch_query:
            mask_s = df_scalar.astype(str).apply(lambda row: row.str.lower().str.contains(srch_query).any(), axis=1)
            df_scalar_filtered = df_scalar[mask_s]
        else:
            df_scalar_filtered = df_scalar

        st.dataframe(df_scalar_filtered, use_container_width=True, hide_index=True)
    else:
        st.info("검출된 스칼라 파라미터 데이터가 없습니다.")


# -----------------------------------------------------------------------------
# TAB 3: Time-Series Dual Mode Graph (Plotly)
# -----------------------------------------------------------------------------
with tab_graph:
    st.markdown("### 📈 세션 시계열 정밀 분석 그래프")
    st.caption("독립형 HTML 대시보드(탭1) 내의 동적 시계열 차트를 활용하거나, 아래 보조 Plotly 차트를 이용할 수 있습니다.")

    ports_data = extracted_meta.get("ports_data", {})
    if not ports_data:
        st.info("시계열 추출 데이터가 없습니다. 탭 1의 인터랙티브 대시보드를 직접 이용해 주세요.")
    else:
        avail_ports = list(ports_data.keys())
        c_p1, c_p2 = st.columns([1, 2])
        with c_p1:
            sel_ports = st.multiselect("분석 대상 단말(Port) 선택", avail_ports, default=avail_ports[:1])
        with c_p2:
            metrics_opts = [
                ("rsrp", "LTE PCell RSRP (dBm)"),
                ("sinr", "LTE PCell SINR (dB)"),
                ("lte_mac_tp", "LTE MAC Total (Mbps)"),
                ("dl_tp", "App DL 속도 (Mbps)"),
                ("pci", "LTE PCell PCI"),
                ("speed", "이동속도 (km/h)")
            ]
            sel_metric_key = st.selectbox("표시 지표", [k for k, v in metrics_opts], format_func=lambda x: next(v for k, v in metrics_opts if k == x))

        if sel_ports and HAS_PLOTLY:
            fig = go.Figure()
            for pk in sel_ports:
                p_pts = ports_data[pk].get("points", [])
                x_times = [p.get("time") for p in p_pts]
                y_vals = []
                for p in p_pts:
                    v = p.get(sel_metric_key)
                    if v is None and p.get("raw"):
                        v = p["raw"].get(sel_metric_key)
                    y_vals.append(v)

                fig.add_trace(go.Scatter(
                    x=x_times,
                    y=y_vals,
                    mode='lines+markers',
                    name=pk,
                    connectgaps=False
                ))

            fig.update_layout(
                template="plotly_dark",
                height=350,
                margin=dict(l=40, r=20, t=30, b=40),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 4: Diagnosis Report & Summary
# -----------------------------------------------------------------------------
with tab_report:
    st.markdown("### 📋 AI 종합 품질 진단 보고서")
    if art["report_txt"]:
        st.text_area("Report Content", art["report_txt"], height=600)
    else:
        st.info("⚠️ 생성된 텍스트 보고서(_Report.txt)가 없습니다.")
