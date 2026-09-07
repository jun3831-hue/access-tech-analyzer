"""
===============================================================================
Script Name   : ts_38331_v1930_nr_rrc_definitions.py
Location      : analyzer/01_base_parsers/nr_rrc/ts_38331_v1930_nr_rrc_definitions.py
3GPP Standard : 3GPP TS 38.331 V19.3.0 (2026-06) NR RRC Specification
Module Role   : 5G NR Master Sub-Tables Parsing Engine (Clean Hierarchical 1-Pass)
===============================================================================
"""

import re
import pandas as pd
from typing import List, Dict, Any
try:
    from core.parsers.asn1_spec_normalizer import ASN1SpecNormalizer
except ImportError:
    from asn1_spec_normalizer import ASN1SpecNormalizer


class NRRRCDefinitionsV1930:
    """Parser for 3GPP TS 38.331 V19.3.0 NR RRC Messages (20 Master Sub-Tables)."""

    EXCLUDED_MESSAGES = {'RRC_RECONFIG', 'RRC_RECONFIG_COMPLETE', 'RRC_MOBILITY'}

    def __init__(self):
        self.normalizer = ASN1SpecNormalizer()

    def parse_packet_blocks(self, lines: List[str]):
        """Splits raw L3 CSV lines into discrete packet blocks (header + body lines)."""
        blocks = []
        curr_hdr = None
        curr_body = []
        for line in lines:
            if line.startswith('__') or ',__' in line or (not line.startswith(',,,,,') and len(line.split(',')) > 6):
                if curr_hdr:
                    blocks.append((curr_hdr, curr_body))
                curr_hdr = line
                curr_body = []
            else:
                curr_body.append(line)
        if curr_hdr:
            blocks.append((curr_hdr, curr_body))
        return blocks

    def parse_all_nr_tables(self, lines: List[str], tracker) -> Dict[str, pd.DataFrame]:
        """Fast Hierarchical 1-Pass 5G NR Master Sub-Tables Parser (Expanding Nested Array Items)."""
        table_specs = {
            '38331_MeasObjectToAddModList_NR': {'keywords': ['measObjectToAddModList', 'measObjectToRemoveList', 'measObjectNR_r15', 'measObjectNR'], 'default_action': 'MODIFY'},
            '38331_ReportConfigToAddModList_NR': {'keywords': ['reportConfigToAddModList', 'reportConfigToRemoveList', 'reportConfigNR'], 'default_action': 'MODIFY'},
            '38331_MeasIdToAddModList_NR': {'keywords': ['measIdToAddModList', 'measIdToRemoveList'], 'default_action': 'MODIFY'},
            '38331_QuantityConfigNR_NR': {'keywords': ['quantityConfigNR'], 'default_action': 'MODIFY'},
            '38331_CellGroupConfig_NR': {'keywords': ['cellGroupConfig', 'nr_SecondaryCellGroupConfig'], 'default_action': 'MODIFY'},
            '38331_RadioBearerConfig_NR': {'keywords': ['radioBearerConfig', 'drb_ToAddModList', 'drb_ToReleaseList', 'srb_ToAddModList'], 'default_action': 'MODIFY'},
            '38331_RLC_BearerConfig_NR': {'keywords': ['rlc_BearerToAddModList', 'rlc_BearerToReleaseList', 'rlc_BearerConfig'], 'default_action': 'MODIFY'},
            '38331_MAC_CellGroupConfig_NR': {'keywords': ['mac_CellGroupConfig'], 'default_action': 'MODIFY'},
            '38331_PhysicalCellGroupConfig_NR': {'keywords': ['physicalCellGroupConfig'], 'default_action': 'MODIFY'},
            '38331_SpCellConfig_NR': {'keywords': ['spCellConfig'], 'default_action': 'MODIFY'},
            '38331_ReconfigurationWithSync_NR': {'keywords': ['reconfigurationWithSync'], 'default_action': 'HANDOVER'},
            '38331_BWP_Downlink_NR': {'keywords': ['initialDownlinkBWP', 'downlinkBWP_ToAddModList', 'downlinkBWP_ToReleaseList', 'zp_CSI_RS_ResourceToAddModList', 'zp_CSI_RS_ResourceToReleaseList', 'dmrs_DownlinkForPDSCH_MappingTypeA', 'pdcch_DMRS_ScramblingID'], 'default_action': 'MODIFY'},
            '38331_BWP_Uplink_NR': {'keywords': ['initialUplinkBWP', 'uplinkBWP_ToAddModList', 'uplinkBWP_ToReleaseList', 'dmrs_UplinkForPUSCH_MappingTypeA'], 'default_action': 'MODIFY'},
            '38331_CSI_MeasConfig_NR': {'keywords': ['nzp_CSI_RS_ResourceToAddModList', 'nzp_CSI_RS_ResourceToReleaseList', 'csi_ResourceConfigToAddModList', 'csi_ResourceConfigToReleaseList', 'csi_ReportConfigToAddModList', 'csi_ReportConfigToReleaseList', 'csi_SSB_ResourceSetToAddModList'], 'default_action': 'MODIFY'},
            '38331_SRS_Config_NR': {'keywords': ['srs_ResourceToAddModList', 'srs_ResourceToReleaseList', 'srs_ResourceSetToAddModList', 'srs_ResourceSetToReleaseList'], 'default_action': 'MODIFY'},
            '38331_SCellToAddModList_NR': {'keywords': ['sCellToAddModList', 'sCellToReleaseList'], 'default_action': 'ADD'},
            '38331_SystemInformationBlockType1_NR': {'keywords': ['systemInformationBlockType1'], 'default_action': 'READ'},
            '38331_SystemInformation_NR': {'keywords': ['systemInformation'], 'default_action': 'READ'},
            '38331_MeasurementReport_Serving_NR': {'keywords': ['measResultServingCell'], 'default_action': 'REPORT'},
            '38331_MeasurementReport_NeighCells_NR': {'keywords': ['measResultNeighCells'], 'default_action': 'REPORT'}
        }

        blocks = self.parse_packet_blocks(lines)
        parsed_rows = {name: [] for name in table_specs.keys()}

        for hdr, body in blocks:
            if tracker:
                tracker.update_from_line(hdr)
                for b_line in body:
                    tracker.update_from_line(b_line)
                state = tracker.get_state()
            else:
                state = {'LTE_PCI': 0, 'LTE_ARFCN': 0, 'NR_PCI': 0, 'NR_ARFCN': 0}

            hdr_parts = [p.strip() for p in hdr.split(',')]
            current_time = hdr_parts[1] if len(hdr_parts) > 1 else ''
            current_msg = hdr_parts[6].replace('__', '') if len(hdr_parts) > 6 else ''

            if current_msg in self.EXCLUDED_MESSAGES:
                continue

            full_body_str = ''.join(body)
            full_body_clean = re.sub(r'[^a-zA-Z0-9]', '', full_body_str).lower()

            for spec_name, spec_info in table_specs.items():
                kws = spec_info['keywords']
                def_act = spec_info['default_action']
                clean_kws = [re.sub(r'[^a-zA-Z0-9]', '', kw).lower() for kw in kws]

                if not any(ckw in full_body_clean for ckw in clean_kws):
                    continue

                b_len = len(body)
                i = 0
                while i < b_len:
                    line = body[i]
                    line_parts = line.split(',')
                    line_strip = line_parts[-1].strip() if len(line_parts) > 5 else line.strip()
                    clean_line = re.sub(r'[^a-zA-Z0-9]', '', line_strip).lower()

                    matched_kw = None
                    for kw, ckw in zip(kws, clean_kws):
                        if ckw in clean_line and ('{' in line_strip or '=' in line_strip):
                            matched_kw = kw
                            break

                    if matched_kw:
                        indent = len(line_strip) - len(line_strip.lstrip())
                        action = def_act
                        if 'release' in clean_line or 'remove' in clean_line or 'toreleaselist' in clean_line or 'toremovelist' in clean_line:
                            action = 'RELEASE'
                        elif 'add' in clean_line or 'mod' in clean_line:
                            action = 'MODIFY'

                        block_data = {
                            'TIME_STAMP': current_time,
                            'MSG_TYPE': current_msg,
                            'LTE_PCI': state.get('LTE_PCI', 0),
                            'LTE_ARFCN': state.get('LTE_ARFCN', 0),
                            'NR_PCI': state.get('NR_PCI', 0),
                            'NR_ARFCN': state.get('NR_ARFCN', 640608),
                            'carrierFreq': state.get('NR_ARFCN', 640608),
                            'ACTION': action,
                            'ItemType': matched_kw
                        }

                        # Single line value
                        if '=' in line_strip and '{' not in line_strip:
                            m = re.search(r'([a-zA-Z0-9_-]+)\s*=\s*([^,\n\}]+)', line_strip)
                            if m:
                                raw_k = m.group(1).strip()
                                raw_v = m.group(2).strip()
                                norm_k = self.normalizer.normalize(raw_k)
                                block_data[raw_k] = raw_v
                                block_data[norm_k] = raw_v
                            parsed_rows[spec_name].append(block_data)
                            i += 1
                            continue

                        # Block structure with {
                        j = i + 1
                        while j < b_len:
                            curr_line = body[j]
                            curr_parts = curr_line.split(',')
                            curr_strip = curr_parts[-1].strip() if len(curr_parts) > 5 else curr_line.strip()
                            curr_indent = len(curr_strip) - len(curr_strip.lstrip())

                            if curr_indent <= indent and '}' in curr_strip:
                                break

                            # Sub-array item detection (only for true array tables like SRS, Bearer, SCell lists)
                            if spec_name not in ('38331_ReconfigurationWithSync_NR', '38331_SpCellConfig_NR', '38331_CellGroupConfig_NR', '38331_PhysicalCellGroupConfig_NR', '38331_MAC_CellGroupConfig_NR', '38331_QuantityConfigNR_NR') and re.search(r'\[\d+\]\s*\{', curr_strip):
                                parsed_rows[spec_name].append(block_data.copy())
                                block_data = {
                                    'TIME_STAMP': current_time,
                                    'MSG_TYPE': current_msg,
                                    'LTE_PCI': state.get('LTE_PCI', 0),
                                    'LTE_ARFCN': state.get('LTE_ARFCN', 0),
                                    'NR_PCI': state.get('NR_PCI', 0),
                                    'NR_ARFCN': state.get('NR_ARFCN', 640608),
                                    'carrierFreq': state.get('NR_ARFCN', 640608),
                                    'ACTION': action,
                                    'ItemType': matched_kw
                                }

                            m = re.search(r'([a-zA-Z0-9_-]+)\s*=\s*([^,\n\}]+)', curr_strip)
                            if m:
                                raw_k = m.group(1).strip()
                                raw_v = m.group(2).strip()
                                norm_k = self.normalizer.normalize(raw_k)
                                block_data[raw_k] = raw_v
                                block_data[norm_k] = raw_v
                            j += 1

                        if spec_name == '38331_MeasObjectToAddModList_NR' and 'ssbFrequency' not in block_data and 'measObjectNR' not in str(matched_kw):
                            i = max(i + 1, j)
                            continue

                        parsed_rows[spec_name].append(block_data)
                        i = max(i + 1, j)
                        continue
                    i += 1

        results = {}
        for name, rows in parsed_rows.items():
            results[name] = pd.DataFrame(rows) if rows else pd.DataFrame()

        return results
