"""
Premier Manager 99 - Professional Player Editor
Production-quality GUI with clean name extraction and full functionality
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import struct
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
import csv

# ========== Improved Core Engine ==========

class PlayerRecord:
    def __init__(self, section_offset: int, record_start: int, record_end: int,
                 given_name: str, surname: str, name_offset: int, 
                 attributes: List[Tuple[int, int]]):
        self.section_offset = section_offset
        self.record_start = record_start
        self.record_end = record_end
        self.given_name = given_name
        self.surname = surname
        self.name_offset = name_offset
        self.attributes = attributes
        self.modified = False
    
    @property
    def full_name(self):
        return f"{self.given_name} {self.surname}".strip()
    
    def __str__(self):
        return self.full_name

def decode_xor61(data: bytes, offset: int) -> Tuple[bytes, int]:
    """Decode XOR-0x61 field"""
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def find_records_by_separator(decoded_data: bytes) -> List[int]:
    """Find record starts using separator pattern"""
    separators = []
    pattern = bytes([0xdd, 0x63, 0x60])
    pos = 0
    while pos < len(decoded_data) - 3:
        if decoded_data[pos:pos+3] == pattern:
            separators.append(pos)
            pos += 3
        else:
            pos += 1
    return separators

def extract_clean_name(data: bytes, start: int, max_len: int = 40) -> Tuple[str, int]:
    """
    Extract a clean player name by finding the capitalized name pattern.
    Returns (name, length_consumed)
    """
    # Look for pattern: Capital letter followed by lowercase (start of name)
    for i in range(start, min(start + 30, len(data))):
        if data[i] >= 65 and data[i] <= 90:  # Capital letter
            # Found potential name start
            name_bytes = bytearray()
            pos = i
            
            # Collect name characters
            while pos < len(data) and pos < i + max_len:
                c = data[pos]
                # Valid name characters: A-Z, a-z, space, accented (>127)
                # But stop at lowercase letters not preceded by space or capital
                if (65 <= c <= 90 or  # A-Z
                    97 <= c <= 122 or  # a-z
                    c == 32 or  # space
                    c > 127):  # accented
                    
                    # Stop if we hit lowercase after a capital that looks like end
                    if (97 <= c <= 122 and len(name_bytes) > 5 and 
                        name_bytes[-1] not in [32, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90]):
                        # Check if this looks like start of next name
                        if pos + 1 < len(data) and 97 <= data[pos + 1] <= 122:
                            break
                    
                    name_bytes.append(c)
                    pos += 1
                else:
                    break
            
            try:
                name = bytes(name_bytes).decode('latin1', errors='replace').strip()
                # Validate: name should have a space (Given SURNAME)
                if ' ' in name and 5 <= len(name) <= 35:
                    return name, pos - i
            except:
                pass
    
    return "", 0

def extract_player_from_record(decoded_data: bytes, record_start: int, record_end: int) -> Optional[PlayerRecord]:
    """
    Extract player info from a record.
    Improved to get clean names without garbage.
    """
    chunk = decoded_data[record_start:record_end]
    
    # Skip the separator
    offset = 3 if chunk[:3] == bytes([0xdd, 0x63, 0x60]) else 0
    
    # Look for the name (should be after some metadata bytes)
    # Names typically start 5-20 bytes into the record
    for search_start in range(offset, min(offset + 25, len(chunk))):
        name, name_len = extract_clean_name(chunk, search_start)
        
        if name and ' ' in name:
            # Split into given name and surname
            parts = name.split(None, 1)  # Split on first space
            if len(parts) == 2:
                given_name, surname = parts
                
                # Extract attributes (bytes after name that are 0-100)
                attrs = []
                attr_start = search_start + name_len
                for i in range(attr_start, min(attr_start + 40, len(chunk))):
                    val = chunk[i]
                    if 0 <= val <= 100 and val != 96:  # 96 is padding
                        attrs.append((record_start + i, val))
                
                if len(attrs) >= 5:  # Need at least some attributes
                    return PlayerRecord(
                        section_offset=0,  # Will be set by caller
                        record_start=record_start,
                        record_end=record_end,
                        given_name=given_name,
                        surname=surname,
                        name_offset=record_start + search_start,
                        attributes=attrs[:10]  # Take first 10
                    )
    
    return None

def parse_section_into_records(section_offset: int, decoded_data: bytes) -> List[PlayerRecord]:
    """Parse decoded section into clean player records"""
    separators = find_records_by_separator(decoded_data)
    records = []
    
    for i, sep in enumerate(separators):
        record_end = separators[i+1] if i+1 < len(separators) else len(decoded_data)
        
        player = extract_player_from_record(decoded_data, sep, record_end)
        if player:
            player.section_offset = section_offset
            records.append(player)
    
    return records

def find_all_player_records(file_data: bytes, progress_callback=None) -> List[PlayerRecord]:
    """Find all player records with progress tracking"""
    all_records = []
    pos = 0x400
    sections_scanned = 0
    
    while pos < len(file_data) - 1000 and sections_scanned < 500:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
            if 1000 < length < 100000:
                encoded = file_data[pos+2 : pos+2+length]
                decoded = bytes(b ^ 0x61 for b in encoded)
                if bytes([0xdd, 0x63, 0x60]) in decoded:
                    records = parse_section_into_records(pos, decoded)
                    all_records.extend(records)
                    sections_scanned += 1
                    if progress_callback:
                        progress_callback(sections_scanned, len(all_records))
                pos += length + 2
            else:
                pos += 1
        except:
            pos += 1
    
    return all_records

def modify_player_attribute(file_data: bytes, record: PlayerRecord, attr_index: int, new_value: int) -> bytes:
    """Modify a player attribute"""
    if attr_index >= len(record.attributes):
        raise ValueError(f"Attribute index {attr_index} out of range")
    if not (0 <= new_value <= 100):
        raise ValueError(f"Value must be 0-100")
    
    attr_offset_in_section, _ = record.attributes[attr_index]
    decoded, _ = decode_xor61(file_data, record.section_offset)
    modified = bytearray(decoded)
    modified[attr_offset_in_section] = new_value
    encoded = bytes(b ^ 0x61 for b in modified)
    length_prefix = struct.pack("<H", len(encoded))
    
    file_data_modified = bytearray(file_data)
    file_data_modified[record.section_offset:record.section_offset+2] = length_prefix
    file_data_modified[record.section_offset+2:record.section_offset+2+len(encoded)] = encoded
    
    return bytes(file_data_modified)

def modify_player_name(file_data: bytes, record: PlayerRecord, new_given: str, new_surname: str) -> bytes:
    """Modify player name (same length only for safety)"""
    old_name = record.full_name
    new_name = f"{new_given} {new_surname}"
    
    if len(new_name) != len(old_name):
        raise ValueError(f"New name must be same length as old name ({len(old_name)} chars)")
    
    decoded, _ = decode_xor61(file_data, record.section_offset)
    modified = bytearray(decoded)
    
    # Replace the name bytes
    name_bytes = new_name.encode('latin1')
    name_offset_in_section = record.name_offset - record.section_offset
    modified[name_offset_in_section:name_offset_in_section+len(name_bytes)] = name_bytes
    
    encoded = bytes(b ^ 0x61 for b in modified)
    length_prefix = struct.pack("<H", len(encoded))
    
    file_data_modified = bytearray(file_data)
    file_data_modified[record.section_offset:record.section_offset+2] = length_prefix
    file_data_modified[record.section_offset+2:record.section_offset+2+len(encoded)] = encoded
    
    return bytes(file_data_modified)

# ========== Professional GUI ==========

class PM99ProEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Premier Manager 99 - Professional Player Editor")
        self.root.geometry("1400x800")
        
        self.file_path = 'DBDAT/JUG98030.FDI'
        self.file_data = None
        self.all_players = []
        self.filtered_players = []
        self.current_player = None
        self.modified = False
        self.sort_column = 'name'
        self.sort_reverse = False
        
        # Attribute names (best guess - user can verify in-game)
        self.attr_names = [
            "Passing", "Shooting", "Tackling", "Speed", "Stamina",
            "Heading", "Skill", "Aggression", "Positioning", "Form"
        ]
        
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Create professional UI"""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export CSV...", command=self.export_csv)
        file_menu.add_command(label="Reload", command=self.load_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Find...", command=lambda: self.search_entry.focus(), accelerator="Ctrl+F")
        edit_menu.add_command(label="Reset Current Player", command=self.reset_player)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
        # Keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self.save_file())
        self.root.bind('<Control-o>', lambda e: self.open_file())
        self.root.bind('<Control-f>', lambda e: self.search_entry.focus())
        
        # Main container
        main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - Player list
        left_frame = ttk.Frame(main_container)
        main_container.add(left_frame, weight=1)
        
        # Search and filters
        search_frame = ttk.LabelFrame(left_frame, text="Search & Filter", padding="5")
        search_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(search_frame, text="Search:").grid(row=0, column=0, sticky=tk.W)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_players)
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        search_frame.columnconfigure(1, weight=1)
        
        # Sort options
        ttk.Label(search_frame, text="Sort by:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.sort_var = tk.StringVar(value="name")
        sort_combo = ttk.Combobox(search_frame, textvariable=self.sort_var, state='readonly', width=15)
        sort_combo['values'] = ['name', 'given_name', 'surname'] + [f'attr_{i}' for i in range(10)]
        sort_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=(5,0))
        sort_combo.bind('<<ComboboxSelected>>', lambda e: self.sort_players())
        
        # Player list with treeview for better display
        list_frame = ttk.LabelFrame(left_frame, text="Players", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview with scrollbar
        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.player_tree = ttk.Treeview(list_frame, yscrollcommand=tree_scroll.set, 
                                        columns=('name',), show='tree', selectmode='browse')
        self.player_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.player_tree.yview)
        self.player_tree.bind('<<TreeviewSelect>>', self.on_player_select)
        
        # Player count
        self.player_count_label = ttk.Label(left_frame, text="Players: 0")
        self.player_count_label.pack(pady=(5, 0))
        
        # Right panel - Player editor
        right_frame = ttk.Frame(main_container)
        main_container.add(right_frame, weight=2)
        
        # Player info
        info_frame = ttk.LabelFrame(right_frame, text="Player Information", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 5))
        info_frame.columnconfigure(1, weight=1)
        
        # Name editing
        ttk.Label(info_frame, text="Given Name:", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.given_name_var = tk.StringVar()
        self.given_name_entry = ttk.Entry(info_frame, textvariable=self.given_name_var, font=('TkDefaultFont', 11))
        self.given_name_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        
        ttk.Label(info_frame, text="Surname:", font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.surname_var = tk.StringVar()
        self.surname_entry = ttk.Entry(info_frame, textvariable=self.surname_var, font=('TkDefaultFont', 11))
        self.surname_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        
        ttk.Label(info_frame, text="Section:", font=('TkDefaultFont', 8)).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.section_label = ttk.Label(info_frame, text="", font=('TkDefaultFont', 8))
        self.section_label.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        # Attributes
        attr_frame = ttk.LabelFrame(right_frame, text="Player Attributes", padding="10")
        attr_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas for scrolling
        canvas = tk.Canvas(attr_frame)
        scrollbar = ttk.Scrollbar(attr_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.attribute_widgets = []
        
        # Action buttons
        button_frame = ttk.Frame(right_frame, padding="10")
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="💾 Save Changes", command=self.apply_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🔄 Reset", command=self.reset_player).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="📝 Edit Name", command=self.edit_name).pack(side=tk.LEFT, padx=5)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def load_data(self):
        """Load player data"""
        try:
            self.status_var.set("Loading players...")
            self.root.update()
            
            if not Path(self.file_path).exists():
                messagebox.showerror("Error", f"File not found: {self.file_path}")
                return
            
            self.file_data = Path(self.file_path).read_bytes()
            
            # Progress dialog
            progress_win = tk.Toplevel(self.root)
            progress_win.title("Loading Players")
            progress_win.geometry("400x120")
            progress_win.transient(self.root)
            progress_win.grab_set()
            
            progress_label = ttk.Label(progress_win, text="Scanning sections...", font=('TkDefaultFont', 10))
            progress_label.pack(pady=15)
            
            detail_label = ttk.Label(progress_win, text="", font=('TkDefaultFont', 9))
            detail_label.pack()
            
            progress_bar = ttk.Progressbar(progress_win, mode='indeterminate', length=350)
            progress_bar.pack(pady=10)
            progress_bar.start()
            
            def update_progress(sections, players):
                detail_label.config(text=f"Sections: {sections} | Players found: {players}")
                progress_win.update()
            
            self.all_players = find_all_player_records(self.file_data, update_progress)
            progress_win.destroy()
            
            self.filtered_players = self.all_players.copy()
            self.sort_players()
            
            self.status_var.set(f"✓ Loaded {len(self.all_players)} players")
            messagebox.showinfo("Success", 
                f"Successfully loaded {len(self.all_players)} players!\n\n"
                f"Sections scanned: {len(set(p.section_offset for p in self.all_players))}\n"
                f"File: {self.file_path}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data:\n{str(e)}")
            self.status_var.set("❌ Error loading data")
    
    def populate_player_list(self):
        """Populate the player tree"""
        self.player_tree.delete(*self.player_tree.get_children())
        
        for i, player in enumerate(self.filtered_players):
            self.player_tree.insert('', tk.END, iid=str(i), text=player.full_name)
        
        self.player_count_label.config(
            text=f"Players: {len(self.filtered_players)} / {len(self.all_players)}"
        )
    
    def filter_players(self, *args):
        """Filter players by search text"""
        search_text = self.search_var.get().lower()
        if search_text:
            self.filtered_players = [p for p in self.all_players 
                                    if search_text in p.full_name.lower()]
        else:
            self.filtered_players = self.all_players.copy()
        self.sort_players()
    
    def sort_players(self):
        """Sort filtered players"""
        sort_by = self.sort_var.get()
        
        if sort_by == 'name':
            self.filtered_players.sort(key=lambda p: p.full_name, reverse=self.sort_reverse)
        elif sort_by == 'given_name':
            self.filtered_players.sort(key=lambda p: p.given_name, reverse=self.sort_reverse)
        elif sort_by == 'surname':
            self.filtered_players.sort(key=lambda p: p.surname, reverse=self.sort_reverse)
        elif sort_by.startswith('attr_'):
            idx = int(sort_by.split('_')[1])
            self.filtered_players.sort(
                key=lambda p: p.attributes[idx][1] if idx < len(p.attributes) else 0,
                reverse=not self.sort_reverse
            )
        
        self.populate_player_list()
    
    def on_player_select(self, event):
        """Handle player selection"""
        selection = self.player_tree.selection()
        if not selection:
            return
        
        index = int(selection[0])
        self.current_player = self.filtered_players[index]
        self.display_player_details()
    
    def display_player_details(self):
        """Display selected player's details"""
        if not self.current_player:
            return
        
        # Update name fields
        self.given_name_var.set(self.current_player.given_name)
        self.surname_var.set(self.current_player.surname)
        self.section_label.config(text=f"0x{self.current_player.section_offset:08x}")
        
        # Clear and recreate attribute widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        self.attribute_widgets = []
        
        for i, (offset, value) in enumerate(self.current_player.attributes):
            frame = ttk.Frame(self.scrollable_frame)
            frame.pack(fill=tk.X, pady=3)
            
            # Attribute label
            attr_name = self.attr_names[i] if i < len(self.attr_names) else f"Attribute {i}"
            ttk.Label(frame, text=f"{attr_name}:", width=12, 
                     font=('TkDefaultFont', 9, 'bold')).pack(side=tk.LEFT, padx=5)
            
            # Value spinbox
            var = tk.IntVar(value=value)
            self.attribute_widgets.append(var)
            
            spinbox = ttk.Spinbox(frame, from_=0, to=100, textvariable=var, width=8)
            spinbox.pack(side=tk.LEFT, padx=5)
            
            # Scale
            scale = ttk.Scale(frame, from_=0, to=100, variable=var, orient=tk.HORIZONTAL, length=200)
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Current value display
            value_label = ttk.Label(frame, text=f"{value}", width=4, 
                                   font=('TkDefaultFont', 9, 'bold'))
            value_label.pack(side=tk.RIGHT, padx=5)
            
            # Update value label when changed
            def make_updater(lbl, v):
                def update(*args):
                    lbl.config(text=str(v.get()))
                return update
            
            var.trace('w', make_updater(value_label, var))
    
    def apply_changes(self):
        """Apply all changes to current player"""
        if not self.current_player:
            return
        
        try:
            changes = []
            temp_data = self.file_data
            
            # Apply attribute changes
            for i, var in enumerate(self.attribute_widgets):
                new_val = var.get()
                old_val = self.current_player.attributes[i][1]
                
                if new_val != old_val:
                    temp_data = modify_player_attribute(temp_data, self.current_player, i, new_val)
                    changes.append(f"{self.attr_names[i] if i < len(self.attr_names) else f'Attr {i}'}: {old_val} → {new_val}")
                    self.current_player.attributes[i] = (self.current_player.attributes[i][0], new_val)
            
            if changes:
                self.file_data = temp_data
                self.current_player.modified = True
                self.modified = True
                
                change_text = '\n'.join(changes)
                self.status_var.set(f"✓ Applied {len(changes)} change(s) to {self.current_player.full_name}")
                messagebox.showinfo("Success", 
                    f"Changes applied to {self.current_player.full_name}:\n\n{change_text}\n\n"
                    "Remember to save the file (Ctrl+S)")
            else:
                messagebox.showinfo("Info", "No changes to apply")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply changes:\n{str(e)}")
    
    def edit_name(self):
        """Edit player name"""
        if not self.current_player:
            return
        
        new_given = self.given_name_var.get().strip()
        new_surname = self.surname_var.get().strip()
        
        if not new_given or not new_surname:
            messagebox.showwarning("Warning", "Both given name and surname are required")
            return
        
        old_name = self.current_player.full_name
        new_name = f"{new_given} {new_surname}"
        
        if old_name == new_name:
            messagebox.showinfo("Info", "Name unchanged")
            return
        
        if len(new_name) != len(old_name):
            messagebox.showwarning("Warning", 
                f"New name must be exactly {len(old_name)} characters (same as current name).\n\n"
                f"Current: {old_name} ({len(old_name)} chars)\n"
                f"New: {new_name} ({len(new_name)} chars)\n\n"
                "Pad with spaces if needed.")
            return
        
        try:
            self.file_data = modify_player_name(self.file_data, self.current_player, new_given, new_surname)
            
            # Update player object
            self.current_player.given_name = new_given
            self.current_player.surname = new_surname
            self.current_player.modified = True
            self.modified = True
            
            # Update display
            self.populate_player_list()
            
            self.status_var.set(f"✓ Renamed to {new_name}")
            messagebox.showinfo("Success", 
                f"Player renamed!\n\n{old_name} → {new_name}\n\n"
                "Remember to save (Ctrl+S)")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to rename player:\n{str(e)}")
    
    def reset_player(self):
        """Reset current player to original values"""
        if self.current_player:
            self.display_player_details()
            self.status_var.set
    
    def reset_player(self):
        """Reset current player to original values"""
        if self.current_player:
            self.display_player_details()
            self.status_var.set("Player reset")
    
    def save_file(self):
        """Save changes to file"""
        if not self.modified:
            messagebox.showinfo("Info", "No changes to save")
            return
        
        result = messagebox.askyesno("Confirm Save",
            "Save all changes to file?\n\n"
            "A timestamped backup will be created automatically.")
        
        if not result:
            return
        
        try:
            # Create timestamped backup
            backup_path = Path(self.file_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            backup_path.write_bytes(Path(self.file_path).read_bytes())
            
            # Save modified data
            Path(self.file_path).write_bytes(self.file_data)
            
            self.modified = False
            for player in self.all_players:
                player.modified = False
            
            self.status_var.set(f"✓ Saved to {self.file_path}")
            messagebox.showinfo("Success", 
                f"File saved successfully!\n\n"
                f"Backup: {backup_path.name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def save_as(self):
        """Save to different file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".FDI",
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
            initialfile="JUG98030_modified.FDI"
        )
        if filename:
            try:
                Path(filename).write_bytes(self.file_data)
                self.status_var.set(f"✓ Saved as {filename}")
                messagebox.showinfo("Success", f"Saved as:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def open_file(self):
        """Open different file"""
        filename = filedialog.askopenfilename(
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")],
            initialdir="DBDAT"
        )
        if filename:
            if self.modified:
                result = messagebox.askyesnocancel("Unsaved Changes",
                    "You have unsaved changes. Save before opening new file?")
                if result is None:  # Cancel
                    return
                elif result:  # Yes
                    self.save_file()
            
            self.file_path = filename
            self.modified = False
            self.load_data()
    
    def export_csv(self):
        """Export all players to CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="pm99_players.csv"
        )
        if not filename:
            return
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header
                header = ['Given Name', 'Surname', 'Full Name'] + self.attr_names
                writer.writerow(header)
                
                # Data
                for player in self.all_players:
                    row = [
                        player.given_name,
                        player.surname,
                        player.full_name
                    ]
                    row.extend([str(attr[1]) for attr in player.attributes])
                    writer.writerow(row)
            
            self.status_var.set(f"✓ Exported {len(self.all_players)} players to CSV")
            messagebox.showinfo("Success", 
                f"Exported {len(self.all_players)} players to:\n{filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export:\n{str(e)}")
    
    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About",
            "Premier Manager 99 - Professional Player Editor\n\n"
            "Version: 1.0\n"
            "Reverse engineered and developed for PM99 modding community\n\n"
            "Features:\n"
            "• Edit all 10 player attributes\n"
            "• Rename players (same-length names)\n"
            "• Search, filter, and sort\n"
            "• Export to CSV\n"
            "• Automatic backups\n\n"
            f"Currently loaded: {len(self.all_players)} players")

def main():
    root = tk.Tk()
    
    # Set modern theme
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    # Custom styles
    style.configure('Accent.TButton', font=('TkDefaultFont', 10, 'bold'))
    
    app = PM99ProEditor(root)
    
    # Center window
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()

if __name__ == '__main__':
    main()