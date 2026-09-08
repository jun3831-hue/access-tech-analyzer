"""
===============================================================================
Module Name   : d00_critical_faults.py
Location      : core/diagnosis_modules/d00_critical_faults.py
Domain        : DOMAIN 00 (Critical Fault Events: 3GPP RRC & NAS Standards)
===============================================================================
"""

import os
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional


class CriticalFaultsDetector:
    """
    Detects critical drop, reject, and failure events across:
    1. EN-DC Dual Connectivity Failures
    2. 5G NR RRC & 5GMM/5GSM NAS Protocol Failures (3GPP TS 38.331 & TS 24.501)
    3. 4G LTE RRC & EMM/ESM NAS Protocol Failures (3GPP TS 36.331 & TS 24.301)
    """

    def __init__(self):
        pass

    def detect_all_critical_events(
        self,
        df_mob: Optional[pd.DataFrame] = None,
        csvs: Optional[Dict[str, Optional[str]]] = None,
        all_l3: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        events = {
            'ENDC': [],
            'NR': [],
            'LTE': []
        }

        # ---------------------------------------------------------------------
        # 1. SCAN L3 & NAS PROTOCOL MESSAGES (SSOT: MessageBrowser / all_l3)
        # ---------------------------------------------------------------------
        raw_lines = []
        if all_l3 and '_raw_lines' in all_l3:
            raw_lines = all_l3['_raw_lines']
        elif csvs and csvs.get('L3_MSG') and os.path.exists(csvs['L3_MSG']):
            try:
                with open(csvs['L3_MSG'], 'r', encoding='utf-8', errors='ignore') as f:
                    raw_lines = f.readlines()
            except Exception:
                pass

        if raw_lines:
            self._scan_l3_protocol_lines(raw_lines, events, df_mob)

        # ---------------------------------------------------------------------
        # 2. SCAN HIGH-LEVEL OPTis-S4 EVENT LOGS (Supplementary: Fav_Event.csv)
        # ---------------------------------------------------------------------
        df_evt = None
        if csvs and csvs.get('EVENT') and os.path.exists(csvs['EVENT']):
            try:
                df_evt = pd.read_csv(csvs['EVENT'], encoding='utf-8', low_memory=False)
            except Exception:
                try:
                    df_evt = pd.read_csv(csvs['EVENT'], encoding='cp949', low_memory=False)
                except Exception:
                    pass

        if df_evt is not None and not df_evt.empty:
            self._scan_high_level_events(df_evt, events, df_mob)

        # Also scan EVENT_DETAIL if available
        df_ed = None
        if csvs and csvs.get('EVENT_DETAIL') and os.path.exists(csvs['EVENT_DETAIL']):
            try:
                df_ed = pd.read_csv(csvs['EVENT_DETAIL'], encoding='utf-8', low_memory=False)
            except Exception:
                try:
                    df_ed = pd.read_csv(csvs['EVENT_DETAIL'], encoding='cp949', low_memory=False)
                except Exception:
                    pass

        if df_ed is not None and not df_ed.empty:
            self._scan_high_level_events(df_ed, events, df_mob)

        # De-duplicate events by (event_id, time_stamp[:19])
        for cat in ['ENDC', 'NR', 'LTE']:
            seen = set()
            deduped = []
            for ev in events[cat]:
                key = (ev['event_id'], str(ev['time_stamp'])[:19])
                if key not in seen:
                    seen.add(key)
                    deduped.append(ev)
            events[cat] = deduped

        return events

    def _scan_l3_protocol_lines(
        self,
        raw_lines: List[str],
        events: Dict[str, List[Dict[str, Any]]],
        df_mob: Optional[pd.DataFrame]
    ):
        curr_ts = ""
        ts_pattern = re.compile(r'\[\s*(\d{4}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s*\]')
        csv_ts_pattern = re.compile(r'^\d+,(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)')

        for idx, line in enumerate(raw_lines):
            # Track Timestamp
            m_csv = csv_ts_pattern.search(line)
            if m_csv:
                curr_ts = m_csv.group(1).strip()
            else:
                m_hdr = ts_pattern.search(line)
                if m_hdr:
                    raw_ts_str = m_hdr.group(1).strip()
                    try:
                        curr_ts = pd.to_datetime(raw_ts_str).strftime('%Y-%m-%d %H:%M:%S.%f')
                    except Exception:
                        pass

            line_lower = line.lower()

            # [A] SCG Failure Information (3GPP TS 38.331 TS 36.331 - scg-FailureCause)
            if 'scgfailureinformation' in line_lower or 'scg-failurecause' in line_lower:
                scg_cause = "t310-Expiry"
                if 'randomaccessproblem' in line_lower:
                    scg_cause = "randomAccessProblem"
                elif 'rlc-maxnumretx' in line_lower:
                    scg_cause = "rlc-MaxNumRetx"
                elif 'synchreconfigfailure-scg' in line_lower:
                    scg_cause = "synchReconfigFailure-SCG"
                elif 'scg-reconfigfailure' in line_lower:
                    scg_cause = "scg-reconfigFailure"
                elif 't310-expiry' in line_lower:
                    scg_cause = "t310-Expiry"

                events['ENDC'].append(self._make_event_dict(
                    'DIAG_E_02_ENDC',
                    f'5G SCG Failure ({scg_cause})',
                    curr_ts,
                    df_mob,
                    f'5G PSCell 무선 링크 실패로 인한 SCG Failure 발생 (3GPP scg-FailureCause: {scg_cause})',
                    cause_code=scg_cause
                ))

            # [B] RRC Connection Reestablishment Request (TS 36.331 TS 38.331 - reestablishmentCause)
            if 'rrcconnectionreestablishmentrequest' in line_lower or 'rrcreestablishmentrequest' in line_lower:
                reest_cause = "otherFailure"
                if 'handoverfailure' in line_lower:
                    reest_cause = "handoverFailure"
                elif 'reconfigurationfailure' in line_lower:
                    reest_cause = "reconfigurationFailure"
                elif 'otherfailure' in line_lower:
                    reest_cause = "otherFailure"
                
                # Cache latest reestablishmentCause for subsequent reject correlation
                self._latest_reest_cause = reest_cause

            # [C] LTE RRC Reestablishment Reject
            if '__rrcconnectionreestablishmentreject' in line_lower or 'dl-ccch [lte] - rrcconnectionreestablishmentreject' in line_lower:
                reest_c = getattr(self, '_latest_reest_cause', 'otherFailure')
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_05_LTE',
                    'LTE RRC Connection Reestablishment Reject',
                    curr_ts,
                    df_mob,
                    f'무선 링크 단절 후 재수립 요청(reestablishmentCause: {reest_c})에 대해 대상 기지국이 컨텍스트 미보유로 ReestablishmentReject를 회신하여 최종 호 단절 발생',
                    missing_data='기지국 내부 거절 로그 부재로 기지국 측 컨텍스트 수신 실패 사유 특정 불가',
                    cause_code=reest_c
                ))

            # [D] NR RRC Reestablishment Reject
            elif 'dl-ccch [nr] - rrcconnectionreestablishmentreject' in line_lower or '__rrcreestablishmentreject' in line_lower:
                reest_c = getattr(self, '_latest_reest_cause', 'otherFailure')
                events['NR'].append(self._make_event_dict(
                    'DIAG_E_05_NR',
                    '5G NR RRC Reestablishment Reject',
                    curr_ts,
                    df_mob,
                    f'5G NR 무선 링크 복구 재수립 요청(reestablishmentCause: {reest_c})을 기지국이 거절하여 5G 세션 단절 발생',
                    missing_data='5G gNB 내부 로그 부재로 Reestablishment Reject 세부 원인 특정 불가',
                    cause_code=reest_c
                ))

            # [E] LTE RRC Connection Reject
            elif '__rrcconnectionreject' in line_lower or 'dl-ccch [lte] - rrcconnectionreject' in line_lower:
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_04_LTE',
                    'LTE RRC Connection Reject',
                    curr_ts,
                    df_mob,
                    '단말의 초기 망 접속 RRC 연결 요청에 대해 기지국이 용량 초과 또는 C-Plane 혼잡으로 인해 RRCConnectionReject 회신',
                    missing_data='기지국 대기 타이머(waitTime) 및 혼잡 레벨 데이터 부재로 기지국 부하 상태 특정 불가'
                ))

            # [F] NR RRC Reject
            elif 'dl-ccch [nr] - rrcconnectionreject' in line_lower or '__rrcreject' in line_lower:
                events['NR'].append(self._make_event_dict(
                    'DIAG_E_04_NR',
                    '5G NR RRC Reject',
                    curr_ts,
                    df_mob,
                    '5G 기지국 용량 초과 또는 제어채널 혼잡으로 인한 RRC 연결 수립 거절',
                    missing_data='gNB 혼잡 상태 데이터 부재로 거절 상세 원인 특정 불가'
                ))

            # [G] RLF Report (T310-Expiry, RandomAccess, MaxReTx)
            elif 'rlf_cause_r11 = t310-expiry' in line_lower or 'rlf-cause = t310-expiry' in line_lower or 'connectionfailuretype_r10 = rlf' in line_lower:
                rlf_cause = "t310-Expiry"
                if 'randomaccessproblem' in line_lower:
                    rlf_cause = "randomAccessProblem"
                elif 'rlc-maxnumretx' in line_lower:
                    rlf_cause = "rlc-MaxNumRetx"
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_01_LTE',
                    f'LTE Radio Link Failure ({rlf_cause})',
                    curr_ts,
                    df_mob,
                    f'서빙 기지국과의 물리계층 동기 상실 또는 RLF({rlf_cause})로 인한 무선 링크 단절 발생',
                    missing_data='L1 물리계층 Out-of-Sync 카운터 데이터 부재로 정확한 물리계층 동기 상실 시점 특정 불가',
                    cause_code=rlf_cause
                ))

            # [H] LTE EMM Attach Reject
            elif 'attach reject' in line_lower or '__attach reject' in line_lower:
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_06_LTE',
                    'LTE EMM Attach Reject',
                    curr_ts,
                    df_mob,
                    '단말의 초기 코어망 접속(Attach) 요청에 대해 MME가 가입자 인증 실패 또는 망 접속 정책에 의해 Attach Reject 회신',
                    missing_data='EMM Cause 원인 코드가 L3 메시지에 누락된 경우 MME 거절 사유 특정 불가'
                ))

            # [I] LTE EMM Service Reject
            elif 'service reject' in line_lower or '__service reject' in line_lower:
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_07_LTE',
                    'LTE EMM Service Reject',
                    curr_ts,
                    df_mob,
                    '유휴(Idle) 상태에서 데이터 송수신을 위한 단말의 Service Request를 코어망(MME)이 거절함',
                    missing_data='MME Service Reject 세부 Cause 코드 부재 시 코어망 혼잡 원인 특정 불가'
                ))

            # [H] LTE EMM Tracking Area Update Reject
            elif 'tracking area update reject' in line_lower or 'tau reject' in line_lower:
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_08_LTE',
                    'LTE EMM Tracking Area Update Reject',
                    curr_ts,
                    df_mob,
                    '단말의 위치등록(TAU) 요청을 MME가 거절하여 단말이 망 재접속(Re-attach) 절차로 전락함',
                    missing_data='TAU Reject 원인 코드(EMM Cause #7, #9, #10 등) 부재 시 거절 사유 특정 불가'
                ))

            # [I] LTE ESM PDN Connectivity Reject
            elif 'pdn connectivity reject' in line_lower:
                events['LTE'].append(self._make_event_dict(
                    'DIAG_E_09_LTE',
                    'LTE ESM PDN Connectivity Reject',
                    curr_ts,
                    df_mob,
                    '데이터 베어러(PDN) 생성을 위한 요청을 코어망(PGW/SGW)이 거절하여 데이터 세션 수립 실패',
                    missing_data='ESM Cause 코드 부재 시 APN 설정 오류인지 망 자원 부족인지 특정 불가'
                ))

            # [J] 5GMM Registration Reject
            elif 'registration reject' in line_lower or '__registration reject' in line_lower:
                events['NR'].append(self._make_event_dict(
                    'DIAG_E_06_NR',
                    '5GMM Registration Reject',
                    curr_ts,
                    df_mob,
                    '5G 코어망(AMF)에서 단말의 망 등록(Registration) 요청을 거절함',
                    missing_data='5GMM Cause 부재 시 가입자 권한 오류 여부 특정 불가'
                ))

            # [K] 5GSM PDU Session Establishment Reject
            elif 'pdu session establishment reject' in line_lower:
                events['NR'].append(self._make_event_dict(
                    'DIAG_E_07_NR',
                    '5GSM PDU Session Establishment Reject',
                    curr_ts,
                    df_mob,
                    '5G 코어망(SMF/UPF)에서 데이터 PDU 세션 수립 요청을 거절함',
                    missing_data='5GSM Cause 부재 시 DNN/NSSAI 파라미터 불일치 특정 불가'
                ))

            # [L] 5GMM Service Reject
            elif '5gmm service reject' in line_lower:
                events['NR'].append(self._make_event_dict(
                    'DIAG_E_08_NR',
                    '5GMM Service Reject',
                    curr_ts,
                    df_mob,
                    '5G 유휴(Idle) 상태에서 데이터 송수신을 위한 Service Request를 망에서 거절함',
                    missing_data='AMF Service Reject 원인 부재로 코어망 부하 특정 불가'
                ))

    # Declarative 3GPP Standard Critical Fault Specs (SSOT: 00_critical_faults.yaml)
    # Strictly excludes transient debug flags like 'Received RAR[False]'
    CRITICAL_EVENT_SPECS = [
        (['SCG Change Failure'], 'ENDC', 'DIAG_E_01_ENDC', 'SCG Change Failure', 'LTE 앵커 기지국과의 타이밍 불일치 또는 5G 타겟 셀 RACH 응답 시간 초과로 인한 SCG 변경 실패', 'RACH 프리앰블 검출 여부 데이터 부재'),
        (['SCG Radio Link Failure', 'SCG RLF'], 'ENDC', 'DIAG_E_02_ENDC', 'SCG Radio Link Failure', '5G PSCell 무선 링크 품질 저하로 인한 SCG Radio Link Failure 발생', '5G L1 Out-of-Sync 카운터 데이터 부재'),
        (['SCG Reconfiguration Failure'], 'ENDC', 'DIAG_E_03_ENDC', 'SCG Reconfiguration Failure', '5G Secondary Cell Group 재구성 메시지 파라미터 불일치로 인한 설정 거절', 'RRCReconfiguration 파라미터 상세 로그 부재'),
        (['NR RLF', '5G RLF'], 'NR', 'DIAG_E_01_NR', '5G NR Radio Link Failure', '5G PSCell 전파 음영 및 T310 타이머 만료로 인한 5G RLF 발생', '5G Out-of-Sync 카운터 부재'),
        (['NR HO Failure', '5G Handover Failure'], 'NR', 'DIAG_E_02_NR', '5G NR Handover Failure', '5G 타겟 셀 RACH 프리앰블 전송 실패 또는 T304 핸드오버 타이머 만료', '타겟 셀 RACH 수신 로그 부재'),
        (['NR Call Drop', '5G Call Drop'], 'NR', 'DIAG_E_03_NR', '5G NR Call Drop', '호 진행 중 5G 세션 비정상 단절 발생', 'Release Cause 코드 부재'),
        (['e-RAB Drop'], 'LTE', 'DIAG_E_03_LTE', '4G LTE e-RAB 호 단절 (e-RAB Drop)', '4G LTE 무선 링크 열화로 인한 전송 베어러 비정상 해제 및 호 단절', 'e-RAB Release Cause 코드 부재'),
        (['RLF(RACH Problem)', 'RACH Problem'], 'LTE', 'DIAG_E_01_LTE', 'LTE 상향 RACH 실패 RLF', 'Random Access Preamble 최대 전송 횟수(preambleTransMax) 도달 후 기지국 무응답으로 인한 상향 RACH Problem RLF 발생', 'L1 Out-of-Sync 카운터 부재'),
        (['LTE Handover Failure', 'LTE HO Fail'], 'LTE', 'DIAG_E_02_LTE', '4G LTE Handover Failure', '4G LTE 타겟 기지국 RACH 실패 및 T304 핸드오버 타이머 만료', '타겟 셀 RACH 응답 로그 부재'),
        (['Call Drop', 'LTE Drop'], 'LTE', 'DIAG_E_03_LTE', '4G LTE Call Drop', '호 진행 중 4G LTE 앵커/데이터 세션 비정상 단절 발생', 'Release Cause 코드 부재'),
    ]

    def _scan_high_level_events(
        self,
        df_evt: pd.DataFrame,
        events: Dict[str, List[Dict[str, Any]]],
        df_mob: Optional[pd.DataFrame]
    ):
        # Identify detail code column from Event_(Detail).csv
        detail_col = next((c for c in df_evt.columns if 'DETAIL CODE1' in str(c).upper() or 'EVENT DETAIL' in str(c).upper()), None)

        for idx, r in df_evt.iterrows():
            ts = str(r.get('TIME_STAMP', ''))
            row_str = " ".join([str(val) for val in r.values if pd.notna(val) and str(val) != 'nan'])

            # Extract 3GPP Failure Cause from Event Detail Code1
            det_val = str(r[detail_col]) if detail_col and pd.notna(r[detail_col]) else ""
            detected_cause = ""
            if 'RACH Problem' in det_val or 'RACH' in row_str:
                detected_cause = "randomAccessProblem"
            elif 'T310 Expiry' in det_val or 'T310' in row_str:
                detected_cause = "t310-Expiry"
            elif 'Max Retx' in det_val or 'MaxRetx' in row_str:
                detected_cause = "rlc-MaxNumRetx"
            elif 'T304 Expiry' in det_val or 'T304' in row_str:
                detected_cause = "handoverFailure"

            for keywords, rat, eid, name, cause, missing in self.CRITICAL_EVENT_SPECS:
                if any(kw in row_str for kw in keywords):
                    events[rat].append(self._make_event_dict(
                        eid, name, ts, df_mob, cause, missing,
                        cause_code=detected_cause
                    ))
                    break

    def _make_event_dict(
        self,
        event_id: str,
        name: str,
        time_stamp: str,
        df_mob: Optional[pd.DataFrame],
        root_cause: str,
        missing_data: str = "",
        cause_code: str = ""
    ) -> Dict[str, Any]:
        info = {
            'event_id': event_id,
            'diag_code': event_id,
            'name': name,
            'title': name,
            'severity': 'HIGH',
            'grade': 'HIGH',
            'time_stamp': time_stamp,
            't_start': time_stamp,
            't_end': time_stamp,
            'domain': '00_CRITICAL_FAULTS',
            'root_cause': root_cause,
            'cause_code': cause_code,
            'standard_cause': cause_code,
            'missing_data': missing_data,
            'lte_pci': None,
            'lte_arfcn': None,
            'nr_pci': None,
            'nr_arfcn': None,
            'rsrp': None,
            'sinr': None,
            'radio_context': '',
            'causal_fragment': {
                'link_failure': f'하향 동기 상실(T310 만료) 또는 RLF({cause_code or "3GPP 표준"})로 인한 무선 링크 단절',
                'recovery_failure': 'RRC Connection Reestablishment Request 중 기지국 거절(Reject)로 링크 복구 실패',
                'bearer_release': '무선 링크 단절로 인한 호 단절(Call Drop / e-RAB Drop)',
                'rach_failure': '상향 랜덤 액세스 프리앰블 전송 한계 도달 및 무응답(RACH Problem RLF)'
            }
        }

        if df_mob is not None and not df_mob.empty and time_stamp:
            df_target = df_mob[df_mob['TIME_STAMP'] <= time_stamp]
            if not df_target.empty:
                last_row = df_target.iloc[-1]
                info['lte_pci'] = last_row.get('LTE_Serving_PCI')
                info['lte_arfcn'] = last_row.get('LTE_Serving_ARFCN')
                info['nr_pci'] = last_row.get('NR_Serving_PCI')
                info['nr_arfcn'] = last_row.get('NR_Serving_ARFCN')
                info['rsrp'] = last_row.get('Serving_RSRP')
                info['sinr'] = last_row.get('Serving_SINR')

                parts = []
                if pd.notna(info['lte_pci']):
                    p_str = f"서빙 LTE PCI {int(info['lte_pci'])}"
                    sub_parts = []
                    if pd.notna(info['rsrp']):
                        sub_parts.append(f"RSRP: {info['rsrp']:.1f} dBm")
                    if pd.notna(info['lte_arfcn']):
                        sub_parts.append(f"EARFCN {int(info['lte_arfcn'])}")
                    if sub_parts:
                        p_str += f" ({', '.join(sub_parts)})"
                    parts.append(p_str)

                if pd.notna(info['nr_pci']):
                    nr_str = f"NR PCI {int(info['nr_pci'])}"
                    if pd.notna(info['nr_arfcn']):
                        nr_str += f" (ARFCN {int(info['nr_arfcn'])})"
                    parts.append(nr_str)

                if parts:
                    info['radio_context'] = " / ".join(parts)

        return info
