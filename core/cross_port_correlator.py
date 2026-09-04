"""
===============================================================================
Module Name   : cross_port_correlator.py
Location      : core/cross_port_correlator.py
Role          : Multi-Port / Multi-UE Spatio-Temporal Incident Correlator
                Synthesizes isolated per-port episodes into unified cross-port
                area outage incidents (e.g. M1 DL + M4 VoLTE simultaneous drops).
===============================================================================
"""

import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np


class CrossPortIncidentCorrelator:
    """
    Correlates episodes across multiple ports (M1, M2, M3, M4)
    using spatio-temporal proximity and shared cell context.
    """

    def __init__(self, time_window_sec: float = 15.0, distance_threshold_m: float = 400.0):
        self.time_window_sec = time_window_sec
        self.distance_threshold_m = distance_threshold_m

    def correlate_ports(
        self,
        port_episodes_dict: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Takes a dict of { 'M1': [episodes], 'M2': [episodes], ... }
        and returns a unified, synthesized cross-port episode list.
        """
        if not port_episodes_dict:
            return []

        # 1. Flatten and tag all episodes with their source port
        all_episodes = []
        for port_key, ep_list in port_episodes_dict.items():
            for ep in ep_list:
                ep_copy = dict(ep)
                ep_copy['source_port'] = port_key
                if 'involved_ports' not in ep_copy:
                    ep_copy['involved_ports'] = [port_key]
                all_episodes.append(ep_copy)

        if not all_episodes:
            return []

        # Sort chronologically by t_start
        all_episodes.sort(key=lambda x: x['t_start'])

        # 2. Cluster across ports
        clusters: List[List[Dict[str, Any]]] = []
        curr_cluster: List[Dict[str, Any]] = []

        for ep in all_episodes:
            if not curr_cluster:
                curr_cluster.append(ep)
                continue

            # Check if ep can merge into curr_cluster
            can_merge = False
            cluster_t_start = min(e['t_start'] for e in curr_cluster)
            cluster_t_end = max(e['t_end'] for e in curr_cluster)
            curr_start = ep['t_start']

            time_gap = (curr_start - cluster_t_end).total_seconds()
            overlap_gap = max(0.0, (curr_start - cluster_t_start).total_seconds())

            # Check cell overlap
            cluster_pcis = set()
            for e in curr_cluster:
                if e.get('srv_pci') is not None:
                    cluster_pcis.add(e['srv_pci'])
                if e.get('tgt_pci') is not None:
                    cluster_pcis.add(e['tgt_pci'])

            ep_pcis = set()
            if ep.get('srv_pci') is not None:
                ep_pcis.add(ep['srv_pci'])
            if ep.get('tgt_pci') is not None:
                ep_pcis.add(ep['tgt_pci'])

            has_shared_cell = bool(cluster_pcis.intersection(ep_pcis))

            # Both are Critical Link Failures / Drop / RLF within time window
            curr_is_crit = (ep.get('severity') == 'HIGH' or ep.get('grade') == 'HIGH' or ep.get('has_call_drop'))
            cluster_is_crit = any(e.get('severity') == 'HIGH' or e.get('grade') == 'HIGH' or e.get('has_call_drop') for e in curr_cluster)

            # Check VoLTE Pair (M3 Caller + M4 Callee)
            cluster_ports = set(e['source_port'] for e in curr_cluster)
            curr_port = ep['source_port']
            is_voice_pair = ({'M3', 'M4'}.issubset(cluster_ports | {curr_port}))
            voice_pair_merge = is_voice_pair and (time_gap <= 25.0)

            if time_gap <= self.time_window_sec:
                if has_shared_cell or (curr_is_crit and cluster_is_crit) or voice_pair_merge:
                    can_merge = True
                elif time_gap <= 3.0:  # Direct temporal coincidence
                    can_merge = True
            elif voice_pair_merge:
                can_merge = True

            if can_merge:
                curr_cluster.append(ep)
            else:
                clusters.append(curr_cluster)
                curr_cluster = [ep]

        if curr_cluster:
            clusters.append(curr_cluster)

        # 3. Synthesize each cluster into unified master episode
        unified_episodes = []
        for cl in clusters:
            unified_episodes.append(self._synthesize_cross_port_cluster(cl))

        unified_episodes.sort(key=lambda x: x['t_start'])
        return unified_episodes

    def _synthesize_cross_port_cluster(self, cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synthesizes a multi-port cluster into an executive-ready multi-UE outage incident.
        """
        if len(cluster) == 1:
            base = dict(cluster[0])
            base['involved_ports'] = [cluster[0]['source_port']]
            base['is_multi_ue'] = False
            return base

        # Multi-UE Event!
        ports = sorted(list(set(e['source_port'] for e in cluster)))
        is_multi_ue = len(ports) > 1

        t_start = min(e['t_start'] for e in cluster)
        t_end = max(e['t_end'] for e in cluster)
        duration_sec = max(1.0, (t_end - t_start).total_seconds())

        # Combine events & story steps
        all_events = []
        all_story_steps = []
        for e in cluster:
            src_p = e['source_port']
            for ev in e.get('events', []):
                ev_copy = dict(ev)
                ev_copy['source_port'] = src_p
                all_events.append(ev_copy)
            for st in e.get('story_steps', []):
                all_story_steps.append(f"[{src_p}] {st}")

        all_events.sort(key=lambda x: x['timestamp'])

        # Aggregate severity
        has_high = any(e.get('severity') == 'HIGH' or e.get('grade') == 'HIGH' for e in cluster)
        has_med = any(e.get('severity') == 'MED' or e.get('grade') == 'MED' for e in cluster)
        composite_grade = 'HIGH' if has_high else ('MED' if has_med else 'LOW')

        # Primary cell context
        srv_pci = next((e['srv_pci'] for e in cluster if e.get('srv_pci') is not None), None)
        tgt_pci = next((e['tgt_pci'] for e in cluster if e.get('tgt_pci') is not None), None)
        srv_rat = next((e['srv_rat'] for e in cluster if e.get('srv_rat')), 'LTE')
        rat_prefix = f"[{srv_rat}] "

        port_tag = "+".join(ports)
        ue_count = len(ports)

        # Count call drops
        drop_ports = []
        for e in cluster:
            if e.get('has_call_drop') or any('Drop' in ev['name'] or 'RLF' in ev['name'] or 'Reject' in ev['name'] for ev in e.get('events', [])):
                if e['source_port'] not in drop_ports:
                    drop_ports.append(e['source_port'])

        # Synthesize Title strictly based on real drop presence
        tgt_label = f"PCI {tgt_pci}" if tgt_pci is not None else ""
        has_unhandled = any(e.get('has_unhandled_ho') for e in cluster)
        max_rep_cnt = max([e.get('rep_cnt') or 0 for e in cluster] + [0])
        has_actual_drop = len(drop_ports) > 0 or any(e.get('has_call_drop') for e in cluster)

        if len(drop_ports) >= 2 or (has_actual_drop and is_multi_ue):
            drop_tag = "+".join(drop_ports) if drop_ports else port_tag
            if has_unhandled and tgt_label:
                rep_str = f" (A3 MR {max_rep_cnt}회 방치)" if max_rep_cnt else ""
                title = f"{rat_prefix}[다중 단말({drop_tag}) 동시 호 단절] 타겟({tgt_label}) HO 방치 후 전멸{rep_str}"
                cause = f"동일 지점 기지국의 타겟 셀({tgt_label}) 핸드오버 미발행(A3 방치)으로 인해 {drop_tag} 다중 단말이 {duration_sec:.1f}초 이내에 연속 무선 링크 붕괴(RLF) 및 통화 절단을 겪음 (기지국 파라미터/이웃 누락 결함)"
            else:
                title = f"{rat_prefix}[다중 단말({drop_tag}) 동시 호 단절] 기지국 무선 링크 붕괴 및 호 단절"
                cause = f"동일 기지국 커버리지 내에서 {drop_tag} 복수 단말이 동시 다발적으로 무선 링크 단절(RLF) 및 RRE 거절 호 단절 발발 (기지국 제어/무선 환경 급격 붕괴)"
        elif is_multi_ue:
            if has_unhandled and tgt_label:
                rep_str = f" (A3 MR {max_rep_cnt}회)" if max_rep_cnt else ""
                title = f"{rat_prefix}[다중 단말({port_tag})] 타겟({tgt_label}) HO 요청 무응답{rep_str}"
                cause = f"{port_tag} 복수 단말이 동일 타겟 셀({tgt_label})에 핸드오버를 요청했으나 기지국 무응답으로 지연됨 (호 정상 유지)"
            elif any(e.get('has_ping_pong') for e in cluster):
                pci_chain_str = next((e.get('pci_chain') for e in cluster if e.get('pci_chain')), '')
                title = f"{rat_prefix}[다중 단말({port_tag})] 핑퐁 핸드오버 ({pci_chain_str})"
                cause = f"{port_tag} 복수 단말이 동일 셀 간 전계 중첩으로 핑퐁 핸드오버를 겪음"
            else:
                clean_first = re.sub(r'\[.*?\]', '', cluster[0]['title']).strip()
                title = f"{rat_prefix}[다중 단말({port_tag})] {clean_first}"
                cause = f"{port_tag} 복수 단말이 동일 시공간 영역에서 상호 연계된 무선 품질 저하를 겪음\n• " + "\n• ".join([f"{e['source_port']}: {e.get('cause_conclusion', '')}" for e in cluster])
        else:
            title = cluster[0]['title']
            cause = cluster[0].get('cause_conclusion', '')

        # Select Representative Trigger Coordinates
        lat = cluster[0].get('lat')
        lon = cluster[0].get('lon')

        return {
            't_start': t_start,
            't_end': t_end,
            'duration_sec': duration_sec,
            'title': title,
            'srv_rat': srv_rat,
            'tgt_rat': cluster[0].get('tgt_rat'),
            'srv_pci': srv_pci,
            'srv_arfcn': cluster[0].get('srv_arfcn'),
            'srv_rsrp': cluster[0].get('srv_rsrp'),
            'srv_sinr': cluster[0].get('srv_sinr'),
            'speed_kmh': cluster[0].get('speed_kmh'),
            'tgt_pci': tgt_pci,
            'tgt_arfcn': cluster[0].get('tgt_arfcn'),
            'tgt_rsrp': cluster[0].get('tgt_rsrp'),
            'delta_rsrp': cluster[0].get('delta_rsrp'),
            'story_steps': all_story_steps,
            'cause_conclusion': cause,
            'total_events': len(all_events),
            'events': all_events,
            'pci_chain': cluster[0].get('pci_chain'),
            'rep_cnt': max_rep_cnt if max_rep_cnt else None,
            'has_call_drop': has_actual_drop,
            'has_unhandled_ho': has_unhandled,
            'has_ping_pong': any(e.get('has_ping_pong') for e in cluster),
            'has_rach_problem': any(e.get('has_rach_problem') for e in cluster),
            'grade': composite_grade,
            'severity': composite_grade,
            'involved_ports': ports,
            'is_multi_ue': is_multi_ue,
            'lat': lat,
            'lon': lon,
            'cluster_episodes': cluster
        }

    def decorate_port_episodes(
        self,
        group_port_dict: Dict[str, Dict[str, Any]],
        unified_episodes: List[Dict[str, Any]]
    ):
        """
        Decorates per-port episodes with multi-UE correlation metadata.
        Does not mutate title text directly to prevent duplicate brackets.
        """
        multi_ue_incidents = [u for u in unified_episodes if u.get('is_multi_ue')]
        if not multi_ue_incidents:
            return

        for u in multi_ue_incidents:
            ports = u['involved_ports']
            u_start = u['t_start']
            u_end = u['t_end']

            for pk in ports:
                if pk not in group_port_dict:
                    continue
                p_episodes = group_port_dict[pk].get('episodes', [])
                for ep in p_episodes:
                    ep_s = ep['t_start']
                    ep_e = ep['t_end']
                    if not (ep_e < u_start or ep_s > u_end):
                        ep['is_multi_ue'] = True
                        ep['involved_ports'] = ports
