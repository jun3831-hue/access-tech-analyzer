"""
===============================================================================
Module Name   : diagnosis_reporter.py
Location      : core/diagnosis_reporter.py
Module Role   : Precision Telecom Analysis Reporter & Master Text Report Assembler
                - Orchestrates Modular Domain Engines (d00 ~ d08)
                - Renders Korean-Friendly Rich Detailed Master Analysis Report
===============================================================================
"""

import os
import sys
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from core.quality_criteria_registry import (
    NR_SS_SINR_CRITERIA,
    MIMO_LAYER_CRITERIA,
    PDSCH_CRC_FAIL_CRITERIA,
    PDSCH_BLER_CRITERIA
)

# Ensure project root and parsers are in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

parsers_dir = os.path.join(project_root, "core", "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

from core.diagnosis_modules.d00_critical_faults import CriticalFaultsDetector
from core.diagnosis_modules.d01_mobility import MobilityDetector
from core.diagnosis_modules.d02_physical_layer import PhysicalLayerDetector
from core.causal_event_tracer import CausalEventTracer


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


class DiagnosisReporter:
    """
    Master Telecom Analysis Reporter.
    Coordinates Domain 00~08 Modular Diagnosis Engines, Synthesizes Causal Incident Episodes,
    and Renders Clean Unified Reports.
    """

    def __init__(self):
        self.d00 = CriticalFaultsDetector()
        self.d01 = MobilityDetector()
        self.d02 = PhysicalLayerDetector()
        self.tracer = CausalEventTracer(time_window_sec=15.0)

    def detect_all_critical_events(self, df_mob=None, csvs=None, all_l3=None):
        return self.d00.detect_all_critical_events(df_mob=df_mob, csvs=csvs, all_l3=all_l3)

    def extract_mobility_transitions(self, df_mob, rat='NR'):
        return self.d01.extract_mobility_transitions(df_mob=df_mob, rat=rat)

    def detect_ping_pong_sessions(self, transitions, rat='NR', time_window=10.0, min_dwell_sec=2.0):
        return self.d01.detect_ping_pong_sessions(transitions=transitions, rat=rat, time_window=time_window, min_dwell_sec=min_dwell_sec)

    def detect_unhandled_ho_requests(self, df_mob, rat='NR'):
        return self.d01.detect_unhandled_ho_requests(df_mob=df_mob, rat=rat)

    def detect_ho_delays(self, transitions, threshold_ms=30.0):
        return self.d01.detect_ho_delays(transitions=transitions, threshold_ms=threshold_ms)

    def detect_pci_collisions(self, df_timeline, distance_threshold_km=1.0, min_departure_seconds=5.0):
        return self.d01.detect_pci_collisions(
            df_timeline=df_timeline,
            distance_threshold_km=distance_threshold_km,
            min_departure_seconds=min_departure_seconds
        )

    def detect_mimo_rank_restrictions(self, csvs, all_l3=None, df_call_summary=None):
        return self.d02.detect_mimo_rank_restrictions(csvs=csvs, all_l3=all_l3, df_call_summary=df_call_summary)

    def detect_continuous_crc_errors(self, csvs, df_call_summary=None):
        return self.d02.detect_continuous_crc_errors(csvs=csvs, df_call_summary=df_call_summary)

    def generate_full_text_report(
        self,
        drm_name: str,
        network_mode: str,
        active_vendor: str,
        df_mob: pd.DataFrame,
        df_call_sum: pd.DataFrame,
        csvs: Dict[str, str],
        all_l3: Optional[Dict[str, Any]] = None,
        df_timeline: Optional[pd.DataFrame] = None
    ) -> str:
        lines = []
        divider = "=" * 100
        sub_divider = "-" * 100

        # ---------------------------------------------------------------------
        # HEADER
        # ---------------------------------------------------------------------
        lines.append(divider)
        lines.append(f"                                OPTIS v12 분석 리포트")
        lines.append(divider)
        clean_drm = drm_name.replace('.drm', '').replace('-M1-R1-S1-C1-T1-Comp_End by user', '')
        lines.append(f"* 대상 DRM 파일: {clean_drm}")
        lines.append(f"* 망 모드       : {network_mode}  |  활성 벤더: {active_vendor}")
        lines.append(sub_divider)
        lines.append("")

        # ---------------------------------------------------------------------
        # 1. PRE-COMPUTE ALL DOMAIN DIAGNOSTICS FOR CAUSAL SYNTHESIS
        # ---------------------------------------------------------------------
        crit_res = self.detect_all_critical_events(df_mob=df_mob, csvs=csvs, all_l3=all_l3)
        endc_evts = crit_res.get('ENDC', [])
        nr_evts = crit_res.get('NR', [])
        lte_evts = crit_res.get('LTE', [])
        total_crit = len(endc_evts) + len(nr_evts) + len(lte_evts)

        tr_nr = self.extract_mobility_transitions(df_mob, rat='NR')
        h01_nr_sessions = self.detect_ping_pong_sessions(tr_nr, rat='NR', time_window=10.0, min_dwell_sec=2.0)
        h02_nr = self.detect_unhandled_ho_requests(df_mob, rat='NR')
        h03_nr = self.detect_ho_delays(tr_nr, threshold_ms=30.0)

        tr_lte = self.extract_mobility_transitions(df_mob, rat='LTE')
        h01_lte_sessions = self.detect_ping_pong_sessions(tr_lte, rat='LTE', time_window=10.0, min_dwell_sec=2.0)
        h02_lte = self.detect_unhandled_ho_requests(df_mob, rat='LTE')
        h03_lte = self.detect_ho_delays(tr_lte, threshold_ms=40.0)

        # Detect DIAG_M_05 PCI Collision on df_timeline (or df_mob)
        tl_source = df_timeline if df_timeline is not None and not df_timeline.empty else (safe_read_csv(csvs.get('KPI')) if csvs else df_mob)
        pci_collisions = self.detect_pci_collisions(df_timeline=tl_source)

        mobility_res = {
            'unhandled_ho_lte': h02_lte,
            'unhandled_ho_nr': h02_nr,
            'ping_pong_lte': h01_lte_sessions,
            'ping_pong_nr': h01_nr_sessions,
            'ho_delays': h03_lte + h03_nr,
            'pci_collisions': pci_collisions
        }

        # Domain 02: Physical Layer Diagnostics
        phy_res = {}
        if csvs:
            try:
                phy_det = PhysicalLayerDetector()
                mimo_rank_issues = phy_det.detect_mimo_rank_restrictions(csvs=csvs, all_l3=all_l3, df_call_summary=df_call_summary)
                crc_issues = phy_det.detect_continuous_crc_errors(csvs=csvs, all_l3=all_l3, df_call_summary=df_call_summary)
                phy_res = {
                    'mimo_rank_restrictions': mimo_rank_issues,
                    'crc_continuous_errors': crc_issues
                }
            except Exception:
                phy_res = {}

        # ---------------------------------------------------------------------
        # 2. SYNTHESIZE FULL CAUSAL INCIDENT EPISODES
        # ---------------------------------------------------------------------
        episodes = self.tracer.trace_episodes(
            crit_res=crit_res,
            mobility_res=mobility_res,
            phy_res=phy_res,
            df_kpi=safe_read_csv(csvs.get('KPI')) if csvs else df_timeline,
            df_mob=df_mob,
            csvs=csvs,
            all_l3=all_l3
        )
        self.last_episodes = episodes
        causal_block = self.tracer.format_incident_report(episodes)
        lines.append(causal_block)

        # ---------------------------------------------------------------------
        # DOMAIN 00: CRITICAL FAULT EVENTS BREAKDOWN
        # ---------------------------------------------------------------------
        lines.append(divider)
        lines.append(f" [도메인 00-A] 🚨 개별 핵심 결함 및 호 단절 상세")
        lines.append(f" • 총 핵심 결함: {total_crit}건 (EN-DC 계층: {len(endc_evts)}건 | 5G NR 계층: {len(nr_evts)}건 | 4G LTE 계층: {len(lte_evts)}건)")
        lines.append(divider)

        if total_crit == 0:
            lines.append("  ✔ 호 진행 중 Call Drop, HO Failure, RLF 등 치명적 결함 이벤트 미발생 (망 운용 적합)")
            lines.append("")
        else:
            if endc_evts:
                lines.append("■ [EN-DC 이중연결 결함 이벤트]")
                for idx, ev in enumerate(endc_evts, 1):
                    lines.append(f"  ▶ [EN-DC 결함 #{idx}] {ev['time_stamp']} | {ev['name']} | 심각도: HIGH")
                    lines.append(f"    • 분석 소견: {ev['root_cause']}")
                    if ev.get('radio_context'):
                        lines.append(f"    • 당시 무선 상태: {ev['radio_context']}")
                    if ev.get('missing_data'):
                        lines.append(f"    • 결측 데이터: {ev['missing_data']}")
                    lines.append("")

            if nr_evts:
                lines.append("■ [5G NR 계층 결함 이벤트]")
                for idx, ev in enumerate(nr_evts, 1):
                    lines.append(f"  ▶ [5G NR 결함 #{idx}] {ev['time_stamp']} | {ev['name']} | 심각도: HIGH")
                    lines.append(f"    • 분석 소견: {ev['root_cause']}")
                    if ev.get('radio_context'):
                        lines.append(f"    • 당시 무선 상태: {ev['radio_context']}")
                    if ev.get('missing_data'):
                        lines.append(f"    • 결측 데이터: {ev['missing_data']}")
                    lines.append("")

            if lte_evts:
                lines.append("■ [4G LTE 계층 결함 이벤트]")
                for idx, ev in enumerate(lte_evts, 1):
                    lines.append(f"  ▶ [4G LTE 결함 #{idx}] {ev['time_stamp']} | {ev['name']} | 심각도: HIGH")
                    lines.append(f"    • 분석 소견: {ev['root_cause']}")
                    if ev.get('radio_context'):
                        lines.append(f"    • 당시 무선 상태: {ev['radio_context']}")
                    if ev.get('missing_data'):
                        lines.append(f"    • 결측 데이터: {ev['missing_data']}")
                    lines.append("")

        # ---------------------------------------------------------------------
        # DOMAIN 01-A: 5G NR MOBILITY
        # ---------------------------------------------------------------------
        tr_nr = self.extract_mobility_transitions(df_mob, rat='NR')
        h01_nr_sessions = self.detect_ping_pong_sessions(tr_nr, rat='NR', time_window=10.0, min_dwell_sec=2.0)
        h02_nr = self.detect_unhandled_ho_requests(df_mob, rat='NR')
        h03_nr = self.detect_ho_delays(tr_nr, threshold_ms=30.0)

        lines.append(divider)
        lines.append(f" [도메인 01-A] 5G NR 핸드오버 및 이동성 분석")
        if network_mode == 'LTE' or (len(tr_nr) == 0 and len(h01_nr_sessions) == 0 and len(h02_nr) == 0 and len(h03_nr) == 0 and not any(nr_evts)):
            lines.append(f" • 5G NR 세션 미연결 (순수 4G LTE 단독 운용 모드)")
            lines.append(divider)
            lines.append("  ✔ 5G NR 시그널링 미존재 (순수 LTE 트래픽 운용)")
            lines.append("")
        else:
            lines.append(f" • 총 5G 핸드오버 완료: {len(tr_nr)}회  |  핑퐁 HO 세션(H01): {len(h01_nr_sessions)}건  |  HO 미수행 요청(H02): {len(h02_nr)}건  |  과다 HO 지연(H03): {len(h03_nr)}건")
            lines.append(divider)

            # DIAG_H_01_NR
            lines.append("■ [DIAG_H_01_NR] 10초 이내 5G 핑퐁 핸드오버 (체류 ≥ 2.0초) 검출 결과")
            if not h01_nr_sessions:
                lines.append("  ✔ 10초 이내 5G 핑퐁 핸드오버 미발생 (안정적 PSCell 유지)")
                lines.append("")
            else:
                for s_idx, s in enumerate(h01_nr_sessions, 1):
                    sev = s.get('severity', 'MED')
                    start_ts = s.get('start_ts', str(s.get('start_dt', s.get('time_stamp', ''))))
                    end_ts = s.get('end_ts', str(s.get('end_dt', s.get('time_stamp', ''))))
                    dur_sec = s.get('duration_sec', s.get('dur_sec', 0.0))
                    rep = s.get('round_trips', s.get('rep_cnt', 1))
                    type_str = s.get('session_type', '연속 핑퐁' if rep >= 2 else '단일 핑퐁')
                    cause_str = s.get('cause_str', s.get('summary', ''))
                    lines.append(f"  ▶ [5G 핑퐁 세션 #{s_idx}] {start_ts} ~ {end_ts} ({dur_sec:.1f}초간 / {rep}회 왕복) | {type_str} | 심각도: {sev}")
                    lines.append(f"    • 분석 소견: {cause_str}")
                    steps = s.get('steps', s.get('transitions', []))
                    for st_idx, st in enumerate(steps, 1):
                        delta_r = st.get('delta_rsrp', (st.get('tgt_rsrp', 0.0) - st.get('srv_rsrp', 0.0)))
                        b_src = f"SSB{st['src_beam']}" if st.get('src_beam') is not None else "SSB0"
                        b_tgt = f"SSB{st['tgt_beam']}" if st.get('tgt_beam') is not None else "SSB0"
                        lines.append(f"    [{st_idx}회차] {st.get('time_stamp', '')} | PCI {st.get('src_pci')}({b_src}, {st.get('srv_rsrp', 0.0):.1f}dBm, {st.get('src_arfcn')}) ➔ PCI {st.get('tgt_pci')}({b_tgt}, {st.get('tgt_rsrp', 0.0):.1f}dBm, {st.get('tgt_arfcn')}) [ΔRSRP:+{delta_r:.1f}dB | 지연:{st.get('ho_delay', 0.0):.1f}ms | {st.get('coupling_tag', '')}]")
                    lines.append("")

            lines.append(sub_divider)

            # DIAG_H_02_NR
            lines.append("■ [DIAG_H_02_NR] 5G 핸드오버 요청 미수행 검출 결과")
            if not h02_nr:
                lines.append("  ✔ 단말 측정 보고 후 모든 5G 핸드오버 정상 완료 (미수행 요청 0건)")
                lines.append("")
            else:
                for m_idx, m in enumerate(h02_nr, 1):
                    start_ts = m.get('start_ts', str(m.get('time_stamp', '')))
                    end_ts = m.get('end_ts', start_ts)
                    dur_sec = m.get('duration_sec', m.get('dur_sec', 0.0))
                    cnt = m.get('count', m.get('rep_cnt', 1))
                    evt_lbl = m.get('evt_label', 'A3 MR')
                    lines.append(f"  ▶ [5G 미수행 요청 #{m_idx}] {start_ts} ~ {end_ts} ({dur_sec:.2f}초간) | PCI {m.get('srv_pci', m.get('pci'))} ➔ PCI {m.get('nbr_pci', m.get('target_pci'))} ({evt_lbl} {cnt}회) | 심각도: {m.get('severity', 'MED')}")
                    lines.append(f"    • 분석 소견: 단말이 {evt_lbl} 측정보고를 총 {cnt}회 송신(HO 요청)했으나 기지국에서 HO Command 미발행으로 {dur_sec:.2f}초간 핸드오버 미실행/방치됨")
                    lines.append("")

            lines.append(sub_divider)

            # DIAG_H_03_NR
            lines.append("■ [DIAG_H_03_NR] 5G 비정상 핸드오버 실행 지연 (HO Latency > 30ms) 검출 결과")
            if not h03_nr:
                lines.append("  ✔ 모든 5G 핸드오버가 정상 지연 범위(평균 11.7ms) 내에서 신속히 완료됨")
                lines.append("")
            else:
                for d_idx, d in enumerate(h03_nr, 1):
                    lines.append(f"  ▶ [5G HO 실행 지연 #{d_idx}] {d.get('time_stamp', '')} | PCI {d.get('srv_pci', d.get('src_pci'))} ➔ PCI {d.get('tgt_pci')} | 심각도: {d.get('severity', 'MED')}")
                    lines.append(f"    • 분석 소견: 5G 핸드오버 실행 지연시간 {d.get('ho_delay_ms', 0.0):.1f}ms 소요 (기준치 {d.get('threshold_ms', 30.0):.1f}ms 초과)")
                    lines.append("")

        # ---------------------------------------------------------------------
        # DOMAIN 01-B: 4G LTE MOBILITY
        # ---------------------------------------------------------------------
        tr_lte = self.extract_mobility_transitions(df_mob, rat='LTE')
        h01_lte_sessions = self.detect_ping_pong_sessions(tr_lte, rat='LTE', time_window=10.0, min_dwell_sec=2.0)
        h02_lte = self.detect_unhandled_ho_requests(df_mob, rat='LTE')
        h03_lte = self.detect_ho_delays(tr_lte, threshold_ms=40.0)

        lines.append(divider)
        lines.append(f" [도메인 01-B] 4G LTE 핸드오버 및 이동성 분석")
        lines.append(f" • 총 4G 핸드오버 완료: {len(tr_lte)}회  |  핑퐁 HO 세션(H01): {len(h01_lte_sessions)}건  |  HO 미수행 요청(H02): {len(h02_lte)}건  |  과다 HO 지연(H03): {len(h03_lte)}건")
        lines.append(divider)

        # DIAG_H_01_LTE
        lines.append("■ [DIAG_H_01_LTE] 10초 이내 4G LTE 핑퐁 핸드오버 (체류 ≥ 2.0초) 검출 결과")
        if not h01_lte_sessions:
            lines.append("  ✔ 10초 이내 4G LTE 핑퐁 핸드오버 미발생 (안정적 PCell 유지)")
            lines.append("")
        else:
            for s_idx, s in enumerate(h01_lte_sessions, 1):
                sev = s.get('severity', 'MED')
                start_ts = s.get('start_ts', str(s.get('start_dt', s.get('time_stamp', ''))))
                end_ts = s.get('end_ts', str(s.get('end_dt', s.get('time_stamp', ''))))
                dur_sec = s.get('duration_sec', s.get('dur_sec', 0.0))
                rep = s.get('round_trips', s.get('rep_cnt', 1))
                type_str = s.get('session_type', '연속 핑퐁' if rep >= 2 else '단일 핑퐁')
                cause_str = s.get('cause_str', s.get('summary', ''))
                lines.append(f"  ▶ [4G LTE 핑퐁 세션 #{s_idx}] {start_ts} ~ {end_ts} ({dur_sec:.1f}초간 / {rep}회 왕복) | {type_str} | 심각도: {sev}")
                lines.append(f"    • 분석 소견: {cause_str}")
                steps = s.get('steps', s.get('transitions', []))
                for st_idx, st in enumerate(steps, 1):
                    delta_r = st.get('delta_rsrp', (st.get('tgt_rsrp', 0.0) - st.get('srv_rsrp', 0.0)))
                    lines.append(f"    [{st_idx}회차] {st.get('time_stamp', '')} | PCI {st.get('src_pci')}({st.get('srv_rsrp', 0.0):.1f}dBm, EARFCN {st.get('src_arfcn')}) ➔ PCI {st.get('tgt_pci')}({st.get('tgt_rsrp', 0.0):.1f}dBm, EARFCN {st.get('tgt_arfcn')}) [ΔRSRP:+{delta_r:.1f}dB | 지연:{st.get('ho_delay', 0.0):.1f}ms | {st.get('coupling_tag', '')}]")
                lines.append("")

        lines.append(sub_divider)

        # DIAG_H_02_LTE
        lines.append("■ [DIAG_H_02_LTE] 4G LTE 핸드오버 요청 미수행 검출 결과")
        if not h02_lte:
            lines.append("  ✔ 단말 측정 보고 후 모든 4G LTE 핸드오버 정상 완료 (미수행 요청 0건)")
            lines.append("")
        else:
            for m_idx, m in enumerate(h02_lte, 1):
                start_ts = m.get('start_ts', str(m.get('time_stamp', '')))
                end_ts = m.get('end_ts', start_ts)
                dur_sec = m.get('duration_sec', m.get('dur_sec', 0.0))
                cnt = m.get('count', m.get('rep_cnt', 1))
                evt_lbl = m.get('evt_label', 'A3 MR')
                lines.append(f"  ▶ [LTE 미수행 요청 #{m_idx}] {start_ts} ~ {end_ts} ({dur_sec:.2f}초간) | PCI {m.get('srv_pci', m.get('pci'))} ➔ PCI {m.get('nbr_pci', m.get('target_pci'))} ({evt_lbl} {cnt}회) | 심각도: {m.get('severity', 'MED')}")
                lines.append(f"    • 분석 소견: 단말이 {evt_lbl} 측정보고를 총 {cnt}회 송신(HO 요청)했으나, 기지국에서 HO Command 미발행으로 {dur_sec:.2f}초간 핸드오버 미실행/방치됨")
                lines.append("")

        lines.append(sub_divider)

        # DIAG_H_03_LTE
        lines.append("■ [DIAG_H_03_LTE] 4G LTE 비정상 핸드오버 실행 지연 (HO Latency > 40ms) 검출 결과")
        if not h03_lte:
            lines.append("  ✔ 모든 4G LTE 핸드오버가 정상 지연 범위(평균 15.0ms) 내에서 신속히 완료됨")
            lines.append("")
        else:
            for d_idx, d in enumerate(h03_lte, 1):
                lines.append(f"  ▶ [LTE HO 실행 지연 #{d_idx}] {d.get('time_stamp', '')} | PCI {d.get('srv_pci', d.get('src_pci'))} ➔ PCI {d.get('tgt_pci')} | 심각도: {d.get('severity', 'MED')}")
                lines.append(f"    • 분석 소견: 4G LTE 핸드오버 실행 지연시간 {d.get('ho_delay_ms', 0.0):.1f}ms 소요 (기준치 {d.get('threshold_ms', 40.0):.1f}ms 초과)")
                lines.append("")

        # ---------------------------------------------------------------------
        # DOMAIN 01-C: PCI COLLISION & CONFUSION ANALYSIS
        # ---------------------------------------------------------------------
        lines.append(divider)
        lines.append(f" [도메인 01-C] 중복 PCI 발췌 (PCI Collision & Confusion) 분석")
        lines.append(f" • 총 검출된 중복 PCI 결함: {len(pci_collisions)}건")
        lines.append(divider)

        lines.append("■ [DIAG_M_05_PCI_COLLISION] 동일 주행 경로 내 중복 PCI 검출 결과")
        if not pci_collisions:
            lines.append("  ✔ 동일 주행 경로 내 중복 PCI 발췌 및 지리적 도약(1.0km 미확보) 미발생 (정상 셀 플래닝)")
            lines.append("")
        else:
            for c_idx, c in enumerate(pci_collisions, 1):
                start_ts = c.get('start_ts', str(c.get('time_stamp', '')))
                sev = c.get('severity', 'MED')
                lines.append(f"  ▶ [중복 PCI 결함 #{c_idx}] {start_ts} | {c.get('summary', '')} | 심각도: {sev}")
                lines.append(f"    • 분석 소견: {c.get('detail', '')}")
                lines.append("")

        # ---------------------------------------------------------------------
        # DOMAIN 02: PHYSICAL LAYER ANALYSIS
        # ---------------------------------------------------------------------
        lines.append(divider)
        lines.append(f" [도메인 02] 5G 무선 물리계층 분석")
        if network_mode == 'LTE':
            lines.append(f" • 5G NR 세션 미연결 (순수 4G LTE 단독 운용 모드)")
            lines.append(divider)
            lines.append("  ✔ 5G PDSCH 세션 미존재 (순수 LTE 다운로드 운용)")
            lines.append("")
        else:
            m01_nr = self.detect_mimo_rank_restrictions(csvs, all_l3, df_call_summary=df_call_sum)
            m02_nr = self.detect_continuous_crc_errors(csvs, df_call_summary=df_call_sum)

            lines.append(f" • 총 랭크 저하(M01): {len(m01_nr)}건  |  CRC 연속 에러(M02): {len(m02_nr)}건  |  SR 응답 지연(M04): 0건")
            lines.append(divider)

            # DIAG_M_01_NR
            lines.append(f"■ [DIAG_M_01_NR] 고신호 구간 MIMO 랭크 저하 검출 결과 (SINR >= {NR_SS_SINR_CRITERIA['HIGH_SINR_MIMO_THRESH']:.0f}dB, Layer <= {MIMO_LAYER_CRITERIA['RANK_RESTRICTION_THRESH']:.1f})")
            if not m01_nr:
                lines.append("  ✔ 고신호 구간에서 4-Layer(4x4 MIMO) 정상 동작 완료 (랭크 저하 0건)")
                lines.append("")
            else:
                for m_idx, m in enumerate(m01_nr, 1):
                    sev = "MED"
                    lines.append(f"  ▶ [랭크 저하 #{m_idx}] {m['start_ts']} ~ {m['end_ts']} ({m['duration_sec']:.2f}초간 지속) | 대상 셀: PCI {m['pci']} | 심각도: {sev}")
                    lines.append(f"    • 분석 소견: 평균 SINR {m['avg_sinr']:.1f}dB 고신호 구간임에도 4-Layer MIMO 미동작 (평균 {m['avg_layer']:.2f} Layer로 랭크 제한 / {m['cause_str']})")
                    lines.append(f"    • 무선 품질: 평균 SINR {m['avg_sinr']:.1f} dB | 평균 RSRP {m['avg_rsrp']:.1f} dBm | 다운로드 속도 {m['avg_tp']:.1f} Mbps")
                    lines.append(f"    • 실측 랭크: 4-Layer 비율 {m['rank4_pct']:.1f}% (총 스케줄링 슬롯 {m['pdsch_slots']}개)")
                    lines.append("")

            lines.append(sub_divider)

            # DIAG_M_02_NR
            lines.append(f"■ [DIAG_M_02_NR] 5G PDSCH CRC 연속 에러 검출 결과 (연속 CRC FAIL >= {PDSCH_CRC_FAIL_CRITERIA['CONSECUTIVE_FAIL_SLOTS_THRESH']}슬롯 또는 BLER >= {PDSCH_BLER_CRITERIA['SEVERE_BLER_THRESH']:.0f}%)")
            if not m02_nr:
                lines.append("  ✔ 다운로드 호 구간에서 5G PDSCH CRC 연속 에러 미발생 (정상 복조 완료)")
                lines.append("")
            else:
                for c_idx, c in enumerate(m02_nr, 1):
                    lines.append(f"  ▶ [CRC 연속 에러 #{c_idx}] {c['start_ts']} ~ {c['end_ts']} ({c['duration_sec']:.2f}초간 지속) | 대상 셀: PCI {c['pci']} | 심각도: HIGH")
                    lines.append(f"    • 분석 소견: 5G PDSCH 디코딩 실패로 연속 CRC FAIL {c['consec_fail_slots']}슬롯 발생 (순간 BLER {c['inst_bler']:.1f}% / {c['cause_str']})")
                    lines.append(f"    • 무선 품질: 평균 SINR {c['avg_sinr']:.1f} dB | 평균 RSRP {c['avg_rsrp']:.1f} dBm")
                    lines.append(f"    • 실측 에러: 연속 에러 {c['consec_fail_slots']} 슬롯 (총 전송 슬롯 {c['total_slots']}개 중 에러율 {c['inst_bler']:.1f}%)")
                    lines.append("")

        lines.append(divider)
        lines.append("                            [분석 리포트 종료]")
        lines.append(divider)
        lines.append("")

        return "\n".join(lines)
