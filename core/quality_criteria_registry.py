# -*- coding: utf-8 -*-
"""
===============================================================================
Module Name   : quality_criteria_registry.py
Location      : core/quality_criteria_registry.py
Module Role   : Single Source of Truth (SSOT) for Quality, RF, and Throughput Criteria
                - Raw Full Column Names from OPTis-S4 / DM CSVs
                - Exact Thresholds for RSRP, SINR, Layer, MCS, BLER, CRC Fail, CQI, RI, Throughput, MOS
===============================================================================
"""

from typing import Dict, Any, List, Optional, Tuple


# ------------------------------------------------------------------------------
# 1. RSRP (전계 세기) 기준
# ------------------------------------------------------------------------------
NR_SS_RSRP_CRITERIA: Dict[str, Any] = {
    'metric_id': 'nr_rsrp',
    'title': '📡 5G NR PSCell RSRP (dBm)',
    'source_column': '[Call & 5G KPI PCell RF Serving SS-RSRP [dBm]]',
    'fallback_columns': ['[NR] SS-RSRP (dBm)', 'SS_RSRP', 'NR_RSRP', 'Serving SS-RSRP'],
    'tiers': [
        {'min': -75.0,  'color': '#10b981', 'label': '≥ -75', 'code': '강전계'},
        {'min': -90.0,  'color': '#eab308', 'label': '-90 ~ -75', 'code': '양호'},
        {'min': -105.0, 'color': '#f97316', 'label': '-105 ~ -90', 'code': '중전계'},
        {'min': -140.0, 'color': '#ef4444', 'label': '< -105', 'code': '음영'}
    ]
}

LTE_SERVING_RSRP_CRITERIA: Dict[str, Any] = {
    'metric_id': 'lte_rsrp',
    'title': '📶 LTE Anchor Pcell RSRP (dBm)',
    'source_column': '[Call & LTE KPI PCell Serving RSRP [dBm]]',
    'fallback_columns': ['[LTE] Serving RSRP (dBm)', 'Serving RSRP (dBm)', 'LTE_Serving_RSRP', 'LTE_RSRP', 'RSRP'],
    'tiers': [
        {'min': -75.0,  'color': '#10b981', 'label': '≥ -75', 'code': '강전계'},
        {'min': -90.0,  'color': '#eab308', 'label': '-90 ~ -75', 'code': '양호'},
        {'min': -105.0, 'color': '#f97316', 'label': '-105 ~ -90', 'code': '중전계'},
        {'min': -140.0, 'color': '#ef4444', 'label': '< -105', 'code': '음영'}
    ]
}

DEFAULT_RSRP_FALLBACK = -75.0


# ------------------------------------------------------------------------------
# 2. SINR (신호 품질 & 간섭 & MIMO 랭크 진단 기준)
# ------------------------------------------------------------------------------
NR_SS_SINR_CRITERIA: Dict[str, Any] = {
    'metric_id': 'nr_sinr',
    'title': '⚡ 5G NR SINR 신호품질 (dB)',
    'source_column': '[Call & 5G KPI PCell RF Serving SS-SINR [dB]]',
    'fallback_columns': ['[NR] SS-SINR (dB)', 'SS_SINR', 'NR_SINR', 'Serving SS-SINR'],
    'tiers': [
        {'min': 20.0,  'color': '#10b981', 'label': '≥ 20', 'code': '고품질'},
        {'min': 10.0,  'color': '#eab308', 'label': '10 ~ 20', 'code': '보통'},
        {'min': 0.0,   'color': '#f97316', 'label': '0 ~ 10', 'code': '주의'},
        {'min': -30.0, 'color': '#ef4444', 'label': '< 0', 'code': '간섭'}
    ],
    'HIGH_SINR_MIMO_THRESH': 13.0,
    'EXCELLENT_SINR_THRESH': 18.0,
    'POOR_SINR_INTERFERENCE_THRESH': 5.0
}

