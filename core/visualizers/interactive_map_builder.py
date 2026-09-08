# -*- coding: utf-8 -*-
r"""
File: 4_Optis_AI_Analyzer/core/visualizers/interactive_map_builder.py
Description: Master Timeline (df_timeline) Direct-Linked 2D GIS Interactive Map Engine
- 100% Traffic vs IDLE Phase Aware
- 1-Second Grid Clean Alignment (Zero Time Duplication)
- Real Ping-Pong Full Path (e.g. 372 ➔ 371 ➔ 372) at Exact Timestamp
- Sidebar Title: '📊 지도 표시 항목' (Default: RSRP)
- 5G NSA Dual LTE/NR Layer Extension
- M1~M4 One-Stop Switcher Tabs
"""

import os
import sys
import re
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
from core.quality_criteria_registry import (
    get_all_map_criteria_dict,
    get_rsrp_evaluation,
    get_sinr_evaluation,
    evaluate_tier,
    LTE_SERVING_RSRP_CRITERIA,
    NR_SS_RSRP_CRITERIA,
    is_clean_rf_condition,
    is_pilot_pollution_condition,
    is_weak_coverage_condition,
    is_rapid_rsrp_drop,
    evaluate_rf_situation
)


def safe_read_csv(file_path: Optional[str]) -> Optional[pd.DataFrame]:
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path, encoding='utf-8', low_memory=False, on_bad_lines='skip')
        if df.empty:
            df = pd.read_csv(file_path, encoding='cp949', low_memory=False, on_bad_lines='skip')
        return df
    except Exception:
        try:
            return pd.read_csv(file_path, encoding='cp949', low_memory=False, on_bad_lines='skip')
        except Exception:
            return None


PCI_COLOR_PALETTE = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899", "#06B6D4",
    "#F97316", "#14B8A6", "#6366F1", "#84CC16", "#D946EF", "#EAB308", "#64748B",
    "#0EA5E9", "#F43F5E", "#22C55E", "#A855F7", "#FB923C", "#2DD4BF", "#4F46E5",
    "#65A30D", "#C026D3", "#CA8A04", "#475569", "#2563EB", "#DC2626", "#059669",
    "#D97706", "#7C3AED", "#DB2777", "#0891B2", "#EA580C"
]


