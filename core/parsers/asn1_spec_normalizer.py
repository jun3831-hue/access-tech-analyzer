"""
===============================================================================
Script Name   : asn1_spec_normalizer.py
Location      : analyzer/01_base_parsers/asn1_spec_normalizer.py
3GPP Standard : 3GPP TS 36.331 (LTE) & TS 38.331 (NR) Specifications
Module Role   : Official 3GPP ASN.1 Field Normalizer (100% Hyphenated Specification Names)
===============================================================================
"""

import re
import os
from typing import List, Dict, Any, Tuple


class ASN1SpecNormalizer:
    """Canonical ASN.1 Field Normalizer using official 3GPP hyphenated specification names."""

    def __init__(self):
        self.clean_map: Dict[str, str] = {}
        self._load_3gpp_schemas()

    def _load_3gpp_schemas(self):
        """Loads official 3GPP ASN.1 field names from workspace schema files and built-in dictionary."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        asn_lte = os.path.join(base_dir, "3gpp_asn1_workspace", "lte_rrc", "EUTRA-RRC-Definitions.asn")
        asn_nr = os.path.join(base_dir, "3gpp_asn1_workspace", "nr_rrc", "NR-RRC-Definitions.asn")

        for asn_path in [asn_lte, asn_nr]:
            if os.path.exists(asn_path):
                try:
                    with open(asn_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    fields = re.findall(r'\b([a-z][a-zA-Z0-9-]*)\b', content)
                    for f_name in fields:
                        clean = re.sub(r'[^a-zA-Z0-9]', '', f_name).lower()
                        if clean and clean not in self.clean_map:
                            self.clean_map[clean] = f_name
                except Exception:
                    pass

        # 100% Official 3GPP Hyphenated Standard Fallback Mapping
        known_fields = [
            "bwp-Id", "cdm-Type", "pucch-ResourceId", "nzp-CSI-RS-ResourceId", "zp-CSI-RS-ResourceId",
            "srs-ResourceId", "srs-ResourceSetId", "csi-ResourceConfigId", "csi-ResourceSetId",
            "nzp-CSI-RS-ResourceSetId", "zp-CSI-RS-ResourceSetId", "csi-IM-ResourceId", "csi-IM-ResourceSetId",
            "sCellToAddModList-r10", "sCellToReleaseList-r10", "measObjectNR-r15", "measIdToRemoveList",
            "measObjectToRemoveList", "reportConfigToRemoveList", "drb-ToAddModList", "drb-ToReleaseList",
            "srb-ToAddModList", "rlc-BearerToAddModList", "rlc-BearerToReleaseList",
            "dmrs-DownlinkForPDSCH-MappingTypeA", "dmrs-UplinkForPUSCH-MappingTypeA",
            "dmrs-TypeA-Position", "pdcch-DMRS-ScramblingID", "p0-NominalWithGrant", "startSymbolAndLength",
            "measObjectId", "reportConfigId", "measId", "nrofPorts", "periodicityAndOffset",
            "firstOFDMSymbolInTimeDomain", "frequencyDomainAllocation", "scramblingID",
            "nrofSRS-Ports", "periodicityAndOffset-p", "b-SRS", "c-SRS", "b-hop", "cyclicShift-n4",
            "combOffset-n4", "transmissionComb", "resourceMapping", "freqDomainPosition", "freqDomainShift",
            "qcl-InfoPeriodicCSI-RS", "startingRB", "nrofRBs", "slots160", "slots320", "slots40", "slots20",
            "physCellId", "rsrpResult", "rsrqResult", "sinrResult", "ssbFrequency", "absoluteFrequencySSB"
        ]
        for field in known_fields:
            clean = re.sub(r'[^a-zA-Z0-9]', '', field).lower()
            if clean and clean not in self.clean_map:
                self.clean_map[clean] = field

    def normalize(self, vendor_field_name: str) -> str:
        """Normalizes raw vendor parameter string to official 3GPP hyphenated field name."""
        if not vendor_field_name:
            return ""
        clean_input = re.sub(r'\[\d+\]', '', str(vendor_field_name)).strip()
        clean_key = re.sub(r'[^a-zA-Z0-9]', '', clean_input).lower()
        return self.clean_map.get(clean_key, clean_input)


class ReleaseAgnosticPathDiscriminator:
    """Full Parent-Child Hierarchy Tuple Path Engine with Release Version Suffix Stripping."""

    @staticmethod
    def normalize_node_name(node_name: str) -> str:
        """Strips 3GPP release version suffixes (-r8, -r15, -v1530) to get canonical node name."""
        clean = re.sub(r'\[\d+\]', '', node_name).strip()
        return re.sub(r'-[r|v]\d+.*', '', clean).strip()

    def discriminate_meas_object(self, raw_path_stack: List[str]) -> str:
        if not raw_path_stack:
            return None

        norm_tuple = tuple(self.normalize_node_name(node) for node in raw_path_stack)
        root_msg = norm_tuple[0]
        leaf_node = norm_tuple[-1]

        if root_msg in ("RRCReconfiguration", "rrcReconfiguration") and leaf_node == "measObjectNR":
            return "38331_MeasObjectToAddModList_NR"
        elif root_msg in ("rrcConnectionReconfiguration", "RRCConnectionReconfiguration") and leaf_node == "measObjectEUTRA":
            return "36331_MeasObjectToAddModList_LTE"
        elif root_msg in ("rrcConnectionReconfiguration", "RRCConnectionReconfiguration") and leaf_node == "measObjectNR":
            return "36331_MeasObjectToAddModList_LTE"

        return None
