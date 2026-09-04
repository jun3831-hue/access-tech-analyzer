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
    evaluate_tier,
    LTE_SERVING_RSRP_CRITERIA,
    NR_SS_RSRP_CRITERIA
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

        # Throughput
        col_dl = self._find_col(df_timeline, ['App_DL_Tput', 'PDCP_DL_Tput', 'NR_MAC_DL_Tput', 'LTE_MAC_DL_Tput', 'App DL 속도', 'PDCP DL 속도'])
        col_ul = self._find_col(df_timeline, ['App_UL_Tput', 'PDCP_UL_Tput', 'NR_MAC_UL_Tput', 'App UL 속도', 'PDCP UL 속도'])
        col_pdcp = self._find_col(df_timeline, ['PDCP_DL_Tput', 'PDCP_Total_DL_Tput', 'App_DL_Tput', '5G NR PDCP UL (Mbps)', 'PDCP UL 속도 (Mbps)', 'PDCP DL 속도'])
        col_nr_mac = self._find_col(df_timeline, ['NR_MAC_DL_Tput', 'NR_MAC_DL_Tput_Sum', 'NR_PDSCH_Tput', '5G NR MAC UL (Mbps)', 'NR MAC DL 속도'])
        col_lte_mac = self._find_col(df_timeline, ['LTE_MAC_DL_Tput', 'LTE_MAC_DL_Tput_Sum', 'LTE_Total_MAC_DL_Tput', 'MAC UL 속도 (Mbps)', 'LTE MAC DL 속도'])

        # Voice
        col_mos = self._find_col(df_timeline, ['MOS', 'POLQA'])
        col_jitter = self._find_col(df_timeline, ['Jitter', 'JITTER'])
        col_loss = self._find_col(df_timeline, ['Packet_Loss', 'Loss (%)', 'Loss'])

        col_call_no = self._find_col(df_timeline, ['Call_No', '호 번호'])
        col_phase = self._find_col(df_timeline, ['Call_Phase', '호 상태'])

        points = []
        last_valid_lat = 37.203205
        last_valid_lon = 127.530609

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

            dl_tp = round(float(row[col_dl]), 1) if col_dl and pd.notna(row[col_dl]) else None
            ul_tp = round(float(row[col_ul]), 1) if col_ul and pd.notna(row[col_ul]) else None
            pdcp_tp = round(float(row[col_pdcp]), 1) if col_pdcp and pd.notna(row[col_pdcp]) else (dl_tp if dl_tp is not None else 0.0)
            nr_mac_tp = round(float(row[col_nr_mac]), 1) if col_nr_mac and pd.notna(row[col_nr_mac]) else 0.0
            lte_mac_tp = round(float(row[col_lte_mac]), 1) if col_lte_mac and pd.notna(row[col_lte_mac]) else (dl_tp if dl_tp is not None else 0.0)

            mos_val = round(min(5.0, max(1.0, float(row[col_mos]))), 2) if col_mos and pd.notna(row[col_mos]) else None
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
                "lte_mac_tp": lte_mac_tp
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

        # Universal raw L3 signaling stream extraction from MessageBrowser
        l3_sig_by_sec = {}
        l3_note_by_sec = {}
        if csvs and csvs.get('L3_MSG'):
            l3_source = csvs['L3_MSG']
            try:
                if isinstance(l3_source, pd.DataFrame):
                    df_l3_raw = l3_source
                elif isinstance(l3_source, str) and os.path.exists(l3_source):
                    try:
                        df_l3_raw = pd.read_csv(l3_source, encoding='utf-8', low_memory=False)
                        if df_l3_raw.empty:
                            df_l3_raw = pd.read_csv(l3_source, encoding='cp949', low_memory=False)
                    except Exception:
                        df_l3_raw = pd.read_csv(l3_source, encoding='cp949', low_memory=False)
                else:
                    df_l3_raw = None

                if df_l3_raw is not None and not df_l3_raw.empty:
                    t_cols = [c for c in df_l3_raw.columns if any(k in c.lower() for k in ['time', '시각', '시간'])]
                    m_cols = [c for c in df_l3_raw.columns if any(k in c.lower() for k in ['message', 'msg', '메시지'])]
                    if t_cols and m_cols:
                        t_col = t_cols[0]
                        m_col = m_cols[0]

                        def _extract_sec_str(val):
                            s = str(val).strip()
                            if ' ' in s:
                                s = s.split(' ')[-1]
                            if '.' in s:
                                s = s.split('.')[0]
                            return s[:8]

                        df_l3_raw['__sec_tag'] = df_l3_raw[t_col].apply(_extract_sec_str)

                        MSG_RULES = [
                            ('rrcConnectionReestablishmentReject', '❌ RRCConnectionReestablishmentReject', '단말 재수립 요청 거절 회신', 1),
                            ('rrcConnectionReestablishmentRequest', '⚠️ RRCConnectionReestablishmentRequest', '무선 링크 이상 재수립 요청', 2),
                            ('rrcConnectionRelease', '🚨 RRCConnectionRelease', 'RRC 연결 정상/비정상 해제', 3),
                            ('rrcConnectionReconfigurationComplete', '🔄 RRCConnectionReconfigurationComplete', '핸드오버 완료 보고', 4),
                            ('rrcConnectionReconfiguration', '🔄 RRCConnectionReconfiguration', '기지국 무선 자원 재구성/핸드오버 명령', 5),
                            ('measurementReport', '⚠️ MeasurementReport (MR)', '기지국 측정 보고 (A3/A2 전송)', 6),
                            ('rrcConnectionSetupComplete', '📡 RRCConnectionSetupComplete', 'RRC 연결 수립 완료', 7),
                            ('rrcConnectionSetup', '📡 RRCConnectionSetup', '기지국 접속 승인 및 자원 할당', 8),
                            ('rrcConnectionRequest', '📡 RRCConnectionRequest', '초기 RRC 접속 요청', 9),
                            ('SecurityMode', 'SecurityModeCommand/Complete', '보안 모드 절차', 10),
                            ('Tracking area update', 'TrackingAreaUpdate', '위치 등록 갱신 (TAU)', 11),
                            ('Service request', 'ServiceRequest', '데이터 서비스 요청', 12),
                        ]

                        for sec_tag, grp in df_l3_raw.groupby('__sec_tag'):
                            msgs = grp[m_col].dropna().astype(str).tolist()
                            matched_entries = []
                            for m in msgs:
                                for pattern, label, note_desc, prio in MSG_RULES:
                                    if pattern.lower() in m.lower():
                                        if not any(e[1] == label for e in matched_entries):
                                            matched_entries.append((prio, label, note_desc))
                                        break
                            if matched_entries:
                                matched_entries.sort(key=lambda x: x[0])
                                l3_sig_by_sec[sec_tag] = " | ".join([e[1] for e in matched_entries[:2]])
                                l3_note_by_sec[sec_tag] = " / ".join([e[2] for e in matched_entries[:2]])
            except Exception:
                pass

        formatted_episodes = []

        if episodes:
            for ep_idx, ep in enumerate(episodes, 1):
                raw_title = ep.get('title', f"결함 구간 #{ep_idx}")
                
                trig_dt = ep.get('t_start') or ep.get('trigger_time')
                if not trig_dt and ep.get('events'):
                    trig_dt = ep['events'][0].get('timestamp')

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
                    matched_idx = min(ep_idx * 50, len(points) - 1)

                dur_sec = ep.get('duration_sec', 10.0)
                dur_pts = max(3, min(60, int(dur_sec)))

                start_idx = max(0, matched_idx - 2)
                end_sec = _to_sec(ep.get('t_end'))
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
                ep_sev = str(ep.get('severity') or ep.get('grade') or 'MED').upper()
                if ep_sev not in ['HIGH', 'MED', 'LOW']:
                    ep_sev = "MED"

                # Standard RAT resolution
                srv_rat = ep.get('srv_rat')
                if srv_rat:
                    rat_str = "5G NR" if ("NR" in srv_rat or "5G" in srv_rat) else srv_rat
                elif "5G" in raw_title or "NR" in raw_title or "DIAG_M_01_NR" in diag_code:
                    rat_str = "5G NR"
                elif scenario == "Voice" or "VoLTE" in raw_title or "DIAG_M_06" in diag_code or "Voice" in domain:
                    rat_str = "VoLTE"
                else:
                    rat_str = "LTE"

                dom_tag = "🅝" if rat_str == "5G NR" else ("🆅" if rat_str == "VoLTE" else "🅻")
                prefix_tag = "🚨" if ep_sev == "HIGH" else dom_tag

                # Clean Multi-UE Port Tag
                involved_ports = ep.get('involved_ports', [])
                is_multi = ep.get('is_multi_ue') or (len(involved_ports) > 1)
                port_tag = f" [{'+'.join(involved_ports)}]" if (is_multi and involved_ports) else ""

                # Target PCI string
                target_pci = ep.get('tgt_pci') if ep.get('tgt_pci') is not None else (points[end_idx]['pci'] if points and end_idx < len(points) else '')
                tgt_str = f"PCI {target_pci}" if target_pci else "타겟"

                # Check actual call drop strictly
                has_call_drop = ep.get('has_call_drop', False)
                if not has_call_drop:
                    has_call_drop = any(
                        ev.get('severity') == 'HIGH' and any(k in ev.get('name', '') for k in ['RLF', 'Radio Link Failure', 'Reestablishment Reject', '호 절단', 'Call Drop', 'e-RAB Drop'])
                        for ev in ep.get('events', [])
                    )

                rep_cnt = ep.get('rep_cnt') or (ep['events'][0].get('count') if ep.get('events') else 0)
                cnt_str = f" (A3 MR {rep_cnt}회)" if rep_cnt and rep_cnt > 0 else ""
                cnt_title_str = f" (A3 MR {rep_cnt}회 연속 송신)" if rep_cnt and rep_cnt > 0 else ""

                # Declarative Priority Hierarchy for Title & Badge Selection
                # Rank 1: Terminal Link Failure / Call Drop / Reject
                # Rank 2: Compound Failure (Unhandled HO with Call Drop, Ping-Pong with Call Drop)
                # Rank 3: Ping-Pong Handover / Bounded Multi-cell Loop (Transition chain format preserved)
                # Rank 4: PCI Collision
                # Rank 5: Physical Layer Degradation (MIMO / CRC)
                # Rank 6: Unhandled HO / Delay (Lowest priority: ONLY when no call drop or ping-pong)
                candidates = []

                # Evaluate Rank 1 & 2: Terminal Link Failure & Compound Failure
                if has_call_drop:
                    if ep.get('has_unhandled_ho') or 'A3' in raw_title or '방치' in raw_title:
                        candidates.append((1, f"타겟({tgt_str}) HO 방치 후 호 단절{cnt_str}", f"타겟({tgt_str}) HO 방치 후 RLF 및 RRE 거절 호 단절{cnt_str}"))
                    elif ep.get('has_ping_pong') or "핑퐁" in raw_title:
                        full_pci_chain = ep.get('pci_chain') or pci_path_str
                        candidates.append((1, f"핑퐁 중 호 단절 ({full_pci_chain})", f"핑퐁 핸드오버 중 기지국 링크 붕괴 및 호 단절 ({full_pci_chain})"))
                    else:
                        candidates.append((1, "RLF 및 RRE 거절 호 단절", "기지국 링크 붕괴 및 RLF/RRE 거절 호 단절"))
                elif ep.get('has_rach_problem') or "RACH Problem" in raw_title:
                    candidates.append((1, "상향 RACH 실패 RLF", "상향 RACH 실패 (RACH Problem RLF)"))

                # Evaluate Rank 3: Ping-Pong Handover (User-preferred 924 ➔ 40 ➔ 924 chain format preserved)
                if ep.get('has_ping_pong') or "핑퐁" in raw_title or "DIAG_M_01_PINGPONG" in diag_code:
                    full_pci_chain = ep.get('pci_chain') or pci_path_str
                    candidates.append((3, f"핑퐁 ({full_pci_chain})", f"핑퐁 핸드오버 ({full_pci_chain})"))

                # Evaluate Rank 4: PCI Collision
                if "중복 PCI" in raw_title or "DIAG_M_05" in diag_code:
                    candidates.append((4, f"중복 PCI 발췌 ({tgt_str})", f"중복 PCI 발췌 ({tgt_str})"))

                # Evaluate Rank 5: Physical Layer Degradation
                if ep.get('has_mimo') or "MIMO" in raw_title or "DIAG_M_01_NR" in diag_code:
                    candidates.append((5, "MIMO 랭크 저하", "고신호 구간 MIMO 랭크 저하 (Layer 제한)"))
                if ep.get('has_crc') or "CRC" in raw_title or "PDSCH" in raw_title or "DIAG_M_02_NR" in diag_code:
                    candidates.append((5, "PDSCH 복조 실패", "하향 PDSCH 복조 실패 (CRC 에러 / High BLER)"))

                # Evaluate Rank 6: Unhandled HO / Delay (Normal call preserved)
                if ep.get('has_unhandled_ho') or "무응답" in raw_title or "A3" in raw_title:
                    candidates.append((6, f"타겟({tgt_str}) HO 요청 무응답{cnt_str}", f"타겟({tgt_str}) 핸드오버 요청 무응답{cnt_title_str}"))

                # Deterministically select highest priority candidate (lowest rank integer)
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    _, base_badge, base_title = candidates[0]
                else:
                    clean_raw = re.sub(r'\[.*?\]', '', raw_title).strip()
                    base_badge = clean_raw
                    base_title = clean_raw

                # Single-pass assemble without duplicate tags
                badge_label = f"{prefix_tag} [{time_tag}] {rat_str} {base_badge}"
                clean_title = f"{prefix_tag} [{time_tag}] {rat_str} {base_title}"

                cause_conclusion = ep.get('cause_conclusion', '')
                rc_list = ep.get('root_causes', [])
                if rc_list:
                    rc_details = "\n".join([f"• {rc.get('name', '')}: {rc.get('detail', '')}" for rc in rc_list])
                    root_cause_text = f"{cause_conclusion}\n\n[상세 인과 요인]\n{rc_details}" if cause_conclusion else rc_details
                else:
                    root_cause_text = cause_conclusion or "기지국 간 전계 중첩 및 핸드오버 지연으로 인한 품질 저하"

                story_steps = ep.get('story_steps', [])
                symp_list = ep.get('symptoms', [])
                if story_steps:
                    symptoms_text = "\n".join([f"• {step}" for step in story_steps])
                elif symp_list:
                    symptoms_text = "\n".join([f"• {s.get('name', '')}: {s.get('detail', '')}" for s in symp_list])
                else:
                    symptoms_text = f"구간 지속 시간: {dur_sec:.1f}초 | 무선 링크 품질 저하 발생"

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
                        if "RLF" in step_text or "무선 링크 단절" in step_text:
                            event_map[step_t] = "🚨 RadioLinkFailure (RLF)"
                            note_map[step_t] = step_text
                        elif "Reestablishment" in step_text or "거절" in step_text or "Reject" in step_text:
                            event_map[step_t] = "❌ RRCConnectionReestablishmentReject"
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
                    if "RACH" in raw_title:
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
                end_dt_val = ep.get('t_end')
                end_time_tag = end_dt_val.strftime('%H:%M:%S') if hasattr(end_dt_val, 'strftime') else (str(end_dt_val).split(' ')[-1][:8] if end_dt_val else (points[end_idx]['time'] if points and end_idx < len(points) else ''))
                end_sec = _to_sec(end_time_tag)

                start_pt_sec = _to_sec(points[max(0, matched_idx - 2)]['time']) if points else t0_sec
                win_start_sec = max(0, min(start_pt_sec, t0_sec) - 6)
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
                        metric_val = f"{ctx_pt['mos']}점" if scenario == "Voice" else (f"{ctx_pt['dl_tp']} Mbps" if ctx_pt['dl_tp'] is not None else "0.0 Mbps")
                    else:
                        pci_val = target_pci or trigger_pt['pci']
                        rsrp_val = "미수집"
                        sinr_val = "미수집"
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

                time_range_str = f"{time_tag} ~ {end_time_tag} ({dur_sec:.1f}초간)" if (time_tag and end_time_tag) else f"{points[start_idx]['time']} ~ {points[end_idx]['time']} ({end_idx - start_idx + 1}초간)"

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

        # Strict Chronological Sorting
        formatted_episodes.sort(key=lambda x: x['start_idx'])
        for idx, ep in enumerate(formatted_episodes, 1):
            ep['id'] = idx

        return formatted_episodes

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

            fourth_btn_name = "🎙️ VoLTE MOS" if scenario == "Voice" else ("🚀 Throughput" if scenario in ["DL", "SST"] else "⬆️ Throughput")
            fourth_btn_key = "mos" if scenario == "Voice" else ("dl_tp" if scenario in ["DL", "SST"] else "ul_tp")

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
                "points": clean_pts,
                "episodes": eps,
                "total_points": len(clean_pts),
                "date_str": date_str,
                "start_time": clean_pts[0]['time'] if clean_pts else "00:00:00",
                "end_time": clean_pts[-1]['time'] if clean_pts else "00:00:00"
            }

        sorted_pcis = sorted(list(all_unique_pcis))
        pci_color_map = {pci: PCI_COLOR_PALETTE[i % len(PCI_COLOR_PALETTE)] for i, pci in enumerate(sorted_pcis)}

        ports_json = json.dumps(packaged_ports, ensure_ascii=False)
        pci_colors_json = json.dumps(pci_color_map, ensure_ascii=False)
        criteria_json = json.dumps(get_all_map_criteria_dict(), ensure_ascii=False)

        default_port = list(packaged_ports.keys())[0] if packaged_ports else "M1"
        def_pts = packaged_ports[default_port]['points'] if default_port in packaged_ports else []
        center_lat = def_pts[len(def_pts) // 2]['lat'] if def_pts else 37.2032
        center_lon = def_pts[len(def_pts) // 2]['lon'] if def_pts else 127.5306

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
  const mapCriteria = {criteria_json};
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
    const isNSA = (networkMode === 'NSA');

    if (isNSA) {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-nr_rsrp" onclick="setMetric('nr_rsrp')">📡 NR RSRP</button>
        <button class="layer-btn" id="btn-lte_rsrp" onclick="setMetric('lte_rsrp')">📶 LTE RSRP</button>
        <button class="layer-btn" id="btn-nr_pci" onclick="setMetric('nr_pci')">🏷️ NR PCI</button>
        <button class="layer-btn" id="btn-lte_pci" onclick="setMetric('lte_pci')">🏷️ LTE PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ NR SINR</button>
        <button class="layer-btn" id="btn-fourth" onclick="setMetric('fourth')">🚀 Throughput</button>
      `;
    }} else {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-rsrp" onclick="setMetric('rsrp')">📡 RSRP (dBm)</button>
        <button class="layer-btn" id="btn-pci" onclick="setMetric('pci')">📶 Serving PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ SINR (dB)</button>
        <button class="layer-btn" id="btn-fourth" onclick="setMetric('fourth')">🚀 Throughput</button>
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

    // 2. Update 4th Button Label
    const fourthBtn = document.getElementById('btn-fourth');
    if (fourthBtn && pdata.fourth_btn_name) fourthBtn.innerText = pdata.fourth_btn_name;

    // 3. Update Legend & Sidebar
    initLegend();
    initEpisodeList();
    renderLayers();

    // 4. Fit map bounds
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
      }} else {{
        val = (pdata.scenario === 'DL' ? pt.dl_tp : pt.ul_tp);
        targetCritKey = 'app_tp';
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
        <button class="layer-btn" id="btn-pdcp_total" onclick="setMetric('pdcp_total')">🚀 PDCP Total</button>
        <button class="layer-btn" id="btn-nr_mac" onclick="setMetric('nr_mac')">⚡ NR Total MAC</button>
        <button class="layer-btn" id="btn-lte_mac" onclick="setMetric('lte_mac')">📶 LTE Total MAC</button>
      `;
    }} else if (networkMode === 'SA') {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-nr_rsrp" onclick="setMetric('nr_rsrp')">📡 NR RSRP</button>
        <button class="layer-btn" id="btn-nr_pci" onclick="setMetric('nr_pci')">🏷️ NR PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ NR SINR</button>
        <button class="layer-btn" id="btn-nr_mac" onclick="setMetric('nr_mac')">🚀 NR Total MAC</button>
      `;
    }} else {{
      el.innerHTML = `
        <button class="layer-btn active" id="btn-rsrp" onclick="setMetric('rsrp')">📡 RSRP (dBm)</button>
        <button class="layer-btn" id="btn-pci" onclick="setMetric('pci')">📶 Serving PCI</button>
        <button class="layer-btn" id="btn-sinr" onclick="setMetric('sinr')">⚡ SINR (dB)</button>
        <button class="layer-btn" id="btn-lte_mac" onclick="setMetric('lte_mac')">🚀 LTE Total MAC</button>
      `;
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
        targetCritKey = (pdata.scenario === 'Voice' ? 'mos' : 'app_tp');
      }}

      if (mapCriteria[targetCritKey]) {{
        const crit = mapCriteria[targetCritKey];
        metricTitle = crit.title;

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

      if (pdata.scenario === 'Voice') {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🎙️ <b>MOS:</b> ${{p.mos}}점 | Loss: ${{p.loss}}% (Jitter: ${{p.jitter}}ms)<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }} else if (networkMode === 'NSA') {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.nr_rsrp}} / ${{p.lte_rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🚀 <b>속도:</b> PDCP ${{p.pdcp_tp}}M | NR ${{p.nr_mac_tp}}M | LTE ${{p.lte_mac_tp}}M<br>
          🚗 ${{p.call_no}} [${{p.call_phase}}] (${{p.speed}} km/h)
        `;
      }} else {{
        tt_body = `
          📡 <b>RSRP:</b> ${{p.rsrp}} dBm | ⚡ <b>SINR:</b> ${{p.sinr}} dB<br>
          🚀 <b>속도:</b> LTE ${{p.lte_mac_tp}} Mbps<br>
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
    
    const metricColHeader = (pdata.scenario === 'Voice' ? 'MOS' : '속도');

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
