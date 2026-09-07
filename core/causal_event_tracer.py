"""
===============================================================================
Module Name   : causal_event_tracer.py
Location      : core/causal_event_tracer.py
Module Role   : 3GPP Protocol-Accurate Causal Incident Story Synthesizer
                - Traces end-to-end incident storylines based on standard 3GPP signaling events
                - Integrates clean Serving/Target Cell RF contexts (integer PCI/ARFCN with backtrack)
                - Formats factual, operator-friendly incident summaries without generic/fake boilerplate
===============================================================================
"""

import os
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from core.quality_criteria_registry import get_rsrp_evaluation, get_sinr_evaluation


class CausalEventTracer:
    """
    Synthesizes disjoint diagnostic events into connected, chronological incident stories
    with standard 3GPP signaling flow and robust RF context.
    """

    def __init__(self, time_window_sec: float = 10.0):
        self.time_window = timedelta(seconds=time_window_sec)

    @staticmethod
    def _parse_ts(ts_val: Any) -> Optional[datetime]:
        if ts_val is None or pd.isna(ts_val):
            return None
        if isinstance(ts_val, datetime):
            return ts_val
        if isinstance(ts_val, pd.Timestamp):
            return ts_val.to_pydatetime()
        try:
            return pd.to_datetime(str(ts_val)).to_pydatetime()
        except Exception:
            return None

    def trace_episodes(
        self,
        crit_res: Dict[str, List[Dict[str, Any]]],
        mobility_res: Dict[str, Any],
        phy_res: Optional[Dict[str, Any]] = None,
        df_qc_kpi: Optional[pd.DataFrame] = None,
        df_mob: Optional[pd.DataFrame] = None,
        csvs: Optional[Dict[str, str]] = None,
        all_l3: Optional[Dict[str, Any]] = None,
        df_kpi: Optional[pd.DataFrame] = None
    ) -> List[Dict[str, Any]]:
        """
        Collects all diagnostic events, clusters them into spatio-temporal episodes,
        and derives structured narrative causal stories.
        """
        if df_qc_kpi is None and df_kpi is not None:
            df_qc_kpi = df_kpi

        all_events: List[Dict[str, Any]] = []

        # 1. Collect Critical Faults (Domain 00)
        for rat_key in ['ENDC', 'NR', 'LTE']:
            for ev in crit_res.get(rat_key, []):
                dt = self._parse_ts(ev.get('time_stamp'))
                if not dt:
                    continue
                name = ev.get('name', 'Critical Fault')
                role = 'IMPACT'
                if 'Reject' in name or 'Drop' in name or 'RLF' in name or 'Failure' in name or 'False' in name:
                    role = 'IMPACT'
                elif 'Report' in name or 'ueInformationResponse' in name:
                    role = 'RECOVERY'

                all_events.append({
                    'timestamp': dt,
                    'role': role,
                    'domain': 'FAULT',
                    'name': name,
                    'severity': 'HIGH',
                    'detail': ev.get('root_cause', ''),
                    'radio_context': ev.get('radio_context', ''),
                    'lte_pci': ev.get('lte_pci'),
                    'lte_arfcn': ev.get('lte_arfcn'),
                    'nr_pci': ev.get('nr_pci'),
                    'nr_arfcn': ev.get('nr_arfcn'),
                    'rsrp': ev.get('rsrp'),
                    'sinr': ev.get('sinr'),
                    'missing_data': ev.get('missing_data', '')
                })

        # 2. Collect Mobility Diagnostics (Domain 01)
        # A. Unhandled HO Requests (LTE / NR)
        for u_ev in mobility_res.get('unhandled_ho_lte', []) + mobility_res.get('unhandled_ho_nr', []):
            dt_s = self._parse_ts(u_ev.get('start_ts') or u_ev.get('start_time'))
            dt_e = self._parse_ts(u_ev.get('end_ts') or u_ev.get('end_time')) or dt_s
            if not dt_s:
                continue
            is_nr = u_ev in mobility_res.get('unhandled_ho_nr', []) or 'NR' in str(u_ev.get('rat', ''))
            rat_name = '5G NR' if is_nr else 'LTE'
            srv_pci = u_ev.get('srv_pci') if u_ev.get('srv_pci') is not None else u_ev.get('serving_pci')
            srv_arfcn = u_ev.get('srv_arfcn') if u_ev.get('srv_arfcn') is not None else u_ev.get('serving_arfcn')
            nbr_pci = u_ev.get('nbr_pci') if u_ev.get('nbr_pci') is not None else u_ev.get('target_pci')
            nbr_arfcn = u_ev.get('nbr_arfcn') if u_ev.get('nbr_arfcn') is not None else u_ev.get('target_arfcn')
            rep_cnt = u_ev.get('count') if u_ev.get('count') is not None else u_ev.get('report_count', 0)
            max_delta = u_ev.get('max_delta') if u_ev.get('max_delta') is not None else u_ev.get('delta_rsrp_max', 0.0)
            dur_sec = u_ev.get('duration_sec', 0.0)
            srv_rsrp = u_ev.get('min_srv_rsrp') if u_ev.get('min_srv_rsrp') is not None else u_ev.get('srv_rsrp_avg')
            nbr_rsrp = u_ev.get('max_nbr_rsrp') if u_ev.get('max_nbr_rsrp') is not None else u_ev.get('tgt_rsrp_avg')

            all_events.append({
                'timestamp': dt_s,
                'end_timestamp': dt_e,
                'role': 'ROOT_CAUSE',
                'domain': 'MOBILITY',
                'rat': rat_name,
                'name': f"핸드오버 지시 미발행 ({rat_name} A3 방치)",
                'severity': u_ev.get('severity', 'MED'),
                'detail': f"단말이 우세한 타겟 셀(PCI {nbr_pci})을 감지하여 eventA3 MeasurementReport를 총 {rep_cnt}회 연속 전송했으나 기지국에서 {dur_sec:.1f}초간 RRCConnectionReconfiguration(핸드오버 명령) 미발행",
                'serving_pci': srv_pci,
                'serving_arfcn': srv_arfcn,
                'target_pci': nbr_pci,
                'target_arfcn': nbr_arfcn,
                'delta_rsrp': max_delta,
                'rep_cnt': rep_cnt,
                'dur_sec': dur_sec,
                'srv_rsrp': srv_rsrp,
                'tgt_rsrp': nbr_rsrp,
                'radio_context': f"서빙 PCI {srv_pci} 대비 타겟 PCI {nbr_pci}가 ΔRSRP +{max_delta:.1f}dB 더 강함"
            })

        # B. Ping-Pong Sessions (LTE / NR)
        for pp in mobility_res.get('ping_pong_nr', []) + mobility_res.get('ping_pong_lte', []):
            dt_s = self._parse_ts(pp.get('start_dt') or pp.get('start_ts') or pp.get('start_time') or pp.get('time_stamp') or pp.get('dt'))
            dt_e = self._parse_ts(pp.get('end_dt') or pp.get('end_ts') or pp.get('end_time') or pp.get('time_stamp') or pp.get('dt')) or dt_s
            if not dt_s:
                continue

            is_nr_pp = pp in mobility_res.get('ping_pong_nr', []) or 'NR' in str(pp.get('rat', ''))
            rat_name = '5G NR' if is_nr_pp else 'LTE'

            pci_seq = []
            if pp.get('pci_seq'):
                pci_seq = pp['pci_seq']
            elif pp.get('steps'):
                pci_seq = [pp['steps'][0]['src_pci']] + [st['tgt_pci'] for st in pp['steps']]
            elif pp.get('pci_chain'):
                pci_seq = [p.strip() for p in pp['pci_chain'].replace('➔', '->').split('->')]
            elif pp.get('orig_pci') is not None:
                pci_seq = [pp.get('orig_pci')]
                if pp.get('pci_pair'):
                    pci_seq.append(pp['pci_pair'][1])
                    pci_seq.append(pp.get('orig_pci'))
            elif pp.get('pci') is not None and pp.get('target_pci') is not None:
                pci_seq = [pp.get('pci'), pp.get('target_pci'), pp.get('pci')]

            clean_seq = [str(p) for p in pci_seq if p is not None and str(p) != 'None']
            if not clean_seq:
                clean_seq = [str(pp.get('pci') or pp.get('orig_pci', '미상'))]

            path_str = f"PCI {' -> '.join(clean_seq)}"
            r_trips = pp.get('rep_cnt') or (len(pp.get('steps', [])) // 2 if 'steps' in pp else pp.get('round_trips', 1))
            dur_sec = pp.get('dur_sec') if pp.get('dur_sec') is not None else pp.get('duration_sec', 0.0)
            pci_a = pp.get('pci') if pp.get('pci') is not None else (pp.get('orig_pci') if pp.get('orig_pci') is not None else clean_seq[0])
            pci_b = pp.get('target_pci') if pp.get('target_pci') is not None else (clean_seq[1] if len(clean_seq) > 1 else pci_a)
            full_pci_chain = pp.get('pci_chain') or (" ➔ ".join(clean_seq))
            pp_sev = pp.get('severity', 'MED')

            all_events.append({
                'timestamp': dt_s,
                'end_timestamp': dt_e,
                'role': 'ROOT_CAUSE',
                'domain': 'MOBILITY',
                'rat': rat_name,
                'name': f"기지국 핑퐁 핸드오버 ({r_trips}회 왕복)",
                'severity': pp_sev,
                'detail': f"{dur_sec:.1f}초간 {full_pci_chain} 핑퐁 핸드오버 발생 (체류시간 기준 만족)",
                'serving_pci': pci_a,
                'target_pci': pci_b,
                'pci_chain': full_pci_chain,
                'r_trips': r_trips,
                'dur_sec': dur_sec,
                'radio_context': f"{full_pci_chain} 핑퐁 반복"
            })

        # C. Excessive HO Latency
        for hd in mobility_res.get('ho_delays', []):
            dt = self._parse_ts(hd.get('timestamp') or hd.get('time_stamp'))
            if not dt:
                continue
            all_events.append({
                'timestamp': dt,
                'role': 'SYMPTOM',
                'domain': 'MOBILITY',
                'name': f"핸드오버 실행 지연 과다 ({hd.get('latency_ms', 0):.0f}ms)",
                'severity': 'MED',
                'detail': f"RRCConnectionReconfiguration ➔ Complete 지연 {hd.get('latency_ms', 0):.0f}ms 소요 (정상 범위 초과)",
                'serving_pci': hd.get('source_pci'),
                'target_pci': hd.get('target_pci')
            })

        # D. PCI Collision & Confusion (DIAG_M_05)
        for col in mobility_res.get('pci_collisions', []):
            dt = self._parse_ts(col.get('start_ts') or col.get('time_stamp'))
            if not dt:
                continue
            rat_tag = col.get('rat', '5G NR')
            pci_val = col.get('pci')
            all_events.append({
                'timestamp': dt,
                'role': 'TRIGGER',
                'domain': 'MOBILITY',
                'name': f"[{rat_tag}] 중복 PCI 검출 (PCI {pci_val})",
                'severity': 'HIGH',
                'detail': col.get('detail', f"동일 PCI {pci_val} ({rat_tag})가 지리적 이격 지점에서 재검출 (중복 할당 결함)"),
                'serving_pci': pci_val,
                'target_pci': pci_val,
                'diag_code': 'DIAG_M_05_PCI_COLLISION'
            })

        # 3. Collect VoLTE Audio & RTP Diagnostics
        if csvs and csvs.get('RTP') and os.path.exists(csvs.get('RTP')):
            try:
                df_rtp = pd.read_csv(csvs.get('RTP'), encoding='utf-8', low_memory=False, on_bad_lines='skip')
                if not df_rtp.empty and 'TIME_STAMP' in df_rtp.columns:
                    s_dt_rtp = pd.to_datetime(df_rtp['TIME_STAMP'], errors='coerce')
                    loss_cols = [c for c in df_rtp.columns if 'Loss' in c and '%' in c]
                    ho_int_cols = [c for c in df_rtp.columns if 'HO Data Interruption' in c]

                    if loss_cols:
                        loss_c = loss_cols[0]
                        s_loss = pd.to_numeric(df_rtp[loss_c], errors='coerce')
                        high_loss = df_rtp[s_loss >= 10.0]
                        for idx_l, r in high_loss.head(5).iterrows():
                            dt = self._parse_ts(s_dt_rtp.loc[idx_l])
                            if dt:
                                all_events.append({
                                    'timestamp': dt,
                                    'role': 'SYMPTOM',
                                    'domain': 'VOICE_RTP',
                                    'name': f"음성 패킷 손실 급증 ({r[loss_c]:.1f}%)",
                                    'severity': '높음',
                                    'detail': f"VoLTE 수신 음성 패킷 손실률 {r[loss_c]:.1f}% 발생"
                                })

                    if ho_int_cols:
                        int_c = ho_int_cols[0]
                        s_int = pd.to_numeric(df_rtp[int_c], errors='coerce')
                        high_int = df_rtp[s_int >= 100.0]
                        for idx_i, r in high_int.head(5).iterrows():
                            dt = self._parse_ts(s_dt_rtp.loc[idx_i])
                            if dt:
                                all_events.append({
                                    'timestamp': dt,
                                    'role': 'SYMPTOM',
                                    'domain': 'VOICE_RTP',
                                    'name': f"핸드오버 음성 데이터 일시 단절 ({r[int_c]:.0f}ms)",
                                    'severity': '높음',
                                    'detail': f"핸드오버 구간 음성 데이터 전송 중단 시간 {r[int_c]:.0f}ms 발생"
                                })
            except Exception:
                pass

        # D. Domain 02 Physical Layer Diagnostics
        if phy_res:
            for mr in phy_res.get('mimo_rank_restrictions', []):
                dt_s = self._parse_ts(mr.get('start_dt') or mr.get('start_ts'))
                dt_e = self._parse_ts(mr.get('end_dt') or mr.get('end_ts')) or dt_s
                if not dt_s:
                    continue
                pci = mr.get('pci', 0)
                dur = mr.get('duration_sec', 0.0)
                cause = mr.get('cause_str', '고신호 전계 상태에서 4-Layer MIMO 미동작(Rank 제한)')
                all_events.append({
                    'timestamp': dt_s,
                    'end_timestamp': dt_e,
                    'role': 'FAULT',
                    'domain': 'PHY',
                    'rat': '5G NR',
                    'name': 'MIMO Rank 제한 결함 (MIMO Layer 축소)',
                    'severity': 'MED',
                    'detail': f"{dur:.1f}초간 PCI {pci}에서 {cause}",
                    'serving_pci': pci,
                    'target_pci': None,
                    'dur_sec': dur,
                    'radio_context': f"MIMO 4-Layer 미동작 (평균 {mr.get('avg_layer', 2.0):.1f} Layer)"
                })
            for cr in phy_res.get('crc_continuous_errors', []):
                dt_s = self._parse_ts(cr.get('start_ts') or cr.get('start_dt'))
                dt_e = self._parse_ts(cr.get('end_ts') or cr.get('end_dt')) or dt_s
                if not dt_s:
                    continue
                pci = cr.get('pci', 0)
                dur = cr.get('duration_sec', 0.0)
                bler = cr.get('slot_bler', 0.0)
                cause = cr.get('cause_str', '하향 PDSCH CRC 연속 오류 및 초고BLER 발생')
                all_events.append({
                    'timestamp': dt_s,
                    'end_timestamp': dt_e,
                    'role': 'FAULT',
                    'domain': 'PHY',
                    'rat': '5G NR',
                    'name': 'PDSCH 복조 실패 (연속 CRC Error / High BLER)',
                    'severity': 'HIGH' if bler >= 50.0 or dur >= 3.0 else 'MED',
                    'detail': f"{dur:.1f}초간 PCI {pci}에서 BLER {bler:.1f}%, {cause}",
                    'serving_pci': pci,
                    'target_pci': None,
                    'dur_sec': dur,
                    'radio_context': f"PDSCH BLER {bler:.1f}% 급증"
                })

        all_events.sort(key=lambda x: x['timestamp'])
        
        # Universal Protocol-Family Causal Association
        # Family 1: Link Failure & Call Drop (RLF, Reestablishment, Drop) within 10s of same session -> Single incident
        # Family 2: Random Access & Initial Access (RACH Problem, RAR False) -> Single incident
        # Family 3: Mobility (Ping-Pong, Unhandled HO) -> Preserved as independent mobility sessions
        # Family 4: Physical Layer (Rank, CRC, RTP Loss) -> Preserved as independent physical sessions
        
        def _get_family(ev):
            name = str(ev.get('name', ''))
            domain = str(ev.get('domain', ''))
            if any(k in name for k in ['RLF', 'Radio Link Failure', 'Reestablishment', '재수립', 'Drop', '호 절단', 'e-RAB Drop', 'Connection Reject']):
                return 'LINK_FAILURE'
            if any(k in name for k in ['RACH', 'PRACH', 'RAR', '랜덤 액세스', 'Random Access']):
                return 'RACH_ACCESS'
            if '핑퐁' in name or 'A3' in name or '핸드오버' in name or domain == 'MOBILITY':
                return 'HO_MOBILITY'
            if any(k in name for k in ['MIMO', 'PDSCH', 'CRC', 'BLER']):
                return 'PHY_LAYER'
            return domain or 'OTHER'

        episodes: List[Dict[str, Any]] = []
        cluster: List[Dict[str, Any]] = []

        for ev in all_events:
            if not cluster:
                cluster.append(ev)
                continue

            prev_ev = cluster[-1]
            prev_fam = _get_family(prev_ev)
            curr_fam = _get_family(ev)
            cluster_latest_end = max(e.get('end_timestamp', e['timestamp']) for e in cluster)
            curr_start = ev['timestamp']
            time_gap = (curr_start - cluster_latest_end).total_seconds()

            # 1. Exact same protocol family within 10.0s (e.g. RLF -> RRE -> Drop, or RACH -> RAR False)
            same_fam_merge = (prev_fam == curr_fam) and (time_gap <= 10.0) and (curr_fam in ['LINK_FAILURE', 'RACH_ACCESS', 'PHY_LAYER'])

            # 2. Bounded Mobility Boundary Edge & Multi-Cell Loop Coupling
            # Merges if:
            #   (a) Same cell boundary pair (2-cell ping-pong or reverse A3, e.g. {924, 40})
            #   (b) Cycle revisit (3-cell loop A->B->C->A, or multi-cell oscillation around anchor cell)
            # Strictly prevents linear driving snowball chaining across driving route!
            def _extract_cells(item):
                cells = set()
                for k in ['serving_pci', 'target_pci', 'srv_pci', 'nbr_pci', 'src_pci', 'tgt_pci', 'pci', 'lte_pci', 'nr_pci']:
                    v = item.get(k)
                    if v is not None:
                        try:
                            iv = int(v)
                            if iv > 0: cells.add(iv)
                        except (ValueError, TypeError): pass
                return cells

            def _get_edge(item):
                return frozenset(_extract_cells(item))

            cluster_edges = {_get_edge(e) for e in cluster if len(_get_edge(e)) >= 2}
            curr_edge = _get_edge(ev)
            is_same_boundary = bool(curr_edge and len(curr_edge) >= 2 and any(curr_edge == ce for ce in cluster_edges))

            cluster_visited_cells = set().union(*[_extract_cells(e) for e in cluster])
            curr_cells = _extract_cells(ev)
            is_cycle_revisit = bool(curr_cells and len(cluster) >= 2 and (curr_cells.issubset(cluster_visited_cells) or any('핑퐁' in e.get('name', '') for e in cluster)))

            same_mobility_boundary_merge = (curr_fam == 'HO_MOBILITY') and any(_get_family(e) == 'HO_MOBILITY' for e in cluster) and \
                                           (is_same_boundary or is_cycle_revisit) and (time_gap <= 20.0)

            # 3. Direct Causal Escalation: Mobility trigger -> Subsequent Link Failure within 15.0s (Too Late HO Call Drop on involved cells)
            has_mobility_trigger = any(_get_family(e) == 'HO_MOBILITY' for e in cluster)
            is_link_failure = (curr_fam == 'LINK_FAILURE')
            cell_matches_failure = bool(curr_cells & cluster_visited_cells) if (curr_cells and cluster_visited_cells) else True
            causal_escalation_merge = (has_mobility_trigger and is_link_failure and cell_matches_failure and time_gap <= 15.0)

            # 4. Cross-layer escalation on same cell / context: PHY_LAYER -> HO_MOBILITY or LINK_FAILURE within 10.0s
            has_phy_trigger = any(_get_family(e) == 'PHY_LAYER' for e in cluster)
            is_subsequent = (curr_fam in ['HO_MOBILITY', 'LINK_FAILURE'])
            phy_escalation_merge = (has_phy_trigger and is_subsequent and time_gap <= 10.0)

            # 5. Temporal overlap within same family
            overlap_merge = (time_gap <= 1.0) and (prev_fam == curr_fam)

            can_merge = same_fam_merge or same_mobility_boundary_merge or causal_escalation_merge or phy_escalation_merge or overlap_merge

            # 3D Context Isolation: Disentangle independent carriers (e.g. LTE Anchor vs 5G NR SCG on different cells)
            c_rat = next((e.get('rat') for e in cluster if e.get('rat')), None)
            ev_rat = ev.get('rat')
            if c_rat and ev_rat and c_rat != ev_rat and ('ENDC' not in str(c_rat) and 'ENDC' not in str(ev_rat)):
                can_merge = False

            if can_merge:
                cluster.append(ev)
            else:
                episodes.append(self._synthesize_episode(cluster, df_mob, df_qc_kpi))
                cluster = [ev]

        if cluster:
            episodes.append(self._synthesize_episode(cluster, df_mob, df_qc_kpi))

        return episodes

    def _extract_rf_context(
        self,
        cluster: List[Dict[str, Any]],
        t_start: datetime,
        t_end: datetime,
        df_mob: Optional[pd.DataFrame],
        df_qc_kpi: Optional[pd.DataFrame]
    ) -> Dict[str, Any]:
        """
        Extracts robust Serving & Target Cell RF info with backward/forward time backtracking,
        ensuring integer formatting and zero NaNs.
        """
        srv_pci, srv_arfcn, srv_rsrp, srv_sinr = None, None, None, None
        tgt_pci, tgt_arfcn, tgt_rsrp, delta_rsrp = None, None, None, None

        # 1. First pass from cluster events
        srv_rat = None
        tgt_rat = None
        for e in cluster:
            if e.get('serving_pci') is not None and not srv_pci: srv_pci = e['serving_pci']
            if e.get('serving_arfcn') is not None and not srv_arfcn: srv_arfcn = e['serving_arfcn']
            if e.get('target_pci') is not None and not tgt_pci: tgt_pci = e['target_pci']
            if e.get('target_arfcn') is not None and not tgt_arfcn: tgt_arfcn = e['target_arfcn']
            if e.get('delta_rsrp') is not None and delta_rsrp is None: delta_rsrp = e['delta_rsrp']
            if e.get('lte_pci') is not None and not srv_pci: srv_pci = e['lte_pci']
            if e.get('lte_arfcn') is not None and not srv_arfcn: srv_arfcn = e['lte_arfcn']
            if e.get('rsrp') is not None and not srv_rsrp: srv_rsrp = e['rsrp']
            if e.get('sinr') is not None and not srv_sinr: srv_sinr = e['sinr']
            if e.get('rat') is not None and not srv_rat:
                srv_rat = '5G NR' if 'NR' in str(e['rat']) or '5G' in str(e['rat']) else 'LTE'

        # 2. Backtrack from df_mob (SSOT RAT and ARFCN)
        if df_mob is not None and not df_mob.empty:
            mob_t_col = next((c for c in df_mob.columns if any(k in str(c).upper() for k in ['시간', 'TIME', 'TIMESTAMP'])), df_mob.columns[0])
            df_mob_dt = pd.to_datetime(df_mob[mob_t_col], errors='coerce')
            if df_mob_dt.dropna().empty:
                df_mob_dt = pd.to_datetime('2026-08-01 ' + df_mob[mob_t_col].astype(str), errors='coerce')
            sub_mob = df_mob[df_mob_dt <= t_end]
            if not sub_mob.empty:
                for idx_b in range(len(sub_mob) - 1, -1, -1):
                    r = sub_mob.iloc[idx_b]
                    r_rat = str(r.get('RAT', ''))
                    if pd.notna(r.get('NR_Serving_PCI')):
                        if not srv_pci:
                            srv_pci = r.get('NR_Serving_PCI')
                            srv_arfcn = r.get('NR_Serving_ARFCN')
                        if not srv_rat:
                            srv_rat = '5G NR'
                    elif pd.notna(r.get('LTE_Serving_PCI')):
                        if not srv_pci:
                            srv_pci = r.get('LTE_Serving_PCI')
                            srv_arfcn = r.get('LTE_Serving_ARFCN')
                        if not srv_rat:
                            srv_rat = 'LTE'
                    elif r_rat and not srv_rat:
                        srv_rat = '5G NR' if 'NR' in r_rat or '5G' in r_rat else 'LTE'

                    if pd.notna(r.get('Serving_RSRP')) and srv_rsrp is None:
                        srv_rsrp = float(r.get('Serving_RSRP'))
                    if pd.notna(r.get('Serving_SINR')) and srv_sinr is None:
                        srv_sinr = float(r.get('Serving_SINR'))
                    if pd.notna(r.get('NBR_1_PCI')) and not tgt_pci:
                        tgt_pci = r.get('NBR_1_PCI')
                        tgt_rsrp = float(r.get('NBR_1_RSRP')) if pd.notna(r.get('NBR_1_RSRP')) else None
                        tgt_rat = srv_rat
                    if srv_pci is not None and srv_rsrp is not None:
                        break

        # 3. Clean type conversions
        def _to_int(val):
            if val is None or pd.isna(val):
                return None
            try:
                return int(float(val))
            except Exception:
                return None

        def _to_float(val):
            if val is None or pd.isna(val):
                return None
            try:
                return round(float(val), 1)
            except Exception:
                return None

        srv_pci_int = _to_int(srv_pci)
        srv_arfcn_int = _to_int(srv_arfcn)
        tgt_pci_int = _to_int(tgt_pci)
        tgt_arfcn_int = _to_int(tgt_arfcn)
        srv_rsrp_flt = _to_float(srv_rsrp)
        srv_sinr_flt = _to_float(srv_sinr)
        tgt_rsrp_flt = _to_float(tgt_rsrp)

        if delta_rsrp is None and tgt_rsrp_flt is not None and srv_rsrp_flt is not None:
            delta_rsrp = round(tgt_rsrp_flt - srv_rsrp_flt, 1)

        # 4. Context telemetry: CQI and Speed from df_qc_kpi
        srv_cqi = None
        speed_kmh = None
        if df_qc_kpi is not None and not df_qc_kpi.empty:
            kpi_t_col = next((c for c in df_qc_kpi.columns if any(k in str(c).upper() for k in ['시간', 'TIME', 'TIMESTAMP'])), df_qc_kpi.columns[0])
            try:
                df_kpi_dt = pd.to_datetime(df_qc_kpi[kpi_t_col], format='mixed', errors='coerce')
                if df_kpi_dt.dropna().empty:
                    df_kpi_dt = pd.to_datetime('2026-08-01 ' + df_qc_kpi[kpi_t_col].astype(str), format='mixed', errors='coerce')
                sub_k = df_qc_kpi[(df_kpi_dt >= t_start - pd.Timedelta(seconds=5)) & (df_kpi_dt <= t_end + pd.Timedelta(seconds=5))]
                if not sub_k.empty:
                    cqi_c = CanonicalColumnRegistry.get_actual_column(sub_k, 'Call & 5G KPI PCell RF CQI') or CanonicalColumnRegistry.get_actual_column(sub_k, 'Call & LTE KPI PCell WB CQI CW0')
                    if cqi_c:
                        s_cqi = pd.to_numeric(sub_k[cqi_c], errors='coerce').dropna()
                        if not s_cqi.empty:
                            srv_cqi = round(float(s_cqi.mean()), 1)
                    spd_c = CanonicalColumnRegistry.get_actual_column(sub_k, 'Call & GPS Speed (km/h)') or CanonicalColumnRegistry.get_actual_column(sub_k, 'GPS Speed (km/h)')
                    if spd_c:
                        s_spd = pd.to_numeric(sub_k[spd_c], errors='coerce').dropna()
                        if not s_spd.empty:
                            speed_kmh = round(float(s_spd.mean()), 1)
            except Exception:
                pass

        return {
            'srv_rat': srv_rat or 'LTE',
            'tgt_rat': tgt_rat or srv_rat or 'LTE',
            'srv_pci': srv_pci_int,
            'srv_arfcn': srv_arfcn_int,
            'srv_rsrp': srv_rsrp_flt,
            'srv_sinr': srv_sinr_flt,
            'srv_cqi': srv_cqi,
            'speed_kmh': speed_kmh,
            'tgt_pci': tgt_pci_int,
            'tgt_arfcn': tgt_arfcn_int,
            'tgt_rsrp': tgt_rsrp_flt,
            'delta_rsrp': delta_rsrp
        }

    def _synthesize_episode(
        self,
        cluster: List[Dict[str, Any]],
        df_mob: Optional[pd.DataFrame],
        df_qc_kpi: Optional[pd.DataFrame]
    ) -> Dict[str, Any]:
        """
        Synthesizes a cluster into a 3GPP signaling-accurate engineering incident story.
        """
        t_start = min(e['timestamp'] for e in cluster)
        t_end = max(e.get('end_timestamp', e['timestamp']) for e in cluster)
        duration_sec = max(0.0, (t_end - t_start).total_seconds())

        rf = self._extract_rf_context(cluster, t_start, t_end, df_mob, df_qc_kpi)
        srv_rat = rf.get('srv_rat') or 'LTE'
        tgt_rat = rf.get('tgt_rat') or srv_rat
        srv_pci = rf['srv_pci']
        srv_arfcn = rf['srv_arfcn']
        srv_rsrp = rf['srv_rsrp']
        srv_sinr = rf['srv_sinr']
        srv_cqi = rf['srv_cqi']
        speed_kmh = rf['speed_kmh']
        tgt_pci = rf['tgt_pci']
        tgt_arfcn = rf['tgt_arfcn']
        tgt_rsrp = rf['tgt_rsrp']
        delta_rsrp = rf['delta_rsrp']

        # Extract preserved attributes from cluster events
        rep_cnts = [e.get('rep_cnt') or e.get('count') for e in cluster if (e.get('rep_cnt') or e.get('count'))]
        rep_cnt = sum(rep_cnts) if rep_cnts else None
        pci_chain = next((e.get('pci_chain') for e in cluster if e.get('pci_chain')), None)

        # Determine Specific 3GPP Signals
        has_unhandled_ho = any('핸드오버 지시 미발행' in e['name'] or 'A3 방치' in e['name'] or 'A3' in e['name'] for e in cluster)
        has_rach_problem = any('RACH Problem' in e['name'] or 'preambleTransMax' in str(e.get('detail', '')) for e in cluster)
        has_rlf = any('RLF' in e['name'] or 'Radio Link Failure' in e['name'] or '무선 링크 실패' in e['name'] for e in cluster)
        has_rre_rej = any('Reestablishment Reject' in e['name'] or '재수립 거절' in e['name'] for e in cluster)
        has_drop = any('Drop' in e['name'] or '호 절단' in e['name'] or '단절' in e['name'] for e in cluster)
        has_ping_pong = any('핑퐁' in e['name'] for e in cluster)
        has_actual_call_drop = has_rlf or has_drop or has_rre_rej or any(e.get('severity') == 'HIGH' and ('Drop' in e['name'] or 'RLF' in e['name'] or 'Reject' in e['name'] or 'Failure' in e['name']) for e in cluster)

        # Build Title & Cause Conclusion using strictly factual RF & protocol analysis
        srv_beam = next((e.get('src_beam') or e.get('srv_beam') for e in cluster if (e.get('src_beam') is not None or e.get('srv_beam') is not None)), None)
        tgt_beam = next((e.get('tgt_beam') or e.get('target_ssb') or e.get('nbr_beam') for e in cluster if (e.get('tgt_beam') is not None or e.get('target_ssb') is not None or e.get('nbr_beam') is not None)), None)

        rat_tag = srv_rat if srv_rat else "LTE"
        rat_prefix = f"[{rat_tag}] "
        is_nr = (rat_tag in ['5G NR', 'NR'])
        srv_beam_str = f"/SSB{srv_beam}" if (is_nr and srv_beam is not None) else ""
        tgt_beam_str = f"/SSB{tgt_beam}" if (is_nr and tgt_beam is not None) else ""

        srv_label = f"PCI {srv_pci}{srv_beam_str}" if srv_pci is not None else "서빙 셀"
        tgt_label = f"PCI {tgt_pci}{tgt_beam_str}" if tgt_pci is not None else "타겟 셀"

        rsrp_val = srv_rsrp if srv_rsrp is not None else -140.0
        rsrp_code, _, _ = get_rsrp_evaluation(rsrp_val, is_nr=is_nr)

        # Declarative Priority Hierarchy for Title & Cause Conclusion
        candidates = []

        # Rank 1: Terminal Link Failure & Compound Failure
        if has_unhandled_ho and has_actual_call_drop:
            rep_cnt_str = f" (A3 MR {rep_cnt}회)" if rep_cnt else ""
            t = f"{rat_prefix}타겟({tgt_label}) HO 방치 후 RLF 및 RRE 거절 호 단절{rep_cnt_str}"
            c = f"서빙 셀({srv_label})의 타겟 셀({tgt_label}) Neighbor 설정 누락 또는 HO 파라미터 불일치로 HO 명령이 미발행(A3 MR {rep_cnt}회 방치)되어 서빙 링크 붕괴(RLF) 및 RRE 재수립 실패 호 단절 발발"
            candidates.append((1, t, c))
        elif has_ping_pong and has_actual_call_drop:
            pci_chain_str = pci_chain or (f"PCI {srv_pci}{srv_beam_str} ⇄ {tgt_pci}{tgt_beam_str}" if srv_pci is not None and tgt_pci is not None else "셀 간")
            t = f"{rat_prefix}핑퐁 핸드오버 중 기지국 링크 붕괴 및 호 단절 ({pci_chain_str})"
            c = f"서빙 셀과 인접 셀 간 핑퐁 핸드오버({pci_chain_str}) 진행 중 타겟 셀 진입 실패 및 무선 링크 단절(RLF) 발발"
            candidates.append((1, t, c))
        elif has_rre_rej and has_rlf:
            t = f"{rat_prefix}RLF 및 RRE 거절 호 단절"
            c = "하향 동기 상실(T310 만료) 무선 링크 단절(RLF) 후 단말이 링크 재수립을 요청했으나 대상 기지국 컨텍스트 부재로 ReestablishmentReject 회신 및 최종 호 단절 발발"
            candidates.append((1, t, c))
        elif has_rre_rej:
            t = f"{rat_prefix}RRE 재수립 거절 호 단절"
            c = "하향 RLF 발생 후 단말이 RRE 요청을 보냈으나 타겟 기지국 보안 컨텍스트 부재로 RRE Reject 회신 및 호 단절 발발"
            candidates.append((1, t, c))
        elif has_drop:
            t = f"{rat_prefix}서빙({srv_label}) e-RAB 베어러 호 단절"
            c = f"{rsrp_code} (RSRP {rsrp_val:.1f}dBm) 상태에서 기지국 제어 결함 또는 베어러 비정상 해제로 인한 통화 단절"
            candidates.append((1, t, c))
        elif has_rach_problem:
            t = f"{rat_prefix}상향 RACH 실패 RLF (RACH Problem)"
            c = f"{rsrp_code} (RSRP {rsrp_val:.1f}dBm) 상태에서 Preamble 최대 전송 횟수 도달 후 기지국 무응답으로 상향 RACH Problem RLF 발발"
            candidates.append((1, t, c))

        # Rank 2: Ping-Pong Handover / Cycle Loop (User-preferred 924 ➔ 40 ➔ 924 chain format preserved)
        if has_ping_pong:
            pci_chain_str = pci_chain or (f"PCI {srv_pci}{srv_beam_str} ⇄ {tgt_pci}{tgt_beam_str}" if srv_pci is not None and tgt_pci is not None else "셀 간")
            r_trips_val = next((ev.get('r_trips') for ev in cluster if ev.get('r_trips')), 1)
            t = f"{rat_prefix}핑퐁 핸드오버 ({pci_chain_str})"
            c = f"서빙 셀과 인접 셀 간 전계 중첩 및 HO Hysteresis 마진 부족으로 {pci_chain_str} 핑퐁 핸드오버 {r_trips_val}회 발생 ({duration_sec:.1f}초 지속)"
            candidates.append((2, t, c))

        # Rank 3: Physical Layer Degradation
        if any('MIMO' in e['name'] for e in cluster):
            t = f"{rat_prefix}고신호 구간 MIMO 랭크 저하 (Layer 제한)"
            c = next((e.get('detail') for e in cluster if 'MIMO' in e['name']), "초강전계 상태에서 MIMO 2-Layer 제한 동작")
            candidates.append((3, t, c))
        if any('PDSCH' in e['name'] or 'CRC' in e['name'] for e in cluster):
            t = f"{rat_prefix}하향 PDSCH 복조 실패 (연속 CRC Error / High BLER)"
            c = next((e.get('detail') for e in cluster if 'PDSCH' in e['name']), "PDSCH 복조 실패 및 연속 CRC Error 발발")
            candidates.append((3, t, c))

        # Rank 4: Unhandled HO / Delay (ONLY when normal call is preserved)
        if has_unhandled_ho:
            rep_cnt_str = f" (A3 MR {rep_cnt}회)" if rep_cnt else ""
            t = f"{rat_prefix}타겟({tgt_label}) HO 요청 무응답{rep_cnt_str}"
            c = f"단말이 eventA3 MR을 {rep_cnt}회 연속 송신하며 핸드오버를 요청했으나 기지국에서 RRC HO 명령을 발행하지 않고 무응답 상태로 유지되었으며, 이후 서빙 전계 회복으로 A3 보고가 자연 종료됨 (호 정상 유지)"
            candidates.append((4, t, c))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, title, cause_conclusion = candidates[0]
        else:
            first_name = cluster[0]['name'] if cluster else '무선 품질 저하'
            title = f"{rat_prefix}{first_name}"
            cause_conclusion = cluster[0].get('detail', '무선 링크 품질 저하 발생')

        # Construct Story Steps using standard 3GPP Message Names
        story_steps = []
        for e in cluster:
            ts_str = e['timestamp'].strftime('%H:%M:%S.%f')[:-3]
            name = e['name']
            detail = e.get('detail', '')

            if 'RACH Problem' in name or 'PRACH' in name:
                story_steps.append(f"[{ts_str}] 상향 PRACH 프리앰블 전송 실패 누적(preambleTransMax 도달)으로 인한 무선 링크 단절(RLF) 발발")
            elif 'RAR False' in name or '랜덤 액세스 응답 실패' in name:
                story_steps.append(f"[{ts_str}] 기지국에 Random Access Preamble을 전송했으나 응답(RAR) 미수신으로 접속 실패")
            elif 'RLF' in name or 'Radio Link Failure' in name or '무선 링크 실패' in name:
                story_steps.append(f"[{ts_str}] 하향 동기 상실(N310 임계치 도달) 및 T310 타이머 만료로 무선 링크 단절(RLF) 발발")
            elif 'Reestablishment Reject' in name or '재수립 거절' in name:
                story_steps.append(f"[{ts_str}] 단말의 RRCConnectionReestablishmentRequest(cause: otherFailure) 요청에 대해 기지국이 ReestablishmentReject를 회신함")
            elif '호 절단' in name or 'e-RAB Drop' in name or 'Call Drop' in name:
                story_steps.append(f"[{ts_str}] RRC 연결 해제 및 통화 전송 베어러(e-RAB) 비정상 종료(Call Drop) 발발")
            elif 'TAU Failure' in name:
                story_steps.append(f"[{ts_str}] 단말의 이동 위치등록 갱신(Tracking Area Update) 요청이 최종 실패함")
            elif '핸드오버 지시 미발행' in name:
                story_steps.append(f"[{ts_str}] {detail}")
            elif '핑퐁' in name:
                story_steps.append(f"[{ts_str}] {detail}")
            elif 'MIMO' in name:
                story_steps.append(f"[{ts_str}] {detail}")
            elif 'PDSCH' in name or 'CRC' in name:
                story_steps.append(f"[{ts_str}] {detail}")
            elif 'Attach Reject' in name:
                story_steps.append(f"[{ts_str}] 망 초기 접속 시 EMM Attach Reject 수신")
            elif 'Service Reject' in name:
                story_steps.append(f"[{ts_str}] 망 서비스 요청(Service Request)에 대해 코어망이 거절(Service Reject) 회신")
            else:
                story_steps.append(f"[{ts_str}] {name} 발생")

        # Determine Episode Composite Grade strictly from underlying event severities (Single SSOT)
        if any(ev.get('severity') == 'HIGH' for ev in cluster) or has_actual_call_drop or has_rach_problem:
            ep_grade = 'HIGH'
        elif any(ev.get('severity') == 'MED' for ev in cluster):
            ep_grade = 'MED'
        else:
            ep_grade = 'LOW'

        return {
            't_start': t_start,
            't_end': t_end,
            'duration_sec': duration_sec,
            'title': title,
            'srv_rat': srv_rat,
            'tgt_rat': tgt_rat,
            'srv_pci': srv_pci,
            'srv_arfcn': srv_arfcn,
            'srv_rsrp': srv_rsrp,
            'srv_sinr': srv_sinr,
            'srv_cqi': srv_cqi,
            'speed_kmh': speed_kmh,
            'tgt_pci': tgt_pci,
            'tgt_arfcn': tgt_arfcn,
            'tgt_rsrp': tgt_rsrp,
            'delta_rsrp': delta_rsrp,
            'story_steps': story_steps,
            'cause_conclusion': cause_conclusion,
            'total_events': len(cluster),
            'events': cluster,
            'pci_chain': next((ev['pci_chain'] for ev in cluster if ev.get('pci_chain')), None),
            'rep_cnt': rep_cnt,
            'has_call_drop': has_actual_call_drop,
            'has_unhandled_ho': has_unhandled_ho,
            'has_ping_pong': has_ping_pong,
            'has_rach_problem': has_rach_problem,
            'has_mimo': any('MIMO' in e['name'] for e in cluster),
            'has_crc': any('PDSCH' in e['name'] or 'CRC' in e['name'] for e in cluster),
            'grade': ep_grade,
            'severity': ep_grade
        }

    def format_incident_report(self, episodes: List[Dict[str, Any]]) -> str:
        """
        Renders clean, structured, executive-ready incident story blocks for _Analysis.txt
        with Critical-first then chronological sorting, box headers, and compact layout without blank lines.
        """
        if not episodes:
            return "  ✔ 특이 인과 연쇄 결함 미발생 (전 구간 안정적 호 운용)\n"

        lines = []
        divider = "=" * 100
        sub_div = "-" * 100

        # Calculate FSI and classify each episode (Strict HIGH, MED, LOW Standard)
        graded_episodes = []
        for ep in episodes:
            title_text = ep['title']
            steps_text = " ".join(ep['story_steps'])
            full_text = f"{title_text} {steps_text}"

            has_high_event = any(ev.get('severity') == 'HIGH' for ev in ep.get('events', []))
            is_high_text = any(k in full_text for k in ['SCG Failure', 'SCG Fail', 'Radio Link Failure', 'RLF', 'Reestablishment Reject', '호 절단', 'Call Drop', 'e-RAB Drop', '2회 왕복', '3회 왕복', '연속 핑퐁', '중복 PCI'])
            has_fault = any(ev.get('domain') == 'FAULT' or ev.get('role') == 'FAULT' for ev in ep.get('events', []))
            is_high_pp = any('핑퐁' in ev.get('name', '') and (ev.get('severity') == 'HIGH' or any(c in ev.get('name', '') for c in ['2회', '3회', '4회', '연속'])) for ev in ep.get('events', []))
            is_med_text = any(k in full_text for k in ['핸드오버 지시 지연', '핸드오버 지시 미발행', '핑퐁', '미수행', '실행 지연'])

            ep_sev = ep.get('severity') or ep.get('grade')
            if ep_sev in ['HIGH', 'MED', 'LOW']:
                grade = ep_sev
                base_w = 100.0 if grade == 'HIGH' else (50.0 if grade == 'MED' else 20.0)
            elif ep.get('severity') == 'HIGH' or has_high_event or is_high_text or has_fault or is_high_pp:
                base_w = 100.0
                grade = 'HIGH'
            elif is_med_text or any(ev.get('severity') == 'MED' for ev in ep.get('events', [])):
                base_w = 50.0
                grade = 'MED'
            else:
                base_w = 20.0
                grade = 'LOW'

            t_dur = max(0.0, ep['duration_sec'])
            n_ev = ep['total_events']
            d_rsrp = ep.get('delta_rsrp') or 0.0

            fsi = base_w * (1.0 + np.log(1.0 + t_dur)) * (1.0 + 0.1 * n_ev) * (1.0 + d_rsrp / 20.0)

            ep_copy = dict(ep)
            ep_copy['fsi'] = fsi
            ep_copy['grade'] = grade
            graded_episodes.append(ep_copy)

        high_and_med = [e for e in graded_episodes if e['grade'] in ['HIGH', 'MED']]
        # Sort: HIGH first (grade == 'HIGH' -> 0, MED -> 1), then chronological (t_start ascending)
        high_and_med.sort(key=lambda x: (0 if x['grade'] == 'HIGH' else 1, x['t_start']))
        low_eps = [e for e in graded_episodes if e['grade'] == 'LOW']

        n_high = sum(1 for e in graded_episodes if e['grade'] == 'HIGH')
        n_med = sum(1 for e in graded_episodes if e['grade'] == 'MED')
        n_low = len(low_eps)

        lines.append(divider)
        lines.append(f" [핵심 요약] 총 검출된 장애 구간: {len(episodes)}건 (HIGH: {n_high}건 │ MED: {n_med}건 │ LOW: {n_low}건)")
        lines.append(divider)

        disp_idx = 1
        for ep in high_and_med:
            srv_rat = ep.get('srv_rat') or 'LTE'
            ts_start_str = ep['t_start'].strftime('%H:%M:%S.%f')[:-3]
            ts_end_str = ep['t_end'].strftime('%H:%M:%S.%f')[:-3]
            lines.append(f"┌──────────────────────────────────────────────────────────────────────────────────────────────────┐")
            lines.append(f"│ [{ep['grade']}] [장애 구간 #{disp_idx:02d} ({srv_rat})] {ts_start_str} ~ {ts_end_str} (지속시간: {ep['duration_sec']:.1f}초)")
            lines.append(f"│ 요약: {ep['title']}")
            lines.append(f"└──────────────────────────────────────────────────────────────────────────────────────────────────┘")

            # 1. RF Environment (Context-aware dynamic metric selection with SSOT RAT)
            arfcn_label = 'NR-ARFCN' if '5G' in srv_rat or 'NR' in srv_rat else 'EARFCN'
            srv_pci_val = ep.get('srv_pci')
            srv_pci_str = f"PCI {srv_pci_val}" if srv_pci_val is not None else "미상"
            srv_arfcn_str = f", {arfcn_label} {ep['srv_arfcn']}" if ep.get('srv_arfcn') is not None else ""
            
            rf_parts = [f"서빙 {srv_rat} {srv_pci_str}{srv_arfcn_str}"]
            if ep.get('srv_rsrp') is not None:
                rf_parts.append(f"RSRP {ep['srv_rsrp']:.1f} dBm")
            if ep.get('srv_sinr') is not None:
                if ep['srv_sinr'] < 3.0:
                    rf_parts.append(f"SINR {ep['srv_sinr']:.1f} dB (간섭 심화)")
                else:
                    rf_parts.append(f"SINR {ep['srv_sinr']:.1f} dB")
            if ep.get('srv_cqi') is not None and ep['srv_cqi'] <= 5.0:
                rf_parts.append(f"CQI {ep['srv_cqi']:.1f} (품질 급락)")

            if ep.get('tgt_pci') is not None:
                tgt_rat = ep.get('tgt_rat') or srv_rat
                tgt_arfcn_label = 'NR-ARFCN' if '5G' in tgt_rat or 'NR' in tgt_rat else 'EARFCN'
                tgt_pci_val = ep['tgt_pci']
                tgt_arfcn_str = f", {tgt_arfcn_label} {ep['tgt_arfcn']}" if ep.get('tgt_arfcn') is not None else ""
                tgt_sub = [f"타겟 {tgt_rat} PCI {tgt_pci_val}{tgt_arfcn_str}"]
                if ep.get('tgt_rsrp') is not None:
                    tgt_sub.append(f"RSRP {ep['tgt_rsrp']:.1f} dBm")
                if ep.get('delta_rsrp') is not None:
                    tgt_sub.append(f"+{ep['delta_rsrp']:.1f} dB 우세")
                rf_parts.append(" | ".join(tgt_sub))

            if ep.get('speed_kmh') is not None and ep['speed_kmh'] >= 40.0:
                rf_parts.append(f"단말 속도: {ep['speed_kmh']:.1f} km/h (고속 이동)")

            lines.append(f"  [1] 발생 당시 무선 환경: {' | '.join(rf_parts)}")

            # 2. Incident Storyline
            lines.append("  [2] 장애 진행 과정:")
            for step in ep['story_steps']:
                lines.append(f"      • {step}")

            # 3. Cause Conclusion (No arrow prefix)
            cause_text = ep.get('cause_conclusion', '상세 원인 미상')
            lines.append(f"  [3] 추정 원인: {cause_text}")
            lines.append(sub_div)
            disp_idx += 1

        if low_eps:
            lines.append(f"■ [LOW 지연 구간 요약] 총 {len(low_eps)}건 발생 (단순 대기 및 일시 지연으로 호 단절 미발생)")
            for m in low_eps:
                m_start = m['t_start'].strftime('%H:%M:%S.%f')[:-3]
                lines.append(f"  • [{m_start}] {m['duration_sec']:.1f}초간 {m['title']}")
            lines.append(sub_div)

        lines.append("")
        return "\n".join(lines)

    def to_dataframe(self, episodes: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Converts synthesized incident episodes into a clean, structured pandas DataFrame.
        """
        if not episodes:
            return pd.DataFrame(columns=[
                'No', '시간 구간', '망 구분 (RAT)', '장애 제목', '서빙 PCI', '타겟 PCI', '추정 원인', '지속 시간 (초)', '심각도'
            ])

        rows = []
        for idx, ep in enumerate(episodes, 1):
            ts_start_str = ep['t_start'].strftime('%H:%M:%S')
            ts_end_str = ep['t_end'].strftime('%H:%M:%S')
            srv_rat = ep.get('srv_rat') or ('5G NR' if 'NR' in str(ep.get('title')) else 'LTE')
            grade = ep.get('grade') or ('Critical' if any(k in ep.get('title', '') for k in ['절단', 'RLF', 'Reject', 'Drop']) else 'Major')
            
            rows.append({
                'No': idx,
                '시간 구간': f"{ts_start_str} ~ {ts_end_str}",
                '망 구분 (RAT)': srv_rat,
                '장애 제목': ep.get('title', ''),
                '서빙 PCI': ep.get('srv_pci', '-'),
                '타겟 PCI': ep.get('tgt_pci', '-'),
                '추정 원인': ep.get('cause_conclusion', ''),
                '지속 시간 (초)': round(ep.get('duration_sec', 0.0), 1),
                '심각도': grade
            })

        return pd.DataFrame(rows)
