# -*- coding: utf-8 -*-
r"""
File: 4_Optis_AI_Analyzer/core/master_workbook_builder.py
Description: M1~M4 Multi-UE Master Consolidated Excel Workbook Builder (_Master.xlsx)
- Integrates AutoCallSummary Scenario & Traffic vs IDLE Breakdown
- Displays Pure Traffic Performance (Throughput / MOS) without IDLE Dilution
- Provides Dedicated NSA (NR+LTE) and Pure LTE 1-second time-series & Call summaries
- Fully expands SST (Speed Test: DL, UL, Ping) multi-scenario sets
"""

import os
import sys
import re
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows


class MasterWorkbookBuilder:
    """
    Consolidates M1, M2, M3, M4 multi-UE test results into a single standardized Master Excel Workbook.
    """

    def __init__(self):
        pass

    def build_multi_ue_total_summary(
        self,
        port_results: Dict[str, Dict[str, Any]],
        display_name: str
    ) -> pd.DataFrame:
        """
        Builds Sheet 1 '01_통합_요약' executive comparison table across M1~M4.
        """
        rows = []
        for port_key, pdata in port_results.items():
            scenario = pdata.get('scenario', 'DL')
            df_tl = pdata.get('df_timeline', pd.DataFrame())
            df_kpi = pdata.get('df_qc_kpi', pd.DataFrame())
            episodes = pdata.get('episodes', [])
            summaries = pdata.get('summaries', {})

            net_mode = df_tl.attrs.get('Network_Mode', 'LTE') if hasattr(df_tl, 'attrs') else 'LTE'
            vendor = df_tl.attrs.get('Active_Vendor', 'COMMON') if hasattr(df_tl, 'attrs') else 'COMMON'
            traffic_model_code = df_tl.attrs.get('Traffic_Model', scenario.upper()) if hasattr(df_tl, 'attrs') else scenario.upper()

            call_count = 1
            pure_traffic_df = df_tl

            if not df_tl.empty:
                if 'Call_No' in df_tl.columns:
                    call_count = df_tl['Call_No'].nunique()
                
                if 'Call_Phase' in df_tl.columns:
                    traffic_mask = df_tl['Call_Phase'].astype(str).str.contains('Traffic', case=False, na=False)
                    if traffic_mask.sum() > 0:
                        pure_traffic_df = df_tl[traffic_mask]

            tot_pts = len(df_tl) if not df_tl.empty else len(df_kpi)

            # Scenario Label
            if traffic_model_code.startswith('VOICE') or scenario == 'Voice':
                voice_prefix = 'VoNR' if net_mode == 'SA' else 'VoLTE'
                voice_dir_str = 'MO (발신)' if 'MO' in traffic_model_code else ('MT (착신)' if 'MT' in traffic_model_code else 'Voice')
                traffic_model = f"{voice_prefix} {voice_dir_str} ({call_count} Calls)"
                sc_mode_clean = f"{voice_prefix} {voice_dir_str}"
            elif traffic_model_code == 'SST':
                traffic_model = f"{net_mode} SST Speed Test ({call_count} Calls)"
                sc_mode_clean = "SST (속도측정)"
            elif traffic_model_code in ['DL_Long_Call', 'DL_LONG_CALL']:
                traffic_model = f"{net_mode} DL Continuous ({call_count} Calls)"
                sc_mode_clean = "DL Long Call (연속 호)"
            elif traffic_model_code in ['DL_Short_Call', 'DL_SHORT_CALL']:
                traffic_model = f"{net_mode} DL Short Call ({call_count} Calls)"
                sc_mode_clean = "DL Short Call (반복 호)"
            elif traffic_model_code in ['UL_Long_Call', 'UL_LONG_CALL']:
                traffic_model = f"{net_mode} UL Continuous ({call_count} Calls)"
                sc_mode_clean = "UL Long Call (연속 호)"
            elif traffic_model_code in ['UL_Short_Call', 'UL_SHORT_CALL', 'UL']:
                traffic_model = f"{net_mode} UL Short Call ({call_count} Calls)"
                sc_mode_clean = "UL Short Call (반복 호)"
            elif traffic_model_code == 'PING' or scenario == 'Ping':
                traffic_model = f"{net_mode} PING TEST ({call_count} Calls)"
                sc_mode_clean = "PING TEST"
            else:
                traffic_model = f"{net_mode} DL ({call_count} Calls)"
                sc_mode_clean = "DL Long Call (연속 호)" if call_count == 1 else "DL Short Call (반복 호)"

            # Throughput & MOS values
            s_app_dl = pd.to_numeric(pure_traffic_df.get('App_DL_Tput'), errors='coerce').dropna() if 'App_DL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_app_ul = pd.to_numeric(pure_traffic_df.get('App_UL_Tput'), errors='coerce').dropna() if 'App_UL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_pdcp_dl = pd.to_numeric(pure_traffic_df.get('PDCP_DL_Tput'), errors='coerce').dropna() if 'PDCP_DL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_pdcp_ul = pd.to_numeric(pure_traffic_df.get('PDCP_UL_Tput'), errors='coerce').dropna() if 'PDCP_UL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_nr_mac_dl = pd.to_numeric(pure_traffic_df.get('NR_MAC_DL_Tput'), errors='coerce').dropna() if 'NR_MAC_DL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_nr_mac_ul = pd.to_numeric(pure_traffic_df.get('NR_MAC_UL_Tput'), errors='coerce').dropna() if 'NR_MAC_UL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_nr_pdsch = pd.to_numeric(pure_traffic_df.get('NR_PDSCH_Tput'), errors='coerce').dropna() if 'NR_PDSCH_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_nr_pusch = pd.to_numeric(pure_traffic_df.get('NR_PUSCH_Tput'), errors='coerce').dropna() if 'NR_PUSCH_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_lte_mac_dl = pd.to_numeric(pure_traffic_df.get('LTE_MAC_DL_Tput'), errors='coerce').dropna() if 'LTE_MAC_DL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_lte_mac_ul = pd.to_numeric(pure_traffic_df.get('LTE_MAC_UL_Tput'), errors='coerce').dropna() if 'LTE_MAC_UL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_lte_pdsch = pd.to_numeric(pure_traffic_df.get('LTE_PDSCH_Tput'), errors='coerce').dropna() if 'LTE_PDSCH_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_lte_pusch = pd.to_numeric(pure_traffic_df.get('LTE_PUSCH_Tput'), errors='coerce').dropna() if 'LTE_PUSCH_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_mac_dl = pd.to_numeric(pure_traffic_df.get('MAC_DL_Tput', pure_traffic_df.get('LTE_MAC_DL_Tput')), errors='coerce').dropna() if 'MAC_DL_Tput' in pure_traffic_df.columns or 'LTE_MAC_DL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_mac_ul = pd.to_numeric(pure_traffic_df.get('MAC_UL_Tput', pure_traffic_df.get('LTE_MAC_UL_Tput')), errors='coerce').dropna() if 'MAC_UL_Tput' in pure_traffic_df.columns or 'LTE_MAC_UL_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_pdsch = pd.to_numeric(pure_traffic_df.get('PDSCH_Tput', pure_traffic_df.get('LTE_PDSCH_Tput')), errors='coerce').dropna() if 'PDSCH_Tput' in pure_traffic_df.columns or 'LTE_PDSCH_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_pusch = pd.to_numeric(pure_traffic_df.get('PUSCH_Tput', pure_traffic_df.get('LTE_PUSCH_Tput')), errors='coerce').dropna() if 'PUSCH_Tput' in pure_traffic_df.columns or 'LTE_PUSCH_Tput' in pure_traffic_df.columns else pd.Series([], dtype=float)
            
            s_ping = pd.to_numeric(pure_traffic_df.get('SST_Ping_Result'), errors='coerce').dropna() if 'SST_Ping_Result' in pure_traffic_df.columns else pd.Series([], dtype=float)
            s_mos = pd.to_numeric(pure_traffic_df.get('MOS'), errors='coerce').dropna() if 'MOS' in pure_traffic_df.columns else pd.Series([], dtype=float)

            # Check if App DL/UL are truly measured (SST or smartphone FTP) vs modem continuous log
            app_dl_val = s_app_dl[s_app_dl > 0.0].mean() if (not s_app_dl.empty and (s_app_dl > 0.0).sum() > 0) else np.nan
            app_ul_val = s_app_ul[s_app_ul > 0.0].mean() if (not s_app_ul.empty and (s_app_ul > 0.0).sum() > 0) else np.nan
            pdcp_dl_val = s_pdcp_dl[s_pdcp_dl > 0.0].mean() if (not s_pdcp_dl.empty and (s_pdcp_dl > 0.0).sum() > 0) else np.nan
            pdcp_ul_val = s_pdcp_ul[s_pdcp_ul > 0.0].mean() if (not s_pdcp_ul.empty and (s_pdcp_ul > 0.0).sum() > 0) else np.nan
            nr_mac_dl_val = s_nr_mac_dl[s_nr_mac_dl > 0.0].mean() if (not s_nr_mac_dl.empty and (s_nr_mac_dl > 0.0).sum() > 0) else np.nan
            nr_mac_ul_val = s_nr_mac_ul[s_nr_mac_ul > 0.0].mean() if (not s_nr_mac_ul.empty and (s_nr_mac_ul > 0.0).sum() > 0) else np.nan
            nr_pdsch_val = s_nr_pdsch[s_nr_pdsch > 0.0].mean() if (not s_nr_pdsch.empty and (s_nr_pdsch > 0.0).sum() > 0) else np.nan
            nr_pusch_val = s_nr_pusch[s_nr_pusch > 0.0].mean() if (not s_nr_pusch.empty and (s_nr_pusch > 0.0).sum() > 0) else np.nan
            lte_mac_dl_val = s_lte_mac_dl[s_lte_mac_dl > 0.0].mean() if (not s_lte_mac_dl.empty and (s_lte_mac_dl > 0.0).sum() > 0) else np.nan
            lte_mac_ul_val = s_lte_mac_ul[s_lte_mac_ul > 0.0].mean() if (not s_lte_mac_ul.empty and (s_lte_mac_ul > 0.0).sum() > 0) else np.nan
            lte_pdsch_val = s_lte_pdsch[s_lte_pdsch > 0.0].mean() if (not s_lte_pdsch.empty and (s_lte_pdsch > 0.0).sum() > 0) else np.nan
            lte_pusch_val = s_lte_pusch[s_lte_pusch > 0.0].mean() if (not s_lte_pusch.empty and (s_lte_pusch > 0.0).sum() > 0) else np.nan
            mac_dl_val = s_mac_dl[s_mac_dl > 0.0].mean() if (not s_mac_dl.empty and (s_mac_dl > 0.0).sum() > 0) else np.nan
            mac_ul_val = s_mac_ul[s_mac_ul > 0.0].mean() if (not s_mac_ul.empty and (s_mac_ul > 0.0).sum() > 0) else np.nan
            pdsch_val = s_pdsch[s_pdsch > 0.0].mean() if (not s_pdsch.empty and (s_pdsch > 0.0).sum() > 0) else np.nan
            pusch_val = s_pusch[s_pusch > 0.0].mean() if (not s_pusch.empty and (s_pusch > 0.0).sum() > 0) else np.nan
            
            ping_val = s_ping[s_ping > 0.0].mean() if (not s_ping.empty and (s_ping > 0.0).sum() > 0) else np.nan
            mos_val = s_mos[s_mos > 0.0].mean() if (not s_mos.empty and (s_mos > 0.0).sum() > 0) else np.nan

            dl_app_str = f"{app_dl_val:.2f}" if pd.notna(app_dl_val) else "-"
            ul_app_str = f"{app_ul_val:.2f}" if pd.notna(app_ul_val) else "-"
            pdcp_dl_str = f"{pdcp_dl_val:.2f}" if pd.notna(pdcp_dl_val) else "-"
            pdcp_ul_str = f"{pdcp_ul_val:.2f}" if pd.notna(pdcp_ul_val) else "-"
            nr_mac_dl_str = f"{nr_mac_dl_val:.2f}" if pd.notna(nr_mac_dl_val) else "-"
            nr_mac_ul_str = f"{nr_mac_ul_val:.2f}" if pd.notna(nr_mac_ul_val) else "-"
            nr_pdsch_str = f"{nr_pdsch_val:.2f}" if pd.notna(nr_pdsch_val) else "-"
            nr_pusch_str = f"{nr_pusch_val:.2f}" if pd.notna(nr_pusch_val) else "-"
            lte_mac_dl_str = f"{lte_mac_dl_val:.2f}" if pd.notna(lte_mac_dl_val) else "-"
            lte_mac_ul_str = f"{lte_mac_ul_val:.2f}" if pd.notna(lte_mac_ul_val) else "-"
            lte_pdsch_str = f"{lte_pdsch_val:.2f}" if pd.notna(lte_pdsch_val) else "-"
            lte_pusch_str = f"{lte_pusch_val:.2f}" if pd.notna(lte_pusch_val) else "-"
            mac_dl_str = f"{mac_dl_val:.2f}" if pd.notna(mac_dl_val) else "-"
            mac_ul_str = f"{mac_ul_val:.2f}" if pd.notna(mac_ul_val) else "-"
            pdsch_str = f"{pdsch_val:.2f}" if pd.notna(pdsch_val) else "-"
            pusch_str = f"{pusch_val:.2f}" if pd.notna(pusch_val) else "-"
            ping_str = f"{ping_val:.1f}" if pd.notna(ping_val) else "-"
            mos_str = f"{mos_val:.2f}" if pd.notna(mos_val) else "-"

            # RF Quality
            s_nr_rsrp = pd.to_numeric(df_tl.get('NR_SS_RSRP'), errors='coerce').dropna() if 'NR_SS_RSRP' in df_tl.columns else pd.Series([], dtype=float)
            s_nr_sinr = pd.to_numeric(df_tl.get('NR_SS_SINR'), errors='coerce').dropna() if 'NR_SS_SINR' in df_tl.columns else pd.Series([], dtype=float)
            s_lte_rsrp = pd.to_numeric(df_tl.get('LTE_RSRP', df_tl.get('SS_RSRP')), errors='coerce').dropna() if 'LTE_RSRP' in df_tl.columns or 'SS_RSRP' in df_tl.columns else pd.Series([], dtype=float)
            s_lte_sinr = pd.to_numeric(df_tl.get('LTE_SINR', df_tl.get('SS_SINR')), errors='coerce').dropna() if 'LTE_SINR' in df_tl.columns or 'SS_SINR' in df_tl.columns else pd.Series([], dtype=float)

            nr_rsrp_str = f"{s_nr_rsrp.mean():.1f} dBm" if (net_mode == 'NSA' and not s_nr_rsrp.empty) else "-"
            nr_sinr_str = f"{s_nr_sinr.mean():.1f} dB" if (net_mode == 'NSA' and not s_nr_sinr.empty) else "-"
            lte_rsrp_str = f"{s_lte_rsrp.mean():.1f} dBm" if not s_lte_rsrp.empty else "-"
            lte_sinr_str = f"{s_lte_sinr.mean():.1f} dB" if not s_lte_sinr.empty else "-"

            # Calculate real call success count from summaries
            succ_rate_str = "Success"
            if 'Total_Summary' in summaries and isinstance(summaries['Total_Summary'], pd.DataFrame) and not summaries['Total_Summary'].empty:
                tot_stat = summaries['Total_Summary'].get('호 상태')
                if tot_stat is not None and not tot_stat.empty and pd.notna(tot_stat.iloc[0]) and str(tot_stat.iloc[0]) != 'N/A':
                    succ_rate_str = str(tot_stat.iloc[0])

            if succ_rate_str in ["Success", "N/A", "-"]:
                for s_key in ['DL', 'UL', 'Voice', 'Ping']:
                    s_df = summaries.get(s_key)
                    if isinstance(s_df, pd.DataFrame) and not s_df.empty and '호 상태' in s_df.columns:
                        s_calls = s_df[s_df['호 번호'] != 'Average'] if '호 번호' in s_df.columns else s_df
                        if not s_calls.empty:
                            tot_c = len(s_calls)
                            suc_c = int((s_calls['호 상태'].astype(str).str.contains('Success|End by user', case=False)).sum())
                            succ_rate_str = f"{suc_c}/{tot_c} ({suc_c/tot_c*100:.1f}%)" if tot_c > 0 else "Success"
                            break

            rows.append({
                "DRM 파일명": display_name,
                "측정 단말 (UE Port)": port_key,
                "망 모드": net_mode,
                "측정 방식": sc_mode_clean,
                "트래픽 모델": traffic_model,
                "활성 벤더": vendor,
                "호 상태 (성공률)": succ_rate_str,
                "총 측정 초수": tot_pts,
                "App DL 평균 (Mbps)": dl_app_str,
                "PDCP DL 평균 (Mbps)": pdcp_dl_str,
                "[NR] MAC DL 평균 (Mbps)": nr_mac_dl_str if net_mode == 'NSA' else "-",
                "[NR] PDSCH 평균 (Mbps)": nr_pdsch_str if net_mode == 'NSA' else "-",
                "[LTE] MAC DL 평균 (Mbps)": lte_mac_dl_str if net_mode == 'NSA' else mac_dl_str,
                "[LTE] PDSCH 평균 (Mbps)": lte_pdsch_str if net_mode == 'NSA' else pdsch_str,
                "App UL 평균 (Mbps)": ul_app_str,
                "PDCP UL 평균 (Mbps)": pdcp_ul_str,
                "[NR] MAC UL 평균 (Mbps)": nr_mac_ul_str if net_mode == 'NSA' else "-",
                "[NR] PUSCH 평균 (Mbps)": nr_pusch_str if net_mode == 'NSA' else "-",
                "[LTE] MAC UL 평균 (Mbps)": lte_mac_ul_str if net_mode == 'NSA' else mac_ul_str,
                "[LTE] PUSCH 평균 (Mbps)": lte_pusch_str if net_mode == 'NSA' else pusch_str,
                "Ping RTT 평균 (ms)": ping_str,
                "[NR] SS-RSRP 평균 (dBm)": nr_rsrp_str,
                "[NR] SS-SINR 평균 (dB)": nr_sinr_str,
                "[LTE] RSRP 평균 (dBm)": lte_rsrp_str,
                "[LTE] SINR 평균 (dB)": lte_sinr_str,
                "MOS 평균": mos_str
            })

        df_total_summary = pd.DataFrame(rows)
        return df_total_summary

    @staticmethod
    def extract_1sec_time_series_sheet(df_tl: pd.DataFrame, sc_tag: str, net_mode: str = 'LTE') -> pd.DataFrame:
        """
        Builds 1-second time-series DataFrame with exact column ordering matching Call summary.
        Supports dedicated 5G NSA (NR+LTE dual) and pure LTE column layouts.
        """
        if df_tl is None or df_tl.empty:
            return pd.DataFrame()

        rows = []
        is_nsa = (net_mode == 'NSA')

        def _to_flt(val, digits=1, default=np.nan):
            if pd.isna(val): return default
            try:
                return round(float(val), digits)
            except Exception:
                if isinstance(val, str):
                    if '64QAM' in val or '256QAM' in val:
                        return 100.0
                return default

        for idx, row in df_tl.iterrows():
            ts_val = row.get('TIME_STAMP')
            if pd.notna(ts_val):
                try:
                    ts_dt = pd.to_datetime(ts_val)
                    ts_str = ts_dt.strftime('%H:%M:%S')
                except Exception:
                    ts_str = str(ts_val)
                    if ' ' in ts_str:
                        ts_str = ts_str.split(' ')[1]
                    if len(ts_str) > 8:
                        ts_str = ts_str[:8]
            else:
                ts_str = ''

            lon = _to_flt(row.get('Lon'), 6)
            lat = _to_flt(row.get('Lat'), 6)
            call_no = str(row.get('Call_No', 'Call 1'))
            call_phase = str(row.get('Call_Phase', f"{sc_tag}_Traffic"))
            speed = _to_flt(row.get('Speed'), 1)

            # Throughput
            pdcp_dl = _to_flt(row.get('PDCP_DL_Tput'), 2)
            raw_app_dl = _to_flt(row.get('App_DL_Tput'), 2)
            app_dl = raw_app_dl if (pd.notna(raw_app_dl) and raw_app_dl > 0) else np.nan
            pdcp_ul = _to_flt(row.get('PDCP_UL_Tput'), 2)
            raw_app_ul = _to_flt(row.get('App_UL_Tput'), 2)
            app_ul = raw_app_ul if (pd.notna(raw_app_ul) and raw_app_ul > 0) else np.nan
            nr_pdsch = _to_flt(row.get('NR_PDSCH_Tput', row.get('PDSCH_Tput')), 2)
            nr_pusch = _to_flt(row.get('NR_PUSCH_Tput', row.get('PUSCH_Tput')), 2)
            nr_mac_dl = _to_flt(row.get('NR_MAC_DL_Tput'), 2)
            nr_mac_ul = _to_flt(row.get('NR_MAC_UL_Tput'), 2)
            lte_mac_dl = _to_flt(row.get('LTE_MAC_DL_Tput'), 2)
            lte_mac_ul = _to_flt(row.get('LTE_MAC_UL_Tput'), 2)
            lte_pdsch = _to_flt(row.get('LTE_PDSCH_Tput', row.get('PDSCH_Tput')), 2)
            lte_pusch = _to_flt(row.get('LTE_PUSCH_Tput', row.get('PUSCH_Tput')), 2)

            # 5G NR Metrics
            nr_cell_id = str(row.get('NR_Cell_ID', row.get('eNB_Cell_ID', '-')))
            nr_pci = int(float(row['NR_Serving_PCI'])) if pd.notna(row.get('NR_Serving_PCI')) else np.nan
            nr_rsrp = _to_flt(row.get('NR_SS_RSRP', row.get('SS_RSRP')), 2)
            nr_sinr = _to_flt(row.get('NR_SS_SINR', row.get('SS_SINR')), 2)
            nr_rsrq = _to_flt(row.get('NR_SS_RSRQ', row.get('SS_RSRQ')), 2)
            nr_cqi = _to_flt(row.get('NR_CQI', row.get('CQI')), 1)
            nr_dl_mcs = _to_flt(row.get('NR_DL_MCS', row.get('DL_MCS')), 1)
            nr_ul_mcs = _to_flt(row.get('NR_UL_MCS', row.get('UL_MCS')), 1)
            nr_pdsch_bler = _to_flt(row.get('NR_PDSCH_BLER', row.get('PDSCH_BLER')), 2)
            nr_pusch_bler = _to_flt(row.get('NR_PUSCH_BLER', row.get('PUSCH_BLER')), 2)
            nr_dl_prb_inc0 = _to_flt(row.get('NR_PRB_Inc0', row.get('PRB_Num_Inc0')), 1)
            nr_ul_prb_inc0 = _to_flt(row.get('NR_UL_PRB_Inc0'), 1)
            nr_wb_ri = _to_flt(row.get('NR_WB_RI', row.get('WB_RI')), 1)
            nr_pusch_pwr = _to_flt(row.get('NR_PUSCH_Power'), 1)
            nr_qam64 = _to_flt(row.get('NR_QAM64_Rate', row.get('QAM64_Rate')), 1)
            nr_qam256 = _to_flt(row.get('NR_QAM256_Rate', row.get('QAM256_Rate')), 1)

            # LTE Anchor Metrics
            lte_cell_id = str(row.get('eNB_Cell_ID', '-'))
            lte_pci = int(float(row['LTE_Serving_PCI'])) if pd.notna(row.get('LTE_Serving_PCI')) else (int(float(row['Serving_PCI'])) if pd.notna(row.get('Serving_PCI')) else np.nan)
            lte_rsrp = _to_flt(row.get('LTE_RSRP', row.get('SS_RSRP')), 2)
            lte_sinr = _to_flt(row.get('LTE_SINR', row.get('SS_SINR')), 2)
            lte_rsrq = _to_flt(row.get('LTE_RSRQ', row.get('SS_RSRQ')), 2)
            lte_cqi = _to_flt(row.get('LTE_CQI', row.get('CQI')), 1)
            lte_dl_mcs = _to_flt(row.get('LTE_DL_MCS', row.get('DL_MCS')), 1)
            lte_ul_mcs = _to_flt(row.get('LTE_UL_MCS', row.get('UL_MCS')), 1)
            lte_pdsch_bler = _to_flt(row.get('LTE_PDSCH_BLER', row.get('PDSCH_BLER')), 2)
            lte_pusch_bler = _to_flt(row.get('LTE_PUSCH_BLER', row.get('PUSCH_BLER')), 2)
            lte_dl_prb_inc0 = _to_flt(row.get('LTE_PRB_Inc0', row.get('PRB_Num_Inc0')), 1)
            lte_ul_prb_inc0 = _to_flt(row.get('LTE_UL_PRB_Inc0'), 1)
            lte_wb_ri = _to_flt(row.get('LTE_WB_RI', row.get('WB_RI')), 1)
            lte_pusch_pwr = _to_flt(row.get('LTE_PUSCH_Power'), 1)
            lte_qam64 = _to_flt(row.get('LTE_QAM64_Rate'), 1)
            lte_qam256 = _to_flt(row.get('LTE_QAM256_Rate'), 1)

            if is_nsa:
                # -------------------------------------------------------------
                # 5G NSA (NR + LTE Dual Connectivity)
                # -------------------------------------------------------------
                if sc_tag == 'DL':
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'App DL 속도 (Mbps)': app_dl if pd.notna(app_dl) else np.nan,
                        'PDCP DL 속도 (Mbps)': pdcp_dl,
                        'NR MAC DL 속도 (Mbps)': nr_mac_dl,
                        'NR PDSCH 속도 (Mbps)': nr_pdsch,
                        'LTE MAC DL 속도 (Mbps)': lte_mac_dl,
                        'LTE PDSCH 속도 (Mbps)': lte_pdsch,
                        '[NR] gNB-Cell ID': nr_cell_id,
                        '[NR] Serving PCI': nr_pci,
                        '[NR] SS-RSRP (dBm)': nr_rsrp,
                        '[NR] SS-SINR (dB)': nr_sinr,
                        '[NR] SS-RSRQ (dB)': nr_rsrq,
                        '[NR] CQI': nr_cqi,
                        '[NR] DL MCS': nr_dl_mcs,
                        '[NR] PDSCH BLER (%)': nr_pdsch_bler,
                        '[NR] DL RB Num (Inc 0)': nr_dl_prb_inc0,
                        '[NR] WB RI': nr_wb_ri,
                        '[NR] 64QAM Rate (%)': nr_qam64,
                        '[NR] 256QAM Rate (%)': nr_qam256,
                        '[LTE] eNB-Cell ID': lte_cell_id,
                        '[LTE] Serving PCI': lte_pci,
                        '[LTE] Serving RSRP (dBm)': lte_rsrp,
                        '[LTE] Serving SINR (dB)': lte_sinr,
                        '[LTE] Serving RSRQ (dB)': lte_rsrq,
                        '[LTE] CQI': lte_cqi,
                        '[LTE] DL MCS': lte_dl_mcs,
                        '[LTE] PDSCH BLER (%)': lte_pdsch_bler,
                        '[LTE] DL RB Num (Inc 0)': lte_dl_prb_inc0,
                        '[LTE] 256QAM Rate (%)': lte_qam256,
                        '이동속도 (km/h)': speed
                    })
                elif sc_tag == 'UL':
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'App UL 속도 (Mbps)': app_ul if pd.notna(app_ul) else np.nan,
                        'PDCP UL 속도 (Mbps)': pdcp_ul,
                        'NR MAC UL 속도 (Mbps)': nr_mac_ul,
                        'NR PUSCH 속도 (Mbps)': nr_pusch,
                        'LTE MAC UL 속도 (Mbps)': lte_mac_ul,
                        'LTE PUSCH 속도 (Mbps)': lte_pusch,
                        '[NR] gNB-Cell ID': nr_cell_id,
                        '[NR] Serving PCI': nr_pci,
                        '[NR] SS-RSRP (dBm)': nr_rsrp,
                        '[NR] SS-SINR (dB)': nr_sinr,
                        '[NR] SS-RSRQ (dB)': nr_rsrq,
                        '[NR] CQI': nr_cqi,
                        '[NR] UL MCS': nr_ul_mcs,
                        '[NR] PUSCH BLER (%)': nr_pusch_bler,
                        '[NR] UL RB Num (Inc 0)': nr_ul_prb_inc0,
                        '[NR] WB RI': nr_wb_ri,
                        '[NR] PUSCH Power (dBm)': nr_pusch_pwr,
                        '[NR] 64QAM Rate (%)': nr_qam64,
                        '[NR] 256QAM Rate (%)': nr_qam256,
                        '[LTE] eNB-Cell ID': lte_cell_id,
                        '[LTE] Serving PCI': lte_pci,
                        '[LTE] Serving RSRP (dBm)': lte_rsrp,
                        '[LTE] Serving SINR (dB)': lte_sinr,
                        '[LTE] Serving RSRQ (dB)': lte_rsrq,
                        '[LTE] CQI': lte_cqi,
                        '[LTE] UL MCS': lte_ul_mcs,
                        '[LTE] PUSCH BLER (%)': lte_pusch_bler,
                        '[LTE] UL RB Num (Inc 0)': lte_ul_prb_inc0,
                        '[LTE] PUSCH Power (dBm)': lte_pusch_pwr,
                        '이동속도 (km/h)': speed
                    })
                elif sc_tag == 'Ping':
                    ping_rtt = round(float(row.get('SST_Ping_Result')), 1) if pd.notna(row.get('SST_Ping_Result')) else np.nan
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'Ping RTT (ms)': ping_rtt,
                        '[NR] gNB-Cell ID': nr_cell_id,
                        '[NR] Serving PCI': nr_pci,
                        '[NR] SS-RSRP (dBm)': nr_rsrp,
                        '[NR] SS-SINR (dB)': nr_sinr,
                        '[NR] CQI': nr_cqi,
                        '[LTE] eNB-Cell ID': lte_cell_id,
                        '[LTE] Serving PCI': lte_pci,
                        '[LTE] Serving RSRP (dBm)': lte_rsrp,
                        '[LTE] Serving SINR (dB)': lte_sinr,
                        '[LTE] CQI': lte_cqi,
                        '이동속도 (km/h)': speed
                    })
                else: # Voice
                    mos = round(float(row.get('MOS')), 2) if pd.notna(row.get('MOS')) else np.nan
                    codec = str(row.get('Codec', 'AMR-WB')) if pd.notna(row.get('Codec')) else 'AMR-WB'
                    loss = round(float(row.get('Packet_Loss')), 2) if pd.notna(row.get('Packet_Loss')) else np.nan
                    jitter = round(float(row.get('Jitter')), 1) if pd.notna(row.get('Jitter')) else np.nan
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'MOS': mos,
                        'Voice Codec': codec,
                        'DL RTP Packet Loss (%)': loss,
                        'RTP Jitter (ms)': jitter,
                        '[NR] Serving PCI': nr_pci,
                        '[NR] SS-RSRP (dBm)': nr_rsrp,
                        '[LTE] eNB-Cell ID': lte_cell_id,
                        '[LTE] Serving PCI': lte_pci,
                        '[LTE] Serving RSRP (dBm)': lte_rsrp,
                        '[LTE] Serving SINR (dB)': lte_sinr,
                        '이동속도 (km/h)': speed
                    })
            else:
                # -------------------------------------------------------------
                # Pure LTE Mode
                # -------------------------------------------------------------
                if sc_tag == 'DL':
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'App DL 속도 (Mbps)': app_dl if pd.notna(app_dl) else np.nan,
                        'PDCP DL 속도 (Mbps)': pdcp_dl,
                        'MAC DL 속도 (Mbps)': lte_mac_dl,
                        'PDSCH 속도 (Mbps)': lte_pdsch,
                        'PCell eNB-Cell ID': lte_cell_id,
                        'Serving PCI': lte_pci,
                        'Serving RSRP (dBm)': lte_rsrp,
                        'Serving SINR (dB)': lte_sinr,
                        'Serving RSRQ (dB)': lte_rsrq,
                        'CQI': lte_cqi,
                        'DL MCS': lte_dl_mcs,
                        'PDSCH BLER (%)': lte_pdsch_bler,
                        'DL RB Num (Inc 0)': lte_dl_prb_inc0,
                        'RI (Rank Indicator)': lte_wb_ri,
                        '64QAM Rate (%)': lte_qam64,
                        '256QAM Rate (%)': lte_qam256,
                        '이동속도 (km/h)': speed
                    })
                elif sc_tag == 'UL':
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'App UL 속도 (Mbps)': app_ul if pd.notna(app_ul) else np.nan,
                        'PDCP UL 속도 (Mbps)': pdcp_ul,
                        'MAC UL 속도 (Mbps)': lte_mac_ul,
                        'PUSCH 속도 (Mbps)': lte_pusch,
                        'PCell eNB-Cell ID': lte_cell_id,
                        'Serving PCI': lte_pci,
                        'Serving RSRP (dBm)': lte_rsrp,
                        'Serving SINR (dB)': lte_sinr,
                        'Serving RSRQ (dB)': lte_rsrq,
                        'CQI': lte_cqi,
                        'UL MCS': lte_ul_mcs,
                        'PUSCH BLER (%)': lte_pusch_bler,
                        'UL RB Num (Inc 0)': lte_ul_prb_inc0,
                        'RI (Rank Indicator)': lte_wb_ri,
                        'PUSCH Power (dBm)': lte_pusch_pwr,
                        '이동속도 (km/h)': speed
                    })
                elif sc_tag == 'Voice':
                    mos = round(float(row.get('MOS')), 2) if pd.notna(row.get('MOS')) else np.nan
                    codec = str(row.get('Codec', 'AMR-WB')) if pd.notna(row.get('Codec')) else 'AMR-WB'
                    loss = round(float(row.get('Packet_Loss')), 2) if pd.notna(row.get('Packet_Loss')) else np.nan
                    jitter = round(float(row.get('Jitter')), 1) if pd.notna(row.get('Jitter')) else np.nan
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'MOS': mos,
                        'Voice Codec': codec,
                        'DL RTP Packet Loss (%)': loss,
                        'RTP Jitter (ms)': jitter,
                        'PCell eNB-Cell ID': lte_cell_id,
                        'Serving PCI': lte_pci,
                        'Serving RSRP (dBm)': lte_rsrp,
                        'Serving SINR (dB)': lte_sinr,
                        'Serving RSRQ (dB)': lte_rsrq,
                        'CQI': lte_cqi,
                        '이동속도 (km/h)': speed
                    })
                else: # Ping
                    ping_rtt = round(float(row.get('SST_Ping_Result')), 1) if pd.notna(row.get('SST_Ping_Result')) else np.nan
                    rows.append({
                        '시간': ts_str,
                        'Lon': lon,
                        'Lat': lat,
                        '호 번호': call_no,
                        '호 상태/구간': call_phase,
                        'Ping RTT (ms)': ping_rtt,
                        'PCell eNB-Cell ID': lte_cell_id,
                        'Serving PCI': lte_pci,
                        'Serving RSRP (dBm)': lte_rsrp,
                        'Serving SINR (dB)': lte_sinr,
                        'Serving RSRQ (dB)': lte_rsrq,
                        'CQI': lte_cqi,
                        '이동속도 (km/h)': speed
                    })

        return pd.DataFrame(rows)

    STANDARD_34_HEADERS = [
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

    HEADER_TO_SOURCE_COLS = {
        '시간 (구간)': ['TIME_STAMP', '시간 구간', '시간'],
        'Lon': ['[Call & GPS Lon]', 'Lon', '경도'],
        'Lat': ['[Call & GPS Lat]', 'Lat', '위도'],
        '호 번호': ['Call_No', 'Call_Index', '[Call & Call State Call No]', '호 번호'],
        '호 상태 (성공률)': ['Call_Phase', '[Call & Call State Call Event]', '호 상태', '호 상태/구간'],
        'App DL 속도 (Mbps)': ['[Call & Speed Test T-put Current App Throughput [Mbps]]', '[Call & APP Throughput Info(All Data) All FWD  Throughput (kbps)]', 'App_DL_Tput', 'App DL 속도 (Mbps)', 'App DL 속도'],
        'PDCP DL 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]', '[Call & LTE KPI PDCP DL Throughput [Mbps]]', 'PDCP_DL_Tput', 'PDCP DL 속도 (Mbps)', 'PDCP DL 속도'],
        'NR MAC DL 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]', 'NR_MAC_DL_Tput', '5G NR MAC Total (Mbps)', 'NR MAC DL 속도 (Mbps)', 'NR MAC DL 속도'],
        'NR PDSCH 속도 (Mbps)': ['[Call & 5G KPI Total Info Layer1 PDSCH Throughput [Mbps]]', '[Call & 5G KPI PCell Layer1 PDSCH Throughput [Mbps]]', 'NR_PDSCH_Tput', 'PDSCH 속도 (Mbps)'],
        'LTE MAC DL 속도 (Mbps)': ['[Call & LTE KPI MAC DL Throughput [Mbps]]', '[Call & LTE KPI Total Info Layer2 MAC DL Throughput [Mbps]]', 'LTE_MAC_DL_Tput', 'LTE MAC Total (Mbps)', 'LTE MAC DL 속도 (Mbps)', 'MAC DL 속도 (Mbps)'],
        'LTE PDSCH 속도 (Mbps)': ['[Call & LTE KPI PDSCH Throughput [Mbps]]', 'LTE_PDSCH_Tput', 'PDSCH 속도 (Mbps)'],
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
        '[LTE] eNB-Cell ID': ['[Call & LTE KPI PCell Serving eNB ID-Cell ID]', 'eNB_Cell_ID', 'LTE PCell eNB-Cell ID', 'PCell eNB-Cell ID'],
        '[LTE] Serving PCI': ['[Call & LTE KPI PCell Serving PCI]', 'LTE_Serving_PCI', 'LTE PCell PCI', 'Serving PCI'],
        '[LTE] Serving RSRP (dBm)': ['[Call & LTE KPI PCell Serving RSRP [dBm]]', 'LTE_RSRP', 'LTE PCell RSRP (dBm)', 'Serving RSRP (dBm)'],
        '[LTE] Serving SINR (dB)': ['[Call & LTE KPI PCell SINR [dB]]', 'LTE_SINR', 'LTE PCell SINR (dB)', 'Serving SINR (dB)'],
        '[LTE] Serving RSRQ (dB)': ['[Call & LTE KPI PCell Serving RSRQ [dB]]', 'LTE_RSRQ', 'LTE PCell RSRQ (dB)', 'Serving RSRQ (dB)'],
        '[LTE] CQI': ['[Call & LTE KPI PCell WB CQI CW0]', 'LTE_CQI', 'LTE PCell WB CQI', 'CQI'],
        '[LTE] DL MCS': ['[Call & LTE KPI PCell DL MCS0]', 'LTE_DL_MCS', 'LTE PCell DL MCS', 'DL MCS'],
        '[LTE] PDSCH BLER (%)': ['[Call & LTE KPI PCell PDSCH BLER [%]]', 'LTE_PDSCH_BLER', 'LTE PCell PDSCH BLER (%)', 'PDSCH BLER (%)'],
        '[LTE] DL RB Num (Inc 0)': ['[Call & LTE KPI PCell PDSCH PRB Number(Including 0)]', 'LTE_PRB_Inc0', 'LTE PCell PRB Num (inc0)', 'DL RB Num (Inc 0)'],
        '[LTE] 256QAM Rate (%)': ['[Call & LTE KPI SCell[2] DL Modulation0]', 'LTE_QAM256_Rate', 'LTE 256QAM (%)', '256QAM Rate (%)'],
        '이동속도 (km/h)': ['[Call & GPS Speed (km/h)]', 'Speed', 'GPS 속도 (km/h)', '이동속도 (km/h)']
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
        else: # mean
            s_num = pd.to_numeric(s, errors='coerce').dropna()
            if not s_num.empty:
                return round(float(s_num.mean()), 2)
            return s.iloc[0]

    def _extract_1sec_rows(self, df_tl: pd.DataFrame) -> List[Dict[str, Any]]:
        rows = []
        if df_tl is None or df_tl.empty:
            return rows

        for _, r in df_tl.iterrows():
            row_dict = {}
            for h in self.STANDARD_34_HEADERS:
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
                        elif any(k in h for k in ['RSRP', 'SINR', 'RSRQ', '이동속도']):
                            try:
                                row_dict[h] = round(float(val), 1)
                            except Exception:
                                row_dict[h] = val
                        elif any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM']):
                            try:
                                row_dict[h] = round(float(val), 2)
                            except Exception:
                                row_dict[h] = val
                        elif any(k in h for k in ['PCI', 'Cell ID', 'CQI', 'MCS', 'RB Num', 'RI']):
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

    def _extract_call_rows(self, df_tl: pd.DataFrame, summaries: Dict[str, Any], scenario: str) -> List[Dict[str, Any]]:
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

            # Pure traffic sub-group to avoid IDLE dilution
            traffic_mask = grp['Call_Phase'].astype(str).str.contains('Traffic', case=False, na=False) if 'Call_Phase' in grp.columns else pd.Series(True, index=grp.index)
            traffic_grp = grp[traffic_mask] if traffic_mask.sum() > 0 else grp

            row_dict['시간 (구간)'] = f"{st_str} ~ {et_str}"
            row_dict['호 번호'] = call_label
            row_dict['호 상태 (성공률)'] = "Success"

            for h in self.STANDARD_34_HEADERS:
                if h in ['시간 (구간)', '호 번호', '호 상태 (성공률)']:
                    continue
                elif h in ['Lon', 'Lat']:
                    row_dict[h] = self._get_val_from_df(traffic_grp, h, agg='first')
                elif any(k in h for k in ['Cell ID', 'PCI']):
                    row_dict[h] = self._get_val_from_df(traffic_grp, h, agg='mode')
                else:
                    val = self._get_val_from_df(traffic_grp, h, agg='mean')
                    row_dict[h] = val if pd.notna(val) else ""
            call_rows.append(row_dict)

        return call_rows

    def _extract_total_summary_row(self, df_tl: pd.DataFrame, call_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        row_dict = {}
        if df_tl is None or df_tl.empty:
            for h in self.STANDARD_34_HEADERS:
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

        for h in self.STANDARD_34_HEADERS:
            if h in ['시간 (구간)', '호 번호', '호 상태 (성공률)']:
                continue
            elif h in ['Lon', 'Lat']:
                row_dict[h] = self._get_val_from_df(traffic_df, h, agg='first')
            elif any(k in h for k in ['Cell ID', 'PCI']):
                row_dict[h] = self._get_val_from_df(traffic_df, h, agg='mode')
            else:
                val = self._get_val_from_df(traffic_df, h, agg='mean')
                row_dict[h] = val if pd.notna(val) else ""

        return row_dict

    def write_3tier_vertical_sheet(self, ws, port_key: str, pdata: Dict[str, Any]):
        """
        Writes a single consolidated worksheet per port with 3 vertical tiers:
        - [1. 전체 종합 요약]
        - [2. Call 단위 결과]
        - [3. 초(sec) 단위 결과]
        All 3 tiers share the exact same 34 standard column headers.
        """
        df_tl = pdata.get('df_timeline', pd.DataFrame())
        summaries = pdata.get('summaries', {})
        scenario = pdata.get('scenario', 'DL')

        sec_rows = self._extract_1sec_rows(df_tl)
        call_rows = self._extract_call_rows(df_tl, summaries, scenario)
        tot_row = self._extract_total_summary_row(df_tl, call_rows)

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
        # Title Row
        ws.cell(row=cur_row, column=1, value=f"■ [1. {port_key} 전체 종합 요약]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_tot_title
        ws.cell(row=cur_row, column=1).alignment = align_left
        for c_idx in range(2, len(self.STANDARD_34_HEADERS) + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.fill = fill_tot_title
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

        # Header Row
        for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_tot_hdr
            cell.alignment = align_center
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        # Data Row (1 row)
        for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
            val = tot_row.get(h, "")
            cell = ws.cell(row=cur_row, column=c_idx, value=val)
            cell.font = tot_data_font
            cell.fill = fill_tot_row
            cell.border = border_all
            if isinstance(val, (int, float)):
                cell.alignment = align_right
                cell.number_format = '0.00' if any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'Lon', 'Lat']) else '0.0'
            else:
                cell.alignment = align_center
        ws.row_dimensions[cur_row].height = 20
        cur_row += 1

        # Blank Spacer Row
        ws.row_dimensions[cur_row].height = 14
        cur_row += 1

        # =====================================================================
        # [블록 2: Call 단위 결과]
        # =====================================================================
        # Title Row
        ws.cell(row=cur_row, column=1, value=f"■ [2. {port_key} Call 단위 결과]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_call_title
        ws.cell(row=cur_row, column=1).alignment = align_left
        for c_idx in range(2, len(self.STANDARD_34_HEADERS) + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.fill = fill_call_title
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

        # Header Row
        for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_call_hdr
            cell.alignment = align_center
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        # Data Rows
        for r_idx, c_row in enumerate(call_rows):
            row_fill = fill_call_row1 if (r_idx % 2 == 0) else fill_call_row2
            for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
                val = c_row.get(h, "")
                cell = ws.cell(row=cur_row, column=c_idx, value=val)
                cell.font = data_font
                cell.fill = row_fill
                cell.border = border_all
                if isinstance(val, (int, float)):
                    cell.alignment = align_right
                    cell.number_format = '0.00' if any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'Lon', 'Lat']) else '0.0'
                else:
                    cell.alignment = align_center
            ws.row_dimensions[cur_row].height = 19
            cur_row += 1

        # Blank Spacer Row
        ws.row_dimensions[cur_row].height = 14
        cur_row += 1

        # =====================================================================
        # [블록 3: 초(sec) 단위 결과]
        # =====================================================================
        # Title Row
        ws.cell(row=cur_row, column=1, value=f"■ [3. {port_key} 초(sec) 단위 결과]")
        ws.cell(row=cur_row, column=1).font = title_font
        ws.cell(row=cur_row, column=1).fill = fill_sec_title
        ws.cell(row=cur_row, column=1).alignment = align_left
        for c_idx in range(2, len(self.STANDARD_34_HEADERS) + 1):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.fill = fill_sec_title
        ws.row_dimensions[cur_row].height = 24
        cur_row += 1

        # Header Row
        for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
            cell = ws.cell(row=cur_row, column=c_idx, value=h)
            cell.font = hdr_font
            cell.fill = fill_sec_hdr
            cell.alignment = align_center
            cell.border = border_all
        ws.row_dimensions[cur_row].height = 22
        cur_row += 1

        # Data Rows
        for r_idx, s_row in enumerate(sec_rows):
            row_fill = fill_sec_row1 if (r_idx % 2 == 0) else fill_sec_row2
            for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
                val = s_row.get(h, "")
                cell = ws.cell(row=cur_row, column=c_idx, value=val)
                cell.font = data_font
                cell.fill = row_fill
                cell.border = border_all
                if isinstance(val, (int, float)):
                    cell.alignment = align_right
                    cell.number_format = '0.00' if any(k in h for k in ['속도', 'Tput', 'BLER', 'Rate', 'QAM', 'Lon', 'Lat']) else '0.0'
                else:
                    cell.alignment = align_center
            ws.row_dimensions[cur_row].height = 18
            cur_row += 1

        # Column width optimization
        for c_idx, h in enumerate(self.STANDARD_34_HEADERS, start=1):
            col_letter = get_column_letter(c_idx)
            h_len = max(len(str(h)) * 1.5, 12)
            ws.column_dimensions[col_letter].width = min(max(h_len, 12), 26)

    def build_master_consolidated_excel(
        self,
        port_results: Dict[str, Dict[str, Any]],
        display_name: str,
        output_xlsx_path: str
    ) -> str:
        """
        Builds the consolidated Multi-Port Master Excel file.
        Layout:
        - Exactly 1 Sheet per active port (e.g. M1, M2, M3, M4)
          Each sheet vertically integrates:
            [1. 전체 종합 요약]
            (1 blank row)
            [2. Call 단위 결과]
            (1 blank row)
            [3. 초(sec) 단위 결과]
          using identical 34 standard summary columns.
        - Preserved engineering inspection sheets:
            L3_단일파라미터_감사, L3_복합구조체_감사, Mobility_Meas
        """
        os.makedirs(os.path.dirname(output_xlsx_path), exist_ok=True)
        wb = openpyxl.Workbook()
        default_sheet = wb.active

        # 1. Create dedicated 3-tier vertical sheet for each Port
        created_port_sheets = []
        for port_key, pdata in port_results.items():
            ws = wb.create_sheet(title=port_key)
            self.write_3tier_vertical_sheet(ws, port_key, pdata)
            created_port_sheets.append(ws)

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
