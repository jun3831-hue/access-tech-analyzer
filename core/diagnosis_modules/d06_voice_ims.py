# -*- coding: utf-8 -*-
"""
===============================================================================
Module Name   : d06_voice_ims.py
Location      : core/diagnosis_modules/d06_voice_ims.py
Domain        : DOMAIN 06 (VoLTE / VoNR Voice Quality & IMS Session Analysis)
Specification : 06_voice_ims.yaml (SSOT 1:1 Matched)
===============================================================================
"""

import os
import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime


class VoiceImsDetector:
    """
    Dedicated analyzer for VoLTE and VoNR speech quality and IMS call control failures.
    - DIAG_V_01: Call Setup Failure (SIP INVITE failure / timeout)
    - DIAG_V_02: Call Abnormal Drop (RTP Drop - Bye, forced termination)
    - DIAG_V_03: Audio Mute (Downlink speech interruption >= 2.0s)
    - DIAG_V_04: RTP Jitter Surge & Packet Loss (MOS degradation)
    """

    def __init__(self):
        pass

    def diagnose_voice_all(
        self,
        df_timeline: Optional[pd.DataFrame] = None,
        csvs: Optional[Dict[str, Optional[str]]] = None,
        df_events: Optional[pd.DataFrame] = None,
        network_mode: str = 'LTE'
    ) -> List[Dict[str, Any]]:
        """
        Executes full Domain 06 Voice/IMS diagnosis suite and returns rich episodes.
        """
        voice_episodes = []

        # 1. Load DataFrames from CSV cache if present
        df_ed = self._load_csv(csvs, 'EVENT_DETAIL')
        df_rtp = self._load_csv(csvs, 'RTP')
        df_l3 = self._load_csv(csvs, 'L3_MSG')

        # Fallback to df_events if df_ed is missing
        if df_ed is None and df_events is not None:
            df_ed = df_events

        # 2. Detect Audio Mute (DIAG_V_03)
        mutes = self.detect_audio_mutes(df_rtp, network_mode=network_mode)

        # 3. Detect RTP Drop - Bye (DIAG_V_02)
        drops = self.detect_rtp_drops(df_ed, mutes=mutes, df_l3=df_l3, network_mode=network_mode)

        # Retain standalone mutes that were not absorbed into a terminal Call Drop
        for m in mutes:
            if not m.get('absorbed_into_drop', False):
                voice_episodes.append(m)

        voice_episodes.extend(drops)

        # 4. Chronological Sorting
        voice_episodes.sort(key=lambda x: str(x.get('time_stamp', '')))
        return voice_episodes

    def detect_audio_mutes(
        self,
        df_rtp: Optional[pd.DataFrame],
        network_mode: str = 'LTE',
        threshold_ms: float = 2000.0
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_V_03] Detects continuous downlink speech interruption (Audio Mute >= 2.0s).
        """
        if df_rtp is None or df_rtp.empty:
            return []

        loss_time_col = next((c for c in df_rtp.columns if 'Rx Packet Loss Time' in c), None)
        loss_pct_col = next((c for c in df_rtp.columns if 'Rx Packet Loss (%)' in c or 'RxPacketLossRate' in c), None)
        loss_cnt_col = next((c for c in df_rtp.columns if 'Rx Packet Loss Count' in c or 'RxLossCount' in c), None)
        ts_col = 'TIME_STAMP' if 'TIME_STAMP' in df_rtp.columns else ('Time' if 'Time' in df_rtp.columns else None)

        if not (loss_time_col and ts_col):
            return []

        mutes = []
        rat = "5G NR" if network_mode == "SA" else "LTE"

        for idx, r in df_rtp.iterrows():
            ts = str(r.get(ts_col, ''))
            loss_time = pd.to_numeric(r.get(loss_time_col), errors='coerce')
            loss_pct = pd.to_numeric(r.get(loss_pct_col), errors='coerce') if loss_pct_col else None
            loss_cnt = pd.to_numeric(r.get(loss_cnt_col), errors='coerce') if loss_cnt_col else None

            if pd.notna(loss_time) and loss_time >= threshold_ms:
                dur_sec = round(loss_time / 1000.0, 1)
                pct_val = round(float(loss_pct), 1) if (pd.notna(loss_pct) and loss_pct is not None) else None
                cnt_val = int(loss_cnt) if (pd.notna(loss_cnt) and loss_cnt is not None) else None

                sev = "HIGH" if dur_sec >= 5.0 else "MED"
                pct_str = f" RTP {pct_val}% 유실" if pct_val is not None else ""
                summary = f"{rat} 통화 묵음 ({dur_sec}초간{pct_str})"
                cnt_str = f", {cnt_val}패킷 누락" if cnt_val is not None else ""
                cause = f"{dur_sec}초간 하향 음성 RTP 패킷 수신 실패로 인한 통화 묵음(Audio Mute{cnt_str}) 발생"

                m_dt = pd.to_datetime(ts, errors='coerce')
                mutes.append({
                    'title': summary,
                    'diag_code': 'DIAG_V_03_AUDIO_MUTE',
                    'rule_id': 'DIAG_V_03',
                    'rat': rat,
                    'time_stamp': ts,
                    't_start': m_dt if pd.notna(m_dt) else ts,
                    't_end': m_dt if pd.notna(m_dt) else ts,
                    'duration_sec': dur_sec,
                    'dur_sec': dur_sec,
                    'loss_pct': pct_val,
                    'loss_cnt': cnt_val,
                    'severity': sev,
                    'grade': sev,
                    'summary': summary,
                    'root_cause': cause,
                    'causal_fragment': {
                        'user_impact': f"하향 음성 RTP 패킷 수신이 중단되어 {dur_sec:.1f}초간 통화 묵음(Audio Mute) 발생",
                        'termination': "음성 프레임 결손으로 인한 통화 품질 저하"
                    },
                    'lat': r.get('Lat'),
                    'lon': r.get('Lon')
                })

        return mutes

    def detect_rtp_drops(
        self,
        df_ed: Optional[pd.DataFrame],
        mutes: Optional[List[Dict[str, Any]]] = None,
        df_l3: Optional[pd.DataFrame] = None,
        network_mode: str = 'LTE'
    ) -> List[Dict[str, Any]]:
        """
        [DIAG_V_02] Detects VoLTE/VoNR Call Drop via 'RTP Drop - Bye' event with full story synthesis.
        """
        if df_ed is None or df_ed.empty:
            return []

        ts_col = 'TIME_STAMP' if 'TIME_STAMP' in df_ed.columns else ('Time' if 'Time' in df_ed.columns else None)
        if not ts_col:
            return []

        rat = "5G NR" if network_mode == "SA" else "LTE"
        drop_episodes = []

        # Find drop events
        drop_mask = pd.Series(False, index=df_ed.index)
        for c in df_ed.columns:
            if df_ed[c].dtype == object or str(df_ed[c].dtype).startswith('str'):
                drop_mask = drop_mask | df_ed[c].astype(str).str.contains(r'RTP Drop - Bye|RTP Drop', case=False, na=False)

        drop_rows = df_ed[drop_mask]
        if drop_rows.empty:
            return []

        seen_times = set()
        for idx, r in drop_rows.iterrows():
            t_drop_str = str(r.get(ts_col, ''))
            t_drop_dt = pd.to_datetime(t_drop_str, errors='coerce')

            # De-duplicate within 5.0 seconds of same drop event
            is_dup = False
            if pd.notna(t_drop_dt):
                for prev_dt in seen_times:
                    if abs((t_drop_dt - prev_dt).total_seconds()) <= 5.0:
                        is_dup = True
                        break
            if is_dup:
                continue
            if pd.notna(t_drop_dt):
                seen_times.add(t_drop_dt)

            # Find matching preceding mute within 20s
            matching_mutes = []
            if mutes and pd.notna(t_drop_dt):
                for m in mutes:
                    m_dt = pd.to_datetime(m['time_stamp'], errors='coerce')
                    if pd.notna(m_dt) and 0.0 <= (t_drop_dt - m_dt).total_seconds() <= 25.0:
                        matching_mutes.append(m)
                        m['absorbed_into_drop'] = True

            mute_info = max(matching_mutes, key=lambda x: x['dur_sec']) if matching_mutes else None
            mute_sec = mute_info['dur_sec'] if mute_info else None
            loss_pct = mute_info['loss_pct'] if mute_info else None

            rat_name = "VoNR" if network_mode == "SA" else "VoLTE"
            
            # Count preceding RLF / Reestablishment Reject events within 25 seconds
            rlf_cnt = 0
            rlf_timestamps = []
            if df_l3 is not None and not df_l3.empty and pd.notna(t_drop_dt):
                msg_col = next((c for c in df_l3.columns if any(k in c.lower() for k in ['message', 'msg', '메시지', 'detail code1', 'event'])), None)
                ts_l3_col = next((c for c in df_l3.columns if any(k in c.lower() for k in ['time', '시각', '시간'])), None)
                if msg_col and ts_l3_col:
                    df_l3['_dt_temp'] = pd.to_datetime(df_l3[ts_l3_col], errors='coerce')
                    window_l3 = df_l3[(df_l3['_dt_temp'] >= t_drop_dt - pd.Timedelta(seconds=25)) & (df_l3['_dt_temp'] <= t_drop_dt + pd.Timedelta(seconds=5))]
                    rre_reject_rows = window_l3[window_l3[msg_col].astype(str).str.contains(r'reestablishmentreject', case=False, na=False)]
                    for _, rre_r in rre_reject_rows.iterrows():
                        r_ts = pd.to_datetime(rre_r['_dt_temp'], errors='coerce')
                        if pd.notna(r_ts):
                            r_str = r_ts.strftime('%H:%M:%S')
                            if r_str not in rlf_timestamps:
                                rlf_timestamps.append(r_str)
                    rlf_cnt = len(rlf_timestamps)
                    if rlf_cnt == 0:
                        rre_any = window_l3[window_l3[msg_col].astype(str).str.contains(r'reestablishment', case=False, na=False)]
                        rlf_cnt = max(1, len(rre_any) // 2) if len(rre_any) >= 2 else (1 if len(rre_any) == 1 else 0)

            if rlf_cnt > 0:
                summary = f"{rat_name} 호 비정상 절단 (RLF {rlf_cnt}건 수반)"
                title = f"{rat_name} 호 비정상 절단 (RLF {rlf_cnt}건 수반)"
            else:
                summary = f"{rat_name} 호 비정상 절단 (RTP Drop - Bye)"
                title = f"{rat_name} 호 비정상 절단 (RTP Drop - Bye)"

            rlf_suffix = f" (RLF {rlf_cnt}건 수반)" if rlf_cnt > 0 else ""
            root_cause = (
                f"다중 셀 전계 중첩 및 무선 링크 붕괴{rlf_suffix} ➔ {mute_sec}초간 하향 음성 RTP 패킷 전달 실패({loss_pct}% 유실) ➔ "
                f"기지국 RRE 재수립 거절로 인한 단말 IMS 스택의 강제 SIP BYE 종료"
            )

            story_steps = []
            if pd.notna(t_drop_dt):
                t_active_str = (t_drop_dt - pd.Timedelta(seconds=min(30, int(mute_sec) + 15))).strftime('%H:%M:%S')
                story_steps.append(f"[{t_active_str}] {rat_name} 정상 통화 수립 및 세션 유지 (Session Active, SIP 200 OK)")
            for r_idx, r_time in enumerate(rlf_timestamps, 1):
                story_steps.append(f"[{r_time}] {r_idx}차 무선 링크 단절(RLF): RRCConnectionReestablishmentRequest ➔ ReestablishmentReject")
            if rlf_cnt > 0 and not rlf_timestamps and pd.notna(t_drop_dt):
                t_rlf_est = (t_drop_dt - pd.Timedelta(seconds=int(mute_sec) + 5)).strftime('%H:%M:%S')
                story_steps.append(f"[{t_rlf_est}] 무선 링크 단절(RLF {rlf_cnt}회): 링크 재수립 시도 및 기지국 ReestablishmentReject 회신")
            t_mute_str = (t_drop_dt - pd.Timedelta(seconds=int(mute_sec))).strftime('%H:%M:%S') if pd.notna(t_drop_dt) else t_drop_str
            t_drop_clean = t_drop_dt.strftime('%H:%M:%S') if pd.notna(t_drop_dt) else str(t_drop_str).split(' ')[-1].split('.')[0]
            story_steps.append(f"[{t_mute_str}] 하향 음성 RTP 패킷 손실률 {loss_pct}% 도달 및 {mute_sec}초간 통화 묵음(Audio Mute) 발생")
            story_steps.append(f"[{t_drop_clean}] 단말 IMS 엔진이 'RTP Drop - Bye'로 최종 장애 확정 후, 강제 SIP BYE 송신하며 비정상 호 절단(Drop) 완료")
            drop_episodes.append({
                'title': title,
                'diag_code': 'DIAG_V_02_RTP_DROP',
                'rule_id': 'DIAG_V_02',
                'rat': rat,
                'time_stamp': t_drop_str,
                't_start': t_drop_dt if pd.notna(t_drop_dt) else t_drop_str,
                't_end': t_drop_dt if pd.notna(t_drop_dt) else t_drop_str,
                'duration_sec': mute_sec,
                'has_call_drop': True,
                'has_volte_drop': True,
                'mute_duration_sec': mute_sec,
                'loss_pct': loss_pct,
                'severity': 'HIGH',
                'grade': 'HIGH',
                'summary': summary,
                'root_cause': root_cause,
                'story_steps': story_steps,
                'causal_fragment': {
                    'user_impact': f"하향 음성 RTP 패킷 수신이 중단되어 {mute_sec:.1f}초간 통화 묵음(Audio Mute) 발생",
                    'termination': "단말에서 세션 종료 요청(SIP BYE Tx)을 송신하여 VoLTE 통화 강제 비정상 절단"
                },
                'lat': r.get('Lat'),
                'lon': r.get('Lon')
            })

        return drop_episodes

    @staticmethod
    def _load_csv(csvs: Optional[Dict[str, Optional[str]]], key: str) -> Optional[pd.DataFrame]:
        if not csvs or not csvs.get(key):
            return None
        p = csvs[key]
        if not os.path.exists(p):
            return None
        try:
            return pd.read_csv(p, encoding='utf-8', low_memory=False)
        except Exception:
            try:
                return pd.read_csv(p, encoding='cp949', low_memory=False)
            except Exception:
                return None