class InteractiveMapBuilder:
    """
    Multi-Port Integrated 2D Leaflet GIS Map Builder using Master Timeline (df_timeline).
    """

    def __init__(self):
        pass

    def detect_scenario_and_model(self, df_timeline: pd.DataFrame, csvs: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Determines scenario and traffic model name directly from df_timeline SSOT attributes/columns.
        """
        traffic_model = 'DL'
        if df_timeline is not None and not df_timeline.empty:
            if hasattr(df_timeline, 'attrs') and 'Traffic_Model' in df_timeline.attrs:
                traffic_model = df_timeline.attrs['Traffic_Model']
            elif 'Traffic_Model' in df_timeline.columns and not df_timeline['Traffic_Model'].dropna().empty:
                traffic_model = str(df_timeline['Traffic_Model'].dropna().iloc[0]).upper()

        if traffic_model == 'SST':
            return {
                "scenario": "SST",
                "traffic_model": "SPEED TEST (SST)"
            }
        elif traffic_model.startswith('VOICE'):
            voice_dir = "발신 (MO)" if "MO" in traffic_model else ("착신 (MT)" if "MT" in traffic_model else "Voice")
            return {
                "scenario": "Voice",
                "traffic_model": f"VoLTE {voice_dir}"
            }
        elif traffic_model in ['DL_Long_Call', 'DL_LONG_CALL']:
            return {
                "scenario": "DL",
                "traffic_model": "DL LONG CALL (연속 호)"
            }
        elif traffic_model in ['DL_Short_Call', 'DL_SHORT_CALL']:
            return {
                "scenario": "DL",
                "traffic_model": "DL SHORT CALL (반복 호)"
            }
        elif traffic_model in ['UL_Long_Call', 'UL_LONG_CALL']:
            return {
                "scenario": "UL",
                "traffic_model": "UL LONG CALL (연속 호)"
            }
        elif traffic_model in ['UL_Short_Call', 'UL_SHORT_CALL', 'UL']:
            return {
                "scenario": "UL",
                "traffic_model": "UL SHORT CALL (반복 호)"
            }
        elif traffic_model == 'PING':
            return {
                "scenario": "Ping",
                "traffic_model": "PING TEST"
            }
        else:
            return {
                "scenario": "DL",
                "traffic_model": "DL LONG CALL (연속 호)"
            }

    @staticmethod
    def _find_col(df: pd.DataFrame, candidates: List[str], exclude: Optional[List[str]] = None) -> Optional[str]:
        if df is None or df.empty:
            return None
        # 1. Exact match
        for cand in candidates:
            for col in df.columns:
                if cand.lower() == str(col).strip().lower():
                    return col
        # 2. Normalized alphanumeric match
        for cand in candidates:
            cand_clean = re.sub(r'[^a-zA-Z0-9가-힣]', '', cand).lower()
            for col in df.columns:
                col_str = str(col).strip()
                if exclude and any(ex.lower() in col_str.lower() for ex in exclude):
                    continue
                col_clean = re.sub(r'[^a-zA-Z0-9가-힣]', '', col_str).lower()
                if cand_clean and (cand_clean in col_clean or col_clean in cand_clean):
                    return col
        return None

    @staticmethod
    def extract_bandwidth_from_timeline(df_timeline: pd.DataFrame) -> Tuple[float, float]:
        """Extracts combined LTE bandwidth (PCell + SCells) and NR bandwidth (MHz)."""
        lte_bw = 0.0
        nr_bw = 0.0
        if df_timeline is None or df_timeline.empty:
            return 60.0, 100.0

        # 1. LTE PCell BW
        pcell_c = next((c for c in df_timeline.columns if 'PCell' in c and 'BandWidth' in c and 'LTE' in c), None)
        if not pcell_c:
            pcell_c = next((c for c in df_timeline.columns if ('BandWidth(DL)' in c or 'BandWidth' in c) and 'LTE' in c), None)
        if pcell_c:
            s = pd.to_numeric(df_timeline[pcell_c], errors='coerce').dropna()
            if not s.empty and s.mode().iloc[0] > 0:
                lte_bw += float(s.mode().iloc[0])

        # LTE SCell BWs
        for s_idx in range(1, 5):
            sc_col = next((c for c in df_timeline.columns if f'SCell[{s_idx}]' in c and 'BandWidth' in c and 'LTE' in c), None)
            if sc_col:
                s_val = pd.to_numeric(df_timeline[sc_col], errors='coerce').dropna()
                if not s_val.empty and s_val.mode().iloc[0] > 0:
                    lte_bw += float(s_val.mode().iloc[0])

        # 2. NR PCell BW
        nr_col = next((c for c in df_timeline.columns if ('5G' in c or 'NR' in c) and 'BandWidth' in c), None)
        if nr_col:
            s_nr = pd.to_numeric(df_timeline[nr_col], errors='coerce').dropna()
            if not s_nr.empty and s_nr.mode().iloc[0] > 0:
                nr_bw += float(s_nr.mode().iloc[0])

        if lte_bw <= 0:
            lte_bw = 60.0
        if nr_bw <= 0:
            nr_bw = 100.0

        return lte_bw, nr_bw

    def extract_trajectory_from_timeline(
        self,
        df_timeline: pd.DataFrame,
        scenario: str = "DL",
        port_name: str = "M1"
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes 100% 1-second continuous trajectory points from Master Timeline (df_timeline).
        """
        if df_timeline.empty:
            return []

        col_time = self._find_col(df_timeline, ['TIME_STAMP', 'Time', 'TIME', 'Timestamp', '시간', 'Time_Stamp']) or df_timeline.columns[0]
        col_lat = self._find_col(df_timeline, ['Lat', 'LAT', '위도'])
        col_lon = self._find_col(df_timeline, ['Lon', 'LON', '경도'])
        col_speed = self._find_col(df_timeline, ['Speed', 'SPEED', '속도'])

        col_nr_pci = self._find_col(df_timeline, ['NR_Serving_PCI', 'NR_PCI', '5G_PCI', 'NR Serving PCI'])
        col_lte_pci = self._find_col(df_timeline, ['LTE_Serving_PCI', 'LTE_PCI', 'Anchor_PCI', 'LTE Serving PCI'])
        col_pci = self._find_col(df_timeline, ['Serving_PCI', 'PCI', 'Serving PCI']) or col_nr_pci or col_lte_pci

        col_nr_rsrp = self._find_col(df_timeline, ['NR_SS_RSRP', 'SS_RSRP', 'NR_RSRP', 'SS-RSRP', 'NR Serving RSRP'])
        col_lte_rsrp = self._find_col(df_timeline, ['LTE_Serving_RSRP', 'LTE_RSRP', 'LTE RSRP', 'Serving RSRP'])
        col_rsrp = col_nr_rsrp or col_lte_rsrp or self._find_col(df_timeline, ['RSRP', 'Serving_RSRP'])

        col_nr_sinr = self._find_col(df_timeline, ['NR_SS_SINR', 'SS_SINR', 'NR_SINR', 'SS-SINR', 'NR Serving SINR'])
        col_lte_sinr = self._find_col(df_timeline, ['LTE_Serving_SINR', 'LTE_SINR', 'LTE SINR', 'Serving SINR'])
        col_sinr = col_nr_sinr or col_lte_sinr or self._find_col(df_timeline, ['SINR', 'Serving_SINR'])

        col_rsrq = self._find_col(df_timeline, ['SS_RSRQ', 'RSRQ', 'Serving_RSRQ'])

        # Throughput: strictly restricted to 3 standard categories (LTE Total MAC, NR Total MAC, PDCP Total)
        col_pdcp = self._find_col(df_timeline, [
            '[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]',
            '[Call & LTE KPI PDCP DL Throughput [Mbps]]',
            'PDCP_DL_Tput', 'PDCP_Total_DL_Tput', 'PDCP DL 속도 (Mbps)', 'PDCP DL 속도'
        ])
        col_pdcp_ul = self._find_col(df_timeline, [
            '[Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]]',
            '[Call & LTE KPI PDCP UL Throughput [Mbps]]',
            'PDCP_UL_Tput', 'PDCP UL 속도 (Mbps)', 'PDCP UL 속도'
        ])
        col_nr_mac = self._find_col(df_timeline, [
            '[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]',
            'NR_MAC_DL_Tput', '5G NR MAC Total (Mbps)', 'NR MAC DL 속도 (Mbps)', 'NR MAC DL 속도'
        ])
        col_lte_mac = self._find_col(df_timeline, [
            '[Call & LTE KPI MAC DL Throughput [Mbps]]',
            '[Call & LTE KPI Total Info Layer2 MAC DL Throughput [Mbps]]',
            'LTE_MAC_DL_Tput', 'LTE MAC Total (Mbps)', 'LTE MAC DL 속도 (Mbps)', 'LTE MAC DL 속도'
        ])

        # Resolve primary DL throughput strictly based on Network Mode
        net_mode_hint = str(df_timeline.attrs.get('Network_Mode', '')).upper() if hasattr(df_timeline, 'attrs') else ''
        if not net_mode_hint and 'Network_Mode' in df_timeline.columns:
            m_s = df_timeline['Network_Mode'].dropna()
            if not m_s.empty:
                net_mode_hint = str(m_s.iloc[0]).upper()

        if 'LTE' in net_mode_hint and 'NSA' not in net_mode_hint:
            col_dl = col_lte_mac or col_pdcp
        elif 'SA' in net_mode_hint or ('NR' in net_mode_hint and 'NSA' not in net_mode_hint):
            col_dl = col_nr_mac or col_pdcp
        else:
            col_dl = col_pdcp or col_nr_mac or col_lte_mac

        col_ul = col_pdcp_ul

        # Voice
        col_mos = self._find_col(df_timeline, ['MOS', 'POLQA'])
        col_jitter = self._find_col(df_timeline, ['Jitter', 'JITTER'])
        col_loss = self._find_col(df_timeline, ['Packet_Loss', 'Loss (%)', 'Loss'])

        col_call_no = self._find_col(df_timeline, ['Call_No', '호 번호'])
        col_phase = self._find_col(df_timeline, ['Call_Phase', '호 상태'])

        points = []
        last_valid_lat = None
        last_valid_lon = None

        for idx, row in df_timeline.iterrows():
            ts = row[col_time]
            if isinstance(ts, (pd.Timestamp, datetime)):
                t_str = ts.strftime('%H:%M:%S')
                dt_obj = ts
            else:
                t_str = str(ts).split(" ")[-1].split(".")[0]
                dt_obj = pd.to_datetime(ts, errors='coerce')

            lat = float(row[col_lat]) if col_lat and pd.notna(row[col_lat]) else None
            lon = float(row[col_lon]) if col_lon and pd.notna(row[col_lon]) else None

            if lat is not None and lon is not None and 33.0 <= lat <= 39.0 and 124.0 <= lon <= 132.0:
                last_valid_lat = lat
                last_valid_lon = lon
            else:
                lat = last_valid_lat
                lon = last_valid_lon

            speed_val = round(float(row[col_speed]), 1) if col_speed and pd.notna(row[col_speed]) else None
            pci_val = int(row[col_pci]) if col_pci and pd.notna(row[col_pci]) and float(row[col_pci]) > 0 else 0
            nr_pci_val = int(row[col_nr_pci]) if col_nr_pci and pd.notna(row[col_nr_pci]) and float(row[col_nr_pci]) > 0 else pci_val
            lte_pci_val = int(row[col_lte_pci]) if col_lte_pci and pd.notna(row[col_lte_pci]) and float(row[col_lte_pci]) > 0 else pci_val

            rsrp_val = round(float(row[col_rsrp]), 1) if col_rsrp and pd.notna(row[col_rsrp]) else -140.0
            nr_rsrp_val = round(float(row[col_nr_rsrp]), 1) if col_nr_rsrp and pd.notna(row[col_nr_rsrp]) else rsrp_val
            lte_rsrp_val = round(float(row[col_lte_rsrp]), 1) if col_lte_rsrp and pd.notna(row[col_lte_rsrp]) else rsrp_val

            sinr_val = round(float(row[col_sinr]), 1) if col_sinr and pd.notna(row[col_sinr]) else -20.0
            nr_sinr_val = round(float(row[col_nr_sinr]), 1) if col_nr_sinr and pd.notna(row[col_nr_sinr]) else sinr_val
            lte_sinr_val = round(float(row[col_lte_sinr]), 1) if col_lte_sinr and pd.notna(row[col_lte_sinr]) else sinr_val

            rsrq_val = round(float(row[col_rsrq]), 1) if col_rsrq and pd.notna(row[col_rsrq]) else -20.0

            def _norm_mbps(val, col_name):
                if val is None or pd.isna(val):
                    return None
                try:
                    f = float(val)
                    if col_name and 'kbps' in str(col_name).lower():
                        return round(f / 1000.0, 1)
                    if f > 10000.0:
                        return round(f / 1000.0, 1)
                    return round(f, 1)
                except (ValueError, TypeError):
                    return None

            dl_tp = _norm_mbps(row[col_dl], col_dl) if col_dl and pd.notna(row[col_dl]) else None
            ul_tp = _norm_mbps(row[col_ul], col_ul) if col_ul and pd.notna(row[col_ul]) else None
            pdcp_tp = _norm_mbps(row[col_pdcp], col_pdcp) if col_pdcp and pd.notna(row[col_pdcp]) else (dl_tp if dl_tp is not None else 0.0)
            nr_mac_tp = _norm_mbps(row[col_nr_mac], col_nr_mac) if col_nr_mac and pd.notna(row[col_nr_mac]) else 0.0
            lte_mac_tp = _norm_mbps(row[col_lte_mac], col_lte_mac) if col_lte_mac and pd.notna(row[col_lte_mac]) else (dl_tp if dl_tp is not None else 0.0)

            mos_raw = float(row[col_mos]) if col_mos and pd.notna(row[col_mos]) else None
            mos_val = round(min(5.0, mos_raw), 2) if (mos_raw is not None and mos_raw > 0) else None
            jit_val = round(float(row[col_jitter]), 1) if col_jitter and pd.notna(row[col_jitter]) else None
            loss_val = round(float(row[col_loss]), 1) if col_loss and pd.notna(row[col_loss]) else None

            call_label = str(row[col_call_no]) if col_call_no and pd.notna(row[col_call_no]) else "Call 1"
            phase_label = str(row[col_phase]) if col_phase and pd.notna(row[col_phase]) else "Traffic"

            points.append({
                "idx": idx,
                "time": t_str,
                "dt": dt_obj,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "speed": speed_val if speed_val is not None else 0,
                "call_no": call_label,
                "call_phase": phase_label,
                "pci": pci_val,
                "nr_pci": nr_pci_val,
                "lte_pci": lte_pci_val,
                "rsrp": rsrp_val,
                "nr_rsrp": nr_rsrp_val,
                "lte_rsrp": lte_rsrp_val,
                "sinr": sinr_val,
                "nr_sinr": nr_sinr_val,
                "lte_sinr": lte_sinr_val,
                "rsrq": rsrq_val,
                "mos": mos_val,
                "jitter": jit_val,
                "loss": loss_val,
                "dl_tp": dl_tp,
                "ul_tp": ul_tp,
                "pdcp_tp": pdcp_tp,
                "nr_mac_tp": nr_mac_tp,
                "lte_mac_tp": lte_mac_tp,
                "sip_msg": str(row['SIP_Msg']) if 'SIP_Msg' in row and pd.notna(row['SIP_Msg']) else "",
                "l3_sig": str(row['L3_Signaling']) if 'L3_Signaling' in row and pd.notna(row['L3_Signaling']) else ""
            })

        return points

    def extract_incident_episodes(
        self,
        episodes: List[Dict[str, Any]],
        points: List[Dict[str, Any]],
        scenario: str,
        network_mode: str,
        csvs: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts episodes mapped precisely by timestamp with universal raw L3 signaling and pure real RF points.
        """
        if not points:
            return []

        # Universal raw L3 & SIP signaling stream extraction directly from master timeline points
        l3_sig_by_sec = {}
        l3_note_by_sec = {}
        for p in points:
            t_sec = p.get('time')
            if not t_sec:
                continue
            sig_list = []
            if p.get('sip_msg'):
                sig_list.append(p['sip_msg'])
            if p.get('l3_sig'):
                sig_list.append(p['l3_sig'])
            if sig_list:
                l3_sig_by_sec[t_sec] = " | ".join(sig_list)
                l3_note_by_sec[t_sec] = " / ".join(sig_list)

        formatted_episodes = []

        if episodes:
            for ep_idx, ep in enumerate(episodes, 1):
                if ep.get('is_merged', False) or ep.get('absorbed_into_too_late', False):
                    continue
                raw_title = ep.get('title') or ep.get('name') or ep.get('summary') or f"결함 구간 #{ep_idx}"
                
                trig_dt = ep.get('t_start') or ep.get('trigger_time') or ep.get('time_stamp') or ep.get('start_dt')
                if not trig_dt and ep.get('events'):
                    trig_dt = ep['events'][0].get('timestamp') or ep['events'][0].get('time_stamp')

                # Exact nearest timestamp matching (time-of-day normalized to prevent date discrepancy)
                def _to_sec(val):
                    if val is None or pd.isna(val):
                        return -1.0
                    if isinstance(val, str):
                        parts = val.strip().split(' ')[-1].split(':')
                        if len(parts) >= 3:
                            try:
                                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                            except ValueError:
                                pass
                    if hasattr(val, 'hour') and hasattr(val, 'minute') and hasattr(val, 'second'):
                        return float(val.hour) * 3600 + float(val.minute) * 60 + float(val.second) + (getattr(val, 'microsecond', 0) / 1e6)
                    return -1.0

                trig_sec = _to_sec(trig_dt)
                matched_idx = 0
                if trig_sec >= 0 and points:
                    matched_idx = min(range(len(points)), key=lambda i: abs(_to_sec(points[i].get('dt') or points[i].get('time')) - trig_sec))
                else:
                    matched_idx = 0

                raw_dur = ep.get('duration_sec') or ep.get('dur_sec')
                dur_sec = float(raw_dur) if (raw_dur is not None and pd.notna(raw_dur) and float(raw_dur) > 0) else None
                dur_pts = max(3, min(60, int(dur_sec))) if dur_sec is not None else 10

                start_idx = max(0, matched_idx - 2)
                end_sec = _to_sec(ep.get('t_end') or ep.get('end_dt') or ep.get('end_ts'))
                if end_sec >= 0 and points:
                    matched_end = min(range(len(points)), key=lambda i: abs(_to_sec(points[i].get('dt') or points[i].get('time')) - end_sec))
                    end_idx = max(start_idx + 1, min(len(points) - 1, matched_end))
                else:
                    end_idx = min(len(points) - 1, start_idx + dur_pts)

                corridor_coords = [[p['lat'], p['lon']] for p in points[start_idx:end_idx + 1]]
                trigger_pt = points[matched_idx] if matched_idx < len(points) else points[start_idx]
                if isinstance(trig_dt, (datetime, pd.Timestamp)):
                    time_tag = trig_dt.strftime('%H:%M:%S')
                else:
                    time_tag = trigger_pt['time']

                # Full PCI Sequence Tracking across Section (Single SSOT from diagnosis episode if present)
                if ep.get('pci_chain'):
                    pci_path_str = ep['pci_chain']
                    chain_cells = [c.strip() for c in pci_path_str.replace('->', '➔').split('➔') if c.strip()]
                    ho_hops = max(1, len(chain_cells) - 1)
                    pci_info_text = f"<b>기지국 천이 경로:</b> {pci_path_str} ({ho_hops}회 핸드오버 발생)"
                else:
                    section_pcis = [p['pci'] for p in points[start_idx:end_idx + 1] if p['pci'] > 0]
                    pci_seq = []
                    for pci in section_pcis:
                        if not pci_seq or pci_seq[-1] != pci:
                            pci_seq.append(pci)
                    
                    if len(pci_seq) > 1:
                        pci_path_str = " ➔ ".join(map(str, pci_seq))
                        pci_info_text = f"<b>기지국 천이 경로:</b> {pci_path_str} ({len(pci_seq)-1}회 핸드오버 발생)"
                    else:
                        pci_path_str = f"PCI {trigger_pt['pci']}"
                        pci_info_text = f"<b>서빙 PCI:</b> {trigger_pt['pci']}"

                # 1. Identify Core Semantic Attributes
                diag_code = str(ep.get('diag_code', ''))
                domain = str(ep.get('domain', ''))
                ep_sev = str(ep.get('severity') or ep.get('grade') or '').upper()
                if not ep_sev or ep_sev not in ['HIGH', 'MED', 'LOW']:
                    if any(k in raw_title for k in ['RLF', '절단', '끊김', '단절', '거절', 'Drop', '다발 핑퐁', 'Reject']):
                        ep_sev = "HIGH"
                    else:
                        ep_sev = "MED"

                # Standard RAT resolution
                srv_rat = ep.get('srv_rat') or ep.get('rat')
                if srv_rat:
                    rat_str = "5G NR" if ("NR" in srv_rat or "5G" in srv_rat) else srv_rat
                elif "5G" in raw_title or "NR" in raw_title or "DIAG_M_01_NR" in diag_code:
                    rat_str = "5G NR"
                elif scenario == "Voice" or "VoLTE" in raw_title or "DIAG_V" in diag_code or "DIAG_M_06" in diag_code or "Voice" in domain:
                    rat_str = "VoLTE"
                else:
                    rat_str = "LTE"

                dom_tag = "🅝" if rat_str == "5G NR" else ("🆅" if rat_str == "VoLTE" else "🅻")
                prefix_tag = "🚨" if ep_sev == "HIGH" else dom_tag

                # Target PCI and RF Metrics Extraction (Single SSOT from diagnosis episode if present)
                target_pci = ep.get('target_pci') if ep.get('target_pci') is not None else (ep.get('tgt_pci') if ep.get('tgt_pci') is not None else None)
                if target_pci is not None:
                    try:
                        target_pci = int(target_pci)
                    except (ValueError, TypeError):
                        pass

                # Serving PCI Extraction (Single SSOT from diagnosis episode if present)
                ep_srv_pci = ep.get('srv_pci') if ep.get('srv_pci') is not None else ep.get('pci')
                if ep_srv_pci is not None:
                    try:
                        srv_pci = int(ep_srv_pci) if int(ep_srv_pci) > 0 else None
                    except (ValueError, TypeError):
                        srv_pci = None
                else:
                    srv_pci = trigger_pt.get('pci') if (trigger_pt.get('pci') and trigger_pt['pci'] > 0) else None

                # Fallback target PCI search from points (MUST NOT be identical to srv_pci!)
                if target_pci is None and points:
                    next_pcis = [p['pci'] for p in points[matched_idx:min(len(points), matched_idx + 10)] if p['pci'] > 0 and (srv_pci is None or p['pci'] != srv_pci)]
                    target_pci = next_pcis[0] if next_pcis else None

                tgt_str = f"PCI {target_pci}" if target_pci else "타겟 셀"

                # Scan A3 Measurement Reports preceding trigger
                pre_win_start = max(0, matched_idx - 10)
                a3_count_pre = sum(1 for p_i in range(pre_win_start, matched_idx + 1) if p_i < len(points) and 'measurementreport' in points[p_i].get('l3_sig', '').lower())
                raw_rep = ep.get('rep_cnt') or a3_count_pre or (ep['events'][0].get('count') if ep.get('events') else 0)
                rep_cnt = int(raw_rep) if (raw_rep is not None and pd.notna(raw_rep)) else 0

                # Extract RF metrics from episode first, fallback to trigger_pt
                ep_srv_rsrp = ep.get('srv_rsrp') if ep.get('srv_rsrp') is not None else ep.get('rsrp')
                if ep_srv_rsrp is not None and pd.notna(ep_srv_rsrp):
                    srv_rsrp = float(ep_srv_rsrp)
                else:
                    raw_rsrp = trigger_pt.get('rsrp')
                    srv_rsrp = float(raw_rsrp) if (raw_rsrp is not None and pd.notna(raw_rsrp)) else None

                ep_srv_sinr = ep.get('srv_sinr') if ep.get('srv_sinr') is not None else ep.get('sinr')
                if ep_srv_sinr is not None and pd.notna(ep_srv_sinr):
                    srv_sinr = float(ep_srv_sinr)
                else:
                    raw_sinr = trigger_pt.get('sinr')
                    srv_sinr = float(raw_sinr) if (raw_sinr is not None and pd.notna(raw_sinr)) else None

                raw_start_rsrp = points[start_idx].get('rsrp') if (points and start_idx < len(points)) else None
                start_rsrp = float(raw_start_rsrp) if (raw_start_rsrp is not None and pd.notna(raw_start_rsrp)) else srv_rsrp
                delta_rsrp = round(srv_rsrp - start_rsrp, 1) if (srv_rsrp is not None and start_rsrp is not None) else None

                # Format RF string conditionally
                pci_label = f"서빙 PCI {srv_pci}" if srv_pci is not None else "서빙 기지국"
                rf_metric_parts = []
                if srv_rsrp is not None:
                    rf_metric_parts.append(f"RSRP {srv_rsrp:.1f} dBm")
                if srv_sinr is not None:
                    rf_metric_parts.append(f"SINR {srv_sinr:.1f} dB")
                rf_summary_str = f"{pci_label} ({', '.join(rf_metric_parts)})" if rf_metric_parts else f"{pci_label} (RF 미수집)"

                # Check actual call drop strictly
                has_call_drop = ep.get('has_call_drop', False)
                if not has_call_drop:
                    has_call_drop = any(
                        ev.get('severity') == 'HIGH' and any(k in ev.get('name', '') for k in ['RLF', 'Radio Link Failure', 'Reestablishment Reject', '호 절단', 'Call Drop', 'e-RAB Drop'])
                        for ev in ep.get('events', [])
                    )
                if not has_call_drop:
                    has_call_drop = (ep_sev == 'HIGH') and any(k in raw_title for k in ['RLF', 'Radio Link Failure', 'Reestablishment Reject', '호 절단', 'Call Drop', 'e-RAB Drop', '거절', '단절'])

                # Semantic Classification Flags
                is_volte_drop = ep.get('has_volte_drop') or any(k in raw_title for k in ['RTP Drop', 'VoLTE 호 비정상 절단', 'VoNR 호 비정상 절단']) or ('DIAG_V_02' in diag_code)
                is_rach_rlf = ('RACH' in raw_title) or ('DIAG_E_01_LTE' in diag_code and 'rach' in raw_title.lower()) or ep.get('has_rach_problem')
                is_ping_pong = ('핑퐁' in raw_title) or ('PINGPONG' in diag_code) or ep.get('has_ping_pong')
                is_a3_drop = ('A3' in raw_title or '방치' in raw_title or rep_cnt >= 2) and (has_call_drop or any(k in raw_title for k in ['RLF', 'Reject', 'Drop', '단절', '거절']))
                is_rlf_reject = has_call_drop or any(k in raw_title for k in ['RLF', 'Reject', '거절', '단절', 'Drop'])

                # Extract 3GPP Standard Failure Cause
                std_cause = ep.get('cause_code') or ep.get('standard_cause')
                if not std_cause and ep.get('events'):
                    for ev_sub in ep['events']:
                        c_sub = ev_sub.get('cause_code') or ev_sub.get('standard_cause')
                        if c_sub:
                            std_cause = c_sub
                            break
                        det_sub = str(ev_sub.get('detail', '')) + " " + str(ev_sub.get('name', ''))
                        if 'RACH Problem' in det_sub or 'randomaccessproblem' in det_sub.lower():
                            std_cause = 'randomAccessProblem'
                            break
                        elif 'T304' in det_sub or 'handoverfailure' in det_sub.lower():
                            std_cause = 'handoverFailure'
                            break
                        elif 'Max Retx' in det_sub or 'rlc-maxnumretx' in det_sub.lower():
                            std_cause = 'rlc-MaxNumRetx'
                            break
                        elif 'T310' in det_sub or 't310-expiry' in det_sub.lower():
                            std_cause = 't310-Expiry'
                            break

                is_rapid_drop = is_rapid_rsrp_drop(delta_rsrp, dur_sec)
                drop_tag_str = f"서빙 전계 급락(ΔRSRP {delta_rsrp:+.1f} dB)" if (is_rapid_drop and delta_rsrp is not None) else None

                # Synthesize Causal Story & Badge
                if is_volte_drop:
                    raw_mute = ep.get('mute_duration_sec') or ep.get('duration_sec')
                    mute_sec = float(raw_mute) if (raw_mute is not None and pd.notna(raw_mute) and float(raw_mute) > 0) else None
                    raw_loss = ep.get('loss_pct')
                    loss_pct = float(raw_loss) if (raw_loss is not None and pd.notna(raw_loss)) else None

                    mute_badge_label = f"{mute_sec:.1f}초 묵음" if mute_sec is not None else "통화 묵음"
                    base_badge = f"통화 묵음 및 RRE 거절 호 절단 ({mute_badge_label} / RTP Drop - Bye)"
                    base_title = f"통화 묵음 지속 및 RRE 거절 후 단말 강제 호 절단 (RTP Drop - Bye)"

                    if is_pilot_pollution_condition(srv_rsrp, srv_sinr):
                        sinr_desc = f"타겟 셀 신호 유입으로 인한 채널 간섭(SINR {srv_sinr:.1f} dB)"
                    elif is_weak_coverage_condition(srv_rsrp):
                        sinr_desc = f"서빙 기지국 음영 진입(RSRP {srv_rsrp:.1f} dBm)"
                    elif drop_tag_str:
                        sinr_desc = f"{drop_tag_str} (SINR {srv_sinr:.1f} dB)"
                    else:
                        sinr_desc = f"무선 채널 품질(RSRP {srv_rsrp:.1f} dBm, SINR {srv_sinr:.1f} dB)" if (srv_rsrp is not None and srv_sinr is not None) else "무선 채널 환경"

                    mute_desc = f"{mute_sec:.1f}초간 지속적인 통화 묵음(Audio Mute" if mute_sec is not None else "지속적인 통화 묵음(Audio Mute"
                    loss_desc = f", 손실률 {loss_pct:.1f}%" if loss_pct is not None else ""

                    root_cause_text = (
                        f"{sinr_desc} 환경에서 하향 링크 동기를 상실하여 RLF가 발생하였으며, 단말이 RRC Connection Reestablishment Request로 셀 복구를 시도했으나 기지국의 Reestablishment Reject로 연결이 거절됨. "
                        f"무선 베어러 단절 이후 하향 음성 RTP 패킷 수신이 완전히 중단되어 {mute_desc}{loss_desc})이 발생함. "
                        f"단말 IMS 통화 엔진의 패킷 무수신 타이머 만료로 망에 SIP BYE(Tx)를 송신하고 통화를 비정상 강제 절단함."
                    )
                    symptoms_text = (
                        f"• 전파 환경: {rf_summary_str}\n"
                        f"• 시그널링 경과: RLF 발생 ➔ Reestablishment Reject 회신 ➔ RTP 수신 차단 ➔ SIP BYE (Tx) 강제 송신\n"
                        f"• 사용자 체감: 통화 도중 음성이 전혀 들리지 않는 묵음 발생 후 통화 강제 끊김"
                    )

                elif is_rach_rlf or std_cause == 'randomAccessProblem':
                    base_badge = "상향 RACH 실패 RLF (randomAccessProblem)"
                    base_title = "상향 랜덤 액세스 프리앰블 전송 한계 초과로 인한 무선 링크 단절 (RACH Problem RLF)"
                    rf_change_desc = f"수신 전계 변화({start_rsrp:.1f} dBm ➔ {srv_rsrp:.1f} dBm, Δ{delta_rsrp:+.1f} dB) 구간에서 " if (start_rsrp is not None and srv_rsrp is not None and delta_rsrp is not None and is_rapid_drop) else ""
                    root_cause_text = (
                        f"단말이 기지국 상향 동기 획득을 위해 Random Access Preamble을 최대 허용 횟수(preambleTransMax)까지 반복 전송했으나, 기지국으로부터 유효한 응답(Random Access Response)을 수신하지 못함. "
                        f"상향 C-Plane 지연 및 전송 한계 도달로 인해 상향 링크 붕괴(RLF: RACH Problem)가 확정되었으며 무선 베어러가 즉시 해제됨. "
                        f"{rf_change_desc}상향 접속 불가로 진행 중이던 세션이 강제 종료됨."
                    )
                    delta_tag = f" | {delta_rsrp:+.1f} dB 전계 변화" if (delta_rsrp is not None and is_rapid_drop) else ""
                    symptoms_text = (
                        f"• 전파 환경: {rf_summary_str}{delta_tag}\n"
                        f"• 시그널링 실패: PRACH Preamble 연속 전송 실패 ➔ Received RAR [False] ➔ RLF(RACH Problem) 발생\n"
                        f"• 서비스 영향: 상향 접속 불가로 인한 데이터 전송 중단 및 RRC 연결 종료"
                    )

                elif is_ping_pong:
                    full_pci_chain = ep.get('pci_chain') or pci_path_str
                    chain_cells = [c.strip() for c in full_pci_chain.split('➔') if c.strip()]
                    hop_cnt = ep.get('rep_cnt') if (ep.get('rep_cnt') is not None and ep['rep_cnt'] > 0) else max(1, len(chain_cells) - 1)
                    raw_delta = ep.get('delta_rsrp')
                    avg_delta = float(raw_delta) if (raw_delta is not None and pd.notna(raw_delta)) else None
                    dur_clause = f"{dur_sec:.1f}초 동안 " if dur_sec is not None else ""
                    hop_rate_str = f" (초당 약 {round(hop_cnt / max(1.0, dur_sec), 1)}회 핸드오버)" if dur_sec is not None else ""

                    base_badge = f"다발 핑퐁 발생 ({hop_cnt}회)"
                    base_title = f"기지국 간 신호 중첩에 의한 다발 핑퐁 핸드오버 ({hop_cnt}회, {full_pci_chain})"
                    delta_clause = f"평균 전계 편차(ΔRSRP {avg_delta:+.1f} dB) 내에서 " if avg_delta is not None else "기지국 간 신호 편차가 미미한 구간에서 "
                    root_cause_text = (
                        f"복수 기지국({full_pci_chain}) 간 중첩 커버리지 구간에서 신호 세기 편차가 미미하고 핸드오버 히스테리시스/오프셋 마진이 부족하여, {dur_clause}{hop_cnt}회에 걸쳐 왕복 핸드오버가 집중 발생함. "
                        f"짧은 시간 내 잦은 셀 변경으로 기지국 및 단말의 C-Plane 시그널링 오버헤드가 급증하고 핸드오버 중 무선 채널 불안정이 가중됨. "
                        f"{delta_clause}불필요한 기지국 재선택이 반복되어 서비스 품질 저하 및 무선 링크 불안정을 유발함."
                    )
                    delta_sub = f" | 평균 천이 편차 ΔRSRP: {avg_delta:+.1f} dB" if avg_delta is not None else ""
                    dur_stat = f"{dur_sec:.1f}초간 " if dur_sec is not None else ""
                    symptoms_text = (
                        f"• 전파 환경: 천이 기지국 그룹 ({full_pci_chain}){delta_sub}\n"
                        f"• 시그널링 통계: {dur_stat}총 {hop_cnt}회 연속 기지국 천이{hop_rate_str}\n"
                        f"• 서비스 영향: 잦은 셀 스위칭으로 인한 순간 전송 지연 및 C-Plane 부하 가중"
                    )

                elif (is_a3_drop or is_rlf_reject) and rep_cnt >= 1 and target_pci:
                    cnt_label = f" (A3 MR {rep_cnt}회)"
                    base_badge = f"타겟({tgt_str}) HO 방치 후 호 단절{cnt_label}"
                    base_title = f"타겟 기지국({tgt_str}) 핸드오버 방치 후 무선 링크 단절(RLF) 및 호 절단{cnt_label}"
                    rf_state_str = f"서빙 전계(RSRP {srv_rsrp:.1f} dBm)" if srv_rsrp is not None else "서빙 기지국"
                    
                    rf_eval = evaluate_rf_situation(srv_rsrp, srv_sinr)
                    if drop_tag_str:
                        sinr_desc = f"{drop_tag_str} 및 물리계층 동기 타이머(T310) 만료"
                    elif is_pilot_pollution_condition(srv_rsrp, srv_sinr):
                        sinr_desc = f"타겟 셀 신호 유입으로 인한 채널 간섭(SINR {srv_sinr:.1f} dB)"
                    elif is_weak_coverage_condition(srv_rsrp):
                        sinr_desc = f"서빙 기지국 음영 진입(RSRP {srv_rsrp:.1f} dBm)"
                    elif srv_sinr is not None and srv_sinr >= 10.0:
                        sinr_desc = f"양호 채널(SINR {srv_sinr:.1f} dB) 상태이나 타겟 핸드오버 미발행 방치"
                    elif srv_sinr is not None:
                        sinr_desc = f"하향 채널({rf_eval.get('summary', f'SINR {srv_sinr:.1f} dB')})"
                    else:
                        sinr_desc = "하향 무선 채널 불안정"

                    root_cause_text = (
                        f"단말이 {rf_state_str} 환경에서 타겟 기지국({tgt_str})으로의 핸드오버를 위해 A3 측정보고(MeasurementReport)를 총 {rep_cnt}회 전송했으나, 기지국에서 핸드오버 명령(RRCConnectionReconfiguration)을 발행하지 않고 방치함. "
                        f"{sinr_desc}으로 하향 동기를 상실하여 무선 링크 단절(RadioLinkFailure)이 발생하였으며, 단말이 기지국 재수립(RRC Connection Reestablishment Request)을 시도했으나 대상 셀의 단말 컨텍스트 부재로 Reestablishment Reject를 수신하여 복구에 실패함. "
                        f"이로 인해 데이터 전송 베어러가 비정상 해제되며 진행 중이던 서비스 호가 완전히 단절됨."
                    )
                    dur_clause = f"{dur_sec:.1f}초간 " if dur_sec is not None else ""
                    symptoms_text = (
                        f"• 전파 환경: {rf_summary_str} | 타겟 후보 {tgt_str}\n"
                        f"• 시그널링 실패: A3 핸드오버 측정보고 {rep_cnt}회 전송 후 기지국 무응답 ➔ T310 만료 RLF ➔ Reestablishment Reject 수신\n"
                        f"• 서비스 영향: {dur_clause}서비스 지연 후 무선 연결 강제 해제 (호 단절 발생)"
                    )

                elif is_rlf_reject:
                    if std_cause == 'handoverFailure':
                        base_badge = f"타겟({tgt_str}) HO 실패 ➔ 호 단절"
                        base_title = f"타겟 기지국({tgt_str}) 핸드오버 실패(T304 만료) 후 RRE 거절 호 절단"
                        cause_detail_str = f"타겟 셀({tgt_str}) 핸드오버 진행 중 T304 타이머 만료 또는 RACH 실패"
                    elif std_cause == 'randomAccessProblem':
                        base_badge = "상향 RACH 실패 ➔ 호 단절"
                        base_title = "상향 랜덤 액세스 프리앰블 전송 실패(RACH Problem) 후 호 단절"
                        cause_detail_str = "상향 Preamble 최대 전송 한계 초과(randomAccessProblem)"
                    elif std_cause == 'rlc-MaxNumRetx':
                        base_badge = "RLC 재전송 초과 ➔ 호 단절"
                        base_title = "RLC 최대 재전송 횟수 초과(rlc-MaxNumRetx) 후 호 단절"
                        cause_detail_str = "RLC 재전송 한도 초과(rlc-MaxNumRetx)"
                    elif std_cause == 't310-Expiry':
                        base_badge = "T310 만료 RLF ➔ 호 단절"
                        base_title = "하향 동기 상실 지속에 따른 T310 만료 RLF 및 호 단절"
                        cause_detail_str = "하향 물리계층 동기 상실에 따른 T310 타이머 만료"
                    else:
                        base_badge = "RLF 및 RRE 거절 호 단절"
                        base_title = "기지국 무선 링크 붕괴(RLF) 및 재수립 거절(Reestablishment Reject) 호 단절"
                        cause_detail_str = "무선 링크 단절(RLF)"

                    if is_pilot_pollution_condition(srv_rsrp, srv_sinr):
                        rf_env_clause = f"타겟 셀 신호 유입에 따른 채널 간섭 우세(SINR {srv_sinr:.1f} dB) 환경에서"
                    elif is_weak_coverage_condition(srv_rsrp):
                        rf_env_clause = f"커버리지 음영 진입(RSRP {srv_rsrp:.1f} dBm) 환경에서"
                    elif drop_tag_str:
                        rf_env_clause = f"{drop_tag_str} 환경에서"
                    else:
                        rf_env_clause = f"무선 전파 환경(RSRP {srv_rsrp:.1f} dBm, SINR {srv_sinr:.1f} dB)에서" if (srv_rsrp is not None and srv_sinr is not None) else "무선 채널 환경에서"

                    root_cause_text = (
                        f"{rf_env_clause} {cause_detail_str}로 무선 링크 단절(RadioLinkFailure)이 발생함. "
                        f"단말이 기지국 재수립(RRC Connection Reestablishment Request)을 시도했으나 기지국이 Reestablishment Reject를 회신하여 복구에 실패함. "
                        f"무선 링크 복구 실패로 인해 연결된 모든 베어러가 강제 해제되며 최종 호 단절이 확정됨."
                    )
                    symptoms_text = (
                        f"• 전파 환경: {rf_summary_str}\n"
                        f"• 시그널링 실패: RLF 발생 ➔ Reestablishment Request ➔ Reestablishment Reject 수신\n"
                        f"• 서비스 영향: 무선 링크 복구 실패로 인한 즉각적인 호 단절"
                    )

                elif 'TAU' in raw_title or 'DIAG_M_06' in diag_code:
                    base_badge = "TAC 핑퐁 (빈번한 TAU)"
                    base_title = "TAC 경계 핑퐁 및 빈번한 Tracking Area Update 발생"
                    root_cause_text = ep.get('root_cause') or "LTE TAC 경계 지역 왕복 이동으로 인한 빈번한 위치 갱신(TAU) 발생"
                    symptoms_text = ep.get('symptoms') or "짧은 시간 내 반복적인 TAU 시그널링으로 단말 C-Plane 오버헤드 증가"

                elif 'MIMO' in raw_title or 'DIAG_M_01_NR' in diag_code:
                    base_badge = "MIMO 랭크 저하"
                    base_title = "고신호 구간 MIMO 랭크 저하 (Layer 제한)"
                    root_cause_text = ep.get('root_cause') or "평균 SINR 양호 구간임에도 4-Layer MIMO 미동작으로 인한 랭크 제한"
                    symptoms_text = ep.get('symptoms') or "다운로드 처리량 저하 및 무선 자원 비효율 발생"

                elif 'CRC' in raw_title or 'PDSCH' in raw_title or 'DIAG_M_02_NR' in diag_code:
                    base_badge = "PDSCH 복조 실패"
                    base_title = "하향 PDSCH 복조 실패 (CRC 에러 / High BLER)"
                    root_cause_text = ep.get('root_cause') or "하향 채널 왜곡으로 인한 PDSCH 연속 CRC 디코딩 실패"
                    symptoms_text = ep.get('symptoms') or "순간 BLER 급증 및 패킷 재전송 발생"

                elif '중복' in raw_title or 'COLLISION' in diag_code or 'DIAG_M_08' in diag_code or 'DIAG_M_05_PCI' in diag_code:
                    dist_km = ep.get('distance_km', 0.0)
                    time_gap = ep.get('time_gap_sec', ep.get('time_diff_sec', 0.0))
                    dep_t = ep.get('departure_time', ep.get('prev_time', ''))
                    ent_t = ep.get('entry_time', ep.get('curr_time', ''))
                    pci_val = ep.get('pci', srv_pci)
                    base_badge = f"중복 PCI (PCI {pci_val}, {dist_km:.1f}km 이격)"
                    base_title = f"동일 주행 경로 내 중복 PCI 검출 (PCI {pci_val}, {dist_km:.1f}km 이격)"
                    root_cause_text = ep.get('root_cause') or (
                        f"동일 PCI {pci_val}를 사용하는 기지국이 물리적 거리 {dist_km:.2f}km 이격된 위치에서 재검출됨. "
                        f"이전 셀 이탈: {dep_t} ➔ 신규 셀 진입: {ent_t} (시간차: {time_gap:.1f}초). "
                        f"물리적 이격 거리 기준 중복 PCI(PCI Collision/Confusion)로 식별되어 핸드오버 모순 및 간섭 위험이 존재함."
                    )
                    symptoms_text = ep.get('symptoms') or f"동일 PCI 재진입 (물리적 거리: {dist_km:.2f}km, 시간차: {time_gap:.1f}초)"

                elif 'A3' in raw_title or '방치' in raw_title or '무응답' in raw_title:
                    base_badge = f"타겟({tgt_str}) HO 요청 무응답 (A3 MR {rep_cnt}회)"
                    base_title = f"타겟({tgt_str}) 핸드오버 요청 무응답 (A3 MR {rep_cnt}회 연속 송신)"
                    dur_clause = f"{dur_sec:.1f}초간 " if dur_sec is not None else ""
                    root_cause_text = ep.get('root_cause') or f"단말이 타겟 셀({tgt_str})에 대해 A3 측정보고를 총 {rep_cnt}회 전송했으나 기지국에서 핸드오버 명령을 미발행하여 {dur_clause}방치됨."
                    symptoms_text = ep.get('symptoms') or f"우세 셀이 타겟 기지국으로 전이되었음에도 핸드오버가 지연되어 서빙 셀 간섭이 심화됨."

                else:
                    clean_raw = re.sub(r'\[.*?\]', '', raw_title).strip()
                    base_badge = clean_raw
                    base_title = clean_raw
                    pci_str = f"서빙 PCI {srv_pci}" if srv_pci is not None else "서빙 기지국"
                    rsrp_str = f", RSRP {srv_rsrp:.1f} dBm" if srv_rsrp is not None else ""
                    root_cause_text = ep.get('root_cause') or f"기지국 간 전계 중첩 및 핸드오버 지연으로 인한 품질 저하 ({pci_str}{rsrp_str})"
                    dur_info = f"구간 지속 시간: {dur_sec:.1f}초 | " if dur_sec is not None else ""
                    symptoms_text = ep.get('symptoms') or f"{dur_info}무선 링크 품질 저하 발생"

                # Guard against duplicated RAT prefix
                if base_badge.startswith(rat_str):
                    base_badge = base_badge[len(rat_str):].strip()
                if base_title.startswith(rat_str):
                    base_title = base_title[len(rat_str):].strip()

                badge_label = f"{prefix_tag} [{time_tag}] {rat_str} {base_badge}"
                clean_title = f"{prefix_tag} [{time_tag}] {rat_str} {base_title}"

                # Build fine-grained second-by-second event map from universal raw L3 stream, ep['events'] and story_steps
                event_map = dict(l3_sig_by_sec)
                note_map = dict(l3_note_by_sec)

                # 1. Overlay from raw cluster events with robust timestamp parsing (datetime or str)
                for ev in ep.get('events', []):
                    ts_ev = ev.get('timestamp') or ev.get('time_stamp') or ev.get('start_ts')
                    if ts_ev is None:
                        continue
                    if isinstance(ts_ev, (datetime, pd.Timestamp)):
                        t_str = ts_ev.strftime('%H:%M:%S')
                    else:
                        t_str = str(ts_ev).split(' ')[-1].split('.')[0][:8]

                    ev_name = str(ev.get('name', ''))
                    ev_det = str(ev.get('detail', ''))
                    sig_label = ev.get('sig_msg') or ev_name
                    note_label = ev.get('note') or ev_det or ev_name

                    if 'MR' in ev_name or 'A3' in ev_name or '측정' in ev_name or '무응답' in ev_name or '방치' in ev_name:
                        tgt_p = ep.get('tgt_pci') or '타겟'
                        sig_label = f"⚠️ eventA3 MeasurementReport (타겟 {tgt_p})"
                        note_label = ev_det or ev_name or "기지국 측정 보고 (HO 명령 미발행)"
                    elif 'Reestablishment' in ev_name or '재수립' in ev_name or 'Reject' in ev_name or '거절' in ev_name:
                        sig_label = "❌ RRCConnectionReestablishmentReject"
                        note_label = "무선 링크 단절 후 재수립 거절로 최종 호 단절"
                    elif 'RLF' in ev_name or 'Radio Link Failure' in ev_name or '무선 링크 실패' in ev_name or '동기 상실' in ev_name:
                        sig_label = "🚨 RadioLinkFailure (하향 동기 상실 / T310 만료)"
                        note_label = "하향 동기 상실(T310 만료 RLF)"
                    elif 'RACH Problem' in ev_name or 'preambleTransMax' in ev_name:
                        sig_label = "🚨 RACH Problem RLF (상향 접속 실패)"
                        note_label = "Random Access Preamble 최대 전송 초과 상향 무선 링크 단절"
                    elif '핑퐁' in ev_name:
                        sig_label = f"🔄 RRC Connection Reconfig (HO ➔ {ep.get('pci_chain') or pci_path_str})"
                        note_label = "핑퐁 핸드오버 반복"
                    elif 'Drop' in ev_name or '호 절단' in ev_name or '단절' in ev_name:
                        sig_label = "🚨 RRC Connection Release / Call Drop"
                        note_label = "통화 호 단절 발발"

                    event_map[t_str] = sig_label
                    note_map[t_str] = note_label

                # 2. Parse fine-grained timeline steps from story_steps (Priority over raw events)
                for step in ep.get('story_steps', []):
                    m_step = re.search(r'\[(\d{2}:\d{2}:\d{2})(?:\.\d+)?\]\s*(.*)', str(step))
                    if m_step:
                        step_t, step_text = m_step.group(1), m_step.group(2)
                        if "BYE" in step_text:
                            event_map[step_t] = "🔴 SIP BYE (통화 종료)"
                            note_map[step_t] = step_text
                        elif "200 OK" in step_text or "Session Active" in step_text:
                            event_map[step_t] = "✅ SIP 200 OK (통화 연결 성공)"
                            note_map[step_t] = step_text
                        elif "RLF" in step_text or "무선 링크 단절" in step_text:
                            event_map[step_t] = "🚨 RadioLinkFailure (RLF)"
                            note_map[step_t] = step_text
                        elif "Reestablishment" in step_text or "거절" in step_text or "Reject" in step_text:
                            event_map[step_t] = "❌ RRCConnectionReestablishmentReject"
                            note_map[step_t] = step_text
                        elif "RTP" in step_text or "묵음" in step_text or "손실" in step_text:
                            event_map[step_t] = "⚠️ RTP Drop / Audio Mute (음성 패킷 손실)"
                            note_map[step_t] = step_text
                        elif "PRACH" in step_text or "프리앰블" in step_text or "RACH" in step_text:
                            event_map[step_t] = "📡 Random Access Preamble (Msg1)"
                            note_map[step_t] = step_text
                        elif "호 절단" in step_text or "Call Drop" in step_text or "e-RAB Drop" in step_text:
                            event_map[step_t] = "🚨 Call Drop (통화 호 단절)"
                            note_map[step_t] = step_text
                        elif step_t not in event_map:
                            event_map[step_t] = "• " + step_text[:35]
                            note_map[step_t] = step_text

                # 3. Guarantee T0 Trigger Point Event if empty
                t0_time = time_tag
                if t0_time not in event_map or event_map[t0_time] == "-":
                    if is_ping_pong:
                        event_map[t0_time] = f"🚨 {base_badge}"
                        note_map[t0_time] = f"기지국 간({ep.get('pci_chain') or pci_path_str}) 잦은 왕복 핸드오버 반복"
                    elif "RACH" in raw_title or is_rach_rlf:
                        event_map[t0_time] = "🚨 RACH Problem RLF (Received RAR[False])"
                        note_map[t0_time] = "기지국 상향 C-Plane 지연 또는 Preamble 자원 충돌"
                    elif "거절" in raw_title or "Reject" in raw_title:
                        event_map[t0_time] = "🚨 RRE Request ➔ Reestablishment Reject"
                        note_map[t0_time] = "무선 링크 단절 후 재수립 거절로 최종 호 단절"
                    elif "RLF" in raw_title or "무선 링크 실패" in raw_title:
                        event_map[t0_time] = "🚨 RadioLinkFailure (RLF)"
                        note_map[t0_time] = "하향 동기 상실(T310 만료)로 인한 무선 링크 단절"
                    elif "Drop" in raw_title or "단절" in raw_title:
                        event_map[t0_time] = "🚨 RRC Connection Release / Call Drop"
                        note_map[t0_time] = "기지국 제어 결함 또는 베어러 비정상 해제"

                # 4. Universal Second-by-Second Timeline Assembly (Union of Points and Events)
                def _to_time_str(sec_val):
                    s = int(round(sec_val)) % 86400
                    h = s // 3600
                    m = (s % 3600) // 60
                    sec_rem = s % 60
                    return f"{h:02d}:{m:02d}:{sec_rem:02d}"

                t0_sec = _to_sec(time_tag)
                end_dt_val = ep.get('t_end') or ep.get('end_dt') or ep.get('end_ts')
                end_time_tag = end_dt_val.strftime('%H:%M:%S') if hasattr(end_dt_val, 'strftime') else (str(end_dt_val).split(' ')[-1][:8] if end_dt_val else (points[end_idx]['time'] if points and end_idx < len(points) else ''))
                end_sec = _to_sec(end_time_tag)

                start_pt_sec = _to_sec(points[max(0, matched_idx - 2)]['time']) if points else t0_sec
                step_secs = [_to_sec(re.search(r'\[(\d{2}:\d{2}:\d{2})', str(st)).group(1)) for st in ep.get('story_steps', []) if re.search(r'\[(\d{2}:\d{2}:\d{2})', str(st))]
                min_step_sec = min(step_secs) if step_secs else t0_sec
                win_start_sec = max(0, min(start_pt_sec, t0_sec, min_step_sec) - 2)
                win_end_sec = max(end_sec, t0_sec) + 6

                pt_by_time = {p['time']: p for p in points}
                all_timeline_secs = set()
                for p in points:
                    p_s = _to_sec(p['time'])
                    if win_start_sec <= p_s <= win_end_sec:
                        all_timeline_secs.add(p['time'])

                for ev_t in event_map.keys():
                    ev_s = _to_sec(ev_t)
                    if win_start_sec <= ev_s <= win_end_sec:
                        all_timeline_secs.add(ev_t)

                if t0_sec >= 0 and end_sec >= t0_sec:
                    for s_int in range(int(round(t0_sec)), int(round(end_sec)) + 1):
                        all_timeline_secs.add(_to_time_str(s_int))

                sorted_timeline_times = sorted(list(all_timeline_secs), key=lambda x: _to_sec(x))

                timeline_rows = []
                for cur_time in sorted_timeline_times:
                    cur_sec = _to_sec(cur_time)
                    rel_sec = int(round(cur_sec - t0_sec)) if t0_sec >= 0 else 0

                    if cur_time == time_tag or (rel_sec == 0 and t0_sec >= 0):
                        phase = "T0 ⚠️ (발생)"
                    elif rel_sec < 0:
                        phase = f"T {rel_sec}s (사전)"
                    elif cur_time == end_time_tag or (end_sec >= 0 and int(round(cur_sec)) == int(round(end_sec))):
                        phase = f"T +{rel_sec}s (종료)"
                    elif end_sec >= 0 and cur_sec > end_sec:
                        phase = f"T +{rel_sec}s (사후)"
                    else:
                        phase = f"T +{rel_sec}s (진행)"

                    ctx_pt = pt_by_time.get(cur_time)
                    if ctx_pt is not None:
                        pci_val = ctx_pt['pci']
                        rsrp_val = f"{ctx_pt['rsrp']} dBm" if ctx_pt['rsrp'] is not None else "미수집"
                        sinr_val = f"{ctx_pt['sinr']} dB" if ctx_pt['sinr'] is not None else "미수집"
                        if scenario == "Voice":
                            metric_val = f"{ctx_pt['mos']}점" if ctx_pt['mos'] is not None else "미수집"
                        elif "UL" in scenario:
                            val_tp = ctx_pt['ul_tp'] if ctx_pt['ul_tp'] is not None else ctx_pt['pdcp_tp']
                            metric_val = f"{val_tp} Mbps" if val_tp is not None else "0.0 Mbps"
                        else:
                            val_tp = ctx_pt['dl_tp'] if ctx_pt['dl_tp'] is not None else ctx_pt['pdcp_tp']
                            metric_val = f"{val_tp} Mbps" if val_tp is not None else "0.0 Mbps"
                    else:
                        pci_val = srv_pci if srv_pci is not None else (trigger_pt['pci'] if trigger_pt else "-")
                        rsrp_val = f"{srv_rsrp:.1f} dBm" if srv_rsrp is not None else "미수집"
                        sinr_val = f"{srv_sinr:.1f} dB" if srv_sinr is not None else "미수집"
                        metric_val = "미수집"

                    sig_msg = event_map.get(cur_time, "-")
                    note = note_map.get(cur_time, "-")

                    timeline_rows.append({
                        "phase": phase,
                        "time": cur_time,
                        "pci": pci_val,
                        "rsrp": rsrp_val,
                        "sinr": sinr_val,
                        "metric_val": metric_val,
                        "sig_msg": sig_msg,
                        "note": note
                    })

                ep_sev = str(ep.get('severity') or ep.get('grade') or '').upper()
                if not ep_sev or ep_sev not in ['HIGH', 'MED', 'LOW']:
                    ep_sev = "HIGH" if any(k in raw_title for k in ['RLF', '절단', '끊김', '단절', '거절', 'Drop']) else "MED"

                if time_tag and end_time_tag:
                    dur_str = f" ({dur_sec:.1f}초간)" if dur_sec is not None else ""
                    time_range_str = f"{time_tag} ~ {end_time_tag}{dur_str}"
                else:
                    time_range_str = f"{points[start_idx]['time']} ~ {points[end_idx]['time']} ({end_idx - start_idx + 1}초간)"

                formatted_episodes.append({
                    "id": ep_idx,
                    "start_idx": start_idx,
                    "time": time_tag,
                    "title": clean_title,
                    "badge_label": badge_label,
                    "time_range": time_range_str,
                    "severity": ep_sev,
                    "lat": trigger_pt['lat'],
                    "lon": trigger_pt['lon'],
                    "corridor": corridor_coords,
                    "pci_info_text": pci_info_text,
                    "serving_pci": points[start_idx]['pci'],
                    "target_pci": points[end_idx]['pci'],
                    "root_cause": root_cause_text,
                    "symptoms": symptoms_text,
                    "timeline": timeline_rows
                })

        # Strict Chronological Sorting & Deduplication / Merging (within 3.0 seconds window)
        formatted_episodes.sort(key=lambda x: _to_sec(x['time']))

        merged_episodes = []
        for ep in formatted_episodes:
            if not merged_episodes:
                merged_episodes.append(ep)
                continue

            prev_ep = merged_episodes[-1]
            prev_sec = _to_sec(prev_ep['time'])
            cur_sec = _to_sec(ep['time'])
            time_diff = abs(cur_sec - prev_sec)

            if time_diff <= 3.0:
                prev_title = prev_ep['title']
                cur_title = ep['title']

                is_prev_rach = "RACH" in prev_title
                is_cur_rach = "RACH" in cur_title
                is_prev_a3 = "타겟" in prev_title or "A3" in prev_title
                is_cur_a3 = "타겟" in cur_title or "A3" in cur_title
                is_prev_volte = "통화 묵음" in prev_title or "RTP" in prev_title
                is_cur_volte = "통화 묵음" in cur_title or "RTP" in cur_title

                should_merge = False
                # Merge criteria
                if (is_prev_rach and is_cur_a3) or (is_prev_a3 and is_cur_rach):
                    should_merge = True
                elif prev_ep.get('target_pci') == ep.get('target_pci') and prev_ep.get('serving_pci') == ep.get('serving_pci'):
                    should_merge = True
                elif is_prev_volte and is_cur_volte:
                    should_merge = True
                elif is_prev_rach and is_cur_rach:
                    should_merge = True
                elif is_prev_a3 and is_cur_a3:
                    should_merge = True
                elif ("RLF" in prev_title or "거절" in prev_title) and ("RLF" in cur_title or "거절" in cur_title):
                    should_merge = True

                if should_merge:
                    # Special synthesis: HO attempt + RACH failure
                    if (is_prev_rach and is_cur_a3) or (is_prev_a3 and is_cur_rach):
                        tgt_p = prev_ep.get('target_pci') if prev_ep.get('target_pci') and prev_ep.get('target_pci') > 0 else ep.get('target_pci')
                        tgt_str = f"PCI {tgt_p}" if (tgt_p and tgt_p > 0) else "타겟 셀"

                        m1 = re.search(r'A3 MR (\d+)회', prev_title)
                        m2 = re.search(r'A3 MR (\d+)회', cur_title)
                        rep_1 = int(m1.group(1)) if m1 else 0
                        rep_2 = int(m2.group(1)) if m2 else 0
                        rep_max = max(rep_1, rep_2)
                        cnt_str = f" (A3 MR {rep_max}회)" if rep_max > 0 else ""

                        rat_name = "LTE" if "LTE" in cur_title else ("5G NR" if "NR" in cur_title else "VoLTE")
                        prev_ep['badge_label'] = f"🚨 [{prev_ep['time']}] {rat_name} 타겟({tgt_str}) HO 중 RACH 실패 RLF{cnt_str}"
                        prev_ep['title'] = f"🚨 [{prev_ep['time']}] {rat_name} 타겟 기지국({tgt_str}) 핸드오버 시도 중 상향 RACH Preamble 실패 무선 링크 단절(RLF){cnt_str}"

                        srv_p = prev_ep.get('serving_pci') or ep.get('serving_pci')
                        prev_ep['root_cause'] = (
                            f"단말이 서빙 기지국(PCI {srv_p})에서 타겟 기지국({tgt_str})으로 핸드오버를 위해 A3 측정보고를 송신하고 타겟 셀 접속을 시도했으나, "
                            f"타겟 셀 상향 Random Access Preamble을 최대 허용 횟수(preambleTransMax)까지 반복 전송하고도 기지국으로부터 유효한 RAR 응답을 수신하지 못함.\n\n"
                            f"상향 동기 획득 실패(RACH Problem)로 인해 핸드오버 실패 및 무선 링크 단절(RLF)이 확정되었으며, 진행 중이던 무선 베어러가 강제 해제됨.\n\n"
                            f"기지국 재수립(RRC Connection Reestablishment Request)을 시도했으나 타겟 셀의 Reestablishment Reject 회신으로 최종 호 단절이 발생함."
                        )
                        prev_ep['symptoms'] = (
                            f"• 전파 환경: 서빙 PCI {srv_p} ➔ 타겟 {tgt_str}\n"
                            f"• 시그널링 실패: A3 MR 송신 ➔ PRACH Preamble 연속 전송 한계 초과 ➔ Received RAR [False] ➔ RLF 확정 ➔ RRE Reject\n"
                            f"• 서비스 영향: 핸드오버 진입 구간 상향 접속 실패로 인한 즉각적인 호 단절"
                        )

                    # Merge timeline rows (union and sort by time)
                    seen_t = {row['time']: row for row in prev_ep.get('timeline', [])}
                    for r in ep.get('timeline', []):
                        t = r['time']
                        if t not in seen_t:
                            seen_t[t] = r
                        else:
                            if seen_t[t]['sig_msg'] == "-" and r['sig_msg'] != "-":
                                seen_t[t]['sig_msg'] = r['sig_msg']
                            if seen_t[t]['note'] == "-" and r['note'] != "-":
                                seen_t[t]['note'] = r['note']
                    prev_ep['timeline'] = sorted(list(seen_t.values()), key=lambda x: _to_sec(x['time']))

                    # Merge corridor
                    existing_coords = {f"{c[0]:.6f},{c[1]:.6f}" for c in prev_ep.get('corridor', []) if c and len(c) >= 2 and c[0] is not None and c[1] is not None}
                    for c in ep.get('corridor', []):
                        if not c or len(c) < 2 or c[0] is None or c[1] is None:
                            continue
                        k = f"{c[0]:.6f},{c[1]:.6f}"
                        if k not in existing_coords:
                            prev_ep.setdefault('corridor', []).append(c)
                            existing_coords.add(k)

                    continue

            merged_episodes.append(ep)

        for idx, ep in enumerate(merged_episodes, 1):
            ep['id'] = idx

        return merged_episodes

    def generate_integrated_multi_port_map(
        self,
        port_data_dict: Dict[str, Dict[str, Any]],
        display_name: str,
        output_html_path: str,
        network_mode: str = "LTE",
        vendor: str = "COMMON"
    ) -> str:
        """
        Builds the Master 2D Multi-Port Unified Standalone Interactive HTML Map.
        """
        packaged_ports = {}
        all_unique_pcis = set()

        for port_key, pdata in port_data_dict.items():
            df_tl = pdata.get('df_timeline', pd.DataFrame())
            csvs = pdata.get('csvs', {})
            incidents = pdata.get('episodes') or pdata.get('incidents', [])

            sc_info = self.detect_scenario_and_model(df_tl, csvs)
            scenario = sc_info['scenario']
            traffic_model = sc_info['traffic_model']

            pts = self.extract_trajectory_from_timeline(df_tl, scenario=scenario, port_name=port_key)
            eps = self.extract_incident_episodes(incidents, pts, scenario=scenario, network_mode=network_mode, csvs=csvs)

            for p in pts:
                if p.get('pci') and p['pci'] > 0:
                    all_unique_pcis.add(p['pci'])
                if p.get('nr_pci') and p['nr_pci'] > 0:
                    all_unique_pcis.add(p['nr_pci'])
                if p.get('lte_pci') and p['lte_pci'] > 0:
                    all_unique_pcis.add(p['lte_pci'])

            lte_bw, nr_bw = self.extract_bandwidth_from_timeline(df_tl)
            port_criteria = get_all_map_criteria_dict(network_mode, lte_bw, nr_bw)

            if network_mode == "NSA":
                bw_str = f"NR {int(nr_bw)}M + LTE {int(lte_bw)}M"
            elif network_mode == "SA":
                bw_str = f"NR {int(nr_bw)}M"
            else:
                bw_str = f"LTE {int(lte_bw)}M"

            has_valid_mos = any(pt.get('mos') is not None and pd.notna(pt.get('mos')) and float(pt.get('mos') or 0) > 0 for pt in pts)

            if scenario == "Voice":
                fourth_btn_name = ("🎙️ VoLTE MOS" if network_mode != "SA" else "🎙️ VoNR MOS") if has_valid_mos else "🎙️ MOS (데이터 없음)"
                fourth_btn_key = "mos"
            elif network_mode == "NSA":
                fourth_btn_name = "🚀 Total PDCP"
                fourth_btn_key = "pdcp_tp"
            elif network_mode == "SA":
                fourth_btn_name = "🚀 NR Total MAC"
                fourth_btn_key = "nr_mac_tp"
            else:  # LTE Only
                fourth_btn_name = "🚀 LTE Total MAC"
                fourth_btn_key = "lte_mac_tp"

            # Clean non-serializable objects from points for JSON export
            clean_pts = []
            for pt in pts:
                p_copy = dict(pt)
                if 'dt' in p_copy:
                    del p_copy['dt']
                clean_pts.append(p_copy)

            first_dt = next((pt['dt'] for pt in pts if pt.get('dt') and pd.notna(pt['dt'])), None)
            date_str = first_dt.strftime('%Y.%m.%d') if first_dt is not None else ""

            packaged_ports[port_key] = {
                "port_name": port_key,
                "scenario": scenario,
                "traffic_model": traffic_model,
                "fourth_btn_name": fourth_btn_name,
                "fourth_btn_key": fourth_btn_key,
                "has_valid_mos": has_valid_mos,
                "bw_str": bw_str,
                "lte_bw": lte_bw,
                "nr_bw": nr_bw,
                "map_criteria": port_criteria,
                "points": clean_pts,
                "episodes": eps,
                "total_points": len(clean_pts),
                "date_str": date_str,
                "start_time": clean_pts[0]['time'] if clean_pts else "00:00:00",
                "end_time": clean_pts[-1]['time'] if clean_pts else "00:00:00"
            }

        sorted_pcis = sorted(list(all_unique_pcis))
        pci_color_map = {pci: PCI_COLOR_PALETTE[i % len(PCI_COLOR_PALETTE)] for i, pci in enumerate(sorted_pcis)}

        default_port = list(packaged_ports.keys())[0] if packaged_ports else "M1"
        def_port_data = packaged_ports.get(default_port, {})
        def_lte_bw = def_port_data.get('lte_bw', 20.0)
        def_nr_bw = def_port_data.get('nr_bw', 100.0)

        ports_json = json.dumps(packaged_ports, ensure_ascii=False)
        pci_colors_json = json.dumps(pci_color_map, ensure_ascii=False)
        criteria_json = json.dumps(get_all_map_criteria_dict(network_mode, def_lte_bw, def_nr_bw), ensure_ascii=False)

        default_port = list(packaged_ports.keys())[0] if packaged_ports else "M1"
        def_pts = packaged_ports[default_port]['points'] if default_port in packaged_ports else []
        valid_coords = [[p['lat'], p['lon']] for p in def_pts if p.get('lat') is not None and p.get('lon') is not None and 33.0 <= p['lat'] <= 39.0 and 124.0 <= p['lon'] <= 132.0]
        center_lat = valid_coords[len(valid_coords) // 2][0] if valid_coords else 37.5665
        center_lon = valid_coords[len(valid_coords) // 2][1] if valid_coords else 126.9780

        html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Optis V12 통합 품질 분석 맵 - {display_name}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Malgun Gothic', sans-serif; background: #0f172a; color: #f8fafc; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }}
  
  /* Top Header */
  #header {{ background: #1e293b; border-bottom: 1px solid #334155; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; z-index: 1000; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3); }}
  .header-left {{ display: flex; align-items: center; gap: 16px; }}
  .header-title {{ font-size: 15px; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 8px; }}
  
  /* Port Switcher Tabs */
  .port-tabs {{ display: flex; gap: 6px; background: #0f172a; padding: 4px; border-radius: 8px; border: 1px solid #334155; }}
  .port-tab {{ background: transparent; border: none; color: #94a3b8; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer; transition: all 0.2s; }}
  .port-tab:hover {{ color: #f8fafc; background: #1e293b; }}
  .port-tab.active {{ background: #2563eb; color: #ffffff; box-shadow: 0 0 10px rgba(37, 99, 235, 0.6); }}

  .header-stats {{ display: flex; gap: 8px; font-size: 12px; color: #94a3b8; }}
  .stat-badge {{ background: #0f172a; padding: 4px 10px; border-radius: 6px; border: 1px solid #334155; color: #e2e8f0; }}
  .stat-badge b {{ color: #38bdf8; }}
  .stat-badge.net b {{ color: #a855f7; }}
  .stat-badge.alert b {{ color: #ef4444; }}
  .stat-badge.traffic b {{ color: #10b981; }}

  /* Main Container */
  #main-container {{ flex: 1; display: flex; position: relative; overflow: hidden; }}

  /* Left Sidebar */
  #sidebar {{ width: 350px; background: #1e293b; border-right: 1px solid #334155; display: flex; flex-direction: column; z-index: 999; overflow-y: auto; box-shadow: 4px 0 10px rgba(0,0,0,0.3); }}
  .sidebar-section {{ padding: 14px 16px; border-bottom: 1px solid #334155; }}
  .section-title {{ font-size: 13px; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }}
  
  /* Layer Buttons (지도 표시 항목) */
  .btn-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .layer-btn {{ background: #0f172a; border: 1px solid #334155; color: #cbd5e1; padding: 9px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; text-align: center; transition: all 0.2s; }}
  .layer-btn:hover {{ background: #334155; color: #fff; }}
  .layer-btn.active {{ background: #2563eb; border-color: #3b82f6; color: #fff; box-shadow: 0 0 10px rgba(37, 99, 235, 0.5); }}

  /* Failure Section List Card Layout */
  .episode-item {{ display: flex; flex-direction: column; gap: 4px; background: #0f172a; padding: 10px 12px; border-radius: 6px; border: 1px solid #334155; margin-bottom: 8px; cursor: pointer; transition: all 0.2s; }}
  .episode-item:hover {{ background: #1e293b; border-color: #ef4444; transform: translateY(-1px); box-shadow: 0 2px 8px rgba(239, 68, 68, 0.25); }}
  .episode-header-row {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 6px; }}
  .episode-title-text {{ font-size: 12px; font-weight: 700; color: #f1f5f9; line-height: 1.4; word-break: keep-all; }}
  .episode-sub-row {{ display: flex; align-items: center; gap: 6px; font-size: 11px; color: #94a3b8; margin-top: 2px; flex-wrap: wrap; }}
  .episode-tag {{ font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; white-space: nowrap; }}
  .tag-HIGH {{ background: #ef4444; color: #ffffff; border: 1px solid #b91c1c; box-shadow: 0 0 6px rgba(239, 68, 68, 0.4); }}
  .tag-MED {{ background: #f59e0b; color: #ffffff; border: 1px solid #d97706; box-shadow: 0 0 6px rgba(245, 158, 11, 0.4); }}
  .tag-LOW {{ background: #3b82f6; color: #ffffff; border: 1px solid #2563eb; box-shadow: 0 0 6px rgba(59, 130, 246, 0.4); }}

  /* Dynamic Legend */
  .legend-bar {{ display: flex; height: 10px; border-radius: 4px; overflow: hidden; margin: 8px 0; }}
  .legend-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; }}

  /* Bottom-Right Floating Dynamic Legend Overlay */
  #floating-legend {{
    position: absolute;
    bottom: 24px;
    right: 24px;
    background: rgba(15, 23, 42, 0.92);
    backdrop-filter: blur(8px);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 14px;
    z-index: 1000;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.7);
    min-width: 250px;
    color: #f8fafc;
    transition: all 0.2s ease;
  }}
  .float-legend-title {{
    font-size: 11px;
    font-weight: 700;
    color: #38bdf8;
    margin-bottom: 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .float-legend-bar {{
    display: flex;
    height: 9px;
    border-radius: 4px;
    overflow: hidden;
    margin: 5px 0;
  }}
  .float-legend-labels {{
    display: flex;
    justify-content: space-between;
    font-size: 10px;
    color: #cbd5e1;
    font-weight: 600;
  }}

  /* Viewport / Leaflet Map */
  #map-viewport {{ flex: 1; position: relative; background: #1a202c; }}
  #map {{ width: 100%; height: 100%; }}

  /* Right Slide-over Modal with Dynamic Resizing */
  #modal-panel {{
    position: absolute;
    top: 0;
    right: -100%;
    width: 920px;
    min-width: 500px;
    max-width: 90vw;
    height: 100%;
    background: #1e293b;
    border-left: 1px solid #334155;
    z-index: 1002;
    transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    display: flex;
    flex-direction: column;
    box-shadow: -10px 0 25px rgba(0,0,0,0.5);
  }}
  #modal-panel.open {{ right: 0 !important; }}
  #modal-panel.resizing {{ transition: none !important; user-select: none; }}

  /* Resize Handle on Left edge of Modal Panel */
  #modal-resize-handle {{
    position: absolute;
    top: 0;
    left: -6px;
    width: 12px;
    height: 100%;
    cursor: ew-resize;
    z-index: 1005;
    background: transparent;
    transition: background 0.15s ease;
  }}
  #modal-resize-handle:hover,
  #modal-panel.resizing #modal-resize-handle {{
    background: #38bdf8;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.8);
  }}

  .modal-header {{ padding: 16px 20px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; background: #0f172a; flex-shrink: 0; }}
  .modal-header h3 {{ font-size: 14px; color: #ef4444; display: flex; align-items: center; gap: 8px; }}
  .close-btn {{ background: transparent; border: none; color: #94a3b8; font-size: 20px; cursor: pointer; }}
  .modal-body {{ padding: 20px; overflow-y: auto; overflow-x: hidden; flex: 1; }}
  .modal-card {{ background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 14px; margin-bottom: 14px; width: 100%; }}
  .card-title {{ font-size: 12px; font-weight: 700; color: #38bdf8; margin-bottom: 6px; text-transform: uppercase; }}
  .card-text {{ font-size: 13px; line-height: 1.5; color: #e2e8f0; white-space: pre-line; word-break: break-word; }}
  
  /* Signaling Table - Fully Expanded without Horizontal Scrolling */
  .ctx-table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 8px; table-layout: fixed; word-break: break-word; }}
  .ctx-table th, .ctx-table td {{ border: 1px solid #334155; padding: 7px 6px; text-align: center; }}
  .ctx-table th {{ background: #1e293b; color: #94a3b8; font-weight: 700; }}
  .ctx-table th:nth-child(1) {{ width: 13%; }} /* 구분 */
  .ctx-table th:nth-child(2) {{ width: 9%; }}  /* Time */
  .ctx-table th:nth-child(3) {{ width: 6%; }}  /* PCI */
  .ctx-table th:nth-child(4) {{ width: 8%; }}  /* RSRP */
  .ctx-table th:nth-child(5) {{ width: 7%; }}  /* SINR */
  .ctx-table th:nth-child(6) {{ width: 8%; }}  /* 속도/MOS */
  .ctx-table th:nth-child(7) {{ width: 25%; }} /* 3GPP 시그널링 */
  .ctx-table th:nth-child(8) {{ width: 24%; }} /* 비고 */
  .ctx-table tr.trigger-row {{ background: rgba(239, 68, 68, 0.35); font-weight: 700; color: #fca5a5; }}
  .ctx-table td.sig-cell {{ text-align: center; font-family: Consolas, monospace; font-size: 11px; color: #38bdf8; }}
  .ctx-table tr:hover {{ background: rgba(51, 65, 85, 0.4); }}
</style>
</head>
<body>

<div id="header">
  <div class="header-left">
    <div class="header-title">
      <span>🗺️</span> <b>{display_name}</b>
    </div>
    <!-- Multi-Port Tabs -->
    <div class="port-tabs" id="port-tabs-container"></div>
  </div>

  <div class="header-stats">
    <div class="stat-badge net">망: <b>{network_mode}</b></div>
    <div class="stat-badge traffic" id="stat-traffic">측정 방식: <b>-</b></div>
    <div class="stat-badge">벤더: <b>{vendor}</b></div>
    <div class="stat-badge" id="stat-time">측정 일시: <b>-</b></div>
    <div class="stat-badge alert" id="stat-incidents">장애 구간: <b>-</b></div>
  </div>
</div>

<div id="main-container">
  <!-- Left Sidebar -->
  <div id="sidebar">
    <div class="sidebar-section">
      <div class="section-title">📊 지도 표시 항목</div>
      <div class="btn-grid" id="layer-btn-grid">
        <button class="layer-btn active" id="btn-rsrp" onclick="setMetric('rsrp')">📡 RSRP (dBm)</button>
        <button class="layer-btn" id="btn-pci" onclick="setMetric('pci')">📶 Serving PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ SINR (dB)</button>
        <button class="layer-btn" id="btn-fourth" onclick="setMetric('fourth')">🚀 Throughput</button>
      </div>
      <div class="section-title" style="margin-top: 10px;">🚨 장애 뱃지 필터</div>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; margin-top: 4px;">
        <button class="sev-btn active" id="btn-sev-high" onclick="toggleSeverity('HIGH')" style="background: #ef4444; color: #fff; border: 1px solid #b91c1c; border-radius: 5px; padding: 6px 0; font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.15s ease;">🔴 HIGH</button>
        <button class="sev-btn active" id="btn-sev-med" onclick="toggleSeverity('MED')" style="background: #f59e0b; color: #fff; border: 1px solid #d97706; border-radius: 5px; padding: 6px 0; font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.15s ease;">🟠 MED</button>
        <button class="sev-btn active" id="btn-sev-low" onclick="toggleSeverity('LOW')" style="background: #3b82f6; color: #fff; border: 1px solid #2563eb; border-radius: 5px; padding: 6px 0; font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.15s ease;">🔵 LOW</button>
      </div>
    </div>

    <div class="sidebar-section" style="flex: 1; overflow-y: auto;">
      <div class="section-title" id="lbl-episode-title">⚠️ 검출된 장애 구간 목록</div>
      <div id="episode-list-container"></div>
    </div>
  </div>

  <!-- Central Map Viewport -->
  <div id="map-viewport">
    <div id="map"></div>
    
    <!-- Floating Bottom-Right Metric Legend Overlay -->
    <div id="floating-legend">
      <div class="float-legend-title">
        <span id="float-legend-title-text">📊 지표 범례</span>
        <button id="float-legend-toggle" onclick="toggleFloatLegend()" style="background:none; border:none; color:#94a3b8; cursor:pointer; font-size:12px; font-weight:bold;">−</button>
      </div>
      <div id="floating-legend-content"></div>
    </div>
  </div>

  <!-- Right Slide-over Episode Modal with Resizer -->
  <div id="modal-panel">
    <div id="modal-resize-handle" title="좌우로 드래그하여 패널 너비 조절"></div>
    <div class="modal-header">
      <h3 id="m-title">⚠️ 장애 구간 정밀 진단</h3>
      <button class="close-btn" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body" id="m-body"></div>
  </div>
</div>

<script>
  const allPortsData = {ports_json};
  const pciColors = {pci_colors_json};
  let mapCriteria = {criteria_json};
  const networkMode = "{network_mode}";

  let currentPort = "{default_port}";
  let currentMetric = (networkMode === 'NSA' ? 'nr_rsrp' : 'rsrp');
  let showEpisodeBadges = true;
  let map;
  let polylineLayers = [];
  let circleMarkers = [];
  let corridorLayers = [];
  let episodeMarkers = [];
  let playMarker = null;
  let playbackIdx = 0, isPlaying = false, playTimer = null;

  function startMapApp() {{
    if (window._mapAppStarted) return;
    window._mapAppStarted = true;
    initMap();
    initPortTabs();
    initMetricButtons();
    initModalResizer();
    loadPort(currentPort);
  }}

  let isResizingModal = false;
  let modalStartWidth = 920;
  let modalStartX = 0;

  function initModalResizer() {{
    const handle = document.getElementById('modal-resize-handle');
    const panel = document.getElementById('modal-panel');
    if (!handle || !panel) return;

    handle.addEventListener('mousedown', function(e) {{
      isResizingModal = true;
      modalStartX = e.clientX;
      modalStartWidth = panel.getBoundingClientRect().width;
      panel.classList.add('resizing');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    }});

    window.addEventListener('mousemove', function(e) {{
      if (!isResizingModal) return;
      const dx = modalStartX - e.clientX;
      const newWidth = Math.max(500, Math.min(window.innerWidth * 0.90, modalStartWidth + dx));
      panel.style.width = newWidth + 'px';
    }});

    window.addEventListener('mouseup', function() {{
      if (isResizingModal) {{
        isResizingModal = false;
        panel.classList.remove('resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }}
    }});
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', startMapApp);
  }} else {{
    startMapApp();
  }}
  window.onload = startMapApp;
  window.addEventListener('resize', function() {{
    if (map) map.invalidateSize();
  }});
  document.addEventListener('visibilitychange', function() {{
    if (!document.hidden && map) {{
      map.invalidateSize();
    }}
  }});

  function initMap() {{
    map = L.map('map', {{
      center: [{center_lat}, {center_lon}],
      zoom: 13,
      zoomControl: true
    }});

    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors',
      maxZoom: 19
    }}).addTo(map);
  }}

  let floatLegendCollapsed = false;
  function toggleFloatLegend() {{
    floatLegendCollapsed = !floatLegendCollapsed;
    const content = document.getElementById('floating-legend-content');
    const toggleBtn = document.getElementById('float-legend-toggle');
    if (content) content.style.display = floatLegendCollapsed ? 'none' : 'block';
    if (toggleBtn) toggleBtn.innerText = floatLegendCollapsed ? '+' : '−';
  }}

  function initPortTabs() {{
    const el = document.getElementById('port-tabs-container');
    if (!el) return;
    let html = '';
    Object.keys(allPortsData).forEach(pk => {{
      const p = allPortsData[pk] || {{}};
      const activeCls = (pk === currentPort ? 'active' : '');
      const trafficStr = (p.traffic_model && typeof p.traffic_model === 'string') 
        ? p.traffic_model.split(' ')[0] 
        : (p.scenario || pk);
      const label = `🔘 ${{pk}} (${{trafficStr}})`;
      html += `<button class="port-tab ${{activeCls}}" id="tab-${{pk}}" onclick="switchPort('${{pk}}')">${{label}}</button>`;
    }});
    el.innerHTML = html;
  }}

  function initMetricButtons() {{
    const el = document.getElementById('layer-btn-grid');
    if (!el) return;
    if (networkMode === 'NSA') {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-nr_rsrp" onclick="setMetric('nr_rsrp')">📡 NR RSRP</button>
        <button class="layer-btn" id="btn-lte_rsrp" onclick="setMetric('lte_rsrp')">📶 LTE RSRP</button>
        <button class="layer-btn" id="btn-nr_pci" onclick="setMetric('nr_pci')">🏷️ NR PCI</button>
        <button class="layer-btn" id="btn-lte_pci" onclick="setMetric('lte_pci')">🏷️ LTE PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ NR SINR</button>
        <button class="layer-btn" id="btn-lte_mac" onclick="setMetric('lte_mac')">🚀 LTE Total MAC</button>
        <button class="layer-btn" id="btn-nr_mac" onclick="setMetric('nr_mac')">🚀 NR Total MAC</button>
        <button class="layer-btn" id="btn-pdcp_total" onclick="setMetric('pdcp_total')">🚀 Total PDCP</button>
      `;
    }} else if (networkMode === 'SA') {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-nr_rsrp" onclick="setMetric('nr_rsrp')">📡 NR RSRP</button>
        <button class="layer-btn" id="btn-nr_pci" onclick="setMetric('nr_pci')">🏷️ NR PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ NR SINR</button>
        <button class="layer-btn" id="btn-fourth" onclick="setMetric('fourth')">🚀 NR Total MAC</button>
      `;
    }} else {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-rsrp" onclick="setMetric('rsrp')">📡 RSRP (dBm)</button>
        <button class="layer-btn" id="btn-pci" onclick="setMetric('pci')">📶 Serving PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ SINR (dB)</button>
        <button class="layer-btn" id="btn-fourth" onclick="setMetric('fourth')">🚀 LTE Total MAC</button>
      `;
    }}
  }}

  function switchPort(pk) {{
    currentPort = pk;
    document.querySelectorAll('.port-tab').forEach(t => t.classList.remove('active'));
    const tabEl = document.getElementById(`tab-${{pk}}`);
    if (tabEl) tabEl.classList.add('active');
    loadPort(pk);
  }}

  let activeSeverities = new Set(['HIGH', 'MED', 'LOW']);

  function loadPort(pk) {{
    const pdata = allPortsData[pk];
    if (!pdata) return;

    // 1. Update Header Stats
    const datePrefix = pdata.date_str ? `${{pdata.date_str}} ` : '';
    const statTraffic = document.getElementById('stat-traffic');
    if (statTraffic) statTraffic.innerHTML = `측정 방식: <b>${{pdata.traffic_model || pdata.scenario || pk}}</b>`;
    const statTime = document.getElementById('stat-time');
    if (statTime) statTime.innerHTML = `측정 일시: <b>${{datePrefix}}${{pdata.start_time || ''}} ~ ${{pdata.end_time || ''}}</b>`;
    const statIncidents = document.getElementById('stat-incidents');
    if (statIncidents) statIncidents.innerHTML = `장애 구간: <b>${{(pdata.episodes || []).length}}개</b>`;

    // 2. Update Map Criteria dynamically from port data (bandwidth-aware)
    if (pdata.map_criteria) {{
      mapCriteria = pdata.map_criteria;
    }}

    // 3. Update 4th Button Label
    const fourthBtn = document.getElementById('btn-fourth');
    if (fourthBtn && pdata.fourth_btn_name) fourthBtn.innerText = pdata.fourth_btn_name;

    // 4. Update Legend & Sidebar
    initLegend();
    initEpisodeList();
    renderLayers();

    // 5. Fit map bounds
    if (pdata.points && pdata.points.length > 0) {{
      const latlngs = pdata.points.map(pt => [pt.lat, pt.lon]);
      const bounds = L.latLngBounds(latlngs);
      map.fitBounds(bounds, {{ padding: [50, 50] }});
    }}
  }}

  function toggleSeverity(sev) {{
    if (activeSeverities.has(sev)) {{
      activeSeverities.delete(sev);
    }} else {{
      activeSeverities.add(sev);
    }}
    const btn = document.getElementById(`btn-sev-${{sev.toLowerCase()}}`);
    if (btn) {{
      if (activeSeverities.has(sev)) {{
        btn.style.opacity = '1.0';
        btn.style.filter = 'none';
      }} else {{
        btn.style.opacity = '0.35';
        btn.style.filter = 'grayscale(80%)';
      }}
    }}
    initEpisodeList();
    renderLayers();
  }}

  function getPciColor(pci) {{
    if (!pci || pci <= 0) return '#64748b';
    if (pciColors && pciColors[pci]) return pciColors[pci];
    const hue = (pci * 137.508) % 360;
    return 'hsl(' + Math.floor(hue) + ', 85%, 55%)';
  }}

  function getPointColor(pt, metric) {{
    const pdata = allPortsData[currentPort];
    if (metric === 'pci' || metric === 'nr_pci') {{
      const targetPci = (pt.nr_pci && pt.nr_pci > 0) ? pt.nr_pci : pt.pci;
      return getPciColor(targetPci);
    }} else if (metric === 'lte_pci') {{
      const targetPci = (pt.lte_pci && pt.lte_pci > 0) ? pt.lte_pci : pt.pci;
      return getPciColor(targetPci);
    }}

    let val = null;
    let targetCritKey = metric;
    if (metric === 'rsrp' || metric === 'nr_rsrp') {{
      val = (pt.nr_rsrp && pt.nr_rsrp < 0) ? pt.nr_rsrp : pt.rsrp;
      targetCritKey = (networkMode === 'NSA' ? 'nr_rsrp' : 'rsrp');
    }} else if (metric === 'lte_rsrp') {{
      val = (pt.lte_rsrp && pt.lte_rsrp < 0) ? pt.lte_rsrp : pt.rsrp;
      targetCritKey = 'lte_rsrp';
    }} else if (metric === 'sinr') {{
      val = (pt.nr_sinr !== undefined && pt.nr_sinr !== null) ? pt.nr_sinr : pt.sinr;
      targetCritKey = (networkMode === 'NSA' ? 'nr_sinr' : 'sinr');
    }} else if (metric === 'pdcp_total') {{
      val = (pt.pdcp_tp !== undefined && pt.pdcp_tp !== null) ? pt.pdcp_tp : pt.dl_tp;
      targetCritKey = 'pdcp_total';
    }} else if (metric === 'nr_mac') {{
      val = (pt.nr_mac_tp !== undefined && pt.nr_mac_tp !== null) ? pt.nr_mac_tp : pt.dl_tp;
      targetCritKey = 'nr_mac';
    }} else if (metric === 'lte_mac') {{
      val = (pt.lte_mac_tp !== undefined && pt.lte_mac_tp !== null) ? pt.lte_mac_tp : pt.dl_tp;
      targetCritKey = 'lte_mac';
    }} else if (metric === 'fourth') {{
      if (pdata.scenario === 'Voice') {{
        val = pt.mos;
        targetCritKey = 'mos';
      }} else if (networkMode === 'NSA') {{
        val = (pt.pdcp_tp !== undefined && pt.pdcp_tp !== null) ? pt.pdcp_tp : pt.dl_tp;
        targetCritKey = 'pdcp_total';
      }} else if (networkMode === 'SA') {{
        val = (pt.nr_mac_tp !== undefined && pt.nr_mac_tp !== null) ? pt.nr_mac_tp : pt.dl_tp;
        targetCritKey = 'nr_mac';
      }} else {{
        val = (pt.lte_mac_tp !== undefined && pt.lte_mac_tp !== null) ? pt.lte_mac_tp : pt.dl_tp;
        targetCritKey = 'lte_mac';
      }}
    }}

    if (val !== null && val !== undefined && mapCriteria[targetCritKey]) {{
      const crit = mapCriteria[targetCritKey];
      for (let i = 0; i < crit.tiers.length; i++) {{
        if (val >= crit.tiers[i].min) {{
          return crit.tiers[i].color;
        }}
      }}
      return crit.tiers[crit.tiers.length - 1].color;
    }}
    return '#38bdf8';
  }}

  let selectedPciSet = new Set();

  function clearPciFilter() {{
    selectedPciSet.clear();
    initLegend();
    renderLayers();
    const pdata = allPortsData[currentPort];
    if (pdata && pdata.points.length > 0) {{
      const latlngs = pdata.points.map(pt => [pt.lat, pt.lon]);
      map.fitBounds(L.latLngBounds(latlngs), {{ padding: [50, 50] }});
    }}
  }}

  function togglePciFilter(pci) {{
    const pciNum = Number(pci);
    if (selectedPciSet.has(pciNum) || selectedPciSet.has(String(pci))) {{
      selectedPciSet.delete(pciNum);
      selectedPciSet.delete(String(pci));
    }} else {{
      selectedPciSet.add(pciNum);
      selectedPciSet.add(String(pci));
    }}
    initLegend();
    renderLayers();

    if (selectedPciSet.size > 0) {{
      const pdata = allPortsData[currentPort];
      const matchedPts = pdata.points.filter(pt => {{
        const curPci = (currentMetric === 'nr_pci' ? pt.nr_pci : (currentMetric === 'lte_pci' ? pt.lte_pci : pt.pci));
        return selectedPciSet.has(curPci) || selectedPciSet.has(Number(curPci)) || selectedPciSet.has(String(curPci));
      }});
      if (matchedPts.length > 0) {{
        const bounds = L.latLngBounds(matchedPts.map(p => [p.lat, p.lon]));
        map.fitBounds(bounds, {{ padding: [60, 60], maxZoom: 16 }});
      }}
    }} else {{
      clearPciFilter();
    }}
  }}

  function setMetric(m) {{
    currentMetric = m;
    selectedPciSet.clear();
    document.querySelectorAll('.layer-btn').forEach(b => {{
      b.classList.remove('active');
    }});
    const activeBtn = document.getElementById(`btn-${{m}}`);
    if (activeBtn) activeBtn.classList.add('active');
    initLegend();
    renderLayers();
  }}

  function initLegend() {{
    const el = document.getElementById('legend-container');
    const floatEl = document.getElementById('floating-legend-content');
    const floatTitle = document.getElementById('float-legend-title-text');
    const pdata = allPortsData[currentPort];
    let legendHtml = '';
    let metricTitle = '📊 지표 범례';

    if (currentMetric === 'pci' || currentMetric === 'nr_pci' || currentMetric === 'lte_pci') {{
      const isNR = (currentMetric === 'nr_pci');
      const isLTE = (currentMetric === 'lte_pci');
      metricTitle = isNR ? '🏷️ 5G NR PSCell PCI (클릭 필터)' : (isLTE ? '📶 LTE Anchor Pcell PCI (클릭 필터)' : '📶 Serving PCI (클릭 필터)');
      
      const allActive = (selectedPciSet.size === 0);
      let html = '<div style="display: flex; flex-wrap: wrap; gap: 5px; max-height: 140px; overflow-y: auto;">';
      html += `<div onclick="clearPciFilter()" style="cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 11px; background: ${{allActive ? '#2563eb' : '#0f172a'}}; color: ${{allActive ? '#fff' : '#94a3b8'}}; padding: 2px 7px; border-radius: 4px; border: 1px solid ${{allActive ? '#38bdf8' : '#334155'}}; font-weight: 700;">
        🌐 ALL PCI
      </div>`;

      Object.keys(pciColors).forEach(pci => {{
        const isSel = selectedPciSet.has(Number(pci)) || selectedPciSet.has(String(pci));
        const op = (!allActive && !isSel) ? '0.4' : '1.0';
        const bg = isSel ? '#1e293b' : '#0f172a';
        const bd = isSel ? '1.5px solid #38bdf8' : '1px solid #334155';
        const shadow = isSel ? 'box-shadow: 0 0 8px rgba(56, 189, 248, 0.7);' : '';
        const prefix = isLTE ? 'LTE ' : (isNR ? 'NR ' : '');

        html += `<div onclick="togglePciFilter('${{pci}}')" style="cursor: pointer; display: flex; align-items: center; gap: 4px; font-size: 11px; background: ${{bg}}; padding: 2px 6px; border-radius: 4px; border: ${{bd}}; ${{shadow}} opacity: ${{op}}; transition: all 0.15s ease;">
          <span style="width: 9px; height: 9px; border-radius: 50%; background: ${{pciColors[pci]}};"></span> ${{prefix}}${{pci}}
        </div>`;
      }});
      html += '</div>';
      legendHtml = html;
    }} else {{
      let targetCritKey = currentMetric;
      if (currentMetric === 'rsrp' || currentMetric === 'nr_rsrp') {{
        targetCritKey = (networkMode === 'NSA' ? 'nr_rsrp' : 'rsrp');
      }} else if (currentMetric === 'sinr') {{
        targetCritKey = (networkMode === 'NSA' ? 'nr_sinr' : 'sinr');
      }} else if (currentMetric === 'fourth') {{
        targetCritKey = (pdata.scenario === 'Voice' ? 'mos' : (networkMode === 'NSA' ? 'pdcp_total' : (networkMode === 'SA' ? 'nr_mac' : 'lte_mac')));
      }} else if (currentMetric === 'pdcp_total') {{
        targetCritKey = 'pdcp_total';
      }} else if (currentMetric === 'nr_mac') {{
        targetCritKey = 'nr_mac';
      }} else if (currentMetric === 'lte_mac') {{
        targetCritKey = 'lte_mac';
      }}

      if (mapCriteria[targetCritKey]) {{
        const crit = mapCriteria[targetCritKey];
        if (targetCritKey === 'mos' && pdata && pdata.fourth_btn_name) {{
          metricTitle = pdata.fourth_btn_name;
        }} else {{
          metricTitle = crit.title;
        }}

        const tierBlocks = crit.tiers.map(t => {{
          return `<div style="flex: 1; text-align: center; background: ${{t.color}}; color: #ffffff; padding: 4px 2px; border-radius: 4px; font-size: 11px; font-weight: 700; text-shadow: 0 1px 2px rgba(0,0,0,0.8); white-space: nowrap;">${{t.label}}</div>`;
        }}).join('');

        legendHtml = `
          <div style="display: flex; gap: 4px; width: 100%; margin-top: 4px;">
            ${{tierBlocks}}
          </div>
        `;
      }}
    }}

    if (el) el.innerHTML = legendHtml;
    if (floatEl) floatEl.innerHTML = legendHtml;
    if (floatTitle) floatTitle.innerText = metricTitle;
  }}

  function initEpisodeList() {{
    const el = document.getElementById('episode-list-container');
    const pdata = allPortsData[currentPort];
    let html = '';
    
    const visibleEpisodes = (pdata.episodes || []).filter(ep => activeSeverities.has(ep.severity));

    if (visibleEpisodes.length === 0) {{
      html = '<div style="color:#64748b; font-size:12px; padding:15px; text-align:center;">표시할 장애 구간이 없습니다</div>';
    }} else {{
      visibleEpisodes.forEach(ep => {{
        const cleanPci = ep.pci_info_text ? ep.pci_info_text.replace(/<[^>]*>?/gm, '') : '';
        html += `
          <div class="episode-item" onclick="focusEpisode(${{ep.id}})">
            <div class="episode-header-row">
              <span class="episode-title-text">${{ep.title}}</span>
              <span class="episode-tag tag-${{ep.severity}}">${{ep.severity}}</span>
            </div>
            <div class="episode-sub-row">
              <span>⏱ ${{ep.time_range}}</span>
              <span>•</span>
              <span>${{cleanPci}}</span>
            </div>
          </div>
        `;
      }});
    }}
    el.innerHTML = html;
  }}

  function renderLayers() {{
    polylineLayers.forEach(l => map.removeLayer(l));
    circleMarkers.forEach(m => map.removeLayer(m));
    corridorLayers.forEach(c => map.removeLayer(c));
    episodeMarkers.forEach(em => map.removeLayer(em));
    polylineLayers = [];
    circleMarkers = [];
    corridorLayers = [];
    episodeMarkers = [];

    const pdata = allPortsData[currentPort];
    if (!pdata || !pdata.points) return;
    const points = pdata.points;

    const hasPciFilter = (selectedPciSet.size > 0) && (currentMetric === 'pci' || currentMetric === 'nr_pci' || currentMetric === 'lte_pci');

    // 1. Route Polylines
    if (points.length > 1) {{
      for (let i = 0; i < points.length - 1; i++) {{
        const p1 = points[i];
        const p2 = points[i + 1];
        const curPci1 = (currentMetric === 'nr_pci' ? p1.nr_pci : (currentMetric === 'lte_pci' ? p1.lte_pci : p1.pci));
        const isMatched = !hasPciFilter || selectedPciSet.has(curPci1) || selectedPciSet.has(Number(curPci1)) || selectedPciSet.has(String(curPci1));

        const color = isMatched ? getPointColor(p1, currentMetric) : '#334155';
        const poly = L.polyline([[p1.lat, p1.lon], [p2.lat, p2.lon]], {{
          color: color,
          weight: isMatched ? 6.0 : 2.0,
          opacity: isMatched ? 0.95 : 0.08,
          lineCap: 'round'
        }}).addTo(map);
        polylineLayers.push(poly);
      }}
    }}

    // 2. High-Visibility 1-Second Circle Markers
    points.forEach((p) => {{
      const curPci = (currentMetric === 'nr_pci' ? p.nr_pci : (currentMetric === 'lte_pci' ? p.lte_pci : p.pci));
      const isMatched = !hasPciFilter || selectedPciSet.has(curPci) || selectedPciSet.has(Number(curPci)) || selectedPciSet.has(String(curPci));

      const color = isMatched ? getPointColor(p, currentMetric) : '#334155';
      const cm = L.circleMarker([p.lat, p.lon], {{
        radius: isMatched ? 5.5 : 2.0,
        fillColor: color,
        color: isMatched ? '#ffffff' : '#475569',
        weight: isMatched ? 1.5 : 0.5,
        opacity: isMatched ? 1.0 : 0.05,
        fillOpacity: isMatched ? 0.95 : 0.05
      }}).addTo(map);

      let tt_body = '';
      const pciDisplay = (networkMode === 'NSA' ? `NR PCI ${{p.nr_pci}} / LTE ${{p.lte_pci}}` : `PCI ${{p.pci}}`);

      const isUlScenario = pdata.scenario && pdata.scenario.includes('UL');
      if (pdata.scenario === 'Voice') {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🎙️ <b>MOS:</b> ${{p.mos}}점 | Loss: ${{p.loss}}% (Jitter: ${{p.jitter}}ms)<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }} else if (isUlScenario) {{
        const ulSpeed = p.ul_tp !== null ? p.ul_tp : (p.pdcp_tp !== null ? p.pdcp_tp : 0.0);
        tt_body = `
          📡 <b>RSRP:</b> ${{p.rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🚀 <b>UL 속도:</b> ${{ulSpeed}} Mbps<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }} else if (networkMode === 'NSA') {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.nr_rsrp}} / ${{p.lte_rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🚀 <b>속도:</b> Total PDCP ${{p.pdcp_tp}}M | NR MAC ${{p.nr_mac_tp}}M | LTE MAC ${{p.lte_mac_tp}}M<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }} else if (networkMode === 'SA') {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.nr_rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🚀 <b>속도:</b> NR MAC ${{p.nr_mac_tp}} Mbps<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }} else {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.lte_rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🚀 <b>속도:</b> LTE MAC ${{p.lte_mac_tp}} Mbps<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }}

      cm.bindTooltip(`
        <div style="font-size: 11px; color: #0f172a; line-height: 1.45;">
          <b>⏱ ${{p.time}} (${{pciDisplay}}) [${{currentPort}}]</b><br>
          ${{tt_body}}
        </div>
      `);
      circleMarkers.push(cm);
    }});

    // 3. Failure Corridors & Badges with Severity Dynamic Colors (HIGH: Red, MED: Amber, LOW: Blue)
    pdata.episodes.forEach(ep => {{
      if (!activeSeverities.has(ep.severity)) return;

      const isHigh = (ep.severity === 'HIGH');
      const isMed = (ep.severity === 'MED');
      const badgeBg = isHigh ? '#ef4444' : (isMed ? '#f59e0b' : '#3b82f6');
      const badgeBorder = isHigh ? '#b91c1c' : (isMed ? '#d97706' : '#2563eb');
      const glowColor = isHigh ? 'rgba(239,68,68,0.8)' : (isMed ? 'rgba(245,158,11,0.8)' : 'rgba(59,130,246,0.8)');

      if (ep.corridor && ep.corridor.length > 1) {{
        const corridorLine = L.polyline(ep.corridor, {{
          color: badgeBg,
          weight: 13,
          opacity: 0.65,
          lineCap: 'round'
        }}).addTo(map);
        corridorLine.on('click', () => openModal(ep));
        corridorLayers.push(corridorLine);
      }}

      const iconHtml = `<div style="display: inline-flex; align-items: center; background: ${{badgeBg}}; color: #ffffff; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; border: 2px solid #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.6), 0 0 12px ${{glowColor}}; cursor: pointer; white-space: nowrap; width: max-content; transform: translate(-50%, -50%); text-shadow: 0 1px 2px rgba(0,0,0,0.8);">${{ep.badge_label}}</div>`;

      const epIcon = L.divIcon({{
        className: 'episode-pin',
        html: iconHtml,
        iconSize: null,
        iconAnchor: [0, 0]
      }});

      const em = L.marker([ep.lat, ep.lon], {{ icon: epIcon }}).addTo(map);
      em.on('click', () => openModal(ep));
      episodeMarkers.push(em);
    }});
  }}

  function openModal(ep) {{
    const panel = document.getElementById('modal-panel');
    document.getElementById('m-title').innerHTML = `${{ep.title}}`;
    const pdata = allPortsData[currentPort];
    
    const isModalUl = pdata.scenario && pdata.scenario.includes('UL');
    const metricColHeader = (pdata.scenario === 'Voice' ? 'MOS' : (isModalUl ? 'UL 속도' : 'DL 속도'));

    let tableHtml = `
      <table class="ctx-table">
        <thead><tr><th>구분</th><th>Time</th><th>PCI</th><th>RSRP</th><th>SINR</th><th>${{metricColHeader}}</th><th>3GPP 시그널링</th><th>비고</th></tr></thead>
        <tbody>
    `;
    ep.timeline.forEach(h => {{
      const isTrig = h.phase.includes('🚨') || h.phase.includes('Trigger') || h.phase.includes('발생') || h.phase.includes('T0');
      tableHtml += `<tr class="${{isTrig ? 'trigger-row' : ''}}">
        <td>${{h.phase}}</td><td>${{h.time}}</td><td>${{h.pci}}</td><td>${{h.rsrp}}</td><td>${{h.sinr}}</td><td>${{h.metric_val}}</td><td class="sig-cell">${{h.sig_msg}}</td><td>${{h.note}}</td>
      </tr>`;
    }});
    tableHtml += '</tbody></table>';

    document.getElementById('m-body').innerHTML = `
      <div class="modal-card">
        <div class="card-title">⏱ 발생 구간 및 기지국</div>
        <div class="card-text"><b>구간:</b> ${{ep.time_range}}<br>${{ep.pci_info_text}}</div>
      </div>
      <div class="modal-card">
        <div class="card-title">🔍 [1] 근본 원인 분석</div>
        <div class="card-text">${{ep.root_cause}}</div>
      </div>
      <div class="modal-card">
        <div class="card-title">⚡ [2] 품질 저하 증상</div>
        <div class="card-text">${{ep.symptoms}}</div>
      </div>
      <div class="modal-card">
        <div class="card-title">📊 [3] 전후 3GPP 시그널링 & RF 타임라인</div>
        ${{tableHtml}}
      </div>
    `;
    panel.classList.add('open');
  }}

  function closeModal() {{
    document.getElementById('modal-panel').classList.remove('open');
  }}

  function focusEpisode(id) {{
    const pdata = allPortsData[currentPort];
    const ep = pdata.episodes.find(e => e.id === id);
    if (ep) {{
      map.setView([ep.lat, ep.lon], 16, {{ animate: true }});
      openModal(ep);
    }}
  }}
</script>
</body>
</html>
"""

        os.makedirs(os.path.dirname(output_html_path), exist_ok=True)
        with open(output_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_html_path
