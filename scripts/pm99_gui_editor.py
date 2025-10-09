"""
Premier Manager 99 - GUI Player Editor
Full-featured Tkinter GUI for editing all player names and attributes
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import struct
from pathlib import Path
from typing import List, Tuple, Dict, Any
from datetime import datetime

# ========== Core Engine (from advanced_player_editor.py) ==========

class PlayerRecord:
    def __init__(self, section_offset: int, record_start: int, record_end: int,
                 name: str, name_offset: int, attributes: List[Tuple[int, int]]):
        self.section_offset = section_offset
        self.record_start = record_start
        self.record_end = record_end
        self.name = name
        self.name_offset = name_offset
        self.attributes = attributes
        self.original_attributes = attributes.copy()  # For tracking changes

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

def extract_player_name(decoded_data: bytes, record_start: int, record_end: int) -> Tuple[str, int]:
    """Extract plaintext player name from record"""
    chunk = decoded_data[record_start:record_end]
    for i in range(len(chunk) - 10):
        if (chunk[i] >= 65 and chunk[i] <= 90 and
            i + 1 < len(chunk) and
            chunk[i+1] >= 97 and chunk[i+1] <= 122):
            name_end = i
            while name_end < len(chunk):
                c = chunk[name_end]
                if (65 <= c <= 90 or 97 <= c <= 122 or c == 32 or c > 127):
                    name_end += 1
                else:
                    break
            name = chunk[i:name_end].decode('latin1', errors='replace').strip()
            if 8 <= len(name) <= 40 and ' ' in name:
                return name, record_start + i
    return "", 0

def extract_attributes(decoded_data: bytes, name_end: int, record_end: int) -> List[Tuple[int, int]]:
    """Extract attribute bytes after name"""
    attrs = []
    chunk = decoded_data[name_end:record_end]
    for i, byte_val in enumerate(chunk[:40]):
        if 0 <= byte_val <= 100 and byte_val != 96:
            attrs.append((name_end + i, byte_val))
    return attrs

def parse_section_into_records(section_offset: int, decoded_data: bytes) -> List[PlayerRecord]:
    """Parse decoded section into player records"""
    separators = find_records_by_separator(decoded_data)
    records = []
    for i, sep in enumerate(separators):
        record_end = separators[i+1] if i+1 < len(separators) else len(decoded_data)
        name, name_offset = extract_player_name(decoded_data, sep, record_end)
        if name:
            attrs = extract_attributes(decoded_data, name_offset + len(name), record_end)
            record = PlayerRecord(
                section_offset=section_offset,
                record_start=sep,
                record_end=record_end,
                name=name,
                name_offset=name_offset,
                attributes=attrs[:10]
            )
            records.append(record)
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

# ========== GUI Application ==========

class PM99EditorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Premier Manager 99 - Player Editor")
        self.root.geometry("1200x700")
        
        self.file_path = 'DBDAT/JUG98030.FDI'
        self.file_data = None
        self.all_players = []
        self.filtered_players = []
        self.current_player = None
        self.modified = False
        
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Create the UI layout"""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open...", command=self.open_file)
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Reload", command=self.load_data)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self.save_file())
        self.root.bind('<Control-f>', lambda e: self.search_entry.focus())
        
        # Main container
        main_container = ttk.Frame(self.root, padding="5")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(1, weight=1)
        
        # Left panel - Player list
        left_frame = ttk.LabelFrame(main_container, text="Players", padding="5")
        left_frame.grid(row=0, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # Search box
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_players)
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Player listbox with scrollbar
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.player_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, width=40)
        self.player_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.player_listbox.yview)
        self.player_listbox.bind('<<ListboxSelect>>', self.on_player_select)
        
        # Player count label
        self.player_count_label = ttk.Label(left_frame, text="Players: 0")
        self.player_count_label.pack(pady=(5, 0))
        
        # Right panel - Player details
        right_frame = ttk.LabelFrame(main_container, text="Player Details", padding="5")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.columnconfigure(1, weight=1)
        
        # Player name
        ttk.Label(right_frame, text="Name:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.name_label = ttk.Label(right_frame, text="", font=('TkDefaultFont', 12))
        self.name_label.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        # Section info
        ttk.Label(right_frame, text="Section:").grid(row=1, column=0, sticky=tk.W)
        self.section_label = ttk.Label(right_frame, text="")
        self.section_label.grid(row=1, column=1, sticky=tk.W)
        
        ttk.Separator(right_frame, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        # Attributes header
        ttk.Label(right_frame, text="Attributes:", font=('TkDefaultFont', 10, 'bold')).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
        
        # Attributes frame with scrollbar
        attr_canvas_frame = ttk.Frame(right_frame)
        attr_canvas_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.rowconfigure(4, weight=1)
        
        attr_canvas = tk.Canvas(attr_canvas_frame, height=300)
        attr_scrollbar = ttk.Scrollbar(attr_canvas_frame, orient=tk.VERTICAL, command=attr_canvas.yview)
        self.attributes_frame = ttk.Frame(attr_canvas)
        
        self.attributes_frame.bind('<Configure>', lambda e: attr_canvas.configure(scrollregion=attr_canvas.bbox('all')))
        attr_canvas.create_window((0, 0), window=self.attributes_frame, anchor=tk.NW)
        attr_canvas.configure(yscrollcommand=attr_scrollbar.set)
        
        attr_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        attr_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.attribute_vars = []
        
        # Bottom panel - Actions
        bottom_frame = ttk.Frame(main_container, padding="5")
        bottom_frame.grid(row=1, column=1, sticky=(tk.W, tk.E))
        
        ttk.Button(bottom_frame, text="Apply Changes", command=self.apply_changes, style='Accent.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Reset", command=self.reset_player).pack(side=tk.LEFT)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))
    
    def load_data(self):
        """Load player data from file"""
        try:
            self.status_var.set("Loading players...")
            self.root.update()
            
            if not Path(self.file_path).exists():
                messagebox.showerror("Error", f"File not found: {self.file_path}")
                return
            
            self.file_data = Path(self.file_path).read_bytes()
            
            # Show progress window
            progress_win = tk.Toplevel(self.root)
            progress_win.title("Loading...")
            progress_win.geometry("300x100")
            progress_win.transient(self.root)
            
            progress_label = ttk.Label(progress_win, text="Scanning sections...")
            progress_label.pack(pady=10)
            
            progress_bar = ttk.Progressbar(progress_win, mode='indeterminate')
            progress_bar.pack(pady=10, padx=20, fill=tk.X)
            progress_bar.start()
            
            def update_progress(sections, players):
                progress_label.config(text=f"Sections: {sections}, Players: {players}")
                progress_win.update()
            
            self.root.update()
            self.all_players = find_all_player_records(self.file_data, update_progress)
            
            progress_win.destroy()
            
            self.filtered_players = self.all_players.copy()
            self.populate_player_list()
            
            self.status_var.set(f"Loaded {len(self.all_players)} players")
            messagebox.showinfo("Success", f"Loaded {len(self.all_players)} players from {len(set(p.section_offset for p in self.all_players))} sections")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {str(e)}")
            self.status_var.set("Error loading data")
    
    def populate_player_list(self):
        """Populate the player listbox"""
        self.player_listbox.delete(0, tk.END)
        for player in self.filtered_players:
            self.player_listbox.insert(tk.END, player.name)
        self.player_count_label.config(text=f"Players: {len(self.filtered_players)} / {len(self.all_players)}")
    
    def filter_players(self, *args):
        """Filter players by search text"""
        search_text = self.search_var.get().lower()
        if search_text:
            self.filtered_players = [p for p in self.all_players if search_text in p.name.lower()]
        else:
            self.filtered_players = self.all_players.copy()
        self.populate_player_list()
    
    def on_player_select(self, event):
        """Handle player selection"""
        selection = self.player_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        self.current_player = self.filtered_players[index]
        self.display_player_details()
    
    def display_player_details(self):
        """Display selected player's details"""
        if not self.current_player:
            return
        
        # Update labels
        self.name_label.config(text=self.current_player.name)
        self.section_label.config(text=f"0x{self.current_player.section_offset:08x}")
        
        # Clear and repopulate attributes
        for widget in self.attributes_frame.winfo_children():
            widget.destroy()
        
        self.attribute_vars = []
        
        # Attribute labels (best guess based on typical football games)
        attr_labels = [
            "Attribute 0", "Attribute 1", "Attribute 2", "Attribute 3", "Attribute 4",
            "Attribute 5", "Attribute 6", "Attribute 7", "Attribute 8", "Attribute 9"
        ]
        
        for i, (offset, value) in enumerate(self.current_player.attributes):
            frame = ttk.Frame(self.attributes_frame)
            frame.pack(fill=tk.X, pady=2)
            
            label_text = attr_labels[i] if i < len(attr_labels) else f"Attribute {i}"
            ttk.Label(frame, text=f"{label_text}:", width=15).pack(side=tk.LEFT)
            
            var = tk.IntVar(value=value)
            self.attribute_vars.append(var)
            
            spinbox = ttk.Spinbox(frame, from_=0, to=100, textvariable=var, width=10)
            spinbox.pack(side=tk.LEFT, padx=5)
            
            # Scale for visual feedback
            scale = ttk.Scale(frame, from_=0, to=100, variable=var, orient=tk.HORIZONTAL)
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Value label
            value_label = ttk.Label(frame, text=str(value), width=5)
            value_label.pack(side=tk.RIGHT)
            
            # Update label when value changes
            def update_label(v=value_label, var=var):
                v.config(text=str(var.get()))
            var.trace('w', lambda *args, u=update_label: u())
    
    def apply_changes(self):
        """Apply attribute changes to the player"""
        if not self.current_player:
            return
        
        try:
            changes_made = False
            temp_data = self.file_data
            
            for i, var in enumerate(self.attribute_vars):
                new_value = var.get()
                old_value = self.current_player.attributes[i][1]
                
                if new_value != old_value:
                    temp_data = modify_player_attribute(temp_data, self.current_player, i, new_value)
                    self.current_player.attributes[i] = (self.current_player.attributes[i][0], new_value)
                    changes_made = True
            
            if changes_made:
                self.file_data = temp_data
                self.modified = True
                self.status_var.set(f"Changes applied to {self.current_player.name}")
                messagebox.showinfo("Success", "Attribute changes applied!\n\nRemember to save the file.")
            else:
                messagebox.showinfo("Info", "No changes to apply")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to apply changes: {str(e)}")
    
    def reset_player(self):
        """Reset player attributes to original values"""
        if self.current_player:
            self.display_player_details()
            self.status_var.set("Player reset")
    
    def save_file(self):
        """Save changes to file"""
        if not self.modified:
            messagebox.showinfo("Info", "No changes to save")
            return
        
        try:
            # Create backup
            backup_path = Path(self.file_path + f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            backup_path.write_bytes(Path(self.file_path).read_bytes())
            
            # Save modified data
            Path(self.file_path).write_bytes(self.file_data)
            
            self.modified = False
            self.status_var.set(f"Saved to {self.file_path}")
            messagebox.showinfo("Success", f"File saved!\nBackup created: {backup_path.name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def save_as(self):
        """Save to a different file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".FDI",
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")]
        )
        if filename:
            try:
                Path(filename).write_bytes(self.file_data)
                self.status_var.set(f"Saved as {filename}")
                messagebox.showinfo("Success", f"Saved as {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {str(e)}")
    
    def open_file(self):
        """Open a different file"""
        filename = filedialog.askopenfilename(
            filetypes=[("FDI files", "*.FDI"), ("All files", "*.*")]
        )
        if filename:
            self.file_path = filename
            self.load_data()

def main():
    root = tk.Tk()
    
    # Set theme (try to use a modern theme)
    style = ttk.Style()
    try:
        style.theme_use('clam')  # Modern looking theme
    except:
        pass
    
    app = PM99EditorGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()