# -*- coding: utf-8 -*-
"""
===============================================================================
Script Name   : app_v1.py
Location      : 3_Optis_AI_Analyzer/app_v1.py
Description   : OPTis AI Web Analyzer - Streamlit 2D GIS Interactive Dashboard
                - Ultra-compact Sidebar with 28px Mini Buttons & [Name] + [X] Grid
                - 1-Line Server IP & Port (No +/- Stepper)
                - 3.2rem Safe Margin ensuring 100% Clickable M1~M4 Header
===============================================================================
"""

import os
import sys
import json
import ftplib
import tempfile
import io
import re
from collections import Counter
import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Ensure local core is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import importlib
import core.visualizers.interactive_map_builder as imb_module
importlib.reload(imb_module)
from core.session_cache_manager import SessionCacheManager, format_standard_session_name, extract_yymmdd
from core.optis_pipeline_runner import OptisPipelineRunner

# -----------------------------------------------------------------------------
# Streamlit Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="OPTis AI Web Analyzer",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for compact buttons & natural high-visibility inputs
st.markdown("""
<style>
    /* Hide Deploy button & Menu */
    .stDeployButton { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    /* Ensure sidebar toggle control is ALWAYS visible and crisp */
    [data-testid="stSidebarCollapsedControl"],
    div[data-testid="stSidebarCollapsedControl"] button {
        display: flex !important;
        visibility: visible !important;
        opacity: 1.0 !important;
        position: fixed !important;
        top: 10px !important;
        left: 10px !important;
        z-index: 9999999 !important;
        background-color: #1e293b !important;
        color: #38bdf8 !important;
        border: 2px solid #38bdf8 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.9) !important;
        cursor: pointer !important;
    }

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

    /* Dark sidebar base styling */
    section[data-testid="stSidebar"] {
        background-color: #0f172a !important;
    }
    section[data-testid="stSidebar"] * {
        color: #f8fafc;
    }

    /* Ultra-compact Sidebar Button Styling (28px height, 11px font) */
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

    /* Natural Slate Gray Input Styling */
    section[data-testid="stSidebar"] input[type="text"],
    section[data-testid="stSidebar"] input[type="password"],
    section[data-testid="stSidebar"] input[type="number"] {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f8fafc !important;
        border-radius: 4px !important;
        padding: 3px 8px !important;
        font-size: 12px !important;
        height: 32px !important;
    }
    section[data-testid="stSidebar"] input:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 1px #38bdf8 !important;
    }

    /* Tighter vertical spacing in sidebar */
    section[data-testid="stSidebar"] .stMarkdown {
        margin-bottom: -6px !important;
    }
    section[data-testid="stSidebar"] hr {
        margin-top: 10px !important;
        margin-bottom: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

CONFIG_FILE = os.path.join(current_dir, ".server_config.json")


def load_saved_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config_dict: dict):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


@st.cache_data(ttl=60, show_spinner=False)
def list_remote_zip_files(host, port, user, password, remote_dir) -> list:
    try:
        port_int = int(str(port).strip())
    except Exception:
        port_int = 10022

    is_sftp = (port_int != 21)

    if is_sftp and HAS_PARAMIKO:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, port=port_int, username=user, password=password, timeout=10)
            sftp = ssh.open_sftp()
            
            clean_dir = remote_dir.strip() if remote_dir.strip() else '.'
            file_attrs = sftp.listdir_attr(clean_dir)
            import re
            zip_files = [f.filename for f in file_attrs if f.filename.lower().endswith('.zip')]
            zip_files = sorted(zip_files, key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(s))])
            sftp.close()
            ssh.close()
            return zip_files
        except Exception:
            return []
    else:
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port_int, timeout=10)
            ftp.login(user, password)
            ftp.set_pasv(True)
            if remote_dir and remote_dir.strip() != '/':
                ftp.cwd(remote_dir.strip())
            filenames = ftp.nlst()
            import re
            zip_files = [f for f in filenames if f.lower().endswith('.zip')]
            zip_files = sorted(zip_files, key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(s))])
            ftp.quit()
            return zip_files
        except Exception:
            return []


def download_remote_file(host, port, user, password, remote_dir, filename, local_dest_path) -> bool:
    try:
        port_int = int(str(port).strip())
    except Exception:
        port_int = 10022

    is_sftp = (port_int != 21)

    if is_sftp and HAS_PARAMIKO:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, port=port_int, username=user, password=password, timeout=15)
            sftp = ssh.open_sftp()
            clean_dir = remote_dir.strip().rstrip('/')
            remote_full_path = f"{clean_dir}/{filename}" if clean_dir else filename
            sftp.get(remote_full_path, local_dest_path)
            sftp.close()
            ssh.close()
            return True
        except Exception:
            return False
    else:
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port_int, timeout=15)
            ftp.login(user, password)
            ftp.set_pasv(True)
            if remote_dir and remote_dir.strip() != '/':
                ftp.cwd(remote_dir.strip())
            with open(local_dest_path, 'wb') as f_out:
                ftp.retrbinary(f"RETR {filename}", f_out.write)
            ftp.quit()
            return True
        except Exception:
            return False


def extract_scenario_summary_tables(excel_source):
    """
    Parses an Excel file (path or bytes) and generates specialized scenario summary tables:
    - DL Summary Table
    - UL Summary Table
    - Ping Summary Table
    - Voice Summary Table
    Preserves 100% of original numeric columns without any truncation or reduction.
    """
    if isinstance(excel_source, bytes):
        xl = pd.ExcelFile(io.BytesIO(excel_source))
    else:
        xl = pd.ExcelFile(excel_source)

    sheets = xl.sheet_names

    scenario_groups = {
        'DL': [],
        'UL': [],
        'Ping': [],
        'Voice': []
    }

    for s in sheets:
        s_lower = s.lower()
        if 'per_call' in s_lower or 'per_sec' not in s_lower and ('dl' in s_lower or 'ul' in s_lower or 'ping' in s_lower or 'voice' in s_lower):
            if 'per_sec' in s_lower or 'master' in s_lower or '01_' in s_lower or 'mobility' in s_lower or 'l3' in s_lower:
                continue
            if 'dl' in s_lower:
                scenario_groups['DL'].append(s)
            elif 'ul' in s_lower:
                scenario_groups['UL'].append(s)
            elif 'ping' in s_lower:
                scenario_groups['Ping'].append(s)
            elif 'voice' in s_lower:
                scenario_groups['Voice'].append(s)

    result_tables = {}

    for sc_name, sheet_list in scenario_groups.items():
        if not sheet_list:
            continue

        rows = []
        for s_name in sheet_list:
            df = xl.parse(s_name)
            if df.empty:
                continue

            # Filter out sheet summary rows ('Average', '평균', 'Total', '합계') to get pure calls
            col0 = df.columns[0]
            df_calls = df[~df[col0].astype(str).str.contains('Average|평균|Total|합계|Sum', case=False, na=False)]
            if df_calls.empty:
                df_calls = df

            parts = s_name.split('_')
            port_name = "M1"
            for p in parts:
                if p.upper().startswith('M') and (len(p) <= 6):
                    port_name = p.upper()
                    break

            total_calls = len(df_calls)
            res_col = next((c for c in df_calls.columns if any(k in str(c).lower() for k in ['결과', 'result', 'status', 'state', '상태'])), None)

            if res_col:
                success_count = sum(df_calls[res_col].astype(str).str.contains('정상|완료|성공|Success|PASS|Pass', case=False, regex=True))
                succ_rate = round(success_count / total_calls * 100.0, 1) if total_calls > 0 else 0.0
                call_stat_str = f"{success_count} / {total_calls} Call ({succ_rate}%)"
            else:
                call_stat_str = f"{total_calls} / {total_calls} Call (100.0%)"

            row_dict = {
                "단말 (포트)": f"{port_name} ({sc_name})",
                "호 성공 / 시도": call_stat_str
            }

            for col in df_calls.columns:
                if col == res_col or col in ['Call_No', '호 번호', 'No', 'Index', '시작시간', '종료시간', 'Time', 'Timestamp']:
                    continue

                num_s = pd.to_numeric(df_calls[col], errors='coerce').dropna()
                if len(num_s) > 0:
                    if any(k in str(col).lower() for k in ['회수', 'count', '건수', 'num', '횟수']):
                        row_dict[col] = int(num_s.sum())
                    else:
                        row_dict[col] = round(float(num_s.mean()), 2)
                else:
                    non_nulls = df_calls[col].dropna()
                    if len(non_nulls) > 0:
                        row_dict[col] = str(non_nulls.iloc[0])

            rows.append(row_dict)

        if rows:
            df_sc = pd.DataFrame(rows)
            result_tables[sc_name] = df_sc

    return result_tables


# -----------------------------------------------------------------------------
# Intelligent Parameter Filter & Multi-Cluster Policy Distribution Helpers
# -----------------------------------------------------------------------------
EXCLUDED_PATTERNS = [
    r'transaction.*ident',
    r'rrc.*transaction',
    r'c-rnti',
    r'physcellid',
    r'physical_cell_id',
    r'cellident',
    r'trackingarea',
    r'shortmac-i',
    r'sqn',
    r'keysetident',
    r'timestamp',
    r'counter',
    r'token',
    r'digest',
    r'signature',
    r'measid$',
    r'reportconfigid$',
    r'measobjectid$',
    r'noncriticalextension',
    r'encoded_msg_len',
    r'sub_fn',
    r'frame_number',
    r's-tmsi',
    r'mmec',
    r'paging',
    r'measurementreport',
    r'measresults',
    r'ulinformationtransfer'
]

def is_meaningful_network_param(param_name: str, struct_path: str = '', unique_ratio: float = 0.0) -> bool:
    """Filters out purely dynamic tokens and UE measurement reports from configuration audit."""
    full_str = f"{struct_path}_{param_name}".lower()
    for pat in EXCLUDED_PATTERNS:
        if re.search(pat, full_str):
            return False
    return True


def compute_multi_cluster_summary(vals_dict: dict, total_pcis: list) -> dict:
    """
    Computes 1st, 2nd, and 3rd/outlier policy clusters across all cells.
    """
    valid_pci_val_pairs = [(pci, vals_dict.get(pci, '미설정')) for pci in total_pcis]
    valid_pairs = [(pci, v) for pci, v in valid_pci_val_pairs if v != '미설정' and str(v).strip() != '' and str(v) != 'nan']
    unset_pcis = [pci for pci, v in valid_pci_val_pairs if v == '미설정' or str(v).strip() == '' or str(v) == 'nan']

    if not valid_pairs:
        return {
            'rank1': '-',
            'rank2': '-',
            'rank3_outliers': '-',
            'unset_info': f"{len(unset_pcis)}개 셀 전수 미설정" if unset_pcis else '-'
        }

    total_valid = len(valid_pairs)
    val_counts = Counter([v for _, v in valid_pairs])
    common = val_counts.most_common()

    # 1위 정책군 (최빈값)
    val1, cnt1 = common[0]
    pct1 = (cnt1 / total_valid) * 100.0
    rank1_str = f"{val1} ({cnt1}개 셀, {pct1:.0f}%)"

    # 2위 정책군 및 3위/특이값 판정
    if len(common) == 1:
        rank2_str = '-'
        rank3_str = '-'
    elif len(common) == 2:
        # 3위가 없는 경우: 2위가 최후의 소수 정책군 -> PCI 100% 전수 명시
        val2, cnt2 = common[1]
        pct2 = (cnt2 / total_valid) * 100.0
        pcis_2 = [str(pci) for pci, v in valid_pairs if v == val2]
        rank2_str = f"{val2} [PCI {', '.join(pcis_2)}] ({cnt2}개 셀, {pct2:.0f}%)"
        rank3_str = '-'
    else:
        # 3위 이상이 존재하는 경우: 2위는 요약치만 표기, 3위 이하에 모든 소수 PCI 100% 명시
        val2, cnt2 = common[1]
        pct2 = (cnt2 / total_valid) * 100.0
        rank2_str = f"{val2} ({cnt2}개 셀, {pct2:.0f}%)"

        outliers = []
        for val_k, cnt_k in common[2:]:
            pcis_k = [str(pci) for pci, v in valid_pairs if v == val_k]
            outliers.append(f"{val_k} [PCI {', '.join(pcis_k)}] ({cnt_k}개 셀)")
        rank3_str = " | ".join(outliers) if outliers else '-'

    # 미설정 셀 (단순 요약 표기)
    if unset_pcis:
        unset_str = f"{len(unset_pcis)}개 셀 미수신/미설정"
    else:
        unset_str = '-'

    return {
        'rank1': rank1_str,
        'rank2': rank2_str,
        'rank3_outliers': rank3_str,
        'unset_info': unset_str
    }


def build_smart_compressed_param_matrix(df_raw, is_struct=True):
    """
    Transforms a wide parameter sheet into a clean 6-column Multi-Cluster Policy Distribution table:
    [메시지 분류], [파라미터 / 프레임 명], [1위 정책군 (최빈값 / 점유율)], [2위 정책군 (차순위 / 점유율)], [3위/특이 설정값 (소수 기지국)], [미수신 / 미설정 셀]
    """
    if df_raw.empty:
        return pd.DataFrame()

    pci_cols = [c for c in df_raw.columns if 'pci' in str(c).lower()]
    base_cols = [c for c in df_raw.columns if c not in pci_cols]

    cat_col = base_cols[0] if len(base_cols) > 0 else df_raw.columns[0]
    param_col = base_cols[1] if (is_struct or len(base_cols) <= 3) else base_cols[2]
    struct_path_col = base_cols[1] if (not is_struct and len(base_cols) > 2) else None

    rows = []
    for _, r in df_raw.iterrows():
        cat_name = str(r[cat_col])
        param_name = str(r[param_col])
        struct_path = str(r[struct_path_col]) if struct_path_col else ''

        vals_dict = {pc.replace('PCI ', '').strip(): str(r[pc]) for pc in pci_cols}
        valid_vals = [v for v in vals_dict.values() if v != '미설정' and str(v).strip() != '' and str(v) != 'nan']

        # Filter out non-meaningful parameters for scalar sheet
        if not is_struct:
            u_ratio = (len(set(valid_vals)) / len(valid_vals)) if valid_vals else 0.0
            if not is_meaningful_network_param(param_name, struct_path, u_ratio):
                continue

        clust = compute_multi_cluster_summary(vals_dict, list(vals_dict.keys()))

        param_display = f"{struct_path} > {param_name}" if struct_path and struct_path != '-' else param_name

        rows.append({
            '메시지 분류': cat_name,
            '파라미터 / 프레임 명': param_display,
            '1위 정책군 (최빈값 / 점유율)': clust['rank1'],
            '2위 정책군 (차순위 / 점유율)': clust['rank2'],
            '3위/특이 설정값 (소수 기지국)': clust['rank3_outliers'],
            '미수신 / 미설정 셀': clust['unset_info']
        })

    return pd.DataFrame(rows)


def extract_l3_struct_and_diffs(excel_source):
    """
    Parses an Excel file and extracts:
    1. The Complex Struct matrix table in multi-cluster format.
    2. The Scalar parameter diffs (rows with rank2 or rank3/outliers) in multi-cluster format.
    """
    if isinstance(excel_source, bytes):
        xl = pd.ExcelFile(io.BytesIO(excel_source))
    else:
        xl = pd.ExcelFile(excel_source)

    sheets = xl.sheet_names

    # 1. Complex Struct Sheet
    struct_sheet = next((s for s in sheets if '복합구조체' in s or '임계치' in s or '05_L3' in s or '11_L3' in s), None)
    df_struct_raw = xl.parse(struct_sheet) if struct_sheet else pd.DataFrame()
    df_struct_comp = build_smart_compressed_param_matrix(df_struct_raw, is_struct=True)

    # 2. Scalar Parameter Sheet
    scalar_sheet = next((s for s in sheets if '단일파라미터' in s or '파라미터' in s or '04_L3' in s or '10_L3' in s), None)
    df_scalar_raw = xl.parse(scalar_sheet) if scalar_sheet else pd.DataFrame()
    df_scalar_comp = build_smart_compressed_param_matrix(df_scalar_raw, is_struct=False)

    # Filter out only differing parameters (where rank2 is present or rank3/outlier exists)
    if not df_scalar_comp.empty:
        df_scalar_diffs_only = df_scalar_comp[
            (df_scalar_comp['2위 정책군 (차순위 / 점유율)'] != '-') |
            (df_scalar_comp['3위/특이 설정값 (소수 기지국)'] != '-')
        ]
    else:
        df_scalar_diffs_only = pd.DataFrame()

    return df_struct_comp, df_scalar_diffs_only


@st.cache_data(show_spinner=False)
def extract_all_per_sec_sheets(excel_source) -> Dict[str, pd.DataFrame]:
    """
    Parses an Excel file and extracts all per-second timeline sheets for each port (M1, M2, M3, M4, etc.).
    """
    sheets = {}
    try:
        if isinstance(excel_source, bytes):
            xl = pd.ExcelFile(io.BytesIO(excel_source), engine='openpyxl')
        else:
            xl = pd.ExcelFile(excel_source, engine='openpyxl')

        for s in xl.sheet_names:
            s_lower = str(s).lower()
            if 'per_sec' in s_lower or '초단위' in s or 'qc_kpi' in s_lower or 'timeline' in s_lower:
                sheets[s] = xl.parse(s)
    except Exception:
        pass
    return sheets


# -----------------------------------------------------------------------------
# Initialize Session State & Cache Manager
# -----------------------------------------------------------------------------
secrets_ftp = {}
try:
    if hasattr(st, "secrets") and "ftp" in st.secrets:
        secrets_ftp = dict(st.secrets["ftp"])
except Exception:
    secrets_ftp = {}

saved_cfg = load_saved_config()
default_host = secrets_ftp.get('host') or saved_cfg.get('host', '113.217.230.27')
default_port = str(secrets_ftp.get('port') or saved_cfg.get('port', 10022))
default_dir = secrets_ftp.get('remote_dir') or saved_cfg.get('remote_dir', '/Personal/전광용/260826 DM TEST')
default_cache_dir = secrets_ftp.get('remote_cache_dir') or saved_cfg.get('remote_cache_dir', '/Personal/전광용/260728_Analyzer Tool/sessions')
default_user = secrets_ftp.get('user') or saved_cfg.get('user', 'skt2')
default_pass = secrets_ftp.get('password') or saved_cfg.get('password', 'setup2')

cache_mgr = SessionCacheManager()

if 'ftp_zip_list' not in st.session_state or not st.session_state['ftp_zip_list']:
    auto_zips = list_remote_zip_files(default_host, default_port, default_user, default_pass, default_dir)
    st.session_state['ftp_zip_list'] = auto_zips

if 'available_cache_sessions' not in st.session_state:
    local_s = cache_mgr.list_local_sessions()
    remote_s = cache_mgr.list_remote_sessions(default_host, default_port, default_user, default_pass, default_cache_dir)
    st.session_state['available_cache_sessions'] = sorted(list(set(local_s + remote_s)), reverse=True)

if 'analysis_sessions' not in st.session_state:
    st.session_state['analysis_sessions'] = {}

if 'selected_session_key' not in st.session_state:
    st.session_state['selected_session_key'] = None


# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.markdown("### 📡 OPTis AI Web Analyzer")
    st.caption("2D GIS 대화형 분석 대시보드")

    # -------------------------------------------------------------------------
    # 0. 📂 사전 분석 세션 불러오기 (측정일 기준 표준 명명)
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("##### 📂 사전 분석 세션 불러오기")

    cached_list = st.session_state.get('available_cache_sessions', [])
    if cached_list:
        selected_cache = st.selectbox(
            "시연/분석 세션 선택:",
            options=cached_list,
            index=0,
            help="클라우드(FTP) 및 로컬 캐시에 저장된 표준 세션입니다. 선택 시 0초만에 즉시 표출됩니다."
        )
        col_load, col_ref = st.columns([0.72, 0.28])
        with col_load:
            if st.button("📥 세션 즉시 로드", type="primary", use_container_width=True):
                with st.spinner(f"'{selected_cache}' 세션 로드 중..."):
                    # 1. Try local cache first
                    s_data = cache_mgr.load_local_session(selected_cache)
                    # 2. If not local, download from remote FTP
                    if not s_data:
                        s_data = cache_mgr.download_remote_session(
                            default_host, default_port, default_user, default_pass, selected_cache, default_cache_dir
                        )
                    if s_data:
                        st.session_state['analysis_sessions'][selected_cache] = s_data
                        st.session_state['selected_session_key'] = selected_cache
                        st.rerun()
                    else:
                        st.sidebar.error("❌ 세션 데이터를 불러오지 못했습니다.")
        with col_ref:
            if st.button("🔄 갱신", key="btn_ref_cache", use_container_width=True):
                local_s = cache_mgr.list_local_sessions()
                remote_s = cache_mgr.list_remote_sessions(default_host, default_port, default_user, default_pass, default_cache_dir)
                st.session_state['available_cache_sessions'] = sorted(list(set(local_s + remote_s)), reverse=True)
                st.rerun()
    else:
        st.info("ℹ️ 캐시 세션을 탐색 중이거나 없습니다.")
        if st.button("🔄 캐시 세션 조회", key="btn_init_cache", use_container_width=True):
            local_s = cache_mgr.list_local_sessions()
            remote_s = cache_mgr.list_remote_sessions(default_host, default_port, default_user, default_pass, default_cache_dir)
            st.session_state['available_cache_sessions'] = sorted(list(set(local_s + remote_s)), reverse=True)
            st.rerun()

    # 0. Compact 2-Column Grid Session Switcher
    sessions = st.session_state.get('analysis_sessions', {})
    if sessions:
        st.markdown("---")
        col_t, col_rst = st.columns([0.72, 0.28])
        with col_t:
            st.markdown("##### 📍 분석 세션")
        with col_rst:
            if st.button("초기화", key="btn_global_reset", use_container_width=True):
                st.session_state['analysis_sessions'] = {}
                st.session_state['selected_session_key'] = None
                st.rerun()

        s_keys = list(sessions.keys())
        if st.session_state['selected_session_key'] not in s_keys:
            st.session_state['selected_session_key'] = s_keys[-1]

        active_k = st.session_state['selected_session_key']

        # Session Rows: [Expander (82%)] [✕ (18%)]
        for sk in s_keys:
            clean_name = str(sk).replace('.zip', '')
            short_name = clean_name if len(clean_name) <= 13 else clean_name[:11] + "..."
            is_cur = (sk == active_k)
            expander_title = f"{'🟢' if is_cur else '⚪'} {short_name}"

            col_exp, col_del = st.columns([0.82, 0.18])
            with col_exp:
                with st.expander(expander_title, expanded=is_cur):
                    if not is_cur:
                        if st.button("🗺️ 이 지도 보기", key=f"btn_v_{sk}", use_container_width=True):
                            st.session_state['selected_session_key'] = sk
                            st.rerun()

                    cur_dl = sessions[sk]
                    st.download_button(
                        label="🗺️ 2D 대화형 맵 (.html)",
                        data=cur_dl['map_html'],
                        file_name=f"Optis_{sk}_Map.html",
                        mime="text/html",
                        key=f"dl_m_{sk}",
                        use_container_width=True
                    )
                    st.download_button(
                        label="📊 통합 마스터 엑셀 (.xlsx)",
                        data=cur_dl['excel_bytes'],
                        file_name=f"Optis_{sk}_Master.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_x_{sk}",
                        use_container_width=True
                    )
                    st.download_button(
                        label="📄 종합 진단 리포트 (.txt)",
                        data=cur_dl['txt_report'],
                        file_name=f"Optis_{sk}_Analysis.txt",
                        mime="text/plain",
                        key=f"dl_t_{sk}",
                        use_container_width=True
                    )

            with col_del:
                if st.button("✕", key=f"del_{sk}", use_container_width=True):
                    del st.session_state['analysis_sessions'][sk]
                    remaining = list(st.session_state['analysis_sessions'].keys())
                    st.session_state['selected_session_key'] = remaining[-1] if remaining else None
                    st.rerun()

    st.markdown("---")
    # Clean connection status badge for demonstration
    st.markdown(
        """<div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 7px 10px; margin-bottom: 8px;">
            <span style="color: #10b981; font-weight: 700; font-size: 12px;">🟢 분석 서버 연결됨</span>
            <span style="color: #94a3b8; font-size: 11px; margin-left: 4px;">(FTP 113.217.230.27)</span>
        </div>""",
        unsafe_allow_html=True
    )

    ftp_host = default_host
    ftp_port = default_port
    ftp_dir = default_dir
    ftp_user = default_user
    ftp_pass = default_pass

    with st.expander("⚙️ 고급 서버 설정 (필요 시)", expanded=False):
        col_ip, col_port = st.columns([0.72, 0.28])
        with col_ip:
            ftp_host = st.text_input("서버 IP", value=default_host, key="web_ftp_host")
        with col_port:
            ftp_port = st.text_input("Port", value=default_port, key="web_ftp_port")

        ftp_dir = st.text_input("원격 경로", value=default_dir, key="web_ftp_dir")

        col_u, col_p = st.columns(2)
        with col_u:
            ftp_user = st.text_input("User", value=default_user, key="web_ftp_user")
        with col_p:
            ftp_pass = st.text_input("Password", value=default_pass, type="password", key="web_ftp_pass")

        if st.button("🔄 파일 목록 다시 조회", key="btn_web_reload_zips", use_container_width=True):
            with st.spinner("서버에서 ZIP 검색 중..."):
                zips = list_remote_zip_files(ftp_host, ftp_port, ftp_user, ftp_pass, ftp_dir)
                st.session_state['ftp_zip_list'] = zips
                if zips:
                    try:
                        p_val = int(str(ftp_port).strip())
                    except Exception:
                        p_val = 10022
                    save_config({'host': ftp_host, 'port': p_val, 'user': ftp_user, 'password': ftp_pass, 'remote_dir': ftp_dir})
                    st.success(f"{len(zips)}개 파일 로드 완료!")

    st.markdown("---")
    st.markdown("##### 📂 분석 대상 ZIP 선택")
    selected_ftp_zips = st.multiselect(
        "분석할 원격 ZIP 파일:",
        options=st.session_state.get('ftp_zip_list', []),
        default=st.session_state.get('ftp_zip_list', [])
    )
    
    uploaded_files = st.file_uploader("또는 로컬 ZIP 업로드", type=['zip'], accept_multiple_files=True)

    st.markdown("---")
    start_analysis = st.button("🚀 맵 생성 및 세션 추가", type="primary", use_container_width=True)


# =============================================================================
# BACKGROUND EXECUTION
# =============================================================================
if start_analysis:
    if not selected_ftp_zips and not uploaded_files:
        st.sidebar.warning("⚠️ 분석할 ZIP 파일을 선택해 주세요.")
    else:
        with st.spinner("⏳ ZIP 파일 다운로드 및 100% 검증된 파이프라인 분석 중..."):
            work_dir = tempfile.mkdtemp(prefix="optis_run_")
            try:
                dl_zips = []
                for zn in selected_ftp_zips:
                    loc_z = os.path.join(work_dir, zn)
                    if download_remote_file(ftp_host, ftp_port, ftp_user, ftp_pass, ftp_dir, zn, loc_z):
                        dl_zips.append(loc_z)

                if uploaded_files:
                    for uf in uploaded_files:
                        loc_u = os.path.join(work_dir, uf.name)
                        with open(loc_u, 'wb') as f_u:
                            f_u.write(uf.getbuffer())
                        dl_zips.append(loc_u)

                # Run exact pipeline runner
                runner = OptisPipelineRunner()
                results = runner.run(dl_zips)

                if results:
                    for r_key, r_val in results.items():
                        # 1. Determine standard session name [YYMMDD]_[Route]-[Ports]
                        sample_seed = r_key
                        if dl_zips:
                            for dz in dl_zips:
                                bn = os.path.basename(dz)
                                if any(yr in bn for yr in ['20', '24', '25', '26']):
                                    sample_seed = bn
                                    break

                        std_session_name = format_standard_session_name(
                            sample_seed, r_key, r_val.get('ports', ['M1'])
                        )

                        # 2. Package and save to local cache
                        meta_dict = {
                            "session_name": std_session_name,
                            "measurement_date": extract_yymmdd(sample_seed),
                            "scenario_name": r_key,
                            "ports": r_val.get('ports', ['M1']),
                            "network_mode": r_val.get('network_mode', 'LTE'),
                            "vendor": r_val.get('vendor', 'COMMON'),
                            "total_episodes": r_val.get('total_episodes', 0),
                            "total_pts": r_val.get('total_pts', 0)
                        }

                        saved_dir = cache_mgr.save_local_session(
                            session_name=std_session_name,
                            map_html=r_val['map_html'],
                            excel_bytes=r_val['excel_bytes'],
                            txt_report=r_val['txt_report'],
                            meta_dict=meta_dict
                        )

                        # 3. Real-time auto-upload to remote FTP
                        with st.spinner(f"🚀 원격 FTP 캐시 업로드 중: {std_session_name}..."):
                            uploaded = cache_mgr.upload_session_to_remote(
                                host=ftp_host,
                                port=ftp_port,
                                user=ftp_user,
                                password=ftp_pass,
                                session_name=std_session_name,
                                local_session_dir=saved_dir,
                                remote_base_dir=default_cache_dir
                            )

                        # 4. Immediate state reflection
                        if 'available_cache_sessions' in st.session_state:
                            if std_session_name not in st.session_state['available_cache_sessions']:
                                st.session_state['available_cache_sessions'].insert(0, std_session_name)

                        st.session_state['analysis_sessions'][std_session_name] = r_val
                        st.session_state['selected_session_key'] = std_session_name

                        if uploaded:
                            st.sidebar.success(f"✅ 원격 FTP 업로드 완료: {std_session_name}")
                        else:
                            st.sidebar.info(f"💾 로컬 캐시 저장 완료 (원격 업로드 확인 필요): {std_session_name}")

                    st.rerun()
                else:
                    st.sidebar.error("❌ 분석 결과 생성 실패 (유효한 타임라인 데이터를 찾을 수 없음).")

            except Exception as e:
                st.sidebar.error(f"분석 중 오류 발생: {str(e)}")
                import traceback
                st.sidebar.code(traceback.format_exc())


# =============================================================================
# MAIN VIEWPORT: Pure Fullscreen 2D GIS Interactive Map
# =============================================================================
sessions = st.session_state.get('analysis_sessions', {})
active_key = st.session_state.get('selected_session_key')

if not sessions or not active_key or active_key not in sessions:
    st.markdown("""
    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; height: 80vh; text-align: center;">
        <h1 style="color: #38BDF8; font-size: 2.2rem; margin-bottom: 0.8rem;">🗺️ OPTis AI 2D GIS Interactive Map</h1>
        <p style="color: #94A3B8; font-size: 1.15rem; max-width: 600px; line-height: 1.6;">
            좌측 사이드바에서 ZIP 파일(M1~M4)을 확인하신 후,<br>
            <b>[ 🚀 맵 생성 및 세션 추가 ]</b> 버튼을 눌러주세요.
        </p>
    </div>
    """, unsafe_allow_html=True)
else:
    target = sessions[active_key]
    tab_map, tab_summary, tab_params, tab_graph = st.tabs([
        "🗺️ 2D 대화형 지도",
        "📊 종합 분석 요약장",
        "⚙️ MSG 기반 파라미터 비교",
        "📈 시계열 정밀 그래프"
    ])

    with tab_map:
        components.html(
            target['map_html'],
            height=940,
            scrolling=False
        )

    with tab_summary:
        st.markdown(f"#### 📊 분석 세션 종합 요약장: `{active_key}`")
        try:
            summary_tables = extract_scenario_summary_tables(target['excel_bytes'])
            if not summary_tables:
                st.info("ℹ️ 해당 세션에서 추출 가능한 시나리오별 Call 요약 시트를 찾지 못했습니다.")
            else:
                if 'DL' in summary_tables:
                    st.markdown("##### 🚀 Data DL (다운로드) 종합 요약")
                    st.dataframe(summary_tables['DL'], use_container_width=True, hide_index=True)
                    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                if 'UL' in summary_tables:
                    st.markdown("##### ⚡ Data UL (업로드) 종합 요약")
                    st.dataframe(summary_tables['UL'], use_container_width=True, hide_index=True)
                    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                if 'Ping' in summary_tables:
                    st.markdown("##### 🏓 Ping / 지연시간 종합 요약")
                    st.dataframe(summary_tables['Ping'], use_container_width=True, hide_index=True)
                    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                if 'Voice' in summary_tables:
                    st.markdown("##### 🎙️ VoLTE Voice (음성) 종합 요약")
                    st.dataframe(summary_tables['Voice'], use_container_width=True, hide_index=True)
        except Exception as ex:
            st.error(f"요약장 파싱 중 오류 발생: {str(ex)}")

    with tab_params:
        st.markdown(f"#### ⚙️ MSG 기반 파라미터 비교: `{active_key}`")
        try:
            df_struct_comp, df_scalar_diffs = extract_l3_struct_and_diffs(target['excel_bytes'])

            # 1. Main Complex Struct Matrix (TOP Placement)
            if not df_struct_comp.empty:
                st.markdown("##### 📋 기지국 핵심 복합 파라미터 / 임계치 비교 매트릭스")
                st.dataframe(
                    df_struct_comp,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "메시지 분류": st.column_config.TextColumn("메시지 분류", width="small"),
                        "파라미터 / 프레임 명": st.column_config.TextColumn("파라미터 / 프레임 명", width="medium"),
                        "1위 정책군 (최빈값 / 점유율)": st.column_config.TextColumn("1위 정책군 (최빈값 / 점유율)", width="large"),
                        "2위 정책군 (차순위 / 점유율)": st.column_config.TextColumn("2위 정책군 (차순위 / 점유율)", width="medium"),
                        "3위/특이 설정값 (소수 기지국)": st.column_config.TextColumn("3위/특이 설정값 (소수 기지국)", width="large"),
                        "미수신 / 미설정 셀": st.column_config.TextColumn("미수신 / 미설정 셀", width="medium"),
                    }
                )
                st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            else:
                st.info("ℹ️ 해당 세션에서 L3 복합구조체 / 임계치 시트를 찾지 못했습니다.")

            # 2. Scalar Param Diffs (BOTTOM Placement)
            st.markdown("##### ⚠️ 단일 파라미터 불일치(Diff) 상세 목록")
            if not df_scalar_diffs.empty:
                st.dataframe(
                    df_scalar_diffs,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "메시지 분류": st.column_config.TextColumn("메시지 분류", width="small"),
                        "파라미터 / 프레임 명": st.column_config.TextColumn("파라미터 / 프레임 명", width="medium"),
                        "1위 정책군 (최빈값 / 점유율)": st.column_config.TextColumn("1위 정책군 (최빈값 / 점유율)", width="large"),
                        "2위 정책군 (차순위 / 점유율)": st.column_config.TextColumn("2위 정책군 (차순위 / 점유율)", width="medium"),
                        "3위/특이 설정값 (소수 기지국)": st.column_config.TextColumn("3위/특이 설정값 (소수 기지국)", width="large"),
                        "미수신 / 미설정 셀": st.column_config.TextColumn("미수신 / 미설정 셀", width="medium"),
                    }
                )
            else:
                st.success("🟢 **주행 경로 내 전체 기지국(PCI) 단일 파라미터 100% 정상 일치** (불일치 파라미터 0건)")
        except Exception as ex:
            st.error(f"파라미터 데이터 파싱 중 오류 발생: {str(ex)}")

    with tab_graph:
        st.markdown(f"#### 📈 시계열 정밀 그래프 분석: `{active_key}`")
        try:
            per_sec_sheets = extract_all_per_sec_sheets(target['excel_bytes'])
            if not per_sec_sheets:
                st.info("ℹ️ 해당 세션에서 시계열(초단위) 데이터를 찾지 못했습니다.")
            else:
                sheet_options = list(per_sec_sheets.keys())
                
                # Control Bar: Port Selector + Metric Selector + Chart Mode
                col_port, col_sel, col_mode = st.columns([0.25, 0.45, 0.30])
                with col_port:
                    selected_sheet = st.selectbox(
                        "📱 분석 단말(포트) 선택",
                        options=sheet_options,
                        index=0,
                        format_func=lambda s: re.search(r'(M\d+(?:-[A-Za-z0-9]+)?)', str(s)).group(1) if re.search(r'(M\d+(?:-[A-Za-z0-9]+)?)', str(s)) else str(s),
                        help="분석할 단말 포트(M1, M2, M1-S1 등)의 시계열 시트를 선택하세요."
                    )
                
                df_timeline = per_sec_sheets[selected_sheet]

                # Discover time column
                time_col = next((c for c in df_timeline.columns if any(k in str(c).upper() for k in ['시간', 'TIME', 'TIMESTAMP'])), df_timeline.columns[0])

                # Zero Column Filtering: Expose 100% of all raw columns in df_timeline
                kpi_candidates = [str(c) for c in df_timeline.columns if c != time_col]

                if not kpi_candidates:
                    st.warning("⚠️ 표출 가능한 KPI 컬럼이 존재하지 않습니다.")
                else:
                    # Default picks: Start completely empty by default as requested by user
                    default_picks = []

                    with col_sel:
                        selected_metrics = st.multiselect(
                            "📊 [KPI] 표출 지표 선택 (다중 선택 가능)",
                            options=kpi_candidates,
                            default=default_picks,
                            help=f"선택된 포트({selected_sheet})의 전체 수치형 지표 중 분석할 컬럼을 선택하세요."
                        )
                    with col_mode:
                        chart_mode = st.radio(
                            "📉 그래프 표출 방식",
                            ["단일 그래프 오버레이 (Combined)", "개별 그래프 분할 (Subplots 아래 추가)"],
                            index=1,
                            help="단일 그래프에 다중 축으로 겹쳐 보거나, 지표별로 아래에 독립 그래프를 생성하여 시간축을 연동합니다."
                        )

                    if not selected_metrics:
                        st.info("👆 상단에서 1개 이상의 KPI 지표를 선택해 주세요.")
                    elif not HAS_PLOTLY:
                        st.warning("⚠️ Plotly 모듈이 로드되지 않아 기본 차트로 대체합니다.")
                        st.line_chart(df_timeline.set_index(time_col)[selected_metrics])
                    else:
                        palette = [
                            '#38BDF8', '#F43F5E', '#10B981', '#F59E0B', '#8B5CF6',
                            '#EC4899', '#06B6D4', '#84CC16', '#EAB308', '#6366F1'
                        ]
                        time_x = df_timeline[time_col].astype(str)

                        if chart_mode == "단일 그래프 오버레이 (Combined)":
                            fig = go.Figure()
                            for idx, metric in enumerate(selected_metrics):
                                color = palette[idx % len(palette)]
                                s_val = pd.to_numeric(df_timeline[metric], errors='coerce')
                                yaxis_name = "y" if idx == 0 else f"y{idx+1}"

                                fig.add_trace(go.Scatter(
                                    x=time_x,
                                    y=s_val,
                                    name=metric,
                                    mode='lines+markers' if len(df_timeline) < 120 else 'lines',
                                    line=dict(color=color, width=2.2),
                                    marker=dict(size=4),
                                    yaxis=yaxis_name,
                                    hovertemplate=f"<b>{metric}</b>: %{{y}}<extra></extra>"
                                ))

                            layout_dict = dict(
                                template="plotly_dark",
                                paper_bgcolor="#0F172A",
                                plot_bgcolor="#1E293B",
                                height=550,
                                margin=dict(l=40, r=40, t=40, b=40),
                                hovermode="x unified",
                                legend=dict(
                                    orientation="h",
                                    yanchor="bottom",
                                    y=1.02,
                                    xanchor="right",
                                    x=1,
                                    font=dict(size=12, color="#E2E8F0")
                                ),
                                xaxis=dict(
                                    title=dict(text="시간 (Time)", font=dict(color="#94A3B8")),
                                    gridcolor="#334155",
                                    tickfont=dict(color="#CBD5E1")
                                ),
                                yaxis=dict(
                                    title=dict(text=selected_metrics[0], font=dict(color=palette[0])),
                                    tickfont=dict(color=palette[0]),
                                    gridcolor="#334155"
                                )
                            )
                            for idx in range(1, len(selected_metrics)):
                                yaxis_key = f"yaxis{idx+1}"
                                col_c = palette[idx % len(palette)]
                                layout_dict[yaxis_key] = dict(
                                    title=dict(text=selected_metrics[idx], font=dict(color=col_c)),
                                    tickfont=dict(color=col_c),
                                    overlaying="y",
                                    side="right" if idx % 2 == 1 else "left",
                                    anchor="free" if idx > 1 else None,
                                    position=1.0 - (idx - 1)*0.06 if idx % 2 == 1 else (idx - 2)*0.06,
                                    showgrid=False
                                )
                            fig.update_layout(**layout_dict)
                            st.plotly_chart(fig, use_container_width=True)

                        else:
                            # Subplots Mode (Stacked Vertically with Synced X-Axis)
                            n_metrics = len(selected_metrics)
                            fig = make_subplots(
                                rows=n_metrics,
                                cols=1,
                                shared_xaxes=True,
                                vertical_spacing=0.04,
                                subplot_titles=[f"📊 {m}" for m in selected_metrics]
                            )

                            for idx, metric in enumerate(selected_metrics):
                                color = palette[idx % len(palette)]
                                s_val = pd.to_numeric(df_timeline[metric], errors='coerce')

                                fig.add_trace(
                                    go.Scatter(
                                        x=time_x,
                                        y=s_val,
                                        name=metric,
                                        mode='lines+markers' if len(df_timeline) < 120 else 'lines',
                                        line=dict(color=color, width=2.0),
                                        fill='tozeroy' if any(k in metric for k in ['속도', 'Throughput', 'MOS']) else None,
                                        fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.12)",
                                        hovertemplate=f"<b>{metric}</b>: %{{y}}<extra></extra>"
                                    ),
                                    row=idx+1,
                                    col=1
                                )
                                fig.update_yaxes(
                                    title_text="",
                                    gridcolor="#334155",
                                    tickfont=dict(color="#CBD5E1"),
                                    row=idx+1,
                                    col=1
                                )

                            fig.update_layout(
                                template="plotly_dark",
                                paper_bgcolor="#0F172A",
                                plot_bgcolor="#1E293B",
                                height=max(260 * n_metrics, 400),
                                margin=dict(l=40, r=40, t=40, b=40),
                                hovermode="x unified",
                                showlegend=False,
                                xaxis_title=dict(text="시간 (Time)", font=dict(color="#94A3B8"))
                            )
                            fig.update_xaxes(gridcolor="#334155", tickfont=dict(color="#CBD5E1"))
                            st.plotly_chart(fig, use_container_width=True)

        except Exception as ex:
            st.error(f"시계열 그래프 렌더링 중 오류 발생: {str(ex)}")