LTE_SERVING_SINR_CRITERIA: Dict[str, Any] = {
    'metric_id': 'lte_sinr',
    'title': '⚡ LTE SINR 신호품질 (dB)',
    'source_column': '[Call & LTE KPI PCell SINR [dB]]',
    'fallback_columns': ['[LTE] Serving SINR (dB)', 'Serving SINR (dB)', 'LTE_Serving_SINR', 'LTE_SINR', 'SINR'],
    'tiers': [
        {'min': 20.0,  'color': '#10b981', 'label': '≥ 20', 'code': '고품질'},
        {'min': 10.0,  'color': '#eab308', 'label': '10 ~ 20', 'code': '보통'},
        {'min': 0.0,   'color': '#f97316', 'label': '0 ~ 10', 'code': '주의'},
        {'min': -30.0, 'color': '#ef4444', 'label': '< 0', 'code': '간섭'}
    ]
}


# ------------------------------------------------------------------------------
# 3. MIMO Layer / Rank Indicator (RI) 기준 (DIAG_M_01_NR)
# ------------------------------------------------------------------------------
MIMO_LAYER_CRITERIA: Dict[str, Any] = {
    'source_column_layer': '[Call & 5G KPI PCell Layer1 DL Layer Num (Avg)]',
    'source_column_ri': '[Call & 5G KPI PCell RF RI(Avg)]',
    'source_column_ri4': '[Call & 5G KPI PCell Layer1 DL RI4 Rate [%]]',
    'fallback_columns_layer': ['[NR] DL Layer Num', 'DL Layer Num', 'DL_Layer_Num'],
    'fallback_columns_ri': ['[NR] WB RI', 'PCell WB RI', 'WB_RI'],
    'TARGET_4LAYER': 4.0,
    'RANK_RESTRICTION_THRESH': 2.2,
    'MIN_DURATION_SEC': 3.0,
    'MIN_SAMPLE_COUNT': 3
}


# ------------------------------------------------------------------------------
# 4. Modulation & Coding Scheme (MCS) 기준
# ------------------------------------------------------------------------------
DL_MCS_CRITERIA: Dict[str, Any] = {
    'source_column_nr': '[Call & 5G KPI PCell Layer1 DL MCS (Avg)]',
    'source_column_lte': '[Call & LTE KPI PCell DL MCS0]',
    'fallback_columns': ['[NR] DL MCS', '[LTE] DL MCS', 'DL MCS', 'DL_MCS'],
    'HIGH_MCS_THRESH': 24.0,
    'LOW_MCS_THRESH': 10.0,
    'MAX_MCS_VALUE': 28.0
}


# ------------------------------------------------------------------------------
# 5. Block Error Rate (BLER) 기준 (DIAG_M_02_NR)
# ------------------------------------------------------------------------------
PDSCH_BLER_CRITERIA: Dict[str, Any] = {
    'source_column_nr': '[Call & 5G KPI PCell Layer1 DL BLER [%]]',
    'source_column_lte': '[Call & LTE KPI PCell PDSCH BLER [%]]',
    'fallback_columns': ['[NR] PDSCH BLER (%)', '[LTE] PDSCH BLER (%)', 'PDSCH BLER', 'BLER'],
    'QUICK_SCAN_THRESH': 15.0,
    'SEVERE_BLER_THRESH': 30.0,
    'NORMAL_BLER_TARGET': 10.0
}


# ------------------------------------------------------------------------------
# 6. PDSCH CRC 연속 FAIL 슬롯 기준 (DIAG_M_02_NR)
# ------------------------------------------------------------------------------
PDSCH_CRC_FAIL_CRITERIA: Dict[str, Any] = {
    'source_csv': 'MAC_PDSCH_PER_SLOT',
    'slot_crc_column': 'CRC_Result',
    'CONSECUTIVE_FAIL_SLOTS_THRESH': 100,
    'MIN_DURATION_SEC': 2.0
}


