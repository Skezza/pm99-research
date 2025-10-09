"""
Premier Manager 99 - Professional Player Editor
Full-featured production GUI with clean name extraction and all functionality
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import struct
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime
import csv

# ========== Core Engine with Improved Name Extraction ==========

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

def decode_xor61(data: bytes, offset: int) -> Tuple[bytes, int]:
    if offset + 2 > len(data):
        return b"", 0
    length = struct.unpack_from("<H", data, offset)[0]
    if offset + 2 + length > len(data):
        return b"", 0
    encoded = data[offset+2 : offset+2+length]
    decoded = bytes(b ^ 0x61 for b in encoded)
    return decoded, 2 + length

def find_records_by_separator(decoded_data: bytes) -> List[int]:
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

def extract_clean_player(decoded: bytes, start: int, end: int) -> Optional[Tuple[str, str, int]]:
    """Extract clean given name and surname. Returns (given, surname, name_length)"""
    chunk = decoded[start:end]
    
    # Look for capital letter start of name (after separator/metadata)
    for i in range(3, min(25, len(chunk))):
        if 65 <= chunk[i] <= 90:  # Capital letter
            # Extract full name
            name_bytes = bytearray()
            pos = i
            
            while pos < len(chunk):
                c = chunk[pos]
                if (65 <= c <= 90 or 97 <= c <= 122 or c == 32 or c > 127):
                    # Stop if we hit lowercase that looks like next player
                    if (pos > i + 8 and 97 <= c <= 122 and  
                        name_bytes and name_bytes[-1] not in [32] and
                        pos + 1 < len(chunk) and 97 <= chunk[pos+1] <= 122):
                        break
                    name_bytes.append(c)
                    pos += 1
                else:
                    break
            
            try:
                name = bytes(name_bytes).decode('latin1', errors='replace').strip()
                # Must have space (Given SURNAME format)
                if ' ' in name and 6 <= len(name) <= 35:
                    parts = name.split(None, 1)
                    if len(parts) == 2:
                        return parts[0], parts[1], pos - i
            except:
                pass
    
    return None

def parse_section_into_records(section_offset: int, decoded_data: bytes) -> List[PlayerRecord]:
    separators = find_records_by_separator(decoded_data)
    records = []
    
    for i, sep in enumerate(separators):
        record_end = separators[i+1] if i+1 < len(separators) else len(decoded_data)
        
        result = extract_clean_player(decoded_data, sep, record_end)
        if result:
            given, surname, name_len = result
            
            # Find name position
            name_pos = sep
            for j in range(sep, record_end):
                if decoded_data[j:j+len(given)] == given.encode('latin1', errors='replace'):
                    name_pos = j
                    break
            
            # Extract attributes after name
            attrs = []
            attr_start = name_pos + len(f"{given} {surname}")
            for j in range(attr_start, min(attr_start + 40, record_end)):
                val = decoded_data[j]
                if 0 <= val <= 100 and val != 96:
                    attrs.append((j, val))
            
            if len(attrs) >= 5:
                player = PlayerRecord(
                    section_offset=section_offset,
                    record_start=sep,
                    record_end=record_end,
                    given_name=given,
                    surname=surname,
                    name_offset=name_pos,
                    attributes=attrs[:10]
                )
                records.append(player)
    
    return records

def find_all_player_records(file_data: bytes, progress_callback=None) -> List[PlayerRecord]:
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
    if attr_index >= len(record.attributes):
        raise ValueError(f"Attribute index out of range")
    if not (0 <= new_value <= 100):
        raise ValueError(f"Value must be 0-100")
    
    attr_offset, _ = record.attributes[attr_index]
    decoded, _ = decode_xor61(file_data, record.section_offset)
    modified = bytearray(decoded)
    modified[attr_offset] = new_value
    encoded = bytes(b ^ 0x61 for b in modified)
    length_prefix = struct.pack("<H", len(encoded))
    
    file_data_modified = bytearray(file_data)
    file_data_modified[record.section_offset:record.section_offset+2] = length_prefix
    file_data_modified[record.section_offset+2:record.section_offset+2+len(encoded)] = encoded
    
    return bytes(file_data_modified)

# ========== Professional GUI ==========

class PM99Editor:
    def __init__(self, root):
        self.root = root
        self.root.title("Premier Manager 99 - Player Editor")
        self.root.geometry("1400x800")
        
        self.file_path = 'DBDAT/JUG98030.FDI'
        self.file_data = None
        self.all_players = []
        self.filtered_players = []
        self.current_player = None
        self.modified = False
        
        self.attr_names = [
            "Passing", "Shooting", "Tackling", "Speed", "Stamina",
            "Heading", "Dribbling", "Aggression", "Positioning", "Form"
        ]
        
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        # Menu
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Export CSV...", command=self.export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        self.root.bind('<Control-s>', lambda e: self.save_file())
        
        # Main layout
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left - Player list
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        # Search
        search_frame = ttk.LabelFrame(left_frame, text="Search", padding="5")
        search_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_players)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(fill=tk.X)
        
        # Player list
        list_frame = ttk.LabelFrame(left_frame, text="Players", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scroll = ttk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.player_tree = ttk.Treeview(list_frame, yscrollcommand=scroll.set, show='tree')
        self.player_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self.player_tree.yview)
        self.player_tree.bind('<<TreeviewSelect>>', self.on_player_select)
        
        self.count_label = ttk.Label(left_frame, text="Players: 0")
        self.count_label.pack(pady=5)
        
        # Right - Editor
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        # Player info
        info_frame = ttk.LabelFrame(right_frame, text="Player", padding="10")
        info_frame.pack(fill=tk.X)
        
        self.name_label = ttk.Label(info_frame, text="", font=('TkDefaultFont', 14, 'bold'))
        self.name_label.pack()
        
        # Attributes
        attr_frame = ttk.LabelFrame(right_frame, text="Attributes", padding="10")
        attr_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        canvas = tk.Canvas(attr_frame)
        scroll_attr = ttk.Scrollbar(attr_frame, orient=tk.VERTICAL, command=canvas.yview)
        self.attr_container = ttk.Frame(canvas)
        
        self.attr_container.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.attr_container, anchor=tk.NW)
        canvas.configure(yscrollcommand=scroll_attr.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_attr.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.attr_vars = []
        
        # Buttons
        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(btn_frame, text="💾 Apply Changes", command=self.apply_changes).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 Reset", command=self.reset).pack(side=tk.LEFT)
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)
    
    def load_data(self):
        try:
            if not Path(self.file_path).exists():
                messagebox.showerror("Error", f"File not found: {self.file_path}")
                return
            
            self.file_data = Path(self.file_path).read_bytes()
            
            # Progress
            progress = tk.Toplevel(self.root)
            progress.title("Loading")
            progress.geometry("350x100")
            progress.transient(self.root)
            progress.grab_set()
            
            lbl = ttk.Label(progress, text="Scanning sections...", font=('TkDefaultFont', 10))
            lbl.pack(pady=15)
            
            detail = ttk.Label(progress, text="")
            detail.pack()
            
            bar = ttk.Progressbar(progress, mode='indeterminate', length=300)
            bar.pack(pady=10)
            bar.start()
            
            def update_progress(sections, players):
                detail.config(text=f"Sections: {sections} | Players: {players}")
                progress.update()
            
            self.all_players = find_all_player_records(self.file_data, update_progress)
            progress.destroy()
            
            self.filtered_players = self.all_players.copy()
            self.populate_list()
            
            messagebox.showinfo("Success", f"Loaded {len(self.all_players)} players!")
            self.status_var.set(f"✓ {len(self.all_players)} players loaded")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load:\n{str(e)}")
    
    def populate_list(self):
        self.player_tree.delete(*self.player_tree.get_children())
        for i, p in enumerate(self.filtered_players):
            self.player_tree.insert('', tk.END, iid=str(i), text=p.full_name)
        self.count_label.config(text=f"Players: {len(self.filtered_players)} / {len(self.all_players)}")
    
    def filter_players(self, *args):
        search = self.search_var.get().lower()
        self.filtered_players = [p for p in self.all_players if search in p.full_name.lower()] if search else self.all_players.copy()
        self.populate_list()
    
    def on_player_select(self, event):
        sel = self.player_tree.selection()
        if sel:
            self.current_player = self.filtered_players[int(sel[0])]
            self.display_player()
    
    def display_player(self):
        if not self.current_player:
            return
        
        self.name_label.config(text=self.current_player.full_name)
        
        for w in self.attr_container.winfo_children():
            w.destroy()
        
        self.attr_vars = []
        
        for i, (offset, val) in enumerate(self.current_player.attributes):
            frame = ttk.Frame(self.attr_container)
            frame.pack(fill=tk.X, pady=2)
            
            name = self.attr_names[i] if i < len(self.attr_names) else f"Attr {i}"
            ttk.Label(frame, text=f"{name}:", width=12, font=('TkDefaultFont', 9, 'bold')).pack(side=tk.LEFT, padx=5)
            
            var = tk.IntVar(value=val)
            self.attr_vars.append(var)
            
            ttk.Spinbox(frame, from_=0, to=100, textvariable=var, width=8).pack(side=tk.LEFT, padx=5)
            ttk.Scale(frame, from_=0, to=100, variable=var, orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            val_lbl = ttk.Label(frame, text=str(val), width=4, font=('TkDefaultFont', 9, 'bold'))
            val_lbl.pack(side=tk.RIGHT, padx=5)
            
            var.trace('w', lambda *args, lbl=val_lbl, v=var: lbl.config(text=str(v.get())))
    
    def apply_changes(self):
        if not self.current_player:
            return
        
        try:
            changes = []
            temp_data = self.file_data
            
            for i, var in enumerate(self.attr_vars):
                new_val = var.get()
                old_val = self.current_player.attributes[i][1]
                
                if new_val != old_val:
                    temp_data = modify_player_attribute(temp_data, self.current_player, i, new_val)
                    changes.append(f"{self.attr_names[i] if i < len(self.attr_names) else f'Attr {i}'}: {old_val} → {new_val}")
                    self.current_player.attributes[i] = (self.current_player.attributes[i][0], new_val)
            
            if changes:
                self.file_data = temp_data
                self.modified = True
                messagebox.showinfo("Success", f"Applied {len(changes)} change(s)!\n\n" + '\n'.join(changes) + "\n\nRemember to save (Ctrl+S)")
                self.status_var.set(f"✓ {len(changes)} changes applied")
            else:
                messagebox.showinfo("Info", "No changes to apply")
        except Exception as e:
            messagebox.showerror("Error", f"Failed:\n{str(e)}")
    
    def reset(self):
        if self.current_player:
            self.display_player()
    
    def save_file(self):
        if not self.modified:
            messagebox.showinfo("Info", "No changes to save")
            return
        
        try:
            backup = Path(self.file_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            backup.write_bytes(Path(self.file_path).read_bytes())
            Path(self.file_path).write_bytes(self.file_data)
            
            self.modified = False
            messagebox.showinfo("Success", f"Saved!\nBackup: {backup.name}")
            self.status_var.set("✓ Saved")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{str(e)}")
    
    def export_csv(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="pm99_players.csv"
        )
        if not filename:
            return
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Given', 'Surname', 'Full Name'] + self.attr_names)
                
                for p in self.all_players:
                    row = [p.given_name, p.surname, p.full_name]
                    row.extend([str(a[1]) for a in p.attributes])
                    writer.writerow(row)
            
            messagebox.showinfo("Success", f"Exported {len(self.all_players)} players to CSV!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export:\n{str(e)}")

def main():
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    app = PM99Editor(root)
    root.mainloop()

if __name__ == '__main__':
    main()