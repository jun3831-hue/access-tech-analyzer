"""
===============================================================================
Script Name   : pci_state_tracker.py
3GPP Standard : Common State Tracker across TS 36.331 / TS 38.331 / TS 36.423 / TS 38.413
Module Role   : Tree Path-Driven Isolated PCI/ARFCN State Tracking Engine
===============================================================================
"""

import re
from typing import Dict, List, Any

class PCIStateTracker:
    """Tree Path-Driven RAT-Isolated PCI & ARFCN state tracker for 4G LTE and 5G NR logs."""
    
    def __init__(self, initial_lte_pci: int = None, initial_lte_earfcn: int = None,
                 initial_nr_pci: int = None, initial_nr_arfcn: int = None):
        self.current_lte_pci = initial_lte_pci
        self.current_lte_earfcn = initial_lte_earfcn
        self.current_nr_pci = initial_nr_pci
        self.current_nr_arfcn = initial_nr_arfcn
        
    def update_from_line(self, line: str, path_stack: List[str] = None) -> None:
        """
        Updates PCI state strictly when PCI-changing messages or headers are encountered.
        Prevents PCI contamination across RAT lines.
        """
        # Header / Pci<X>@Earfcn<Y> (LTE)
        lte_m = re.search(r'Pci(\d+)@Earfcn(\d+)', line, re.IGNORECASE)
        if lte_m:
            self.current_lte_pci = int(lte_m.group(1))
            self.current_lte_earfcn = int(lte_m.group(2))

        # Header / Pci<X>@NrArfcn<Y> (NR)
        nr_m = re.search(r'Pci(\d+)@NrArfcn(\d+)', line, re.IGNORECASE)
        if nr_m:
            self.current_nr_pci = int(nr_m.group(1))
            self.current_nr_arfcn = int(nr_m.group(2))

        # Explicit PathStack PCI updates for Handover Sync / MobilityControlInfo
        if path_stack:
            clean_stack = [re.sub(r'[^a-zA-Z0-9]', '', p).lower() for p in path_stack]

            # LTE Mobility Control Info Target PCI
            if 'mobilitycontrolinfo' in clean_stack and 'targetphyscellid' in line.lower():
                m = re.search(r'=\s*(\d+)', line)
                if m:
                    self.current_lte_pci = int(m.group(1))

            # NR Sync Target PCI
            if ('reconfigurationwithsync' in clean_stack or 'spcellconfigcommon' in clean_stack) and 'physcellid' in line.lower():
                m = re.search(r'=\s*(\d+)', line)
                if m:
                    self.current_nr_pci = int(m.group(1))

    def get_state(self) -> Dict[str, Any]:
        """Returns current isolated PCI/ARFCN snapshot."""
        return {
            'LTE_PCI': self.current_lte_pci,
            'LTE_ARFCN': self.current_lte_earfcn,
            'NR_PCI': self.current_nr_pci,
            'NR_ARFCN': self.current_nr_arfcn
        }