# ------------------------------------------------------------------------------
# 7. Channel Quality Indicator (CQI) 기준
# ------------------------------------------------------------------------------
CQI_CRITERIA: Dict[str, Any] = {
    'source_column_nr': '[Call & 5G KPI PCell RF CQI]',
    'source_column_lte': '[Call & LTE KPI PCell WB CQI CW0]',
    'fallback_columns': ['[NR] CQI', '[LTE] CQI', 'CQI', 'Serving CQI'],
    'tiers': [
        {'min': 12.0, 'label': 'CQI 12~15 (고품질 256QAM)', 'color': '#10b981'},
        {'min': 7.0,  'label': 'CQI 7~11 (보통 64QAM/16QAM)', 'color': '#eab308'},
        {'min': 1.0,  'label': 'CQI 1~6 (저품질 QPSK)',     'color': '#ef4444'}
    ]
}


# ------------------------------------------------------------------------------
# 8. Throughput (데이터 전송 속도) 기준
# ------------------------------------------------------------------------------
PDCP_TOTAL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'pdcp_total',
    'title': '🚀 PDCP Total (4G+5G 듀얼 결합 속도)',
    'source_column': '[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]',
    'fallback_columns': ['PDCP DL 속도 (Mbps)', 'PDCP_DL_Tput', 'PDCP_Total_DL_Tput'],
    'tiers': [
        {'min': 660.0, 'color': '#0ea5e9', 'label': '≥ 660', 'code': '우수'},
        {'min': 380.0, 'color': '#10b981', 'label': '380 ~ 660', 'code': '양호'},
        {'min': 160.0, 'color': '#f59e0b', 'label': '160 ~ 380', 'code': '미흡'},
        {'min': 0.0,   'color': '#ef4444', 'label': '< 160', 'code': '불량'}
    ]
}

NR_MAC_DL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'nr_mac',
    'title': '⚡ NR Total MAC (5G 물리 계층 속도)',
    'source_column': '[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]',
    'fallback_columns': ['NR MAC DL 속도 (Mbps)', 'NR_MAC_DL_Tput', 'NR MAC DL Throughput (Mbps)'],
    'tiers': [
        {'min': 480.0, 'color': '#0ea5e9', 'label': '≥ 480', 'code': '우수'},
        {'min': 280.0, 'color': '#10b981', 'label': '280 ~ 480', 'code': '양호'},
        {'min': 120.0, 'color': '#f59e0b', 'label': '120 ~ 280', 'code': '미흡'},
        {'min': 0.0,   'color': '#ef4444', 'label': '< 120', 'code': '불량'}
    ]
}

LTE_MAC_DL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'lte_mac',
    'title': '📶 LTE Total MAC (LTE CA 전체 통합 속도)',
    'source_column': '[Call & LTE KPI Total Info Layer2 MAC DL Throughput [Mbps]]',
    'fallback_columns': ['[LTE] LTE MAC DL 속도 (Mbps)', 'MAC DL 속도 (Mbps)', 'LTE_MAC_DL_Tput'],
    'tiers': [
        {'min': 180.0, 'color': '#0ea5e9', 'label': '≥ 180', 'code': '우수'},
        {'min': 100.0, 'color': '#10b981', 'label': '100 ~ 180', 'code': '양호'},
        {'min': 45.0,  'color': '#f59e0b', 'label': '45 ~ 100', 'code': '미흡'},
        {'min': 0.0,   'color': '#ef4444', 'label': '< 45', 'code': '불량'}
    ]
}

APP_DL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'app_tp',
    'title': '🚀 Throughput 속도 (Mbps)',
    'source_column': '[Call & Speed Test T-put Current App Throughput [Mbps]]',
    'fallback_columns': ['App DL 속도 (Mbps)', 'App_DL_Tput', 'Current App Throughput [Mbps]'],
    'tiers': [
        {'min': 400.0, 'color': '#0ea5e9', 'label': '≥ 400', 'code': '우수'},
        {'min': 200.0, 'color': '#10b981', 'label': '200 ~ 400', 'code': '양호'},
        {'min': 80.0,  'color': '#f59e0b', 'label': '80 ~ 200', 'code': '미흡'},
        {'min': 0.0,   'color': '#ef4444', 'label': '< 80', 'code': '불량'}
    ]
}


