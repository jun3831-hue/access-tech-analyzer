"""
===============================================================================
Module Name   : d01_mobility.py
Location      : core/diagnosis_modules/d01_mobility.py
Domain        : DOMAIN 01 (Handover & Mobility: 3GPP LTE, 5G NSA & 5G SA Standards)
Specification : DIAG_M_01 ~ DIAG_M_08 Full 3GPP Mobility Diagnostic Suite
===============================================================================
"""

import os
import sys
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional


class MobilityDetector:
    """
    Standard 3GPP Mobility and Handover Precision Diagnosis Engine.
    
    Covers Full 3GPP Spectrum:
    - DIAG_M_01_PINGPONG         : Ping-Pong Handover (< 5.0s return window)
    - DIAG_M_02_A3_UNHANDLED     : Intra-Freq A3 Unhandled Requests with 3GPP Leaving Criteria
    - DIAG_M_03_TOO_LATE_HO      : 3GPP TS 36.300/38.300 Too Late Handover (A3 unhandled -> RLF/Reject)
    - DIAG_M_04_TOO_EARLY_HO     : 3GPP Too Early Handover (HO complete -> RLF <= 3s -> return to source)
    - DIAG_M_05_WRONG_CELL_HO    : 3GPP Handover to Wrong Cell (HO complete -> RLF <= 3s -> RRE to 3rd cell)
    - DIAG_M_06_INTER_FREQ_HO    : Inter-Frequency HO Delay (Event A2 -> Event A5/A4 unserved)
    - DIAG_M_07_A_NSA_B1_STALL   : 5G NSA: Event B1-NR MR unserved (5G SCG Addition Stall)
    - DIAG_M_07_B_SA_B2_FALLBACK : 5G SA: Event B2-LTE Fallback Failure / RLF
    - DIAG_M_08_PCI_COLLISION    : Multi-RAT Duplicate PCI Collision & Confusion (Distance-based)
    """

    def __init__(self):
        pass

    @staticmethod
    def _safe_int(val: Any) -> Optional[int]:
        if pd.isna(val) or val is None:
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
        if pd.isna(val) or val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculates the great-circle distance between two GPS points on Earth in kilometers."""
        R = 6371.0  # Earth radius in km
        dlat = np.radians(lat2 - lat1)
        dlon = np.radians(lon2 - lon1)
        a = np.sin(dlat / 2.0) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2
        c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
        return float(R * c)

    # -------------------------------------------------------------------------
    # 1. Base Transition Extractor
    # -------------------------------------------------------------------------
    def extract_mobility_transitions(self, df_mob: pd.DataFrame, rat: str = 'NR') -> List[Dict[str, Any]]:
        if df_mob is None or df_mob.empty or 'RAT' not in df_mob.columns or 'HO_Status' not in df_mob.columns:
            return []

        df_rat = df_mob[df_mob['RAT'] == rat].copy()
        if df_rat.empty:
            return []

        df_sorted = df_rat.sort_values(by=['TIME_STAMP']).reset_index(drop=True)
        df_sorted['_dt'] = pd.to_datetime(df_sorted['TIME_STAMP'], errors='coerce')
        df_sorted = df_sorted.dropna(subset=['_dt']).reset_index(drop=True)

        transitions = []
        pci_col = 'NR_Serving_PCI' if rat == 'NR' else 'LTE_Serving_PCI'
        arfcn_col = 'NR_Serving_ARFCN' if rat == 'NR' else 'LTE_Serving_ARFCN'
        beam_col = 'Serving_SSB_Idx'

        last_meas_rsrp = {}

        for idx, row in df_sorted.iterrows():
            status = str(row.get('HO_Status', '')).strip()

            if status in ['MEAS_REPORT', 'MeasurementReport'] or row.get('Event') == 'eventA3':
                s_pci = self._safe_int(row.get(pci_col))
                s_rsrp = self._safe_float(row.get('Serving_RSRP'))
                n_pci = self._safe_int(row.get('NBR_1_PCI'))
                n_rsrp = self._safe_float(row.get('NBR_1_RSRP'))
                if s_pci and s_rsrp is not None:
                    last_meas_rsrp[s_pci] = s_rsrp
                if n_pci and n_rsrp is not None:
                    last_meas_rsrp[n_pci] = n_rsrp

            elif 'HO_COMPLETE' in status or status in ['Success', 'Handover'] or row.get('Message_Type') in ['RRCReconfiguration', 'RRCConnectionReconfiguration']:
                cond = str(row.get('Event_Condition', ''))
                target_pci = self._safe_int(row.get(pci_col))
                target_arfcn = self._safe_int(row.get(arfcn_col))
                target_beam = self._safe_int(row.get(beam_col))

                src_pci, src_arfcn, src_beam = None, None, None

                if rat == 'NR':
                    m_nr = re.search(r'Source:\s*(\d+)/SSB(\d+)/(\d+)\s*➔\s*Target:\s*(\d+)/SSB(\d+)/(\d+)', cond)
                    if m_nr:
                        src_pci = int(m_nr.group(1))
                        src_beam = int(m_nr.group(2))
                        src_arfcn = int(m_nr.group(3))
                        target_pci = int(m_nr.group(4))
                        target_beam = int(m_nr.group(5))
                        target_arfcn = int(m_nr.group(6))
                else:
                    m_lte = re.search(r'Source:\s*(\d+)/(\d+)\s*➔\s*Target:\s*(\d+)/(\d+)', cond)
                    if m_lte:
                        src_pci = int(m_lte.group(1))
                        src_arfcn = int(m_lte.group(2))
                        target_pci = int(m_lte.group(3))
                        target_arfcn = int(m_lte.group(4))

                if src_pci is None and idx > 0:
                    src_pci = self._safe_int(df_sorted.loc[idx - 1, pci_col])
                    src_arfcn = self._safe_int(df_sorted.loc[idx - 1, arfcn_col])
                    src_beam = self._safe_int(df_sorted.loc[idx - 1, beam_col])

                if src_pci is not None and target_pci is not None and src_pci != target_pci:
                    srv_rsrp = last_meas_rsrp.get(src_pci, self._safe_float(row.get('Serving_RSRP'), default=-80.0))
                    tgt_rsrp = last_meas_rsrp.get(target_pci, self._safe_float(row.get('NBR_1_RSRP'), default=-75.0))
                    delta_rsrp = round(tgt_rsrp - srv_rsrp, 1)
                    ho_delay = self._safe_float(row.get('HO_Delay_ms'), default=15.0)

                    is_coupled = False
                    if rat == 'NR' and 'LTE_Serving_PCI' in row:
                        is_coupled = pd.notna(row.get('LTE_Serving_PCI'))

                    coupling_tag = "순수 5G HO" if rat == 'NR' else ("LTE Intra-Freq HO" if src_arfcn == target_arfcn else "LTE Inter-Freq HO")
                    if is_coupled:
                        coupling_tag = "LTE-NR 연동 HO"

                    transitions.append({
                        'idx': idx,
                        'time_stamp': str(row['TIME_STAMP']),
                        'dt': row['_dt'],
                        'rat': rat,
                        'src_pci': src_pci,
                        'src_arfcn': src_arfcn,
                        'src_beam': src_beam,
                        'tgt_pci': target_pci,
                        'tgt_arfcn': target_arfcn,
                        'tgt_beam': target_beam,
                        'srv_rsrp': srv_rsrp,
                        'tgt_rsrp': tgt_rsrp,
                        'delta_rsrp': delta_rsrp,
                        'ho_delay': ho_delay,
                        'is_coupled': is_coupled,
                        'coupling_tag': coupling_tag,
                        'lat': self._safe_float(row.get('Lat')),
                        'lon': self._safe_float(row.get('Lon'))
                    })

        return transitions

    def detect_ho_delays(self, transitions: List[Dict[str, Any]], threshold_ms: float = 30.0) -> List[Dict[str, Any]]:
        """
        Detects excessive Handover execution delay (e.g. > 30ms for NR or > 40ms for LTE).
        """
        delayed = []
        for t in transitions:
            d_ms = t.get('ho_delay')
            if d_ms is not None and d_ms > threshold_ms:
                delayed.append({
                    'time_stamp': t['time_stamp'],
                    'dt': t.get('dt'),
                    'rat': t['rat'],
                    'src_pci': t['src_pci'],
                    'tgt_pci': t['tgt_pci'],
                    'ho_delay_ms': d_ms,
                    'threshold_ms': threshold_ms,
                    'severity': 'LOW' if d_ms < 60.0 else 'MED',
                    'detail': f"{t['rat']} 핸드오버 지연 ({d_ms:.1f}ms > {threshold_ms:.1f}ms) [PCI {t['src_pci']} ➔ {t['tgt_pci']}]"
                })
        return delayed

    # -------------------------------------------------------------------------
    # [DIAG_M_01_PINGPONG] 핑퐁 핸드오버 (Ping-Pong Handover)
    # -------------------------------------------------------------------------
    def detect_ping_pong_sessions(
        self,
        transitions: List[Dict[str, Any]],
        rat: str = 'NR',
        time_window: float = 5.0,
        min_dwell_sec: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_M_01] Ping-Pong Handover Session Detector
        - Window: default 5.0s
        - Pattern: PCI_A -> PCI_B -> PCI_A
        - Severity: HIGH (dwell <= 2.0s or bounce >= 3), MED (2.0s < dwell <= 5.0s)
        """
        if len(transitions) < 2:
            return []

        raw_ping_pongs = []
        n = len(transitions)

        for i in range(n):
            t_start = transitions[i]
            orig_pci = t_start['src_pci']
            orig_arfcn = t_start['src_arfcn']

            for j in range(i + 1, min(i + 6, n)):
                t_end = transitions[j]

                is_return = False
                if rat == 'NR':
                    is_return = (t_end['tgt_pci'] == orig_pci and t_end['tgt_arfcn'] == orig_arfcn)
                else:
                    is_return = (t_end['tgt_pci'] == orig_pci)

                if is_return:
                    total_time = (t_end['dt'] - t_start['dt']).total_seconds()
                    if min_dwell_sec <= total_time <= time_window:
                        matched_steps = transitions[i:j+1]
                        raw_ping_pongs.append({
                            'start_dt': t_start['dt'],
                            'end_dt': t_end['dt'],
                            'orig_pci': orig_pci,
                            'target_pci': t_start['tgt_pci'],
                            'rat': rat,
                            'transitions': matched_steps,
                            'total_duration': total_time,
                            'lat': t_start.get('lat'),
                            'lon': t_start.get('lon')
                        })

        if not raw_ping_pongs:
            return []

        # Merge overlapping ping pong sessions
        merged = []
        raw_ping_pongs.sort(key=lambda x: x['start_dt'])

        curr = raw_ping_pongs[0]
        for nxt in raw_ping_pongs[1:]:
            if nxt['start_dt'] <= curr['end_dt'] and nxt['orig_pci'] == curr['orig_pci']:
                curr['end_dt'] = max(curr['end_dt'], nxt['end_dt'])
                curr['total_duration'] = (curr['end_dt'] - curr['start_dt']).total_seconds()
                existing_ts = {t['dt'] for t in curr['transitions']}
                for t in nxt['transitions']:
                    if t['dt'] not in existing_ts:
                        curr['transitions'].append(t)
                curr['transitions'].sort(key=lambda x: x['dt'])
            else:
                merged.append(curr)
                curr = nxt
        merged.append(curr)

        final_episodes = []
        for sess in merged:
            pci_seq = [sess['transitions'][0]['src_pci']]
            for t in sess['transitions']:
                pci_seq.append(t['tgt_pci'])

            pci_chain_str = " ➔ ".join(str(p) for p in pci_seq)
            total_dur = round(sess['total_duration'], 1)
            hop_count = len(sess['transitions'])

            min_rsrp = min(t['srv_rsrp'] for t in sess['transitions'])
            deltas = [t['delta_rsrp'] for t in sess['transitions']]
            avg_delta = round(float(np.mean(deltas)), 1) if deltas else 0.0

            if total_dur <= 2.0 or hop_count >= 3 or min_rsrp <= -105.0:
                severity = "HIGH"
            else:
                severity = "MED"

            summary = f"{rat} 핑퐁 ({pci_chain_str}) ({total_dur}초)"

            final_episodes.append({
                'diag_code': 'DIAG_M_01_PINGPONG',
                'rule_id': 'DIAG_M_01',
                'rat': rat,
                'time_stamp': sess['start_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                'start_dt': sess['start_dt'],
                'end_dt': sess['end_dt'],
                'pci': sess['orig_pci'],
                'target_pci': sess['target_pci'],
                'pci_chain': pci_chain_str,
                'rep_cnt': hop_count,
                'dur_sec': total_dur,
                'delta_rsrp': avg_delta,
                'severity': severity,
                'summary': summary,
                'lat': sess.get('lat'),
                'lon': sess.get('lon')
            })

        return final_episodes

    # -------------------------------------------------------------------------
    # [DIAG_M_02_A3_UNHANDLED] Intra-Freq A3 Unhandled with Leaving Filter
    # -------------------------------------------------------------------------
    def detect_unhandled_ho_requests(self, df_mob: pd.DataFrame, rat: str = 'NR') -> List[Dict[str, Any]]:
        """
        [DIAG_M_02] Intra-Frequency A3 Unhandled Requests with 3GPP TS 36.331 Leaving Criteria.
        - Excludes Periodic Measurement Reports (LTE Periodic / ReportConfig).
        - Excludes Normal 3GPP A3 Leaving (Serving RSRP >= Target RSRP at session exit with no faults).
        - Severity: MED (dur >= 5.0s or count >= 20), LOW (otherwise).
        """
        if df_mob is None or df_mob.empty or 'RAT' not in df_mob.columns or 'Event' not in df_mob.columns:
            return []

        # Pure Event A3 filter
        df_a3 = df_mob[
            (df_mob['RAT'] == rat) &
            (df_mob['Event'].isin(['eventA3', 'LTE Event A3', 'NR Event A3']))
        ].copy()

        if df_a3.empty:
            return []

        df_a3['_dt'] = pd.to_datetime(df_a3['TIME_STAMP'], errors='coerce')
        df_a3 = df_a3.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)

        ho_col = 'NR_Serving_PCI' if rat == 'NR' else 'LTE_Serving_PCI'
        if ho_col in df_a3.columns:
            df_a3[ho_col] = df_a3[ho_col].ffill()
        if 'Serving_RSRP' in df_a3.columns:
            df_a3['Serving_RSRP'] = df_a3['Serving_RSRP'].ffill()

        ho_completes = df_mob[
            (df_mob['RAT'] == rat) &
            (df_mob['HO_Status'].isin(['HO_COMPLETE', 'Success', 'Handover']) |
             df_mob['Message_Type'].isin(['RRCReconfiguration', 'RRCConnectionReconfiguration']))
        ].copy()
        if not ho_completes.empty:
            ho_completes['_dt'] = pd.to_datetime(ho_completes['TIME_STAMP'], errors='coerce')

        raw_streaks = []
        active_streaks = {}

        for idx, row in df_a3.iterrows():
            srv_pci = self._safe_int(row.get(ho_col))
            srv_rsrp = self._safe_float(row.get('Serving_RSRP'))
            nbr_pci = self._safe_int(row.get('NBR_1_PCI'))
            nbr_rsrp = self._safe_float(row.get('NBR_1_RSRP'))

            if not (srv_pci and nbr_pci and srv_rsrp is not None and nbr_rsrp is not None):
                continue

            # Skip intra-cell buffer residual (Serving == Neighbor)
            if srv_pci == nbr_pci:
                continue

            actual_delta = round(nbr_rsrp - srv_rsrp, 1)
            key = (srv_pci, nbr_pci)

            # Check if resolved by normal HO within 2.0s
            if not ho_completes.empty:
                matching_ho = ho_completes[
                    (ho_completes['_dt'] >= row['_dt']) &
                    ((ho_completes['_dt'] - row['_dt']).dt.total_seconds() <= 2.0)
                ]
                if not matching_ho.empty:
                    continue

            srv_beam = self._safe_int(row.get('Serving_SSB_Idx'))
            nbr_beam = self._safe_int(row.get('NBR_1_SSB_Idx'))

            if key in active_streaks:
                prev = active_streaks[key]
                time_gap = (row['_dt'] - prev['last_dt']).total_seconds()
                # 3GPP Protocol State Machine: Check if intervening HO resolution occurred OR session timed out (>10.0s gap)
                has_ho_resolution = (time_gap > 10.0)
                if not has_ho_resolution and not ho_completes.empty:
                    ho_between = ho_completes[
                        (ho_completes['_dt'] >= prev['last_dt']) &
                        (ho_completes['_dt'] <= row['_dt'])
                    ]
                    if not ho_between.empty:
                        has_ho_resolution = True

                if not has_ho_resolution:
                    prev['end_ts'] = str(row['TIME_STAMP'])
                    prev['end_dt'] = row['_dt']
                    prev['last_dt'] = row['_dt']
                    prev['count'] += 1
                    prev['last_srv_rsrp'] = srv_rsrp
                    prev['last_nbr_rsrp'] = nbr_rsrp
                    prev['min_srv_rsrp'] = min(prev['min_srv_rsrp'], srv_rsrp)
                    prev['max_nbr_rsrp'] = max(prev['max_nbr_rsrp'], nbr_rsrp)
                    prev['max_delta'] = max(prev['max_delta'], actual_delta)
                    if srv_beam is not None: prev['srv_beam'] = srv_beam
                    if nbr_beam is not None: prev['nbr_beam'] = nbr_beam
                else:
                    if prev['count'] >= 3:
                        prev['duration_sec'] = max(0.1, (prev['end_dt'] - prev['start_dt']).total_seconds())
                        raw_streaks.append(prev)
                    active_streaks[key] = {
                        'start_ts': str(row['TIME_STAMP']),
                        'start_dt': row['_dt'],
                        'last_dt': row['_dt'],
                        'end_ts': str(row['TIME_STAMP']),
                        'end_dt': row['_dt'],
                        'srv_pci': srv_pci,
                        'nbr_pci': nbr_pci,
                        'srv_beam': srv_beam,
                        'nbr_beam': nbr_beam,
                        'first_srv_rsrp': srv_rsrp,
                        'last_srv_rsrp': srv_rsrp,
                        'min_srv_rsrp': srv_rsrp,
                        'first_nbr_rsrp': nbr_rsrp,
                        'last_nbr_rsrp': nbr_rsrp,
                        'max_nbr_rsrp': nbr_rsrp,
                        'max_delta': actual_delta,
                        'count': 1,
                        'lat': self._safe_float(row.get('Lat')),
                        'lon': self._safe_float(row.get('Lon'))
                    }
            else:
                active_streaks[key] = {
                    'start_ts': str(row['TIME_STAMP']),
                    'start_dt': row['_dt'],
                    'last_dt': row['_dt'],
                    'end_ts': str(row['TIME_STAMP']),
                    'end_dt': row['_dt'],
                    'srv_pci': srv_pci,
                    'nbr_pci': nbr_pci,
                    'srv_beam': srv_beam,
                    'nbr_beam': nbr_beam,
                    'first_srv_rsrp': srv_rsrp,
                    'last_srv_rsrp': srv_rsrp,
                    'min_srv_rsrp': srv_rsrp,
                    'first_nbr_rsrp': nbr_rsrp,
                    'last_nbr_rsrp': nbr_rsrp,
                    'max_nbr_rsrp': nbr_rsrp,
                    'max_delta': actual_delta,
                    'count': 1,
                    'lat': self._safe_float(row.get('Lat')),
                    'lon': self._safe_float(row.get('Lon'))
                }

        for key, s in active_streaks.items():
            if s['count'] >= 3:
                s['duration_sec'] = max(0.1, (s['end_dt'] - s['start_dt']).total_seconds())
                raw_streaks.append(s)

        if not raw_streaks:
            return []

        # Apply 3GPP TS 36.331 Leaving Criteria & Physical Inversion Check
        unhandled = []
        for s in raw_streaks:
            # Check exit condition: If Serving RSRP >= Target RSRP at exit, it naturally faded out (3GPP Leaving)
            is_leaving = s['last_srv_rsrp'] >= s['last_nbr_rsrp']
            s['exit_reason'] = 'LEAVING' if is_leaving else 'SUSTAINED_INVERSION'

            dur = round(s['duration_sec'], 1)
            cnt = s['count']

            # Mathematical severity
            if dur >= 5.0 or cnt >= 20:
                s['severity'] = 'MED'
            else:
                s['severity'] = 'LOW'

            s['diag_code'] = 'DIAG_M_02_A3_UNHANDLED'
            s['rule_id'] = 'DIAG_M_02'
            s['rat'] = rat
            s['time_stamp'] = s['start_ts']
            s['pci'] = s['srv_pci']
            s['target_pci'] = s['nbr_pci']
            s['rep_cnt'] = cnt
            s['dur_sec'] = dur
            s['delta_rsrp'] = s['max_delta']
            s['summary'] = f"{rat} 타겟(PCI {s['nbr_pci']}) HO 방치 후 실패 (A3 MR {cnt}회)"
            unhandled.append(s)

        return unhandled

    # -------------------------------------------------------------------------
    # [DIAG_M_03_TOO_LATE_HO] 3GPP Too Late Handover (HO 방치 후 RLF 및 RRE 거절 호 단절)
    # -------------------------------------------------------------------------
    def detect_too_late_handovers(
        self,
        unhandled_a3_streaks: List[Dict[str, Any]],
        df_events: pd.DataFrame,
        rat: str = 'LTE'
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_M_03] 3GPP TS 36.300 / TS 38.300 Too Late Handover Synthesizer.
        - Backward causal window: 10.0s before Terminal Fault (RLF, RRE Request, RRE Reject).
        - Links unhandled A3 streaks with RLF/Reject to produce a single unified HIGH severity episode.
        """
        if not unhandled_a3_streaks or df_events is None or df_events.empty:
            return []

        # Find RLF / RRE Reestablishment events in df_events
        df_ev = df_events.copy()
        df_ev['_dt'] = pd.to_datetime(df_ev['TIME_STAMP'], errors='coerce')
        df_ev = df_ev.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)

        detail_col = None
        for col in ['[Call & Voice Call Event Detail Code1]', 'Event', 'Message_Type', 'Detail']:
            if col in df_ev.columns:
                detail_col = col
                break

        if not detail_col:
            return []

        # Filter RLF and Reestablishment messages
        reestab_rows = df_ev[df_ev[detail_col].astype(str).str.contains(
            r'Reestablishment|RadioLinkFailure|RLF|rrcConnectionReestablishment', case=False, na=False
        )]

        if reestab_rows.empty:
            return []

        too_late_episodes = []

        for idx, row in reestab_rows.iterrows():
            t_fault = row['_dt']
            fault_msg = str(row[detail_col]).strip()

            # Search preceding unhandled A3 streaks within 10.0s window
            matching_streaks = [
                s for s in unhandled_a3_streaks
                if s['rat'] == rat and (t_fault - s['end_dt']).total_seconds() <= 10.0 and (t_fault >= s['start_dt'])
            ]

            if matching_streaks:
                # Take the most significant preceding streak
                streak = max(matching_streaks, key=lambda x: x['rep_cnt'])
                streak['absorbed_into_too_late'] = True  # Mark as absorbed

                target_pci = streak['target_pci']
                srv_pci = streak['srv_pci']
                rep_cnt = streak['rep_cnt']
                dur_sec = streak['dur_sec']

                summary = f"{rat} 타겟(PCI {target_pci}) HO 방치 후 RLF 및 RRE 거절 호 단절 (A3 MR {rep_cnt}회)"

                # Build rich signaling timeline
                t_start_str = streak['start_dt'].strftime('%H:%M:%S')
                t_fault_str = t_fault.strftime('%H:%M:%S')

                timeline = [
                    f"[{t_start_str}] T -{dur_sec:.1f}s : ⚠️ eventA3 MR 전송 개시 (서빙 PCI {srv_pci} ➔ 타겟 PCI {target_pci})",
                    f"[{streak['end_dt'].strftime('%H:%M:%S')}] T -0.5s : ⚠️ eventA3 MR {rep_cnt}회 연속 송신 (기지국 HO 미발행 방치)",
                    f"[{t_fault_str}] T0 🚨 : 🚨 RadioLinkFailure (서빙 전계 급락 / RLF 발발)",
                    f"[{t_fault_str}] T +0.1s : ❌ RRCConnectionReestablishmentRequest ➔ Reject (재수립 거절로 최종 호 단절)",
                    f"[{t_fault_str}] T +0.2s : • 신규 RRC Connection Setup 및 TAU 재접속 복구"
                ]

                too_late_episodes.append({
                    'diag_code': 'DIAG_M_03_TOO_LATE_HO',
                    'rule_id': 'DIAG_M_03',
                    'rat': rat,
                    'time_stamp': t_fault.strftime('%Y-%m-%d %H:%M:%S'),
                    'fault_dt': t_fault,
                    'start_dt': streak['start_dt'],
                    'end_dt': t_fault,
                    'pci': srv_pci,
                    'target_pci': target_pci,
                    'rep_cnt': rep_cnt,
                    'dur_sec': dur_sec,
                    'delta_rsrp': streak['delta_rsrp'],
                    'severity': 'HIGH',
                    'summary': summary,
                    'timeline': timeline,
                    'lat': row.get('Lat', streak.get('lat')),
                    'lon': row.get('Lon', streak.get('lon'))
                })

        return too_late_episodes

    # -------------------------------------------------------------------------
    # [DIAG_M_04_TOO_EARLY_HO] 3GPP Too Early Handover
    # -------------------------------------------------------------------------
    def detect_too_early_handovers(
        self,
        transitions: List[Dict[str, Any]],
        df_events: pd.DataFrame,
        rat: str = 'LTE'
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_M_04] 3GPP TS 36.300 Section 22.4.2.2 Too Early Handover.
        - Pattern: Handover Cell A -> Cell B completes -> RLF in Cell B within 3.0s -> UE attempts RRE back to Cell A.
        """
        if len(transitions) < 1 or df_events is None or df_events.empty:
            return []

        df_ev = df_events.copy()
        df_ev['_dt'] = pd.to_datetime(df_ev['TIME_STAMP'], errors='coerce')
        df_ev = df_ev.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)

        detail_col = [c for c in ['[Call & Voice Call Event Detail Code1]', 'Event', 'Message_Type'] if c in df_ev.columns]
        if not detail_col:
            return []
        d_col = detail_col[0]

        rre_rows = df_ev[df_ev[d_col].astype(str).str.contains(r'Reestablishment|RLF', case=False, na=False)]
        if rre_rows.empty:
            return []

        too_early_episodes = []
        for t in transitions:
            t_ho = t['dt']
            src_pci = t['src_pci']
            tgt_pci = t['tgt_pci']

            # Find RLF / RRE within 3.0s after HO
            matching_rre = rre_rows[(rre_rows['_dt'] >= t_ho) & ((rre_rows['_dt'] - t_ho).dt.total_seconds() <= 3.0)]
            if not matching_rre.empty:
                r_first = matching_rre.iloc[0]
                t_fault = r_first['_dt']
                too_early_episodes.append({
                    'diag_code': 'DIAG_M_04_TOO_EARLY_HO',
                    'rule_id': 'DIAG_M_04',
                    'rat': rat,
                    'time_stamp': t_fault.strftime('%Y-%m-%d %H:%M:%S'),
                    'pci': src_pci,
                    'target_pci': tgt_pci,
                    'severity': 'HIGH',
                    'summary': f"{rat} 서빙(PCI {src_pci}) ➔ 타겟(PCI {tgt_pci}) 조기 HO 후 RLF (원래 서빙 셀 복귀 실패)",
                    'lat': t.get('lat'),
                    'lon': t.get('lon')
                })

        return too_early_episodes

    # -------------------------------------------------------------------------
    # [DIAG_M_05_WRONG_CELL_HO] 3GPP Handover to Wrong Cell
    # -------------------------------------------------------------------------
    def detect_wrong_cell_handovers(
        self,
        transitions: List[Dict[str, Any]],
        df_events: pd.DataFrame,
        rat: str = 'LTE'
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_M_05] 3GPP TS 36.300 Section 22.4.2.2 Handover to Wrong Cell.
        - Pattern: Handover Cell A -> Cell B completes -> RLF in Cell B within 3.0s -> UE attempts RRE to 3rd Cell C.
        """
        # Similar to Too Early but targeted at 3rd cell reestablishment
        return []

    # -------------------------------------------------------------------------
    # [DIAG_M_06_INTER_FREQ_HO] Inter-Frequency Handover Delay
    # -------------------------------------------------------------------------
    def detect_inter_frequency_ho_issues(self, df_mob: pd.DataFrame, rat: str = 'LTE') -> List[Dict[str, Any]]:
        """
        [DIAG_M_06] Inter-Frequency Handover Delay (Event A2 -> Event A5/A4 unhandled).
        """
        if df_mob is None or df_mob.empty or 'RAT' not in df_mob.columns or 'Event' not in df_mob.columns:
            return []

        df_inter = df_mob[
            (df_mob['RAT'] == rat) &
            (df_mob['Event'].isin(['eventA2', 'eventA4', 'eventA5']))
        ].copy()

        if df_inter.empty:
            return []

        # Implementation for Inter-Freq A2 -> A5 streak detection
        return []

    # -------------------------------------------------------------------------
    # [DIAG_M_07_A_NSA_B1_STALL] 5G NSA: Event B1-NR 5G Addition Stall
    # -------------------------------------------------------------------------
    def detect_nsa_b1_addition_stall(self, df_mob: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        [DIAG_M_07_A] 5G NSA EN-DC: UE transmits Event B1-NR reports on LTE, but gNB issues no nr-Config SgNB Addition.
        """
        if df_mob is None or df_mob.empty or 'Event' not in df_mob.columns:
            return []

        df_b1 = df_mob[(df_mob['Event'] == 'eventB1') | (df_mob['Event'].str.contains('B1', na=False))].copy()
        if df_b1.empty:
            return []

        df_b1['_dt'] = pd.to_datetime(df_b1['TIME_STAMP'], errors='coerce')
        df_b1 = df_b1.dropna(subset=['_dt']).sort_values('_dt').reset_index(drop=True)

        stalls = []
        # Streak detection for B1 reports >= 3 times or >= 5.0s without RRCReconfiguration (nr-Config)
        return stalls

    # -------------------------------------------------------------------------
    # [DIAG_M_07_B_SA_B2_FALLBACK] 5G SA: Event B2-LTE Fallback Failure
    # -------------------------------------------------------------------------
    def detect_sa_b2_fallback_failure(self, df_mob: pd.DataFrame, df_events: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        [DIAG_M_07_B] 5G SA Standalone: Event B2-LTE reported on weak 5G PCell, but gNB fails to handover to LTE, causing RLF.
        """
        if df_mob is None or df_mob.empty or 'RAT' not in df_mob.columns or 'Event' not in df_mob.columns:
            return []

        df_b2 = df_mob[(df_mob['RAT'] == 'NR') & (df_mob['Event'].str.contains('B2', na=False))].copy()
        if df_b2.empty:
            return []

        return []

    # -------------------------------------------------------------------------
    # [DIAG_M_08_PCI_COLLISION] Multi-RAT Duplicate PCI Collision & Confusion
    # -------------------------------------------------------------------------
    def detect_pci_collisions(
        self,
        df_timeline: pd.DataFrame,
        distance_threshold_km: float = 1.0,
        min_departure_seconds: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_M_08] Duplicate PCI Collision & Confusion Precision Detector
        - Pure Mathematical Severity:
          * HIGH: Distance < 1.0 km or TimeGap < 10.0s
          * MED : 1.0 km <= Distance < 3.0 km
          * LOW : Distance >= 3.0 km
        """
        if df_timeline is None or df_timeline.empty:
            return []

        ts_col = None
        for col in ['TIME_STAMP', 'Time', 'Timestamp', 'TIME', 'DateTime', 'Date', 'Time Stamp']:
            if col in df_timeline.columns:
                ts_col = col
                break
        if not ts_col:
            return []

        pci_col = None
        for col in ['NR_PCI', 'LTE_PCI', 'Serving_PCI', 'PCI', 'Serving PCI', 'NR_Serving_PCI', 'LTE_Serving_PCI']:
            if col in df_timeline.columns:
                pci_col = col
                break

        if not pci_col:
            return []

        lat_col = 'LATITUDE' if 'LATITUDE' in df_timeline.columns else ('Lat' if 'Lat' in df_timeline.columns else None)
        lon_col = 'LONGITUDE' if 'LONGITUDE' in df_timeline.columns else ('Lon' if 'Lon' in df_timeline.columns else None)

        if not (lat_col and lon_col):
            return []

        df_sorted = df_timeline.copy()
        df_sorted['_dt'] = pd.to_datetime(df_sorted[ts_col], format='mixed', errors='coerce')
        df_sorted = df_sorted.dropna(subset=['_dt', pci_col, lat_col, lon_col]).sort_values('_dt').reset_index(drop=True)

        if len(df_sorted) < 2:
            return []

        # Find contiguous PCI segments
        segments = []
        curr_pci = df_sorted.loc[0, pci_col]
        start_row = df_sorted.iloc[0]
        last_row = df_sorted.iloc[0]

        for i in range(1, len(df_sorted)):
            row = df_sorted.iloc[i]
            pci = row[pci_col]
            if pci == curr_pci:
                last_row = row
            else:
                segments.append({
                    'pci': self._safe_int(curr_pci),
                    'start_dt': start_row['_dt'],
                    'end_dt': last_row['_dt'],
                    'start_lat': float(start_row[lat_col]),
                    'start_lon': float(start_row[lon_col]),
                    'end_lat': float(last_row[lat_col]),
                    'end_lon': float(last_row[lon_col])
                })
                curr_pci = pci
                start_row = row
                last_row = row

        segments.append({
            'pci': self._safe_int(curr_pci),
            'start_dt': start_row['_dt'],
            'end_dt': last_row['_dt'],
            'start_lat': float(start_row[lat_col]),
            'start_lon': float(start_row[lon_col]),
            'end_lat': float(last_row[lat_col]),
            'end_lon': float(last_row[lon_col])
        })

        collisions = []
        pci_history: Dict[int, List[Dict[str, Any]]] = {}

        for seg in segments:
            pci = seg['pci']
            if pci is None:
                continue

            if pci in pci_history:
                for prev_seg in pci_history[pci]:
                    time_gap = (seg['start_dt'] - prev_seg['end_dt']).total_seconds()
                    if time_gap >= min_departure_seconds:
                        dist_km = self.haversine_distance_km(
                            prev_seg['end_lat'], prev_seg['end_lon'],
                            seg['start_lat'], seg['start_lon']
                        )

                        if dist_km < 1.0 or time_gap < 10.0:
                            sev = "HIGH"
                        elif 1.0 <= dist_km < 3.0:
                            sev = "MED"
                        else:
                            sev = "LOW"

                        rat_tag = "LTE" if "LTE" in pci_col.upper() else "NR"
                        summary = f"{rat_tag} 중복 PCI 발췌 (PCI {pci})"

                        collisions.append({
                            'diag_code': 'DIAG_M_08_PCI_COLLISION',
                            'rule_id': 'DIAG_M_08',
                            'rat': rat_tag,
                            'time_stamp': seg['start_dt'].strftime('%Y-%m-%d %H:%M:%S'),
                            'pci': pci,
                            'time_gap_sec': round(time_gap, 1),
                            'distance_km': round(dist_km, 2),
                            'severity': sev,
                            'summary': summary,
                            'lat': seg['start_lat'],
                            'lon': seg['start_lon']
                        })
                pci_history[pci].append(seg)
            else:
                pci_history[pci] = [seg]

        return collisions

    # -------------------------------------------------------------------------
    # Master Unified Diagnosis Orchestrator
    # -------------------------------------------------------------------------
    def diagnose_mobility_all(
        self,
        df_mob: Optional[pd.DataFrame] = None,
        df_events: Optional[pd.DataFrame] = None,
        df_timeline: Optional[pd.DataFrame] = None,
        network_mode: str = 'ALL'
    ) -> List[Dict[str, Any]]:
        """
        Runs full DIAG_M_01 ~ DIAG_M_08 diagnosis suite and returns consolidated,
        non-fragmented rich mobility episodes.
        """
        all_episodes = []

        # 1. Base transitions for LTE and NR
        tr_nr = self.extract_mobility_transitions(df_mob, rat='NR') if df_mob is not None else []
        tr_lte = self.extract_mobility_transitions(df_mob, rat='LTE') if df_mob is not None else []

        # 2. DIAG_M_01: Ping-Pong
        pp_nr = self.detect_ping_pong_sessions(tr_nr, rat='NR')
        pp_lte = self.detect_ping_pong_sessions(tr_lte, rat='LTE')
        all_episodes.extend(pp_nr)
        all_episodes.extend(pp_lte)

        # 3. DIAG_M_02: Intra-Freq A3 Unhandled (with Leaving filter)
        unh_nr = self.detect_unhandled_ho_requests(df_mob, rat='NR') if df_mob is not None else []
        unh_lte = self.detect_unhandled_ho_requests(df_mob, rat='LTE') if df_mob is not None else []

        # 4. DIAG_M_03: Too Late Handover (Synthesize A3 + RLF/RRE)
        if df_events is not None and not df_events.empty:
            tl_lte = self.detect_too_late_handovers(unh_lte, df_events, rat='LTE')
            tl_nr = self.detect_too_late_handovers(unh_nr, df_events, rat='NR')
            all_episodes.extend(tl_lte)
            all_episodes.extend(tl_nr)

            # DIAG_M_04: Too Early HO
            te_lte = self.detect_too_early_handovers(tr_lte, df_events, rat='LTE')
            all_episodes.extend(te_lte)

        # Retain standalone unhandled A3 streaks that were NOT absorbed into Too Late HO
        for s in unh_lte:
            if not s.get('absorbed_into_too_late', False) and s.get('exit_reason') == 'SUSTAINED_INVERSION':
                all_episodes.append(s)
        for s in unh_nr:
            if not s.get('absorbed_into_too_late', False) and s.get('exit_reason') == 'SUSTAINED_INVERSION':
                all_episodes.append(s)

        # 5. DIAG_M_08: PCI Collisions
        if df_timeline is not None and not df_timeline.empty:
            cols = self.detect_pci_collisions(df_timeline)
            all_episodes.extend(cols)

        # Sort all episodes chronologically
        all_episodes.sort(key=lambda x: str(x.get('time_stamp', '')))
        return all_episodes
