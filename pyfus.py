import sys
import os
import subprocess

# --- AUTOMATIC DEPENDENCY BOOTSTRAPPER ---
required_libs = ["customtkinter", "psutil"]
missing_libs = []
for lib in required_libs:
    try:
        __import__(lib)
    except ImportError:
        missing_libs.append(lib)

if missing_libs:
    print(f"[*] Linux system setup: Installing missing libraries {missing_libs}...")
    try:
        cmd = [sys.executable, "-m", "pip", "install"] + missing_libs + ["--break-system-packages"]
        subprocess.check_call(cmd)
    except Exception as e:
        print(f"[!] Auto-install failed: {e}. Attempting native fallback...")
        print("Please manually run: sudo apt install python3-customtkinter python3-psutil")
        sys.exit(1)

import customtkinter as ctk
import psutil
import threading
import re
import json
from tkinter import messagebox

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PyfusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Pyfus - Dedicated Linux USB Flasher")
        self.geometry("540x610")
        self.resizable(False, False)
        
        # State variables
        self.iso_path = ctk.StringVar()
        self.selected_drive = ctk.StringVar()
        self.partition_scheme = ctk.StringVar(value="gpt")
        self.target_system = ctk.StringVar(value="uefi")
        self.is_flashing = False
        self.usb_drives_data = {}

        self.setup_ui()
        self.refresh_drives()

    def setup_ui(self):
        # --- 1. ISO Selection ---
        iso_frame = ctk.CTkFrame(self, corner_radius=10)
        iso_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(iso_frame, text="1. Select Bootable ISO Image (Type, Paste, or Browse)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))
        
        iso_inner = ctk.CTkFrame(iso_frame, fg_color="transparent")
        iso_inner.pack(fill="x", padx=15, pady=(0, 10))
        
        self.path_entry = ctk.CTkEntry(iso_inner, textvariable=self.iso_path, placeholder_text="/home/username/Downloads/linux.iso")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(iso_inner, text="Browse", width=90, command=self.browse_iso).pack(side="right")

        # --- 2. Device Selection ---
        device_frame = ctk.CTkFrame(self, corner_radius=10)
        device_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(device_frame, text="2. Target USB Drive", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))
        
        dev_inner = ctk.CTkFrame(device_frame, fg_color="transparent")
        dev_inner.pack(fill="x", padx=15, pady=(0, 15))
        self.drive_dropdown = ctk.CTkOptionMenu(dev_inner, variable=self.selected_drive, values=["Scanning storage..."])
        self.drive_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(dev_inner, text="Refresh", width=90, fg_color="#333333", hover_color="#444444", command=self.refresh_drives).pack(side="right")

        # --- 3. Rufus Linux Optimization Parameters ---
        opts_frame = ctk.CTkFrame(self, corner_radius=10)
        opts_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(opts_frame, text="3. Advanced Partition Configuration", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))
        
        grid_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        grid_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # Partition Layout Group
        ctk.CTkLabel(grid_frame, text="Partition scheme:").grid(row=0, column=0, sticky="w", pady=8)
        ctk.CTkRadioButton(grid_frame, text="MBR (Legacy compatibility)", variable=self.partition_scheme, value="mbr").grid(row=0, column=1, padx=20, sticky="w")
        ctk.CTkRadioButton(grid_frame, text="GPT (Modern Layout)", variable=self.partition_scheme, value="gpt").grid(row=0, column=2, padx=20, sticky="w")
        
        # Target System Architecture Group
        ctk.CTkLabel(grid_frame, text="Target system:").grid(row=1, column=0, sticky="w", pady=8)
        ctk.CTkRadioButton(grid_frame, text="BIOS (or UEFI-CSM)", variable=self.target_system, value="bios").grid(row=1, column=1, padx=20, sticky="w")
        ctk.CTkRadioButton(grid_frame, text="UEFI (non CSM)", variable=self.target_system, value="uefi").grid(row=1, column=2, padx=20, sticky="w")

        # --- 4. Progress Hub ---
        exec_frame = ctk.CTkFrame(self, fg_color="transparent")
        exec_frame.pack(fill="x", padx=20, pady=10)

        self.progress_bar = ctk.CTkProgressBar(exec_frame, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=5)

        self.status_label = ctk.CTkLabel(exec_frame, text="Status: Ready", font=ctk.CTkFont(size=12, slant="italic"))
        self.status_label.pack(anchor="w", pady=2)

        self.start_btn = ctk.CTkButton(exec_frame, text="START EXTRACTION & FLASH", font=ctk.CTkFont(weight="bold", size=14), height=45, fg_color="#d9534f", hover_color="#c9302c", command=self.confirm_and_start)
        self.start_btn.pack(fill="x", pady=10)

    def browse_iso(self):
        """Forces the file explorer to run as your native user identity, uncovering all hidden directories."""
        real_user = os.environ.get("SUDO_USER", "root")
        user_home = f"/home/{real_user}" if real_user != "root" else "/root"
        
        # Base zenity call command configuration
        zenity_cmd = ["zenity", "--file-selection", f"--filename={user_home}/", "--title=Select Bootable ISO (Unlocked)"]
        
        # If running via sudo, drop privileges back down to the target user identity to map files accurately
        if real_user != "root":
            cmd = ["sudo", "-u", real_user, "env", f"DISPLAY={os.environ.get('DISPLAY', ':0')}", f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}"] + zenity_cmd
        else:
            cmd = zenity_cmd

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            file_path = result.stdout.strip()
            if file_path and os.path.exists(file_path):
                self.iso_path.set(file_path)
                return
        except Exception:
            pass

        # Native fallback selection layer running under user privileges
        kdialog_cmd = ["kdialog", "--getopenfilename", user_home, "", "--title", "Select Bootable ISO"]
        if real_user != "root":
            cmd = ["sudo", "-u", real_user, "env", f"DISPLAY={os.environ.get('DISPLAY', ':0')}", f"XAUTHORITY={os.environ.get('XAUTHORITY', '')}"] + kdialog_cmd
        else:
            cmd = kdialog_cmd

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            file_path = result.stdout.strip()
            if file_path:
                self.iso_path.set(file_path)
                return
        except Exception:
            pass

        # Final terminal backup instructions if desktop rendering engines stall completely
        messagebox.showinfo("Manual Path Entry", "System dialog permissions locked. Please paste or drag-and-drop the ISO file path directly into the text entry field container.")

    def refresh_drives(self):
        try:
            cmd = ["lsblk", "-d", "-o", "NAME,SIZE,MODEL,RM", "--json"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            
            drive_list = []
            self.usb_drives_data.clear()

            for device in data.get("blockdevices", []):
                if (device.get("rm") in (True, "1", 1)) and not device['name'].startswith(('loop', 'zram')):
                    dev_path = f"/dev/{device['name']}"
                    label = f"{dev_path} - {device.get('model', 'Unknown').strip()} ({device.get('size', 'N/A')})"
                    drive_list.append(label)
                    self.usb_drives_data[label] = dev_path

            if drive_list:
                self.drive_dropdown.configure(values=drive_list)
                self.selected_drive.set(drive_list[0])
            else:
                self.drive_dropdown.configure(values=["No Linux USB drives found"])
                self.selected_drive.set("No Linux USB drives found")
        except Exception as e:
            messagebox.showerror("Error", f"Linux storage mapping system failed:\n{str(e)}")

    def confirm_and_start(self):
        if self.is_flashing: return
        
        raw_path = self.iso_path.get().strip()
        clean_path = raw_path.strip("'\"")
        self.iso_path.set(clean_path)

        iso = clean_path
        drive_label = self.selected_drive.get()

        if not iso or not os.path.exists(iso):
            messagebox.showerror("Error", f"Cannot access file position location:\n{iso}\nPlease check path accuracy.")
            return
        if drive_label not in self.usb_drives_data:
            messagebox.showerror("Error", "Please select a valid hardware device target.")
            return

        target_dev = self.usb_drives_data[drive_label]
        confirm = messagebox.askyesno(
            "⚠️ DATA DESTRUCTION WARNING",
            f"ALL DATA ON '{drive_label}' WILL BE WIPED FOREVER!\n\n"
            "Pyfus will now force-unmount and partition the raw blocks. Continue?", icon="warning"
        )
        if confirm:
            self.is_flashing = True
            self.start_btn.configure(state="disabled", fg_color="#555555")
            self.drive_dropdown.configure(state="disabled")
            threading.Thread(target=self.flash_worker, args=(iso, target_dev), daemon=True).start()

    def flash_worker(self, iso_path, drive_path):
        try:
            self.status_label.configure(text="Status: Forcing absolute system drive lockdown...")
            subprocess.run(["fuser", "-f", "-k", f"{drive_path}*"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, shell=True)
            subprocess.run(["udisksctl", "unmount", "-b", f"{drive_path}1"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["umount", "-f", f"{drive_path}*"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, shell=True)
            
            drive_name = drive_path.split("/")[-1]
            subprocess.run(["dmsetup", "remove", f"{drive_name}*"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, shell=True)
            subprocess.run(["wipefs", "-a", "-f", drive_path], check=True)

            self.status_label.configure(text="Status: Allocating partition layout geometries...")
            table_type = "msdos" if self.partition_scheme.get() == "mbr" else "gpt"
            
            subprocess.run(["parted", drive_path, "mklabel", table_type, "-s"], check=True)
            subprocess.run(["parted", drive_path, "mkpart", "primary", "fat32", "1MiB", "100%"], check=True)
            
            if self.target_system.get() == "uefi":
                subprocess.run(["parted", drive_path, "set", "1", "esp", "on"], check=True)
            else:
                subprocess.run(["parted", drive_path, "set", "1", "boot", "on"], check=True)

            self.status_label.configure(text="Status: Launching optimized dd image engine...")
            total_bytes = os.path.getsize(iso_path)
            
            cmd = ["dd", f"if={iso_path}", f"of={drive_path}", "bs=4M", "status=progress", "oflag=direct,sync"]
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    match = re.search(r"(\d+)\s+bytes", line)
                    if match:
                        bytes_copied = int(match.group(1))
                        percentage = bytes_copied / total_bytes
                        
                        self.progress_bar.set(percentage)
                        self.status_label.configure(text=f"Status: Copying image blocks... {percentage*100:.1f}%")
                        self.update_idletasks()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)

            self.status_label.configure(text="Status: Flushing OS cache memories to physical USB silicon...")
            subprocess.run(["sync"], check=True)

            self.progress_bar.set(1.0)
            self.status_label.configure(text="Status: Success! Drive ready to boot.")
            messagebox.showinfo("Success", "Linux Bootable USB Drive generated successfully!")

        except subprocess.CalledProcessError as e:
            messagebox.showerror("System Error", f"An internal Linux sub-process returned an error code:\n{str(e)}")
            self.status_label.configure(text="Status: Execution aborted due to system tool failure.")
        except Exception as e:
            messagebox.showerror("Unexpected Error", f"Fatal execution breakdown:\n{str(e)}")
            self.status_label.configure(text="Status: Process halted.")
        finally:
            self.is_flashing = False
            self.start_btn.configure(state="normal", fg_color="#d9534f")
            self.drive_dropdown.configure(state="normal")
            self.progress_bar.set(0)

if __name__ == "__main__":
    if os.getuid() != 0:
        print("[!] Privilege Error: Pyfus requires root execution to interact with system block layers.")
        print("    Please run: sudo ./pyfus")
        sys.exit(1)
        
    # --- AUTOMATIC DISPLAY SERVER BRIDGE ---
    real_user = os.environ.get("SUDO_USER")
    if real_user and real_user != "root":
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"
        if "XAUTHORITY" not in os.environ:
            os.environ["XAUTHORITY"] = f"/home/{real_user}/.Xauthority"

    app = PyfusApp()
    app.mainloop()