def get_bandwidth_based_throughput_criteria(
    net_mode: str = 'NSA',
    lte_bw: float = 60.0,
    nr_bw: float = 100.0,
    metric_id: str = 'fourth'
) -> Dict[str, Any]:
    """
    Calculates dynamic Throughput criteria based on combined carrier bandwidth (MHz)
    with realistic field MAC-layer efficiency coefficients:
    - LTE MAC coefficient: 5.0 Mbps / MHz (20M -> 100M, 40M -> 200M, 60M -> 300M)
    - NR MAC coefficient: 8.0 Mbps / MHz (100M -> 800M)
    - Tiers: Tier 1 (>= 60%), Tier 2 (35% ~ 60%), Tier 3 (15% ~ 35%), Tier 4 (< 15%)
    """
    mode = str(net_mode).upper()
    eff_lte = max(float(lte_bw), 10.0) if lte_bw and lte_bw > 0 else 60.0
    eff_nr = max(float(nr_bw), 20.0) if nr_bw and nr_bw > 0 else 100.0

    if mode == 'LTE':
        v_target = eff_lte * 5.0
        title = f'🚀 LTE Total MAC [LTE {int(eff_lte)}MHz]'
        m_id = 'lte_mac'
    elif mode == 'SA':
        v_target = eff_nr * 8.0
        title = f'🚀 NR Total MAC [NR {int(eff_nr)}MHz]'
        m_id = 'nr_mac'
    else:  # NSA
        tot_bw = eff_nr + eff_lte
        v_target = (eff_nr * 8.0) + (eff_lte * 5.0)
        title = f'🚀 Total PDCP [NR {int(eff_nr)}MHz + LTE {int(eff_lte)}MHz]'
        m_id = 'pdcp_total'

    v_target = round(v_target / 10.0) * 10.0
    t1_min = round((v_target * 0.60) / 10.0) * 10.0
    t2_min = round((v_target * 0.35) / 10.0) * 10.0
    t3_min = round((v_target * 0.15) / 5.0) * 5.0

    return {
        'metric_id': m_id,
        'title': title,
        'target_peak': v_target,
        'effective_bw': int(eff_lte if mode == 'LTE' else (eff_nr if mode == 'SA' else (eff_nr + eff_lte))),
        'tiers': [
            {'min': float(t1_min), 'color': '#0ea5e9', 'label': f'≥ {int(t1_min)}', 'code': '우수'},
            {'min': float(t2_min), 'color': '#10b981', 'label': f'{int(t2_min)} ~ {int(t1_min)}', 'code': '양호'},
            {'min': float(t3_min), 'color': '#f59e0b', 'label': f'{int(t3_min)} ~ {int(t2_min)}', 'code': '미흡'},
            {'min': 0.0,           'color': '#ef4444', 'label': f'< {int(t3_min)}', 'code': '불량'}
        ]
    }


# ------------------------------------------------------------------------------
# 9. VoLTE 음성 통화 품질 (MOS) 기준
# ------------------------------------------------------------------------------
VOLTE_MOS_CRITERIA: Dict[str, Any] = {
    'metric_id': 'mos',
    'title': '🎙️ VoLTE 음성 MOS 점수',
    'source_column': 'MOS',
    'fallback_columns': ['MOS', 'POLQA', 'Voice_MOS'],
    'tiers': [
        {'min': 4.0, 'color': '#10b981', 'label': '≥ 4.0', 'code': '우수'},
        {'min': 3.5, 'color': '#eab308', 'label': '3.5 ~ 4.0', 'code': '양호'},
        {'min': 3.0, 'color': '#f97316', 'label': '3.0 ~ 3.5', 'code': '주의'},
        {'min': 1.0, 'color': '#ef4444', 'label': '< 3.0', 'code': '불량'}
    ]
}


# ------------------------------------------------------------------------------
# 10. L3 CSI / CQI / PMI 보고 설정 기준 (Domain 07)
# ------------------------------------------------------------------------------
L3_CSI_REPORTING_POLICY: Dict[str, Any] = {
    'EXCLUDED_VARIABLE_INDEXES': [
        r'cqi_pmi_ConfigIndex',
        r'cqi-pmi-ConfigIndex',
        r'ri_ConfigIndex',
        r'ri-ConfigIndex',
        r'srs_ConfigIndex',
        r'srs-ConfigIndex',
        r'sr_ConfigIndex',
        r'sr-ConfigIndex'
    ],
    'AUDITED_FUNCTIONAL_PARAMETERS': [
        'cqi_FormatIndicatorPeriodic',
        'cqi-FormatIndicatorPeriodic',
        'nomPDSCH_RS_EPRE_Offset',
        'nomPDSCH-RS-EPRE-Offset',
        'simultaneousAckNackAndCQI'
    ]
}


