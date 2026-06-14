import os
import sys
import subprocess
import string
import ctypes
import shutil
import time
import threading
from tkinter import ttk
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinterdnd2 import DND_FILES, TkinterDnD
import torrent_parser as tp

INSTANCE_NAME = "TFF"

# Windows-specific flag to completely suppress black terminal popups during background subprocess runs
CREATE_NO_WINDOW = 0x08000000

def is_running_as_admin():
    """Returns True if the script is running with administrative privileges, False otherwise."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

class TorrentLocatorsApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        if sys.platform == "win32":
            try:
                # Define the necessary Windows message constants
                WM_DROPFILES = 0x0233
                WM_COPYDATA = 0x004A
                WM_MSGFILTER_MIN = 0x0049  # Often passed as raw 0x0049 or 0x0047
                MSGFLT_ADD = 1
                
                # Punch holes in the User Interface Privilege Isolation (UIPI) filter
                ctypes.windll.user32.ChangeWindowMessageFilter(WM_DROPFILES, MSGFLT_ADD)
                ctypes.windll.user32.ChangeWindowMessageFilter(WM_COPYDATA, MSGFLT_ADD)
                ctypes.windll.user32.ChangeWindowMessageFilter(WM_MSGFILTER_MIN, MSGFLT_ADD)
            except Exception as e:
                print(f"Failed to bind UIPI exceptions: {e}")
        self.title(f"Torrent File Finder (Instance: {INSTANCE_NAME})")
        self.geometry("1280x720")
        self.center_window_on_screen()
        
        self.torrent_files = []
        self.drive_vars = {}
        self.is_multi_file = False
        self.root_node_id = None
        self.torrent_name = ""
        self.torrent_levels = 1
        self.current_torrent_path = ""  # Track the loaded .torrent file path
        
        # --- Strict Admin Check Intercept ---
        if not is_running_as_admin():
            messagebox.showerror(
                "Administrator Rights Required",
                "This application requires Administrative Privileges to run.\n\n"
                "The search engine needs low-level read access to NTFS tables\n"
                "to index your drives instantly.\n\n"
                "Please right-click the executable and select 'Run as administrator'."
            )
            self.destroy()
            sys.exit(0)
        
        # --- Environment Setup & Initialization ---
        self.setup_environment_paths()
        self.ensure_everything_is_running()
        self.build_ui()
        self.detect_ntfs_drives()
        
        self.protocol("WM_DELETE_WINDOW", self.on_exit_cleanup)
        
    def center_window_on_screen(self):
        """Initial screen centering for the main window layout."""
        self.update_idletasks()
        width = 1280
        height = 720
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def center_dialog(self, dialog, width, height):
        """Calculates coordinates to center a dialog window perfectly over the main app frame."""
        dialog.update_idletasks()
        
        # Pull current parent window coordinates and dimensions
        parent_x = self.winfo_x()
        parent_y = self.winfo_y()
        parent_width = self.winfo_width()
        parent_height = self.winfo_height()
        
        # Run placement offsets calculation
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)
        
        # Enforce boundary safety thresholds
        x = max(0, x)
        y = max(0, y)
        
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        
    def setup_environment_paths(self):
        appdata_roaming = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
        self.permanent_dir = os.path.normpath(os.path.join(appdata_roaming, "TorrentFileFinder"))
        os.makedirs(self.permanent_dir, exist_ok=True)
        
        self.everything_path = os.path.join(self.permanent_dir, "Everything.exe")
        self.es_path = os.path.join(self.permanent_dir, "es.exe")
        self.ini_path = os.path.join(self.permanent_dir, "Everything-TFF.ini")
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            bundle_dir = sys._MEIPASS
            
            embedded_everything = os.path.join(bundle_dir, "Everything.exe")
            embedded_es = os.path.join(bundle_dir, "es.exe")
            embedded_ini = os.path.join(bundle_dir, "Everything-TFF.ini")
            
            if not os.path.exists(self.everything_path) and os.path.exists(embedded_everything):
                try: shutil.copy2(embedded_everything, self.everything_path)
                except Exception as e: print(f"[Error] Staging error: {e}")
                    
            if not os.path.exists(self.es_path) and os.path.exists(embedded_es):
                try: shutil.copy2(embedded_es, self.es_path)
                except Exception as e: print(f"[Error] Staging error: {e}")
                    
            if not os.path.exists(self.ini_path) and os.path.exists(embedded_ini):
                try: shutil.copy2(embedded_ini, self.ini_path)
                except Exception as e: print(f"[Error] Staging error: {e}")
        else:
            if not os.path.exists(self.everything_path) and os.path.exists("Everything.exe"):
                shutil.copy2("Everything.exe", self.everything_path)
            if not os.path.exists(self.es_path) and os.path.exists("es.exe"):
                shutil.copy2("es.exe", self.es_path)
            if not os.path.exists(self.ini_path) and os.path.exists("Everything-TFF.ini"):
                shutil.copy2("Everything-TFF.ini", self.ini_path)

    def is_instance_responsive(self):
        try:
            if not os.path.exists(self.es_path):
                return False
            result = subprocess.run(
                [self.es_path, '-instance', INSTANCE_NAME, '-get-result-count'],
                capture_output=True, text=True, timeout=1.5,
                creationflags=CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def ensure_everything_is_running(self):
        if not os.path.exists(self.es_path) or not os.path.exists(self.everything_path):
            messagebox.showerror(
                "Dependency Missing", 
                f"Missing binaries inside location:\n{self.permanent_dir}"
            )
            self.destroy()
            return

        if not self.is_instance_responsive():
            subprocess.Popen(
                [self.everything_path, '-instance', INSTANCE_NAME, '-startup'], 
                creationflags=subprocess.DETACHED_PROCESS | CREATE_NO_WINDOW
            )
            for _ in range(10):
                time.sleep(0.5)
                if self.is_instance_responsive():
                    return

    def on_exit_cleanup(self):
        if os.path.exists(self.everything_path) and self.is_instance_responsive():
            try:
                subprocess.run(
                    [self.everything_path, '-instance', INSTANCE_NAME, '-exit'], 
                    capture_output=True, 
                    creationflags=CREATE_NO_WINDOW
                )
            except Exception as e:
                print(f"Cleanup warning: {e}")
        self.destroy()

    def build_ui(self):
        self.drop_frame = tk.LabelFrame(
            self, text=" Load Torrent File ", 
            bg="#2c3e50", fg="white", font=("Arial", 11, "bold"), bd=2, relief="groove"
        )
        self.drop_frame.pack(fill="x", padx=5, pady=5)
        
        inner_drop = tk.Frame(self.drop_frame, bg="#2c3e50")
        inner_drop.pack(pady=5)

        self.drop_label = tk.Label(
            inner_drop, text="Use this button to load a torrent file: ", 
            bg="#2c3e50", fg="white", font=("Arial", 12)
        )
        self.drop_label.pack(side="left")

        self.browse_btn = tk.Button(
            inner_drop, text="Browse File", bg="#34495e", fg="white", 
            relief="raised", font=("Arial", 10, "bold"), command=self.browse_torrent_file
        )
        self.browse_btn.pack(side="left")
        
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self.handle_drop)

        drive_frame = tk.LabelFrame(self, text="Select NTFS Drives to search", padx=5, pady=5)
        drive_frame.pack(fill="x", padx=5, pady=5)
        
        self.drives_container = tk.Frame(drive_frame)
        self.drives_container.pack(anchor="w")

        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        self.tree = ttk.Treeview(tree_frame, columns=("Size", "Status"), show="tree headings")
        self.tree.heading("#0", text="Folder Structure / Filename", anchor="w")
        self.tree.heading("Size", text="Size (Bytes)", anchor="w")
        self.tree.heading("Status", text="Search Result", anchor="w")
        self.tree.column("#0", width=650)
        self.tree.column("Size", width=140, stretch=False)
        self.tree.column("Status", width=400)
        
        self.tree.tag_configure("structure_match", foreground="#2ecc71")
        self.tree.tag_configure("pending", foreground="#7f8c8d")
        
        # --- Context Menu Binding ---
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Copy Name", command=self.copy_context_name)
        self.context_menu.add_command(label="Copy Size", command=self.copy_context_size)
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.start_btn = tk.Button(
            self, text="Start Search", 
            bg="#2ecc71", fg="white", font=("Arial", 12, "bold"),
            command=self.trigger_background_search, state="disabled",
            disabledforeground="#7f8c8d",
            background="#bdc3c7"
        )
        self.start_btn.pack(fill="x", padx=5, pady=5)

    # --- Right Click Context Actions ---
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def copy_context_name(self):
        selected_item = self.tree.selection()
        if selected_item:
            name = self.tree.item(selected_item[0], "text")
            self.clipboard_clear()
            self.clipboard_append(name)

    def copy_context_size(self):
        selected_item = self.tree.selection()
        if selected_item:
            values = self.tree.item(selected_item[0], "values")
            if values:
                size = values[0]
                self.clipboard_clear()
                self.clipboard_append(size)

    def detect_ntfs_drives(self):
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:"
                file_system_buf = ctypes.create_unicode_buffer(261)
                ctypes.windll.kernel32.GetVolumeInformationW(
                    f"{drive}\\", None, 0, None, None, None, file_system_buf, len(file_system_buf)
                )
                if file_system_buf.value == "NTFS":
                    var = tk.BooleanVar(value=True)
                    self.drive_vars[drive] = var
                    cb = tk.Checkbutton(self.drives_container, text=f"{drive}", variable=var)
                    cb.pack(side="left", padx=5)
            bitmask >>= 1

    def browse_torrent_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Torrent File",
            filetypes=[("Torrent Files", "*.torrent"), ("All Files", "*.*")]
        )
        if file_path:
            self.process_selected_file(file_path)

    def handle_drop(self, event):
        file_path = event.data.strip('{}')
        self.process_selected_file(file_path)

    def process_selected_file(self, file_path):
        if file_path.lower().endswith('.torrent'):
            try:
                self.current_torrent_path = os.path.normpath(file_path)
                self.parse_torrent(file_path)
                self.start_btn.config(state="normal", bg="#2ecc71", fg="white")
                self.drop_frame.config(text=f" Loaded: {os.path.basename(file_path)} ", bg="#16a085")
                self.drop_label.config(bg="#16a085", text=f"Active File: {os.path.basename(file_path)}  ")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to parse torrent file:\n{str(e)}")

    def parse_torrent(self, torrent_path):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.torrent_files = []
        self.root_node_id = None

        torrent_data = tp.parse_torrent_file(torrent_path)
        info = torrent_data.get('info', {})
        self.torrent_name = info.get('name')
        
        if 'files' in info:
            self.is_multi_file = True
            self.root_node_id = self.tree.insert("", "end", text=self.torrent_name, open=True, tags=("pending",))
            
            for f in info['files']:
                length = f.get('length')
                path_parts = f.get('path')
                item_levels = len(path_parts)
                
                current_node = self.root_node_id
                for part in path_parts[:-1]:
                    found = False
                    for child in self.tree.get_children(current_node):
                        if self.tree.item(child, "text") == part:
                            current_node = child
                            found = True
                            break
                    if not found:
                        current_node = self.tree.insert(current_node, "end", text=part, open=True, tags=("pending",))
                
                filename = path_parts[-1]
                node_id = self.tree.insert(current_node, "end", text=filename, values=(length, "Pending..."), tags=("pending",))
                
                relative_path = os.path.join(*path_parts)
                self.torrent_files.append({
                    "node_id": node_id, 
                    "filename": filename, 
                    "size": length,
                    "rel_path": relative_path,
                    "found_path": None,
                    "is_structured": False,
                    "levels": item_levels
                })
        else:
            self.is_multi_file = False
            length = info.get('length')
            node_id = self.tree.insert("", "end", text=self.torrent_name, values=(length, "Pending..."), tags=("pending",))
            self.torrent_files.append({
                "node_id": node_id, 
                "filename": self.torrent_name, 
                "size": length,
                "rel_path": self.torrent_name,
                "found_path": None,
                "is_structured": False,
                "levels": 0
            })

    def trigger_background_search(self):
        self.start_btn.config(
            state="disabled", 
            text="Searching Database (Please Wait)...",
            bg="#bdc3c7",         
            fg="#7f8c8d",
            activebackground="#bdc3c7",
            activeforeground="#7f8c8d"
        )
        self.tree.focus_set()
        self.update_idletasks()
        
        search_thread = threading.Thread(target=self.start_search, daemon=True)
        search_thread.start()

    def start_search(self):
        self.ensure_everything_is_running()

        selected_drives = [drive.lower() for drive, var in self.drive_vars.items() if var.get()]
        if not selected_drives:
            messagebox.showwarning("Warning", "Please select at least one drive to search.")
            self.start_btn.config(state="normal", text="Start Search", bg="#2ecc71", fg="white")
            return

        print(f"\n=== HYBRID SMART SEARCH ACTIVE [{INSTANCE_NAME}] ===")
        discovered_parent_dir = None
        total_found_count = 0
        
        for item in self.torrent_files:
            filename = item["filename"]
            size = item["size"]
            rel_path = item["rel_path"]
            item_levels = item["levels"]
            
            cmd = [self.es_path, '-instance', INSTANCE_NAME, '-n', '5', f'size:{size}', filename]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    creationflags=CREATE_NO_WINDOW
                )
                matches = result.stdout.strip().split('\n')
                
                for match in matches:
                    if not match: continue
                    drive_letter = os.path.splitdrive(match)[0].lower()
                    if drive_letter not in selected_drives: continue
                        
                    normalized_match = os.path.normpath(match)
                    expected_suffix = os.path.normpath(os.path.join(self.torrent_name, rel_path))
                    if normalized_match.endswith(expected_suffix):
                        upward_walk = normalized_match
                        for _ in range(item_levels + 1):
                            upward_walk = os.path.dirname(upward_walk)
                        discovered_parent_dir = upward_walk
                        print(f"[Smart Anchor] Absolute parental root verified at: {discovered_parent_dir}")
                        break
            except Exception as e:
                print(f"Anchor scan error: {e}")
            if discovered_parent_dir:
                break

        for item in self.torrent_files:
            filename = item["filename"]
            size = item["size"]
            node_id = item["node_id"]
            rel_path = item["rel_path"]
            
            self.tree.set(node_id, "Status", "Searching...")
            
            if discovered_parent_dir:
                predicted_path = os.path.normpath(os.path.join(discovered_parent_dir, self.torrent_name, rel_path))
                if os.path.exists(predicted_path) and os.path.getsize(predicted_path) == size:
                    drive_letter = os.path.splitdrive(predicted_path)[0].lower()
                    if drive_letter in selected_drives:
                        item["found_path"] = predicted_path
                        total_found_count += 1
                        item["is_structured"] = True
                        self.tree.set(node_id, "Status", f"[✔ Structure Match]: {predicted_path}")
                        self.tree.item(node_id, tags=("structure_match",))
                        continue

            cmd = [self.es_path, '-instance', INSTANCE_NAME, '-n', '1', f'size:{size}', filename]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                    creationflags=CREATE_NO_WINDOW
                )
                match = result.stdout.strip()
                
                if match:
                    drive_letter = os.path.splitdrive(match)[0].lower()
                    if drive_letter in selected_drives:
                        item["found_path"] = match
                        total_found_count += 1
                        normalized_match = os.path.normpath(match)
                        
                        if discovered_parent_dir:
                            expected_path = os.path.normpath(os.path.join(discovered_parent_dir, self.torrent_name, rel_path))
                            if normalized_match == expected_path:
                                item["is_structured"] = True
                                self.tree.set(node_id, "Status", f"[✔ Structure Match]: {match}")
                                self.tree.item(node_id, tags=("structure_match",))
                            else:
                                self.tree.set(node_id, "Status", f"Found (Out of Structure): {match}")
                                self.tree.item(node_id, tags=("structure_match",)) # Paint green even out of structure
                        else:
                            self.tree.set(node_id, "Status", f"Found: {match}")
                            self.tree.item(node_id, tags=("structure_match",)) # Paint green on single/flat match configurations
                    else:
                        self.tree.set(node_id, "Status", "Not Found on Selected Drives")
                else:
                    self.tree.set(node_id, "Status", "Not Found")
            except Exception as e:
                print(f"Execution Error: {e}")
                self.tree.set(node_id, "Status", "Error")

        print("=== END OF QUERY SEQUENCING ===\n")
        self.after(0, self.evaluate_search_results, total_found_count, discovered_parent_dir)

    def evaluate_search_results(self, total_found, discovered_parent_dir):
        self.start_btn.config(
            state="normal", 
            text="Start Search",
            bg="#2ecc71",         
            fg="white"            
        )
        found_items = [item for item in self.torrent_files if item["found_path"] is not None]
        
        if total_found == 0:
            messagebox.showinfo("Search Complete", "No torrent content files were found on selected drives.")
            return

        if not self.is_multi_file and total_found == 1:
            matching_root = os.path.dirname(self.torrent_files[0]["found_path"])
            self.show_seeding_success_modal(matching_root, is_partial=False)
            return

        all_found_are_structured = all(item["is_structured"] for item in found_items)

        if self.is_multi_file and total_found == len(self.torrent_files) and all_found_are_structured:
            self.tree.item(self.root_node_id, tags=("structure_match",))
            self.color_subfolders_green(self.root_node_id)
            self.show_seeding_success_modal(discovered_parent_dir, is_partial=False)
            return

        if self.is_multi_file and total_found < len(self.torrent_files) and all_found_are_structured and discovered_parent_dir:
            self.show_seeding_success_modal(discovered_parent_dir, is_partial=True)
            return

        if self.is_multi_file and total_found > 0:
            self.prompt_relocation_workflow()

    def prompt_relocation_workflow(self):
        reloc_win = tk.Toplevel(self)
        reloc_win.title("Structure Mismatch Discovered")
        self.center_dialog(reloc_win, 500, 180)
        
        reloc_win.resizable(False, False)
        reloc_win.grab_set()
       
        lbl = tk.Label(
            reloc_win, 
            text="Files were found, but their folder layout doesn't match the torrent.\n"
                 "Would you like to automatically reconstruct the directory layout?", 
            font=("Arial", 10), justify="center", pady=30
        )
        lbl.pack()

        btn_frame = tk.Frame(reloc_win)
        btn_frame.pack(pady=5)

        def select_op(mode):
            reloc_win.destroy()
            self.execute_relocation_engine(mode)

        tk.Button(btn_frame, text="Copy Files...", width=15, bg="#2ecc71", fg="white", command=lambda: select_op("copy")).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Move Files...", width=15, bg="#f2ab5e", fg="white", command=lambda: select_op("move")).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", width=12, command=reloc_win.destroy).pack(side="left", padx=5)

    def execute_relocation_engine(self, mode):
        target_root = filedialog.askdirectory(title="Select Destination Folder to Build Blueprint Inside")
        if not target_root: return

        seeding_path = os.path.normpath(target_root)
        try:
            for item in self.torrent_files:
                src_path = item["found_path"]
                if not src_path: continue
                    
                rel_path = item["rel_path"]
                node_id = item["node_id"]
                
                dest_path = os.path.join(seeding_path, self.torrent_name, rel_path)
                dest_dir = os.path.dirname(dest_path)
                
                os.makedirs(dest_dir, exist_ok=True)
                
                if mode == "copy":
                    self.tree.set(node_id, "Status", "Copying...")
                    self.update_idletasks()
                    shutil.copy2(src_path, dest_path)
                elif mode == "move":
                    self.tree.set(node_id, "Status", "Moving...")
                    self.update_idletasks()
                    shutil.move(src_path, dest_path)
                
                self.tree.set(node_id, "Status", f"[✔ Structure Match]: {dest_path}")
                self.tree.item(node_id, tags=("structure_match",))

            messagebox.showinfo("Success", "Files successfully relocated to matching structure.")
            self.show_seeding_success_modal(seeding_path, is_partial=False)
        except Exception as e:
            messagebox.showerror("IO Processing Error", f"Failed to complete disk operations:\n{e}")

    def show_seeding_success_modal(self, path_string, is_partial=False):
        modal = tk.Toplevel(self)
        modal.title("Ready to Seed")
        
        # Determine dynamic width sizing depending on qBittorrent option availability
        appdata_roaming = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
        qbittorrent_exe = os.path.join(appdata_roaming, "qBittorrent", "qbittorrent.exe")
        qb_exists = os.path.exists(qbittorrent_exe)
        
        window_width = 760 if qb_exists else 620
        self.center_dialog(modal, window_width, 170)
        
        modal.resizable(False, False)
        modal.grab_set()    

        if is_partial:
            msg_text = f"You are missing some files, but you can start seeding the ones you have\nusing this download path: \"{path_string}\"\n\nWARNING: If you add this torrent, the client will attempt to download the missing files."
        else:
            msg_text = f"You can start seeding this torrent by setting the download path to:\n\n\"{path_string}\""
        
        lbl = tk.Label(modal, text=msg_text, font=("Arial", 10), justify="center", wraplength=window_width - 50, pady=20)
        lbl.pack()

        btn_frame = tk.Frame(modal)
        btn_frame.pack(pady=5)

        def copy_to_clipboard():
            self.clipboard_clear()
            self.clipboard_append(path_string)
            self.update()
            copy_btn.config(text="Copied!", state="disabled")

        def start_qbittorrent_seeding():
            if not self.current_torrent_path:
                messagebox.showerror("Error", "Missing dynamic context pointer for original .torrent source file.")
                return
            
            cmd = [
                qbittorrent_exe,
                "--category=TFF",
                "--skip-dialog=true",
                "--add-stopped=false",
                f"--save-path={path_string}",
                self.current_torrent_path
            ]
            try:
                subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS | CREATE_NO_WINDOW)
                modal.destroy()
            except Exception as e:
                messagebox.showerror("Execution Fault", f"Could not launch qBittorrent container:\n{e}")

        copy_btn = tk.Button(btn_frame, text="Copy Path", width=14, bg="#2ecc71", fg="white", command=copy_to_clipboard)
        copy_btn.pack(side="left", padx=5)
        
        if qb_exists:
            qb_btn = tk.Button(btn_frame, text="Add to qBittorrent", width=18, bg="#3498db", fg="white", command=start_qbittorrent_seeding)
            qb_btn.pack(side="left", padx=5)
        
        tk.Button(btn_frame, text="OK", width=12, command=modal.destroy).pack(side="left", padx=5)

    def color_subfolders_green(self, parent_node):
        for child in self.tree.get_children(parent_node):
            if self.tree.get_children(child):
                self.tree.item(child, tags=("structure_match",))
                self.color_subfolders_green(child)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    app = TorrentLocatorsApp()
    app.mainloop()