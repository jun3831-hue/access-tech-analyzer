# -*- coding: utf-8 -*-
"""
===============================================================================
Module Name   : session_cache_manager.py
Location      : 3_Optis_AI_Analyzer/core/session_cache_manager.py
Description   : Cloud & Local Session Cache Manager for Optis AI Web Analyzer
                - Standard Session Naming: [YYMMDD]_[Route/Scenario]-[Ports]
                  (e.g., 260623_0623 상무지구-M1, 250715_이천~충주 하행-M1~M4)
                - Local & FTP Storing, Listing, Streaming Hydration
                - Zero Re-computation 0-Second Instant Demo Hydration
===============================================================================
"""

import os
import re
import io
import json
import ftplib
import tempfile
from typing import Dict, List, Any, Optional, Tuple

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


def extract_yymmdd(raw_val: Any) -> str:
    """
    Extracts a 6-digit YYMMDD string from a date, timestamp, or filename string.
    e.g. '2025-07-15 13:08:52' -> '250715'
         '2026-06-23'          -> '260623'
         '260814_093129'       -> '260814'
         '250807'              -> '250807'
    """
    s = str(raw_val).strip()
    # 1. Match YYYY-MM-DD or YYYY/MM/DD
    m_full = re.search(r'20(\d{2})[-/.](\d{2})[-/.](\d{2})', s)
    if m_full:
        return f"{m_full.group(1)}{m_full.group(2)}{m_full.group(3)}"

    # 2. Match 6-digit YYMMDD at start of string
    m_yymmdd = re.search(r'^(2[4-9]\d{4})', s)
    if m_yymmdd:
        return m_yymmdd.group(1)

    # 3. Match 4-digit MMDD like 0623 -> Assume 2026 if context implies 260623
    m_mmdd = re.search(r'(?:^|[^0-9])(0[1-9]|1[0-2])([0-3]\d)(?:[^0-9]|$)', s)
    if m_mmdd:
        # Default to 26 for 2026 if current project dataset
        return f"26{m_mmdd.group(1)}{m_mmdd.group(2)}"

    return "250715"


def format_ports_summary(ports: List[str]) -> str:
    """
    Formats a list of port names into a compact range string.
    e.g. ['M1'] -> 'M1'
         ['M1', 'M2', 'M3', 'M4'] -> 'M1~M4'
         ['M1', 'M2'] -> 'M1~M2'
         ['M1-R1', 'M1-R2'] -> 'M1-R1~M1-R2'
    """
    if not ports:
        return "M1"
    if len(ports) == 1:
        return ports[0]
    
    # Check if purely M1, M2, ...
    nums = []
    for p in ports:
        m = re.match(r'^M(\d+)$', p, re.I)
        if m:
            nums.append(int(m.group(1)))
    
    if len(nums) == len(ports):
        nums = sorted(nums)
        if nums == list(range(nums[0], nums[-1] + 1)):
            return f"M{nums[0]}~M{nums[-1]}"
    
    return f"{ports[0]}~{ports[-1]}"


def format_standard_session_name(date_val: Any, scenario_name: str, ports: List[str]) -> str:
    """
    Creates standard session name: [YYMMDD]_[Route/Scenario]-[Ports]
    e.g. 260623_0623 상무지구-M1
         250715_이천~충주 하행-M1~M4
    """
    yymmdd = extract_yymmdd(date_val)
    
    # Clean scenario name: remove legacy prefixes and port suffixes
    sc_clean = re.sub(r'^Optis_V12_', '', scenario_name, flags=re.I)
    sc_clean = re.sub(r'[-_#]M\d+.*$', '', sc_clean, flags=re.I)
    sc_clean = re.sub(r'[-_]M\d+~M\d+.*$', '', sc_clean, flags=re.I)
    sc_clean = sc_clean.replace('_Map', '').replace('_Master', '').strip()
    
    # Standardize route wave tilde (이천충주하행 -> 이천~충주 하행)
    if '이천충주' in sc_clean:
        sc_clean = sc_clean.replace('이천충주', '이천~충주 ')
    elif '충주문경' in sc_clean:
        sc_clean = sc_clean.replace('충주문경', '충주~문경 ')
    elif '문경충주' in sc_clean:
        sc_clean = sc_clean.replace('문경충주', '문경~충주 ')
    elif '충주이천' in sc_clean:
        sc_clean = sc_clean.replace('충주이천', '충주~이천 ')

    ports_summary = format_ports_summary(ports)
    return f"{yymmdd}_{sc_clean}-{ports_summary}"


