"""
===============================================================================
Script Name   : ts_36331_v1930_eutra_rrc_definitions.py
Location      : analyzer/01_base_parsers/lte_rrc/ts_36331_v1930_eutra_rrc_definitions.py
3GPP Standard : 3GPP TS 36.331 V19.3.0 E-UTRA RRC Specification
Module Role   : 4G LTE Master Sub-Tables Parsing Engine (Clean Hierarchical 1-Pass)
===============================================================================
"""

import re
import pandas as pd
from typing import List, Dict, Any
try:
    from core.parsers.asn1_spec_normalizer import ASN1SpecNormalizer
except ImportError:
    from asn1_spec_normalizer import ASN1SpecNormalizer


class EUTRARRCDefinitionsV1930:
    """Parser for 3GPP TS 36.331 V19.3.0 E-UTRA RRC Messages (16 Master Sub-Tables)."""

    EXCLUDED_MESSAGES = set()

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

    def parse_all_lte_tables(self, lines: List[str], tracker) -> Dict[str, pd.DataFrame]:
        """Fast Hierarchical 1-Pass LTE Master Sub-Tables Parser (Expanding Nested Array Items)."""
        table_specs = {
            '36331_MeasObjectToAddModList_LTE': {'keywords': ['measObjectToAddModList', 'measObjectToRemoveList'], 'default_action': 'MODIFY'},
            '36331_ReportConfigToAddModList_LTE': {'keywords': ['reportConfigToAddModList', 'reportConfigToRemoveList', 'reportConfigEUTRA'], 'default_action': 'MODIFY'},
            '36331_MeasIdToAddModList_LTE': {'keywords': ['measIdToAddModList', 'measIdToRemoveList'], 'default_action': 'MODIFY'},
            '36331_QuantityConfig_LTE': {'keywords': ['quantityConfigEUTRA', 'quantityConfig'], 'default_action': 'MODIFY'},
            '36331_RadioResourceConfigDedicated_LTE': {'keywords': ['radioResourceConfigDedicated'], 'default_action': 'MODIFY'},
            '36331_RadioBearerConfig_LTE': {'keywords': ['srb_ToAddModList', 'drb_ToAddModList', 'drb_ToReleaseList'], 'default_action': 'MODIFY'},
            '36331_SCellToAddModList_LTE': {'keywords': ['sCellToAddModList_r10', 'sCellToReleaseList_r10'], 'default_action': 'ADD'},
            '36331_MAC_MainConfig_LTE': {'keywords': ['mac_MainConfig'], 'default_action': 'MODIFY'},
            '36331_PhysicalConfigDedicated_LTE': {'keywords': ['physicalConfigDedicated'], 'default_action': 'MODIFY'},
            '36331_SystemInformationBlockType1_LTE': {'keywords': ['systemInformationBlockType1'], 'default_action': 'READ'},
            '36331_SystemInformation_LTE': {'keywords': ['systemInformation-r8', 'systemInformation'], 'default_action': 'READ'},
            '36331_MobilityControlInfo_LTE': {'keywords': ['mobilityControlInfo'], 'default_action': 'HANDOVER'},
            '36331_RRCConnectionReconfiguration_LTE': {'keywords': ['rrcConnectionReconfiguration-r8', 'rrcConnectionReconfiguration'], 'default_action': 'MODIFY'},
            '36331_MeasurementReport_Serving_LTE': {'keywords': ['measResults', 'measResultPCell'], 'default_action': 'REPORT'},
            '36331_MeasurementReport_NeighCells_LTE': {'keywords': ['measResultListEUTRA', 'measResultNeighCellListNR-r15', 'measResultNeighCells'], 'default_action': 'REPORT'},
            '36331_CG_ConfigInfo_LTE': {'keywords': ['cg_ConfigInfo'], 'default_action': 'MODIFY'}
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
                state = {}
            hdr_parts = [p.strip() for p in hdr.split(',')]
            current_time = hdr_parts[1] if len(hdr_parts) > 1 else ''
            current_msg = hdr_parts[6].replace('__', '') if len(hdr_parts) > 6 else ''

            if current_msg in self.EXCLUDED_MESSAGES:
                continue

            b_len = len(body)
            for spec_name, spec in table_specs.items():
                kws = spec['keywords']
                def_act = spec['default_action']
                clean_kws = [k.replace('_', '').replace('-', '').lower() for k in kws]

                i = 0
                while i < b_len:
                    line = body[i]
                    parts = line.split(',')
                    line_strip = parts[-1].strip() if len(parts) > 5 else line.strip()
                    clean_line = line_strip.replace('_', '').replace('-', '').lower()

                    matched_kw = None
                    for kw, ckw in zip(kws, clean_kws):
                        if ckw in clean_line and ('{' in line_strip or '=' in line_strip or 'result' in clean_line):
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
                            'NR_ARFCN': state.get('NR_ARFCN', 0),
                            'ACTION': action,
                            'ItemType': matched_kw
                        }

                        # Single line value
                        if ('=' in line_strip or re.search(r'^[a-zA-Z0-9_-]+\s+[-+]?\d+', line_strip)) and '{' not in line_strip:
                            m = re.search(r'([a-zA-Z0-9_-]+)(?:\s*=\s*|\s+)([^,\n\}]+)', line_strip)
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

                            # Sub-array item detection (e.g. measIdToAddModList[1] { ... })
                            if re.search(r'\[\d+\]\s*\{', curr_strip):
                                parsed_rows[spec_name].append(block_data.copy())
                                block_data = {
                                    'TIME_STAMP': current_time,
                                    'MSG_TYPE': current_msg,
                                    'LTE_PCI': state.get('LTE_PCI', 0),
                                    'LTE_ARFCN': state.get('LTE_ARFCN', 0),
                                    'NR_PCI': state.get('NR_PCI', 0),
                                    'NR_ARFCN': state.get('NR_ARFCN', 0),
                                    'ACTION': action,
                                    'ItemType': matched_kw
                                }

                            m = re.search(r'([a-zA-Z0-9_-]+)(?:\s*=\s*|\s+)([^,\n\}]+)', curr_strip)
                            if m and '{' not in curr_strip:
                                raw_k = m.group(1).strip()
                                raw_v = m.group(2).strip()
                                norm_k = self.normalizer.normalize(raw_k)
                                block_data[raw_k] = raw_v
                                block_data[norm_k] = raw_v
                            j += 1

                        if spec_name == '36331_MeasObjectToAddModList_LTE' and 'ssbFrequency' in block_data:
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
