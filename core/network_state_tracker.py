"""
===============================================================================
Script Name   : network_state_tracker.py
Location      : 4_Optis_AI_Analyzer/core/network_state_tracker.py
Module Role   : Event-Driven Real-Time Mode, Vendor & Serving Cell State Machine
===============================================================================
"""

import os
import sys
import re
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from core.vendor_classifier import VendorClassifier


class NetworkStateTracker:
    """Tracks dynamic Network Mode (SA/NSA/Fallback), Active Vendor, and Serving Cells."""

    def __init__(self, initial_lte_pci: Optional[int] = None, initial_lte_arfcn: Optional[int] = None,
                 initial_nr_pci: Optional[int] = None, initial_nr_arfcn: Optional[int] = None):
        self.vendor_classifier = VendorClassifier()
        self.state: Dict[str, Any] = {
            'LTE_PCI': initial_lte_pci,
            'LTE_ARFCN': initial_lte_arfcn,
            'NR_PCI': initial_nr_pci,
            'NR_ARFCN': initial_nr_arfcn,
            'Network_Mode': 'LTE', # Pure LTE by default until NR signaling detected
            'Active_Vendor': 'COMMON' # NOKIA, SAMSUNG, ERICSSON, HUAWEI, COMMON
        }

    def identify_vendor_from_l3(self, rrc_tables: Dict[str, Any], raw_line: str = "") -> str:
        """
        2-Tier Vendor Identification Engine:
        Tier 1: L3 ASN.1 Domain Rule Signatures (nokia_domain_rules.yaml CSI-RS 3-Pool & SRS sl40)
        Tier 2: Direct vendor tokens & parameters
        """
        # Tier 1: Domain Rule Signature Matching (Nokia 3-Pool & SRS sl40, Samsung, Ericsson)
        if rrc_tables:
            raw_lines = rrc_tables.get('_raw_lines', [])
            all_txt = "\n".join(raw_lines[:5000]) if raw_lines else str(rrc_tables)
            all_txt_lower = all_txt.lower()

            # A. Nokia CSI-RS Pool Offsets (Pool 0: 25, 65, 105 / Pool 1: 26, 66, 106 / Pool 2: 27, 107)
            nokia_csirs_match = any(re.search(rf"nzp-csi-rs-resourceid\s*[:=]?\s*{oid}\b", all_txt_lower) for oid in [25, 65, 105, 26, 66, 106, 27, 107])

            # B. Nokia 4-hop Subband SRS Signature (sl40 periodicity pattern)
            nokia_srs_match = ('sl40' in all_txt_lower or 'srs_resourcesettoaddmodlist' in all_txt_lower or 'srs-resourcesettoaddmodlist' in all_txt_lower)

            # C. Nokia explicit keyword
            if 'nokia' in all_txt_lower or nokia_csirs_match or nokia_srs_match:
                return 'NOKIA'
            elif 'samsung' in all_txt_lower:
                return 'SAMSUNG'
            elif 'ericsson' in all_txt_lower:
                return 'ERICSSON'
            elif 'huawei' in all_txt_lower:
                return 'HUAWEI'

        if raw_line:
            clean_l = raw_line.lower()
            if 'nokia' in clean_l or 'sl40' in clean_l:
                return 'NOKIA'
            elif 'samsung' in clean_l:
                return 'SAMSUNG'
            elif 'ericsson' in clean_l:
                return 'ERICSSON'
            elif 'huawei' in clean_l:
                return 'HUAWEI'

        return 'COMMON'

    def update_from_tables(self, parsed_tables: Dict[str, Any]) -> None:
        if not parsed_tables:
            return

        has_nr_cell_group = any(not parsed_tables.get(k, pd.DataFrame()).empty for k in [
            '38331_CellGroupConfig_NR',
            '38331_ReconfigurationWithSync_NR',
            '38331_SpCellConfig_NR',
            '38331_BWP_Downlink_NR'
        ])

        has_sa_sib1 = False
        if '38331_SystemInformationBlockType1_NR' in parsed_tables:
            df_sib1 = parsed_tables['38331_SystemInformationBlockType1_NR']
            if not df_sib1.empty and any('[5gnr]' in str(x).lower() for x in df_sib1.get('MSG_TYPE', [])):
                has_sa_sib1 = True

        if has_sa_sib1:
            self.state['Network_Mode'] = 'SA'
        elif has_nr_cell_group:
            self.state['Network_Mode'] = 'NSA'
        else:
            self.state['Network_Mode'] = 'LTE'

        self.state['Active_Vendor'] = self.identify_vendor_from_l3(parsed_tables)

    def update_from_line(self, line: str, parsed_tables: Optional[Dict[str, Any]] = None) -> None:
        if not line:
            return

        # 1. Serving Cell PCI & Frequency
        m_nr = re.search(r'Pci(\d+)@NrArfcn(\d+)', line, re.IGNORECASE)
        if m_nr:
            self.state['NR_PCI'] = int(m_nr.group(1))
            self.state['NR_ARFCN'] = int(m_nr.group(2))

        m_lte = re.search(r'Pci(\d+)@Earfcn(\d+)', line, re.IGNORECASE)
        if m_lte:
            self.state['LTE_PCI'] = int(m_lte.group(1))
            self.state['LTE_ARFCN'] = int(m_lte.group(2))

        # 2. Dynamic Network Mode Detection
        line_clean = line.lower()
        if 'nr-secondarycellgroupconfig' in line_clean or 'reconfigurationwithsync' in line_clean:
            self.state['Network_Mode'] = 'NSA'
        elif 'mobilityfromnrcommand' in line_clean or 'eps-fallback' in line_clean or 'irat' in line_clean:
            self.state['Network_Mode'] = 'SA_FALLBACK'
        elif 'systeminformationblocktype1' in line_clean and '[5gnr]' in line_clean:
            self.state['Network_Mode'] = 'SA'

        # 3. Dynamic Vendor Detection
        if parsed_tables:
            self.state['Active_Vendor'] = self.identify_vendor_from_l3(parsed_tables, line)

    def get_state(self) -> Dict[str, Any]:
        return self.state.copy()
