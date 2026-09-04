"""
===============================================================================
Module Name   : d02_physical_layer.py
Location      : core/diagnosis_modules/d02_physical_layer.py
Domain        : DOMAIN 02 (5G NR Physical Layer: MIMO Rank, CRC, DMRS, SR Latency)
===============================================================================
"""

import os
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from core.quality_criteria_registry import (
    NR_SS_SINR_CRITERIA,
    MIMO_LAYER_CRITERIA,
    DL_MCS_CRITERIA,
    PDSCH_BLER_CRITERIA,
    PDSCH_CRC_FAIL_CRITERIA,
    DEFAULT_RSRP_FALLBACK
)


class PhysicalLayerDetector:
    """Detects Physical Layer issues (DIAG_M_01_NR MIMO Rank, DIAG_M_02_NR CRC Continuous Errors)."""

    def __init__(self):
        pass

    # =========================================================================
    # 1. DIAG_M_01_NR: High-SINR MIMO Rank Restriction
    # =========================================================================
    def detect_mimo_rank_restrictions(
        self,
        csvs: Optional[Dict[str, Optional[str]]] = None,
        all_l3: Optional[Dict[str, Any]] = None,
        df_call_summary: Optional[pd.DataFrame] = None
    ) -> List[Dict[str, Any]]:
        if not csvs:
            return []

        kpi_path = csvs.get('KPI') or csvs.get('QC_KPI') or csvs.get('NSN_QC_UL') or csvs.get('QC_KPI_DL')
        if not kpi_path or not os.path.exists(kpi_path):
            return []

        try:
            df_kpi = pd.read_csv(kpi_path, encoding='utf-8')
        except Exception:
            df_kpi = pd.read_csv(kpi_path, encoding='cp949')

        if df_kpi.empty:
            return []

        sinr_col = self._find_col(df_kpi, ['SS-SINR'])
        rsrp_col = self._find_col(df_kpi, ['SS-RSRP'])
        pci_col = self._find_col(df_kpi, ['Serving PCI'])
        layer_col = self._find_col(df_kpi, ['DL Layer Num'])
        ri4_col = self._find_col(df_kpi, ['RI4 Rate'])
        tp_col = self._find_col(df_kpi, ['PDCP DL Throughput'])

        if not sinr_col or not layer_col:
            return []

        # Tag or filter by Traffic_Phase
        if 'Traffic_Phase' not in df_kpi.columns and df_call_summary is not None and not df_call_summary.empty:
            from core.kpi_summary_engine import KPISummaryEngine
            df_kpi = KPISummaryEngine.tag_call_traffic_phases(df_kpi, df_call_summary)

        # Enforce DL Traffic Phase
        if 'Traffic_Phase' in df_kpi.columns:
            df_kpi = df_kpi[df_kpi['Traffic_Phase'] == 'DL'].copy().reset_index(drop=True)
            if df_kpi.empty:
                return []

        # Single-shot work DataFrame creation (Zero Fragmentation)
        s_dt = pd.to_datetime(df_kpi['TIME_STAMP'], errors='coerce')
        valid_mask = s_dt.notna()
        df_work = pd.DataFrame({
            'TIME_STAMP': df_kpi.loc[valid_mask, 'TIME_STAMP'].astype(str),
            '_dt': s_dt[valid_mask],
            '_sinr': pd.to_numeric(df_kpi.loc[valid_mask, sinr_col], errors='coerce'),
            '_rsrp': pd.to_numeric(df_kpi.loc[valid_mask, rsrp_col], errors='coerce') if rsrp_col else DEFAULT_RSRP_FALLBACK,
            '_layer': pd.to_numeric(df_kpi.loc[valid_mask, layer_col], errors='coerce'),
            '_ri4': pd.to_numeric(df_kpi.loc[valid_mask, ri4_col], errors='coerce').fillna(0) if ri4_col else 0.0,
            '_tp': pd.to_numeric(df_kpi.loc[valid_mask, tp_col], errors='coerce').fillna(0) if tp_col else 0.0,
            '_pci': pd.to_numeric(df_kpi.loc[valid_mask, pci_col], errors='coerce').fillna(0).astype(int) if pci_col else 0
        }).sort_values('_dt').reset_index(drop=True)
        df_kpi = df_work

        pdsch_path = csvs.get('MAC_PDSCH_PER_SLOT') or csvs.get('MAC_PDSCH_Per_Slot') or csvs.get('PDSCH')
        df_pdsch = None
        if pdsch_path and os.path.exists(pdsch_path):
            try:
                df_pdsch = pd.read_csv(pdsch_path, encoding='utf-8')
            except Exception:
                df_pdsch = pd.read_csv(pdsch_path, encoding='cp949')
            if not df_pdsch.empty and 'TIME_STAMP' in df_pdsch.columns:
                df_pdsch['_dt'] = pd.to_datetime(df_pdsch['TIME_STAMP'], errors='coerce')

        phone_path = csvs.get('SMART_PHONE') or csvs.get('Smart_Phone') or csvs.get('PHONE')
        df_phone = None
        if phone_path and os.path.exists(phone_path):
            try:
                df_phone = pd.read_csv(phone_path, encoding='utf-8')
            except Exception:
                df_phone = pd.read_csv(phone_path, encoding='cp949')
            if not df_phone.empty and 'TIME_STAMP' in df_phone.columns:
                df_phone['_dt'] = pd.to_datetime(df_phone['TIME_STAMP'], errors='coerce')

        l3_2port_pcis = set()
        if all_l3:
            for msg in all_l3.get('rrc_reconfig_msgs', []):
                raw_text = str(msg.get('raw_text', ''))
                if 'nrofPorts p2' in raw_text or 'nrofPorts = p2' in raw_text:
                    pci = msg.get('pci')
                    if pci: l3_2port_pcis.add(pci)

        cond = (df_kpi['_sinr'] >= NR_SS_SINR_CRITERIA['HIGH_SINR_MIMO_THRESH']) & (df_kpi['_layer'] <= MIMO_LAYER_CRITERIA['RANK_RESTRICTION_THRESH'])

        events = []
        curr_ev = None

        for idx, r in df_kpi.iterrows():
            if cond.iloc[idx]:
                if curr_ev is None:
                    curr_ev = {
                        'start_dt': r['_dt'], 'end_dt': r['_dt'],
                        'start_ts': str(r['TIME_STAMP']), 'end_ts': str(r['TIME_STAMP']),
                        'pci': r['_pci'],
                        'sinrs': [r['_sinr']], 'rsrps': [r['_rsrp']],
                        'layers': [r['_layer']], 'ri4s': [r['_ri4']], 'tps': [r['_tp']],
                        'count': 1
                    }
                else:
                    curr_ev['end_dt'] = r['_dt']
                    curr_ev['end_ts'] = str(r['TIME_STAMP'])
                    curr_ev['sinrs'].append(r['_sinr'])
                    curr_ev['rsrps'].append(r['_rsrp'])
                    curr_ev['layers'].append(r['_layer'])
                    curr_ev['ri4s'].append(r['_ri4'])
                    curr_ev['tps'].append(r['_tp'])
                    curr_ev['count'] += 1
            else:
                if curr_ev is not None:
                    dur = (curr_ev['end_dt'] - curr_ev['start_dt']).total_seconds()
                    if dur >= 3.0 and curr_ev['count'] >= 3:
                        self._finalize_m01_event(curr_ev, df_pdsch, df_phone, l3_2port_pcis)
                        if curr_ev.get('valid_event'):
                            events.append(curr_ev)
                    curr_ev = None

        if curr_ev is not None:
            dur = (curr_ev['end_dt'] - curr_ev['start_dt']).total_seconds()
            if dur >= 3.0 and curr_ev['count'] >= 3:
                self._finalize_m01_event(curr_ev, df_pdsch, df_phone, l3_2port_pcis)
                if curr_ev.get('valid_event'):
                    events.append(curr_ev)

        return events

    def _finalize_m01_event(
        self,
        ev: Dict[str, Any],
        df_pdsch: Optional[pd.DataFrame],
        df_phone: Optional[pd.DataFrame],
        l3_2port_pcis: set
    ):
        dur = (ev['end_dt'] - ev['start_dt']).total_seconds()
        ev['duration_sec'] = dur
        ev['avg_sinr'] = float(np.mean(ev['sinrs']))
        ev['avg_rsrp'] = float(np.mean(ev['rsrps']))
        ev['avg_layer'] = float(np.mean(ev['layers']))
        ev['avg_ri4'] = float(np.mean(ev['ri4s']))
        ev['avg_tp'] = float(np.mean(ev['tps']))

        pci = ev['pci']
        s_dt = ev['start_dt']
        e_dt = ev['end_dt']

        pdsch_slots = 0
        rank4_pct = 0.0
        rx2_count = 0
        rx4_count = 0
        if df_pdsch is not None and not df_pdsch.empty and '_dt' in df_pdsch.columns:
            sub_pdsch = df_pdsch[(df_pdsch['_dt'] >= s_dt) & (df_pdsch['_dt'] <= e_dt)]
            pdsch_slots = len(sub_pdsch)
            if pdsch_slots > 0:
                layer_c = self._find_col(sub_pdsch, ['Num Layers'])
                if layer_c:
                    rank4_pct = float((sub_pdsch[layer_c] == 4).mean() * 100.0)
                rx_c = self._find_col(sub_pdsch, ['Number of Rx Antennas'])
                if rx_c:
                    rx2_count = int((sub_pdsch[rx_c].astype(str).str.contains('2x2')).sum())
                    rx4_count = int((sub_pdsch[rx_c].astype(str).str.contains('4x4')).sum())

        ev['pdsch_slots'] = pdsch_slots
        ev['rank4_pct'] = rank4_pct

        battery_temp = None
        if df_phone is not None and not df_phone.empty and '_dt' in df_phone.columns:
            sub_ph = df_phone[(df_phone['_dt'] >= s_dt) & (df_phone['_dt'] <= e_dt)]
            if not sub_ph.empty:
                temp_c = self._find_col(sub_ph, ['Battery Temperature'])
                if temp_c:
                    battery_temp = float(pd.to_numeric(sub_ph[temp_c], errors='coerce').mean())

        # Determine Root Cause
        if pci in l3_2port_pcis:
            ev['valid_event'] = True
            ev['cause_str'] = f"기지국 RRC 메시지의 CSI-RS 2포트(p2) 설정으로 인해 물리적 2-Layer로 고정 동작함"
        elif rx2_count > rx4_count:
            ev['valid_event'] = True
            if battery_temp and battery_temp >= 42.0:
                ev['cause_str'] = f"단말 내부 고온 발열({battery_temp:.1f}℃)로 인한 2Rx 안테나 차단 추정"
            else:
                ev['cause_str'] = f"단말 모뎀의 수신 안테나 2Rx 축소로 인한 2-Layer 동작 추정"
        elif ev['avg_ri4'] >= 50.0:
            ev['valid_event'] = True
            ev['cause_str'] = f"단말의 4-Layer 수신 가능(RI4={ev['avg_ri4']:.1f}%) 보고 대비 기지국 스케줄러의 Rank 2 제한 추정"
        elif pdsch_slots > 50 and rank4_pct <= 10.0:
            ev['valid_event'] = True
            ev['cause_str'] = f"SINR {ev['avg_sinr']:.1f}dB 최상급 전계이나 해당 기지국(PCI {pci})의 2-Layer 고정 동작 추정"
        elif pdsch_slots == 0 and ev['avg_tp'] < 1.0:
            ev['valid_event'] = False
        else:
            ev['valid_event'] = True
            ev['cause_str'] = f"우수 전계이나 기지국 및 무선 채널 제약으로 인한 2-Layer 동작 추정"

    # =========================================================================
    # 2. DIAG_M_02_NR: 5G PDSCH Continuous CRC Burst Errors (Hierarchical 2-Stage)
    # =========================================================================
    def detect_continuous_crc_errors(
        self,
        csvs: Optional[Dict[str, Optional[str]]] = None,
        df_call_summary: Optional[pd.DataFrame] = None
    ) -> List[Dict[str, Any]]:
        """
        Hierarchical 2-Stage PDSCH CRC Burst Error Detector:
          - Stage 1: Quick scan on QC_KPI (PDSCH BLER >= 15.0%)
          - Stage 2: Micro-slicing on MAC_PDSCH_Per_Slot (Consecutive FAIL >= 100 slots or slot BLER >= 30%)
        """
        if not csvs:
            return []

        kpi_path = csvs.get('KPI') or csvs.get('QC_KPI') or csvs.get('QC_KPI_DL')
        if not kpi_path or not os.path.exists(kpi_path):
            return []

        try:
            df_kpi = pd.read_csv(kpi_path, encoding='utf-8')
        except Exception:
            df_kpi = pd.read_csv(kpi_path, encoding='cp949')

        if df_kpi.empty:
            return []

        bler_col = self._find_col(df_kpi, ['PDSCH BLER', 'DL BLER', 'BLER'])
        sinr_col = self._find_col(df_kpi, ['SS-SINR'])
        rsrp_col = self._find_col(df_kpi, ['SS-RSRP'])
        pci_col = self._find_col(df_kpi, ['Serving PCI'])
        mcs_col = self._find_col(df_kpi, ['DL MCS', 'PDSCH MCS'])

        if not bler_col or not sinr_col:
            return []

        # Tag Traffic_Phase
        if 'Traffic_Phase' not in df_kpi.columns and df_call_summary is not None and not df_call_summary.empty:
            from core.kpi_summary_engine import KPISummaryEngine
            df_kpi = KPISummaryEngine.tag_call_traffic_phases(df_kpi, df_call_summary)

        if 'Traffic_Phase' in df_kpi.columns:
            df_kpi = df_kpi[df_kpi['Traffic_Phase'] == 'DL'].copy().reset_index(drop=True)
            if df_kpi.empty:
                return []

        # Single-shot work DataFrame creation (Zero Fragmentation)
        s_dt = pd.to_datetime(df_kpi['TIME_STAMP'], errors='coerce')
        valid_mask = s_dt.notna()
        df_work = pd.DataFrame({
            'TIME_STAMP': df_kpi.loc[valid_mask, 'TIME_STAMP'].astype(str),
            '_dt': s_dt[valid_mask],
            '_bler': pd.to_numeric(df_kpi.loc[valid_mask, bler_col], errors='coerce').fillna(0),
            '_sinr': pd.to_numeric(df_kpi.loc[valid_mask, sinr_col], errors='coerce'),
            '_rsrp': pd.to_numeric(df_kpi.loc[valid_mask, rsrp_col], errors='coerce') if rsrp_col else -75.0,
            '_mcs': pd.to_numeric(df_kpi.loc[valid_mask, mcs_col], errors='coerce').fillna(14) if mcs_col else 14.0,
            '_pci': pd.to_numeric(df_kpi.loc[valid_mask, pci_col], errors='coerce').fillna(0).astype(int) if pci_col else 0
        }).sort_values('_dt').reset_index(drop=True)
        df_kpi = df_work

        # Stage 1: Quick Scan on QC_KPI for BLER >= 15.0%
        bad_intervals = []
        curr_int = None
        for idx, r in df_kpi.iterrows():
            if r['_bler'] >= 15.0:
                if curr_int is None:
                    curr_int = {'start_dt': r['_dt'], 'end_dt': r['_dt'], 'pci': r['_pci'], 'sinrs': [r['_sinr']], 'rsrps': [r['_rsrp']], 'mcss': [r['_mcs']], 'blers': [r['_bler']]}
                else:
                    curr_int['end_dt'] = r['_dt']
                    curr_int['sinrs'].append(r['_sinr'])
                    curr_int['rsrps'].append(r['_rsrp'])
                    curr_int['mcss'].append(r['_mcs'])
                    curr_int['blers'].append(r['_bler'])
            else:
                if curr_int is not None:
                    bad_intervals.append(curr_int)
                    curr_int = None
        if curr_int is not None:
            bad_intervals.append(curr_int)

        if not bad_intervals:
            return []

        # Stage 2: Precision Slicing on MAC_PDSCH_Per_Slot
        pdsch_path = csvs.get('MAC_PDSCH_PER_SLOT') or csvs.get('MAC_PDSCH_Per_Slot') or csvs.get('PDSCH')
        df_pdsch = None
        if pdsch_path and os.path.exists(pdsch_path):
            try:
                df_pdsch = pd.read_csv(pdsch_path, encoding='utf-8')
            except Exception:
                df_pdsch = pd.read_csv(pdsch_path, encoding='cp949')
            if not df_pdsch.empty and 'TIME_STAMP' in df_pdsch.columns:
                df_pdsch['_dt'] = pd.to_datetime(df_pdsch['TIME_STAMP'], errors='coerce')

        crc_events = []
        for interval in bad_intervals:
            s_dt = interval['start_dt']
            e_dt = interval['end_dt']
            dur = max(1.0, (e_dt - s_dt).total_seconds())

            avg_sinr = float(np.mean(interval['sinrs']))
            avg_rsrp = float(np.mean(interval['rsrps']))
            avg_mcs = float(np.mean(interval['mcss']))
            avg_bler = float(np.mean(interval['blers']))
            pci = interval['pci']

            consecutive_fails = 0
            total_slots = 0
            fail_slots = 0

            if df_pdsch is not None and not df_pdsch.empty and '_dt' in df_pdsch.columns:
                sub_pdsch = df_pdsch[(df_pdsch['_dt'] >= s_dt) & (df_pdsch['_dt'] <= e_dt)]
                total_slots = len(sub_pdsch)
                if total_slots > 0:
                    crc_col = self._find_col(sub_pdsch, ['CRC Status', 'CRC_Status', 'CRC'])
                    if crc_col:
                        crc_vals = sub_pdsch[crc_col].astype(str).str.upper()
                        is_fail = crc_vals.str.contains('FAIL') | (crc_vals == '0')
                        fail_slots = int(is_fail.sum())

                        # Max consecutive fail count
                        max_consec = 0
                        cur_consec = 0
                        for f in is_fail:
                            if f:
                                cur_consec += 1
                                if cur_consec > max_consec:
                                    max_consec = cur_consec
                            else:
                                cur_consec = 0
                        consecutive_fails = max_consec

            # Check threshold from quality_criteria_registry
            slot_bler = (fail_slots / total_slots * 100.0) if total_slots > 0 else avg_bler
            if (consecutive_fails >= PDSCH_CRC_FAIL_CRITERIA['CONSECUTIVE_FAIL_SLOTS_THRESH']
                or slot_bler >= PDSCH_BLER_CRITERIA['SEVERE_BLER_THRESH']
                or avg_bler >= PDSCH_BLER_CRITERIA['SEVERE_BLER_THRESH']):
                # Deduce Root Cause
                if avg_sinr <= NR_SS_SINR_CRITERIA['POOR_SINR_INTERFERENCE_THRESH']:
                    cause_str = "수신 SINR 저하(간섭/잡음 증가)로 인한 PDSCH 복조 실패 추정"
                elif avg_sinr >= NR_SS_SINR_CRITERIA['EXCELLENT_SINR_THRESH'] and avg_mcs >= DL_MCS_CRITERIA['HIGH_MCS_THRESH']:
                    cause_str = f"우수 전계이나 기지국이 과도하게 높은 MCS({avg_mcs:.0f}, 256QAM)를 할당하여 복조 실패 추정"
                else:
                    cause_str = "수신 전계 대비 급격한 채널 위상 왜곡으로 인한 PDSCH 복조 실패 추정"

                crc_events.append({
                    'start_ts': str(s_dt),
                    'end_ts': str(e_dt),
                    'duration_sec': dur,
                    'pci': pci,
                    'avg_sinr': avg_sinr,
                    'avg_rsrp': avg_rsrp,
                    'avg_mcs': avg_mcs,
                    'slot_bler': slot_bler,
                    'total_slots': total_slots,
                    'fail_slots': fail_slots,
                    'consecutive_fails': consecutive_fails,
                    'cause_str': cause_str
                })

        return crc_events

    @staticmethod
    def _find_col(df: pd.DataFrame, keywords) -> Optional[str]:
        if df is None or df.empty:
            return None
        from core.canonical_registry import CanonicalColumnRegistry
        kws = keywords if isinstance(keywords, list) else [keywords]
        for kw in kws:
            actual = CanonicalColumnRegistry.get_actual_column(df, kw)
            if actual:
                return actual
        for kw in kws:
            kw_clean = re.sub(r'[^a-zA-Z0-9]', '', kw.lower())
            for c in df.columns:
                c_clean = re.sub(r'[^a-zA-Z0-9]', '', str(c).lower())
                if kw_clean in c_clean:
                    return c
        return None
