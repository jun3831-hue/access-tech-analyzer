# -*- coding: utf-8 -*-
r"""
File: 4_Optis_AI_Analyzer/core/parsers/master_timeline_parser.py
Description: Multi-Source Integrated Master Timeline Parser with AutoCallSummary Traffic vs IDLE Phase Alignment
"""

import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from core.canonical_registry import CanonicalColumnRegistry


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

    @classmethod
    def _extract_sip_and_l3_events(
        cls,
        df_ed: Optional[pd.DataFrame],
        l3_csv_path: Optional[str] = None
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        Extracts SIP/IMS and 3GPP L3 signaling mapped by second string ('HH:MM:SS').
        Preserves chronological millisecond sequence with ' ➔ ' connectors and full L3 message fidelity.
        Returns:
            (sip_by_sec, l3_by_sec)
        """
        sip_by_sec = {}
        l3_by_sec = {}

        # 1. From Fav_Event_(Detail).csv
        if df_ed is not None and not df_ed.empty and 'TIME_STAMP' in df_ed.columns:
            st_col = cls._find_col(df_ed, ['[Call & Voice Call Event Status]', 'Voice Call Event Status', 'Status'])
            c1_col = cls._find_col(df_ed, ['[Call & Voice Call Event Detail Code1]', 'Voice Call Event Detail Code1', 'Detail Code1'])
            c2_col = cls._find_col(df_ed, ['[Call & Voice Call Event Detail Code2]', 'Voice Call Event Detail Code2', 'Detail Code2'])
            info_col = cls._find_col(df_ed, ['[Call & Voice Call Event Info]', 'Voice Call Event Info', 'Info'])

            df_temp = df_ed.dropna(subset=['TIME_STAMP']).copy()
            df_temp['_dt'] = pd.to_datetime(df_temp['TIME_STAMP'], errors='coerce')
            df_temp = df_temp.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)
            df_temp['__sec'] = df_temp['_dt'].dt.strftime('%H:%M:%S')

            for sec_str, grp in df_temp.groupby('__sec', sort=False):
                sip_items = []
                l3_items = []
                for _, r in grp.iterrows():
                    st_val = str(r.get(st_col, '')).strip() if st_col else ''
                    c1_val = str(r.get(c1_col, '')).strip() if c1_col else ''
                    c2_val = str(r.get(c2_col, '')).strip() if c2_col else ''
                    info_val = str(r.get(info_col, '')).strip() if info_col else ''
                    full_txt = f"{st_val} {c1_val} {c2_val} {info_val}".lower()

                    # SIP check (Exclude periodic/in-traffic SIP UPDATE noise unless explicit error)
                    if any(k in full_txt for k in ['sip', 'bye', 'invite', '200 ok', '180', 'ringing']):
                        dir_tag = "(Tx)" if ('tx' in c2_val.lower() or 'tx' in full_txt) else ("(Rx)" if ('rx' in c2_val.lower() or 'rx' in full_txt) else "")
                        if 'bye' in full_txt:
                            msg_name = f"SIP BYE {dir_tag}".strip()
                        elif '200 ok' in full_txt:
                            msg_name = f"SIP 200 OK {dir_tag}".strip()
                        elif '180' in full_txt or 'ringing' in full_txt:
                            msg_name = f"SIP 180 Ringing {dir_tag}".strip()
                        elif 'invite' in full_txt:
                            msg_name = f"SIP INVITE {dir_tag}".strip()
                        else:
                            msg_name = f"SIP: {c1_val or info_val or st_val}".strip()
                        if msg_name and msg_name not in sip_items:
                            sip_items.append(msg_name)

                    # L3 / NAS / Radio Event check (Exclude periodic broadcast noise: MIB, SIB1)
                    if any(k in full_txt for k in ['reestablishment', 'reconfiguration', 'setup', 'reject', 'request', 'release', 'drop', 'measurementreport', 'tau', 'tracking area', 'handover', 'rlf', 'link failure', 'rach']):
                        # Ignore periodic broadcast noise
                        if any(nb in full_txt for nb in ['masterinformationblock', 'systeminformationblocktype1', 'mib', 'sib1']):
                            continue

                        if 'reestablishment' in full_txt:
                            l3_label = 'RRCConnectionReestablishmentReject' if 'reject' in full_txt else 'RRCConnectionReestablishmentRequest'
                        elif 'reconfiguration' in full_txt:
                            l3_label = 'RRCConnectionReconfigurationComplete' if 'complete' in full_txt else 'RRCConnectionReconfiguration'
                        elif 'setup' in full_txt:
                            l3_label = 'RRCConnectionSetupComplete' if 'complete' in full_txt else 'RRCConnectionSetup'
                        elif 'release' in full_txt or 'drop' in full_txt:
                            l3_label = 'RRCConnectionRelease'
                        elif 'tau' in full_txt or 'tracking area' in full_txt:
                            l3_label = 'TrackingAreaUpdateRequest' if 'request' in full_txt else 'TrackingAreaUpdateAccept'
                        elif 'rach' in full_txt:
                            l3_label = 'RACH Preamble Transmitted'
                        elif 'rlf' in full_txt or 'link failure' in full_txt:
                            l3_label = 'RadioLinkFailure (RLF)'
                        else:
                            l3_label = c1_val or st_val
                        if l3_label and l3_label not in l3_items:
                            l3_items.append(l3_label)

                if sip_items:
                    sip_by_sec[sec_str] = " ➔ ".join(sip_items)
                if l3_items:
                    l3_by_sec[sec_str] = " ➔ ".join(l3_items)

        # 2. From MessageBrowser if available (Full L3/NAS preservation with chronological arrow)
        if l3_csv_path and os.path.exists(l3_csv_path):
            try:
                df_mb = safe_read_csv(l3_csv_path)
                if df_mb is not None and not df_mb.empty:
                    t_col = cls._find_col(df_mb, ['TIME_STAMP', 'Time', '시간', '시각'])
                    m_col = cls._find_col(df_mb, ['Message_Name', 'Message Name', 'Message', 'msg', '메시지'])
                    if t_col and m_col:
                        df_mb['_dt'] = pd.to_datetime(df_mb[t_col], errors='coerce')
                        df_mb = df_mb.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)
                        df_mb['_sec'] = df_mb['_dt'].dt.strftime('%H:%M:%S')

                        canonical_patterns = [
                            ('reestablishmentreject', 'RRCConnectionReestablishmentReject'),
                            ('reestablishmentrequest', 'RRCConnectionReestablishmentRequest'),
                            ('reconfigurationcomplete', 'RRCConnectionReconfigurationComplete'),
                            ('reconfiguration', 'RRCConnectionReconfiguration'),
                            ('setupcomplete', 'RRCConnectionSetupComplete'),
                            ('setuprequest', 'RRCConnectionRequest'),
                            ('setup', 'RRCConnectionSetup'),
                            ('connectionrelease', 'RRCConnectionRelease'),
                            ('measurementreport', 'MeasurementReport'),
                            ('securitymodecommand', 'SecurityModeCommand'),
                            ('securitymodecomplete', 'SecurityModeComplete'),
                            ('trackingareaupdaterequest', 'Tracking Area Update Request'),
                            ('trackingareaupdateaccept', 'Tracking Area Update Accept'),
                            ('attachrequest', 'Attach Request'),
                            ('attachaccept', 'Attach Accept'),
                            ('servicerequest', 'Service Request'),
                            ('mobilityfromeutracommand', 'MobilityFromEUTRACommand')
                        ]

                        for sec_str, grp in df_mb.groupby('_sec', sort=False):
                            mb_l3 = []
                            for m in grp[m_col].dropna().astype(str).tolist():
                                m_clean = m.strip()
                                m_lower = m_clean.lower()
                                # Ignore pure periodic broadcast noise
                                if m_lower in ['masterinformationblock', 'mib', 'systeminformationblocktype1', 'sib1', '__masterinformationblock', '__systeminformationblocktype1']:
                                    continue
                                matched_canon = None
                                for pat, canon in canonical_patterns:
                                    if pat in m_lower:
                                        matched_canon = canon
                                        break
                                label_to_add = matched_canon or m_clean
                                if label_to_add and (not mb_l3 or mb_l3[-1] != label_to_add):
                                    mb_l3.append(label_to_add)

                            if mb_l3:
                                existing = l3_by_sec.get(sec_str, "")
                                combined = [x.strip() for x in existing.split(" ➔ ") if x.strip()] if existing else []
                                for it in mb_l3:
                                    if it not in combined:
                                        combined.append(it)
                                l3_by_sec[sec_str] = " ➔ ".join(combined)
            except Exception:
                pass

        return sip_by_sec, l3_by_sec

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

        # 1. Base KPI Table (Preserve 100% of original raw CSV columns)
        kpi_csv = csvs.get('KPI') or csvs.get('QC_KPI')
        df_kpi = safe_read_csv(kpi_csv)
        sub_kpi = None
        if df_kpi is not None and not df_kpi.empty and 'TIME_STAMP' in df_kpi.columns:
            sub_kpi = df_kpi.copy()
            for target, kws in [
                ('Lat', ['Lat', '[Call & GPS Lat]']),
                ('Lon', ['Lon', '[Call & GPS Lon]']),
                ('Speed', ['[Call & GPS Speed (km/h)]', 'Speed']),
                ('LTE_PDCP_DL_Tput', ['[Call & LTE KPI PDCP DL Throughput [Mbps]]', 'PDCP DL Throughput [Mbps]']),
                ('NR_PDCP_DL_Tput', ['[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]', 'Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]']),
                ('LTE_PDCP_UL_Tput', ['[Call & LTE KPI PDCP UL Throughput [Mbps]]', 'PDCP UL Throughput [Mbps]']),
                ('NR_PDCP_UL_Tput', ['[Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]]', 'Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]']),
                ('App_DL_Tput', ['[Call & APP Throughput Info(All Data) All FWD  Throughput (kbps)]', '[Call & SKT Speed Test Call Info Download Event Info DL Throughput]', 'FTP FWD Throughput', 'Current App Throughput']),
                ('App_UL_Tput', ['[Call & APP Throughput Info(All Data) All RVS Throughput (kbps)]', '[Call & SKT Speed Test Call Info Upload Event Info UL Throughput]', 'FTP RVS Throughput', 'Current App Throughput']),
                ('NR_PDSCH_Tput', ['[Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PDSCH Throughput [Mbps]]', 'PCell PDSCH Throughput']),
                ('NR_PUSCH_Tput', ['[Call & 5G KPI Total Info Layer1 PUSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PUSCH Throughput [Mbps]]', 'PCell PUSCH Throughput']),
                ('NR_MAC_DL_Tput', ['[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]', 'NR-DL MAC PCell DL MAC Throughput']),
                ('NR_MAC_UL_Tput', ['[Call & 5G KPI Total Info Layer2 MAC UL Throughput [Mbps]]', 'Layer2 MAC UL Throughput']),
                ('LTE_PDSCH_Tput', ['[Call & LTE KPI PDSCH Throughput [Mbps]]', 'PDSCH Throughput [Mbps]']),
                ('LTE_PUSCH_Tput', ['[Call & LTE KPI PUSCH Throughput [Mbps]]', 'PUSCH Throughput [Mbps]']),
                ('LTE_MAC_DL_Tput', ['[Call & LTE KPI MAC DL Throughput [Mbps]]', 'L1/L2 Throughput [Mbps] MAC DL Throughput']),
                ('LTE_MAC_UL_Tput', ['[Call & LTE KPI MAC UL Throughput [Mbps]]', '[Call & LTE KPI PCell MAC UL Throughput [Mbps]]']),
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
                ('NR_UL_QAM64_Rate', ['[Call & 5G KPI PCell Layer1 UL Modulation UL 64QAM Rate [%]]']),
                ('NR_UL_QAM256_Rate', ['[Call & 5G KPI PCell Layer1 UL Modulation UL 256 QAM Rate [%]]']),
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
                ('SST_DL_Tput', ['[Call & SKT Speed Test Call Info Download Event Info DL Throughput]']),
                ('SST_UL_Tput', ['[Call & SKT Speed Test Call Info Upload Event Info UL Throughput]']),
                ('SST_Ping_Result', ['[Call & SKT Speed Test Call Info Ping Event Info Ping Throughput Result]']),
                ('SST_Event', ['[Call & SKT Speed Test Call Info SST Call Event]']),
                ('MOS', ['MOS P863', 'MOS Result', 'P863(POLQA)', 'POLQA', 'MOS'])
            ]:
                found = self._find_col(df_kpi, kws)
                if found:
                    if target in ['App_DL_Tput', 'App_UL_Tput']:
                        s_vals = pd.to_numeric(df_kpi[found], errors='coerce')
                        if 'kbps' in str(found).lower() or (not s_vals.dropna().empty and s_vals.dropna().max() > 10000):
                            sub_kpi[target] = s_vals / 1000.0
                        else:
                            sub_kpi[target] = s_vals
                    else:
                        sub_kpi[target] = df_kpi[found]

            # Dynamic calculation of LTE PCell DL Modulation Rate (64QAM, 256QAM)
            lte_dl_mod_col = self._find_col(df_kpi, ['[Call & LTE KPI PCell DL Modulation0]', 'PCell DL Modulation0', 'LTE PCell DL Modulation0'])
            if lte_dl_mod_col and lte_dl_mod_col in df_kpi.columns:
                s_mod = df_kpi[lte_dl_mod_col].astype(str).str.upper()
                valid_mask = df_kpi[lte_dl_mod_col].notna() & (s_mod != 'NAN') & (s_mod != '')
                sub_kpi['LTE_QAM64_Rate'] = np.where(valid_mask, np.where(s_mod.str.contains('64QAM|64 QAM'), 100.0, 0.0), np.nan)
                sub_kpi['LTE_QAM256_Rate'] = np.where(valid_mask, np.where(s_mod.str.contains('256QAM|256 QAM'), 100.0, 0.0), np.nan)
            else:
                sub_kpi['LTE_QAM64_Rate'] = np.nan
                sub_kpi['LTE_QAM256_Rate'] = np.nan

            # Dynamic calculation of LTE PCell UL Modulation Rate (64QAM, 256QAM)
            lte_ul_mod_col = self._find_col(df_kpi, ['[Call & LTE KPI PCell UL Modulation]', 'PCell UL Modulation', 'LTE PCell UL Modulation'])
            if lte_ul_mod_col and lte_ul_mod_col in df_kpi.columns:
                s_ul_mod = df_kpi[lte_ul_mod_col].astype(str).str.upper()
                valid_ul_mask = df_kpi[lte_ul_mod_col].notna() & (s_ul_mod != 'NAN') & (s_ul_mod != '')
                sub_kpi['LTE_UL_QAM64_Rate'] = np.where(valid_ul_mask, np.where(s_ul_mod.str.contains('64QAM|64 QAM'), 100.0, 0.0), np.nan)
                sub_kpi['LTE_UL_QAM256_Rate'] = np.where(valid_ul_mask, np.where(s_ul_mod.str.contains('256QAM|256 QAM'), 100.0, 0.0), np.nan)
            else:
                sub_kpi['LTE_UL_QAM64_Rate'] = np.nan
                sub_kpi['LTE_UL_QAM256_Rate'] = np.nan

            sub_kpi['Source_Type'] = 'QC_KPI'
            time_series_frames.append(sub_kpi)

        # 2. Smart Phone Telemetry
        sub_sp = None
        sp_csv = csvs.get('SMART_PHONE') or csvs.get('Smart_Phone')
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
        sub_rtp = None
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
        df_event = safe_read_csv(csvs.get('EVENT') or csvs.get('Event'))
        df_ed = safe_read_csv(csvs.get('EVENT_DETAIL') or csvs.get('Event_(Detail)') or csvs.get('EVENT_(DETAIL)'))
        df_call_res = safe_read_csv(csvs.get('CALL_RESULT') or csvs.get('Call_Result'))

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

        # 3-A. 원천 데이터(Call Result, Event Detail) 공식 필드 기반 시나리오 및 콜 종류 식별
        raw_call_types = []
        if df_call_res is not None and not df_call_res.empty:
            for c_cand in ['[Call & AutoCallSummary Scenario Name]', 'Scenario Name', '[Call & AutoCallSummary Call type]', 'Call Type', 'Call type', 'Service Type']:
                c_fld = self._find_col(df_call_res, [c_cand])
                if c_fld and c_fld in df_call_res.columns:
                    raw_call_types.extend(df_call_res[c_fld].dropna().astype(str).unique())

        if df_ed is not None and not df_ed.empty:
            for c_cand in ['[Call & AutoCallSummary Scenario Name]', 'AutoCallSummary Scenario Name', '[Call & AutoCallSummary Call type]', 'AutoCallSummary Call type']:
                c_fld = self._find_col(df_ed, [c_cand])
                if c_fld and c_fld in df_ed.columns:
                    raw_call_types.extend(df_ed[c_fld].dropna().astype(str).unique())

        call_types_str = " ".join(raw_call_types).upper()

        # 3-B. SST (속도측정/인지품질) 공식 원천 컬럼 확인
        is_sst_event = False
        if df_kpi is not None and not df_kpi.empty:
            sst_cols = ['[Call & SKT Speed Test Call Info SST Call Event]', '[Call & SKT Speed Test Call Info Download Event Info DL Throughput]', '[Call & SKT Speed Test Call Info Ping Event Info Ping Response]']
            for sc_c in sst_cols:
                act_c = CanonicalColumnRegistry.get_actual_column(df_kpi, sc_c)
                if act_c and act_c in df_kpi.columns and not df_kpi[act_c].dropna().empty:
                    is_sst_event = True
                    break

        if not is_sst_event and df_event is not None and not df_event.empty:
            for c in df_event.columns:
                if df_event[c].dropna().astype(str).str.contains('Ping-Start|Download-Start|Upload-Start|SpeedTest', case=False).any():
                    is_sst_event = True
                    break

        # 3-C. VoLTE / VoNR 음성 공식 이벤트 및 실측 RTP 스트림 확인
        has_real_voice_rtp = False
        if df_rtp is not None and not df_rtp.empty and len(df_rtp) > 5:
            for c in df_rtp.columns:
                if any(kw in str(c).lower() for kw in ['mos', 'jitter', 'loss', 'packet', 'vocoder', 'codec']):
                    if df_rtp[c].dropna().count() > 3:
                        has_real_voice_rtp = True
                        break

        has_voice_event = False
        if any(k in call_types_str for k in ['VOICE', 'VOLTE', 'VONR']):
            has_voice_event = True
        if not has_voice_event and df_event is not None and not df_event.empty:
            v_col = self._find_col(df_event, ['Voice Call Service(per second)', 'Voice Call Service(Transition)'])
            if v_col and df_event[v_col].dropna().astype(str).str.contains('VoLTE|Voice', case=False, na=False).any():
                has_voice_event = True

        # 3-D. 원천 필드 직결 트래픽 모델 결정 (SST -> Voice -> Ping -> UL vs DL)
        if is_sst_event or 'SST' in call_types_str:
            base_traffic_model = 'SST'
        elif has_voice_event or (has_real_voice_rtp and not any(k in call_types_str for k in ['FTP', 'DATA', 'PING'])):
            base_traffic_model = 'VOICE'
        elif 'PING' in call_types_str:
            base_traffic_model = 'PING'
        elif any(k in call_types_str for k in ['_UL', 'FTP_UL', 'UL_', 'DATA UL', 'UPLOAD']):
            base_traffic_model = 'UL'
        elif any(k in call_types_str for k in ['_DL', 'FTP_DL', 'DL_', 'DATA DL', 'DOWNLOAD']):
            base_traffic_model = 'DL'
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

            if any(k in call_types_str for k in ['_MT', 'MT', '착신', 'TERMINATING']):
                traffic_model = 'VOICE_MT'
            elif any(k in call_types_str for k in ['_MO', 'MO', '발신', 'ORIGINATING']):
                traffic_model = 'VOICE_MO'
            elif has_sip_rx and not has_sip_tx:
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
                v_rows = df_event[df_event[v_stat].fillna('').astype(str).str.contains('VoLTE|Voice', case=False)]
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

        # Merge all frames preserving 100% of all original and alias columns with continuous 1s index
        all_ts_series = []
        for f in time_series_frames:
            if f is not None and not f.empty and 'TIME_STAMP' in f.columns:
                s_t = pd.to_datetime(f['TIME_STAMP'], errors='coerce').dropna()
                if not s_t.empty:
                    all_ts_series.append(s_t)

        if all_ts_series:
            full_ts = pd.concat(all_ts_series)
            t_min = full_ts.min().floor('s')
            t_max = full_ts.max().floor('s')
            df_1hz = pd.DataFrame({'clean_sec': pd.date_range(start=t_min, end=t_max, freq='1s')})
        else:
            df_1hz = pd.DataFrame(columns=['clean_sec'])

        if sub_kpi is not None and not sub_kpi.empty and 'TIME_STAMP' in sub_kpi.columns:
            sub_kpi['clean_sec'] = pd.to_datetime(sub_kpi['TIME_STAMP'], errors='coerce').dt.floor('s')
            kpi_dedup = sub_kpi.dropna(subset=['clean_sec']).groupby('clean_sec').last().reset_index().drop(columns=['TIME_STAMP', 'Source_Type'], errors='ignore')
            df_1hz = pd.merge(df_1hz, kpi_dedup, on='clean_sec', how='left')

        if sub_sp is not None and not sub_sp.empty and 'TIME_STAMP' in sub_sp.columns:
            sub_sp['clean_sec'] = pd.to_datetime(sub_sp['TIME_STAMP'], errors='coerce').dt.floor('s')
            sp_dedup = sub_sp.dropna(subset=['clean_sec']).groupby('clean_sec').last().reset_index().drop(columns=['TIME_STAMP', 'Source_Type'], errors='ignore')
            new_sp_cols = [c for c in sp_dedup.columns if c not in df_1hz.columns or c == 'clean_sec']
            df_1hz = pd.merge(df_1hz, sp_dedup[new_sp_cols], on='clean_sec', how='left')

        if sub_rtp is not None and not sub_rtp.empty and 'TIME_STAMP' in sub_rtp.columns:
            sub_rtp['clean_sec'] = pd.to_datetime(sub_rtp['TIME_STAMP'], errors='coerce').dt.floor('s')
            rtp_dedup = sub_rtp.dropna(subset=['clean_sec']).groupby('clean_sec').last().reset_index().drop(columns=['TIME_STAMP', 'Source_Type'], errors='ignore')
            new_rtp_cols = [c for c in rtp_dedup.columns if c not in df_1hz.columns or c == 'clean_sec']
            df_1hz = pd.merge(df_1hz, rtp_dedup[new_rtp_cols], on='clean_sec', how='left')

        df_1hz['TIME_STAMP'] = df_1hz['clean_sec']
        df_1hz = df_1hz.drop(columns=['clean_sec'], errors='ignore')

        # Extract and attach unified SIP and L3 Signaling
        sip_by_sec, l3_by_sec = self._extract_sip_and_l3_events(df_ed, csvs.get('L3_MSG'))
        df_1hz['sec_tag'] = pd.to_datetime(df_1hz['TIME_STAMP'], errors='coerce').dt.strftime('%H:%M:%S')
        df_1hz['SIP_Msg'] = df_1hz['sec_tag'].map(sip_by_sec).fillna('')
        # Bind unified metrics based on detected Network_Mode
        if net_mode == 'LTE':
            df_1hz['PDCP_DL_Tput'] = df_1hz.get('LTE_PDCP_DL_Tput', np.nan)
            df_1hz['PDCP_UL_Tput'] = df_1hz.get('LTE_PDCP_UL_Tput', np.nan)
            df_1hz['MAC_DL_Tput'] = df_1hz.get('LTE_MAC_DL_Tput', np.nan)
            df_1hz['MAC_UL_Tput'] = df_1hz.get('LTE_MAC_UL_Tput', np.nan)
            df_1hz['PDSCH_Tput'] = df_1hz.get('LTE_PDSCH_Tput', np.nan)
            df_1hz['PUSCH_Tput'] = df_1hz.get('LTE_PUSCH_Tput', np.nan)
            df_1hz['SS_RSRP'] = df_1hz.get('LTE_RSRP', np.nan)
            df_1hz['SS_SINR'] = df_1hz.get('LTE_SINR', np.nan)
            df_1hz['SS_RSRQ'] = df_1hz.get('LTE_RSRQ', np.nan)
            df_1hz['CQI'] = df_1hz.get('LTE_CQI', np.nan)
            df_1hz['DL_MCS'] = df_1hz.get('LTE_DL_MCS', np.nan)
            df_1hz['UL_MCS'] = df_1hz.get('LTE_UL_MCS', np.nan)
            df_1hz['PDSCH_BLER'] = df_1hz.get('LTE_PDSCH_BLER', np.nan)
            df_1hz['PUSCH_BLER'] = df_1hz.get('LTE_PUSCH_BLER', np.nan)
            df_1hz['PRB_Num_Inc0'] = df_1hz.get('LTE_PRB_Inc0', np.nan)
            df_1hz['WB_RI'] = df_1hz.get('LTE_WB_RI', np.nan)
            df_1hz['QAM64_Rate'] = df_1hz.get('LTE_QAM64_Rate', np.nan)
            df_1hz['QAM256_Rate'] = df_1hz.get('LTE_QAM256_Rate', np.nan)
            df_1hz['UL_QAM64_Rate'] = df_1hz.get('LTE_UL_QAM64_Rate', np.nan)
            df_1hz['UL_QAM256_Rate'] = df_1hz.get('LTE_UL_QAM256_Rate', np.nan)
        else:
            df_1hz['PDCP_DL_Tput'] = df_1hz.get('NR_PDCP_DL_Tput', df_1hz.get('LTE_PDCP_DL_Tput', np.nan))
            df_1hz['PDCP_UL_Tput'] = df_1hz.get('NR_PDCP_UL_Tput', df_1hz.get('LTE_PDCP_UL_Tput', np.nan))
            df_1hz['MAC_DL_Tput'] = df_1hz.get('NR_MAC_DL_Tput', df_1hz.get('LTE_MAC_DL_Tput', np.nan))
            df_1hz['MAC_UL_Tput'] = df_1hz.get('NR_MAC_UL_Tput', df_1hz.get('LTE_MAC_UL_Tput', np.nan))
            df_1hz['PDSCH_Tput'] = df_1hz.get('NR_PDSCH_Tput', df_1hz.get('LTE_PDSCH_Tput', np.nan))
            df_1hz['PUSCH_Tput'] = df_1hz.get('NR_PUSCH_Tput', df_1hz.get('LTE_PUSCH_Tput', np.nan))
            df_1hz['SS_RSRP'] = df_1hz.get('NR_SS_RSRP', df_1hz.get('LTE_RSRP', np.nan))
            df_1hz['SS_SINR'] = df_1hz.get('NR_SS_SINR', df_1hz.get('LTE_SINR', np.nan))
            df_1hz['SS_RSRQ'] = df_1hz.get('NR_SS_RSRQ', df_1hz.get('LTE_RSRQ', np.nan))
            df_1hz['CQI'] = df_1hz.get('NR_CQI', df_1hz.get('LTE_CQI', np.nan))
            df_1hz['DL_MCS'] = df_1hz.get('NR_DL_MCS', df_1hz.get('LTE_DL_MCS', np.nan))
            df_1hz['UL_MCS'] = df_1hz.get('NR_UL_MCS', df_1hz.get('LTE_UL_MCS', np.nan))
            df_1hz['PDSCH_BLER'] = df_1hz.get('NR_PDSCH_BLER', df_1hz.get('LTE_PDSCH_BLER', np.nan))
            df_1hz['PUSCH_BLER'] = df_1hz.get('NR_PUSCH_BLER', df_1hz.get('LTE_PUSCH_BLER', np.nan))
            df_1hz['PRB_Num_Inc0'] = df_1hz.get('NR_PRB_Inc0', df_1hz.get('LTE_PRB_Inc0', np.nan))
            df_1hz['WB_RI'] = df_1hz.get('NR_WB_RI', df_1hz.get('LTE_WB_RI', np.nan))
            df_1hz['QAM64_Rate'] = df_1hz.get('NR_QAM64_Rate', df_1hz.get('LTE_QAM64_Rate', np.nan))
            df_1hz['QAM256_Rate'] = df_1hz.get('NR_QAM256_Rate', df_1hz.get('LTE_QAM256_Rate', np.nan))
            df_1hz['UL_QAM64_Rate'] = df_1hz.get('NR_UL_QAM64_Rate', df_1hz.get('LTE_UL_QAM64_Rate', np.nan))
            df_1hz['UL_QAM256_Rate'] = df_1hz.get('NR_UL_QAM256_Rate', df_1hz.get('LTE_UL_QAM256_Rate', np.nan))

        # Forward Fill RF & Serving Parameters (excluding Speed)
        ffill_cols = [
            'eNB_ID', 'Cell_ID', 'TAC', 'EARFCN',
            'NR_Serving_PCI', 'LTE_Serving_PCI',
            'SS_RSRP', 'SS_SINR', 'SS_RSRQ', 'CQI', 'DL_MCS', 'UL_MCS',
            'PDSCH_BLER', 'PUSCH_BLER', 'PDSCH_Tput', 'PUSCH_Tput', 'PRB_Num_Inc0', 'WB_RI',
            'QAM64_Rate', 'QAM256_Rate', 'UL_QAM64_Rate', 'UL_QAM256_Rate',
            'LTE_QAM64_Rate', 'LTE_QAM256_Rate', 'LTE_UL_QAM64_Rate', 'LTE_UL_QAM256_Rate',
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

        # Refresh unified columns if mode is NSA / SA
        if net_mode in ['NSA', 'SA']:
            df_1hz['PDCP_DL_Tput'] = df_1hz.get('NR_PDCP_DL_Tput', df_1hz.get('LTE_PDCP_DL_Tput', np.nan))
            df_1hz['PDCP_UL_Tput'] = df_1hz.get('NR_PDCP_UL_Tput', df_1hz.get('LTE_PDCP_UL_Tput', np.nan))
            df_1hz['MAC_DL_Tput'] = df_1hz.get('NR_MAC_DL_Tput', df_1hz.get('LTE_MAC_DL_Tput', np.nan))
            df_1hz['MAC_UL_Tput'] = df_1hz.get('NR_MAC_UL_Tput', df_1hz.get('LTE_MAC_UL_Tput', np.nan))
            df_1hz['PDSCH_Tput'] = df_1hz.get('NR_PDSCH_Tput', df_1hz.get('LTE_PDSCH_Tput', np.nan))
            df_1hz['PUSCH_Tput'] = df_1hz.get('NR_PUSCH_Tput', df_1hz.get('LTE_PUSCH_Tput', np.nan))
            df_1hz['SS_RSRP'] = df_1hz.get('NR_SS_RSRP', df_1hz.get('LTE_RSRP', np.nan))
            df_1hz['SS_SINR'] = df_1hz.get('NR_SS_SINR', df_1hz.get('LTE_SINR', np.nan))
            df_1hz['SS_RSRQ'] = df_1hz.get('NR_SS_RSRQ', df_1hz.get('LTE_RSRQ', np.nan))
            df_1hz['CQI'] = df_1hz.get('NR_CQI', df_1hz.get('LTE_CQI', np.nan))
            df_1hz['DL_MCS'] = df_1hz.get('NR_DL_MCS', df_1hz.get('LTE_DL_MCS', np.nan))
            df_1hz['UL_MCS'] = df_1hz.get('NR_UL_MCS', df_1hz.get('LTE_UL_MCS', np.nan))
            df_1hz['PDSCH_BLER'] = df_1hz.get('NR_PDSCH_BLER', df_1hz.get('LTE_PDSCH_BLER', np.nan))
            df_1hz['PUSCH_BLER'] = df_1hz.get('NR_PUSCH_BLER', df_1hz.get('LTE_PUSCH_BLER', np.nan))
            df_1hz['PRB_Num_Inc0'] = df_1hz.get('NR_PRB_Inc0', df_1hz.get('LTE_PRB_Inc0', np.nan))
            df_1hz['WB_RI'] = df_1hz.get('NR_WB_RI', df_1hz.get('LTE_WB_RI', np.nan))
            df_1hz['QAM64_Rate'] = df_1hz.get('NR_QAM64_Rate', df_1hz.get('LTE_QAM64_Rate', np.nan))
            df_1hz['QAM256_Rate'] = df_1hz.get('NR_QAM256_Rate', df_1hz.get('LTE_QAM256_Rate', np.nan))
            df_1hz['UL_QAM64_Rate'] = df_1hz.get('NR_UL_QAM64_Rate', df_1hz.get('LTE_UL_QAM64_Rate', np.nan))
            df_1hz['UL_QAM256_Rate'] = df_1hz.get('NR_UL_QAM256_Rate', df_1hz.get('LTE_UL_QAM256_Rate', np.nan))

        # Determine DL Long Call vs Short Call vs UL Long/Short
        is_explicit_short = any(k in call_types_str for k in ['SHORT', '반복', 'REPEAT', 'REPEATED'])
        is_explicit_long = any(k in call_types_str for k in ['CONTINUOUS', 'LONG CALL', 'LONG_CALL', '연속'])

        if traffic_model in ['DL', 'DL_Long_Call', 'DL_Short_Call']:
            if is_explicit_short:
                traffic_model = 'DL_Short_Call'
            elif is_explicit_long:
                traffic_model = 'DL_Long_Call'
            elif call_intervals:
                durations = [(ci['end'] - ci['start']).total_seconds() for ci in call_intervals if 'start' in ci and 'end' in ci]
                med_dur = np.median(durations) if durations else 0
                if len(call_intervals) > 1 or med_dur < 90.0:
                    traffic_model = 'DL_Short_Call'
                else:
                    traffic_model = 'DL_Long_Call'
            else:
                traffic_model = 'DL_Long_Call'
        elif traffic_model in ['UL', 'UL_Long_Call', 'UL_Short_Call']:
            if is_explicit_short:
                traffic_model = 'UL_Short_Call'
            elif is_explicit_long:
                traffic_model = 'UL_Long_Call'
            elif call_intervals:
                durations = [(ci['end'] - ci['start']).total_seconds() for ci in call_intervals if 'start' in ci and 'end' in ci]
                med_dur = np.median(durations) if durations else 0
                if len(call_intervals) > 1 or med_dur < 90.0:
                    traffic_model = 'UL_Short_Call'
                else:
                    traffic_model = 'UL_Long_Call'
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

        # Fine-grained SST (SKT Speed Test) sub-phase assignment
        if traffic_model.startswith('SST'):
            c_ping_resp = '[Call & SKT Speed Test Call Info Ping Event Info Ping Response]'
            c_sst_ev = '[Call & SKT Speed Test Call Info SST Call Event]'
            c_dl_tput = '[Call & SKT Speed Test Call Info Download Event Info DL Throughput]'
            c_dl_res = '[Call & SKT Speed Test Call Info Download Event Info DL Throughput Result]'
            c_ul_tput = '[Call & SKT Speed Test Call Info Upload Event Info UL Throughput]'
            c_ul_res = '[Call & SKT Speed Test Call Info Upload Event Info UL Throughput Result]'

            m_ping = (df_1hz[c_ping_resp].notna() if c_ping_resp in df_1hz.columns else pd.Series(False, index=df_1hz.index)) | \
                     (df_1hz[c_sst_ev].astype(str).str.contains('Ping', case=False, na=False) if c_sst_ev in df_1hz.columns else pd.Series(False, index=df_1hz.index))
            m_dl = (df_1hz[c_dl_tput].notna() if c_dl_tput in df_1hz.columns else pd.Series(False, index=df_1hz.index)) | \
                   (df_1hz[c_dl_res].notna() if c_dl_res in df_1hz.columns else pd.Series(False, index=df_1hz.index)) | \
                   (df_1hz[c_sst_ev].astype(str).str.contains('Down', case=False, na=False) if c_sst_ev in df_1hz.columns else pd.Series(False, index=df_1hz.index))
            m_ul = (df_1hz[c_ul_tput].notna() if c_ul_tput in df_1hz.columns else pd.Series(False, index=df_1hz.index)) | \
                   (df_1hz[c_ul_res].notna() if c_ul_res in df_1hz.columns else pd.Series(False, index=df_1hz.index)) | \
                   (df_1hz[c_sst_ev].astype(str).str.contains('Up', case=False, na=False) if c_sst_ev in df_1hz.columns else pd.Series(False, index=df_1hz.index))

            df_1hz.loc[m_ping, 'Call_Phase'] = 'Ping_Traffic'
            df_1hz.loc[m_dl, 'Call_Phase'] = 'DL_Traffic'
            df_1hz.loc[m_ul, 'Call_Phase'] = 'UL_Traffic'

        # Ensure Standard RAT & HO_Status columns exist on Master Timeline
        has_nr = ('NR_SS_RSRP' in df_1hz.columns and not df_1hz['NR_SS_RSRP'].dropna().empty) or \
                 ('NR_Serving_PCI' in df_1hz.columns and (pd.to_numeric(df_1hz['NR_Serving_PCI'], errors='coerce') > 0).any())
        df_1hz['RAT'] = 'NR' if has_nr else 'LTE'

        if 'HO_Status' not in df_1hz.columns:
            df_1hz['HO_Status'] = ''
            pci_col = 'NR_Serving_PCI' if has_nr else 'LTE_Serving_PCI'
            if pci_col not in df_1hz.columns and 'pci' in df_1hz.columns:
                pci_col = 'pci'
            if pci_col in df_1hz.columns:
                s_p = pd.to_numeric(df_1hz[pci_col], errors='coerce')
                pci_changed = (s_p.diff() != 0) & (s_p.shift(1).notna()) & (s_p > 0)
                df_1hz.loc[pci_changed, 'HO_Status'] = 'Success'

            if 'L3_Signaling' in df_1hz.columns:
                l3_s = df_1hz['L3_Signaling'].astype(str).str.lower()
                m_meas = l3_s.str.contains('measurementreport|eventa3', na=False) & (df_1hz['HO_Status'] == '')
                df_1hz.loc[m_meas, 'HO_Status'] = 'MEAS_REPORT'
                m_fail = l3_s.str.contains('reestablishment|rlf|reject', na=False)
                df_1hz.loc[m_fail, 'HO_Status'] = 'Failure'

        # Register SSOT DataFrame attributes
        df_1hz.attrs['Network_Mode'] = net_mode
        df_1hz.attrs['Active_Vendor'] = vendor
        df_1hz.attrs['Traffic_Model'] = traffic_model
        df_1hz.attrs['Port_Key'] = port_key

        return df_1hz
