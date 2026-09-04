# -*- coding: utf-8 -*-
"""
===============================================================================
Module Name   : optis_pipeline_runner.py
Location      : 5_Optis_Web_App/core/optis_pipeline_runner.py
Description   : Complete non-UI analysis pipeline copied 100% directly from Optis AI Analyzer v12.
                - 1:1 Isolated Multi-Port ZIP Extraction & Companion Matching
                - 3GPP ASN.1 L3 Full Parser (EUTRARRCDefinitionsV1930 & NRRRCDefinitionsV1930)
                - Master Timeline SSOT (4-Stage Pipeline)
                - 160-Slot Matrix & L3 Parameter Audit (Cross-PCI Comparative Audit)
                - Mobility Measurements Master Table Synthesis
                - Domain 00~08 Modular Diagnosis (Extracting All 7+ Incidents on M1)
                - In-Memory Master Workbook (.xlsx), 2D GIS Map (.html), and Text Reports
===============================================================================
"""

import os
import sys
import re
import zipfile
import tempfile
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

parsers_dir = os.path.join(current_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

visualizers_dir = os.path.join(current_dir, "visualizers")
if visualizers_dir not in sys.path:
    sys.path.insert(0, visualizers_dir)

from core.parsers.master_timeline_parser import MasterTimelineParser, safe_read_csv
from core.parsers.pci_state_tracker import PCIStateTracker
from core.parsers.ts_36331_v1930_eutra_rrc_definitions import EUTRARRCDefinitionsV1930
from core.parsers.ts_38331_v1930_nr_rrc_definitions import NRRRCDefinitionsV1930
from core.parsers.slot_matrix_parser import SlotMatrixParser
from core.parsers.l3_cell_parameter_auditor import L3CellParameterAuditor
from core.parsers.mobility_measurement_parser import MobilityMeasurementParser
from core.parsers.dl_rs_parser import DLRSParser
from core.parsers.ul_rs_parser import ULRSParser
from core.network_state_tracker import NetworkStateTracker
from core.diagnosis_reporter import DiagnosisReporter
from core.kpi_summary_engine import KPISummaryEngine
from core.master_workbook_builder import MasterWorkbookBuilder
from core.visualizers.interactive_map_builder import InteractiveMapBuilder


def clean_drm_name(filename_or_path: str) -> str:
    base = os.path.basename(filename_or_path)
    if base.lower().endswith('.zip'):
        base = base[:-4]
    if base.lower().endswith('.csv'):
        base = base[:-4]
    m = re.search(r'^(.*?[-_]M\d+)', base, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return base


def extract_route_group_key(name_or_path: str) -> str:
    base = os.path.basename(name_or_path)
    if base.lower().endswith('.zip'):
        base = base[:-4]
    if base.lower().endswith('.csv'):
        base = base[:-4]
    m = re.split(r'[-_#]M\d+', base, flags=re.IGNORECASE)
    if m and len(m) > 0 and m[0].strip():
        return m[0].strip()
    return base


def compute_smart_port_keys(display_names: list) -> list:
    parsed = []
    for i, name in enumerate(display_names):
        m_m = re.search(r'M([1-4])', name, re.I)
        m_r = re.search(r'-R([0-9]+)', name, re.I)
        m_s = re.search(r'-S([0-9]+)', name, re.I)
        parsed.append({
            'idx': i + 1,
            'm': f"M{m_m.group(1)}" if m_m else None,
            'r': f"R{m_r.group(1)}" if m_r else None,
            's': f"S{m_s.group(1)}" if m_s else None
        })

    m_list = [p['m'] for p in parsed]
    if all(m is not None for m in m_list) and len(set(m_list)) == len(display_names):
        return m_list

    mr_list = []
    for p in parsed:
        m_str = p['m'] if p['m'] else f"M{p['idx']}"
        r_str = f"-{p['r']}" if p['r'] else ""
        mr_list.append(f"{m_str}{r_str}")

    if len(set(mr_list)) == len(display_names):
        return mr_list

    return [f"M{i+1}" for i in range(len(display_names))]


class OptisPipelineRunner:
    """
    Direct non-UI execution engine replicating 100% of Optis AI Analyzer v12.
    """

    def __init__(self):
        self.timeline_parser = MasterTimelineParser()
        self.matrix_parser = SlotMatrixParser()
        self.kpi_engine = KPISummaryEngine()
        self.auditor = L3CellParameterAuditor()
        self.mob_parser = MobilityMeasurementParser()
        self.dl_parser = DLRSParser()
        self.ul_parser = ULRSParser()
        self.wb_builder = MasterWorkbookBuilder()
        self.map_builder = InteractiveMapBuilder()

    def extract_and_map_zip_files(self, zip_paths: List[str], work_dir: str) -> Dict[str, Dict[str, str]]:
        """
        Extracts each ZIP file into an isolated directory and builds the 12-CSV dictionary per DRM.
        """
        extracted_dict = {}

        for z_idx, zp in enumerate(zip_paths, 1):
            base_name = os.path.basename(zp).replace('.zip', '')
            display_name = clean_drm_name(zp)
            target_dir = os.path.join(work_dir, f"extract_port_{z_idx}_{base_name}")
            os.makedirs(target_dir, exist_ok=True)

            try:
                with zipfile.ZipFile(zp, 'r') as zf:
                    zf.extractall(target_dir)
            except Exception as e:
                print(f"[!] ZIP extraction failed for {zp}: {e}")
                continue

            extracted_csvs = []
            for root, _, files in os.walk(target_dir):
                for f in files:
                    if f.lower().endswith('.csv'):
                        extracted_csvs.append(os.path.join(root, f))

            csvs = {}
            for fpath in extracted_csvs:
                fname_lower = os.path.basename(fpath).lower()
                if 'qc_kpi' in fname_lower:
                    csvs['KPI'] = fpath
                elif 'messagebrowser' in fname_lower or 'fav_l3_msg' in fname_lower:
                    csvs['L3_MSG'] = fpath
                elif 'event_(detail)' in fname_lower or 'event_detail' in fname_lower:
                    csvs['EVENT_DETAIL'] = fpath
                elif 'event' in fname_lower and 'detail' not in fname_lower:
                    csvs['EVENT'] = fpath
                elif 'smart_phone' in fname_lower:
                    csvs['SMART_PHONE'] = fpath
                elif 'rtp' in fname_lower:
                    csvs['RTP'] = fpath
                elif 'call_result' in fname_lower:
                    csvs['CALL_RESULT'] = fpath
                elif 'mac_csf' in fname_lower:
                    csvs['MAC_CSF'] = fpath
                elif 'mac_dl_dci' in fname_lower:
                    csvs['MAC_DL_DCI'] = fpath
                elif 'mac_pdsch' in fname_lower:
                    csvs['MAC_PDSCH'] = fpath
                elif 'mac_ul_dci' in fname_lower:
                    csvs['MAC_UL_DCI'] = fpath
                elif 'mac_ul_phy_cha_pc' in fname_lower:
                    csvs['MAC_UL_PC'] = fpath
                elif 'mac_ul_phy_cha_sche' in fname_lower:
                    csvs['MAC_UL_SCHE'] = fpath

            # Fallback for KPI if named differently
            if 'KPI' not in csvs:
                for fpath in extracted_csvs:
                    if 'kpi' in os.path.basename(fpath).lower() and 'message' not in os.path.basename(fpath).lower():
                        csvs['KPI'] = fpath
                        break

            extracted_dict[display_name] = csvs

        return extracted_dict

    def run(self, zip_paths: List[str]) -> Dict[str, Any]:
        """
        Executes the exact 12-step v12 analysis pipeline for all provided ZIP files.
        """
        if not zip_paths:
            return {}

        def natural_sort_key(s: str):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

        sorted_zip_paths = sorted(zip_paths, key=natural_sort_key)

        with tempfile.TemporaryDirectory(prefix="optis_exec_") as work_dir:
            extracted_dict = self.extract_and_map_zip_files(sorted_zip_paths, work_dir)
            if not extracted_dict:
                return {}

            drm_names = sorted(list(extracted_dict.keys()), key=natural_sort_key)
            smart_port_keys = compute_smart_port_keys(drm_names)
            port_results_list = []

            for drm_idx, display_name in enumerate(drm_names, 1):
                csvs = extracted_dict.get(display_name, {})
                port_key = smart_port_keys[drm_idx - 1] if drm_idx - 1 < len(smart_port_keys) else f"M{drm_idx}"

                # A. Raw KPI Load
                kpi_csv = csvs.get('KPI')
                df_qc_kpi = safe_read_csv(kpi_csv)
                if df_qc_kpi is None:
                    df_qc_kpi = pd.DataFrame()

                # B. L3 Full-Text RRC Parsing & Dynamic State Machine
                l3_csv = csvs.get('L3_MSG')
                all_l3 = {}
                l3_lines = []

                if l3_csv and os.path.exists(l3_csv):
                    try:
                        with open(l3_csv, 'r', encoding='utf-8', errors='ignore') as f_l3:
                            l3_lines = f_l3.readlines()
                    except Exception:
                        try:
                            with open(l3_csv, 'r', encoding='cp949', errors='ignore') as f_l3:
                                l3_lines = f_l3.readlines()
                        except Exception:
                            l3_lines = []

                    if l3_lines:
                        tracker_lte = PCIStateTracker()
                        tracker_nr = PCIStateTracker()
                        lte_parser = EUTRARRCDefinitionsV1930()
                        nr_parser = NRRRCDefinitionsV1930()

                        lte_tables = lte_parser.parse_all_lte_tables(l3_lines, tracker_lte)
                        nr_tables = nr_parser.parse_all_nr_tables(l3_lines, tracker_nr)
                        all_l3 = {**lte_tables, **nr_tables}
                        all_l3['_raw_lines'] = l3_lines

                tracker = NetworkStateTracker()
                if all_l3:
                    tracker.update_from_tables(all_l3)
                for l in (l3_lines[:300] if l3_lines else []):
                    tracker.update_from_line(l, all_l3)
                detected_state = tracker.get_state()
                active_vendor = detected_state['Active_Vendor']
                network_mode = detected_state['Network_Mode']

                # D. SSOT Master Timeline Table & Scenario Dedicated Summaries
                df_timeline = self.timeline_parser.build_master_timeline(
                    csvs, all_l3=all_l3, detected_state=detected_state, port_key=port_key
                )
                if df_timeline is None or df_timeline.empty:
                    continue

                summaries = self.kpi_engine.build_scenario_dedicated_summaries(
                    display_name, csvs, df_timeline, df_qc_kpi, detected_state
                )

                traffic_model_code = df_timeline.attrs.get('Traffic_Model', 'DL_Long_Call') if hasattr(df_timeline, 'attrs') else 'DL_Long_Call'
                if traffic_model_code == 'SST' or (summaries.get('DL') is not None and summaries.get('UL') is not None and not summaries.get('DL').empty and not summaries.get('UL').empty):
                    call_summary_list = [summaries.get(k) for k in ['DL', 'UL', 'Ping'] if summaries.get(k) is not None and not summaries.get(k).empty]
                    df_c_sum = pd.concat(call_summary_list, ignore_index=True) if call_summary_list else summaries.get('DL', pd.DataFrame())
                elif traffic_model_code.startswith('VOICE') or (summaries.get('Voice') is not None and not summaries.get('Voice').empty):
                    df_c_sum = summaries.get('Voice', pd.DataFrame())
                elif traffic_model_code.startswith('UL') or (summaries.get('UL') is not None and not summaries.get('UL').empty):
                    df_c_sum = summaries.get('UL', pd.DataFrame())
                elif traffic_model_code == 'PING' or (summaries.get('Ping') is not None and not summaries.get('Ping').empty):
                    df_c_sum = summaries.get('Ping', pd.DataFrame())
                else:
                    df_c_sum = summaries.get('DL', pd.DataFrame())

                if df_c_sum is not None and not df_c_sum.empty:
                    df_qc_kpi = KPISummaryEngine.tag_call_traffic_phases(df_qc_kpi, df_c_sum)

                # E. 160-Slot 2D Matrices & Mobility/RS Table Synthesis
                valid_matrices = self.matrix_parser.compute_all_matrices(csvs)

                df_l3_scalar, df_l3_struct = self.auditor.build_audit_dataframes(
                    l3_source=all_l3.get('_raw_lines', l3_csv) if all_l3 else l3_csv,
                    kpi_file_path=kpi_csv,
                    df_timeline=df_timeline
                )

                df_smart_phone = safe_read_csv(csvs.get('SMART_PHONE'))
                df_mob_sheet = self.mob_parser.parse(all_l3 if all_l3 else df_qc_kpi, df_kpi=df_qc_kpi, df_sp=df_smart_phone)
                if df_mob_sheet.empty and not df_qc_kpi.empty:
                    df_mob_sheet = self.mob_parser.parse(df_qc_kpi, df_kpi=df_qc_kpi, df_sp=df_smart_phone)

                fact_dl = self.dl_parser.parse(all_l3) if all_l3 else {}
                df_dl_raw = self.dl_parser.build_raw_set_table(fact_dl)
                df_dl_syn = self.dl_parser.build_synthesized_table(df_dl_raw, vendor=active_vendor)

                df_ul_raw = self.ul_parser.build_raw_set_table(all_l3 if all_l3 else l3_csv)
                df_ul_syn = self.ul_parser.build_synthesized_table(df_ul_raw, vendor=active_vendor)

                # F. v12 Modular Domain Diagnosis (d00 ~ d08) & Causal Event Tracing (7+ Episodes)
                reporter = DiagnosisReporter()
                txt_rep = reporter.generate_full_text_report(
                    drm_name=display_name,
                    network_mode=network_mode,
                    active_vendor=active_vendor,
                    df_mob=df_mob_sheet,
                    df_call_sum=df_c_sum,
                    csvs=csvs,
                    all_l3=all_l3
                )

                incidents_list = getattr(reporter, 'last_episodes', [])

                pdata = {
                    'scenario': traffic_model_code,
                    'df_timeline': df_timeline,
                    'df_qc_kpi': df_qc_kpi,
                    'df_l3_scalar': df_l3_scalar,
                    'df_l3_struct': df_l3_struct,
                    'df_mob': df_mob_sheet,
                    'df_dl_syn': df_dl_syn,
                    'df_ul_syn': df_ul_syn,
                    'episodes': incidents_list,
                    'txt_rep': txt_rep,
                    'summaries': summaries,
                    'csvs': csvs
                }
                port_results_list.append((display_name, pdata))

            # Group by Route
            grouped_port_results = {}
            for disp_name, pdata in port_results_list:
                g_key = extract_route_group_key(disp_name)
                if g_key not in grouped_port_results:
                    grouped_port_results[g_key] = []
                grouped_port_results[g_key].append((disp_name, pdata))

            final_results = {}

            for g_key, items in grouped_port_results.items():
                items = sorted(items, key=lambda x: natural_sort_key(x[0]))
                item_drm_names = [d_name for d_name, _ in items]
                group_port_keys = compute_smart_port_keys(item_drm_names)

                group_port_dict = {}
                for pk, (d_name, pd_item) in zip(group_port_keys, items):
                    group_port_dict[pk] = pd_item

                sorted_pks = sorted(list(group_port_dict.keys()), key=natural_sort_key)
                group_port_dict = {k: group_port_dict[k] for k in sorted_pks}

                first_p = list(group_port_dict.values())[0] if group_port_dict else {}
                first_tl = first_p.get('df_timeline', pd.DataFrame())
                group_net_mode = first_tl.attrs.get('Network_Mode', 'LTE') if hasattr(first_tl, 'attrs') else 'LTE'
                group_vendor = first_tl.attrs.get('Active_Vendor', 'COMMON') if hasattr(first_tl, 'attrs') else 'COMMON'

                # Build Multi-Port Map Data directly from individual ports (M1, M2, etc.)
                map_port_dict = dict(group_port_dict)

                tmp_map_path = os.path.join(work_dir, f"{g_key}_Map.html")
                self.map_builder.generate_integrated_multi_port_map(
                    port_data_dict=map_port_dict,
                    display_name=g_key,
                    output_html_path=tmp_map_path,
                    network_mode=group_net_mode,
                    vendor=group_vendor
                )
                with open(tmp_map_path, 'r', encoding='utf-8', errors='ignore') as f_m:
                    map_html = f_m.read()

                tmp_xlsx_path = os.path.join(work_dir, f"{g_key}_Master.xlsx")
                self.wb_builder.build_master_consolidated_excel(
                    port_results=group_port_dict,
                    display_name=g_key,
                    output_xlsx_path=tmp_xlsx_path
                )
                with open(tmp_xlsx_path, 'rb') as f_x:
                    excel_bytes = f_x.read()

                combined_txt_reports = []
                for pk, p_item in group_port_dict.items():
                    combined_txt_reports.append(p_item.get('txt_rep', ''))

                total_episodes = sum(len(d.get('episodes', [])) for d in group_port_dict.values())
                total_pts = sum(len(d['df_timeline']) for d in group_port_dict.values())

                final_results[g_key] = {
                    'map_html': map_html,
                    'excel_bytes': excel_bytes,
                    'txt_report': "\n\n".join(combined_txt_reports),
                    'network_mode': group_net_mode,
                    'vendor': group_vendor,
                    'ports': list(group_port_dict.keys()),
                    'total_episodes': total_episodes,
                    'total_pts': total_pts
                }

            return final_results
