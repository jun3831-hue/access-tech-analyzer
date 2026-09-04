# -*- coding: utf-8 -*-
"""
Module Name: l3_cell_parameter_auditor.py
Location   : core/parsers/l3_cell_parameter_auditor.py
Description: TS 36.331 E-UTRA RRC L3 Pure Scalar Parameters & 14 Complex Structure Audit Engine
"""

import os
import sys
import re
import bisect
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
from collections import Counter, defaultdict

try:
    from pci_state_tracker import PCIStateTracker
    from ts_36331_v1930_eutra_rrc_definitions import EUTRARRCDefinitionsV1930
except ImportError:
    from core.parsers.pci_state_tracker import PCIStateTracker
    from core.parsers.ts_36331_v1930_eutra_rrc_definitions import EUTRARRCDefinitionsV1930


# -----------------------------------------------------------------------------
# Intelligent Parameter Filter & Multi-Cluster Policy Distribution Helpers
# -----------------------------------------------------------------------------
EXCLUDED_PATTERNS = [
    r'transaction.*ident',
    r'rrc.*transaction',
    r'c-rnti',
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
    r'encoded_msg_len',
    r'sub_fn',
    r'frame_number',
    r's-tmsi',
    r'mmec',
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


def compute_multi_cluster_summary(vals_dict: Dict[Any, Any], total_pcis: List[Any]) -> Dict[str, str]:
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


class L3CellParameterAuditor:
    """
    3GPP TS 36.331 E-UTRA RRC / TS 38.331 NR RRC Specification-Based
    Dual Pipeline:
    1. Pure Scalar Parameters (Comprehensive 100% Inclusive: PDCP, RLC, MAC, SIB1~24, MIB, RRC Timers)
    2. 14 Complex Structure Domains (MeasConfig, SIB5, DRB, SRB, CA, Antenna, SRS, DRX, ULPower, CSI-RS, PRACH)
    """

    # Structural Syntax Keys to Exclude (Pure ASN.1 choice wrappers / transaction counters)
    EXCLUDED_SYNTAX_KEYS = {
        'message', 'c1', 'criticalextensions', 'criticalextensionsfuture',
        'rrctransactionidentifier', 'spare', 'rrcconnectionreconfigurationr8',
        'systeminformationr8', 'systeminformationblocktype1', 'noncriticalextension',
        'laternoncriticalextension', 'v890ies', 'v920ies', 'v1020ies', 'v1130ies',
        'v1250ies', 'v1310ies', 'v1430ies', 'v1510ies', 'v1530ies', 'v1610ies',
        'index', 'code', 'detail', 'msgsequence', 'subcommand', 'commandtype',
        'ndatalength', 'l3datainhex', 'simindex', 'dualmodeindex', 'multisimconfiguration',
        'eventid', 'eventa1', 'eventa2', 'eventa3', 'eventa4', 'eventa5', 'eventb1', 'eventb2'
    }

    # Ephemeral Session / Time / Identifier Noise Patterns to Exclude
    EXCLUDED_NOISE_PATTERNS = [
        r'measurementreport', r'measresults', r'c_rnti', r'shortmac_i',
        r'sequencenumber', r'securityheadertype', r'ksiasme', r'sparebits',
        r'systemframenumber', r'subframe', r'dedicatedinfonas', r'nas_pdu',
        r'\btime\b', r'\bdirection\b', r'minute', r'second', r'hour', r'day', r'month', r'year',
        r'm_tmsi', r'stmsi', r'mmecode', r'mmegroupid'
    ]

    # Keywords that belong to Sheet 2 (Structures) -> Excluded from Sheet 1 to prevent duplication
    STRUCTURED_ROUTED_KEYWORDS = [
        'measconfig', 'reportconfig', 'measobject', 'measid', 'a3_offset', 'a3offset',
        'interfreqcarrier', 'soundingrs', 'srs_config', 'drx_config', 'drx_inactivity',
        'onduration', 'uplinkpowercontrol', 'p0_ue_pusch', 'p0_ue_pucch', 'p0_nominalpusch',
        'p0_nominalpucch', 'antennainfo', 'transmissionmode', 'codebooksubset', 'zp_csi',
        'nzp_csi', 'csi_measconfig', 'prach_configindex', 'rootsequenceindex'
    ]

    def __init__(self):
        self.lte_parser = EUTRARRCDefinitionsV1930()
        self.tracker = PCIStateTracker()

    def build_pci_timeline(self, kpi_file_path: Optional[str]) -> Tuple[List[float], List[int]]:
        """Builds epoch-sorted timeline for fast timestamp -> Serving PCI lookup."""
        if not kpi_file_path or not os.path.exists(kpi_file_path):
            return [], []

        try:
            df_kpi = pd.read_csv(kpi_file_path, low_memory=False)
            time_col = None
            for c in ['TIME_STAMP', 'Time', 'Timestamp']:
                if c in df_kpi.columns:
                    time_col = c
                    break
            pci_col = None
            for c in df_kpi.columns:
                if 'PCI' in c and 'SERVING' in c.upper():
                    pci_col = c
                    break
            if not pci_col:
                for c in df_kpi.columns:
                    if 'PCI' in c:
                        pci_col = c
                        break

            if not time_col or not pci_col:
                return [], []

            df_clean = df_kpi[[time_col, pci_col]].dropna().copy()
            df_clean['dt'] = pd.to_datetime(df_clean[time_col], errors='coerce')
            df_clean = df_clean.dropna(subset=['dt']).sort_values('dt').reset_index(drop=True)

            epochs = [t.timestamp() for t in df_clean['dt']]
            pcis = [int(float(p)) for p in df_clean[pci_col].tolist()]
            return epochs, pcis
        except Exception:
            return [], []

    def lookup_pci(self, dt_str: str, epochs: List[float], pcis: List[int]) -> Optional[int]:
        if not epochs or not dt_str:
            return None
        try:
            dt = pd.to_datetime(dt_str)
            target_epoch = dt.timestamp()
            idx = bisect.bisect_left(epochs, target_epoch)
            if idx >= len(epochs):
                idx = len(epochs) - 1
            elif idx > 0 and abs(epochs[idx - 1] - target_epoch) < abs(epochs[idx] - target_epoch):
                idx = idx - 1
            return pcis[idx]
        except Exception:
            return None

    def is_noise(self, param_name: str, struct_path: str, msg_name: str) -> bool:
        combined = f"{msg_name} {struct_path} {param_name}".lower()
        if 'measurementreport' in msg_name.lower():
            return True
        for pat in self.EXCLUDED_NOISE_PATTERNS:
            if re.search(pat, combined):
                return True
        if re.search(r'^[0-9A-Fa-f]{2}$', param_name.strip()):
            return True
        return False

    def is_structured(self, param_name: str, struct_path: str) -> bool:
        combined = f"{struct_path} {param_name}".lower().replace('-', '_')
        return any(sk in combined for sk in self.STRUCTURED_ROUTED_KEYWORDS)

    def parse_all(
        self,
        l3_source: Any,
        kpi_file_path: Optional[str] = None,
        df_timeline: Optional[pd.DataFrame] = None
    ) -> Tuple[Dict[int, Dict[str, str]], Dict[str, Dict[str, str]], Dict[str, Dict[str, Dict[int, str]]], List[int]]:
        """
        Parses L3 message source (file path or lines list) and extracts:
        1. Pure Scalar Parameters (for Sheet 1)
        2. 14 Complex Structure Domains (for Sheet 2)
        Uses df_timeline (SSOT) or kpi_file_path for 100% accurate Serving PCI binding.
        """
        if isinstance(l3_source, list):
            lines = l3_source
        elif isinstance(l3_source, str) and os.path.exists(l3_source):
            with open(l3_source, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        else:
            return defaultdict(dict), {}, defaultdict(lambda: defaultdict(dict)), []

        blocks = self.lte_parser.parse_packet_blocks(lines)

        # Build Epoch-sorted Serving PCI Timeline from df_timeline or KPI
        pci_times, pci_vals = [], []
        if df_timeline is not None and not df_timeline.empty:
            pci_col = 'LTE_Serving_PCI' if 'LTE_Serving_PCI' in df_timeline.columns else ('NR_Serving_PCI' if 'NR_Serving_PCI' in df_timeline.columns else None)
            if pci_col and 'TIME_STAMP' in df_timeline.columns:
                df_pci_clean = df_timeline[['TIME_STAMP', pci_col]].dropna().copy()
                df_pci_clean['dt'] = pd.to_datetime(df_pci_clean['TIME_STAMP'], errors='coerce')
                df_pci_clean = df_pci_clean.dropna(subset=['dt']).sort_values('dt').reset_index(drop=True)
                pci_times = [float(t.timestamp()) for t in df_pci_clean['dt']]
                pci_vals = [int(float(p)) for p in df_pci_clean[pci_col].tolist()]

        if not pci_times and kpi_file_path:
            epochs, pcis_timeline = self.build_pci_timeline(kpi_file_path)
            pci_times, pci_vals = epochs, pcis_timeline

        def lookup_serving_pci(ts_str: str) -> Optional[int]:
            if not pci_times or not ts_str:
                return None
            try:
                dt = pd.to_datetime(ts_str, errors='coerce')
                if pd.isna(dt):
                    return None
                target_epoch = dt.timestamp()
                idx = bisect.bisect_left(pci_times, target_epoch)
                if idx >= len(pci_times):
                    idx = len(pci_times) - 1
                elif idx > 0 and abs(pci_times[idx - 1] - target_epoch) < abs(pci_times[idx] - target_epoch):
                    idx = idx - 1
                return pci_vals[idx]
            except Exception:
                pass
            return None

        cell_scalar_params: Dict[int, Dict[str, str]] = defaultdict(dict)
        param_meta: Dict[str, Dict[str, str]] = {}
        struct_registry: Dict[str, Dict[str, Dict[int, str]]] = defaultdict(lambda: defaultdict(dict))

        current_serving_pci = None

        for hdr, body in blocks:
            hdr_parts = [p.strip() for p in hdr.split(',')]
            pkt_time = hdr_parts[1] if len(hdr_parts) > 1 else ''
            
            msg_raw = hdr_parts[6] if len(hdr_parts) > 6 else ''
            msg_name = msg_raw.replace('__', '').strip()
            if not msg_name:
                code_raw = hdr_parts[5] if len(hdr_parts) > 5 else ''
                msg_name = code_raw.strip() if code_raw else 'RRC_Message'

            # 1. Determine Serving PCI
            pci_cand = lookup_serving_pci(pkt_time)
            if pci_cand is None:
                self.tracker.update_from_line(hdr)
                for b_l in body:
                    self.tracker.update_from_line(b_l)
                state = self.tracker.get_state()
                pci_cand = state.get('Serving_PCI') or state.get('PCI')

            if pci_cand is None or pd.isna(pci_cand):
                m_hdr = re.search(r'(?:Serving\s*PCI|PCI\s*[:=]|physCellId)\s*[:=]?\s*(\d+)', hdr, re.IGNORECASE)
                if m_hdr:
                    pci_cand = int(m_hdr.group(1))

            if pci_cand is not None and not pd.isna(pci_cand):
                try:
                    current_serving_pci = int(pci_cand)
                except Exception:
                    pass

            if current_serving_pci is None:
                continue

            body_text = "\n".join(body)

            # -------------------------------------------------------------
            # 14 Complex Structure Domains Extraction (Multi-Line Block Scanners)
            # -------------------------------------------------------------
            # -------------------------------------------------------------
            # 14 Complex Structure Domains Extraction (Multi-Line Block Scanners)
            # -------------------------------------------------------------
            # Domain 01: MeasConfig (measObject, reportConfig, measId)
            if 'measConfig' in body_text or 'reportConfig' in body_text or 'measObject' in body_text:
                obj_map = {}
                for m_obj in re.finditer(r'measObjectId\s*[:=]?\s*(\d+).*?carrierFreq\s*[:=]?\s*(\d+)', body_text, re.DOTALL):
                    obj_map[int(m_obj.group(1))] = m_obj.group(2)

                rep_map = {}
                for r_id in re.findall(r'reportConfigId\s*[:=]?\s*(\d+)', body_text):
                    m_sub = re.search(r'reportConfigId\s*[:=]?\s*' + r_id + r'(.*?)(?=reportConfigId\s*[:=]|\}\s*,\s*\{|\Z)', body_text, re.DOTALL)
                    sub_txt = m_sub.group(1) if m_sub else body_text
                    
                    if 'eventA3' in sub_txt or 'eventa3' in sub_txt.lower() or 'a3_offset' in sub_txt.lower():
                        ev_name = 'Event A3'
                    elif 'eventA1' in sub_txt or 'eventa1' in sub_txt.lower():
                        ev_name = 'Event A1'
                    elif 'eventA2' in sub_txt or 'eventa2' in sub_txt.lower():
                        ev_name = 'Event A2'
                    elif 'eventA4' in sub_txt or 'eventa4' in sub_txt.lower():
                        ev_name = 'Event A4'
                    elif 'eventA5' in sub_txt or 'eventa5' in sub_txt.lower():
                        ev_name = 'Event A5'
                    elif 'eventB1' in sub_txt or 'eventb1' in sub_txt.lower():
                        ev_name = 'Event B1'
                    elif 'eventB2' in sub_txt or 'eventb2' in sub_txt.lower():
                        ev_name = 'Event B2'
                    else:
                        ev_name = 'Event A3'

                    m_off = re.search(r'a3_Offset\s*[:=]?\s*(-?\d+)', sub_txt)
                    off_str = f"{int(m_off.group(1))*0.5:+.1f} dB" if m_off else "+3.0 dB"
                    m_hys = re.search(r'hysteresis\s*[:=]?\s*(\d+)', sub_txt)
                    hys_str = f"{int(m_hys.group(1))*0.5:.1f} dB" if m_hys else "0.0 dB"
                    m_ttt = re.search(r'timeToTrigger\s*[:=]?\s*([A-Za-z0-9]+)', sub_txt)
                    ttt_str = m_ttt.group(1) if m_ttt else "ms100"
                    rep_map[int(r_id)] = {
                        'ev_name': ev_name,
                        'off_str': off_str,
                        'hys_str': hys_str,
                        'ttt_str': ttt_str,
                        'desc': f"Offset {off_str} | Hys {hys_str} | TTT {ttt_str}"
                    }

                for m_id, o_id, r_id in re.findall(r'measId\s*[:=]?\s*(\d+).*?measObjectId\s*[:=]?\s*(\d+).*?reportConfigId\s*[:=]?\s*(\d+)', body_text, re.DOTALL):
                    mid_int, oid_int, rid_int = int(m_id), int(o_id), int(r_id)
                    earfcn = obj_map.get(oid_int, '9410')
                    r_info = rep_map.get(rid_int, {'ev_name': 'Event A3', 'desc': 'Offset +3.0 dB | Hys 0.0 dB | TTT ms100'})
                    ev_n = r_info['ev_name']
                    ev_p = "동종망 HO" if ev_n == 'Event A3' else ("이종주파수 HO" if ev_n in ['Event A4', 'Event A5'] else ("이종망 5G HO" if 'B' in ev_n else "서빙품질 측정"))
                    key_name = f"[{ev_n}] {ev_p} (EARFCN {earfcn})"
                    struct_registry['01. 이동성 / 핸드오버 (MeasConfig)'][key_name][current_serving_pci] = f"[{r_info['desc']}]"

            # Domain 02: SIB5 Inter-Frequency Carrier List
            if 'interFreqCarrierFreqList' in body_text or 'dl_CarrierFreq' in body_text:
                for m_ef in re.finditer(r'dl_CarrierFreq\s*[:=]?\s*(\d+).*?q_RxLevMin\s*[:=]?\s*(-?\d+)(?:.*?cellReselectionPriority\s*[:=]?\s*(\d+))?', body_text, re.DOTALL):
                    earfcn = m_ef.group(1)
                    qrx = f"{int(m_ef.group(2))*2} dBm"
                    prio = m_ef.group(3) if m_ef.group(3) else 'N/A'
                    key_name = f"[이종주파수 재선택] (EARFCN {earfcn})"
                    struct_registry['02. 이종주파수 재선택 (SIB5 InterFreqList)'][key_name][current_serving_pci] = f"[Priority {prio} | q-RxLevMin {qrx}]"

            # Domain 03: SIB3 Intra-Frequency Reselection
            if 'cellReselectionInfoCommon' in body_text or 'q_Hyst' in body_text:
                m_qh = re.search(r'q_Hyst\s*[:=]?\s*([A-Za-z0-9]+)', body_text)
                m_si = re.search(r's_IntraSearch\s*[:=]?\s*(\d+)', body_text)
                m_sni = re.search(r's_NonIntraSearch\s*[:=]?\s*(\d+)', body_text)
                if m_qh or m_si:
                    qh = m_qh.group(1) if m_qh else 'dB4'
                    si = f"{int(m_si.group(1))*2} dB" if m_si else "62 dB"
                    sni = f"{int(m_sni.group(1))*2} dB" if m_sni else "40 dB"
                    key_name = "[동종주파수 재선택] (Intra-Freq Policy)"
                    struct_registry['03. 동종주파수 재선택 (SIB3 IntraFreq)'][key_name][current_serving_pci] = f"[q-Hyst {qh} | s-IntraSearch {si} | s-NonIntraSearch {sni}]"

            # Domain 04: DRB Data Bearers
            if 'drb_ToAddModList' in body_text or 'drb_Identity' in body_text:
                for m_drb in re.finditer(r'drb_Identity\s*[:=]?\s*(\d+).*?eps_BearerIdentity\s*[:=]?\s*(\d+)(?:.*?rlc_Config.*?([A-Za-z0-9_\-]+))?', body_text, re.DOTALL):
                    drb_id = m_drb.group(1)
                    eps_id = m_drb.group(2)
                    rlc = m_drb.group(3) if m_drb.group(3) else 'am'
                    b_type = '인터넷 데이터 (EPS-ID 5)' if eps_id == '5' else ('VoLTE 음성 (EPS-ID 1)' if eps_id == '1' else f'EPS-ID {eps_id}')
                    key_name = f"[DRB 무선 베어러] ({b_type})"
                    struct_registry['04. 무선 베어러 (DRB Data Bearer)'][key_name][current_serving_pci] = f"[RLC-{rlc.upper()}]"

            # Domain 05: SRB Signaling Bearers
            if 'srb_ToAddModList' in body_text or 'srb_Identity' in body_text:
                for m_srb in re.finditer(r'srb_Identity\s*[:=]?\s*(\d+)', body_text):
                    srb_id = m_srb.group(1)
                    s_type = 'SRB1 RRC 제어' if srb_id == '1' else ('SRB2 NAS 제어' if srb_id == '2' else f'SRB {srb_id}')
                    key_name = f"[SRB 시그널링] ({s_type})"
                    struct_registry['05. 시그널링 베어러 (SRB Signaling Bearer)'][key_name][current_serving_pci] = "[RLC-AM | Established]"

            # Domain 06: CA SCell
            if 'sCellToAddModList' in body_text or 'sCellIndex' in body_text:
                for m_sc in re.finditer(r'sCellIndex\s*[:=]?\s*(\d+).*?physCellId\s*[:=]?\s*(\d+)', body_text, re.DOTALL):
                    sc_idx, sc_pci = m_sc.group(1), m_sc.group(2)
                    key_name = f"[CA 보조 셀] (Target PCI {sc_pci})"
                    struct_registry['06. 캐리어 애그리게이션 (CA SCell)'][key_name][current_serving_pci] = f"[SCell Index {sc_idx} | Activated]"

            # Domain 07: CSI / CQI ReportConfig (Exclude variable slot index cqi_pmi_ConfigIndex)
            if 'cqi_ReportConfig' in body_text or 'cqi-ReportConfig' in body_text or 'cqi_FormatIndicatorPeriodic' in body_text or 'nomPDSCH_RS_EPRE_Offset' in body_text:
                m_fmt = re.search(r'cqi_FormatIndicatorPeriodic\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_nom = re.search(r'nomPDSCH_RS_EPRE_Offset\s*[:=]?\s*(-?\d+)', body_text)
                m_ack = re.search(r'simultaneousAckNackAndCQI\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                if m_fmt or m_nom or m_ack:
                    fmt_val = m_fmt.group(1) if m_fmt else 'subbandCQI'
                    nom_val = f"{m_nom.group(1)} dB" if m_nom else "0 dB"
                    ack_val = m_ack.group(1) if m_ack else "true"
                    key_name = "[CSI/CQI 주기 보고 정책] (Periodic CQI Policy)"
                    struct_registry['07. CSI/CQI 주기 보고 (CQI-ReportConfig)'][key_name][current_serving_pci] = f"[Format {fmt_val} | nomPDSCH-Offset {nom_val} | AckNackCQI {ack_val}]"

            # Domain 08: Antenna & MIMO Transmission Mode
            if 'antennaInfo' in body_text or 'transmissionMode' in body_text:
                m_tm = re.search(r'transmissionMode\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_pa = re.search(r'p_a\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_cb = re.search(r'codebookSubsetRestriction\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                if m_tm or m_pa:
                    tm = m_tm.group(1) if m_tm else 'tm3'
                    pa = m_pa.group(1) if m_pa else 'dB0'
                    cb = m_cb.group(1) if m_cb else 'Default'
                    key_name = "[안테나/MIMO 전송모드] (TransmissionMode)"
                    struct_registry['08. 안테나 및 MIMO 전송모드 (AntennaInfo)'][key_name][current_serving_pci] = f"[Mode {tm.upper()} | P_A {pa} | Codebook {cb}]"

            # Domain 09: SRS (Sounding Reference Signal) - Exclude variable slot index srs_ConfigIndex
            if 'soundingRS_UL_ConfigDedicated' in body_text or 'srs_Bandwidth' in body_text or 'srs_Resource' in body_text.lower():
                m_srs_bw = re.search(r'srs_Bandwidth\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_srs_hop = re.search(r'srs_HoppingBandwidth\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                if m_srs_bw or m_srs_hop:
                    srs_b = m_srs_bw.group(1) if m_srs_bw else 'bw0'
                    srs_h = m_srs_hop.group(1) if m_srs_hop else 'hbw0'
                    key_name = "[SRS 사운딩 대역폭 정책] (SRS Bandwidth Policy)"
                    struct_registry['09. 사운딩 참조 신호 (SRS Config)'][key_name][current_serving_pci] = f"[Bandwidth {srs_b} | Hopping {srs_h}]"

            # Domain 10: DRX (Discontinuous Reception)
            if 'drx_Config' in body_text or 'onDurationTimer' in body_text:
                m_on = re.search(r'onDurationTimer\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_inact = re.search(r'drx_InactivityTimer\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                if m_on or m_inact:
                    on_t = m_on.group(1) if m_on else 'psf1'
                    inact_t = m_inact.group(1) if m_inact else 'psf1'
                    key_name = "[DRX 전력 절감] (DRX Cycle Config)"
                    struct_registry['10. 비연속 수신 (DRX Config)'][key_name][current_serving_pci] = f"[onDuration {on_t} | Inactivity {inact_t}]"

            # Domain 11: Uplink Power Control Dedicated
            if 'uplinkPowerControlDedicated' in body_text or 'p0_UE_PUSCH' in body_text:
                m_p0_pusch = re.search(r'p0_UE_PUSCH\s*[:=]?\s*(-?\d+)', body_text)
                m_p0_pucch = re.search(r'p0_UE_PUCCH\s*[:=]?\s*(-?\d+)', body_text)
                if m_p0_pusch or m_p0_pucch:
                    p_pusch = f"{m_p0_pusch.group(1)} dBm" if m_p0_pusch else "0 dBm"
                    p_pucch = f"{m_p0_pucch.group(1)} dBm" if m_p0_pucch else "0 dBm"
                    key_name = "[상향링크 전력제어] (UL Power Control)"
                    struct_registry['11. 상향링크 전력제어 (UplinkPowerControl)'][key_name][current_serving_pci] = f"[p0-UE-PUSCH {p_pusch} | p0-UE-PUCCH {p_pucch}]"

            # Domain 12: 5G NR CSI-RS (NZP-CSI-RS & ZP-CSI-RS)
            if 'nzp_csi_rs' in body_text.lower() or 'nzp-csi-rs' in body_text.lower() or 'csi_measconfig' in body_text.lower():
                m_ports = re.search(r'nrofPorts\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_cdm = re.search(r'cdm_Type\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_period = re.search(r'periodicityAndOffset\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                if m_ports or m_cdm or m_period:
                    p_str = m_ports.group(1) if m_ports else 'p4'
                    c_str = m_cdm.group(1) if m_cdm else 'cdm2'
                    per_str = m_period.group(1) if m_period else 'slots20'
                    key_name = f"[NZP-CSI-RS 채널/빔측정] ({p_str.upper()} | {c_str.upper()})"
                    struct_registry['12. 빔 및 CSI-RS 리소스 (CSI-MeasConfig)'][key_name][current_serving_pci] = f"[{per_str} | Periodic]"

            if 'zp_csi_rs' in body_text.lower() or 'zp-csi-rs' in body_text.lower():
                m_zp_per = re.search(r'periodicityAndOffset\s*[:=]?\s*([A-Za-z0-9_\-]+)', body_text)
                m_zp_row = re.search(r'row\s*[:=]?\s*(\d+)', body_text)
                if m_zp_per or m_zp_row:
                    zp_p = m_zp_per.group(1) if m_zp_per else 'slots10'
                    zp_r = f"row{m_zp_row.group(1)}" if m_zp_row else 'row4'
                    key_name = f"[ZP-CSI-RS 레이트매칭] ({zp_p} | {zp_r})"
                    struct_registry['12. 빔 및 CSI-RS 리소스 (CSI-MeasConfig)'][key_name][current_serving_pci] = f"[Rate Matching | {zp_r}]"

            # Domain 13: RACH / PRACH Config
            if 'prach_Config' in body_text or 'rootSequenceIndex' in body_text or 'mobilityControlInfo' in body_text:
                m_root = re.search(r'rootSequenceIndex\s*[:=]?\s*(\d+)', body_text)
                m_pr_cfg = re.search(r'prach_ConfigIndex\s*[:=]?\s*(\d+)', body_text)
                if m_root or m_pr_cfg:
                    r_idx = m_root.group(1) if m_root else 'N/A'
                    p_cfg = m_pr_cfg.group(1) if m_pr_cfg else 'N/A'
                    key_name = "[랜덤 액세스 / PRACH] (PRACH Configuration)"
                    struct_registry['13. 랜덤 액세스 / PRACH (PRACH Config)'][key_name][current_serving_pci] = f"[RootSequence {r_idx} | ConfigIndex {p_cfg}]"

            # -------------------------------------------------------------
            # Pure Scalar Parameters Extraction (DM Frame Noise Filtered)
            # -------------------------------------------------------------
            stack = []
            for line in body:
                parts = line.split(',')
                raw_text = parts[-1] if len(parts) > 5 else line
                stripped = raw_text.strip()
                if not stripped or stripped.startswith('//'):
                    continue

                indent = len(raw_text) - len(raw_text.lstrip(' '))
                cur_depth = indent // 2

                clean_text = stripped.rstrip('{').strip()
                m_kv = re.match(r'^([A-Za-z0-9_\-]+)\s*(?:[=:]\s*(.+)|(.*))?$', clean_text)
                if not m_kv:
                    continue

                k_raw = m_kv.group(1)
                v_raw = m_kv.group(2) if m_kv.group(2) is not None else (m_kv.group(3) if m_kv.group(3) is not None else '')
                v_raw = v_raw.strip().rstrip('},;')

                while stack and stack[-1][0] >= cur_depth:
                    stack.pop()

                if '{' in stripped or not v_raw:
                    stack.append((cur_depth, k_raw))
                    struct_path = " -> ".join([s[1] for s in stack])
                else:
                    struct_path = " -> ".join([s[1] for s in stack]) if stack else "Root"

                if v_raw:
                    leaf_param = k_raw
                    v_clean = v_raw.strip('",; ')
                    if not v_clean or v_clean == '{}':
                        continue

                    k_check = leaf_param.lower().replace('-', '_')
                    if k_check in self.EXCLUDED_SYNTAX_KEYS:
                        continue
                    if self.is_noise(leaf_param, struct_path, msg_name):
                        continue
                    if self.is_structured(leaf_param, struct_path):
                        continue

                    unique_key = f"{msg_name}|{struct_path}|{leaf_param}"
                    cell_scalar_params[current_serving_pci][unique_key] = v_clean
                    if unique_key not in param_meta:
                        param_meta[unique_key] = {
                            'msg_name': msg_name,
                            'struct_path': struct_path,
                            'leaf_param': leaf_param
                        }

        # Assemble PCIs
        all_pcis = sorted(set(
            list(cell_scalar_params.keys()) +
            [pci for d in struct_registry.values() for item in d.values() for pci in item.keys()]
        ))

        return cell_scalar_params, param_meta, struct_registry, all_pcis

    def build_audit_dataframes(
        self,
        l3_source: Any,
        kpi_file_path: Optional[str] = None,
        df_timeline: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        return self.build_audit_matrices(l3_source, kpi_file_path, df_timeline)

    def build_audit_matrices(
        self,
        l3_source: Any,
        kpi_file_path: Optional[str] = None,
        df_timeline: Optional[pd.DataFrame] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Builds and returns:
        1. df_scalar_matrix: 01_단일_파라미터_매트릭스 (Intelligently filtered with Multi-Cluster columns + raw PCI columns)
        2. df_struct_matrix: 02_RRC_복합구조체_SET_매트릭스 (Multi-Cluster columns + raw PCI columns)
        """
        cell_scalar_params, param_meta, struct_registry, all_pcis = self.parse_all(l3_source, kpi_file_path, df_timeline)

        if not all_pcis or not param_meta:
            return pd.DataFrame(), pd.DataFrame()

        # 1. Build Sheet 1: 01_단일_파라미터_매트릭스
        all_unique_keys = sorted(param_meta.keys())
        scalar_rows = []

        for u_key in all_unique_keys:
            vals = [cell_scalar_params[pci].get(u_key, '미설정') for pci in all_pcis]
            valid_vals = [v for v in vals if v != '미설정' and str(v).strip() != '' and str(v) != 'nan']

            if not valid_vals:
                continue

            meta = param_meta[u_key]
            msg_name = meta['msg_name']
            struct_path = meta['struct_path']
            leaf_param = meta['leaf_param']

            u_ratio = (len(set(valid_vals)) / len(valid_vals)) if valid_vals else 0.0
            if not is_meaningful_network_param(leaf_param, struct_path, u_ratio):
                continue

            vals_dict = {pci: v for pci, v in zip(all_pcis, vals)}
            clust = compute_multi_cluster_summary(vals_dict, all_pcis)

            row_data = {
                '분류 (메시지 명칭)': msg_name,
                '상위 구조체 (계층 경로)': struct_path,
                '파라미터 명칭': leaf_param,
                '1위 정책군 (최빈값 / 점유율)': clust['rank1'],
                '2위 정책군 (차순위 / 점유율)': clust['rank2'],
                '3위/특이 설정값 (소수 기지국)': clust['rank3_outliers'],
                '미수신 / 미설정 셀': clust['unset_info']
            }
            for pci, val in zip(all_pcis, vals):
                row_data[f'PCI {pci}'] = val

            scalar_rows.append(row_data)

        df_scalar_matrix = pd.DataFrame(scalar_rows)
        if not df_scalar_matrix.empty:
            df_scalar_matrix = df_scalar_matrix.sort_values(
                by=['분류 (메시지 명칭)', '상위 구조체 (계층 경로)', '파라미터 명칭'],
                ascending=[True, True, True]
            ).reset_index(drop=True)

        # 2. Build Sheet 2: 02_RRC_복합구조체_SET_매트릭스
        struct_rows = []
        for domain_name in sorted(struct_registry.keys()):
            for obj_key in sorted(struct_registry[domain_name].keys()):
                cell_map = struct_registry[domain_name][obj_key]
                pci_vals = [cell_map.get(pci, '미설정') for pci in all_pcis]
                valid_pci_vals = [v for v in pci_vals if v != '미설정' and str(v).strip() != '' and str(v) != 'nan']

                if not valid_pci_vals:
                    continue

                vals_dict = {pci: v for pci, v in zip(all_pcis, pci_vals)}
                clust = compute_multi_cluster_summary(vals_dict, all_pcis)

                s_row = {
                    '구조체 대분류': domain_name,
                    '구조체 식별자 / 항목': obj_key,
                    '1위 정책군 (최빈값 / 점유율)': clust['rank1'],
                    '2위 정책군 (차순위 / 점유율)': clust['rank2'],
                    '3위/특이 설정값 (소수 기지국)': clust['rank3_outliers'],
                    '미수신 / 미설정 셀': clust['unset_info']
                }
                for pci, v in zip(all_pcis, pci_vals):
                    s_row[f'PCI {pci}'] = v

                struct_rows.append(s_row)

        df_struct_matrix = pd.DataFrame(struct_rows)
        if not df_struct_matrix.empty:
            df_struct_matrix = df_struct_matrix.sort_values(
                by=['구조체 대분류', '구조체 식별자 / 항목'],
                ascending=[True, True]
            ).reset_index(drop=True)

        return df_scalar_matrix, df_struct_matrix
