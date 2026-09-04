"""
===============================================================================
Module Name   : kpi_summary_engine.py
Location      : core/kpi_summary_engine.py
Module Role   : Dynamic Multi-Dimensional Scenario Summary Engine
                - Generates scenario-tailored sheets: 01_Total_Summary, 02_DL (or 02_Voice), 03_UL, 04_Ping
                - Incorporates LTE PCell eNB ID-Cell ID
                - Dynamically trims active SCells and appends them at the far right end
                - Accurately slices VoLTE AutoCall calls (Call 1 ~ Call N) using master events
===============================================================================
"""

import os
import re
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Tuple, Optional, Any, List
from core.canonical_registry import CanonicalColumnRegistry


def safe_read_csv(fpath: Optional[str]) -> Optional[pd.DataFrame]:
    if not fpath or not os.path.exists(fpath):
        return None
    try:
        return pd.read_csv(fpath, encoding='utf-8', low_memory=False, on_bad_lines='skip')
    except Exception:
        try:
            return pd.read_csv(fpath, encoding='cp949', low_memory=False, on_bad_lines='skip')
        except Exception:
            return None


class KPISummaryEngine:
    """
    Computes scenario-dedicated summary tables with clean, unpolluted schemas.
    """

    @classmethod
    def apply_1m_route_binning(cls, df: Optional[pd.DataFrame]) -> pd.DataFrame:
        """
        Applies Haversine 1.0m Route Binning to remove stopover/traffic light over-sampling.
        If GPS is missing or invalid, returns the input DataFrame without loss.
        """
        if df is None or df.empty or len(df) <= 1:
            return df if df is not None else pd.DataFrame()

        lon_cols = [c for c in df.columns if 'lon' in str(c).lower()]
        lat_cols = [c for c in df.columns if 'lat' in str(c).lower()]
        if not lon_cols or not lat_cols:
            return df

        lon_col, lat_col = lon_cols[0], lat_cols[0]
        s_lon = pd.to_numeric(df[lon_col], errors='coerce').ffill().bfill()
        s_lat = pd.to_numeric(df[lat_col], errors='coerce').ffill().bfill()

        if s_lon.isna().all() or s_lat.isna().all():
            return df

        lons = np.radians(s_lon.values)
        lats = np.radians(s_lat.values)

        bin_ids = np.zeros(len(lons), dtype=int)
        curr_bin = 0
        ref_lon, ref_lat = lons[0], lats[0]

        for i in range(1, len(lons)):
            dlat = lats[i] - ref_lat
            dlon = lons[i] - ref_lon
            a = np.sin(dlat / 2.0)**2 + np.cos(ref_lat) * np.cos(lats[i]) * np.sin(dlon / 2.0)**2
            c = 2.0 * np.arcsin(np.sqrt(min(1.0, max(0.0, a))))
            dist_m = 6371000.0 * c
            if dist_m >= 1.0:
                curr_bin += 1
                ref_lon, ref_lat = lons[i], lats[i]
            bin_ids[i] = curr_bin

        df_b = df.copy()
        df_b['_Route_Bin_ID'] = bin_ids

        # Compute numeric mean per Bin, and take mode/first for non-numeric/identifier
        numeric_cols = df_b.select_dtypes(include=[np.number]).columns.tolist()
        if '_Route_Bin_ID' in numeric_cols:
            numeric_cols.remove('_Route_Bin_ID')

        df_binned = df_b.groupby('_Route_Bin_ID')[numeric_cols].mean().reset_index(drop=True)
        return df_binned

    @classmethod
    def build_pci_summaries_dl_ul(
        cls,
        df_qc_kpi: Optional[pd.DataFrame],
        mode: str = 'NSA',
        df_timeline: Optional[pd.DataFrame] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Builds rich, distinct PCI Summary sheets for DL and UL separately.
        Does NOT build PCI summary for pure Ping or pure Voice logs.
        """
        if df_qc_kpi is None or df_qc_kpi.empty:
            return {}

        results = {}
        pci_col = 'Call & 5G KPI PCell RF Serving PCI' if mode != 'LTE' else 'Call & LTE KPI PCell Serving PCI'
        actual_pci_col = CanonicalColumnRegistry.get_actual_column(df_qc_kpi, pci_col)
        if not actual_pci_col or actual_pci_col not in df_qc_kpi.columns:
            return {}

        s_pci = pd.to_numeric(df_qc_kpi[actual_pci_col], errors='coerce').dropna()
        if s_pci.empty:
            return {}

        # 1. Check if DL / UL traffic exists in this dataset
        dl_app_col = CanonicalColumnRegistry.get_actual_column(df_qc_kpi, 'Call & Speed Test T-put Current App Throughput [Mbps]')
        if not dl_app_col:
            dl_app_col = CanonicalColumnRegistry.get_actual_column(df_qc_kpi, 'Call & APP Throughput Info(All Data) All FWD  Throughput')
        has_dl = dl_app_col is not None or ('5g' in mode.lower() or 'nsa' in mode.lower() or 'dl' in mode.lower())

        ul_app_col = CanonicalColumnRegistry.get_actual_column(df_qc_kpi, 'Call & APP Throughput Info(All Data) All RVS Throughput')
        has_ul = ul_app_col is not None and not pd.to_numeric(df_qc_kpi[ul_app_col], errors='coerce').dropna().empty

        df_dl_kpi = df_qc_kpi
        df_ul_kpi = df_qc_kpi

        if df_timeline is not None and not df_timeline.empty and 'TIME_STAMP' in df_qc_kpi.columns:
            s_dt = pd.to_datetime(df_qc_kpi['TIME_STAMP'], errors='coerce')
            
            # Check for Call_Phase (from MasterTimelineParser) or Service_Type
            if 'Call_Phase' in df_timeline.columns:
                dl_times = df_timeline[df_timeline['Call_Phase'] == 'DL_Traffic']['TIME_STAMP'].dropna()
                if not dl_times.empty:
                    t_min, t_max = pd.to_datetime(dl_times.min()), pd.to_datetime(dl_times.max())
                    df_dl_kpi = df_qc_kpi[(s_dt >= t_min) & (s_dt <= t_max)]
                    has_dl = not df_dl_kpi.empty

                ul_times = df_timeline[df_timeline['Call_Phase'] == 'UL_Traffic']['TIME_STAMP'].dropna()
                if not ul_times.empty:
                    t_min, t_max = pd.to_datetime(ul_times.min()), pd.to_datetime(ul_times.max())
                    df_ul_kpi = df_qc_kpi[(s_dt >= t_min) & (s_dt <= t_max)]
                    has_ul = not df_ul_kpi.empty
                else:
                    has_ul = False
            elif 'Service_Type' in df_timeline.columns:
                dl_spans = df_timeline[df_timeline['Service_Type'].str.contains('DL', case=False, na=False)]
                if not dl_spans.empty:
                    dl_masks = []
                    for _, row in dl_spans.iterrows():
                        t_s = pd.to_datetime(row.get('Start_Time'))
                        t_e = pd.to_datetime(row.get('End_Time'))
                        if pd.notna(t_s) and pd.notna(t_e):
                            dl_masks.append((s_dt >= t_s) & (s_dt <= t_e))
                    if dl_masks:
                        combined_mask = np.logical_or.reduce(dl_masks)
                        df_dl_kpi = df_qc_kpi[combined_mask]
                        has_dl = not df_dl_kpi.empty

                ul_spans = df_timeline[df_timeline['Service_Type'].str.contains('UL', case=False, na=False)]
                if not ul_spans.empty:
                    ul_masks = []
                    for _, row in ul_spans.iterrows():
                        t_s = pd.to_datetime(row.get('Start_Time'))
                        t_e = pd.to_datetime(row.get('End_Time'))
                        if pd.notna(t_s) and pd.notna(t_e):
                            ul_masks.append((s_dt >= t_s) & (s_dt <= t_e))
                    if ul_masks:
                        combined_mask = np.logical_or.reduce(ul_masks)
                        df_ul_kpi = df_qc_kpi[combined_mask]
                        has_ul = not df_ul_kpi.empty
                else:
                    has_ul = False

        # --- BUILD PCI_Summary_DL ---
        if has_dl and not df_dl_kpi.empty and actual_pci_col in df_dl_kpi.columns:
            valid_pci_df = df_dl_kpi.dropna(subset=[actual_pci_col])
            if not valid_pci_df.empty:
                dl_groups = valid_pci_df.groupby(valid_pci_df[actual_pci_col].astype(int))
                tot_samples = len(valid_pci_df)
                dl_rows = []
                for pci_val, grp in dl_groups:
                    cnt = len(grp)
                    ratio = round((cnt / tot_samples) * 100.0, 1) if tot_samples > 0 else 0.0
                    if mode == 'LTE':
                        dl_rows.append({
                            'PCI': pci_val,
                            'Count': cnt,
                            '점유율 (%)': ratio,
                            'LTE PDCP DL (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PDCP DL Throughput [Mbps]'), 2),
                            'LTE MAC Total (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI MAC DL Throughput [Mbps]'), 2),
                            'LTE RSRP (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                            'LTE RSRQ (dB)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell Serving RSRQ [dB]'), 1),
                            'LTE RSSI (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell Serving RSSI [dBm]'), 1),
                            'LTE SINR (dB)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell SINR [dB]'), 1),
                            'LTE WB CQI': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell WB CQI CW0'), 1),
                            'LTE DL MCS': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell DL MCS0'), 1),
                            'LTE PDSCH BLER (%)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2),
                            'LTE PRB Num (avg)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI Pcell PDSCH PRB Number(Avg)'), 1),
                            'LTE RI (Avg)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell WB RI'), 1),
                        })
                    else:
                        dl_rows.append({
                            'PCI': pci_val,
                            'Count': cnt,
                            '점유율 (%)': ratio,
                            '5G NR PDCP DL (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]'), 2),
                            '5G NR MAC DL (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]'), 2),
                            '5G MAC T-put per RB (kbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & Qualcomm 5G-NR UL/DL Info Summary(In-Traffic) PCell MAC Throughput per RB DL MAC Throughput Per RB [kbps]'), 2),
                            '5G SS-RSRP (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]'), 1),
                            '5G SS-RSRQ (dB)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF Serving SS-RSRQ [dB]'), 1),
                            '5G SS-SINR (dB)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]'), 1),
                            '5G CQI': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF CQI'), 1),
                            '5G DL MCS': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Layer1 DL MCS (Avg)'), 1),
                            '5G PDSCH BLER (%)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Physical PDSCH BLER [%]'), 2),
                            '5G PRB Num (avg)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Physical PDSCH RB Num (AVG)'), 1),
                            '5G DL Layer Num': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Physical DL Layer Num'), 1),
                            '5G RI (Avg)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF RI(Avg)'), 1),
                        })
                if dl_rows:
                    results['PCI_Summary_DL'] = pd.DataFrame(dl_rows).sort_values('Count', ascending=False).reset_index(drop=True)

        # --- BUILD PCI_Summary_UL ---
        if has_ul and not df_ul_kpi.empty and actual_pci_col in df_ul_kpi.columns:
            valid_pci_ul = df_ul_kpi.dropna(subset=[actual_pci_col])
            if not valid_pci_ul.empty:
                ul_groups = valid_pci_ul.groupby(valid_pci_ul[actual_pci_col].astype(int))
                tot_samples = len(valid_pci_ul)
                ul_rows = []
                for pci_val, grp in ul_groups:
                    cnt = len(grp)
                    ratio = round((cnt / tot_samples) * 100.0, 1) if tot_samples > 0 else 0.0
                    if mode == 'LTE':
                        ul_rows.append({
                            'PCI': pci_val,
                            'Count': cnt,
                            '점유율 (%)': ratio,
                            'LTE PDCP UL (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PDCP UL Throughput [Mbps]'), 2),
                            'LTE MAC Total (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell MAC UL Throughput [Mbps]'), 2),
                            'LTE RSRP (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                            'LTE SINR (dB)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell SINR [dB]'), 1),
                            'LTE UL MCS': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell UL MCS'), 1),
                            'LTE PUSCH BLER (%)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell PUSCH BLER [%]'), 2),
                            'LTE PRB Num (avg)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell PUSCH PRB Number(Avg)'), 1),
                            'LTE PUSCH Power (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell PUSCH Power [dBm]'), 1),
                            'LTE SRS Power (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell SRS Power [dBm]'), 1),
                            'LTE Total Tx Power (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & LTE KPI PCell Total Tx Power [dBm]'), 1),
                        })
                    else:
                        ul_rows.append({
                            'PCI': pci_val,
                            'Count': cnt,
                            '점유율 (%)': ratio,
                            '5G NR PDCP UL (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]'), 2),
                            '5G NR MAC UL (Mbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI Total Info Layer2 MAC UL Throughput [Mbps]'), 2),
                            '5G MAC T-put per RB UL (kbps)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & Qualcomm 5G-NR UL/DL Info Summary(In-Traffic) PCell MAC Throughput per RB UL MAC Throughput Per RB [kbps]'), 2),
                            '5G SS-RSRP (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]'), 1),
                            '5G SS-SINR (dB)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]'), 1),
                            '5G UL MCS': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Layer1 UL MCS (Avg)'), 1),
                            '5G PUSCH BLER (%)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Layer1 UL BLER [%]'), 2),
                            '5G NR UL RB Num (avg)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell Layer1 UL RB Num (Avg)'), 1),
                            '5G PUSCH Power (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF PUSCH Power [dBm]'), 1),
                            '5G PUCCH Power (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF PUCCH Power [dBm]'), 1),
                            '5G SRS Power (dBm)': round(CanonicalColumnRegistry.get_numeric_mean(grp, 'Call & 5G KPI PCell RF SRS Power [dBm]'), 1),
                        })
                if ul_rows:
                    results['PCI_Summary_UL'] = pd.DataFrame(ul_rows).sort_values('Count', ascending=False).reset_index(drop=True)

        return results

    @classmethod
    def build_scenario_dedicated_summaries(
        cls,
        drm_name: str,
        csvs: Dict[str, Optional[str]],
        df_timeline: Optional[pd.DataFrame],
        df_qc_kpi: Optional[pd.DataFrame],
        detected_state: dict
    ) -> Dict[str, pd.DataFrame]:
        df_smart_phone = safe_read_csv(csvs.get('SMART_PHONE')) if csvs else None
        df_event_detail = safe_read_csv(csvs.get('EVENT_DETAIL')) if csvs else None
        df_rtp = safe_read_csv(csvs.get('RTP')) if csvs else None
        mode = detected_state.get('Network_Mode', 'NSA')
        vendor = detected_state.get('Active_Vendor', 'COMMON')

        def find_col(df: Optional[pd.DataFrame], keywords: List[str], rat: Optional[str] = None) -> Optional[str]:
            if df is None or df.empty:
                return None
            for kw in keywords:
                for c in df.columns:
                    c_str = str(c)
                    c_low = c_str.lower()
                    if kw.lower() in c_low and '(mode)' not in c_low:
                        if rat == '5G':
                            if '5g' in c_low or 'nr' in c_low:
                                return c
                        elif rat == 'LTE':
                            if 'lte' in c_low or 'eutra' in c_low:
                                return c
                        else:
                            return c
            # Fallback without RAT filter
            for kw in keywords:
                for c in df.columns:
                    if kw.lower() in str(c).lower():
                        return c
            return None

        # Pre-process Timestamps for Sub-Window Dominant Cell Extraction
        s_sp_dt = pd.to_datetime(df_smart_phone['TIME_STAMP'], errors='coerce') if (df_smart_phone is not None and not df_smart_phone.empty and 'TIME_STAMP' in df_smart_phone.columns) else pd.Series(dtype='datetime64[ns]')
        s_kpi_dt = pd.to_datetime(df_qc_kpi['TIME_STAMP'], errors='coerce') if (df_qc_kpi is not None and not df_qc_kpi.empty and 'TIME_STAMP' in df_qc_kpi.columns) else pd.Series(dtype='datetime64[ns]')
        s_rtp_dt = pd.to_datetime(df_rtp['TIME_STAMP'], errors='coerce') if (df_rtp is not None and not df_rtp.empty and 'TIME_STAMP' in df_rtp.columns) else pd.Series(dtype='datetime64[ns]')

        def get_dominant_cell_info(t_start, t_end) -> Tuple[Any, Any, Any, Any, Any]:
            sub_sp = df_smart_phone[(s_sp_dt >= t_start) & (s_sp_dt <= t_end)] if not s_sp_dt.empty else pd.DataFrame()
            sub_kpi = df_qc_kpi[(s_kpi_dt >= t_start) & (s_kpi_dt <= t_end)] if not s_kpi_dt.empty else pd.DataFrame()

            enb_m, sec_m, tac_m, pci_m, enb_cell_str = np.nan, np.nan, np.nan, np.nan, np.nan

            target_sp = sub_sp if not sub_sp.empty else (df_smart_phone if (df_smart_phone is not None and not df_smart_phone.empty) else pd.DataFrame())

            if not target_sp.empty:
                s_enb = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, '[Call & Smart Phone Android LTE Parameter Info eNB ID]'), errors='coerce').dropna()
                if s_enb.empty:
                    s_enb = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, 'LTE Parameter Info eNB ID'), errors='coerce').dropna()

                s_cid = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, '[Call & Smart Phone Android LTE Parameter Info Cell ID]'), errors='coerce').dropna()
                if s_cid.empty:
                    s_cid = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, 'LTE Parameter Info Cell ID'), errors='coerce').dropna()

                s_tac = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, '[Call & Smart Phone Android LTE Parameter Info TAC]'), errors='coerce').dropna()
                if s_tac.empty:
                    s_tac = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, 'LTE Parameter Info TAC'), errors='coerce').dropna()

                s_pci_5g = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, '[Call & Smart Phone Android 5G-NR Parameter Info PCI]'), errors='coerce').dropna()
                if s_pci_5g.empty:
                    s_pci_5g = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, '5G-NR Parameter Info PCI'), errors='coerce').dropna()

                s_pci_lte = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, '[Call & Smart Phone Android LTE Parameter Info PCI]'), errors='coerce').dropna()
                if s_pci_lte.empty:
                    s_pci_lte = pd.to_numeric(CanonicalColumnRegistry.get_series(target_sp, 'LTE Parameter Info PCI'), errors='coerce').dropna()

                if not s_enb.empty:
                    enb_m = int(s_enb.mode().iloc[0])
                if not s_cid.empty:
                    sec_m = int(s_cid.mode().iloc[0])

                if pd.notna(enb_m) and pd.notna(sec_m):
                    if sec_m >= 256:
                        enb_cell_str = f"{sec_m // 256}-{sec_m % 256}"
                    else:
                        enb_cell_str = f"{enb_m}-{sec_m}"
                elif pd.notna(sec_m):
                    enb_cell_str = f"{sec_m // 256}-{sec_m % 256}" if sec_m >= 256 else f"{sec_m}"

                if not s_tac.empty:
                    tac_m = int(s_tac.mode().iloc[0])
                if not s_pci_5g.empty and mode != 'LTE':
                    pci_m = int(s_pci_5g.mode().iloc[0])
                elif not s_pci_lte.empty:
                    pci_m = int(s_pci_lte.mode().iloc[0])

            if pd.isna(pci_m) and not sub_kpi.empty:
                s_pci_kpi = pd.to_numeric(CanonicalColumnRegistry.get_series(sub_kpi, 'Call & 5G KPI PCell RF Serving PCI' if mode != 'LTE' else 'Call & LTE KPI PCell Serving PCI'), errors='coerce').dropna()
                if not s_pci_kpi.empty:
                    pci_m = int(s_pci_kpi.mode().iloc[0])

            return enb_cell_str, enb_m, sec_m, tac_m, pci_m

        # ---------------------------------------------------------------------
        # 1. Detect Active SCell Carriers in this Log (for dynamic trimming)
        # ---------------------------------------------------------------------
        active_lte_scells = []
        if df_qc_kpi is not None and not df_qc_kpi.empty:
            for s_idx in range(1, 5):
                s_rsrp = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, f'Call & LTE KPI SCell[{s_idx}] Serving RSRP [dBm]'), errors='coerce').dropna()
                s_tput = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, f'Call & LTE KPI SCell[{s_idx}] PDSCH Throughput [Mbps]'), errors='coerce').dropna()
                if not s_rsrp.empty or (not s_tput.empty and s_tput.max() > 0):
                    active_lte_scells.append(s_idx)

        has_nr_scell = False
        if df_qc_kpi is not None and not df_qc_kpi.empty:
            s_nr_scell = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & 5G KPI SCell[1] Serving SS-RSRP [dBm]'), errors='coerce').dropna()
            if not s_nr_scell.empty:
                has_nr_scell = True

        def get_col_val(df: Optional[pd.DataFrame], col_name: str) -> float:
            return CanonicalColumnRegistry.get_numeric_mean(df, col_name)

        # ---------------------------------------------------------------------
        # 2. SST & Call Segments Analysis
        # ---------------------------------------------------------------------
        is_sst = False
        if df_qc_kpi is not None and not df_qc_kpi.empty:
            p_res_check = CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Ping Event Info Ping Throughput Result').dropna()
            d_res_check = CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Download Event Info DL Throughput Result').dropna()
            if not p_res_check.empty or not d_res_check.empty:
                is_sst = True

        dl_rows, ul_rows, ping_rows, voice_rows = [], [], [], []

        if is_sst:
            # SST: Use raw time-series KPI directly without Binning
            p_res_s = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Ping Event Info Ping Throughput Result'), errors='coerce')
            d_res_s = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Download Event Info DL Throughput Result'), errors='coerce')
            u_res_s = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Upload Event Info UL Throughput Result'), errors='coerce')

            p_res_list = p_res_s.dropna().reset_index(drop=True)
            d_res_list = d_res_s.dropna().reset_index(drop=True)
            u_res_list = u_res_s.dropna().reset_index(drop=True)

            p_raw_s = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Ping Event Info Ping Response'), errors='coerce')
            d_raw_s = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Download Event Info DL Throughput'), errors='coerce')
            u_raw_s = pd.to_numeric(CanonicalColumnRegistry.get_series(df_qc_kpi, 'Call & SKT Speed Test Call Info Upload Event Info UL Throughput'), errors='coerce')

            ts_s = df_qc_kpi['TIME_STAMP'] if (df_qc_kpi is not None and 'TIME_STAMP' in df_qc_kpi.columns) else pd.Series(dtype=object)

            p_raw_df = pd.DataFrame({'TIME_STAMP': ts_s, 'val': p_raw_s}).dropna().reset_index(drop=True) if not p_raw_s.dropna().empty else pd.DataFrame()
            d_raw_df = pd.DataFrame({'TIME_STAMP': ts_s, 'val': d_raw_s}).dropna().reset_index(drop=True) if not d_raw_s.dropna().empty else pd.DataFrame()
            u_raw_df = pd.DataFrame({'TIME_STAMP': ts_s, 'val': u_raw_s}).dropna().reset_index(drop=True) if not u_raw_s.dropna().empty else pd.DataFrame()

            n_calls = max(len(p_res_list), len(d_res_list), len(u_res_list))

            for i in range(n_calls):
                p_val = p_res_list.iloc[i] if i < len(p_res_list) else np.nan
                d_val = d_res_list.iloc[i] if i < len(d_res_list) else np.nan
                u_val = u_res_list.iloc[i] if i < len(u_res_list) else np.nan

                # Ping Window
                p_start_idx = i * 50
                p_end_idx = min(p_start_idx + 50, len(p_raw_df))
                p_kpi = pd.DataFrame()
                p_enb_cell, p_enb, p_sec, p_tac, p_pci = np.nan, np.nan, np.nan, np.nan, np.nan
                if not p_raw_df.empty and p_start_idx < len(p_raw_df) and df_qc_kpi is not None:
                    p_ts_s = pd.to_datetime(p_raw_df['TIME_STAMP'].iloc[p_start_idx])
                    p_ts_e = pd.to_datetime(p_raw_df['TIME_STAMP'].iloc[p_end_idx - 1])
                    p_kpi = df_qc_kpi[(s_kpi_dt >= p_ts_s) & (s_kpi_dt <= p_ts_e)]
                    p_enb_cell, p_enb, p_sec, p_tac, p_pci = get_dominant_cell_info(p_ts_s, p_ts_e)

                # DL Window
                d_start_idx = i * 16
                d_end_idx = min(d_start_idx + 16, len(d_raw_df))
                d_kpi = pd.DataFrame()
                d_enb_cell, d_enb, d_sec, d_tac, d_pci = np.nan, np.nan, np.nan, np.nan, np.nan
                if not d_raw_df.empty and d_start_idx < len(d_raw_df) and df_qc_kpi is not None:
                    d_ts_s = pd.to_datetime(d_raw_df['TIME_STAMP'].iloc[d_start_idx])
                    d_ts_e = pd.to_datetime(d_raw_df['TIME_STAMP'].iloc[d_end_idx - 1])
                    d_kpi = df_qc_kpi[(s_kpi_dt >= d_ts_s) & (s_kpi_dt <= d_ts_e)]
                    d_enb_cell, d_enb, d_sec, d_tac, d_pci = get_dominant_cell_info(d_ts_s, d_ts_e)

                # UL Window
                u_start_idx = i * 16
                u_end_idx = min(u_start_idx + 16, len(u_raw_df))
                u_kpi = pd.DataFrame()
                u_enb_cell, u_enb, u_sec, u_tac, u_pci = np.nan, np.nan, np.nan, np.nan, np.nan
                if not u_raw_df.empty and u_start_idx < len(u_raw_df) and df_qc_kpi is not None:
                    u_ts_s = pd.to_datetime(u_raw_df['TIME_STAMP'].iloc[u_start_idx])
                    u_ts_e = pd.to_datetime(u_raw_df['TIME_STAMP'].iloc[u_end_idx - 1])
                    u_kpi = df_qc_kpi[(s_kpi_dt >= u_ts_s) & (s_kpi_dt <= u_ts_e)]
                    u_enb_cell, u_enb, u_sec, u_tac, u_pci = get_dominant_cell_info(u_ts_s, u_ts_e)

                # Dynamic 망 모드 판정
                call_5g_ratio = get_col_val(d_kpi, 'Call & 5G KPI Total Info 5G Duration Ratio [%]')
                call_mode_dl = mode
                if mode == 'NSA' and pd.notna(call_5g_ratio) and call_5g_ratio < 95.0 and call_5g_ratio > 0.0:
                    call_mode_dl = 'NSA (LTE Fallback)'

                # -------------------------------------------------------------
                # Build Master DL Row (02_DL) - Drop lat/lon/5G-ratio/RLC/PDSCH-SINR
                # -------------------------------------------------------------
                if pd.notna(d_val) or not d_kpi.empty:
                    ts_range = f"{d_ts_s.strftime('%H:%M:%S')} ~ {d_ts_e.strftime('%H:%M:%S')}" if not d_kpi.empty else "N/A"
                    app_dl_res = round(d_val, 2) if pd.notna(d_val) else round(get_col_val(d_kpi, 'Call & Speed Test T-put Current App Throughput [Mbps]'), 2)
                    if pd.isna(app_dl_res):
                        raw_app = get_col_val(d_kpi, 'Call & APP Throughput Info(All Data) All FWD  Throughput (kbps)')
                        if pd.isna(raw_app):
                            raw_app = get_col_val(d_kpi, 'Call & APP Throughput Info(All Data) All FWD  Throughput')
                        app_dl_res = round(raw_app / 1000.0, 2) if pd.notna(raw_app) else np.nan

                    gps_spd = round(get_col_val(d_kpi, 'Call & GPS Speed (km/h)'), 1)
                    if pd.isna(gps_spd):
                        gps_spd = round(get_col_val(d_kpi, 'GPS Speed (km/h)'), 1)

                    if mode == 'LTE':
                        # Pure LTE
                        row_dl = {
                            '호 번호': f"Call {i + 1}",
                            '시간 구간': ts_range,
                            '시나리오': 'LTE SST (DL)',
                            '망 모드': 'LTE',
                            '호 상태': 'Success' if pd.notna(d_val) else 'Fail',
                            'App DL 속도 (Mbps)': app_dl_res,
                            'GPS 속도 (km/h)': gps_spd,
                            'LTE PDCP DL (Mbps)': round(get_col_val(d_kpi, 'Call & LTE KPI PDCP DL Throughput [Mbps]'), 2),
                            'LTE MAC Total (Mbps)': round(get_col_val(d_kpi, 'Call & LTE KPI MAC DL Throughput [Mbps]'), 2),
                            'LTE PCell eNB-Cell ID': d_enb_cell,
                            'LTE PCell PCI': d_pci,
                            'LTE PCell TAC': d_tac,
                            'LTE PCell EARFCN': get_col_val(d_kpi, 'Call & LTE KPI PCell Serving EARFCN(DL)'),
                            'LTE PCell BandWidth (MHz)': get_col_val(d_kpi, 'Call & LTE KPI PCell Serving BandWidth(DL)'),
                            'LTE PCell RSRP (dBm)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                            'LTE PCell RSRQ (dB)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell Serving RSRQ [dB]'), 1),
                            'LTE PCell RSSI (dBm)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell Serving RSSI [dBm]'), 1),
                            'LTE PCell SINR (dB)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell SINR [dB]'), 1),
                            'LTE PCell WB CQI': round(get_col_val(d_kpi, 'Call & LTE KPI PCell WB CQI CW0'), 1),
                            'LTE PCell DL MCS': round(get_col_val(d_kpi, 'Call & LTE KPI PCell DL MCS0'), 1),
                            'LTE PCell PDSCH BLER (%)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2),
                            'LTE PCell PRB Num (avg)': round(get_col_val(d_kpi, 'Call & LTE KPI Pcell PDSCH PRB Number(Avg)'), 1),
                            'LTE PCell PRB Num (inc0)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell PDSCH PRB Number(Including 0)'), 1),
                            'LTE PCell RI (Avg)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell WB RI'), 1),
                        }
                        for s_idx in active_lte_scells:
                            row_dl[f'LTE SCell[{s_idx}] EARFCN'] = get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] Serving EARFCN(DL)')
                            row_dl[f'LTE SCell[{s_idx}] BW (MHz)'] = get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] Serving BandWidth(DL)')
                            row_dl[f'LTE SCell[{s_idx}] RSRP (dBm)'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] Serving RSRP [dBm]'), 1)
                            row_dl[f'LTE SCell[{s_idx}] RSRQ (dB)'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] Serving RSRQ [dB]'), 1)
                            row_dl[f'LTE SCell[{s_idx}] SINR (dB)'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] Serving SINR [dB]'), 1)
                            row_dl[f'LTE SCell[{s_idx}] DL MCS'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] DL MCS0'), 1)
                            row_dl[f'LTE SCell[{s_idx}] BLER (%)'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] PDSCH BLER [%]'), 2)
                            row_dl[f'LTE SCell[{s_idx}] PRB Num (avg)'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] PDSCH PRB Number(Avg)'), 1)
                            row_dl[f'LTE SCell[{s_idx}] T-put (Mbps)'] = round(get_col_val(d_kpi, f'Call & LTE KPI SCell[{s_idx}] PDSCH Throughput [Mbps]'), 2)
                    else:
                        # NSA / SA Mode
                        mac_per_rb_dl = get_col_val(d_kpi, 'Call & Qualcomm 5G-NR UL/DL Info Summary(In-Traffic) PCell MAC Throughput per RB DL MAC Throughput Per RB [kbps]')
                        if pd.isna(mac_per_rb_dl):
                            mac_per_rb_dl = get_col_val(d_kpi, 'DL MAC Throughput Per RB')

                        row_dl = {
                            '호 번호': f"Call {i + 1}",
                            '시간 구간': ts_range,
                            '시나리오': '5G SST (DL)',
                            '망 모드': call_mode_dl,
                            '호 상태': 'Success' if pd.notna(d_val) else 'Fail',
                            'App DL 속도 (Mbps)': app_dl_res,
                            'GPS 속도 (km/h)': gps_spd,
                            '5G NR PDCP (+Split) (Mbps)': round(get_col_val(d_kpi, 'Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]'), 2),
                            '5G NR MAC Total (Mbps)': round(get_col_val(d_kpi, 'Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]'), 2),
                            '5G MAC T-put per RB (kbps)': round(mac_per_rb_dl, 2) if pd.notna(mac_per_rb_dl) else np.nan,
                            '5G PSCell PCI': d_pci,
                            '5G PSCell ARFCN': get_col_val(d_kpi, 'Call & 5G KPI PCell RF NR-ARFCN'),
                            '5G PSCell SSB Index (Avg)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell RF Serving SSB Idx'), 1),
                            '5G SS-RSRP (dBm)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]'), 1),
                            '5G SS-RSRQ (dB)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell RF Serving SS-RSRQ [dB]'), 1),
                            '5G SS-SINR (dB)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]'), 1),
                            '5G PSCell CQI': round(get_col_val(d_kpi, 'Call & 5G KPI PCell RF CQI'), 1),
                            '5G DL MCS': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL MCS (Avg)'), 1),
                            '5G PDSCH BLER (%)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL BLER [%]'), 2),
                            '5G NR RB (avg)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL RB Num (Avg)'), 1),
                            '5G NR RB (inc0)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL RB Num (Including 0)'), 1),
                            '5G DL Layer Num': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL Layer Num (Avg)'), 1),
                            '5G RI (Avg)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell RF RI(Avg)'), 1),
                            '5G QPSK (%)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL QPSK Rate [%]'), 1),
                            '5G 16QAM (%)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 16QAM Rate [%]'), 1),
                            '5G 64QAM (%)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]'), 1),
                            '5G 256QAM (%)': round(get_col_val(d_kpi, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]'), 1),
                            'LTE PCell eNB-Cell ID': d_enb_cell,
                            'LTE PCell PCI': get_col_val(d_kpi, 'Call & LTE KPI PCell Serving PCI'),
                            'LTE PCell TAC': d_tac,
                            'LTE PCell EARFCN': get_col_val(d_kpi, 'Call & LTE KPI PCell Serving EARFCN(DL)'),
                            'LTE PCell BandWidth (MHz)': get_col_val(d_kpi, 'Call & LTE KPI PCell Serving BandWidth(DL)'),
                            'LTE PCell RSRP (dBm)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                            'LTE PCell SINR (dB)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell SINR [dB]'), 1),
                            'LTE PCell DL MCS': round(get_col_val(d_kpi, 'Call & LTE KPI PCell DL MCS0'), 1),
                            'LTE PCell PDSCH BLER (%)': round(get_col_val(d_kpi, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2),
                            'LTE PCell PRB Num (avg)': round(get_col_val(d_kpi, 'Call & LTE KPI Pcell PDSCH PRB Number(Avg)'), 1),
                        }
                        if has_nr_scell:
                            row_dl['5G SCell[1] ARFCN'] = get_col_val(d_kpi, 'Call & 5G KPI SCell[1] Serving ARFCN')
                            row_dl['5G SCell[1] SS-RSRP (dBm)'] = round(get_col_val(d_kpi, 'Call & 5G KPI SCell[1] Serving SS-RSRP [dBm]'), 1)
                            row_dl['5G SCell[1] SS-SINR (dB)'] = round(get_col_val(d_kpi, 'Call & 5G KPI SCell[1] Serving SS-SINR [dB]'), 1)
                            row_dl['5G SCell[1] T-put (Mbps)'] = round(get_col_val(d_kpi, 'Call & 5G KPI SCell[1] Throughput [Mbps]'), 2)

                    dl_rows.append(row_dl)

                # -------------------------------------------------------------
                # Build Master UL Row (03_UL) - Drop lat/lon/5G-ratio/RLC
                # -------------------------------------------------------------
                if pd.notna(u_val) or not u_kpi.empty:
                    ts_range = f"{u_ts_s.strftime('%H:%M:%S')} ~ {u_ts_e.strftime('%H:%M:%S')}" if not u_kpi.empty else "N/A"
                    app_ul_res = round(u_val, 2) if pd.notna(u_val) else round(get_col_val(u_kpi, 'Call & Speed Test T-put Current App Throughput [Mbps]'), 2)
                    if pd.isna(app_ul_res):
                        raw_app = get_col_val(u_kpi, 'Call & APP Throughput Info(All Data) All RVS Throughput (kbps)')
                        if pd.isna(raw_app):
                            raw_app = get_col_val(u_kpi, 'Call & APP Throughput Info(All Data) All RVS Throughput')
                        app_ul_res = round(raw_app / 1000.0, 2) if pd.notna(raw_app) else np.nan

                    gps_spd = round(get_col_val(u_kpi, 'Call & GPS Speed (km/h)'), 1)
                    if pd.isna(gps_spd):
                        gps_spd = round(get_col_val(u_kpi, 'GPS Speed (km/h)'), 1)

                    if mode == 'LTE':
                        row_ul = {
                            '호 번호': f"Call {i + 1}",
                            '시간 구간': ts_range,
                            '시나리오': 'LTE SST (UL)',
                            '망 모드': 'LTE',
                            '호 상태': 'Success' if pd.notna(u_val) else 'Fail',
                            'App UL 속도 (Mbps)': app_ul_res,
                            'GPS 속도 (km/h)': gps_spd,
                            'LTE PDCP UL (Mbps)': round(get_col_val(u_kpi, 'Call & LTE KPI PDCP UL Throughput [Mbps]'), 2),
                            'LTE MAC UL Total (Mbps)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell MAC UL Throughput [Mbps]'), 2),
                            'LTE PCell eNB-Cell ID': u_enb_cell,
                            'LTE PCell PCI': u_pci,
                            'LTE PCell TAC': u_tac,
                            'LTE PCell EARFCN': get_col_val(u_kpi, 'Call & LTE KPI PCell Serving EARFCN(UL)'),
                            'LTE PCell RSRP (dBm)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                            'LTE PCell SINR (dB)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell SINR [dB]'), 1),
                            'LTE PCell UL MCS': round(get_col_val(u_kpi, 'Call & LTE KPI PCell UL MCS'), 1),
                            'LTE PCell PUSCH BLER (%)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell PUSCH BLER [%]'), 2),
                            'LTE PCell PUSCH PRB Num (avg)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell PUSCH PRB Number(Avg)'), 1),
                            'LTE PCell PUSCH Power (dBm)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell PUSCH Power [dBm]'), 1),
                            'LTE PCell SRS Power (dBm)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell SRS Power [dBm]'), 1),
                            'LTE PCell Total Tx Power (dBm)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell Total Tx Power [dBm]'), 1),
                        }
                        for s_idx in active_lte_scells:
                            row_ul[f'LTE SCell[{s_idx}] PUSCH T-put (Mbps)'] = round(get_col_val(u_kpi, f'Call & LTE KPI SCell[{s_idx}] PUSCH Throughput [Mbps]'), 2)
                    else:
                        mac_per_rb_ul = get_col_val(u_kpi, 'Call & Qualcomm 5G-NR UL/DL Info Summary(In-Traffic) PCell MAC Throughput per RB UL MAC Throughput Per RB [kbps]')
                        if pd.isna(mac_per_rb_ul):
                            mac_per_rb_ul = get_col_val(u_kpi, 'UL MAC Throughput Per RB')

                        srs_pwr = get_col_val(u_kpi, 'Call & 5G KPI PCell RF SRS Power [dBm]')
                        if pd.isna(srs_pwr):
                            srs_pwr = get_col_val(u_kpi, 'Call & 5G KPI PCell RF SRS Tx Power [dBm]')

                        row_ul = {
                            '호 번호': f"Call {i + 1}",
                            '시간 구간': ts_range,
                            '시나리오': '5G SST (UL)',
                            '망 모드': mode,
                            '호 상태': 'Success' if pd.notna(u_val) else 'Fail',
                            'App UL 속도 (Mbps)': app_ul_res,
                            'GPS 속도 (km/h)': gps_spd,
                            '5G NR PDCP UL (Mbps)': round(get_col_val(u_kpi, 'Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]'), 2),
                            '5G NR MAC UL (Mbps)': round(get_col_val(u_kpi, 'Call & 5G KPI Total Info Layer2 MAC UL Throughput [Mbps]'), 2),
                            '5G MAC T-put per RB UL (kbps)': round(mac_per_rb_ul, 2) if pd.notna(mac_per_rb_ul) else np.nan,
                            '5G PSCell PCI': u_pci,
                            '5G PSCell ARFCN': get_col_val(u_kpi, 'Call & 5G KPI PCell RF NR-ARFCN'),
                            '5G SS-RSRP (dBm)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]'), 1),
                            '5G SS-SINR (dB)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]'), 1),
                            '5G PSCell CQI': round(get_col_val(u_kpi, 'Call & 5G KPI PCell RF CQI'), 1),
                            '5G UL MCS': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL MCS (Avg)'), 1),
                            '5G PUSCH BLER (%)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL BLER [%]'), 2),
                            '5G NR UL RB Num (avg)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL RB Num (Avg)'), 1),
                            '5G NR UL RB Num (inc0)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL RB Num (Including 0)'), 1),
                            '5G UL Modulation QPSK (%)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL Modulation UL QPSK Rate [%]'), 1),
                            '5G UL Modulation 16QAM (%)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL Modulation UL 16QAM Rate [%]'), 1),
                            '5G UL Modulation 64QAM (%)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL Modulation UL 64QAM Rate [%]'), 1),
                            '5G UL Modulation 256QAM (%)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell Layer1 UL Modulation UL 256 QAM Rate [%]'), 1),
                            '5G PUSCH Power (dBm)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell RF PUSCH Power [dBm]'), 1),
                            '5G PUCCH Power (dBm)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell RF PUCCH Power [dBm]'), 1),
                            '5G SRS Power (dBm)': round(srs_pwr, 1) if pd.notna(srs_pwr) else np.nan,
                            '5G Total Tx Power (dBm)': round(get_col_val(u_kpi, 'Call & 5G KPI PCell RF ENDC Tx Power [dBm]'), 1),
                            'LTE PCell eNB-Cell ID': u_enb_cell,
                            'LTE PCell PCI': get_col_val(u_kpi, 'Call & LTE KPI PCell Serving PCI'),
                            'LTE PCell TAC': u_tac,
                            'LTE PCell EARFCN': get_col_val(u_kpi, 'Call & LTE KPI PCell Serving EARFCN(UL)'),
                            'LTE PCell RSRP (dBm)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                            'LTE PCell SINR (dB)': round(get_col_val(u_kpi, 'Call & LTE KPI PCell SINR [dB]'), 1),
                        }
                    ul_rows.append(row_ul)

                # -------------------------------------------------------------
                # Build Pure Ping Row (04_Ping) - All Web Columns Dropped
                # -------------------------------------------------------------
                if pd.notna(p_val) or not p_kpi.empty:
                    ts_range = f"{p_ts_s.strftime('%H:%M:%S')} ~ {p_ts_e.strftime('%H:%M:%S')}" if not p_kpi.empty else "N/A"
                    p_resp_s = pd.to_numeric(CanonicalColumnRegistry.get_series(p_kpi, 'Call & SKT Speed Test Call Info Ping Event Info Ping Response'), errors='coerce').dropna()
                    p_cnt = len(p_resp_s)
                    p_min = float(p_resp_s.min()) if p_cnt > 0 else (p_val if pd.notna(p_val) else np.nan)
                    p_max = float(p_resp_s.max()) if p_cnt > 0 else (p_val if pd.notna(p_val) else np.nan)
                    p_avg = float(p_resp_s.mean()) if p_cnt > 0 else (p_val if pd.notna(p_val) else np.nan)
                    p_jitter = float(p_resp_s.std()) if p_cnt > 1 else 0.0
                    p_good_ratio = float((p_resp_s < 30.0).sum() / p_cnt * 100.0) if p_cnt > 0 else np.nan
                    p_slow_ratio = float((p_resp_s > 100.0).sum() / p_cnt * 100.0) if p_cnt > 0 else np.nan

                    row_ping = {
                        '호 번호': f"Call {i + 1}",
                        '시간 구간': ts_range,
                        '시나리오': 'Ping Test',
                        '망 모드': mode,
                        '호 상태': 'Success' if (p_cnt > 0 or pd.notna(p_val)) else 'Fail',
                        'Ping 시도 횟수': 10,
                        'Ping 성공 횟수': p_cnt if p_cnt > 0 else (10 if pd.notna(p_val) else 0),
                        'Ping 성공률 (%)': round(p_cnt / 10.0 * 100.0, 1) if 0 < p_cnt <= 10 else (100.0 if pd.notna(p_val) else 0.0),
                        '최소 Ping RTT (ms)': round(p_min, 2),
                        '최대 Ping RTT (ms)': round(p_max, 2),
                        '평균 Ping RTT (ms)': round(p_avg, 2),
                        'Ping Jitter (ms)': round(p_jitter, 2),
                        'Ping RTT < 30ms 양호율 (%)': round(p_good_ratio, 1) if pd.notna(p_good_ratio) else np.nan,
                        'Ping RTT > 100ms 지연율 (%)': round(p_slow_ratio, 1) if pd.notna(p_slow_ratio) else np.nan,
                        'Ping Packet Loss (%)': 0.0 if (p_cnt > 0 or pd.notna(p_val)) else 100.0,
                        'Serving PCI': p_pci,
                        'LTE PCell eNB-Cell ID': p_enb_cell,
                        'LTE PCell TAC': p_tac,
                        'SS-RSRP (dBm)': round(get_col_val(p_kpi, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]' if mode != 'LTE' else 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                        'SS-SINR (dB)': round(get_col_val(p_kpi, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]' if mode != 'LTE' else 'Call & LTE KPI PCell SINR [dB]'), 1),
                        'CQI': round(get_col_val(p_kpi, 'Call & 5G KPI PCell RF CQI' if mode != 'LTE' else 'Call & LTE KPI PCell WB CQI CW0'), 1),
                    }
                    ping_rows.append(row_ping)

            # Global Dominant Cell
            tot_enb_cell, tot_enb, tot_sec, tot_tac, tot_pci = get_dominant_cell_info(pd.to_datetime('1970-01-01'), pd.to_datetime('2099-12-31'))
            succ_calls = sum(1 for i in range(n_calls) if (i < len(d_res_list) and pd.notna(d_res_list.iloc[i])) or (i < len(u_res_list) and pd.notna(u_res_list.iloc[i])))

            tot_row = {
                'DRM 파일명': drm_name,
                '호 번호 (Call No)': f"Total ({n_calls} Calls)",
                '시나리오': f"{mode} SST Short Call",
                '망 모드': mode,
                '활성 벤더': vendor,
                '호 상태': f"{succ_calls}/{n_calls} ({succ_calls/n_calls*100:.1f}%)" if n_calls > 0 else 'N/A',
                '총 측정 초수': len(df_qc_kpi) if df_qc_kpi is not None else n_calls * 36,
                'App DL 평균 (Mbps)': round(d_res_list.mean(), 2) if not d_res_list.empty else np.nan,
                'App UL 평균 (Mbps)': round(u_res_list.mean(), 2) if not u_res_list.empty else np.nan,
                '평균 Ping RTT (ms)': round(p_res_list.mean(), 2) if not p_res_list.empty else np.nan,
                'MOS 평균': np.nan
            }
            df_total_summary = pd.DataFrame([tot_row])

        else:
            # -----------------------------------------------------------------
            # Unified Traffic Model Determination (SSOT: df_timeline.attrs)
            # -----------------------------------------------------------------
            traffic_model = 'DL'
            if df_timeline is not None and hasattr(df_timeline, 'attrs') and 'Traffic_Model' in df_timeline.attrs:
                traffic_model = df_timeline.attrs['Traffic_Model']
            elif df_timeline is not None and 'Traffic_Model' in df_timeline.columns and not df_timeline['Traffic_Model'].empty:
                traffic_model = str(df_timeline['Traffic_Model'].iloc[0]).upper()

            # Check for VoLTE Multi-Call (AutoCall) from Event, Event_(Detail), Call_Result, or RTP
            df_event = safe_read_csv(csvs.get('EVENT')) if csvs else None
            df_call_res = safe_read_csv(csvs.get('CALL_RESULT')) if csvs else None

            is_volte = traffic_model.startswith('VOICE')
            voice_dir = '발신 (MO)' if 'MO' in traffic_model else ('착신 (MT)' if 'MT' in traffic_model else '발신 (MO)')
            voice_scen_title = f"{'VoNR' if mode == 'SA' else 'VoLTE'} {'MO' if 'MO' in traffic_model else 'MT'} Call ({voice_dir})"

            voice_calls = []
            if is_volte and df_event_detail is not None and not df_event_detail.empty:
                st_col = find_col(df_event_detail, ['[Call & AutoCallSummary Status]', 'AutoCallSummary Status', '[Call & Voice Call Event Status]', 'Voice Call Event Status', 'AutoCall Status'])
                cd1_col = find_col(df_event_detail, ['[Call & AutoCallSummary Detail Code1]', 'AutoCallSummary Detail Code1', '[Call & Voice Call Event Detail Code1]', 'Voice Call Event Detail Code1'])
                cnt_col = find_col(df_event_detail, ['[Call & AutoCallSummary Call count]', 'AutoCallSummary Call count'])

                if st_col:
                    cur_start = None
                    cur_call_no = 1
                    for idx, row in df_event_detail.dropna(subset=['TIME_STAMP']).iterrows():
                        st_val = str(row[st_col]).strip()
                        cd1_val = str(row[cd1_col]).strip() if cd1_col else ''
                        c_cnt = int(row[cnt_col]) if (cnt_col and pd.notna(row[cnt_col])) else None
                        ts_val = row['TIME_STAMP']

                        if (st_val == 'Traffic' or cd1_val == 'Start') and cur_start is None:
                            cur_start = pd.to_datetime(ts_val)
                            if c_cnt is not None:
                                cur_call_no = c_cnt
                        elif st_val in ['Success', 'Drop', 'Release', 'Fail', 'End By User'] or cd1_val in ['Success', 'Drop', 'Fail']:
                            if cur_start is not None:
                                cur_end = pd.to_datetime(ts_val)
                                dur = (cur_end - cur_start).total_seconds()
                                if dur >= 1.0:
                                    is_succ = (st_val in ['Success', 'Release', 'End By User'] or cd1_val == 'Success')
                                    voice_calls.append({
                                        'call_no': f"Call {cur_call_no}",
                                        'start_dt': cur_start,
                                        'end_dt': cur_end,
                                        'dur_sec': dur,
                                        'status': 'Success' if is_succ else 'Drop',
                                        'cause': cd1_val if cd1_val else ('Normal' if is_succ else 'Drop')
                                    })
                                cur_start = None
                                if c_cnt is None:
                                    cur_call_no += 1

            if is_volte:
                # If no discrete calls extracted from event detail, fallback to 1 continuous call
                if not voice_calls and df_qc_kpi is not None and not df_qc_kpi.empty:
                    t_min = pd.to_datetime(df_qc_kpi['TIME_STAMP'].iloc[0])
                    t_max = pd.to_datetime(df_qc_kpi['TIME_STAMP'].iloc[-1])
                    voice_calls.append({
                        'call_no': "Call 1",
                        'start_dt': t_min,
                        'end_dt': t_max,
                        'dur_sec': (t_max - t_min).total_seconds(),
                        'status': 'Success',
                        'cause': 'Normal'
                    })

                for vc in voice_calls:
                    v_start, v_end = vc['start_dt'], vc['end_dt']
                    sub_tl = df_timeline[(df_timeline['TIME_STAMP'] >= v_start) & (df_timeline['TIME_STAMP'] <= v_end)] if (df_timeline is not None and not df_timeline.empty) else pd.DataFrame()
                    if sub_tl.empty and df_timeline is not None and 'Call_No' in df_timeline.columns:
                        sub_tl = df_timeline[df_timeline['Call_No'] == vc['call_no']]

                    # RF parameters directly from df_timeline (SSOT)
                    c_pci = int(sub_tl['LTE_Serving_PCI'].dropna().mode()[0]) if ('LTE_Serving_PCI' in sub_tl.columns and not sub_tl['LTE_Serving_PCI'].dropna().empty) else np.nan
                    c_enb_cell = str(sub_tl['eNB_Cell_ID'].dropna().mode()[0]) if ('eNB_Cell_ID' in sub_tl.columns and not sub_tl['eNB_Cell_ID'].dropna().empty) else "-"
                    rsrp_val = round(float(sub_tl['SS_RSRP'].dropna().mean()), 1) if ('SS_RSRP' in sub_tl.columns and not sub_tl['SS_RSRP'].dropna().empty) else np.nan
                    sinr_val = round(float(sub_tl['SS_SINR'].dropna().mean()), 1) if ('SS_SINR' in sub_tl.columns and not sub_tl['SS_SINR'].dropna().empty) else np.nan
                    cqi_val = round(float(sub_tl['CQI'].dropna().mean()), 1) if ('CQI' in sub_tl.columns and not sub_tl['CQI'].dropna().empty) else np.nan

                    # MOS & Jitter from df_timeline / RTP
                    mos_s = sub_tl['MOS'].dropna() if 'MOS' in sub_tl.columns else pd.Series([], dtype=float)
                    mos_avg = float(mos_s.mean()) if not mos_s.empty else np.nan
                    mos_min = float(mos_s.min()) if not mos_s.empty else np.nan
                    mos_max = float(mos_s.max()) if not mos_s.empty else np.nan

                    jit_s = sub_tl['Jitter'].dropna() if 'Jitter' in sub_tl.columns else pd.Series([], dtype=float)
                    j_min = float(jit_s.min()) if not jit_s.empty else np.nan
                    j_max = float(jit_s.max()) if not jit_s.empty else np.nan
                    j_avg = float(jit_s.mean()) if not jit_s.empty else np.nan
                    j_std = float(jit_s.std()) if len(jit_s) > 1 else (0.0 if not jit_s.empty else np.nan)

                    loss_dl = float(sub_tl['Packet_Loss'].dropna().mean()) if ('Packet_Loss' in sub_tl.columns and not sub_tl['Packet_Loss'].dropna().empty) else np.nan

                    voice_rows.append({
                        '호 번호': vc['call_no'],
                        '호 방향': voice_dir,
                        '시간 구간': f"{v_start.strftime('%H:%M:%S')} ~ {v_end.strftime('%H:%M:%S')}",
                        '시나리오': voice_scen_title,
                        '망 모드': 'SA' if mode == 'SA' else 'LTE',
                        '호 상태': vc['status'],
                        '호 릴리즈 원인 (Cause)': vc['cause'],
                        '통화 지속 시간 (초)': round(vc['dur_sec'], 1),
                        'MOS 평균': round(mos_avg, 2) if pd.notna(mos_avg) else np.nan,
                        'MOS 최소 (Min)': round(mos_min, 2) if pd.notna(mos_min) else np.nan,
                        'Voice Codec': str(sub_tl['Codec'].dropna().iloc[0]) if ('Codec' in sub_tl.columns and not sub_tl['Codec'].dropna().empty) else ('AMR-WB' if not jit_s.empty or not mos_s.empty else np.nan),
                        'RTP Jitter 최소 (ms)': round(j_min, 1) if pd.notna(j_min) else np.nan,
                        'RTP Jitter 최대 (ms)': round(j_max, 1) if pd.notna(j_max) else np.nan,
                        'RTP Jitter 평균 (ms)': round(j_avg, 1) if pd.notna(j_avg) else np.nan,
                        'RTP Jitter 표준편차 (ms)': round(j_std, 1) if pd.notna(j_std) else np.nan,
                        'LTE PCell eNB-Cell ID': c_enb_cell,
                        'Serving PCI': c_pci,
                        'Serving RSRP (dBm)': rsrp_val,
                        'Serving SINR (dB)': sinr_val,
                        'Serving CQI': cqi_val,
                    })

                succ_cnt = sum(1 for vc in voice_calls if vc['status'] == 'Success')
                tot_cnt = len(voice_calls)

                tot_row = {
                    'DRM 파일명': drm_name,
                    '호 번호 (Call No)': f"Total ({tot_cnt} Calls)",
                    '시나리오': voice_scen_title,
                    '망 모드': 'SA' if mode == 'SA' else 'LTE',
                    '활성 벤더': vendor,
                    '호 상태': f"{succ_cnt}/{tot_cnt} ({succ_cnt/tot_cnt*100:.1f}%)" if tot_cnt > 0 else 'N/A',
                    '총 측정 초수': len(df_timeline) if df_timeline is not None else 0,
                    'App DL 평균 (Mbps)': np.nan,
                    'App UL 평균 (Mbps)': np.nan,
                    '평균 Ping RTT (ms)': np.nan,
                    'MOS 평균': round(pd.DataFrame(voice_rows)['MOS 평균'].dropna().mean(), 2) if (voice_rows and 'MOS 평균' in pd.DataFrame(voice_rows).columns and not pd.DataFrame(voice_rows)['MOS 평균'].dropna().empty) else np.nan
                }
                df_total_summary = pd.DataFrame([tot_row])

            elif not is_volte and df_event_detail is not None and not df_event_detail.empty and find_col(df_event_detail, ['[Call & AutoCallSummary Status]', 'AutoCallSummary Status', 'AutoCall Status']):
                # -------------------------------------------------------------
                # FTP Short Call Multi-Call Segmentation (DL / UL)
                # -------------------------------------------------------------
                st_col = find_col(df_event_detail, ['[Call & AutoCallSummary Status]', 'AutoCallSummary Status', 'AutoCall Status'])
                cd1_col = find_col(df_event_detail, ['[Call & AutoCallSummary Detail Code1]', 'AutoCallSummary Detail Code1'])
                
                is_ftp_ul = traffic_model.startswith('UL')
                is_ftp_dl = traffic_model.startswith('DL')

                ftp_calls = []
                cur_start = None
                call_cnt = 0
                for idx, row in df_event_detail.dropna(subset=['TIME_STAMP']).iterrows():
                    st_val = str(row[st_col]).strip()
                    cd1_val = str(row[cd1_col]).strip() if cd1_col else ''
                    ts_val = row['TIME_STAMP']
                    
                    if (st_val == 'Traffic' or cd1_val == 'Start') and cur_start is None:
                        cur_start = pd.to_datetime(ts_val)
                    elif st_val in ['Success', 'Drop', 'Release', 'Fail', 'End By User'] or cd1_val in ['Success', 'Drop', 'Fail']:
                        if cur_start is not None:
                            cur_end = pd.to_datetime(ts_val)
                            dur = (cur_end - cur_start).total_seconds()
                            if dur >= 3.0:
                                call_cnt += 1
                                is_succ = (st_val == 'Success' or cd1_val == 'Success')
                                ftp_calls.append({
                                    'call_no': f"Call {call_cnt}",
                                    'start_dt': cur_start,
                                    'end_dt': cur_end,
                                    'dur_sec': dur,
                                    'status': 'Success' if is_succ else 'Drop'
                                })
                                cur_start = None

                # Continuous Long Call fallback when no Short Call event intervals are detected
                if not ftp_calls:
                    first_ts = None
                    last_ts = None
                    if df_timeline is not None and not df_timeline.empty and 'TIME_STAMP' in df_timeline.columns:
                        first_ts = pd.to_datetime(df_timeline['TIME_STAMP'].iloc[0])
                        last_ts = pd.to_datetime(df_timeline['TIME_STAMP'].iloc[-1])
                    elif not s_kpi_dt.empty:
                        first_ts = s_kpi_dt.iloc[0]
                        last_ts = s_kpi_dt.iloc[-1]

                    if first_ts is not None and last_ts is not None:
                        dur = (last_ts - first_ts).total_seconds() if hasattr(last_ts - first_ts, 'total_seconds') else float(len(df_timeline))
                        ftp_calls.append({
                            'call_no': 'Call 1 (Long Call)',
                            'start_dt': first_ts,
                            'end_dt': last_ts,
                            'dur_sec': max(dur, 1.0),
                            'status': 'Success'
                        })

                for fc in ftp_calls:
                    f_start, f_end = fc['start_dt'], fc['end_dt']
                    sub_kpi = df_qc_kpi[(s_kpi_dt >= f_start) & (s_kpi_dt <= f_end)] if not s_kpi_dt.empty else pd.DataFrame()
                    sub_tl = df_timeline[(df_timeline['TIME_STAMP'] >= f_start) & (df_timeline['TIME_STAMP'] <= f_end)] if (df_timeline is not None and not df_timeline.empty) else pd.DataFrame()
                    if sub_tl.empty and df_timeline is not None and 'Call_No' in df_timeline.columns:
                        sub_tl = df_timeline[df_timeline['Call_No'] == fc['call_no']]

                    f_enb_cell, f_enb, f_sec, f_tac, f_pci = get_dominant_cell_info(f_start, f_end)
                    ts_range = f"{f_start.strftime('%H:%M:%S')} ~ {f_end.strftime('%H:%M:%S')}"

                    gps_spd = round(float(sub_tl['Speed'].dropna().mean()), 1) if ('Speed' in sub_tl and not sub_tl['Speed'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & GPS Speed (km/h)'), 1)
                    pci_val = int(sub_tl['LTE_Serving_PCI'].dropna().mode()[0]) if ('LTE_Serving_PCI' in sub_tl and not sub_tl['LTE_Serving_PCI'].dropna().empty) else (int(sub_tl['NR_Serving_PCI'].dropna().mode()[0]) if ('NR_Serving_PCI' in sub_tl and not sub_tl['NR_Serving_PCI'].dropna().empty) else f_pci)
                    enb_cell_val = str(sub_tl['eNB_Cell_ID'].dropna().mode()[0]) if ('eNB_Cell_ID' in sub_tl and not sub_tl['eNB_Cell_ID'].dropna().empty) else (f_enb_cell or "-")
                    rsrp_val = round(float(sub_tl['SS_RSRP'].dropna().mean()), 1) if ('SS_RSRP' in sub_tl and not sub_tl['SS_RSRP'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1)
                    sinr_val = round(float(sub_tl['SS_SINR'].dropna().mean()), 1) if ('SS_SINR' in sub_tl and not sub_tl['SS_SINR'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell SINR [dB]'), 1)
                    rsrq_val = round(float(sub_tl['SS_RSRQ'].dropna().mean()), 1) if ('SS_RSRQ' in sub_tl and not sub_tl['SS_RSRQ'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell Serving RSRQ [dB]'), 1)
                    cqi_val = round(float(sub_tl['CQI'].dropna().mean()), 1) if ('CQI' in sub_tl and not sub_tl['CQI'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell WB CQI CW0'), 1)
                    dl_mcs_val = round(float(sub_tl['DL_MCS'].dropna().mean()), 1) if ('DL_MCS' in sub_tl and not sub_tl['DL_MCS'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell DL MCS0'), 1)
                    ul_mcs_val = round(float(sub_tl['UL_MCS'].dropna().mean()), 1) if ('UL_MCS' in sub_tl and not sub_tl['UL_MCS'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell UL MCS'), 1)
                    pdsch_bler_val = round(float(sub_tl['PDSCH_BLER'].dropna().mean()), 2) if ('PDSCH_BLER' in sub_tl and not sub_tl['PDSCH_BLER'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2)
                    pusch_bler_val = round(float(sub_tl['PUSCH_BLER'].dropna().mean()), 2) if ('PUSCH_BLER' in sub_tl and not sub_tl['PUSCH_BLER'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PUSCH BLER [%]'), 2)
                    prb_inc0_val = round(float(sub_tl['PRB_Num_Inc0'].dropna().mean()), 1) if ('PRB_Num_Inc0' in sub_tl and not sub_tl['PRB_Num_Inc0'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PDSCH PRB Number(Including 0)'), 1)
                    ri_val = round(float(sub_tl['WB_RI'].dropna().mean()), 1) if ('WB_RI' in sub_tl and not sub_tl['WB_RI'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell WB RI'), 1)
                    qam64_val = round(float(sub_tl['QAM64_Rate'].dropna().mean()), 1) if ('QAM64_Rate' in sub_tl and not sub_tl['QAM64_Rate'].dropna().empty) else (100.0 if ('64QAM' in str(sub_tl.get('DL_Modulation', ''))) else np.nan)
                    qam256_val = round(float(sub_tl['QAM256_Rate'].dropna().mean()), 1) if ('QAM256_Rate' in sub_tl and not sub_tl['QAM256_Rate'].dropna().empty) else (100.0 if ('256QAM' in str(sub_tl.get('DL_Modulation', ''))) else np.nan)

                    is_nsa = (mode == 'NSA')
                    
                    def _safe_num_mean(s_data):
                        if s_data is None: return np.nan
                        s = pd.to_numeric(s_data, errors='coerce').dropna()
                        return float(s.mean()) if not s.empty else np.nan

                    # NR Metrics
                    nr_pci_val = int(sub_tl['NR_Serving_PCI'].dropna().mode()[0]) if ('NR_Serving_PCI' in sub_tl and not sub_tl['NR_Serving_PCI'].dropna().empty) else (f_pci if is_nsa else np.nan)
                    nr_rsrp_val = round(_safe_num_mean(sub_tl.get('NR_SS_RSRP')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_SS_RSRP'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]'), 1)
                    nr_sinr_val = round(_safe_num_mean(sub_tl.get('NR_SS_SINR')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_SS_SINR'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]'), 1)
                    nr_rsrq_val = round(_safe_num_mean(sub_tl.get('NR_SS_RSRQ')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_SS_RSRQ'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell RF Serving SS-RSRQ [dB]'), 1)
                    nr_cqi_val = round(_safe_num_mean(sub_tl.get('NR_CQI')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_CQI'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell RF CQI'), 1)
                    nr_dl_mcs_val = round(_safe_num_mean(sub_tl.get('NR_DL_MCS')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_DL_MCS'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 DL MCS (Avg)'), 1)
                    nr_ul_mcs_val = round(_safe_num_mean(sub_tl.get('NR_UL_MCS')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_UL_MCS'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 UL MCS (Avg)'), 1)
                    nr_pdsch_bler_val = round(_safe_num_mean(sub_tl.get('NR_PDSCH_BLER')), 2) if pd.notna(_safe_num_mean(sub_tl.get('NR_PDSCH_BLER'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 DL BLER [%]'), 2)
                    nr_pusch_bler_val = round(_safe_num_mean(sub_tl.get('NR_PUSCH_BLER')), 2) if pd.notna(_safe_num_mean(sub_tl.get('NR_PUSCH_BLER'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 UL BLER [%]'), 2)
                    nr_dl_prb_inc0_val = round(_safe_num_mean(sub_tl.get('NR_PRB_Inc0')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_PRB_Inc0'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 DL RB Num (Including 0)'), 1)
                    nr_ul_prb_inc0_val = round(_safe_num_mean(sub_tl.get('NR_UL_PRB_Inc0')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_UL_PRB_Inc0'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 UL RB Num (Including 0)'), 1)
                    nr_wb_ri_val = round(_safe_num_mean(sub_tl.get('NR_WB_RI')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_WB_RI'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell RF RI(Avg)'), 1)
                    nr_pusch_pwr_val = round(_safe_num_mean(sub_tl.get('NR_PUSCH_Power')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_PUSCH_Power'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell RF PUSCH Power [dBm]'), 1)
                    nr_qam64_val = round(_safe_num_mean(sub_tl.get('NR_QAM64_Rate')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_QAM64_Rate'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]'), 1)
                    nr_qam256_val = round(_safe_num_mean(sub_tl.get('NR_QAM256_Rate')), 1) if pd.notna(_safe_num_mean(sub_tl.get('NR_QAM256_Rate'))) else round(get_col_val(sub_kpi, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]'), 1)

                    # LTE Metrics
                    lte_pci_val = int(sub_tl['LTE_Serving_PCI'].dropna().mode()[0]) if ('LTE_Serving_PCI' in sub_tl and not sub_tl['LTE_Serving_PCI'].dropna().empty) else f_pci
                    lte_rsrp_val = round(_safe_num_mean(sub_tl.get('LTE_RSRP')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_RSRP'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1)
                    lte_sinr_val = round(_safe_num_mean(sub_tl.get('LTE_SINR')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_SINR'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell SINR [dB]'), 1)
                    lte_rsrq_val = round(_safe_num_mean(sub_tl.get('LTE_RSRQ')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_RSRQ'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell Serving RSRQ [dB]'), 1)
                    lte_cqi_val = round(_safe_num_mean(sub_tl.get('LTE_CQI')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_CQI'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell WB CQI CW0'), 1)
                    lte_dl_mcs_val = round(_safe_num_mean(sub_tl.get('LTE_DL_MCS')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_DL_MCS'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell DL MCS0'), 1)
                    lte_ul_mcs_val = round(_safe_num_mean(sub_tl.get('LTE_UL_MCS')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_UL_MCS'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell UL MCS'), 1)
                    lte_pdsch_bler_val = round(_safe_num_mean(sub_tl.get('LTE_PDSCH_BLER')), 2) if pd.notna(_safe_num_mean(sub_tl.get('LTE_PDSCH_BLER'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2)
                    lte_pusch_bler_val = round(_safe_num_mean(sub_tl.get('LTE_PUSCH_BLER')), 2) if pd.notna(_safe_num_mean(sub_tl.get('LTE_PUSCH_BLER'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PUSCH BLER [%]'), 2)
                    lte_dl_prb_inc0_val = round(_safe_num_mean(sub_tl.get('LTE_PRB_Inc0')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_PRB_Inc0'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PDSCH PRB Number(Including 0)'), 1)
                    lte_ul_prb_inc0_val = round(_safe_num_mean(sub_tl.get('LTE_UL_PRB_Inc0')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_UL_PRB_Inc0'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PUSCH PRB Number(Including 0)'), 1)
                    lte_wb_ri_val = round(_safe_num_mean(sub_tl.get('LTE_WB_RI')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_WB_RI'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell WB RI'), 1)
                    lte_pusch_pwr_val = round(_safe_num_mean(sub_tl.get('LTE_PUSCH_Power')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_PUSCH_Power'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PUSCH Power [dBm]'), 1)
                    lte_qam64_val = round(_safe_num_mean(sub_tl.get('LTE_QAM64_Rate')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_QAM64_Rate'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI SCell[1] DL Modulation0'), 1)
                    lte_qam256_val = round(_safe_num_mean(sub_tl.get('LTE_QAM256_Rate')), 1) if pd.notna(_safe_num_mean(sub_tl.get('LTE_QAM256_Rate'))) else round(get_col_val(sub_kpi, 'Call & LTE KPI SCell[2] DL Modulation0'), 1)

                    if is_ftp_dl:
                        raw_app = get_col_val(sub_kpi, 'Call & Speed Test T-put Current App Throughput [Mbps]')
                        if pd.isna(raw_app):
                            raw_app_k = get_col_val(sub_kpi, 'Call & APP Throughput Info(All Data) All FWD  Throughput (kbps)')
                            if pd.isna(raw_app_k):
                                raw_app_k = get_col_val(sub_kpi, 'Call & APP Throughput Info(All Data) All FWD  Throughput')
                            raw_app = raw_app_k / 1000.0 if (pd.notna(raw_app_k) and raw_app_k > 0) else np.nan

                        pdcp_dl_val = round(float(sub_tl['PDCP_DL_Tput'].dropna().mean()), 2) if ('PDCP_DL_Tput' in sub_tl and not sub_tl['PDCP_DL_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]'), 2)
                        if pd.isna(pdcp_dl_val):
                            pdcp_dl_val = round(get_col_val(sub_kpi, 'Call & LTE KPI PDCP DL Throughput [Mbps]'), 2)
                        
                        nr_pdsch_val = round(float(sub_tl['NR_PDSCH_Tput'].dropna().mean()), 2) if ('NR_PDSCH_Tput' in sub_tl and not sub_tl['NR_PDSCH_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]'), 2)
                        nr_mac_dl_val = round(float(sub_tl['NR_MAC_DL_Tput'].dropna().mean()), 2) if ('NR_MAC_DL_Tput' in sub_tl and not sub_tl['NR_MAC_DL_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]'), 2)
                        lte_mac_dl_val = round(float(sub_tl['LTE_MAC_DL_Tput'].dropna().mean()), 2) if ('LTE_MAC_DL_Tput' in sub_tl and not sub_tl['LTE_MAC_DL_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI MAC DL Throughput [Mbps]'), 2)
                        lte_pdsch_val = round(float(sub_tl['LTE_PDSCH_Tput'].dropna().mean()), 2) if ('LTE_PDSCH_Tput' in sub_tl and not sub_tl['LTE_PDSCH_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PDSCH Throughput [Mbps]'), 2)
                        app_dl_val = round(float(sub_tl['App_DL_Tput'].dropna().mean()), 2) if ('App_DL_Tput' in sub_tl and not sub_tl['App_DL_Tput'].dropna().empty and sub_tl['App_DL_Tput'].dropna().mean() > 0) else (round(raw_app, 2) if pd.notna(raw_app) else np.nan)

                        if is_nsa:
                            row_dl = {
                                '호 번호': fc['call_no'],
                                '시간 구간': ts_range,
                                '호 상태': fc['status'],
                                '통화 지속 시간 (초)': round(fc['dur_sec'], 1),
                                'App DL 속도 (Mbps)': app_dl_val if pd.notna(app_dl_val) else np.nan,
                                'PDCP DL 속도 (Mbps)': pdcp_dl_val,
                                'NR MAC DL 속도 (Mbps)': nr_mac_dl_val,
                                'NR PDSCH 속도 (Mbps)': nr_pdsch_val,
                                'LTE MAC DL 속도 (Mbps)': lte_mac_dl_val,
                                'LTE PDSCH 속도 (Mbps)': lte_pdsch_val,
                                '[NR] gNB-Cell ID': enb_cell_val,
                                '[NR] Serving PCI': nr_pci_val,
                                '[NR] SS-RSRP (dBm)': nr_rsrp_val,
                                '[NR] SS-SINR (dB)': nr_sinr_val,
                                '[NR] SS-RSRQ (dB)': nr_rsrq_val,
                                '[NR] CQI': nr_cqi_val,
                                '[NR] DL MCS': nr_dl_mcs_val,
                                '[NR] PDSCH BLER (%)': nr_pdsch_bler_val,
                                '[NR] DL RB Num (Inc 0)': nr_dl_prb_inc0_val,
                                '[NR] WB RI': nr_wb_ri_val,
                                '[NR] 64QAM Rate (%)': nr_qam64_val,
                                '[NR] 256QAM Rate (%)': nr_qam256_val,
                                '[LTE] eNB-Cell ID': enb_cell_val,
                                '[LTE] Serving PCI': lte_pci_val,
                                '[LTE] Serving RSRP (dBm)': lte_rsrp_val,
                                '[LTE] Serving SINR (dB)': lte_sinr_val,
                                '[LTE] Serving RSRQ (dB)': lte_rsrq_val,
                                '[LTE] CQI': lte_cqi_val,
                                '[LTE] DL MCS': lte_dl_mcs_val,
                                '[LTE] PDSCH BLER (%)': lte_pdsch_bler_val,
                                '[LTE] DL RB Num (Inc 0)': lte_dl_prb_inc0_val,
                                '[LTE] 256QAM Rate (%)': lte_qam256_val,
                                '이동속도 (km/h)': gps_spd
                            }
                        else:
                            row_dl = {
                                '호 번호': fc['call_no'],
                                '시간 구간': ts_range,
                                '호 상태': fc['status'],
                                '통화 지속 시간 (초)': round(fc['dur_sec'], 1),
                                'App DL 속도 (Mbps)': app_dl_val if pd.notna(app_dl_val) else np.nan,
                                'PDCP DL 속도 (Mbps)': pdcp_dl_val,
                                'MAC DL 속도 (Mbps)': lte_mac_dl_val,
                                'PDSCH 속도 (Mbps)': lte_pdsch_val,
                                'PCell eNB-Cell ID': enb_cell_val,
                                'Serving PCI': lte_pci_val,
                                'Serving RSRP (dBm)': lte_rsrp_val,
                                'Serving SINR (dB)': lte_sinr_val,
                                'Serving RSRQ (dB)': lte_rsrq_val,
                                'CQI': lte_cqi_val,
                                'DL MCS': lte_dl_mcs_val,
                                'PDSCH BLER (%)': lte_pdsch_bler_val,
                                'DL RB Num (Inc 0)': lte_dl_prb_inc0_val,
                                'RI (Rank Indicator)': lte_wb_ri_val,
                                '64QAM Rate (%)': lte_qam64_val,
                                '256QAM Rate (%)': lte_qam256_val,
                                '이동속도 (km/h)': gps_spd
                            }
                        dl_rows.append(row_dl)
                    else:
                        raw_app = get_col_val(sub_kpi, 'Call & Speed Test T-put Current App Throughput [Mbps]')
                        if pd.isna(raw_app):
                            raw_app_k = get_col_val(sub_kpi, 'Call & APP Throughput Info(All Data) All RVS Throughput (kbps)')
                            if pd.isna(raw_app_k):
                                raw_app_k = get_col_val(sub_kpi, 'Call & APP Throughput Info(All Data) All RVS Throughput')
                            raw_app = raw_app_k / 1000.0 if (pd.notna(raw_app_k) and raw_app_k > 0) else np.nan

                        pdcp_ul_val = round(float(sub_tl['PDCP_UL_Tput'].dropna().mean()), 2) if ('PDCP_UL_Tput' in sub_tl and not sub_tl['PDCP_UL_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & 5G KPI Total Info Layer2 PDCP UL Throughput(+Split Bearer) [Mbps]'), 2)
                        if pd.isna(pdcp_ul_val):
                            pdcp_ul_val = round(get_col_val(sub_kpi, 'Call & LTE KPI PDCP UL Throughput [Mbps]'), 2)

                        nr_pusch_val = round(float(sub_tl['NR_PUSCH_Tput'].dropna().mean()), 2) if ('NR_PUSCH_Tput' in sub_tl and not sub_tl['NR_PUSCH_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & 5G KPI Total Info Layer1 PUSCH Throughput [Mbps]'), 2)
                        nr_mac_ul_val = round(float(sub_tl['NR_MAC_UL_Tput'].dropna().mean()), 2) if ('NR_MAC_UL_Tput' in sub_tl and not sub_tl['NR_MAC_UL_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & 5G KPI Total Info Layer2 MAC UL Throughput [Mbps]'), 2)
                        lte_mac_ul_val = round(float(sub_tl['LTE_MAC_UL_Tput'].dropna().mean()), 2) if ('LTE_MAC_UL_Tput' in sub_tl and not sub_tl['LTE_MAC_UL_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell MAC UL Throughput [Mbps]'), 2)
                        lte_pusch_val = round(float(sub_tl['LTE_PUSCH_Tput'].dropna().mean()), 2) if ('LTE_PUSCH_Tput' in sub_tl and not sub_tl['LTE_PUSCH_Tput'].dropna().empty) else round(get_col_val(sub_kpi, 'Call & LTE KPI PCell PUSCH Throughput [Mbps]'), 2)
                        app_ul_val = round(float(sub_tl['App_UL_Tput'].dropna().mean()), 2) if ('App_UL_Tput' in sub_tl and not sub_tl['App_UL_Tput'].dropna().empty and sub_tl['App_UL_Tput'].dropna().mean() > 0) else (round(raw_app, 2) if pd.notna(raw_app) else np.nan)

                        if is_nsa:
                            row_ul = {
                                '호 번호': fc['call_no'],
                                '시간 구간': ts_range,
                                '호 상태': fc['status'],
                                '통화 지속 시간 (초)': round(fc['dur_sec'], 1),
                                'App UL 속도 (Mbps)': app_ul_val if pd.notna(app_ul_val) else np.nan,
                                'PDCP UL 속도 (Mbps)': pdcp_ul_val,
                                'NR MAC UL 속도 (Mbps)': nr_mac_ul_val,
                                'NR PUSCH 속도 (Mbps)': nr_pusch_val,
                                'LTE MAC UL 속도 (Mbps)': lte_mac_ul_val,
                                'LTE PUSCH 속도 (Mbps)': lte_pusch_val,
                                '[NR] gNB-Cell ID': enb_cell_val,
                                '[NR] Serving PCI': nr_pci_val,
                                '[NR] SS-RSRP (dBm)': nr_rsrp_val,
                                '[NR] SS-SINR (dB)': nr_sinr_val,
                                '[NR] SS-RSRQ (dB)': nr_rsrq_val,
                                '[NR] CQI': nr_cqi_val,
                                '[NR] UL MCS': nr_ul_mcs_val,
                                '[NR] PUSCH BLER (%)': nr_pusch_bler_val,
                                '[NR] UL RB Num (Inc 0)': nr_ul_prb_inc0_val,
                                '[NR] WB RI': nr_wb_ri_val,
                                '[NR] PUSCH Power (dBm)': nr_pusch_pwr_val,
                                '[NR] 64QAM Rate (%)': nr_qam64_val,
                                '[NR] 256QAM Rate (%)': nr_qam256_val,
                                '[LTE] eNB-Cell ID': enb_cell_val,
                                '[LTE] Serving PCI': lte_pci_val,
                                '[LTE] Serving RSRP (dBm)': lte_rsrp_val,
                                '[LTE] Serving SINR (dB)': lte_sinr_val,
                                '[LTE] Serving RSRQ (dB)': lte_rsrq_val,
                                '[LTE] CQI': lte_cqi_val,
                                '[LTE] UL MCS': lte_ul_mcs_val,
                                '[LTE] PUSCH BLER (%)': lte_pusch_bler_val,
                                '[LTE] UL RB Num (Inc 0)': lte_ul_prb_inc0_val,
                                '[LTE] PUSCH Power (dBm)': lte_pusch_pwr_val,
                                '이동속도 (km/h)': gps_spd
                            }
                        else:
                            row_ul = {
                                '호 번호': fc['call_no'],
                                '시간 구간': ts_range,
                                '호 상태': fc['status'],
                                '통화 지속 시간 (초)': round(fc['dur_sec'], 1),
                                'App UL 속도 (Mbps)': app_ul_val if pd.notna(app_ul_val) else np.nan,
                                'PDCP UL 속도 (Mbps)': pdcp_ul_val,
                                'MAC UL 속도 (Mbps)': lte_mac_ul_val,
                                'PUSCH 속도 (Mbps)': lte_pusch_val,
                                'PCell eNB-Cell ID': enb_cell_val,
                                'Serving PCI': lte_pci_val,
                                'Serving RSRP (dBm)': lte_rsrp_val,
                                'Serving SINR (dB)': lte_sinr_val,
                                'Serving RSRQ (dB)': lte_rsrq_val,
                                'CQI': lte_cqi_val,
                                'UL MCS': lte_ul_mcs_val,
                                'PUSCH BLER (%)': lte_pusch_bler_val,
                                'UL RB Num (Inc 0)': lte_ul_prb_inc0_val,
                                'RI (Rank Indicator)': lte_wb_ri_val,
                                'PUSCH Power (dBm)': lte_pusch_pwr_val,
                                '이동속도 (km/h)': gps_spd
                            }
                        ul_rows.append(row_ul)

                tot_cnt = len(ftp_calls)
                succ_cnt = sum(1 for fc in ftp_calls if fc['status'] == 'Success')
                avg_dl_s = pd.DataFrame(dl_rows)['App DL 속도 (Mbps)'].dropna() if dl_rows else pd.Series([])
                avg_ul_s = pd.DataFrame(ul_rows)['App UL 속도 (Mbps)'].dropna() if ul_rows else pd.Series([])

                tot_row = {
                    'DRM 파일명': drm_name,
                    '호 번호 (Call No)': f"Total ({tot_cnt} Calls)",
                    '시나리오': f"{mode} {'DL' if is_ftp_dl else 'UL'} {'Long Call' if traffic_model in ['DL_Long_Call', 'UL_Long_Call'] else 'Short Call'}",
                    '망 모드': mode,
                    '활성 벤더': vendor,
                    '호 상태': f"{succ_cnt}/{tot_cnt} ({succ_cnt/tot_cnt*100:.1f}%)" if tot_cnt > 0 else 'N/A',
                    '총 측정 초수': len(df_qc_kpi) if df_qc_kpi is not None else 0,
                    'App DL 평균 (Mbps)': round(avg_dl_s.mean(), 2) if not avg_dl_s.empty else np.nan,
                    'App UL 평균 (Mbps)': round(avg_ul_s.mean(), 2) if not avg_ul_s.empty else np.nan,
                    '평균 Ping RTT (ms)': np.nan,
                    'MOS 평균': np.nan
                }
                df_total_summary = pd.DataFrame([tot_row])

            else:
                # Continuous Long Call (Drive Test) ➔ Apply 1m Route Binning
                df_binned_long = cls.apply_1m_route_binning(df_qc_kpi)

                # Throughput & RF calculation on 1m Binned DataFrame
                app_dl = get_col_val(df_binned_long, 'Call & Speed Test T-put Current App Throughput [Mbps]')
                if pd.isna(app_dl):
                    raw_app = get_col_val(df_binned_long, 'Call & APP Throughput Info(All Data) All FWD  Throughput (kbps)')
                    if pd.isna(raw_app):
                        raw_app = get_col_val(df_binned_long, 'Call & APP Throughput Info(All Data) All FWD  Throughput')
                    app_dl = raw_app / 1000.0 if (pd.notna(raw_app) and raw_app > 0) else np.nan

                tot_enb_cell, tot_enb, tot_sec, tot_tac, tot_pci = get_dominant_cell_info(pd.to_datetime('1970-01-01'), pd.to_datetime('2099-12-31'))
                scen_title = f'{mode} DL Long Call'

                # Total Summary
                tot_row = {
                    'DRM 파일명': drm_name,
                    '호 번호 (Call No)': 'Total (Continuous)',
                    '시나리오': scen_title,
                    '망 모드': mode,
                    '활성 벤더': vendor,
                    '호 상태': 'Success (100.0%)',
                    '총 측정 초수': len(df_qc_kpi) if df_qc_kpi is not None else 0,
                    'App DL 평균 (Mbps)': round(app_dl, 2) if pd.notna(app_dl) else np.nan,
                    'App UL 평균 (Mbps)': np.nan,
                    '평균 Ping RTT (ms)': np.nan,
                    'MOS 평균': np.nan
                }
                df_total_summary = pd.DataFrame([tot_row])

                # -------------------------------------------------------------
                # Build Master DL Row (02_DL) - Drop lat/lon
                # -------------------------------------------------------------
                gps_spd = round(get_col_val(df_binned_long, 'Call & GPS Speed (km/h)'), 1)
                if pd.isna(gps_spd):
                    gps_spd = round(get_col_val(df_binned_long, 'GPS Speed (km/h)'), 1)

                is_nsa = (mode == 'NSA')
                if not is_nsa:
                    row_dl = {
                        '호 번호': 'Call 1',
                        '시간 구간': '전체 구간',
                        '호 상태': 'Success',
                        '통화 지속 시간 (초)': len(df_qc_kpi) if df_qc_kpi is not None else 0,
                        'App DL 속도 (Mbps)': round(app_dl, 2) if pd.notna(app_dl) else np.nan,
                        'PDCP DL 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & LTE KPI PDCP DL Throughput [Mbps]'), 2),
                        'MAC DL 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & LTE KPI MAC DL Throughput [Mbps]'), 2),
                        'PDSCH 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell PDSCH Throughput [Mbps]'), 2),
                        'PCell eNB-Cell ID': tot_enb_cell,
                        'Serving PCI': tot_pci,
                        'Serving RSRP (dBm)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                        'Serving SINR (dB)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell SINR [dB]'), 1),
                        'Serving RSRQ (dB)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell Serving RSRQ [dB]'), 1),
                        'CQI': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell WB CQI CW0'), 1),
                        'DL MCS': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell DL MCS0'), 1),
                        'PDSCH BLER (%)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2),
                        'DL RB Num (Inc 0)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell PDSCH PRB Number(Including 0)'), 1),
                        'RI (Rank Indicator)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell WB RI'), 1),
                        '64QAM Rate (%)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]'), 1),
                        '256QAM Rate (%)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]'), 1),
                        '이동속도 (km/h)': gps_spd
                    }
                else:
                    # NSA Mode
                    row_dl = {
                        '호 번호': 'Call 1',
                        '시간 구간': '전체 구간',
                        '호 상태': 'Success',
                        '통화 지속 시간 (초)': len(df_qc_kpi) if df_qc_kpi is not None else 0,
                        'App DL 속도 (Mbps)': round(app_dl, 2) if pd.notna(app_dl) else np.nan,
                        'PDCP DL 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]'), 2),
                        'NR MAC DL 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]'), 2),
                        'NR PDSCH 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]'), 2),
                        'LTE MAC DL 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & LTE KPI MAC DL Throughput [Mbps]'), 2),
                        'LTE PDSCH 속도 (Mbps)': round(get_col_val(df_binned_long, 'Call & LTE KPI PDSCH Throughput [Mbps]'), 2),
                        '[NR] gNB-Cell ID': tot_enb_cell,
                        '[NR] Serving PCI': int(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF Serving PCI')) if pd.notna(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF Serving PCI')) else tot_pci,
                        '[NR] SS-RSRP (dBm)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF Serving SS-RSRP [dBm]'), 1),
                        '[NR] SS-SINR (dB)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF Serving SS-SINR [dB]'), 1),
                        '[NR] SS-RSRQ (dB)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF Serving SS-RSRQ [dB]'), 1),
                        '[NR] CQI': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF CQI'), 1),
                        '[NR] DL MCS': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL MCS (Avg)'), 1),
                        '[NR] PDSCH BLER (%)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL BLER [%]'), 2),
                        '[NR] DL RB Num (Inc 0)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL RB Num (Including 0)'), 1),
                        '[NR] WB RI': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell RF RI(Avg)'), 1),
                        '[NR] 64QAM Rate (%)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 64QAM Rate [%]'), 1),
                        '[NR] 256QAM Rate (%)': round(get_col_val(df_binned_long, 'Call & 5G KPI PCell Layer1 DL Modulation0 DL 256 QAM Rate [%]'), 1),
                        '[LTE] eNB-Cell ID': tot_enb_cell,
                        '[LTE] Serving PCI': int(get_col_val(df_binned_long, 'Call & LTE KPI PCell Serving PCI')) if pd.notna(get_col_val(df_binned_long, 'Call & LTE KPI PCell Serving PCI')) else tot_pci,
                        '[LTE] Serving RSRP (dBm)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell Serving RSRP [dBm]'), 1),
                        '[LTE] Serving SINR (dB)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell SINR [dB]'), 1),
                        '[LTE] Serving RSRQ (dB)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell Serving RSRQ [dB]'), 1),
                        '[LTE] CQI': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell WB CQI CW0'), 1),
                        '[LTE] DL MCS': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell DL MCS0'), 1),
                        '[LTE] PDSCH BLER (%)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell PDSCH BLER [%]'), 2),
                        '[LTE] DL RB Num (Inc 0)': round(get_col_val(df_binned_long, 'Call & LTE KPI PCell PDSCH PRB Number(Including 0)'), 1),
                        '[LTE] 256QAM Rate (%)': round(get_col_val(df_binned_long, 'Call & LTE KPI SCell[2] DL Modulation0'), 1),
                        '이동속도 (km/h)': gps_spd
                    }

                dl_rows.append(row_dl)

        df_dl_res = pd.DataFrame(dl_rows)
        df_ul_res = pd.DataFrame(ul_rows)
        df_ping_res = pd.DataFrame(ping_rows)
        df_voice_res = pd.DataFrame(voice_rows)

        # Helper to compute and append Average summary row at bottom
        def _append_avg_row(df: pd.DataFrame, label: str = 'Average') -> pd.DataFrame:
            if df.empty: return df
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            avg_dict = {col: round(df[col].mean(), 2) for col in numeric_cols}
            first_col = df.columns[0]
            avg_dict[first_col] = label
            if len(df.columns) > 1 and df.columns[1] in df.columns:
                avg_dict[df.columns[1]] = '-'
            return pd.concat([df, pd.DataFrame([avg_dict])], ignore_index=True)

        return {
            'Total_Summary': df_total_summary,
            'DL': _append_avg_row(df_dl_res),
            'UL': _append_avg_row(df_ul_res),
            'Ping': _append_avg_row(df_ping_res),
            'Voice': _append_avg_row(df_voice_res)
        }

    @classmethod
    def build_unified_master_summaries(cls, drm_name: str, csvs: Dict[str, Optional[str]], df_timeline: Optional[pd.DataFrame], df_qc_kpi: Optional[pd.DataFrame], detected_state: dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Backward-compatibility bridge."""
        summaries = cls.build_scenario_dedicated_summaries(drm_name, csvs, df_timeline, df_qc_kpi, detected_state)
        df_tot = summaries.get('Total_Summary', pd.DataFrame())
        df_c = summaries.get('DL')
        if df_c is None or df_c.empty:
            df_c = summaries.get('Voice')
        if df_c is None or df_c.empty:
            df_c = summaries.get('Ping', pd.DataFrame())
        return df_tot, df_c

    @staticmethod
    def tag_call_traffic_phases(df: Optional[pd.DataFrame], df_call_summary: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """
        Tags Call_Index (int) and Traffic_Phase ('DL', 'UL', 'PING', 'WEB', 'VOICE')
        at the very beginning of the DataFrame.
        """
        if df is None or df.empty or 'TIME_STAMP' not in df.columns:
            return df

        if 'Call_Index' in df.columns and 'Traffic_Phase' in df.columns:
            return df

        df = df.copy()
        s_dt = pd.to_datetime(df['TIME_STAMP'], errors='coerce')

        call_index_arr = np.zeros(len(df), dtype=int)
        traffic_phase_arr = np.full(len(df), 'IDLE', dtype=object)

        if df_call_summary is not None and not df_call_summary.empty:
            for c_idx, c_row in df_call_summary.iterrows():
                st_val = c_row.get('시작 시간') or c_row.get('시간 구간') or c_row.get('Start_Time')
                et_val = c_row.get('종료 시간') or c_row.get('End_Time')
                c_type_raw = str(c_row.get('시나리오') or c_row.get('Call 유형') or 'DL').upper()

                if 'UL' in c_type_raw:
                    phase = 'UL'
                elif 'PING' in c_type_raw:
                    phase = 'PING'
                elif 'WEB' in c_type_raw:
                    phase = 'WEB'
                elif 'VOICE' in c_type_raw or 'VOLTE' in c_type_raw:
                    phase = 'VOICE'
                else:
                    phase = 'DL'

                try:
                    if isinstance(st_val, str) and '~' in st_val:
                        parts = st_val.split('~')
                        base_date = s_dt.dropna().dt.date.iloc[0] if not s_dt.dropna().empty else None
                        if base_date:
                            st_dt = pd.to_datetime(f"{base_date} {parts[0].strip()}", errors='coerce')
                            et_dt = pd.to_datetime(f"{base_date} {parts[1].strip()}", errors='coerce')
                        else:
                            st_dt = pd.to_datetime(parts[0].strip(), errors='coerce')
                            et_dt = pd.to_datetime(parts[1].strip(), errors='coerce')
                    else:
                        st_dt = pd.to_datetime(st_val, errors='coerce')
                        et_dt = pd.to_datetime(et_val, errors='coerce')

                    if pd.notna(st_dt) and pd.notna(et_dt):
                        mask = (s_dt >= st_dt) & (s_dt <= et_dt)
                        call_index_arr[mask] = (c_idx + 1)
                        traffic_phase_arr[mask] = phase
                except Exception:
                    pass

        ts_idx = df.columns.get_loc('TIME_STAMP') if 'TIME_STAMP' in df.columns else 0
        df.insert(ts_idx + 1, 'Call_Index', call_index_arr)
        df.insert(ts_idx + 2, 'Traffic_Phase', traffic_phase_arr)
        return df
