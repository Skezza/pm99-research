"""Data models for PM99 database records.

Implements Python dataclasses matching the binary structures from MANAGPRE.EXE.
"""

from dataclasses import dataclass, field
from typing import Optional, List
import struct
import logging

from app.xor import decode_entry, encode_entry, read_string, write_string
 
logger = logging.getLogger(__name__)
import re

class TeamRecord:
    """Team record with ID and stadium extraction + modification support."""

    def __init__(self, data: bytes, record_offset: int):
        self.raw_data = bytearray(data)
        self.original_raw_data = bytes(data)
        self.record_offset = record_offset
        self.container_offset = None
        self.container_relative_offset = None

        # Team ID and where it was found (offset inside raw_data) so we can write it back
        try:
            tid, tid_off = self._extract_team_id()
        except Exception:
            tid, tid_off = 0, None
        self.team_id = tid
        self.team_id_offset = tid_off

        # Team name and byte-range
        try:
            name, ns, ne = self._extract_name()
        except Exception:
            name, ns, ne = "Unknown Team", 0, 0
        self.name = self._clean_extracted_text(name)
        self.name_start = ns
        self.name_end = ne

        # Stadium name and its byte-range (usually follows the team name)
        try:
            stadium, ss, se = self._extract_stadium()
        except Exception:
            stadium, ss, se = "", 0, 0
        self.stadium = self._clean_extracted_text(stadium)
        self.stadium_start = ss
        self.stadium_end = se

        # Additional team metadata often embedded in EQ team subrecords (heuristic parsing).
        self.full_club_name = None
        self.chairman = None
        self.shirt_sponsor = None
        self.kit_supplier = None
        try:
            self._extract_team_metadata_fields()
        except Exception:
            pass

        # Parsed stadium details (capacity, car park, pitch quality)
        try:
            cap, car, pitch = self._parse_stadium_details(self.stadium or "")
        except Exception:
            cap, car, pitch = None, None, None
        self.stadium_capacity = cap
        self.car_park = car
        self.pitch = pitch
        self._sync_stadium_detail_aliases()

        # League information (to be parsed from metadata)
        try:
            league = self._extract_league()
        except Exception:
            league = "Unknown League"
        self.league = league

    def _clean_extracted_text(self, text: str) -> str:
        """Normalize common parser artifacts while keeping conservative semantics."""
        if not text:
            return text
        cleaned = "".join(ch for ch in text if (" " <= ch <= "~")).strip()
        # Team/stadium extraction can preserve a leading delimiter 'a' artifact before a
        # capitalized phrase, e.g. 'aOld Trafford' or 'aBritannia Stadium'.
        if len(cleaned) >= 2 and cleaned[0] == 'a' and cleaned[1].isupper():
            cleaned = cleaned[1:]
        return cleaned

    def _iter_printable_runs(self):
        """Return printable ASCII runs from raw_data as (start, end, text)."""
        out = []
        try:
            data = bytes(self.raw_data)
            for m in re.finditer(rb'[\x20-\x7e]{3,100}', data):
                text = m.group().decode('latin-1', errors='ignore').strip()
                if text:
                    out.append((m.start(), m.end(), text))
        except Exception:
            return []
        return out

    def _normalize_meta_run(self, text: str) -> str:
        if not text:
            return ""
        cleaned = "".join(ch for ch in text if (" " <= ch <= "~")).replace("`", " ").strip()
        # Strip common delimiter-ish prefixes ending in 'a' before a capitalized payload.
        cleaned = re.sub(r'^[A-Za-z]{0,4}a(?=[A-Z0-9])', '', cleaned)
        cleaned = re.sub(r'^[^A-Za-z0-9]+', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def _trim_meta_tail_artifacts(self, text: str) -> str:
        """Trim common trailing junk chars from team metadata strings."""
        if not text:
            return text
        s = text.strip().rstrip('., ')
        low = s.lower()
        has_club_keyword = any(k in low for k in ("football club", "f. c", "f.c.", "club", "s.a.d"))
        if has_club_keyword:
            while len(s) > 4:
                last = s[-1]
                prev = s[-2] if len(s) >= 2 else ""
                # Common artifacts are a trailing digit/letter glued to an otherwise valid phrase.
                if last.isdigit():
                    s = s[:-1].rstrip('., ')
                    continue
                # Strip a single lowercase artifact after punctuation/space, e.g. "F. C.e"
                if last.islower() and not prev.islower():
                    s = s[:-1].rstrip('., ')
                    continue
                # Some decoded strings end with a single garbage lowercase suffix char (e.g. x).
                if last.islower() and prev.islower():
                    separator_chars = set('aioghijkmnpqruvwx')
                    valid_endings = {'ona', 'ivo', 'alo', 'ano', 'ino'}
                    if last in separator_chars and (len(s) < 4 or s[-3:].lower() not in valid_endings):
                        s = s[:-1].rstrip('., ')
                        continue
                if last.isupper() and prev.islower():
                    s = s[:-1].rstrip('., ')
                    continue
                break
        else:
            # Also trim a single common garbage suffix letter on shorter club labels (e.g. "Manchester Cityx").
            if len(s) > 4 and s[-1].islower() and s[-2].islower():
                separator_chars = set('aioghijkmnpqruvwx')
                if s[-1] in separator_chars:
                    s = s[:-1].rstrip('., ')
        return s

    def _looks_like_meta_text(self, text: str) -> bool:
        if not text:
            return False
        if len(text) < 4 or len(text) > 80:
            return False
        letters = sum(1 for ch in text if ch.isalpha())
        if letters < 3:
            return False
        if (letters / max(1, len(text))) < 0.45:
            return False
        return True

    def _extract_person_name_from_run(self, raw_text: str):
        if not raw_text:
            return None
        text = self._normalize_meta_run(raw_text)
        if not text:
            return None
        # Remove common delimiter residues before capitalized chunks so "aaauaSir X" -> "Sir X".
        text = re.sub(r'\b[a-z]{1,6}a(?=[A-Z])', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        low = text.lower()
        if any(k in low for k in ("stadium", "ground", "park", "lane", "football club", "club")):
            return None

        patterns = [
            r'\b(?:Sir|Mr|Mrs|Ms|Dr)\s+[A-Z][A-Za-z.\'-]+(?:\s+[A-Z][A-Za-z.\'-]+){0,5}\b',
            r'\b(?:[A-Z]\.?\s*){1,4}[A-Z][A-Za-z][A-Za-z.\'-]*(?:\s+[A-Z][A-Za-z.\'-]+){0,5}\b',
            r'\b[A-Z][a-z]+(?:\s+[A-Z][A-Za-z.\'-]+){1,5}\b',
        ]
        best = None
        for pat in patterns:
            for m in re.finditer(pat, text):
                cand = m.group(0).strip().rstrip('., ')
                if len(cand) < 4:
                    continue
                if best is None or len(cand) > len(best):
                    best = cand
        return best

    def _extract_brand_pair_from_run(self, raw_text: str):
        if not raw_text:
            return None
        text = self._normalize_meta_run(raw_text)
        if not text:
            return None
        low_text = text.lower()
        if any(k in low_text for k in ("football club", "stadium", "ground", "sir ", " mr ", " mrs ", " dr ")):
            return None

        def _brand_like(value: str) -> bool:
            v = self._trim_meta_tail_artifacts(value.strip())
            if not v:
                return False
            if any(k in v.lower() for k in ("football", "club", "stadium", "ground")):
                return False
            if not any(ch.isalpha() for ch in v):
                return False
            # reject all-lowercase and long person-like phrases
            if v.lower() == v:
                return False
            if len(v.split()) > 3:
                return False
            return True

        def _brand_clean(value: str) -> str:
            v = value.strip().strip('., ')
            v = re.sub(r'^[a-z]{1,6}(?=[A-Z])', '', v).strip()
            # Strip a single trailing digit/obvious punctuation artifact, but keep normal lowercase endings
            v = v.rstrip(' .,-')
            if v.endswith(tuple('0123456789')):
                v = v.rstrip('0123456789').rstrip(' .,-')
            return v

        # Common sponsor/supplier strings are joined by tiny delimiter fragments (da/ea/fa/ga/etc).
        m = re.search(r'([A-Za-z0-9&.\' -]{2,40}?)[a-z]a([A-Za-z0-9&.\' -]{2,40})', text)
        if m:
            left = _brand_clean(m.group(1))
            right = _brand_clean(m.group(2))
            if left and right and _brand_like(left) and _brand_like(right):
                if _brand_like(left) and _brand_like(right):
                    return left, right
        toks = re.findall(r'[A-Z][A-Z0-9&.\'-]{2,}', text)
        deny = {"F.C", "FC", "S.A.D", "S.A.D.", "CLUB", "STADIUM"}
        out = []
        for tok in toks:
            if tok in deny:
                continue
            if tok not in out:
                out.append(tok)
        if len(out) >= 2:
            return out[0], out[1]
        return None

    def _extract_club_name_candidate_from_run(self, raw_text: str):
        text = self._normalize_meta_run(raw_text)
        if not self._looks_like_meta_text(text):
            return None
        text = self._trim_meta_tail_artifacts(text)
        if not self._looks_like_meta_text(text):
            return None
        # Exclude obvious brand-only / coded chunks.
        if text.isupper() and " " not in text and len(text) <= 20:
            return None
        return text

    def _extract_team_metadata_fields(self):
        """Heuristically parse extra metadata from EQ team subrecords (additive only)."""
        self.full_club_name = None
        self.chairman = None
        self.shirt_sponsor = None
        self.kit_supplier = None
        runs = self._iter_printable_runs()
        if not runs:
            return

        # Prefer runs after the parsed stadium slice; fallback to all runs if unavailable.
        start_after = int(getattr(self, 'stadium_end', 0) or 0)
        post_runs = [(s, e, t) for (s, e, t) in runs if s >= start_after]
        if not post_runs:
            post_runs = runs

        team_name = (self.name or "").strip()
        stadium = (self.stadium or "").strip()

        club_name_idx = None
        best_keyword_club = None
        best_keyword_idx = None
        first_plausible_club = None
        first_plausible_idx = None

        for idx, (_s, _e, raw_text) in enumerate(post_runs[:12]):
            cand = self._extract_club_name_candidate_from_run(raw_text)
            if not cand:
                continue
            if cand in (team_name, stadium):
                continue
            low = cand.lower()
            if any(k in low for k in ("football club", "f. c", "f.c.", " club", "s.a.d")):
                best_keyword_club = cand
                best_keyword_idx = idx
                break
            if first_plausible_club is None:
                # Allow shorter club aliases like "Stoke City" even without club keywords.
                if re.search(r'[A-Za-z]', cand):
                    first_plausible_club = cand
                    first_plausible_idx = idx

        if best_keyword_club is not None:
            self.full_club_name = best_keyword_club
            club_name_idx = best_keyword_idx
        elif first_plausible_club is not None:
            self.full_club_name = first_plausible_club
            club_name_idx = first_plausible_idx

        # Chairman/president style person string usually follows club-name fields.
        person_start_idx = (club_name_idx + 1) if isinstance(club_name_idx, int) else 0
        chairman_idx = None
        for idx, (_s, _e, raw_text) in enumerate(post_runs[person_start_idx:person_start_idx + 10], start=person_start_idx):
            cand = self._extract_person_name_from_run(raw_text)
            if not cand:
                continue
            if cand in (team_name, stadium, self.full_club_name):
                continue
            self.chairman = cand
            chairman_idx = idx
            break

        # Sponsor + kit supplier are often stored as two uppercase brand tokens in one run.
        brand_start_idx = (chairman_idx + 1) if isinstance(chairman_idx, int) else person_start_idx
        for _s, _e, raw_text in post_runs[brand_start_idx:brand_start_idx + 10]:
            pair = self._extract_brand_pair_from_run(raw_text)
            if not pair:
                continue
            sponsor, supplier = pair
            # Ignore cases where we accidentally captured club acronyms from the full club name.
            if sponsor in {"RTA", "TVA"}:
                continue
            self.shirt_sponsor = sponsor
            self.kit_supplier = supplier
            break

        # Legacy-friendly aliases for downstream callers.
        try:
            self.sponsor = self.shirt_sponsor
        except Exception:
            pass
        try:
            self.kit_manufacturer = self.kit_supplier
        except Exception:
            pass

    def _extract_team_id(self):
        """Scan for plausible team ID (3000-5000 range) and return (value, offset)."""
        for i in range(0, len(self.raw_data) - 1, 2):
            if i + 2 <= len(self.raw_data):
                try:
                    val = struct.unpack_from("<H", self.raw_data, i)[0]
                except Exception:
                    continue
                if 3000 <= val <= 5000:
                    return val, i
        return 0, None

    def _extract_name(self):
        """Extract team name from team record data.
        
        Team records from EQ98030.FDI have structure:
        [separator: 0x61 0xdd 0x63] [prefix bytes] [TEAM NAME] [lowercase 'a' separator] [STADIUM/DATA]
        """
        try:
            data_bytes = bytes(self.raw_data)
            
            # Skip separator if present at start (3 bytes: 0x61 0xdd 0x63)
            start = 0
            if len(data_bytes) >= 3 and data_bytes[0:3] == bytes([0x61, 0xdd, 0x63]):
                start = 3
            
            # Skip prefix bytes until we find first uppercase letter
            # Prefix is typically like: 0x61 0x60 XX 0x61 or similar
            while start < len(data_bytes) and start < 20:
                if data_bytes[start] >= ord('A') and data_bytes[start] <= ord('Z'):
                    break
                start += 1
            
            if start >= len(data_bytes):
                return "Unknown Team", 0, 0
            
            # Find end of team name
            # Team names typically end with lowercase 'a' before stadium text
            # or when we hit the stadium name (next uppercase run)
            end = start
            for i in range(start, min(start + 60, len(data_bytes))):
                c = data_bytes[i]
                
                # Stop at certain separator patterns:
                # 1. Lowercase 'a' followed by uppercase (stadium name starts)
                if c == ord('a') and i > start + 5:
                    # Check if next char is uppercase (stadium name)
                    if i + 1 < len(data_bytes):
                        next_c = data_bytes[i + 1]
                        # Also check for common stadium prefixes
                        if (ord('A') <= next_c <= ord('Z')) or next_c in [ord('S'), ord('O'), ord('V')]:
                            end = i
                            break
                
                # Stop at non-printable characters
                if c < 32 or c > 126:
                    end = i
                    break
                
                end = i + 1
            
            if end > start:
                name_bytes = data_bytes[start:end]
                name = name_bytes.decode('latin1', errors='replace').strip()
                
                # Clean up: remove ONLY the final trailing single lowercase letter if it's a separator
                # Pattern: "Barcelonai" -> "Barcelona", "Athletic Clubh" -> "Athletic Club"
                # But preserve: "Barcelona" (already clean)
                if len(name) > 5 and name[-1].islower():
                    # Check if it looks like a separator (single letter after word)
                    last_char = name[-1]
                    
                    # If preceded by uppercase, space, or period: definitely a separator
                    # Examples: "F.|p", "Club|h", "Madrid|q"
                    if len(name) >= 2:
                        prev_char = name[-2]
                        if prev_char.isupper() or prev_char in ['.', ' ']:
                            # Remove just this one letter
                            name = name[:-1].strip()
                        elif prev_char.islower():
                            # It's part of a word - check if it's a common separator letter
                            # Common separators: single letters like i, o, g, h, j, k, m, n, p, q, r, u, v, x
                            # that wouldn't normally end a team name
                            # Preserve: s (plural), d (Madrid, United)
                            separator_chars = set('aioghijkmnpqruvwx')
                            if last_char in separator_chars:
                                # Additional check: Spanish/Italian team names often end in specific letters
                                # Keep if it's part of a valid ending
                                valid_endings = {'ona', 'ivo', 'alo', 'ano', 'ino'}  # Barcelona, Deportivo, etc.
                                if len(name) >= 4:
                                    last_three = name[-3:].lower()
                                    if last_three not in valid_endings:
                                        name = name[:-1].strip()
                
                # Additional cleanup: remove trailing dots, commas, spaces
                name = name.rstrip('., ')
                
                # Final validation
                if len(name) >= 3 and name[0].isupper() and any(c.isalpha() for c in name):
                    return name, start, end
            
            return "Unknown Team", 0, 0
            
        except Exception as e:
            logger.debug("TeamRecord._extract_name failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
            return "Parse Error", 0, 0

    def _find_name_start(self) -> int:
        """Helper to find name start offset; kept for compatibility with older callers."""
        try:
            return self.name_start or 0
        except Exception:
            return 0

    def _extract_stadium(self):
        """Attempt to locate a stadium name appearing after the team name.

        Heuristics:
        - Search for printable runs after the name_end
        - Prefer runs containing common stadium keywords (stadium, ground, park, lane, arena, road, centre)
        - Fallback: the first printable run after the team name
        """
        try:
            data = bytes(self.raw_data)
            start_search = self.name_end if getattr(self, 'name_end', None) else 0
            if start_search < 0:
                start_search = 0

            text_pattern = rb'[\x20-\x7e]{4,80}'
            # Search in the remainder of the data
            tail = data[start_search:]
            matches = list(re.finditer(text_pattern, tail))
            if not matches:
                return "", 0, 0

            # Look for stadium-like keywords
            stadium_keywords = ('stadium', 'ground', 'park', 'lane', 'field', 'arena', 'centre', 'center', 'stadio', 'road')
            for m in matches:
                text = m.group().decode('latin-1', errors='replace').strip()
                if not text:
                    continue
                lower = text.lower()
                if any(k in lower for k in stadium_keywords):
                    abs_start = start_search + m.start()
                    abs_end = start_search + m.end()
                    return text, abs_start, abs_end

            # Fallback to the first printable run after the name
            m = matches[0]
            text = m.group().decode('latin-1', errors='replace').strip()
            abs_start = start_search + m.start()
            abs_end = start_search + m.end()
            return text, abs_start, abs_end
        except Exception as e:
            logger.debug("TeamRecord._extract_stadium failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
            return "", 0, 0

    def _parse_stadium_details(self, text: str):
        """Parse capacity, car park and pitch quality from a stadium description string."""
        if not text:
            return None, None, None
        cap = None
        car = None
        pitch = None
        try:
            # CAPACITY: 32,786 seats
            import re as _re
            m = _re.search(r'CAPACITY[:\s]*([\d,]+)', text, flags=_re.IGNORECASE)
            if m:
                try:
                    cap = int(m.group(1).replace(',', ''))
                except Exception:
                    cap = None

            # CAR PARK: 2,000 spaces
            m2 = _re.search(r'CAR\s*PARK[:\s]*([\d,]+)', text, flags=_re.IGNORECASE)
            if m2:
                try:
                    car = int(m2.group(1).replace(',', ''))
                except Exception:
                    car = None

            # PITCH: GOOD / EXCELLENT / POOR
            m3 = _re.search(r'PITCH[:\s]*([A-Za-z]+)', text, flags=_re.IGNORECASE)
            if m3:
                pitch = m3.group(1).upper()
        except Exception:
            pass
        return cap, car, pitch

    def _extract_league(self):
        """Extract league information based on team_id ranges.
        
        Uses the league_definitions module to map team IDs to leagues.
        """
        if not hasattr(self, 'team_id') or self.team_id is None or self.team_id == 0:
            return "Unknown League"
        
        try:
            from app.league_definitions import get_team_league
            country, league_name = get_team_league(self.team_id)
            if country and league_name:
                return league_name
        except Exception:
            pass
        
        return "Unknown League"

    def _sync_stadium_detail_aliases(self):
        """Maintain legacy attribute names used by older GUI/export code paths."""
        try:
            self.capacity = int(self.stadium_capacity) if self.stadium_capacity is not None else 0
        except Exception:
            self.capacity = 0
        self.pitch_quality = (self.pitch or "UNKNOWN")
    
    def get_country(self) -> str:
        """Get the country this team belongs to."""
        try:
            from app.league_definitions import get_team_league
            country, _ = get_team_league(self.team_id)
            return country or "Unknown"
        except Exception:
            return "Unknown"

    def set_name(self, new_name: str):
        """Set new team name in raw_data (in-place when possible)."""
        if new_name is None:
            return bytes(self.raw_data)
        if len(new_name) > 60:
            new_name = new_name[:60]
        new_bytes = new_name.encode('latin-1', errors='replace')

        # Ensure name_start/name_end exist; recompute if needed
        if not getattr(self, 'name_start', None) or not getattr(self, 'name_end', None) or self.name_end <= self.name_start:
            # Recompute via _extract_name
            name, ns, ne = self._extract_name()
            self.name = name
            self.name_start = ns
            self.name_end = ne

        old_len = self.name_end - self.name_start if (self.name_end and self.name_start) else 0
        if old_len <= 0:
            # Append near end if no slot found
            self.raw_data.extend(new_bytes + b' ')
            self.name_start = len(self.raw_data) - len(new_bytes) - 1
            self.name_end = self.name_start + len(new_bytes)
        else:
            if len(new_bytes) <= old_len:
                padded = new_bytes + b' ' * (old_len - len(new_bytes))
                self.raw_data[self.name_start:self.name_start + old_len] = padded
                self.name_end = self.name_start + old_len
            else:
                # Expand in-place
                self.raw_data[self.name_start:self.name_end] = new_bytes
                self.name_end = self.name_start + len(new_bytes)

        self.name = new_name
        # Recompute stadium region after name changes
        self.stadium, self.stadium_start, self.stadium_end = self._extract_stadium()
        self.stadium = self._clean_extracted_text(self.stadium)
        try:
            self._extract_team_metadata_fields()
        except Exception:
            pass
        # Re-parse stadium details
        self.stadium_capacity, self.car_park, self.pitch = self._parse_stadium_details(self.stadium)
        self._sync_stadium_detail_aliases()
        return bytes(self.raw_data)

    def set_stadium_name(self, new_stadium: str):
        """Replace stadium text region (in-place if possible)."""
        if new_stadium is None:
            return bytes(self.raw_data)
        if len(new_stadium) > 120:
            new_stadium = new_stadium[:120]
        new_bytes = new_stadium.encode('latin-1', errors='replace')

        # Ensure stadium region exists; recompute if missing
        if not getattr(self, 'stadium_start', None) or not getattr(self, 'stadium_end', None) or self.stadium_end <= self.stadium_start:
            self.stadium, self.stadium_start, self.stadium_end = self._extract_stadium()

        old_len = (self.stadium_end - self.stadium_start) if (self.stadium_end and self.stadium_start) else 0
        if old_len <= 0:
            # Append after name_end if possible
            pos = self.name_end or len(self.raw_data)
            insert_at = pos
            # Insert a single space separator before stadium
            self.raw_data[insert_at:insert_at] = b' ' + new_bytes + b' '
            self.stadium_start = insert_at + 1
            self.stadium_end = self.stadium_start + len(new_bytes)
        else:
            if len(new_bytes) <= old_len:
                pad = b' ' * (old_len - len(new_bytes))
                self.raw_data[self.stadium_start:self.stadium_start + old_len] = new_bytes + pad
                self.stadium_end = self.stadium_start + old_len
            else:
                # Expand in-place by slice assignment
                self.raw_data[self.stadium_start:self.stadium_end] = new_bytes
                self.stadium_end = self.stadium_start + len(new_bytes)

        self.stadium = new_stadium
        try:
            self._extract_team_metadata_fields()
        except Exception:
            pass
        # Re-parse stadium details
        self.stadium_capacity, self.car_park, self.pitch = self._parse_stadium_details(self.stadium)
        self._sync_stadium_detail_aliases()
        return bytes(self.raw_data)

    def set_capacity(self, capacity: int):
        """Update stadium capacity metadata if present in stadium text; otherwise append it."""
        try:
            cap = int(capacity) if capacity is not None else None
        except Exception:
            cap = None
        if cap is None:
            return bytes(self.raw_data)

        # If stadium text contains CAPACITY, replace it; otherwise append a " CAPACITY: X" token
        s = self.stadium or ""
        import re as _re
        if _re.search(r'CAPACITY[:\s]*[\d,]+', s, flags=_re.IGNORECASE):
            s2 = _re.sub(r'CAPACITY[:\s]*[\d,]+', f'CAPACITY: {cap:,}', s, flags=_re.IGNORECASE)
        else:
            if s:
                s2 = f"{s}  CAPACITY: {cap:,}"
            else:
                s2 = f"CAPACITY: {cap:,}"
        self.set_stadium_name(s2)
        return bytes(self.raw_data)

    def set_car_park(self, spaces: int):
        """Update car park count in stadium text similarly to capacity."""
        try:
            n = int(spaces) if spaces is not None else None
        except Exception:
            n = None
        if n is None:
            return bytes(self.raw_data)

        s = self.stadium or ""
        import re as _re
        if _re.search(r'CAR\s*PARK[:\s]*[\d,]+', s, flags=_re.IGNORECASE):
            s2 = _re.sub(r'CAR\s*PARK[:\s]*[\d,]+', f'CAR PARK: {n:,}', s, flags=_re.IGNORECASE)
        else:
            if s:
                s2 = f"{s}  CAR PARK: {n:,}"
            else:
                s2 = f"CAR PARK: {n:,}"
        self.set_stadium_name(s2)
        return bytes(self.raw_data)

    def set_pitch(self, quality: str):
        """Set pitch quality in stadium text (GOOD / MEDIUM / POOR)."""
        q = (quality or "").strip().upper()
        if not q:
            return bytes(self.raw_data)
        s = self.stadium or ""
        import re as _re
        if _re.search(r'PITCH[:\s]*[A-Za-z]+', s, flags=_re.IGNORECASE):
            s2 = _re.sub(r'PITCH[:\s]*[A-Za-z]+', f'PITCH: {q}', s, flags=_re.IGNORECASE)
        else:
            if s:
                s2 = f"{s}  PITCH: {q}"
            else:
                s2 = f"PITCH: {q}"
        self.set_stadium_name(s2)
        return bytes(self.raw_data)

    def to_bytes(self) -> bytes:
        """Return decoded payload suitable for saving (no length-prefix)."""
        raw = bytearray(self.raw_data)
        # If we detected team_id position, write it back
        try:
            if getattr(self, 'team_id', None) is not None and getattr(self, 'team_id_offset', None) is not None:
                struct.pack_into("<H", raw, int(self.team_id_offset), int(self.team_id))
            else:
                # best-effort: write at start if there are at least 2 bytes
                if len(raw) >= 2 and getattr(self, 'team_id', None) is not None:
                    struct.pack_into("<H", raw, 0, int(self.team_id))
        except Exception:
            # best-effort only; don't fail serialization because of this
            pass
        return bytes(raw)


class CoachRecord:
    """Basic coach record parser (managers)"""
    def __init__(self, data: bytes, record_offset: int):
        self.raw_data = bytearray(data)
        self.record_offset = record_offset
        self.coach_id = self._extract_coach_id()
        self.given_name = ""
        self.surname = ""
        self.full_name = self._extract_name()

    def _extract_coach_id(self) -> int:
        """Extract coach ID, assume sequential or from header"""
        return 0

    def _extract_name(self) -> str:
        """Extract coach name using 32-bit XOR decode; fallback to regex-based parser if necessary."""
        try:
            inner_pos = 1
            given, c1 = self._decode_string_32bit(self.raw_data, inner_pos)
            if c1 > 0:
                inner_pos += c1
                surname, c2 = self._decode_string_32bit(self.raw_data, inner_pos)
                if c2 > 0:
                    self.given_name = given
                    self.surname = surname
                    return f"{given} {surname}".strip()
        except Exception as e:
            logger.debug("CoachRecord extraction failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
 
        # Fallback: try the lighter regex-based parser to extract names if structured decode fails
        try:
            from app.coach_models import parse_coaches_from_record as _parse
            coaches = _parse(bytes(self.raw_data))
            if coaches:
                c = coaches[0]
                try:
                    self.given_name = getattr(c, 'given_name', '')
                    self.surname = getattr(c, 'surname', '')
                    self.full_name = getattr(c, 'full_name', '') or f"{self.given_name} {self.surname}".strip()
                    return self.full_name
                except Exception:
                    # If coach dataclass doesn't match expected fields, fall through
                    pass
        except Exception as e:
            logger.debug("CoachRecord regex fallback failed at offset 0x%x: %s", getattr(self, 'record_offset', 0), e)
 
        return "Unknown Coach"

    def _decode_string_32bit(self, blob: bytes, offset: int) -> tuple[str, int]:
        """Decode inner 32-bit XOR string"""
        if offset + 2 > len(blob):
            return "", 0

        length = struct.unpack_from("<H", blob, offset)[0]
        if length > 500 or offset + 2 + length > len(blob):
            return "", 0

        encoded = blob[offset+2 : offset+2+length]
        decoded = bytearray()

        p = 0
        while p + 4 <= len(encoded):
            dword = struct.unpack_from("<I", encoded, p)[0]
            decoded.extend(struct.pack("<I", dword ^ 0x61616161))
            p += 4
        if p + 2 <= len(encoded):
            word = struct.unpack_from("<H", encoded, p)[0]
            decoded.extend(struct.pack("<H", word ^ 0x6161))
            p += 2
        if p < len(encoded):
            decoded.append(encoded[p] ^ 0x61)

        if b'\x00' in decoded:
            decoded = decoded[:decoded.index(b'\x00')]

        try:
            return bytes(decoded).decode('cp1252', errors='replace'), 2 + length
        except:
            return "", 2 + length

    def encode_string_32bit(self, text: str) -> bytes:
        """Encode a plain text string into the 32-bit-XOR entry format (length prefixed)."""
        raw = text.encode('cp1252')
        out = bytearray()
        p = 0
        while p + 4 <= len(raw):
            dword = struct.unpack_from("<I", raw, p)[0]
            out.extend(struct.pack("<I", dword ^ 0x61616161))
            p += 4
        if p + 2 <= len(raw):
            word = struct.unpack_from("<H", raw, p)[0]
            out.extend(struct.pack("<H", word ^ 0x6161))
            p += 2
        if p < len(raw):
            out.append(raw[p] ^ 0x61)
        return struct.pack("<H", len(out)) + bytes(out)

    def set_name(self, given_name: str, surname: str) -> bytes:
        """
        Replace the encoded given/surname pair stored after the initial header byte.
        This performs an in-place replacement of the old encoded blocks with newly encoded ones.
        The total decoded payload length may change; callers should use the returned bytes
        from to_bytes() for saving.
        """
        inner_pos = 1
        # Determine the existing consumed lengths so we can replace that slice
        _, c1 = self._decode_string_32bit(bytes(self.raw_data), inner_pos)
        _, c2 = self._decode_string_32bit(bytes(self.raw_data), inner_pos + c1)
        old_total = c1 + c2

        new_given = self.encode_string_32bit(given_name)
        new_surname = self.encode_string_32bit(surname)
        new_block = new_given + new_surname

        # Replace slice (may change total payload length)
        self.raw_data[inner_pos:inner_pos + old_total] = new_block

        self.given_name = given_name
        self.surname = surname
        self.full_name = f"{given_name} {surname}".strip()
        return bytes(self.raw_data)

    def to_bytes(self) -> bytes:
        """Return decoded payload suitable for saving (no length-prefix)."""
        return bytes(self.raw_data)
@dataclass
class PlayerRecord:
    """Player record structure from PM99 FDI files.
    
    Corresponds to the structure parsed by MANAGPRE.EXE.FUN_004afd80().
    """
    # Core identity
    record_id: int = 0
    given_name: str = ""
    surname: str = ""
    name: str = ""  # Full display name (compatibility with legacy code)
    
    # File structure fields (bytes 0-2)
    team_id: int = 0
    squad_number: int = 0
    
    # Codes and identifiers
    initial_char: int = ord('a')  # Single byte character
    initials: bytes = b'aaaaaa'  # 6-byte sequence
    nationality: int = 0
    position_primary: int = 0
    position_secondary: int = 0
    unknown_1c: int = 0
    
    # Birth data
    birth_day: int = 1
    birth_month: int = 1
    birth_year: int = 1975
    
    # Physical attributes
    height: int = 175  # cm
    weight: Optional[int] = None  # kg when present; parser-backed for indexed JUG payloads and legacy records with a dedicated marker-backed slot
    
    # Core skill attributes (10 skills, duplicated in two offset locations)
    skills: List[int] = field(default_factory=lambda: [50] * 10)
    
    # Extended fields (version >= 700)
    extended: List[int] = field(default_factory=lambda: [0] * 6)
    
    # Metadata
    region_code: int = 0x1e  # 30 = English
    version: int = 700
    
    # Optional/unknown blocks (preserved as raw bytes)
    contract_data: Optional[bytes] = None
    unknown_blocks: List[bytes] = field(default_factory=list)
    
    # Raw record data for serialization (preserves unknown fields)
    raw_data: Optional[bytes] = None
    # Modification flag used by GUI and saving paths
    modified: bool = False
    # Confidence score (0-100) for heuristics; lower = less certain. GUI can surface suppressed candidates.
    confidence: int = 100
    # Mark records that are low-confidence or suppressed by deduplication heuristics so the UI can hide/show them.
    suppressed: bool = False
    # Internal flag signalling that the raw name bytes need rebuilding before serialization.
    name_dirty: bool = field(default=False, init=False, repr=False)
    # Indexed suffix bytes adjacent to the confirmed metadata block. Preserved as raw decoded values for investigation.
    indexed_unknown_0: Optional[int] = field(default=None, init=False)
    indexed_unknown_1: Optional[int] = field(default=None, init=False)
    indexed_face_components: List[int] = field(default_factory=list, init=False)
    indexed_unknown_9: Optional[int] = field(default=None, init=False)
    indexed_unknown_10: Optional[int] = field(default=None, init=False)
    
    @classmethod
    def from_bytes(cls, data: bytes, offset: int, version: int = 700) -> 'PlayerRecord':
        """
        Parse a player record from XOR-decoded player record data.
        
        Uses the CORRECT parsing approach based on reverse engineering:
        - Team ID at bytes 0-1 (LE uint16)
        - Squad # at byte 2
        - Name at bytes 5+ (variable length, Latin-1)
        - Name-end marker: 0x61 0x61 0x61 0x61
        - Position at name_end + 7 (double-XOR)
        - Nationality at name_end + 8 (double-XOR)
        - DOB at name_end + 9,10,11 (day/month/year, double-XOR)
        - Height at name_end + 13 (double-XOR)
        - Indexed DMFIv1.0 JUG payloads also expose a second metadata block
          immediately after the visible name suffix; when that pattern validates,
          it overrides the conservative marker read and exposes weight
        - Attributes at FIXED offset from end: len-19 to len-7 (double-XOR)
        
        Args:
            data: XOR-decoded player record bytes (NOT the full file)
            offset: Record offset (used for error reporting)
            version: Database version
            
        Returns:
            PlayerRecord with all fields populated
        """
        try:
            # Extract team ID (bytes 0-1, little-endian)
            team_id = struct.unpack_from("<H", data, 0)[0]
            # Normalize embedded/garbled team IDs (legacy heuristic)
            if team_id > 5000:
                team_id = 0

            # Extract squad number (byte 2)
            squad_num = data[2]
            
            # Extract player name from bytes 5-45 (Latin-1 encoding)
            name = cls._extract_name(data)
            
            # Find name-end marker (0x61 0x61 0x61 0x61)
            name_end = cls._find_name_end(data)
            
            # Extract metadata fields using dynamic offsets from name_end
            weight = None
            indexed_unknown_0 = None
            indexed_unknown_1 = None
            indexed_face_components: List[int] = []
            indexed_unknown_9 = None
            indexed_unknown_10 = None
            if name_end is not None:
                # Position at name_end + 7 (with double-XOR)
                position = cls._extract_position(data, name_end)
                
                # Nationality at name_end + 8 (with double-XOR)
                nationality = data[name_end + 8] ^ 0x61 if (name_end + 8) < len(data) else 0
                
                # DOB at name_end + 9, 10, 11 (day/month/year with double-XOR)
                birth_day = data[name_end + 9] ^ 0x61 if (name_end + 9) < len(data) else 1
                birth_month = data[name_end + 10] ^ 0x61 if (name_end + 10) < len(data) else 1
                
                if (name_end + 12) < len(data):
                    y0 = data[name_end + 11] ^ 0x61
                    y1 = data[name_end + 12] ^ 0x61
                    birth_year = struct.unpack_from("<H", bytes([y0, y1]), 0)[0]
                else:
                    birth_year = 1975
                
                # Height at name_end + 13 (with double-XOR)
                height = data[name_end + 13] ^ 0x61 if (name_end + 13) < len(data) else 175
                weight = cls._extract_legacy_marker_weight(data, name_end)
            else:
                # Fallback if no name-end marker found
                position = 0
                nationality = 0
                birth_day = 1
                birth_month = 1
                birth_year = 1975
                height = 175

            indexed_meta = cls._extract_indexed_suffix_metadata(data, name)
            if indexed_meta is not None:
                position = indexed_meta["position"]
                nationality = indexed_meta["nationality"]
                birth_day = indexed_meta["birth_day"]
                birth_month = indexed_meta["birth_month"]
                birth_year = indexed_meta["birth_year"]
                height = indexed_meta["height"]
                weight = indexed_meta["weight"]
                indexed_unknown_0 = indexed_meta["indexed_unknown_0"]
                indexed_unknown_1 = indexed_meta["indexed_unknown_1"]
                indexed_face_components = indexed_meta["face_components"]
                indexed_unknown_9 = indexed_meta["indexed_unknown_9"]
                indexed_unknown_10 = indexed_meta["indexed_unknown_10"]
            
            # Extract attributes from FIXED offset from end (last 12 bytes with double-XOR)
            skills = []
            attr_start = len(data) - 19
            attr_end = len(data) - 7
            if attr_start >= 0 and attr_end <= len(data):
                for i in range(attr_start, attr_end):
                    if i < len(data):
                        attr_val = data[i] ^ 0x61
                        skills.append(attr_val)
            
            # Pad skills to 12 if needed (legacy records include up to 12 attributes)
            while len(skills) < 12:
                skills.append(50)
            
            # Extract given name and surname from full name
            name_parts = name.split(maxsplit=1)
            given_name = name_parts[0] if len(name_parts) > 0 else "Unknown"
            surname = name_parts[1] if len(name_parts) > 1 else ""
            
            # Validate birth year
            if birth_year < 1900 or birth_year > 1999:
                birth_year = 1975
            
            # Validate height
            if height < 150 or height > 250:
                height = 175
            
            # Construct instance from parsed fields. Preserve raw_data but ensure
            # encoded metadata bytes exist in raw_data for discoverability and tests.
            extras = skills[10:12]
            extended_list = [0] * 6
            for i, v in enumerate(extras):
                extended_list[i] = v

            rec = cls(
                record_id=0,  # Set externally
                given_name=given_name,
                surname=surname,
                name=name,
                team_id=team_id,
                squad_number=squad_num,
                initial_char=ord('a'),
                initials=b'aaaaaa',
                nationality=nationality,
                position_primary=position,
                position_secondary=0,
                unknown_1c=0,
                birth_day=birth_day,
                birth_month=birth_month,
                birth_year=birth_year,
                height=height,
                weight=weight,
                skills=skills[:10],
                extended=extended_list,
                region_code=0x1e,
                version=version,
                contract_data=None,
                unknown_blocks=[],
                raw_data=data  # Store original record for serialization (may be patched below)
            )
            try:
                rec.nationality_id = nationality
            except Exception:
                pass
            rec.indexed_unknown_0 = indexed_unknown_0
            rec.indexed_unknown_1 = indexed_unknown_1
            rec.indexed_face_components = list(indexed_face_components)
            rec.indexed_unknown_9 = indexed_unknown_9
            rec.indexed_unknown_10 = indexed_unknown_10

            # If a name-end marker was found, ensure encoded metadata bytes are present
            # in the stored raw_data so tests and downstream consumers can inspect them.
            if name_end is not None:
                try:
                    raw = bytearray(rec.raw_data if rec.raw_data is not None else data)
                    real_name_end = PlayerRecord._find_name_end_in_data(bytes(raw))
                    if real_name_end is None:
                        real_name_end = name_end

                    pos_off = real_name_end + 7
                    nat_off = real_name_end + 8
                    day_off = real_name_end + 9
                    month_off = real_name_end + 10
                    year_off = real_name_end + 11
                    height_off = real_name_end + 13

                    patched = False

                    # Helper to safely write a single byte
                    def _write_byte_if_needed(buf, idx, val):
                        nonlocal patched
                        if 0 <= idx < len(buf) and buf[idx] != val:
                            buf[idx] = val
                            patched = True

                    # Normalize parsed values and choose safe defaults when parsed values are suspicious.
                    pos_val = position if 0 <= position <= 3 else 0
                    nat_val = nationality if 0 <= nationality <= 255 else 0
                    day_val = birth_day if 1 <= birth_day <= 31 else 1
                    month_val = birth_month if 1 <= birth_month <= 12 else 1
                    year_val = birth_year if 1900 <= birth_year <= 1999 else 1975
                    height_val = height if 50 <= height <= 250 else 175

                    # Write encoded (XOR'd) bytes for each metadata field.
                    _write_byte_if_needed(raw, pos_off, (pos_val ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, nat_off, (nat_val ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, day_off, (day_val ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, month_off, (month_val ^ 0x61) & 0xFF)
                    if year_off + 1 < len(raw):
                        yb = struct.pack("<H", year_val)
                        _write_byte_if_needed(raw, year_off, (yb[0] ^ 0x61) & 0xFF)
                        _write_byte_if_needed(raw, year_off + 1, (yb[1] ^ 0x61) & 0xFF)
                    _write_byte_if_needed(raw, height_off, (height_val ^ 0x61) & 0xFF)

                    if patched:
                        rec.raw_data = bytes(raw)
                except Exception:
                    # If patching fails for any reason, keep original raw_data unchanged
                    pass

            rec.name_dirty = False
            return rec
            
        except Exception as e:
            logger.debug("Parse error at offset 0x%x: %s", offset, e)
            return cls(
                record_id=0,
                given_name="Parse Error",
                surname="",
                name="Parse Error",
                version=version,
                raw_data=data  # Store even on error for safe serialization
            )
    
    @staticmethod
    def _extract_name(data: bytes) -> str:
        """Extract player name from two length-prefixed XOR-encoded strings.
        
        Format: [uint16 len1][XOR-encoded given name][uint16 len2][XOR-encoded surname]
        """
        from app.xor import read_string
        import struct
        
        try:
            # Names start at byte 5 (after team_id and squad_number)
            pos = 5
            
            # Read first string (given name)
            if pos + 2 > len(data):
                return "Parse Error"
            
            given_name, consumed1 = read_string(data, pos)
            pos += consumed1
            
            # Read second string (surname)
            if pos + 2 > len(data):
                # Only got given name
                return given_name if given_name else "Unknown Player"
            
            surname, consumed2 = read_string(data, pos)
            
            # Combine names
            full_name = f"{given_name} {surname}".strip()
            
            # Validate we got something reasonable
            if len(full_name) >= 3:
                return full_name
            
            return "Unknown Player"
            
        except Exception as e:
            logger.debug(f"Name extraction error: {e}")
            # Fallback to old parsing method for backwards compatibility
            try:
                import re
                name_region = data[5:45]
                text = name_region.decode('latin-1', errors='ignore')
                
                # Simple pattern matching as fallback
                patterns = [
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ]{3,20})',
                    r'([A-ZÀ-ÿ][a-zà-ÿ]{2,15})\s+([A-ZÀ-ÿ][a-zà-ÿ]{3,20})'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        return f"{match.group(1)} {match.group(2)}".strip()
                
                return "Unknown Player"
            except:
                return "Parse Error"
    
    @staticmethod
    def _find_name_end(data: bytes) -> Optional[int]:
        """Find the 'aaaa' (0x61 0x61 0x61 0x61) name-end marker."""
        search_end = max(0, min(60, len(data) - 4))
        for start, stop in ((20, search_end), (5, min(20, search_end))):
            for i in range(start, stop):
                if data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                    return i
        return None
    
    @staticmethod
    def _extract_position(data: bytes, name_end: int) -> int:
        """Extract position using dynamic offset from name-end marker."""
        # Try offset +7 first, then +8 as fallback
        attr_limit = len(data) - 19
        for delta in (7, 8):
            pos_offset = name_end + delta
            if pos_offset < attr_limit:
                pos_value = data[pos_offset] ^ 0x61  # Double-XOR
                if 0 <= pos_value <= 3:
                    return pos_value
        return 0

    @staticmethod
    def _find_legacy_weight_offset(data: bytes, name_end: Optional[int] = None) -> Optional[int]:
        """Return the legacy marker-backed weight offset when a dedicated slot exists."""
        if name_end is None:
            name_end = PlayerRecord._find_name_end(data)
        if name_end is None:
            return None

        attr_start = len(data) - 19
        weight_offset = name_end + 14
        if weight_offset >= len(data) or weight_offset >= attr_start:
            return None
        return weight_offset

    @staticmethod
    def _extract_legacy_marker_weight(data: bytes, name_end: Optional[int] = None) -> Optional[int]:
        """Extract a legacy marker-backed weight byte when the slot validates."""
        weight_offset = PlayerRecord._find_legacy_weight_offset(data, name_end)
        if weight_offset is None:
            return None

        weight = data[weight_offset] ^ 0x61
        if not (40 <= weight <= 140):
            return None
        return weight

    @staticmethod
    def _find_indexed_suffix_anchor(data: bytes, parsed_name: str) -> Optional[int]:
        """Return the indexed JUG suffix-metadata anchor when the payload shape matches."""
        if len(data) < 24 or not parsed_name:
            return None
        if data[2:5] != bytes([0xDD, 0x63, 0x61]):
            return None

        needle = parsed_name.encode("latin-1", errors="ignore")
        if not needle:
            return None

        pos = data.find(needle)
        if pos < 0 or pos > 80:
            return None

        anchor = pos + len(needle)
        while anchor < len(data) and 0x41 <= data[anchor] <= 0x5A:
            anchor += 1

        if anchor + 18 > len(data):
            return None

        return anchor

    @staticmethod
    def _extract_indexed_suffix_metadata(data: bytes, parsed_name: str):
        """Extract richer metadata from indexed DMFIv1.0 JUG payloads.

        These payloads carry a second metadata block after the visible name
        suffix. The current parser's `aaaa` anchor is not consistently present
        there, so use the name suffix as an anchor when the indexed header
        signature matches and the decoded values are internally consistent.
        """
        anchor = PlayerRecord._find_indexed_suffix_anchor(data, parsed_name)
        if anchor is None:
            return None

        indexed_unknown_0 = data[anchor] ^ 0x61
        indexed_unknown_1 = data[anchor + 1] ^ 0x61

        face_components: List[int] = []
        for i in range(6):
            raw_value = data[anchor + 2 + i] ^ 0x61
            if 1 <= raw_value <= 18:
                face_components.append(raw_value - 1)
            else:
                break

        nationality = data[anchor + 8] ^ 0x61
        indexed_unknown_9 = data[anchor + 9] ^ 0x61
        indexed_unknown_10 = data[anchor + 10] ^ 0x61
        position = data[anchor + 11] ^ 0x61
        birth_day = data[anchor + 12] ^ 0x61
        birth_month = data[anchor + 13] ^ 0x61
        birth_year = (data[anchor + 14] ^ 0x61) | ((data[anchor + 15] ^ 0x61) << 8)
        height = data[anchor + 16] ^ 0x61
        weight = data[anchor + 17] ^ 0x61

        if not (0 <= position <= 3):
            return None
        if not (1 <= birth_day <= 31 and 1 <= birth_month <= 12):
            return None
        if not (1900 <= birth_year <= 1999):
            return None
        if not (150 <= height <= 250):
            return None
        if not (40 <= weight <= 140):
            return None

        return {
            "indexed_unknown_0": indexed_unknown_0,
            "indexed_unknown_1": indexed_unknown_1,
            "face_components": face_components,
            "nationality": nationality,
            "indexed_unknown_9": indexed_unknown_9,
            "indexed_unknown_10": indexed_unknown_10,
            "position": position,
            "birth_day": birth_day,
            "birth_month": birth_month,
            "birth_year": birth_year,
            "height": height,
            "weight": weight,
        }

    @staticmethod
    def _extract_indexed_post_weight_byte(data: bytes, parsed_name: str) -> Optional[int]:
        """Return the decoded byte that FUN_0043d170 stores at [player + 0x48].

        This is the single encoded byte that appears immediately after the confirmed
        indexed suffix metadata block (through weight) and immediately before the
        parser advances into the three variable-length string blocks.
        """
        anchor = PlayerRecord._find_indexed_suffix_anchor(data, parsed_name)
        if anchor is None:
            return None
        if PlayerRecord._extract_indexed_suffix_metadata(data, parsed_name) is None:
            return None
        byte_offset = anchor + 18
        if not (0 <= byte_offset < len(data)):
            return None
        return data[byte_offset] ^ 0x61

    @staticmethod
    def _analyze_indexed_tail_layout(data: bytes, parsed_name: str):
        """Locate the indexed tail split between the final variable block and fixed trailer.

        Current DBASEPRE.EXE analysis strongly suggests the indexed player parser consumes:
        - 1 encoded byte after the suffix metadata (stored at [player + 0x48])
        - 3 XOR-length-prefixed strings
        - 7 more XOR-length-prefixed blocks
        - then a fixed 10-byte trailer skip

        On records that match that layout, the first three trailing attribute bytes live in the
        payload of the final length-prefixed block, while the remaining nine live in the fixed
        trailer immediately before the trailing padding.
        """
        anchor = PlayerRecord._find_indexed_suffix_anchor(data, parsed_name)
        if anchor is None:
            return None

        cursor = anchor + 18
        if cursor >= len(data):
            return None
        cursor += 1

        for _ in range(10):
            if cursor + 1 >= len(data):
                return None
            seg_len = (data[cursor] ^ 0x61) | ((data[cursor + 1] ^ 0x61) << 8)
            cursor += 2 + seg_len
            if cursor > len(data):
                return None

        attr_start = len(data) - 19
        attr_end = len(data) - 7
        before_skip = cursor
        after_skip = cursor + 10

        return {
            "final_block_cutoff": before_skip,
            "fixed_skip_end": after_skip,
            "attribute_start": attr_start,
            "attribute_end": attr_end,
            "layout_matches_expected": (
                before_skip == (attr_start + 3)
                and after_skip == (len(data) - 6)
            ),
        }

    @staticmethod
    def _extract_indexed_post_attribute_byte(data: bytes, parsed_name: str) -> Optional[int]:
        """Return the decoded post-attribute byte that DBASEPRE stores at [player + 0x6E]."""
        layout = PlayerRecord._analyze_indexed_tail_layout(data, parsed_name)
        if not layout or not bool(layout.get("layout_matches_expected")):
            return None
        byte_offset = int(layout.get("attribute_end", -1))
        if not (0 <= byte_offset < len(data)):
            return None
        return data[byte_offset] ^ 0x61

    @staticmethod
    def _extract_indexed_post_attribute_sidecar_byte(data: bytes, parsed_name: str) -> Optional[int]:
        """Return the decoded post-attribute byte that DBASEPRE stores at [player + 0x6F]."""
        layout = PlayerRecord._analyze_indexed_tail_layout(data, parsed_name)
        if not layout or not bool(layout.get("layout_matches_expected")):
            return None
        byte_offset = int(layout.get("fixed_skip_end", -1))
        if not (0 <= byte_offset < len(data)):
            return None
        return data[byte_offset] ^ 0x61

    def to_bytes(self) -> bytes:
        """
        Serialize player record to an in-file decoded payload (XOR-decoded, no length prefix).

        This method returns the raw decoded record bytes suitable for XOR encoding
        and length-prefixing by app.xor.encode_entry() or by the file_writer.
        If the instance was created via from_bytes() and raw_data is present we base the serialization on the
        original structure (preserving unknown fields). Otherwise we construct
        a reasonable canonical record from the dataclass fields.
        """
        # Build XOR-decoded payload first (decoded = in-file decoded record)
        if self.raw_data is not None:
            if getattr(self, 'name_dirty', False):
                self._rebuild_name_region()

            data = bytearray(self.raw_data)

            # Update team ID (bytes 0-1, little-endian)
            struct.pack_into("<H", data, 0, self.team_id)

            # Update squad number (byte 2)
            data[2] = self.squad_number

            # Compute attribute start limit to avoid overwriting attributes
            attr_start = len(data) - 19

            # Find name-end marker to write metadata back
            name_end = self._find_name_end_in_data(data)

            if name_end is not None:
                # Position (name_end + 7, double-XOR)
                pos_offset = name_end + 7
                if pos_offset < attr_start and 0 <= self.position_primary <= 3:
                    data[pos_offset] = self.position_primary ^ 0x61

                # Nationality (name_end + 8, double-XOR)
                nat_offset = name_end + 8
                if nat_offset < attr_start and 0 <= self.nationality <= 255:
                    data[nat_offset] = self.nationality ^ 0x61

                # DOB: day/month/year (name_end + 9,10,11,12 - year is 2 bytes LE, double-XOR)
                day_offset = name_end + 9
                month_offset = name_end + 10
                year_offset = name_end + 11
                if (year_offset + 1) < attr_start:
                    data[day_offset] = self.birth_day ^ 0x61
                    data[month_offset] = self.birth_month ^ 0x61
                    year_bytes = struct.pack("<H", self.birth_year)
                    data[year_offset] = year_bytes[0] ^ 0x61
                    data[year_offset + 1] = year_bytes[1] ^ 0x61

                # Height (name_end + 13, double-XOR)
                height_offset = name_end + 13
                if height_offset < attr_start and 50 <= self.height <= 250:
                    data[height_offset] = self.height ^ 0x61

                # Legacy weight slot (name_end + 14) when it still lands before the
                # trailing attribute window.
                legacy_weight_offset = self._find_legacy_weight_offset(data, name_end)
                if legacy_weight_offset is not None and self.weight is not None and 40 <= self.weight <= 140:
                    data[legacy_weight_offset] = self.weight ^ 0x61

            indexed_name = (self.name or f"{self.given_name} {self.surname}".strip()).strip()
            indexed_anchor = self._find_indexed_suffix_anchor(bytes(data), indexed_name)
            if indexed_anchor is not None:
                if 0 <= self.nationality <= 255:
                    data[indexed_anchor + 8] = self.nationality ^ 0x61
                if 0 <= self.position_primary <= 3:
                    data[indexed_anchor + 11] = self.position_primary ^ 0x61
                if 1 <= self.birth_day <= 31:
                    data[indexed_anchor + 12] = self.birth_day ^ 0x61
                if 1 <= self.birth_month <= 12:
                    data[indexed_anchor + 13] = self.birth_month ^ 0x61
                if 1900 <= self.birth_year <= 1999:
                    year_bytes = struct.pack("<H", self.birth_year)
                    data[indexed_anchor + 14] = year_bytes[0] ^ 0x61
                    data[indexed_anchor + 15] = year_bytes[1] ^ 0x61
                if 150 <= self.height <= 250:
                    data[indexed_anchor + 16] = self.height ^ 0x61
                if self.weight is not None and 40 <= self.weight <= 140:
                    data[indexed_anchor + 17] = self.weight ^ 0x61

            # Update attributes (double-XOR) - fixed offset from end
            attr_end = len(data) - 7
            for i, attr_val in enumerate(list(self.skills)[:12]):  # Max 12 attributes
                offset = attr_start + i
                if 0 <= offset < attr_end and 0 <= attr_val <= 100:
                    data[offset] = attr_val ^ 0x61

            decoded = bytes(data)
            self.raw_data = decoded
        else:
            # Construct a canonical decoded record from fields (sized so attributes align).
            from app.xor import write_string
            
            header = struct.pack("<H", self.team_id) + bytes([self.squad_number]) + b'\x00\x00'

            # Encode names as two separate length-prefixed XOR strings (matches game format)
            given = (self.given_name or "Unknown").strip()
            surname = (self.surname or "Player").strip()
            
            given_encoded = write_string(given)
            surname_encoded = write_string(surname)

            # Metadata anchor + placeholder window (position, nationality, DOB, height, etc.).
            # The current conservative write path keys off the leading 'aaaa' marker.
            metadata = (b'\x61' * 4) + (b'\x00' * 10)

            # Attributes: take up to 12, pad to 12, XOR encode
            attrs = list(self.skills)[:12]
            while len(attrs) < 12:
                attrs.append(50)
            attr_encoded = bytes([a ^ 0x61 for a in attrs])

            # Build complete record
            core = header + given_encoded + surname_encoded + metadata + attr_encoded
            
            # Add trailing padding to ensure minimum size
            trailing = b'\x00' * 7
            decoded = core + trailing

        # If this instance was created programmatically (no raw_data) we return a fully-encoded
        # FDI entry (length-prefixed + XOR) because some callers/tests construct files by
        # concatenating the per-record entries returned by to_bytes().
        # If raw_data exists (record read from file) return the decoded payload (no length-prefix).
        if self.raw_data is None:
            return encode_entry(decoded)
        return decoded

    def _update_full_name(self):
        """Synchronise the legacy `name` field with given + surname."""
        self.name = f"{self.given_name} {self.surname}".strip()

    def _mark_name_dirty(self):
        """Mark the record so the raw name bytes are rebuilt on next serialization."""
        self.modified = True
        self.name_dirty = True

    def _rebuild_name_region(self):
        """Rebuild the raw_data name region ensuring metadata/attributes remain aligned.
 
        This implementation stores a plain printable name run (e.g. "Given SURNAME")
        while preserving the original metadata/attribute tail where possible.
        It keeps the decoded record length stable to avoid unsafe rewrites.
        """
        if self.raw_data is None:
            self.name_dirty = False
            return
 
        data = bytearray(self.raw_data)
 
        # Name region typically starts at byte 5
        name_start = 5
        # Attributes live at the tail: len(data) - 19 .. len(data) - 7
        attr_start = len(data) - 19 if len(data) >= 19 else len(data)
 
        marker = bytes([0x61, 0x61, 0x61, 0x61])

        # Find an existing marker anywhere in the pre-attribute region (not just 20..60).
        marker_pos = None
        for i in range(name_start, max(name_start, attr_start - 3)):
            if data[i:i+4] == marker:
                marker_pos = i
                break

        # Try to parse the legacy two-string layout conservatively; reject absurd lengths.
        parsed_names_end = None
        try:
            pos = name_start
            for _ in range(2):
                if pos + 2 > attr_start:
                    raise ValueError("name length prefix out of range")
                seg_len = struct.unpack_from("<H", data, pos)[0]
                if seg_len < 0 or seg_len > 64 or pos + 2 + seg_len > attr_start:
                    raise ValueError("implausible name segment length")
                pos += 2 + seg_len
            parsed_names_end = pos
        except Exception:
            parsed_names_end = None

        if marker_pos is not None and marker_pos < attr_start:
            old_names_end = marker_pos
            metadata_start = min(attr_start, marker_pos + 4)
            keep_marker = True
        elif parsed_names_end is not None:
            old_names_end = parsed_names_end
            metadata_start = parsed_names_end
            keep_marker = False
        else:
            # Unknown layout (common in scanner-synthesized/minimal records): treat the
            # whole pre-attribute region as name space and preserve only the attribute tail.
            old_names_end = attr_start
            metadata_start = attr_start
            keep_marker = False

        # Preserve existing metadata and attributes regions exactly to keep record size stable.
        metadata_block = data[metadata_start:attr_start]
        attributes_block = data[attr_start:]
 
        header = data[:name_start]
 
        # Build a plain printable name run preserving caller-provided case.
        given = (self.given_name or "").strip()
        surname = (self.surname or "").strip()
        if given:
            full_name = f"{given} {surname}".strip()
        else:
            full_name = surname or ""
 
        # Encode as Latin-1 printable run
        name_bytes = full_name.encode("latin-1", errors="replace")
 
        fixed_tail = len(header) + len(metadata_block) + len(attributes_block) + (4 if keep_marker else 0)
        target_len = max(0, len(data) - fixed_tail)
 
        if len(name_bytes) > target_len:
            # If name would overflow target space, truncate surname to fit while preserving given name
            given_b = given.encode("latin-1", errors="replace")
            sep = b" "
            allowed_for_surname = target_len - len(given_b) - len(sep)
            if allowed_for_surname <= 0:
                # Fallback: take first target_len bytes
                name_bytes = name_bytes[:target_len]
            else:
                surname_b = surname.encode("latin-1", errors="replace")[:allowed_for_surname]
                name_bytes = given_b + sep + surname_b
        else:
            # Pad with spaces to preserve overall record length.
            name_bytes = name_bytes + b" " * (target_len - len(name_bytes))
 
        # Construct new decoded payload preserving total length.
        new_data = bytearray()
        new_data += header
        new_data += name_bytes
        if keep_marker:
            new_data += marker
        new_data += metadata_block
        new_data += attributes_block

        # Final length guard: trim/pad the name region if heuristics drifted.
        if len(new_data) != len(data):
            delta = len(data) - len(new_data)
            if delta > 0:
                # Grow name region with spaces to keep record size stable.
                insert_at = len(header) + len(name_bytes)
                new_data[insert_at:insert_at] = b" " * delta
            elif delta < 0:
                # Trim from the padded end of the name region first.
                trim = min(-delta, len(name_bytes))
                if trim:
                    start = len(header) + max(0, len(name_bytes) - trim)
                    del new_data[start:start + trim]
            if len(new_data) != len(data):
                new_data = new_data[:len(data)] + (b"\x00" * max(0, len(data) - len(new_data)))

        self.raw_data = bytes(new_data)
        self.name_dirty = False

    @staticmethod
    def _find_name_end_in_data(data: bytes) -> Optional[int]:
        """Find the 'aaaa' (0x61 0x61 0x61 0x61) name-end marker in data."""
        search_end = max(0, min(60, len(data) - 4))
        for start, stop in ((20, search_end), (5, min(20, search_end))):
            for i in range(start, stop):
                if data[i:i+4] == bytes([0x61, 0x61, 0x61, 0x61]):
                    return i
        return None

    # Compatibility and mutator helpers used by GUI and scripts
    @property
    def attributes(self) -> List[int]:
        """Return a 12-element attributes list (compat with legacy code).

        This returns exactly 12 values: first 10 primary skills then up to 2
        extra attributes sourced from the `extended` area (legacy storage).
        """
        attrs = list(self.skills) if self.skills is not None else []
        # Ensure primary skills length is 10
        while len(attrs) < 10:
            attrs.append(50)
        # Append up to two extras from extended (legacy storage)
        extras = list(self.extended) if getattr(self, 'extended', None) else []
        if extras:
            attrs.extend(extras[:2])
        # Pad to 12 with default 50
        while len(attrs) < 12:
            attrs.append(50)
        # Trim any excess to ensure exactly 12 elements
        return attrs[:12]

    @attributes.setter
    def attributes(self, vals: List[int]):
        """Set attributes from a 12-element list (or shorter)."""
        if not isinstance(vals, (list, tuple)):
            raise ValueError("attributes must be a list or tuple")
        vals = list(vals)
        # Ensure minimum length of 10 for skills storage
        while len(vals) < 10:
            vals.append(50)
        self.skills = vals[:10]
        # Save up to 2 extras into extended area (maintain existing extended length)
        extras = vals[10:12]
        if extras:
            if self.extended is None:
                # initialize extended with sensible size (6) to preserve indexing used elsewhere
                self.extended = [0] * 6
            # write extras into the first two positions of extended
            for i, v in enumerate(extras):
                if i < len(self.extended):
                    self.extended[i] = v
                else:
                    self.extended.append(v)
        self.modified = True

    def set_attribute(self, index: int, value: int):
        """Set a single attribute by index (0..11)."""
        if not (0 <= index <= 11):
            raise ValueError("Attribute index must be 0-11")
        if not (0 <= value <= 100):
            raise ValueError("Attribute value must be 0-100")
        if index < 10:
            # primary skills region
            if len(self.skills) < 10:
                while len(self.skills) < 10:
                    self.skills.append(50)
            self.skills[index] = value
        else:
            # secondary/extended region
            ext_idx = index - 10
            if self.extended is None:
                self.extended = [0] * 6
            if ext_idx >= len(self.extended):
                # expand if necessary
                while len(self.extended) <= ext_idx:
                    self.extended.append(0)
            self.extended[ext_idx] = value
        self.modified = True

    def set_team_id(self, team_id: int):
        """Set team ID (0-65535)."""
        if not (0 <= team_id <= 65535):
            raise ValueError("Team ID must be 0-65535")
        self.team_id = team_id
        self.modified = True

    def set_squad_number(self, number: int):
        """Set squad number (0-255)."""
        if not (0 <= number <= 255):
            raise ValueError("Squad number must be 0-255")
        self.squad_number = number
        self.modified = True

    def get_position_name(self) -> str:
        """Convert position code to human name."""
        positions = {0: "Goalkeeper", 1: "Defender", 2: "Midfielder", 3: "Forward"}
        return positions.get(getattr(self, 'position_primary', getattr(self, 'position', 0)), f"Unknown ({getattr(self,'position_primary',0)})")

    def set_position(self, pos_code: int):
        """Set player position (0-3)."""
        if not (0 <= pos_code <= 3):
            raise ValueError("Position must be 0-3")
        self.position_primary = pos_code
        self.modified = True
    
    def set_given_name(self, new_name: str):
        """Set player's given name (first name).

        Args:
            new_name: New given name (1-12 characters, validated by game)
            
        Raises:
            ValueError: If name is empty or too long
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Given name cannot be empty")
        if len(new_name) > 12:
            raise ValueError("Given name too long (max 12 characters)")

        self.given_name = new_name
        self._update_full_name()
        self._mark_name_dirty()
    
    def set_surname(self, new_name: str):
        """Set player's surname (last name).
        
        Args:
            new_name: New surname (1-12 characters, validated by game)
            
        Raises:
            ValueError: If name is empty or too long
        """
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Surname cannot be empty")
        if len(new_name) > 12:
            raise ValueError("Surname too long (max 12 characters)")

        self.surname = new_name
        self._update_full_name()
        self._mark_name_dirty()
    
    def set_name(self, full_name: str):
        """Set player's full name (splits into given name and surname).
        
        Args:
            full_name: Full name in format "Given Surname"
            
        Raises:
            ValueError: If name format is invalid
        """
        full_name = full_name.strip()
        if not full_name:
            raise ValueError("Name cannot be empty")
        
        parts = full_name.split(maxsplit=1)
        if len(parts) < 2:
            raise ValueError("Name must contain both given name and surname")
        
        given, surname = parts[0], parts[1]
        self.given_name = given.strip()
        self.surname = surname.strip()
        self._update_full_name()
        self._mark_name_dirty()

    def set_nationality(self, nat_id: int):
        """Set nationality ID (0-255)."""
        if not (0 <= nat_id <= 255):
            raise ValueError("Nationality ID must be 0-255")
        self.nationality = nat_id
        # Provide backwards-compatible attribute name used elsewhere
        try:
            self.nationality_id = nat_id
        except Exception:
            setattr(self, 'nationality_id', nat_id)
        self.modified = True

    @property
    def dob(self):
        """Return DOB as (day, month, year) tuple."""
        return (self.birth_day, self.birth_month, self.birth_year)

    @dob.setter
    def dob(self, t):
        """Set DOB tuple (day, month, year)."""
        if not (isinstance(t, (list, tuple)) and len(t) == 3):
            raise ValueError("DOB must be a (day, month, year) tuple")
        day, month, year = t
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
            raise ValueError("Invalid DOB")
        self.birth_day = day
        self.birth_month = month
        self.birth_year = year
        self.modified = True

    def set_dob(self, day: int, month: int, year: int):
        """Convenience setter for DOB."""
        self.dob = (day, month, year)

    def set_height(self, height_cm: int):
        """Set player's height in cm."""
        if not (50 <= height_cm <= 250):
            raise ValueError("Height must be in cm")
        self.height = height_cm
        self.modified = True

    @classmethod
    def attribute_slot_labels(cls) -> List[str]:
        """Return the current best-known labels for the trailing 12-byte attribute window."""
        return [
            "Attr 0 (unresolved, read-only)",
            "Attr 1 (unresolved, read-only)",
            "Attr 2 (unresolved, read-only)",
            "Attr 3 (Speed)",
            "Attr 4 (Stamina)",
            "Attr 5 (Aggression)",
            "Attr 6 (Quality)",
            "Attr 7 (Heading)",
            "Attr 8 (Dribbling)",
            "Attr 9 (Passing)",
            "Attr 10 (Shooting)",
            "Attr 11 (Tackling)",
        ]

    @classmethod
    def editable_attribute_indices(cls) -> List[int]:
        """Return the trailing-attribute slots that are currently safe to expose for editing."""
        return list(range(3, 12))

    def supports_weight_write(self) -> bool:
        """Return True when this record exposes a parser-backed in-place weight slot."""
        if self.raw_data is None:
            return False

        indexed_name = (self.name or f"{self.given_name} {self.surname}".strip()).strip()
        try:
            stored_name = self._extract_name(self.raw_data)
        except Exception:
            stored_name = indexed_name

        if self._find_indexed_suffix_anchor(self.raw_data, stored_name) is not None:
            return True
        if stored_name != indexed_name and self._find_indexed_suffix_anchor(self.raw_data, indexed_name) is not None:
            return True
        return self._find_legacy_weight_offset(self.raw_data) is not None

    def set_weight(self, weight_kg: int):
        """Set player's weight in kg for record shapes that support it."""
        if not (40 <= weight_kg <= 140):
            raise ValueError("Weight must be 40-140 kg")
        self.weight = weight_kg
        self.modified = True

    @property
    def position(self):
        """Alias property for legacy code expecting `position`."""
        return self.position_primary

    @position.setter
    def position(self, value):
        self.set_position(value)

    def __str__(self) -> str:
        """Human-readable representation."""
        return (
            f"Player #{self.record_id}: {self.given_name} {self.surname} "
            f"(Born: {self.birth_day:02d}/{self.birth_month:02d}/{self.birth_year}, "
            f"Pos: {self.position_primary}, Nation: {self.nationality})"
        )


@dataclass
class FDIHeader:
    """FDI file header structure.

    Based on MANAGPRE.EXE header parsing and the maintained notes in docs/DATA_FORMATS.md.
    """
    signature: bytes = b'DMFIv1.0'
    record_count: int = 0
    version: int = 2
    max_offset: int = 0
    dir_size: int = 0
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'FDIHeader':
        """Parse FDI header from file bytes."""
        if len(data) < 0x20:
            raise ValueError("File too small for FDI header")
        
        signature = data[0:8]
        if signature != b'DMFIv1.0':
            raise ValueError(f"Invalid signature: {signature}")
        
        record_count = struct.unpack_from("<I", data, 0x10)[0]
        version = struct.unpack_from("<I", data, 0x14)[0]
        max_offset = struct.unpack_from("<I", data, 0x18)[0]
        dir_size = struct.unpack_from("<I", data, 0x1C)[0]
        
        return cls(
            signature=signature,
            record_count=record_count,
            version=version,
            max_offset=max_offset,
            dir_size=dir_size
        )
    
    def to_bytes(self) -> bytes:
        """Serialize header to bytes."""
        header = bytearray(0x20)
        header[0:8] = self.signature
        struct.pack_into("<I", header, 0x10, self.record_count)
        struct.pack_into("<I", header, 0x14, self.version)
        struct.pack_into("<I", header, 0x18, self.max_offset)
        struct.pack_into("<I", header, 0x1C, self.dir_size)
        return bytes(header)


@dataclass
class DirectoryEntry:
    """FDI directory entry (offset table entry).
    
    Each entry is 8 bytes: <uint32 offset, uint16 tag, uint16 index>
    """
    offset: int
    tag: int  # Character code like 'G', 'N', 'L'
    index: int
    
    @classmethod
    def from_bytes(cls, data: bytes, pos: int) -> 'DirectoryEntry':
        """Parse a single directory entry."""
        if pos + 8 > len(data):
            raise ValueError(f"Truncated directory entry at 0x{pos:x}")
        
        offset, tag, index = struct.unpack_from("<IHH", data, pos)
        return cls(offset=offset, tag=tag, index=index)
    
    def to_bytes(self) -> bytes:
        """Serialize to 8-byte directory entry."""
        return struct.pack("<IHH", self.offset, self.tag, self.index)