# ------------------------------------------------------------------------------
# Helper Resolution Functions
# ------------------------------------------------------------------------------
def evaluate_tier(val: Optional[float], criteria: Dict[str, Any]) -> Dict[str, str]:
    """Returns the matching tier dict for a given numeric value."""
    if val is None or val == -140.0:
        return criteria['tiers'][-1]
    for t in criteria['tiers']:
        if val >= t['min']:
            return t
    return criteria['tiers'][-1]


def get_rsrp_evaluation(rsrp_val: Optional[float], is_nr: bool = False) -> Tuple[str, str, str]:
    """Returns (code, label, color) for RSRP."""
    crit = NR_SS_RSRP_CRITERIA if is_nr else LTE_SERVING_RSRP_CRITERIA
    tier = evaluate_tier(rsrp_val, crit)
    return tier['code'], tier['label'], tier['color']


def get_sinr_evaluation(sinr_val: Optional[float], is_nr: bool = False) -> Tuple[str, str, str]:
    """Returns (code, label, color) for SINR."""
    crit = NR_SS_SINR_CRITERIA if is_nr else LTE_SERVING_SINR_CRITERIA
    tier = evaluate_tier(sinr_val, crit)
    return tier['code'], tier['label'], tier['color']


def get_all_map_criteria_dict(
    net_mode: Optional[str] = None,
    lte_bw: Optional[float] = None,
    nr_bw: Optional[float] = None
) -> Dict[str, Any]:
    """Returns a serializable dictionary of all map metrics for JavaScript injection with dynamic bandwidth awareness."""
    base_dict = {
        'nr_rsrp': NR_SS_RSRP_CRITERIA,
        'lte_rsrp': LTE_SERVING_RSRP_CRITERIA,
        'rsrp': LTE_SERVING_RSRP_CRITERIA,
        'nr_sinr': NR_SS_SINR_CRITERIA,
        'lte_sinr': LTE_SERVING_SINR_CRITERIA,
        'sinr': NR_SS_SINR_CRITERIA,
        'pdcp_total': PDCP_TOTAL_TPUT_CRITERIA,
        'nr_mac': NR_MAC_DL_TPUT_CRITERIA,
        'lte_mac': LTE_MAC_DL_TPUT_CRITERIA,
        'app_tp': APP_DL_TPUT_CRITERIA,
        'mos': VOLTE_MOS_CRITERIA
    }
    if net_mode:
        m = str(net_mode).upper()
        eff_lte = float(lte_bw) if (lte_bw and lte_bw > 0) else 60.0
        eff_nr = float(nr_bw) if (nr_bw and nr_bw > 0) else 100.0

        if m == 'NSA':
            base_dict['pdcp_total'] = get_bandwidth_based_throughput_criteria('NSA', eff_lte, eff_nr, metric_id='pdcp_total')
            base_dict['nr_mac'] = get_bandwidth_based_throughput_criteria('SA', 0.0, eff_nr, metric_id='nr_mac')
            base_dict['lte_mac'] = get_bandwidth_based_throughput_criteria('LTE', eff_lte, 0.0, metric_id='lte_mac')
            base_dict['fourth'] = base_dict['pdcp_total']
            base_dict['app_tp'] = base_dict['pdcp_total']
        elif m == 'SA':
            base_dict['nr_mac'] = get_bandwidth_based_throughput_criteria('SA', 0.0, eff_nr, metric_id='nr_mac')
            base_dict['fourth'] = base_dict['nr_mac']
            base_dict['app_tp'] = base_dict['nr_mac']
        else:  # LTE
            base_dict['lte_mac'] = get_bandwidth_based_throughput_criteria('LTE', eff_lte, 0.0, metric_id='lte_mac')
            base_dict['fourth'] = base_dict['lte_mac']
            base_dict['app_tp'] = base_dict['lte_mac']
    return base_dict


