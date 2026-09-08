# -*- coding: utf-8 -*-
r"""
File: 4_Optis_AI_Analyzer/core/parsers/master_timeline_parser.py
Description: Multi-Source Integrated Master Timeline Parser with AutoCallSummary Traffic vs IDLE Phase Alignment
"""

import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime


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


class MasterTimelineParser:
    """
    Parses and builds a universal 1-second unified master timeline.
    - Accurately parses Event_(Detail).csv [AutoCallSummary] to segment Traffic (23s/65s) vs Idle_Gap (25s).
    - Integrates QC_KPI, RTP (MOS/Jitter/Loss), Smart_Phone, and L3_MSG.
    """

    def __init__(self):
        pass

    @staticmethod
    def _find_col(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
        if df is None or df.empty:
            return None
        # 1. Exact match first (Verbatim)
        for kw in keywords:
            if kw in df.columns:
                return kw
        # 2. Case-insensitive exact match
        for kw in keywords:
            kw_clean = kw.strip().lower()
            for col in df.columns:
                if str(col).strip().lower() == kw_clean:
                    return col
        # 3. Exact match without brackets
        for kw in keywords:
            kw_nobracket = kw.strip('[]').strip().lower()
            for col in df.columns:
                if str(col).strip('[]').strip().lower() == kw_nobracket:
                    return col
        # 4. Robust substring match for [Call & ...] columns
        for kw in keywords:
            kw_clean = kw.strip('[]').strip().lower()
            if len(kw_clean) >= 6:
                for col in df.columns:
                    col_clean = str(col).strip('[]').strip().lower()
                    if kw_clean in col_clean:
                        return col
        return None

    def build_master_timeline(
        self,
        csvs: Dict[str, Optional[str]],
        all_l3: Optional[Dict[str, Any]] = None,
        detected_state: Optional[Dict[str, Any]] = None,
        port_key: str = 'M1'
    ) -> pd.DataFrame:
        """
        Builds a unified 1-second master timeline table from all extracted CSVs.
        Manages 4 core automated attributes as the Single Source of Truth (SSOT):
        1. Network_Mode (LTE / NSA / SA)
        2. Active_Vendor (SAMSUNG / ERICSSON / NOKIA / COMMON)
        3. Traffic_Model (VOICE / DL / UL / PING) & Call_Phase (VOICE_Traffic, DL_Traffic, etc.)
        4. Port_Key (M1~M4, M1-R1~M1-R2, etc.)
        """
        time_series_frames = []

        state = detected_state or {}
        net_mode = state.get('Network_Mode', 'LTE')
        vendor = state.get('Active_Vendor', 'COMMON')

        if vendor == 'COMMON':
            try:
                from core.network_state_tracker import NetworkStateTracker
                tracker = NetworkStateTracker()
                if all_l3:
                    vendor = tracker.identify_vendor_from_l3(all_l3)
                if vendor == 'COMMON' and csvs.get('L3_MSG') and os.path.exists(csvs['L3_MSG']):
                    with open(csvs['L3_MSG'], 'r', encoding='utf-8', errors='ignore') as f_l3:
                        sample_lines = [f_l3.readline() for _ in range(5000)]
                    vendor = tracker.identify_vendor_from_l3({'_raw_lines': sample_lines})
            except Exception:
                pass

        # 1. Base KPI Table
        kpi_csv = csvs.get('KPI')
        df_kpi = safe_read_csv(kpi_csv)
        if df_kpi is not None and not df_kpi.empty and 'TIME_STAMP' in df_kpi.columns:
            sub_kpi = pd.DataFrame()
            sub_kpi['TIME_STAMP'] = df_kpi['TIME_STAMP']
            for target, kws in [
                ('Lat', ['Lat', '[Call & GPS Lat]']),
                ('Lon', ['Lon', '[Call & GPS Lon]']),
                ('Speed', ['[Call & GPS Speed (km/h)]', 'Speed']),
                ('PDCP_DL_Tput', ['[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]', '[Call & LTE KPI PDCP DL Throughput [Mbps]]', 'PDCP DL Throughput']),
                ('PDCP_UL_Tput', ['[Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]]', '[Call & LTE KPI PDCP UL Throughput [Mbps]]', 'PDCP UL Throughput']),
                ('App_DL_Tput', ['[Call & SKT Speed Test Call Info Download Event Info DL Throughput]', 'FTP FWD Throughput', 'Current App Throughput']),
                ('App_UL_Tput', ['[Call & SKT Speed Test Call Info Upload Event Info UL Throughput]', 'FTP RVS Throughput', 'Current App Throughput']),
                ('NR_PDSCH_Tput', ['[Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PDSCH Throughput [Mbps]]', 'PCell PDSCH Throughput']),
                ('NR_PUSCH_Tput', ['[Call & 5G KPI Total Info Layer1 PUSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PUSCH Throughput [Mbps]]', 'PCell PUSCH Throughput']),
                ('NR_MAC_DL_Tput', ['[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]', 'NR-DL MAC PCell DL MAC Throughput']),
                ('NR_MAC_UL_Tput', ['[Call & 5G KPI Total Info Layer2 MAC UL Throughput [Mbps]]', 'Layer2 MAC UL Throughput']),
                ('LTE_PDSCH_Tput', ['[Call & LTE KPI PDSCH Throughput [Mbps]]', 'PDSCH Throughput [Mbps]']),
                ('LTE_PUSCH_Tput', ['[Call & LTE KPI PUSCH Throughput [Mbps]]', 'PUSCH Throughput [Mbps]']),
                ('LTE_MAC_DL_Tput', ['[Call & LTE KPI MAC DL Throughput [Mbps]]', 'L1/L2 Throughput [Mbps] MAC DL Throughput']),
                ('LTE_MAC_UL_Tput', ['[Call & LTE KPI MAC UL Throughput [Mbps]]']),
                ('PDSCH_Tput', ['[Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]]', '[Call & LTE KPI PDSCH Throughput [Mbps]]', 'PCell PDSCH Throughput', 'PDSCH Throughput [Mbps]']),
                ('PUSCH_Tput', ['[Call & 5G KPI Total Info Layer1 PUSCH Throughput [Mbps]]', '[Call & LTE KPI PUSCH Throughput [Mbps]]', 'PCell PUSCH Throughput', 'PUSCH Throughput [Mbps]']),
                ('NR_Serving_PCI', ['[Call & 5G KPI PCell RF Serving PCI]', 'PCell RF Serving PCI']),
                ('NR_SS_RSRP', ['[Call & 5G KPI PCell RF Serving SS-RSRP [dBm]]', 'PCell RF Serving SS-RSRP', 'Serving SS-RSRP']),
                ('NR_SS_SINR', ['[Call & 5G KPI PCell RF Serving SS-SINR [dB]]', 'PCell RF Serving SS-SINR', 'Serving SS-SINR']),
                ('NR_SS_RSRQ', ['[Call & 5G KPI PCell RF Serving SS-RSRQ [dB]]', 'PCell RF Serving SS-RSRQ', 'Serving SS-RSRQ']),
                ('NR_CQI', ['[Call & 5G KPI PCell RF CQI]', 'PCell CQI (WideBand)']),
                ('NR_DL_MCS', ['[Call & 5G KPI PCell Layer1 DL MCS (Avg)]', 'DL MCS Idx0[Avg]']),
                ('NR_UL_MCS', ['[Call & 5G KPI PCell Layer1 UL MCS (Avg)]', 'Layer1 UL MCS (Avg)']),
                ('NR_PDSCH_BLER', ['[Call & 5G KPI PCell Layer1 DL BLER [%]]', 'PDSCH BLER']),
                ('NR_PUSCH_BLER', ['[Call & 5G KPI PCell Layer1 UL BLER [%]]', 'PUSCH BLER']),
                ('NR_PRB_Inc0', ['[Call & 5G KPI PCell Layer1 DL RB Num (Including 0)]', 'PCell PDSCH PRB Number(Including 0)']),
                ('NR_UL_PRB_Inc0', ['[Call & 5G KPI PCell Layer1 UL RB Num (Including 0)]', 'PCell PUSCH PRB Number(Including 0)']),
                ('NR_WB_RI', ['[Call & 5G KPI PCell RF RI(Avg)]', 'PCell WB RI']),
                ('NR_PUSCH_Power', ['[Call & 5G KPI PCell RF PUSCH Power [dBm]]']),
                ('NR_QAM64_Rate', ['[Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]]', '64QAM Rate [%]']),
                ('NR_QAM256_Rate', ['[Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]]', '256 QAM Rate [%]']),
                ('LTE_Serving_PCI', ['[Call & LTE KPI PCell Serving PCI]', 'PCell Serving PCI', 'Serving PCI']),
                ('LTE_RSRP', ['[Call & LTE KPI PCell Serving RSRP [dBm]]', 'PCell Serving RSRP', 'Serving RSRP']),
                ('LTE_SINR', ['[Call & LTE KPI PCell SINR [dB]]', 'PCell SINR', 'Serving SINR']),
                ('LTE_RSRQ', ['[Call & LTE KPI PCell Serving RSRQ [dB]]', 'PCell Serving RSRQ', 'Serving RSRQ']),
                ('LTE_CQI', ['[Call & LTE KPI PCell WB CQI CW0]', 'Serving CQI']),
                ('LTE_DL_MCS', ['[Call & LTE KPI PCell DL MCS0]', 'DL MCS']),
                ('LTE_UL_MCS', ['[Call & LTE KPI PCell UL MCS]', 'UL MCS']),
                ('LTE_PDSCH_BLER', ['[Call & LTE KPI PCell PDSCH BLER [%]]', 'BLER']),
                ('LTE_PUSCH_BLER', ['[Call & LTE KPI PCell PUSCH BLER [%]]', 'PUSCH BLER']),
                ('LTE_PRB_Inc0', ['[Call & LTE KPI PCell PDSCH PRB Number(Including 0)]', 'PCell PDSCH PRB Number(Including 0)']),
                ('LTE_UL_PRB_Inc0', ['[Call & LTE KPI PCell PUSCH PRB Number(Including 0)]', 'PCell PUSCH PRB Number(Including 0)']),
                ('LTE_WB_RI', ['[Call & LTE KPI PCell WB RI]', 'RF RI(Avg)', 'WB RI']),
                ('LTE_PUSCH_Power', ['[Call & LTE KPI PCell PUSCH Power [dBm]]']),
                ('LTE_QAM64_Rate', ['[Call & LTE KPI SCell[1] DL Modulation0]', 'DL 64QAM Rate', '64QAM Rate [%]']),
                ('LTE_QAM256_Rate', ['[Call & LTE KPI SCell[2] DL Modulation0]', 'DL 256 QAM Rate', '256 QAM Rate [%]']),
                ('SS_RSRP', ['[Call & 5G KPI PCell RF Serving SS-RSRP [dBm]]', '[Call & LTE KPI PCell Serving RSRP [dBm]]', 'PCell RF Serving SS-RSRP', 'Serving SS-RSRP', 'Serving RSRP']),
                ('SS_SINR', ['[Call & 5G KPI PCell RF Serving SS-SINR [dB]]', '[Call & LTE KPI PCell SINR [dB]]', 'PCell RF Serving SS-SINR', 'Serving SS-SINR', 'Serving SINR']),
                ('SS_RSRQ', ['[Call & 5G KPI PCell RF Serving SS-RSRQ [dB]]', '[Call & LTE KPI PCell Serving RSRQ [dB]]', 'PCell RF Serving SS-RSRQ', 'Serving SS-RSRQ', 'Serving RSRQ']),
                ('CQI', ['[Call & 5G KPI PCell RF CQI]', '[Call & LTE KPI PCell WB CQI CW0]', 'PCell CQI (WideBand)', 'Serving CQI']),
                ('DL_MCS', ['[Call & 5G KPI PCell Layer1 DL MCS (Avg)]', '[Call & LTE KPI PCell DL MCS0]', 'DL MCS Idx0[Avg]', 'DL MCS']),
                ('UL_MCS', ['[Call & 5G KPI PCell Layer1 UL MCS (Avg)]', '[Call & LTE KPI PCell UL MCS]', 'Layer1 UL MCS (Avg)', 'UL MCS']),
                ('PDSCH_BLER', ['[Call & 5G KPI PCell Layer1 DL BLER [%]]', '[Call & LTE KPI PCell PDSCH BLER [%]]', 'PDSCH BLER', 'BLER']),
                ('PUSCH_BLER', ['[Call & 5G KPI PCell Layer1 UL BLER [%]]', '[Call & LTE KPI PCell PUSCH BLER [%]]', 'PUSCH BLER']),
                ('PRB_Num_Inc0', ['[Call & 5G KPI PCell Layer1 DL RB Num (Including 0)]', '[Call & LTE KPI PCell PDSCH PRB Number(Including 0)]', 'PCell PDSCH PRB Number(Including 0)']),
                ('WB_RI', ['[Call & 5G KPI PCell RF RI(Avg)]', '[Call & LTE KPI PCell WB RI]', 'PCell WB RI', 'RF RI(Avg)']),
                ('QAM64_Rate', ['[Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]]', '64QAM Rate [%]']),
                ('QAM256_Rate', ['[Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]]', '256 QAM Rate [%]']),
                ('SST_DL_Tput', ['[Call & SKT Speed Test Call Info Download Event Info DL Throughput]']),
                ('SST_UL_Tput', ['[Call & SKT Speed Test Call Info Upload Event Info UL Throughput]']),
                ('SST_Ping_Result', ['[Call & SKT Speed Test Call Info Ping Event Info Ping Throughput Result]']),
                ('SST_Event', ['[Call & SKT Speed Test Call Info SST Call Event]']),
                ('MOS', ['MOS P863', 'MOS Result', 'P863(POLQA)', 'POLQA', 'MOS'])
            ]:
                found = self._find_col(df_kpi, kws)
                if found:
                    sub_kpi[target] = df_kpi[found]

            sub_kpi['Source_Type'] = 'QC_KPI'
            time_series_frames.append(sub_kpi)

        # 2. Smart Phone Telemetry
        sp_csv = csvs.get('SMART_PHONE')
        df_sp = safe_read_csv(sp_csv)
        if df_sp is not None and not df_sp.empty and 'TIME_STAMP' in df_sp.columns:
            sp_cols = {'TIME_STAMP': 'TIME_STAMP'}
            for target, kws in [
                ('Battery_Temp', ['Battery Temperature', 'Battery_Temp', 'Temp']),
                ('CPU_Usage', ['CPU Usage', 'CPU_Usage', 'CPU']),
                ('Memory_Usage', ['Memory Usage', 'Memory']),
                ('eNB_ID', ['eNB ID', 'eNBId']),
                ('Cell_ID', ['Cell ID', 'CellId']),
                ('TAC', ['TAC', 'Tracking Area Code']),
                ('EARFCN', ['EARFCN', 'ARFCN']),
                ('LTE_Serving_PCI', ['PCI'])
            ]:
                found = self._find_col(df_sp, kws)
                if found:
                    sp_cols[found] = target

            sub_sp = df_sp[list(sp_cols.keys())].rename(columns=sp_cols).copy()
            sub_sp['Source_Type'] = 'Smart_Phone'
            time_series_frames.append(sub_sp)

        # 3. RTP (Dual-Schema: Schema 1 RxJitter/RxLoss & Schema 2 Audio Rx Jitter)
        rtp_csv = csvs.get('RTP')
        df_rtp = safe_read_csv(rtp_csv)
        if df_rtp is not None and not df_rtp.empty and 'TIME_STAMP' in df_rtp.columns:
            rtp_cols = {'TIME_STAMP': 'TIME_STAMP'}
            for target, kws in [
                ('MOS', ['MOS P863', 'MOS Result', 'MOS', 'POLQA']),
                ('Jitter', ['RxJitter', 'Audio Rx Jitter', 'Rx Jitter', 'Jitter']),
                ('Packet_Loss', ['RxPacketLossRate', 'Audio Rx Packet Loss', 'Packet Loss', 'Loss (%)']),
                ('DL_Packets', ['RxRTPCount', 'Audio Rx Packet Count', 'Rx Packet Count']),
                ('UL_Packets', ['TxRTPCount', 'Audio Tx Packet Count', 'Tx Packet Count']),
                ('Codec', ['Vocoder Mode(DL)', 'Vocoder Mode', 'Codec'])
            ]:
                found = self._find_col(df_rtp, kws)
                if found:
                    rtp_cols[found] = target

            sub_rtp = df_rtp[list(rtp_cols.keys())].rename(columns=rtp_cols).copy()
            sub_rtp['Source_Type'] = 'RTP'
            time_series_frames.append(sub_rtp)

        # 4. Event & Event Detail (AutoCallSummary / Voice Call Service)
        df_event = safe_read_csv(csvs.get('EVENT'))
        df_ed = safe_read_csv(csvs.get('EVENT_DETAIL'))
        df_call_res = safe_read_csv(csvs.get('CALL_RESULT'))

        # =====================================================================
        # [4단계 순차 판별 파이프라인 (Waterfall Decision Pipeline)]
        # 1단계: 망 모드 (Network_Mode: NSA / SA / LTE)
        # 2단계: 활성 벤더 (Active_Vendor: NOKIA / SAMSUNG / ERICSSON / COMMON)
        # 3단계: 트래픽 모델 (Traffic_Model: SST / VOICE / DL / UL - 망별 순수 PDCP 단독 참조)
        # 4단계: 단말 포트 및 세부 시나리오 (Port_Key, VOICE_MO/MT, Long/Short Call)
        # =====================================================================

        # -----------------------------------------------------------------
        # [1단계: 망 모드 판별]
        # -----------------------------------------------------------------
        if net_mode == 'LTE':
            if df_kpi is not None and not df_kpi.empty:
                if self._find_col(df_kpi, ['[Call & 5G KPI PCell RF Serving SS-RSRP [dBm]]', 'PCell RF Serving SS-RSRP', 'Serving SS-RSRP']):
                    s_nr = pd.to_numeric(df_kpi[self._find_col(df_kpi, ['[Call & 5G KPI PCell RF Serving SS-RSRP [dBm]]', 'PCell RF Serving SS-RSRP', 'Serving SS-RSRP'])], errors='coerce').dropna()
                    if not s_nr.empty:
                        net_mode = 'NSA'
            if net_mode == 'LTE' and df_sp is not None and not df_sp.empty:
                sp_net_c = self._find_col(df_sp, ['Network Type', 'Network Mode', 'System Mode'])
                if sp_net_c and df_sp[sp_net_c].dropna().astype(str).str.contains('5G|NR|NSA', case=False).any():
                    net_mode = 'NSA'

        # -----------------------------------------------------------------
        # [2단계: 활성 벤더 판별]
        # -----------------------------------------------------------------
        # (vendor is initialized above and refined via L3 state tracker)

        # -----------------------------------------------------------------
        # [3단계: 트래픽 모델 판별 (망별 순수 PDCP 단독 참조)]
        # -----------------------------------------------------------------
        scen_name_col = self._find_col(df_ed, ['[Call & AutoCallSummary Scenario Name]', 'AutoCallSummary Scenario Name', 'Scenario Name']) if df_ed is not None else None
        call_type_col = self._find_col(df_ed, ['[Call & AutoCallSummary Call type]', 'AutoCallSummary Call type', 'Call type']) if df_ed is not None else None
        cd1_col = self._find_col(df_ed, ['[Call & AutoCallSummary Detail Code1]', 'AutoCallSummary Detail Code1', '[Call & Voice Call Event Detail Code1]', 'Voice Call Event Detail Code1']) if df_ed is not None else None
        cd2_col = self._find_col(df_ed, ['[Call & AutoCallSummary Detail Code2]', 'AutoCallSummary Detail Code2', '[Call & Voice Call Event Detail Code2]', 'Voice Call Event Detail Code2']) if df_ed is not None else None
        info_col = self._find_col(df_ed, ['[Call & AutoCallSummary Info]', 'AutoCallSummary Info', '[Call & Voice Call Event Info]', 'Voice Call Event Info']) if df_ed is not None else None

        # 3-A. 순수 시나리오명 텍스트 수집 (경로 오염 방지: 파일명은 폴백으로만 사용)
        candidate_scen_texts = []
        if scen_name_col and df_ed is not None and not df_ed[scen_name_col].dropna().empty:
            candidate_scen_texts.extend(df_ed[scen_name_col].dropna().astype(str).unique())
        if not candidate_scen_texts and df_call_res is not None and not df_call_res.empty:
            sc_c = self._find_col(df_call_res, ['[Call & AutoCallSummary Scenario Name]', 'Scenario Name'])
            if sc_c and sc_c in df_call_res.columns:
                candidate_scen_texts.extend(df_call_res[sc_c].dropna().astype(str).unique())
        if not candidate_scen_texts and csvs.get('KPI'):
            candidate_scen_texts.append(os.path.basename(csvs['KPI']))
        scen_combined = " ".join(candidate_scen_texts).upper()

        scen_has_sst = any(k in scen_combined for k in ['SST', '인지품질', 'SPEEDTEST', 'SPEED TEST'])
        scen_has_voice = any(k in scen_combined for k in ['VOICE', 'VOLTE', 'VONR', '음성', 'AMR'])
        scen_has_ul = any(k in scen_combined for k in ['_UL', 'FTP_UL', 'UL_', ' UPLOAD', '상향'])
        scen_has_dl = any(k in scen_combined for k in ['_DL', 'FTP_DL', 'DL_', ' DOWNLOAD', '하향'])

        # 3-B. 망 모드별 순수 PDCP Throughput 단독 추출 (무작정 다 더하지 않음)
        avg_dl_pdcp = 0.0
        avg_ul_pdcp = 0.0
        if df_kpi is not None and not df_kpi.empty:
            if net_mode in ['NSA', 'SA']:
                dl_pdcp_col = self._find_col(df_kpi, ['[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]', 'Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]', 'Layer2 PDCP DL Throughput'])
                ul_pdcp_col = self._find_col(df_kpi, ['[Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]]', 'Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]', 'Layer2 PDCP UL Throughput'])
            else:
                dl_pdcp_col = self._find_col(df_kpi, ['[Call & LTE KPI PDCP DL Throughput [Mbps]]', 'PDCP DL Throughput [Mbps]', 'PDCP DL Throughput'])
                ul_pdcp_col = self._find_col(df_kpi, ['[Call & LTE KPI PDCP UL Throughput [Mbps]]', 'PDCP UL Throughput [Mbps]', 'PDCP UL Throughput'])

            if dl_pdcp_col and dl_pdcp_col in df_kpi.columns:
                avg_dl_pdcp = float(pd.to_numeric(df_kpi[dl_pdcp_col], errors='coerce').dropna().mean() or 0.0)
            if ul_pdcp_col and ul_pdcp_col in df_kpi.columns:
                avg_ul_pdcp = float(pd.to_numeric(df_kpi[ul_pdcp_col], errors='coerce').dropna().mean() or 0.0)

        # 3-C. SST 및 Voice 실측 이벤트 검사
        is_sst_event = False
        if df_kpi is not None and not df_kpi.empty:
            if any(self._find_col(df_kpi, [k]) for k in ['[Call & SKT Speed Test Call Info SST Call Event]', '[Call & SKT Speed Test Call Info Download Event Info DL Throughput]']):
                is_sst_event = True
        if not is_sst_event and df_event is not None and not df_event.empty:
            for c in df_event.columns:
                if df_event[c].dropna().astype(str).str.contains('Ping-Start|Download-Start|Upload-Start|SST|인지품질', case=False).any():
                    is_sst_event = True
                    break
        if not is_sst_event and df_ed is not None and not df_ed.empty:
            for c in df_ed.columns:
                if df_ed[c].dropna().astype(str).str.contains('Ping-Start|Download-Start|Upload-Start|SST|인지품질|Ping Start|Download Start|Upload Start', case=False).any():
                    is_sst_event = True
                    break

        has_real_voice_rtp = False
        if df_rtp is not None and not df_rtp.empty and len(df_rtp) > 5:
            for c in df_rtp.columns:
                if any(kw in str(c).lower() for kw in ['mos', 'jitter', 'loss', 'packet', 'vocoder', 'codec']):
                    if df_rtp[c].dropna().count() > 3:
                        has_real_voice_rtp = True
                        break

        has_voice_event = False
        if call_type_col and df_ed is not None and df_ed[call_type_col].dropna().astype(str).str.contains('Voice|VoLTE', case=False).any():
            has_voice_event = True
        if df_event is not None and not df_event.empty:
            v_col = self._find_col(df_event, ['Voice Call Service(per second)', 'Voice Call Service(Transition)'])
            if v_col and df_event[v_col].dropna().astype(str).str.contains('VoLTE|Voice', case=False, na=False).any():
                has_voice_event = True

        # 3-D. 3단계 트래픽 모델 결정 (SST -> VOICE -> DL vs UL)
        base_traffic_model = 'DL'
        if (scen_has_sst and is_sst_event) or is_sst_event:
            base_traffic_model = 'SST'
        elif (scen_has_voice and (has_real_voice_rtp or has_voice_event)) or has_real_voice_rtp or has_voice_event:
            base_traffic_model = 'VOICE'
        elif scen_has_ul and avg_ul_pdcp > 0.5:
            base_traffic_model = 'UL'
        elif scen_has_dl and avg_dl_pdcp > 0.5:
            base_traffic_model = 'DL'
        elif avg_ul_pdcp > 1.0 and avg_ul_pdcp > avg_dl_pdcp * 2.0:
            base_traffic_model = 'UL'
        elif avg_dl_pdcp > 1.0 and avg_dl_pdcp > avg_ul_pdcp * 2.0:
            base_traffic_model = 'DL'
        elif scen_has_ul:
            base_traffic_model = 'UL'
        else:
            base_traffic_model = 'DL'

        # -----------------------------------------------------------------
        # [4단계: 단말 포트 및 세부 시나리오 판별 (MO/MT, Long/Short Call)]
        # -----------------------------------------------------------------
        traffic_model = base_traffic_model

        if base_traffic_model == 'VOICE':
            has_sip_tx = False
            has_sip_rx = False
            if df_ed is not None and not df_ed.empty:
                for col_cand in [cd2_col, cd1_col, info_col]:
                    if col_cand and col_cand in df_ed.columns:
                        s_str = " ".join(df_ed[col_cand].dropna().astype(str).unique()).upper()
                        if any(k in s_str for k in ['SIP TX', 'INVITE (TX)', 'ORIGINATING', 'CALL SETUP', 'INVITE TX']):
                            has_sip_tx = True
                        if any(k in s_str for k in ['SIP RX', 'INVITE (RX)', 'TERMINATING', 'RINGING (RX)', 'INVITE RX']):
                            has_sip_rx = True

            scen_has_mo = any(k in scen_combined for k in ['_MO', 'MO_', ' MO', '발신', 'ORIGINATING', 'CALL_MO'])
            scen_has_mt = any(k in scen_combined for k in ['_MT', 'MT_', ' MT', '착신', 'TERMINATING', 'CALL_MT'])

            if scen_has_mo and (has_sip_tx or not has_sip_rx):
                traffic_model = 'VOICE_MO'
            elif scen_has_mt and (has_sip_rx or not has_sip_tx):
                traffic_model = 'VOICE_MT'
            elif has_sip_tx and not has_sip_rx:
                traffic_model = 'VOICE_MO'
            elif has_sip_rx and not has_sip_tx:
                traffic_model = 'VOICE_MT'
            elif scen_has_mo:
                traffic_model = 'VOICE_MO'
            elif scen_has_mt:
                traffic_model = 'VOICE_MT'
            else:
                traffic_model = 'VOICE_MO'

        # 5. Extract Call Intervals & Sequence (AutoCallSummary / Voice Call Event / KPI Events)
        call_intervals = []
        if df_ed is not None and not df_ed.empty and 'TIME_STAMP' in df_ed.columns:
            st_col = self._find_col(df_ed, ['[Call & AutoCallSummary Status]', 'AutoCallSummary Status', '[Call & Voice Call Event Status]', 'Voice Call Event Status', 'AutoCall Status'])
            cnt_col = self._find_col(df_ed, ['[Call & AutoCallSummary Call count]', 'AutoCallSummary Call count', 'Call count'])
            cd1_col = self._find_col(df_ed, ['[Call & AutoCallSummary Detail Code1]', 'AutoCallSummary Detail Code1', '[Call & Voice Call Event Detail Code1]', 'Voice Call Event Detail Code1'])

            if st_col:
                cur_start = None
                cur_call_idx = 1
                for idx, row in df_ed.dropna(subset=['TIME_STAMP']).iterrows():
                    st_val = str(row[st_col]).strip()
                    cd1_val = str(row[cd1_col]).strip() if cd1_col else ''
                    ts_val = pd.to_datetime(row['TIME_STAMP'])
                    c_cnt = int(row[cnt_col]) if (cnt_col and pd.notna(row[cnt_col])) else None

                    if (st_val == 'Traffic' or cd1_val == 'Start') and cur_start is None:
                        cur_start = ts_val
                        if c_cnt is not None:
                            cur_call_idx = c_cnt
                    elif st_val in ['Success', 'Drop', 'Release', 'Fail', 'End By User'] or cd1_val in ['Success', 'Drop', 'Fail']:
                        if cur_start is not None:
                            dur = (ts_val - cur_start).total_seconds()
                            if dur >= 1.0:
                                call_intervals.append({
                                    'call_no': f"Call {cur_call_idx}",
                                    'start': cur_start,
                                    'end': ts_val,
                                    'status': st_val,
                                    'detail': cd1_val
                                })
                            cur_start = None
                            if c_cnt is None:
                                cur_call_idx += 1

        # Fallback to KPI or Event if no AutoCallSummary
        if not call_intervals and df_event is not None and not df_event.empty and 'TIME_STAMP' in df_event.columns:
            v_stat = self._find_col(df_event, ['Voice Call Service(per second)', 'Voice Call Service(Transition)'])
            if v_stat:
                v_rows = df_event[df_event[v_stat].dropna().astype(str).str.contains('VoLTE|Voice', case=False, na=False)]
                if not v_rows.empty:
                    call_intervals.append({
                        'call_no': 'Call 1',
                        'start': pd.to_datetime(v_rows['TIME_STAMP'].iloc[0]),
                        'end': pd.to_datetime(v_rows['TIME_STAMP'].iloc[-1]),
                        'status': 'Success',
                        'detail': 'VoLTE'
                    })

        if not time_series_frames:
            return pd.DataFrame()

        # Merge all frames
        df_merged = pd.concat(time_series_frames, ignore_index=True)
        df_merged['TIME_STAMP'] = pd.to_datetime(df_merged['TIME_STAMP'], errors='coerce')
        df_merged = df_merged.dropna(subset=['TIME_STAMP']).sort_values('TIME_STAMP').reset_index(drop=True)

        # 1-Second Grid Normalization (Floor to seconds)
        df_merged['clean_sec'] = df_merged['TIME_STAMP'].dt.floor('s')

        # Deduplicate per second, prioritizing QC_KPI / RTP
        df_1hz = df_merged.groupby('clean_sec').last().reset_index()
        df_1hz['TIME_STAMP'] = df_1hz['clean_sec']
        df_1hz = df_1hz.drop(columns=['clean_sec'])

        # Forward Fill RF & Serving Parameters (excluding Speed)
        ffill_cols = [
            'eNB_ID', 'Cell_ID', 'TAC', 'EARFCN',
            'NR_Serving_PCI', 'LTE_Serving_PCI',
            'SS_RSRP', 'SS_SINR', 'SS_RSRQ', 'CQI', 'DL_MCS', 'UL_MCS',
            'PDSCH_BLER', 'PUSCH_BLER', 'PDSCH_Tput', 'PUSCH_Tput', 'PRB_Num_Inc0', 'WB_RI', 'QAM64_Rate', 'QAM256_Rate',
            'Lat', 'Lon'
        ]
        for c in ffill_cols:
            if c in df_1hz.columns:
                df_1hz[c] = df_1hz[c].ffill().bfill()

        # Compute Haversine speed specifically for rows where NMEA sensor speed is NaN
        if 'Lon' in df_1hz.columns and 'Lat' in df_1hz.columns:
            def haversine_m(lon1, lat1, lon2, lat2):
                if pd.isna(lon1) or pd.isna(lat1) or pd.isna(lon2) or pd.isna(lat2):
                    return 0.0
                lon1_r, lat1_r, lon2_r, lat2_r = map(np.radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
                dlon = lon2_r - lon1_r
                dlat = lat2_r - lat1_r
                a = np.sin(dlat / 2.0)**2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2.0)**2
                c = 2 * np.arcsin(np.clip(np.sqrt(a), 0, 1))
                return 6371000.0 * c

            if 'Speed' not in df_1hz.columns:
                df_1hz['Speed'] = np.nan

            s_speeds = pd.to_numeric(df_1hz['Speed'], errors='coerce')
            calc_speeds = []
            for i in range(len(df_1hz)):
                curr_s = s_speeds.iloc[i]
                if pd.notna(curr_s):
                    calc_speeds.append(round(float(curr_s), 1))
                else:
                    if i == 0:
                        calc_speeds.append(0.0)
                    else:
                        prev_lon = df_1hz['Lon'].iloc[i - 1]
                        prev_lat = df_1hz['Lat'].iloc[i - 1]
                        curr_lon = df_1hz['Lon'].iloc[i]
                        curr_lat = df_1hz['Lat'].iloc[i]

                        prev_ts = df_1hz['TIME_STAMP'].iloc[i - 1]
                        curr_ts = df_1hz['TIME_STAMP'].iloc[i]
                        dt_sec = (curr_ts - prev_ts).total_seconds() if (pd.notna(prev_ts) and pd.notna(curr_ts)) else 1.0
                        if dt_sec <= 0:
                            dt_sec = 1.0

                        d_m = haversine_m(prev_lon, prev_lat, curr_lon, curr_lat)
                        spd_kmh = (d_m / dt_sec) * 3.6
                        calc_speeds.append(round(float(spd_kmh), 1))
            df_1hz['Speed'] = calc_speeds

        # Compute clean eNB_Cell_ID
        if 'eNB_ID' in df_1hz.columns and 'Cell_ID' in df_1hz.columns:
            def format_enb_cell(row):
                if pd.notna(row['eNB_ID']) and pd.notna(row['Cell_ID']):
                    try:
                        enb_i = int(float(row['eNB_ID']))
                        cell_i = int(float(row['Cell_ID']))
                        return f"{enb_i}-{cell_i % 256}"
                    except Exception:
                        return f"{row['eNB_ID']}-{row['Cell_ID']}"
                return "-"
            df_1hz['eNB_Cell_ID'] = df_1hz.apply(format_enb_cell, axis=1)

        # Auto-detect NSA mode if NR measurements exist
        if net_mode == 'LTE':
            if 'NR_SS_RSRP' in df_1hz.columns and not df_1hz['NR_SS_RSRP'].dropna().empty:
                net_mode = 'NSA'
            elif 'NR_Serving_PCI' in df_1hz.columns and not df_1hz['NR_Serving_PCI'].dropna().empty:
                net_mode = 'NSA'

        # Determine DL Long Call vs Short Call vs UL Long/Short
        if traffic_model in ['DL', 'DL_Long_Call', 'DL_Short_Call']:
            is_long_kw = any(k in scen_combined for k in ['CONTINUOUS', 'LONG', '무선품질', '연속'])
            if is_long_kw:
                traffic_model = 'DL_Long_Call'
            elif call_intervals:
                durations = [(ci['end'] - ci['start']).total_seconds() for ci in call_intervals if 'start' in ci and 'end' in ci]
                med_dur = np.median(durations) if durations else 0
                max_dur = max(durations) if durations else 0
                if len(call_intervals) == 1 and max_dur >= 60.0:
                    traffic_model = 'DL_Long_Call'
                elif med_dur >= 120.0:
                    traffic_model = 'DL_Long_Call'
                else:
                    traffic_model = 'DL_Short_Call'
            else:
                traffic_model = 'DL_Long_Call'
        elif traffic_model in ['UL', 'UL_Long_Call', 'UL_Short_Call']:
            is_long_kw = any(k in scen_combined for k in ['CONTINUOUS', 'LONG', '무선품질', '연속'])
            if is_long_kw:
                traffic_model = 'UL_Long_Call'
            elif call_intervals:
                durations = [(ci['end'] - ci['start']).total_seconds() for ci in call_intervals if 'start' in ci and 'end' in ci]
                med_dur = np.median(durations) if durations else 0
                max_dur = max(durations) if durations else 0
                if len(call_intervals) == 1 and max_dur >= 60.0:
                    traffic_model = 'UL_Long_Call'
                elif med_dur >= 120.0:
                    traffic_model = 'UL_Long_Call'
                else:
                    traffic_model = 'UL_Short_Call'
            else:
                traffic_model = 'UL_Long_Call'

        # Ingest 4 Core Automated SSOT Attributes
        df_1hz['Network_Mode'] = net_mode
        df_1hz['Active_Vendor'] = vendor
        df_1hz['Port_Key'] = port_key
        df_1hz['Traffic_Model'] = traffic_model
        df_1hz['Call_No'] = 'Call 1'
        df_1hz['Call_Phase'] = 'IDLE_Gap'

        traffic_phase_prefix = 'VOICE' if traffic_model.startswith('VOICE') else ('UL' if traffic_model.startswith('UL') else ('DL' if traffic_model.startswith('DL') else traffic_model))

        if call_intervals:
            for interval in call_intervals:
                c_mask = (df_1hz['TIME_STAMP'] >= interval['start']) & (df_1hz['TIME_STAMP'] <= interval['end'])
                df_1hz.loc[c_mask, 'Call_No'] = interval['call_no']
                df_1hz.loc[c_mask, 'Call_Phase'] = f"{traffic_phase_prefix}_Traffic"
        else:
            # Fallback continuous
            if traffic_model.startswith('VOICE'):
                df_1hz['Call_Phase'] = 'VOICE_Traffic'
            elif traffic_model.startswith('DL'):
                s_pdcp = pd.to_numeric(df_1hz['PDCP_DL_Tput'], errors='coerce').fillna(0) if 'PDCP_DL_Tput' in df_1hz.columns else pd.Series(0.0, index=df_1hz.index)
                s_pdsch = pd.to_numeric(df_1hz['PDSCH_Tput'], errors='coerce').fillna(0) if 'PDSCH_Tput' in df_1hz.columns else pd.Series(0.0, index=df_1hz.index)
                s_app = pd.to_numeric(df_1hz['App_DL_Tput'], errors='coerce').fillna(0) if 'App_DL_Tput' in df_1hz.columns else pd.Series(0.0, index=df_1hz.index)
                tput_s = s_pdcp + s_pdsch + s_app
                df_1hz.loc[tput_s > 0.0, 'Call_Phase'] = 'DL_Traffic'
            elif traffic_model.startswith('UL'):
                s_pdcp_ul = pd.to_numeric(df_1hz['PDCP_UL_Tput'], errors='coerce').fillna(0) if 'PDCP_UL_Tput' in df_1hz.columns else pd.Series(0.0, index=df_1hz.index)
                s_pusch = pd.to_numeric(df_1hz['PUSCH_Tput'], errors='coerce').fillna(0) if 'PUSCH_Tput' in df_1hz.columns else pd.Series(0.0, index=df_1hz.index)
                s_app_ul = pd.to_numeric(df_1hz['App_UL_Tput'], errors='coerce').fillna(0) if 'App_UL_Tput' in df_1hz.columns else pd.Series(0.0, index=df_1hz.index)
                tput_s = s_pdcp_ul + s_pusch + s_app_ul
                df_1hz.loc[tput_s > 0.0, 'Call_Phase'] = 'UL_Traffic'
            else:
                df_1hz['Call_Phase'] = f"{traffic_phase_prefix}_Traffic"

        # Register SSOT DataFrame attributes
        df_1hz.attrs['Network_Mode'] = net_mode
        df_1hz.attrs['Active_Vendor'] = vendor
        df_1hz.attrs['Traffic_Model'] = traffic_model
        df_1hz.attrs['Port_Key'] = port_key

        return df_1hz
