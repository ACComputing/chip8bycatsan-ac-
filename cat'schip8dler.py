#!/usr/bin/env python3
"""
chip8-warev0.py - A simple Chip‑8 code viewer/disassembler with export.
Opens a binary Chip‑8 file, disassembles it, and displays the mnemonics.
You can edit the text and export it to a file.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import os

class Chip8WareApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chip‑8 Ware v0")
        self.root.geometry("800x600")

        # Current file path (for export default)
        self.current_file = None

        # Build the UI
        self.create_menu()
        self.create_text_area()
        self.create_status_bar()

        # Keyboard shortcuts
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.export_file())
        self.root.bind("<Control-q>", lambda e: self.quit_app())

    def create_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open", accelerator="Ctrl+O", command=self.open_file)
        file_menu.add_command(label="Export", accelerator="Ctrl+S", command=self.export_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Ctrl+Q", command=self.quit_app)
        menubar.add_cascade(label="File", menu=file_menu)

        about_menu = tk.Menu(menubar, tearoff=0)
        about_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=about_menu)

        self.root.config(menu=menubar)

    def create_text_area(self):
        """Create a scrollable text widget for displaying/editing the disassembly."""
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=1)

        self.text_area = scrolledtext.ScrolledText(
            frame, wrap=tk.NONE, font=("Courier New", 10)
        )
        self.text_area.pack(fill=tk.BOTH, expand=1)

        # Optional syntax highlighting? (not implemented for simplicity)
        # self.text_area.tag_configure("comment", foreground="gray")

    def create_status_bar(self):
        """Status bar at the bottom showing file info."""
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ----------------------------------------------------------------------
    # Chip‑8 disassembler
    # ----------------------------------------------------------------------
    def disassemble(self, data, start_addr=0x200):
        """
        Convert binary Chip‑8 data into a list of disassembly lines.
        Each line: "ADDR: MNEMONICS"
        """
        lines = []
        addr = start_addr
        i = 0
        while i + 1 < len(data):
            # Read two bytes (big‑endian)
            op = (data[i] << 8) | data[i+1]
            mnemonic = self.decode_opcode(op, addr)
            lines.append(f"{addr:04X}:  {mnemonic}")
            addr += 2
            i += 2
        # If there is a trailing byte, show it as data
        if i < len(data):
            lines.append(f"{addr:04X}:  .byte 0x{data[i]:02X}  (odd trailing byte)")
        return lines

    def decode_opcode(self, op, addr):
        """Return a mnemonic string for the given 16‑bit Chip‑8 opcode."""
        # Extract nibbles
        nibble1 = (op & 0xF000) >> 12
        nibble2 = (op & 0x0F00) >> 8
        nibble3 = (op & 0x00F0) >> 4
        nibble4 = op & 0x000F

        addr12 = op & 0x0FFF
        x = nibble2
        y = nibble3
        kk = op & 0x00FF
        n = nibble4

        # 0nnn - SYS (ignored in most interpreters)
        if nibble1 == 0x0:
            if op == 0x00E0:
                return "CLS"
            elif op == 0x00EE:
                return "RET"
            else:
                return f"SYS 0x{addr12:03X}"

        # 1nnn - JP addr
        elif nibble1 == 0x1:
            return f"JP 0x{addr12:03X}"

        # 2nnn - CALL addr
        elif nibble1 == 0x2:
            return f"CALL 0x{addr12:03X}"

        # 3xkk - SE Vx, byte
        elif nibble1 == 0x3:
            return f"SE V{x:X}, 0x{kk:02X}"

        # 4xkk - SNE Vx, byte
        elif nibble1 == 0x4:
            return f"SNE V{x:X}, 0x{kk:02X}"

        # 5xy0 - SE Vx, Vy
        elif nibble1 == 0x5 and nibble4 == 0x0:
            return f"SE V{x:X}, V{y:X}"

        # 6xkk - LD Vx, byte
        elif nibble1 == 0x6:
            return f"LD V{x:X}, 0x{kk:02X}"

        # 7xkk - ADD Vx, byte
        elif nibble1 == 0x7:
            return f"ADD V{x:X}, 0x{kk:02X}"

        # 8xy0 - LD Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x0:
            return f"LD V{x:X}, V{y:X}"

        # 8xy1 - OR Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x1:
            return f"OR V{x:X}, V{y:X}"

        # 8xy2 - AND Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x2:
            return f"AND V{x:X}, V{y:X}"

        # 8xy3 - XOR Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x3:
            return f"XOR V{x:X}, V{y:X}"

        # 8xy4 - ADD Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x4:
            return f"ADD V{x:X}, V{y:X}"

        # 8xy5 - SUB Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x5:
            return f"SUB V{x:X}, V{y:X}"

        # 8xy6 - SHR Vx {, Vy}  (commonly just SHR Vx)
        elif nibble1 == 0x8 and nibble4 == 0x6:
            return f"SHR V{x:X}"

        # 8xy7 - SUBN Vx, Vy
        elif nibble1 == 0x8 and nibble4 == 0x7:
            return f"SUBN V{x:X}, V{y:X}"

        # 8xyE - SHL Vx {, Vy}
        elif nibble1 == 0x8 and nibble4 == 0xE:
            return f"SHL V{x:X}"

        # 9xy0 - SNE Vx, Vy
        elif nibble1 == 0x9 and nibble4 == 0x0:
            return f"SNE V{x:X}, V{y:X}"

        # Annn - LD I, addr
        elif nibble1 == 0xA:
            return f"LD I, 0x{addr12:03X}"

        # Bnnn - JP V0, addr
        elif nibble1 == 0xB:
            return f"JP V0, 0x{addr12:03X}"

        # Cxkk - RND Vx, byte
        elif nibble1 == 0xC:
            return f"RND V{x:X}, 0x{kk:02X}"

        # Dxyn - DRW Vx, Vy, n
        elif nibble1 == 0xD:
            return f"DRW V{x:X}, V{y:X}, 0x{n:X}"

        # Ex9E - SKP Vx
        elif nibble1 == 0xE and kk == 0x9E:
            return f"SKP V{x:X}"

        # ExA1 - SKNP Vx
        elif nibble1 == 0xE and kk == 0xA1:
            return f"SKNP V{x:X}"

        # Fx07 - LD Vx, DT
        elif nibble1 == 0xF and kk == 0x07:
            return f"LD V{x:X}, DT"

        # Fx0A - LD Vx, K
        elif nibble1 == 0xF and kk == 0x0A:
            return f"LD V{x:X}, K"

        # Fx15 - LD DT, Vx
        elif nibble1 == 0xF and kk == 0x15:
            return f"LD DT, V{x:X}"

        # Fx18 - LD ST, Vx
        elif nibble1 == 0xF and kk == 0x18:
            return f"LD ST, V{x:X}"

        # Fx1E - ADD I, Vx
        elif nibble1 == 0xF and kk == 0x1E:
            return f"ADD I, V{x:X}"

        # Fx29 - LD F, Vx
        elif nibble1 == 0xF and kk == 0x29:
            return f"LD F, V{x:X}"

        # Fx33 - LD B, Vx
        elif nibble1 == 0xF and kk == 0x33:
            return f"LD B, V{x:X}"

        # Fx55 - LD [I], Vx   (stores V0..Vx)
        elif nibble1 == 0xF and kk == 0x55:
            return f"LD [I], V{x:X}"

        # Fx65 - LD Vx, [I]   (reads V0..Vx)
        elif nibble1 == 0xF and kk == 0x65:
            return f"LD V{x:X}, [I]"

        else:
            return f".word 0x{op:04X}   ; unknown opcode"

    # ----------------------------------------------------------------------
    # File operations
    # ----------------------------------------------------------------------
    def open_file(self):
        """Open a binary Chip‑8 file and display its disassembly."""
        file_path = filedialog.askopenfilename(
            title="Open Chip‑8 binary",
            filetypes=[("Chip‑8 files", "*.ch8"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                data = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"Could not read file:\n{e}")
            return

        # Disassemble
        lines = self.disassemble(data)
        text = "\n".join(lines)

        # Clear and insert into text area
        self.text_area.delete(1.0, tk.END)
        self.text_area.insert(tk.END, text)

        # Update status and current file
        self.current_file = file_path
        self.status_var.set(f"Loaded: {os.path.basename(file_path)} ({len(data)} bytes)")

    def export_file(self):
        """Export the current content of the text area to a file."""
        if not self.text_area.get(1.0, tk.END).strip():
            messagebox.showwarning("Warning", "Nothing to export.")
            return

        # Suggest a default filename based on current file if any
        initial_file = ""
        if self.current_file:
            base = os.path.splitext(self.current_file)[0]
            initial_file = base + ".txt"
        else:
            initial_file = "disassembly.txt"

        file_path = filedialog.asksaveasfilename(
            title="Export disassembly",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=os.path.basename(initial_file)
        )
        if not file_path:
            return

        try:
            content = self.text_area.get(1.0, tk.END)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror("Error", f"Could not write file:\n{e}")
            return

        self.status_var.set(f"Exported to: {os.path.basename(file_path)}")

    def quit_app(self):
        """Quit the application."""
        self.root.quit()

    def show_about(self):
        """Show an about dialog."""
        messagebox.showinfo(
            "About Chip‑8 Ware v0",
            "A simple Chip‑8 code viewer/disassembler.\n\n"
            "Open a .ch8 binary file to see its disassembly.\n"
            "You can edit the text and export it as a plain text file.\n\n"
            "Chip‑8 opcodes are decoded using the standard set."
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = Chip8WareApp(root)
    root.mainloop()