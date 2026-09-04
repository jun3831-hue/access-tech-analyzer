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
    'title': '🚀 PDCP Total (4G+5G 듀얼 총합 속도)',
    'source_column': '[Call & 5G KPI Total Info Layer2 PDCP DL Throughput(+Split Bearer) [Mbps]]',
    'fallback_columns': ['PDCP DL 속도 (Mbps)', 'PDCP_DL_Tput', 'PDCP_Total_DL_Tput'],
    'tiers': [
        {'min': 1000.0, 'color': '#10b981', 'label': '≥ 1000', 'code': '초고속'},
        {'min': 500.0,  'color': '#eab308', 'label': '500 ~ 1000', 'code': '우수'},
        {'min': 100.0,  'color': '#f97316', 'label': '100 ~ 500', 'code': '보통'},
        {'min': 0.0,    'color': '#ef4444', 'label': '< 100', 'code': '저속'}
    ]
}

NR_MAC_DL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'nr_mac',
    'title': '⚡ NR Total MAC (5G 물리 전송 속도)',
    'source_column': '[Call & 5G KPI Total Info Layer2 MAC DL Throughput [Mbps]]',
    'fallback_columns': ['NR MAC DL 속도 (Mbps)', 'NR_MAC_DL_Tput', 'NR MAC DL Throughput (Mbps)'],
    'tiers': [
        {'min': 1000.0, 'color': '#10b981', 'label': '≥ 1000', 'code': '초고속'},
        {'min': 500.0,  'color': '#eab308', 'label': '500 ~ 1000', 'code': '우수'},
        {'min': 100.0,  'color': '#f97316', 'label': '100 ~ 500', 'code': '보통'},
        {'min': 0.0,    'color': '#ef4444', 'label': '< 100', 'code': '저속'}
    ]
}

LTE_MAC_DL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'lte_mac',
    'title': '📶 LTE Total MAC (LTE CA 전체 통합 속도)',
    'source_column': '[Call & LTE KPI Total Info Layer2 MAC DL Throughput [Mbps]]',
    'fallback_columns': ['[LTE] LTE MAC DL 속도 (Mbps)', 'MAC DL 속도 (Mbps)', 'LTE_MAC_DL_Tput'],
    'tiers': [
        {'min': 100.0, 'color': '#10b981', 'label': '≥ 100', 'code': '초고속'},
        {'min': 50.0,  'color': '#eab308', 'label': '50 ~ 100', 'code': '우수'},
        {'min': 20.0,  'color': '#f97316', 'label': '20 ~ 50', 'code': '보통'},
        {'min': 0.0,   'color': '#ef4444', 'label': '< 20', 'code': '저속'}
    ]
}

APP_DL_TPUT_CRITERIA: Dict[str, Any] = {
    'metric_id': 'app_tp',
    'title': '🚀 App Throughput 속도 (Mbps)',
    'source_column': '[Call & Speed Test T-put Current App Throughput [Mbps]]',
    'fallback_columns': ['App DL 속도 (Mbps)', 'App_DL_Tput', 'Current App Throughput [Mbps]'],
    'tiers': [
        {'min': 500.0, 'color': '#10b981', 'label': '≥ 500', 'code': '초고속'},
        {'min': 300.0, 'color': '#eab308', 'label': '300 ~ 500', 'code': '우수'},
        {'min': 100.0, 'color': '#f97316', 'label': '100 ~ 300', 'code': '보통'},
        {'min': 0.0,   'color': '#ef4444', 'label': '< 100', 'code': '저속'}
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


def get_all_map_criteria_dict() -> Dict[str, Any]:
    """Returns a serializable dictionary of all map metrics for JavaScript injection."""
    return {
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