# ------------------------------------------------------------------------------
# 3GPP 진단 및 인과 추적 전용 복합 전계 판별 표준 함수 (Single SSOT)
# ------------------------------------------------------------------------------

def is_clean_rf_condition(rsrp: Optional[float], sinr: Optional[float], is_nr: bool = False) -> bool:
    """
    RSRP가 중전계 이상(>= -105.0 dBm)이면서 SINR이 보통/고품질 티어(>= 10.0 dB)인 정상 무선 품질 구간 판별.
    호 절단/RLF 발생 시 '간섭'이 아닌 '상향 동기 상실/기지국 거절/동기 상실'로 인과관계를 분기하는 가드.
    """
    if rsrp is None or sinr is None:
        return False
    return rsrp >= -105.0 and sinr >= 10.0


def is_pilot_pollution_condition(rsrp: Optional[float], sinr: Optional[float], overlap_cnt: int = 0) -> bool:
    """
    서빙 전계는 양호/중전계(>= -100.0 dBm)이나 복수 셀 중첩 등으로 SINR이 간섭 티어(< 0.0 dB 또는 overlap >= 3)인 상태 판별.
    """
    if rsrp is None or sinr is None:
        return False
    return (rsrp >= -100.0 and sinr < 0.0) or (overlap_cnt >= 3 and sinr < 3.0)


def is_weak_coverage_condition(rsrp: Optional[float], sinr: Optional[float] = None) -> bool:
    """
    신호 세기 자체가 고갈된 음영 티어(RSRP < -105.0 dBm) 상태 판별.
    """
    if rsrp is None:
        return False
    return rsrp < -105.0


def evaluate_rf_situation(rsrp: Optional[float], sinr: Optional[float], is_nr: bool = False) -> Dict[str, Any]:
    """
    RSRP와 SINR을 통합 평가하여 상황 코드와 요약 텍스트를 반환.
    반환 dict: {'rsrp_code', 'sinr_code', 'is_clean', 'is_interference', 'is_weak_coverage', 'summary'}
    """
    rsrp_code, _, _ = get_rsrp_evaluation(rsrp, is_nr=is_nr)
    sinr_code, _, _ = get_sinr_evaluation(sinr, is_nr=is_nr)
    clean = is_clean_rf_condition(rsrp, sinr, is_nr=is_nr)
    pilot = is_pilot_pollution_condition(rsrp, sinr)
    weak = is_weak_coverage_condition(rsrp, sinr)

    if weak:
        summary = f"커버리지 음영 (RSRP {rsrp_code})"
    elif pilot:
        summary = f"채널 간섭 우세 (SINR {sinr_code})"
    elif clean:
        summary = f"양호 전파 환경 ({rsrp_code} / {sinr_code})"
    else:
        summary = f"일반 전파 환경 ({rsrp_code} / {sinr_code})"

    return {
        'rsrp_code': rsrp_code,
        'sinr_code': sinr_code,
        'is_clean': clean,
        'is_interference': pilot,
        'is_weak_coverage': weak,
        'summary': summary
    }


# ------------------------------------------------------------------------------
# 급격한 서빙 전계 낙폭 판별 표준 기준 (Single SSOT)
# ------------------------------------------------------------------------------
RAPID_RSRP_DROP_DELTA_DB: float = -10.0
RAPID_RSRP_DROP_WINDOW_SEC: float = 5.0


def is_rapid_rsrp_drop(delta_rsrp: Optional[float], delta_sec: Optional[float] = None) -> bool:
    """
    서빙 전계의 급격한 낙폭(5초 이내 delta_rsrp <= -10.0 dB) 여부를 판별하는 단일 SSOT 가드.
    단순 1~2 dB 미세 변동 구간을 '급격한 전계 급락'으로 오진하는 것을 방지.
    """
    if delta_rsrp is None:
        return False
    if delta_sec is not None and delta_sec > RAPID_RSRP_DROP_WINDOW_SEC:
        return False
    return delta_rsrp <= RAPID_RSRP_DROP_DELTA_DB