class SessionCacheManager:
    """
    Unified manager for local and remote (FTP/SFTP) session caching.
    """
    REMOTE_BASE_CACHE_DIR = "/Personal/전광용/260728_Analyzer Tool/sessions"

    def __init__(self, local_base_dir: Optional[str] = None):
        if local_base_dir is None:
            # Default to 3_Optis_AI_Analyzer/cache/sessions
            cur = os.path.dirname(os.path.abspath(__file__))
            analyzer_root = os.path.abspath(os.path.join(cur, ".."))
            self.local_base_dir = os.path.join(analyzer_root, "cache", "sessions")
        else:
            self.local_base_dir = local_base_dir

        os.makedirs(self.local_base_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Local Cache Methods
    # -------------------------------------------------------------------------
    def save_local_session(
        self,
        session_name: str,
        map_html: str,
        excel_bytes: bytes,
        txt_report: str,
        meta_dict: Dict[str, Any]
    ) -> str:
        """
        Saves a session bundle to the local cache directory.
        """
        session_dir = os.path.join(self.local_base_dir, session_name)
        os.makedirs(session_dir, exist_ok=True)

        # 1. session_meta.json
        meta_path = os.path.join(session_dir, "session_meta.json")
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_dict, f, ensure_ascii=False, indent=2)

        # 2. map.html
        map_path = os.path.join(session_dir, "map.html")
        with open(map_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(map_html)

        # 3. master.xlsx
        excel_path = os.path.join(session_dir, "master.xlsx")
        with open(excel_path, 'wb') as f:
            f.write(excel_bytes)

        # 4. report.txt
        txt_path = os.path.join(session_dir, "report.txt")
        with open(txt_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.write(txt_report)

        return session_dir

    def list_local_sessions(self) -> List[str]:
        """
        Lists all available session directories in the local cache.
        """
        if not os.path.exists(self.local_base_dir):
            return []
        sessions = []
        for name in os.listdir(self.local_base_dir):
            p = os.path.join(self.local_base_dir, name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "map.html")):
                sessions.append(name)
        return sorted(sessions)

    def load_local_session(self, session_name: str) -> Optional[Dict[str, Any]]:
        """
        Loads a local session bundle directly into memory for instant Streamlit display.
        """
        session_dir = os.path.join(self.local_base_dir, session_name)
        if not os.path.exists(session_dir):
            return None

        meta_path = os.path.join(session_dir, "session_meta.json")
        map_path = os.path.join(session_dir, "map.html")
        excel_path = os.path.join(session_dir, "master.xlsx")
        txt_path = os.path.join(session_dir, "report.txt")

        if not os.path.exists(map_path):
            return None

        meta = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

        with open(map_path, 'r', encoding='utf-8', errors='ignore') as f:
            map_html = f.read()

        excel_bytes = b""
        if os.path.exists(excel_path):
            with open(excel_path, 'rb') as f:
                excel_bytes = f.read()

        txt_report = ""
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
                txt_report = f.read()

        return {
            'map_html': map_html,
            'excel_bytes': excel_bytes,
            'txt_report': txt_report,
            'network_mode': meta.get('network_mode', 'LTE'),
            'vendor': meta.get('vendor', 'COMMON'),
            'ports': meta.get('ports', ['M1']),
            'total_episodes': meta.get('total_episodes', 0),
            'total_pts': meta.get('total_pts', 0),
            'meta': meta
        }

    # -------------------------------------------------------------------------
    # Remote (FTP/SFTP) Cache Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_port(port: Any) -> int:
        try:
            return int(str(port).strip())
        except Exception:
            return 10022

    def list_remote_sessions(
        self,
        host: str,
        port: Any,
        user: str,
        password: str,
        remote_base_dir: Optional[str] = None
    ) -> List[str]:
        """
        Queries FTP/SFTP server for all available session directories under remote_base_dir.
        """
        r_dir = (remote_base_dir or self.REMOTE_BASE_CACHE_DIR).strip().rstrip('/')
        port_int = self._parse_port(port)
        is_sftp = (port_int != 21)

        if is_sftp and HAS_PARAMIKO:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, port=port_int, username=user, password=password, timeout=10)
                sftp = ssh.open_sftp()
                try:
                    entries = sftp.listdir_attr(r_dir)
                    # Directory with session format
                    dirs = [e.filename for e in entries if e.longname.startswith('d') or not '.' in e.filename]
                except Exception:
                    dirs = []
                sftp.close()
                ssh.close()
                return sorted(dirs)
            except Exception:
                return []
        else:
            try:
                ftp = ftplib.FTP()
                ftp.connect(host, port_int, timeout=10)
                ftp.login(user, password)
                ftp.set_pasv(True)
                dirs = []
                try:
                    ftp.cwd(r_dir)
                    names = ftp.nlst()
                    dirs = [n for n in names if not n.endswith('.html') and not n.endswith('.xlsx') and not n.endswith('.json')]
                except Exception:
                    dirs = []
                ftp.quit()
                return sorted(dirs)
            except Exception:
                return []

    def upload_session_to_remote(
        self,
        host: str,
        port: Any,
        user: str,
        password: str,
        session_name: str,
        local_session_dir: Optional[str] = None,
        remote_base_dir: Optional[str] = None
    ) -> bool:
        """
        Uploads local session bundle to remote FTP/SFTP:
        /Optis_Cache/sessions/[session_name]/
        """
        r_base = (remote_base_dir or self.REMOTE_BASE_CACHE_DIR).strip().rstrip('/')
        r_session_dir = f"{r_base}/{session_name}"
        l_dir = local_session_dir or os.path.join(self.local_base_dir, session_name)
        if not os.path.exists(l_dir):
            return False

        files_to_upload = ["session_meta.json", "map.html", "master.xlsx", "report.txt"]
        port_int = self._parse_port(port)
        is_sftp = (port_int != 21)

        if is_sftp and HAS_PARAMIKO:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, port=port_int, username=user, password=password, timeout=15)
                sftp = ssh.open_sftp()

                # Ensure remote directory structure exists using POSIX path logic
                parts = [p for p in r_session_dir.split('/') if p]
                cur_p = ""
                for part in parts:
                    cur_p += f"/{part}"
                    try:
                        sftp.mkdir(cur_p)
                    except Exception:
                        pass

                # Upload files
                for fn in files_to_upload:
                    local_f = os.path.join(l_dir, fn)
                    if os.path.exists(local_f):
                        sftp.put(local_f, f"{r_session_dir}/{fn}")

                sftp.close()
                ssh.close()
                return True
            except Exception as e:
                print(f"[!] SFTP upload failed: {e}")
                return False
        else:
            try:
                ftp = ftplib.FTP()
                ftp.connect(host, port_int, timeout=15)
                ftp.login(user, password)
                ftp.set_pasv(True)

                # Make dirs
                parts = [p for p in r_session_dir.split('/') if p]
                curr_path = ""
                for part in parts:
                    curr_path += f"/{part}"
                    try:
                        ftp.mkd(curr_path)
                    except Exception:
                        pass

                ftp.cwd(r_session_dir)
                for fn in files_to_upload:
                    local_f = os.path.join(l_dir, fn)
                    if os.path.exists(local_f):
                        with open(local_f, 'rb') as fp:
                            ftp.storbinary(f"STOR {fn}", fp)

                ftp.quit()
                return True
            except Exception as e:
                print(f"[!] FTP upload failed: {e}")
                return False

    def download_remote_session(
        self,
        host: str,
        port: Any,
        user: str,
        password: str,
        session_name: str,
        remote_base_dir: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Downloads a remote session bundle directly into memory (and saves to local cache).
        """
        r_base = (remote_base_dir or self.REMOTE_BASE_CACHE_DIR).strip().rstrip('/')
        r_session_dir = f"{r_base}/{session_name}"
        port_int = self._parse_port(port)
        is_sftp = (port_int != 21)

        downloaded_bytes = {}
        files_to_get = ["session_meta.json", "map.html", "master.xlsx", "report.txt"]

        if is_sftp and HAS_PARAMIKO:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host, port=port_int, username=user, password=password, timeout=15)
                sftp = ssh.open_sftp()
                for fn in files_to_get:
                    try:
                        remote_f = f"{r_session_dir}/{fn}"
                        with sftp.open(remote_f, 'rb') as rf:
                            downloaded_bytes[fn] = rf.read()
                    except Exception:
                        pass
                sftp.close()
                ssh.close()
            except Exception as e:
                print(f"[!] SFTP download failed: {e}")
                return None
        else:
            try:
                ftp = ftplib.FTP()
                ftp.connect(host, port_int, timeout=15)
                ftp.login(user, password)
                ftp.set_pasv(True)
                ftp.cwd(r_session_dir)
                for fn in files_to_get:
                    buf = io.BytesIO()
                    try:
                        ftp.retrbinary(f"RETR {fn}", buf.write)
                        downloaded_bytes[fn] = buf.getvalue()
                    except Exception:
                        pass
                ftp.quit()
            except Exception as e:
                print(f"[!] FTP download failed: {e}")
                return None

        if "map.html" not in downloaded_bytes:
            return None

        map_html = downloaded_bytes["map.html"].decode('utf-8', errors='ignore')
        excel_bytes = downloaded_bytes.get("master.xlsx", b"")
        txt_report = downloaded_bytes.get("report.txt", b"").decode('utf-8', errors='ignore')
        
        meta = {}
        if "session_meta.json" in downloaded_bytes:
            try:
                meta = json.loads(downloaded_bytes["session_meta.json"].decode('utf-8'))
            except Exception:
                meta = {}

        # Cache locally for future instant loads
        try:
            self.save_local_session(session_name, map_html, excel_bytes, txt_report, meta)
        except Exception:
            pass

        return {
            'map_html': map_html,
            'excel_bytes': excel_bytes,
            'txt_report': txt_report,
            'network_mode': meta.get('network_mode', 'LTE'),
            'vendor': meta.get('vendor', 'COMMON'),
            'ports': meta.get('ports', ['M1']),
            'total_episodes': meta.get('total_episodes', 0),
            'total_pts': meta.get('total_pts', 0),
            'meta': meta
        }
