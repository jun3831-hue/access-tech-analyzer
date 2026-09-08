# -*- coding: utf-8 -*-
r"""
File: 4_Optis_AI_Analyzer/core/master_workbook_builder.py
Description: M1~M4 Multi-UE Master Consolidated Excel Workbook Builder (_Master.xlsx)
- Automatically separates sheets per traffic model (M1_DL, M1_UL, M1_Ping, M1_VoLTE, etc.)
- Standard 3-tier vertical structure for each traffic sheet:
    [1. 전체 종합 요약]
    [2. Call 단위 결과]
    [3. 초(sec) 단위 결과]
- Dedicated header sets for DL, UL, VoLTE, and Ping scenarios
- Seamless unit conversion: kbps -> Mbps (/1000.0) for App DL/UL Throughput
- Unified Sheet 1 '01_통합_요약' executive comparison dashboard
- Clean removal of legacy _per_call and _Voice_Call duplicate sheets
"""

import os
import sys
import re
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows


class MasterWorkbookBuilder:
    """
    Consolidates M1, M2, M3, M4 multi-UE test results into a standardized Master Excel Workbook.
    """

    def __init__(self):
        pass

    # =========================================================================
    # Standard Header Specifications per Scenario
    # =========================================================================
    STANDARD_DL_HEADERS = [
        '시간 (구간)', 'Lon', 'Lat', '호 번호', '호 상태 (성공률)',
        'App DL 속도 (Mbps)', 'PDCP DL 속도 (Mbps)', 'NR MAC DL 속도 (Mbps)', 'NR PDSCH 속도 (Mbps)',
        'LTE MAC DL 속도 (Mbps)', 'LTE PDSCH 속도 (Mbps)',
        '[NR] gNB-Cell ID', '[NR] Serving PCI', '[NR] SS-RSRP (dBm)', '[NR] SS-SINR (dB)', '[NR] SS-RSRQ (dB)',
        '[NR] CQI', '[NR] DL MCS', '[NR] PDSCH BLER (%)', '[NR] DL RB Num (Inc 0)', '[NR] WB RI',
        '[NR] 64QAM Rate (%)', '[NR] 256QAM Rate (%)',
        '[LTE] eNB-Cell ID', '[LTE] Serving PCI', '[LTE] Serving RSRP (dBm)', '[LTE] Serving SINR (dB)', '[LTE] Serving RSRQ (dB)',
        '[LTE] CQI', '[LTE] DL MCS', '[LTE] PDSCH BLER (%)', '[LTE] DL RB Num (Inc 0)', '[LTE] 256QAM Rate (%)',
        '이동속도 (km/h)'
    ]

    STANDARD_UL_HEADERS = [
        '시간 (구간)', 'Lon', 'Lat', '호 번호', '호 상태 (성공률)',
        'App UL 속도 (Mbps)', 'PDCP UL 속도 (Mbps)', 'NR MAC UL 속도 (Mbps)', 'NR PUSCH 속도 (Mbps)',
        'LTE MAC UL 속도 (Mbps)', 'LTE PUSCH 속도 (Mbps)',
        '[NR] gNB-Cell ID', '[NR] Serving PCI', '[NR] SS-RSRP (dBm)', '[NR] SS-SINR (dB)', '[NR] SS-RSRQ (dB)',
        '[NR] Power Headroom (dB)', '[NR] UL MCS', '[NR] PUSCH BLER (%)', '[NR] PUSCH Power (dBm)',
        '[LTE] eNB-Cell ID', '[LTE] Serving PCI', '[LTE] Serving RSRP (dBm)', '[LTE] Serving SINR (dB)', '[LTE] Serving RSRQ (dB)',
        '[LTE] Power Headroom (dB)', '[LTE] UL MCS', '[LTE] PUSCH BLER (%)', '[LTE] PUSCH Power (dBm)',
        '이동속도 (km/h)'
    ]

    STANDARD_VOICE_HEADERS = [
        '시간 (구간)', 'Lon', 'Lat', '호 번호', '호 상태 (성공률)',
        '음성 코덱 (Codec)', 'Audio MOS', 'DL RTP Packet Loss (%)', 'RTP Jitter (ms)',
        'Rx Packet Loss Count', 'Rx Packet Loss Time (ms)',
        '[NR] gNB-Cell ID', '[NR] Serving PCI', '[NR] SS-RSRP (dBm)', '[NR] SS-SINR (dB)',
        '[LTE] eNB-Cell ID', '[LTE] Serving PCI', '[LTE] Serving RSRP (dBm)', '[LTE] Serving SINR (dB)',
        '이동속도 (km/h)'
    ]

    STANDARD_PING_HEADERS = [
        '시간 (구간)', 'Lon', 'Lat', '호 번호', '호 상태 (성공률)',
        'Ping RTT (ms)', 'Ping 결과', 'Ping 손실률 (%)', 'RTT Jitter (ms)',
        '[NR] gNB-Cell ID', '[NR] Serving PCI', '[NR] SS-RSRP (dBm)', '[NR] SS-SINR (dB)',
        '[LTE] eNB-Cell ID', '[LTE] Serving PCI', '[LTE] Serving RSRP (dBm)', '[LTE] Serving SINR (dB)',
        '이동속도 (km/h)'
    ]

    # Legacy compatibility alias
    STANDARD_34_HEADERS = STANDARD_DL_HEADERS

    HEADER_TO_SOURCE_COLS = {
        # Common
        '시간 (구간)': ['TIME_STAMP', '시간 구간', '시간'],
        'Lon': ['[Call & GPS Lon]', 'Lon', '경도'],
        'Lat': ['[Call & GPS Lat]', 'Lat', '위도'],
        '호 번호': ['Call_No', 'Call_Index', '[Call & Call State Call No]', '호 번호'],
        '호 상태 (성공률)': ['Call_Phase', '[Call & Call State Call Event]', '호 상태', '호 상태/구간'],
        '이동속도 (km/h)': ['[Call & GPS Speed (km/h)]', 'Speed', 'GPS 속도 (km/h)', '이동속도 (km/h)'],

        # DL Traffic
        'App DL 속도 (Mbps)': ['[Call & APP Throughput Info(All Data) All FWD  Throughput (kbps)]', '[Call & Speed Test T-put Current App Throughput [Mbps]]', 'App_DL_Tput', 'App DL 속도 (Mbps)', 'App DL 속도'],
        'PDCP DL 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]', '[Call & LTE KPI PDCP DL Throughput [Mbps]]', 'PDCP_DL_Tput', 'PDCP DL 속도 (Mbps)', 'PDCP DL 속도'],
        'NR MAC DL 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]', 'NR_MAC_DL_Tput', '5G NR MAC Total (Mbps)', 'NR MAC DL 속도 (Mbps)', 'NR MAC DL 속도'],
        'NR PDSCH 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PDSCH Throughput [Mbps]]', 'NR_PDSCH_Tput', 'PDSCH 속도 (Mbps)'],
        'LTE MAC DL 속도 (Mbps)': ['[Call & LTE KPI MAC DL Throughput [Mbps]]', '[Call & LTE KPI Total Info Layer2 MAC DL Throughput [Mbps]]', 'LTE_MAC_DL_Tput', 'LTE MAC Total (Mbps)', 'LTE MAC DL 속도 (Mbps)', 'MAC DL 속도 (Mbps)'],
        'LTE PDSCH 속도 (Mbps)': ['[Call & LTE KPI PDSCH Throughput [Mbps]]', 'LTE_PDSCH_Tput', 'PDSCH 속도 (Mbps)'],

        # UL Traffic
        'App UL 속도 (Mbps)': ['[Call & APP Throughput Info(All Data) All RVS Throughput (kbps)]', '[Call & Speed Test T-put Current App Throughput [Mbps]]', 'App_UL_Tput', 'App UL 속도 (Mbps)', 'App UL 속도'],
        'PDCP UL 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]]', '[Call & LTE KPI PDCP UL Throughput [Mbps]]', 'PDCP_UL_Tput', 'PDCP UL 속도 (Mbps)', 'PDCP UL 속도'],
        'NR MAC UL 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer2 MAC UL Throughput [Mbps]]', 'NR_MAC_UL_Tput', '5G NR MAC UL Total (Mbps)', 'NR MAC UL 속도 (Mbps)'],
        'NR PUSCH 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer1 PUSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PUSCH Throughput [Mbps]]', 'NR_PUSCH_Tput', 'PUSCH 속도 (Mbps)'],
        'LTE MAC UL 속도 (Mbps)': ['[Call & LTE KPI MAC UL Throughput [Mbps]]', '[Call & LTE KPI Total Info Layer2 MAC UL Throughput [Mbps]]', 'LTE_MAC_UL_Tput', 'LTE MAC UL 속도 (Mbps)'],
        'LTE PUSCH 속도 (Mbps)': ['[Call & LTE KPI PUSCH Throughput [Mbps]]', 'LTE_PUSCH_Tput', 'PUSCH 속도 (Mbps)'],
        '[NR] Power Headroom (dB)': ['[Call & 5G KPI PCell Layer1 UL Power Headroom (dB)]', 'Power Headroom', 'PHR'],
        '[NR] UL MCS': ['[Call & 5G KPI PCell Layer1 UL MCS (Avg)]', 'NR_UL_MCS', '5G UL MCS', 'UL_MCS'],
        '[NR] PUSCH BLER (%)': ['[Call & 5G KPI PCell Layer1 UL BLER [%]]', 'NR_PUSCH_BLER', 'PUSCH_BLER'],
        '[NR] PUSCH Power (dBm)': ['[Call & 5G KPI PCell RF PUSCH Power [dBm]]', 'NR_PUSCH_Power'],
        '[LTE] Power Headroom (dB)': ['[Call & LTE KPI PCell Power Headroom [dB]]', 'LTE Power Headroom', 'PHR'],
        '[LTE] UL MCS': ['[Call & LTE KPI PCell UL MCS]', 'LTE_UL_MCS', 'UL MCS'],
        '[LTE] PUSCH BLER (%)': ['[Call & LTE KPI PCell PUSCH BLER [%]]', 'LTE_PUSCH_BLER'],
        '[LTE] PUSCH Power (dBm)': ['[Call & LTE KPI PCell PUSCH Power [dBm]]', 'LTE_PUSCH_Power'],

        # Voice / VoLTE
        '음성 코덱 (Codec)': ['Vocoder Mode(DL)', 'Vocoder Mode', 'Codec', '음성 코덱'],
        'Audio MOS': ['[Voice Quality Info Audio MOS]', 'Audio MOS', 'MOS', 'POLQA', 'P863(POLQA)'],
        'DL RTP Packet Loss (%)': ['RxPacketLossRate', '[Call & Audio Rx Packet Loss (%)]', 'Audio Rx Packet Loss (%)', 'Packet_Loss'],
        'RTP Jitter (ms)': ['RxJitter', '[Call & Audio Rx Jitter (ms)]', 'Audio Rx Jitter (ms)', 'Jitter', 'RTP Jitter (ms)'],
        'Rx Packet Loss Count': ['[Call & Audio Rx Packet Loss Count]', 'Rx Packet Loss Count', 'Rx Loss Count'],
        'Rx Packet Loss Time (ms)': ['[Call & Audio Rx Packet Loss Time (ms)]', 'Rx Packet Loss Time (ms)', 'Loss Time'],

        # Ping
        'Ping RTT (ms)': ['[Call & SKT Speed Test Call Info Ping Event Info Ping Response]', '[Call & SKT Speed Test Call Info Ping Event Info Ping Throughput Result]', 'SST_Ping_Result', 'Ping RTT (ms)', 'RTT (ms)', 'RTT'],
        'Ping 결과': ['[Call & SKT Speed Test Call Info Ping Event Info Ping Result]', 'Ping_Result', 'Ping 결과'],
        'Ping 손실률 (%)': ['[Call & SKT Speed Test Call Info Ping Event Info Ping Loss Rate]', 'Ping_Loss_Rate', 'Loss Rate'],
        'RTT Jitter (ms)': ['[Call & SKT Speed Test Call Info Ping Event Info Ping Jitter]', 'Ping_Jitter', 'RTT Jitter'],

        # NR RF / PHY
        '[NR] gNB-Cell ID': ['[Call & 5G KPI PCell RF Serving gNB ID-Cell ID]', 'NR_Cell_ID', 'gNB_Cell_ID', 'PCell gNB-Cell ID'],
        '[NR] Serving PCI': ['[Call & 5G KPI PCell RF Serving PCI]', 'NR_Serving_PCI', '5G PSCell PCI', 'NR_PCI'],
        '[NR] SS-RSRP (dBm)': ['[Call & 5G KPI PCell RF Serving SS-RSRP [dBm]]', 'NR_SS_RSRP', '5G SS-RSRP (dBm)', 'SS_RSRP'],
        '[NR] SS-SINR (dB)': ['[Call & 5G KPI PCell RF Serving SS-SINR [dB]]', 'NR_SS_SINR', '5G SS-SINR (dB)', 'SS_SINR'],
        '[NR] SS-RSRQ (dB)': ['[Call & 5G KPI PCell RF Serving SS-RSRQ [dB]]', 'NR_SS_RSRQ', '5G SS-RSRQ (dB)', 'SS_RSRQ'],
        '[NR] CQI': ['[Call & 5G KPI PCell RF CQI]', 'NR_CQI', '5G PSCell CQI', 'CQI'],
        '[NR] DL MCS': ['[Call & 5G KPI PCell Layer1 DL MCS (Avg)]', 'NR_DL_MCS', '5G DL MCS', 'DL_MCS'],
        '[NR] PDSCH BLER (%)': ['[Call & 5G KPI PCell Layer1 DL BLER [%]]', 'NR_PDSCH_BLER', '5G PDSCH BLER (%)', 'PDSCH_BLER'],
        '[NR] DL RB Num (Inc 0)': ['[Call & 5G KPI PCell Layer1 DL RB Num (Including 0)]', 'NR_PRB_Inc0', '5G NR RB (inc0)', 'PRB_Num_Inc0'],
        '[NR] WB RI': ['[Call & 5G KPI PCell RF RI(Avg)]', 'NR_WB_RI', '5G RI (Avg)', 'WB_RI'],
        '[NR] 64QAM Rate (%)': ['[Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]]', 'NR_QAM64_Rate', '5G 64QAM (%)', 'QAM64_Rate'],
        '[NR] 256QAM Rate (%)': ['[Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]]', 'NR_QAM256_Rate', '5G 256QAM (%)', 'QAM256_Rate'],

        # LTE RF / PHY
        '[LTE] eNB-Cell ID': ['[Call & LTE KPI PCell Serving eNB ID-Cell ID]', 'eNB_Cell_ID', 'LTE PCell eNB-Cell ID', 'PCell eNB-Cell ID'],
        '[LTE] Serving PCI': ['[Call & LTE KPI PCell Serving PCI]', 'LTE_Serving_PCI', 'LTE PCell PCI', 'Serving PCI'],
        '[LTE] Serving RSRP (dBm)': ['[Call & LTE KPI PCell Serving RSRP [dBm]]', 'LTE_RSRP', 'LTE PCell RSRP (dBm)', 'Serving RSRP (dBm)'],
        '[LTE] Serving SINR (dB)': ['[Call & LTE KPI PCell SINR [dB]]', 'LTE_SINR', 'LTE PCell SINR (dB)', 'Serving SINR (dB)'],
        '[LTE] Serving RSRQ (dB)': ['[Call & LTE KPI PCell Serving RSRQ [dB]]', 'LTE_RSRQ', 'LTE PCell RSRQ (dB)', 'Serving RSRQ (dB)'],
        '[LTE] CQI': ['[Call & LTE KPI PCell WB CQI CW0]', 'LTE_CQI', 'LTE PCell WB CQI', 'CQI'],
        '[LTE] DL MCS': ['[Call & LTE KPI PCell DL MCS0]', 'LTE_DL_MCS', 'LTE PCell DL MCS', 'DL MCS'],
        '[LTE] PDSCH BLER (%)': ['[Call & LTE KPI PCell PDSCH BLER [%]]', 'LTE_PDSCH_BLER', 'LTE PCell PDSCH BLER (%)', 'PDSCH BLER (%)'],
        '[LTE] DL RB Num (Inc 0)': ['[Call & LTE KPI PCell PDSCH PRB Number(Including 0)]', 'LTE_PRB_Inc0', 'LTE PCell PRB Num (inc0)', 'DL RB Num (Inc 0)'],
        '[LTE] 256QAM Rate (%)': ['[Call & LTE KPI SCell[2] DL Modulation0]', 'LTE_QAM256_Rate', 'LTE 256QAM (%)', '256QAM Rate (%)']
    }

    @classmethod
    def _find_source_col(cls, df: Optional[pd.DataFrame], header: str) -> Optional[str]:
        if df is None or df.empty:
            return None
        cands = cls.HEADER_TO_SOURCE_COLS.get(header, [header])
        # 1. Exact match
        for cand in cands:
            if cand in df.columns:
                return cand
        # 2. Case-insensitive exact match
        for cand in cands:
            cand_clean = cand.strip().lower()
            for c in df.columns:
                if str(c).strip().lower() == cand_clean:
                    return c
        # 3. Substring match
        for cand in cands:
            cand_clean = cand.strip('[]').strip().lower()
            if len(cand_clean) >= 4:
                for c in df.columns:
                    if cand_clean in str(c).strip('[]').strip().lower():
                        return c
        return None

    @staticmethod
    def _get_series(df: Optional[pd.DataFrame], candidates: List[str]) -> pd.Series:
        if df is None or df.empty:
            return pd.Series([], dtype=float)
        for c in candidates:
            if c in df.columns:
                s = pd.to_numeric(df[c], errors='coerce').dropna()
                if not s.empty:
                    return s
        return pd.Series([], dtype=float)

    @classmethod
    def _get_val_from_df(cls, df: Optional[pd.DataFrame], header: str, agg: str = 'mean') -> Any:
        col = cls._find_source_col(df, header)
        if not col or df is None or df.empty:
            return np.nan
        s = df[col].dropna()
        if s.empty:
            return np.nan
        if agg == 'mode':
            modes = s.mode()
            return modes.iloc[0] if not modes.empty else s.iloc[0]
        elif agg == 'first':
            return s.iloc[0]
        elif agg == 'last':
            return s.iloc[-1]
        else:  # mean
            s_num = pd.to_numeric(s, errors='coerce').dropna()
            if not s_num.empty:
                val = float(s_num.mean())
                if ('App DL 속도' in header or 'App UL 속도' in header) and ('kbps' in str(col).lower() or val > 10000):
                    val = val / 1000.0
                return round(val, 2)
            return s.iloc[0]

    def _extract_1sec_rows(self, df_tl: pd.DataFrame, headers: List[str]) -> List[Dict[str, Any]]:
        rows = []
        if df_tl is None or df_tl.empty:
            return rows

        for _, r in df_tl.iterrows():
            row_dict = {}
            for h in headers:
                if h == '시간 (구간)':
                    ts = r.get('TIME_STAMP')
                    if isinstance(ts, (pd.Timestamp, datetime)):
                        row_dict[h] = ts.strftime('%H:%M:%S')
                    else:
                        row_dict[h] = str(ts).split(" ")[-1].split(".")[0] if pd.notna(ts) else ""
                elif h == '호 번호':
                    row_dict[h] = str(r.get('Call_No', 'Call 1')) if pd.notna(r.get('Call_No')) else 'Call 1'
                elif h == '호 상태 (성공률)':
                    row_dict[h] = str(r.get('Call_Phase', 'Traffic')) if pd.notna(r.get('Call_Phase')) else 'Traffic'
                else:
                    col = self._find_source_col(df_tl, h)
                    val = r.get(col) if col else np.nan
                    if pd.notna(val):
                        if h in ['Lon', 'Lat']:
                            try:
                                row_dict[h] = round(float(val), 6)
                            except Exception:
                                row_dict[h] = val
                        elif ('App DL 속도' in h or 'App UL 속도' in h):
                            try:
                                f_val = float(val)
                                if 'kbps' in str(col).lower() or f_val > 10000:
                                    row_dict[h] = round(f_val / 1000.0, 2)
                                else:
                                    row_dict[h] = round(f_val, 2)
                            except Exception:
                                row_dict[h] = val
                        elif any(k in h for k in ['RSRP', 'SINR', 'RSRQ', '이동속도', 'Power', 'Jitter']):
                            try:
                                row_dict[h] = round(float(val), 1)
                            except Exception:
                                row_dict[h] = val
                        elif any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'MOS', '손실률', 'Loss']):
                            try:
                                row_dict[h] = round(float(val), 2)
                            except Exception:
                                row_dict[h] = val
                        elif any(k in h for k in ['PCI', 'Cell ID', 'CQI', 'MCS', 'RB Num', 'RI', 'Count', 'Time']):
                            try:
                                f_val = float(val)
                                row_dict[h] = int(f_val) if f_val.is_integer() else round(f_val, 1)
                            except Exception:
                                row_dict[h] = val
                        else:
                            row_dict[h] = val
                    else:
                        row_dict[h] = ""
            rows.append(row_dict)
        return rows

    def _extract_call_rows(self, df_tl: pd.DataFrame, headers: List[str], scenario: str) -> List[Dict[str, Any]]:
        call_rows = []
        if df_tl is None or df_tl.empty:
            return call_rows

        call_groups = []
        if 'Call_No' in df_tl.columns and df_tl['Call_No'].nunique() > 1:
            for c_name, grp in df_tl.groupby('Call_No', sort=False):
                call_groups.append((str(c_name), grp))
        else:
            call_groups.append(('Call 1', df_tl))

        for c_idx, (call_label, grp) in enumerate(call_groups):
            row_dict = {}
            ts_s = pd.to_datetime(grp['TIME_STAMP'], errors='coerce').dropna()
            st_str = ts_s.min().strftime('%H:%M:%S') if not ts_s.empty else "00:00:00"
            et_str = ts_s.max().strftime('%H:%M:%S') if not ts_s.empty else "00:00:00"

            traffic_mask = grp['Call_Phase'].astype(str).str.contains('Traffic', case=False, na=False) if 'Call_Phase' in grp.columns else pd.Series(True, index=grp.index)
            traffic_grp = grp[traffic_mask] if traffic_mask.sum() > 0 else grp

            row_dict['시간 (구간)'] = f"{st_str} ~ {et_str}"
            row_dict['호 번호'] = call_label
            row_dict['호 상태 (성공률)'] = "Success"

            for h in headers:
                if h in ['시간 (구간)', '호 번호', '호 상태 (성공률)']:
                    continue
                elif h in ['Lon', 'Lat']:
                    row_dict[h] = self._get_val_from_df(traffic_grp, h, agg='first')
                elif any(k in h for k in ['Cell ID', 'PCI', 'Codec', '결과']):
                    row_dict[h] = self._get_val_from_df(traffic_grp, h, agg='mode')
                else:
                    val = self._get_val_from_df(traffic_grp, h, agg='mean')
                    row_dict[h] = val if pd.notna(val) else ""
            call_rows.append(row_dict)

        return call_rows

    def _extract_total_summary_row(self, df_tl: pd.DataFrame, call_rows: List[Dict[str, Any]], headers: List[str]) -> Dict[str, Any]:
        row_dict = {}
        if df_tl is None or df_tl.empty:
            for h in headers:
                row_dict[h] = ""
            return row_dict

        ts_s = pd.to_datetime(df_tl['TIME_STAMP'], errors='coerce').dropna()
        st_str = ts_s.min().strftime('%H:%M:%S') if not ts_s.empty else "00:00:00"
        et_str = ts_s.max().strftime('%H:%M:%S') if not ts_s.empty else "00:00:00"

        total_calls = len(call_rows) if call_rows else 1
        success_calls = sum(1 for c in call_rows if 'Success' in str(c.get('호 상태 (성공률)', ''))) if call_rows else total_calls
        succ_rate = round(success_calls / total_calls * 100.0, 1) if total_calls > 0 else 100.0

        traffic_mask = df_tl['Call_Phase'].astype(str).str.contains('Traffic', case=False, na=False) if 'Call_Phase' in df_tl.columns else pd.Series(True, index=df_tl.index)
        traffic_df = df_tl[traffic_mask] if traffic_mask.sum() > 0 else df_tl

        row_dict['시간 (구간)'] = f"전체 ({st_str} ~ {et_str})"
        row_dict['호 번호'] = f"All Calls ({total_calls}개)"
        row_dict['호 상태 (성공률)'] = f"{success_calls} / {total_calls} Call ({succ_rate}%)"

        for h in headers:
            if h in ['시간 (구간)', '호 번호', '호 상태 (성공률)']:
                continue
            elif h in ['Lon', 'Lat']:
                row_dict[h] = self._get_val_from_df(traffic_df, h, agg='first')
            elif any(k in h for k in ['Cell ID', 'PCI', 'Codec', '결과']):
                row_dict[h] = self._get_val_from_df(traffic_df, h, agg='mode')
            else:
                val = self._get_val_from_df(traffic_df, h, agg='mean')
                row_dict[h] = val if pd.notna(val) else ""

        return row_dict

    def write_3tier_vertical_sheet(self, ws, sheet_title: str, df_tl: pd.DataFrame, scenario: str, headers: List[str]):
        """
        Writes a single consolidated worksheet per port & scenario with 3 vertical tiers:
        - [1. 전체 종합 요약]
        - [2. Call 단위 결과]
        - [3. 초(sec) 단위 결과]
        """
        sec_rows = self._extract_1sec_rows(df_tl, headers)
        call_rows = self._extract_call_rows(df_tl, headers, scenario)
        tot_row = self._extract_total_summary_row(df_tl, call_rows, headers)

        # Style definitions
        font_family = "Malgun Gothic"
        title_font = Font(name=font_family, size=11, bold=True, color="FFFFFF")
        hdr_font = Font(name=font_family, size=9, bold=True, color="FFFFFF")
        data_font = Font(name=font_family, size=9, color="000000")
        tot_data_font = Font(name=font_family, size=9, bold=True, color="0F172A")

        fill_tot_title = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        fill_tot_hdr = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        fill_tot_row = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")

        fill_call_title = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_call_hdr = PatternFill(start_color="475569", end_color="475569", fill_type="solid")
        fill_call_row1 = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_call_row2 = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        fill_sec_title = PatternFill(start_color="134E4A", end_color="134E4A", fill_type="solid")
        fill_sec_hdr = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
        fill_sec_row1 = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_sec_row2 = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        thin_side = Side(border_style="thin", color="CBD5E1")
        border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")

        cur_row = 1

        # =====================================================================
        # [블록 1: 전체 종합 요약]
        # =====================================================================
        ws.cell(row=cur_row, column=1, value=f"■ [1. {sheet_title} 전체 종합 요약]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_tot_title
        ws.cell(row=cur_row, column=1).alignment = align_left
        for c_idx in range(2, len(headers) + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.fill = fill_tot_title
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_tot_hdr
            cell.alignment = align_center
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        for c_idx, h in enumerate(headers, start=1):
            val = tot_row.get(h, "")
            cell = ws.cell(row=cur_row, column=c_idx, value=val)
            cell.font = tot_data_font
            cell.fill = fill_tot_row
            cell.border = border_all
            if isinstance(val, (int, float)):
                cell.alignment = align_right
                cell.number_format = '0.00' if any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'Lon', 'Lat', 'MOS']) else '0.0'
            else:
                cell.alignment = align_center
        ws.row_dimensions[cur_row].height = 20
        cur_row += 1

        ws.row_dimensions[cur_row].height = 14
        cur_row += 1

        # =====================================================================
        # [블록 2: Call 단위 결과]
        # =====================================================================
        ws.cell(row=cur_row, column=1, value=f"■ [2. {sheet_title} Call 단위 결과]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_call_title
        ws.cell(row=cur_row, column=1).alignment = align_left
        for c_idx in range(2, len(headers) + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.fill = fill_call_title
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_call_hdr
            cell.alignment = align_center
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        for r_idx, c_row in enumerate(call_rows):
            row_fill = fill_call_row1 if (r_idx % 2 == 0) else fill_call_row2
            for c_idx, h in enumerate(headers, start=1):
                val = c_row.get(h, "")
                cell = ws.cell(row=cur_row, column=c_idx, value=val)
                cell.font = data_font
                cell.fill = row_fill
                cell.border = border_all
                if isinstance(val, (int, float)):
                    cell.alignment = align_right
                    cell.number_format = '0.00' if any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'Lon', 'Lat', 'MOS']) else '0.0'
                else:
                    cell.alignment = align_center
            ws.row_dimensions[cur_row].height = 19
            cur_row += 1

        ws.row_dimensions[cur_row].height = 14
        cur_row += 1

        # =====================================================================
        # [블록 3: 초(sec) 단위 결과]
        # =====================================================================
        ws.cell(row=cur_row, column=1, value=f"■ [3. {sheet_title} 초(sec) 단위 결과]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_sec_title
        ws.cell(row=cur_row, column=1).alignment = align_left
        for c_idx in range(2, len(headers) + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.fill = fill_sec_title
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_sec_hdr
            cell.alignment = align_center
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        for r_idx, s_row in enumerate(sec_rows):
            row_fill = fill_sec_row1 if (r_idx % 2 == 0) else fill_sec_row2
            for c_idx, h in enumerate(headers, start=1):
                val = s_row.get(h, "")
                cell = ws.cell(row=cur_row, column=c_idx, value=val)
                cell.font = data_font
                cell.fill = row_fill
                cell.border = border_all
                if isinstance(val, (int, float)):
                    cell.alignment = align_right
                    cell.number_format = '0.00' if any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'Lon', 'Lat', 'MOS']) else '0.0'
                else:
                    cell.alignment = align_center
            ws.row_dimensions[cur_row].height = 18
            cur_row += 1

        # Column width optimization
        for c_idx, h in enumerate(headers, start=1):
            col_letter = get_column_letter(c_idx)
            h_len = max(len(str(h)) * 1.5, 12)
            ws.column_dimensions[col_letter].width = min(max(h_len, 12), 26)

    def _detect_sub_traffic_models(self, df_tl: pd.DataFrame, scenario: str) -> Dict[str, pd.DataFrame]:
        """
        Splits a Port's df_timeline into multiple dedicated traffic model sub-dataframes if multiple scenarios exist.
        e.g. M1 with DL + Ping -> {'DL': df_dl, 'Ping': df_ping}
        e.g. M3 with Voice -> {'VoLTE': df_voice}
        """
        if df_tl is None or df_tl.empty:
            sc_code = 'VoLTE' if any(k in str(scenario).upper() for k in ['VOICE', 'VOLTE', 'VONR']) else ('UL' if 'UL' in str(scenario).upper() else ('Ping' if 'PING' in str(scenario).upper() else 'DL'))
            return {sc_code: pd.DataFrame()}

        sub_dfs = {}

        if 'Call_Phase' in df_tl.columns:
            phases = df_tl['Call_Phase'].dropna().astype(str).unique()
            has_dl_phase = any('DL' in p.upper() for p in phases)
            has_ul_phase = any('UL' in p.upper() for p in phases)
            has_voice_phase = any('VOICE' in p.upper() or 'VOLTE' in p.upper() or 'VONR' in p.upper() for p in phases)
            has_ping_phase = any('PING' in p.upper() for p in phases)

            active_scens = []
            if has_dl_phase: active_scens.append('DL')
            if has_ul_phase: active_scens.append('UL')
            if has_voice_phase: active_scens.append('VoLTE')
            if has_ping_phase: active_scens.append('Ping')

            if len(active_scens) > 1:
                for sc in active_scens:
                    match_key = 'VOICE' if sc == 'VoLTE' else sc
                    mask = df_tl['Call_Phase'].astype(str).str.contains(match_key, case=False, na=False)
                    sub_df = df_tl[mask].copy()
                    if not sub_df.empty:
                        sub_dfs[sc] = sub_df

        if not sub_dfs:
            sc_clean = 'VoLTE' if any(k in str(scenario).upper() for k in ['VOICE', 'VOLTE', 'VONR']) else ('UL' if 'UL' in str(scenario).upper() else ('Ping' if 'PING' in str(scenario).upper() else 'DL'))
            sub_dfs[sc_clean] = df_tl

        return sub_dfs

    def _get_headers_for_scenario(self, sc_code: str) -> Tuple[List[str], str]:
        sc_up = str(sc_code).upper()
        if any(k in sc_up for k in ['VOICE', 'VOLTE', 'VONR']):
            return self.STANDARD_VOICE_HEADERS, 'Voice'
        elif 'UL' in sc_up and 'PUL' not in sc_up:
            return self.STANDARD_UL_HEADERS, 'UL'
        elif 'PING' in sc_up:
            return self.STANDARD_PING_HEADERS, 'Ping'
        else:
            return self.STANDARD_DL_HEADERS, 'DL'

    def write_executive_summary_sheet(
        self,
        ws,
        port_results: Dict[str, Dict[str, Any]],
        display_name: str
    ):
        """
        Writes Sheet 1 '01_통합_요약' executive comparison table across all ports and scenarios.
        """
        font_family = "Malgun Gothic"
        title_font = Font(name=font_family, size=12, bold=True, color="FFFFFF")
        hdr_font = Font(name=font_family, size=9, bold=True, color="FFFFFF")
        data_font = Font(name=font_family, size=9, color="000000")
        thin_side = Side(border_style="thin", color="CBD5E1")
        border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        fill_main_title = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        fill_hdr = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        fill_row1 = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        fill_row2 = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        cur_row = 1

        # Title
        ws.cell(row=cur_row, column=1, value=f"■ [종합 분석 요약장: {display_name}]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_main_title
        for c in range(2, 13):
            ws.cell(row=cur_row, column=c).fill = fill_main_title
        ws.row_dimensions[cur_row].height = 26
        cur_row += 1

        # Headers
        sum_headers = [
            '단말/시트명', '호 시나리오', '망 모드', '제조사', '측정 시간',
            '총 호수', '성공률 (%)', '대표 품질/속도 (평균)', '대표 품질/속도 (최대)',
            '평균 RSRP (dBm)', '평균 SINR (dB)', '품질 특이사항'
        ]
        for c_idx, h in enumerate(sum_headers, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_hdr
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        # Rows per Port & Traffic Model
        r_idx = 0
        for port_key, pdata in port_results.items():
            df_tl = pdata.get('df_timeline', pd.DataFrame())
            scenario = pdata.get('scenario', 'DL')
            net_mode = df_tl.attrs.get('Network_Mode', 'LTE') if hasattr(df_tl, 'attrs') else 'LTE'
            vendor = df_tl.attrs.get('Active_Vendor', 'COMMON') if hasattr(df_tl, 'attrs') else 'COMMON'
            episodes = pdata.get('episodes', [])

            sub_models = self._detect_sub_traffic_models(df_tl, scenario)
            for sc_code, df_sub in sub_models.items():
                r_fill = fill_row1 if (r_idx % 2 == 0) else fill_row2
                r_idx += 1

                sheet_name = f"{port_key}_{sc_code}"
                ts_s = pd.to_datetime(df_sub['TIME_STAMP'], errors='coerce').dropna() if not df_sub.empty and 'TIME_STAMP' in df_sub.columns else pd.Series([], dtype='datetime64[ns]')
                st_str = ts_s.min().strftime('%H:%M:%S') if not ts_s.empty else "00:00:00"
                et_str = ts_s.max().strftime('%H:%M:%S') if not ts_s.empty else "00:00:00"
                time_range = f"{st_str} ~ {et_str}"

                call_cnt = df_sub['Call_No'].nunique() if ('Call_No' in df_sub.columns and not df_sub.empty) else 1

                # Specific KPIs based on scenario
                avg_metric_str = "-"
                max_metric_str = "-"

                if sc_code == 'DL':
                    sc_label = "DL Traffic (하향)"
                    s_mac = self._get_series(df_sub, ['NR_MAC_DL_Tput', 'LTE_MAC_DL_Tput', 'MAC_DL_Tput'])
                    s_app = self._get_series(df_sub, ['App_DL_Tput'])
                    if not s_app.empty and s_app.max() > 10000:
                        s_app = s_app / 1000.0
                    target_s = s_app if (not s_app.empty and s_app.mean() > 0) else s_mac
                    if not target_s.empty:
                        avg_metric_str = f"App DL {target_s.mean():.2f} Mbps"
                        max_metric_str = f"최대 {target_s.max():.2f} Mbps"

                elif sc_code == 'UL':
                    sc_label = "UL Traffic (상향)"
                    s_pusch = self._get_series(df_sub, ['NR_PUSCH_Tput', 'LTE_PUSCH_Tput', 'PUSCH_Tput'])
                    s_app = self._get_series(df_sub, ['App_UL_Tput'])
                    if not s_app.empty and s_app.max() > 10000:
                        s_app = s_app / 1000.0
                    target_s = s_app if (not s_app.empty and s_app.mean() > 0) else s_pusch
                    if not target_s.empty:
                        avg_metric_str = f"App UL {target_s.mean():.2f} Mbps"
                        max_metric_str = f"최대 {target_s.max():.2f} Mbps"

                elif sc_code in ['VoLTE', 'VoNR', 'Voice']:
                    sc_label = "VoLTE / VoNR (음성)"
                    s_mos = self._get_series(df_sub, ['MOS', 'Audio MOS', 'POLQA'])
                    s_mos_valid = s_mos[s_mos > 0]
                    if not s_mos_valid.empty:
                        avg_metric_str = f"Audio MOS {s_mos_valid.mean():.2f}"
                        max_metric_str = f"최저 {s_mos_valid.min():.2f}"
                    else:
                        avg_metric_str = "MOS (데이터 없음)"
                        max_metric_str = "-"

                elif sc_code == 'Ping':
                    sc_label = "Ping (인지품질)"
                    s_ping = self._get_series(df_sub, [
                        '[Call & SKT Speed Test Call Info Ping Event Info Ping Response]',
                        'SST_Ping_Result',
                        '[Call & SKT Speed Test Call Info Ping Event Info Ping Throughput Result]',
                        'Ping RTT (ms)'
                    ])
                    if not s_ping.empty:
                        avg_metric_str = f"평균 RTT {s_ping.mean():.1f} ms"
                        max_metric_str = f"최대 {s_ping.max():.1f} ms"
                else:
                    sc_label = sc_code

                # RF Serving values
                s_rsrp = self._get_series(df_sub, ['SS_RSRP', 'NR_SS_RSRP', 'LTE_RSRP', 'Serving_RSRP'])
                s_sinr = self._get_series(df_sub, ['SS_SINR', 'NR_SS_SINR', 'LTE_SINR', 'Serving_SINR'])
                rsrp_str = f"{s_rsrp.mean():.1f}" if not s_rsrp.empty else "-"
                sinr_str = f"{s_sinr.mean():.1f}" if not s_sinr.empty else "-"

                # Incident summary
                ep_titles = [ep.get('title', '') for ep in episodes[:2]]
                incident_str = " / ".join(ep_titles) if ep_titles else "특이사항 없음 (정상)"

                row_vals = [
                    sheet_name, sc_label, net_mode, vendor, time_range,
                    call_cnt, "100.0%", avg_metric_str, max_metric_str,
                    rsrp_str, sinr_str, incident_str
                ]

                for c_idx, val in enumerate(row_vals, start=1):
                    cell = ws.cell(row=cur_row, column=c_idx, value=val)
                    cell.font = data_font
                    cell.fill = r_fill
                    cell.border = border_all
                    if c_idx in [6, 7]:
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    elif c_idx in [1, 2, 3, 4, 5]:
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    elif c_idx in [10, 11]:
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    else:
                        cell.alignment = Alignment(horizontal="left", vertical="center")
                ws.row_dimensions[cur_row].height = 20
                cur_row += 1

        # Column widths for executive summary
        for c_idx, h in enumerate(sum_headers, start=1):
            col_letter = get_column_letter(c_idx)
            ws.column_dimensions[col_letter].width = max(len(str(h)) * 1.6, 16)

    def build_multi_ue_total_summary(
        self,
        port_results: Dict[str, Dict[str, Any]],
        display_name: str
    ) -> pd.DataFrame:
        """
        Builds summary DataFrame across active ports.
        """
        rows = []
        for port_key, pdata in port_results.items():
            df_tl = pdata.get('df_timeline', pd.DataFrame())
            scenario = pdata.get('scenario', 'DL')
            net_mode = df_tl.attrs.get('Network_Mode', 'LTE') if hasattr(df_tl, 'attrs') else 'LTE'
            vendor = df_tl.attrs.get('Active_Vendor', 'COMMON') if hasattr(df_tl, 'attrs') else 'COMMON'

            sub_models = self._detect_sub_traffic_models(df_tl, scenario)
            for sc_code, df_sub in sub_models.items():
                call_cnt = df_sub['Call_No'].nunique() if ('Call_No' in df_sub.columns and not df_sub.empty) else 1
                rows.append({
                    '단말/시트명': f"{port_key}_{sc_code}",
                    '시나리오': sc_code,
                    '망 모드': net_mode,
                    '제조사': vendor,
                    '총 호수': call_cnt
                })
        return pd.DataFrame(rows)

    def build_master_consolidated_excel(
        self,
        port_results: Dict[str, Dict[str, Any]],
        display_name: str,
        output_xlsx_path: str
    ) -> str:
        """
        Builds the consolidated Multi-Port Master Excel file.
        Layout:
        - Sheet 1: '01_통합_요약' (Executive Dashboard)
        - Dedicated Sheets per Port & Scenario: M1_DL, M1_Ping, M2_UL, M3_VoLTE, etc.
          Each sheet vertically integrates:
            [1. 전체 종합 요약]
            (1 blank row)
            [2. Call 단위 결과]
            (1 blank row)
            [3. 초(sec) 단위 결과]
        - Preserved engineering inspection sheets:
            L3_단일파라미터_감사, L3_복합구조체_감사, Mobility_Meas
        """
        os.makedirs(os.path.dirname(output_xlsx_path), exist_ok=True)
        wb = openpyxl.Workbook()
        default_sheet = wb.active

        # 0. Create Executive Summary Sheet: '01_통합_요약'
        ws_sum = wb.create_sheet(title="01_통합_요약")
        self.write_executive_summary_sheet(ws_sum, port_results, display_name)

        # 1. Create dedicated 3-tier vertical sheet for each Port & Traffic Model
        for port_key, pdata in port_results.items():
            df_tl = pdata.get('df_timeline', pd.DataFrame())
            scenario = pdata.get('scenario', 'DL')

            sub_models = self._detect_sub_traffic_models(df_tl, scenario)
            for sc_code, df_sub in sub_models.items():
                sheet_title = f"{port_key}_{sc_code}"
                ws = wb.create_sheet(title=sheet_title)
                headers, _ = self._get_headers_for_scenario(sc_code)
                self.write_3tier_vertical_sheet(ws, sheet_title, df_sub, sc_code, headers)

        # 2. Remove default blank sheet
        if default_sheet in wb.worksheets and len(wb.worksheets) > 1:
            wb.remove(default_sheet)

        # 3. Dedicated L3 Parameter Audit Sheets (if available)
        first_pdata = list(port_results.values())[0] if port_results else {}
        df_l3_scalar = first_pdata.get('df_l3_scalar', pd.DataFrame())
        df_l3_struct = first_pdata.get('df_l3_struct', pd.DataFrame())

        if df_l3_scalar.empty or df_l3_struct.empty:
            for pdata in port_results.values():
                if df_l3_scalar.empty and not pdata.get('df_l3_scalar', pd.DataFrame()).empty:
                    df_l3_scalar = pdata.get('df_l3_scalar')
                if df_l3_struct.empty and not pdata.get('df_l3_struct', pd.DataFrame()).empty:
                    df_l3_struct = pdata.get('df_l3_struct')

        hdr_font_l3 = Font(name="Malgun Gothic", size=9, bold=True, color="FFFFFF")
        fill_hdr_l3 = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        thin_side = Side(border_style="thin", color="CBD5E1")
        border_all = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        if df_l3_scalar is not None and not df_l3_scalar.empty:
            ws_l3_sc = wb.create_sheet(title="L3_단일파라미터_감사")
            for r_idx, row in enumerate(dataframe_to_rows(df_l3_scalar, index=False, header=True), start=1):
                for c_idx, val in enumerate(row, start=1):
                    cell = ws_l3_sc.cell(row=r_idx, column=c_idx, value=val)
                    cell.border = border_all
                    if r_idx == 1:
                        cell.font = hdr_font_l3
                        cell.fill = fill_hdr_l3
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        cell.font = Font(name="Malgun Gothic", size=9)

        if df_l3_struct is not None and not df_l3_struct.empty:
            ws_l3_st = wb.create_sheet(title="L3_복합구조체_감사")
            for r_idx, row in enumerate(dataframe_to_rows(df_l3_struct, index=False, header=True), start=1):
                for c_idx, val in enumerate(row, start=1):
                    cell = ws_l3_st.cell(row=r_idx, column=c_idx, value=val)
                    cell.border = border_all
                    if r_idx == 1:
                        cell.font = hdr_font_l3
                        cell.fill = fill_hdr_l3
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        cell.font = Font(name="Malgun Gothic", size=9)

        # 4. Dedicated Mobility Measurement Sheet (if available)
        df_mob_sheet = first_pdata.get('df_mob', pd.DataFrame())
        if df_mob_sheet.empty:
            for pdata in port_results.values():
                if not pdata.get('df_mob', pd.DataFrame()).empty:
                    df_mob_sheet = pdata.get('df_mob')
                    break

        if df_mob_sheet is not None and not df_mob_sheet.empty:
            ws_mob = wb.create_sheet(title="Mobility_Meas")
            for r_idx, row in enumerate(dataframe_to_rows(df_mob_sheet, index=False, header=True), start=1):
                for c_idx, val in enumerate(row, start=1):
                    cell = ws_mob.cell(row=r_idx, column=c_idx, value=val)
                    cell.border = border_all
                    if r_idx == 1:
                        cell.font = hdr_font_l3
                        cell.fill = fill_hdr_l3
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        cell.font = Font(name="Malgun Gothic", size=9)

        wb.save(output_xlsx_path)
        wb.close()
        return output_xlsx_path
