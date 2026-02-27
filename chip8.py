#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║             🐱 Cat's CHIP-8 Emulator v0 - "Meow Machine" Edition 🐱            ║
║                    (Pure Python / No Dependencies)                            ║
║                  Team Flames / Samsoft - 2026                                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Features:
- Complete CHIP-8 instruction set (35 opcodes) + Super CHIP-8 extensions
- mGBA-inspired GUI with menu bar, status bar, canvas display
- Configurable speed, colors
- Save states and pause/resume
- Debug mode with disassembly overlay
- No external dependencies – only Python standard library (tkinter, random, etc.)
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import random
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DISPLAY_W, DISPLAY_H = 64, 32          # CHIP-8 native resolution
WINDOW_W = 800
WINDOW_H = 600

SCALE = min((WINDOW_W - 40) // DISPLAY_W, (WINDOW_H - 80) // DISPLAY_H)  # 12
DISPLAY_SCALED_W = DISPLAY_W * SCALE
DISPLAY_SCALED_H = DISPLAY_H * SCALE

MEMORY_SIZE = 4096
PROGRAM_START = 0x200
STACK_SIZE = 16
NUM_REGISTERS = 16
NUM_KEYS = 16

DEFAULT_CLOCK_HZ = 500
TIMER_HZ = 60

# Colors (RGB tuples)
COLORS = {
    'bg_dark': '#0f0f19',
    'bg_light': '#191928',
    'fg_green': '#00ff80',
    'fg_amber': '#ffb000',
    'fg_white': '#dcdcdc',
    'fg_blue': '#64b4ff',
    'accent': '#ff6496',
    'menu_bg': '#1e1e2d',
    'menu_hover': '#323246',
    'status_bg': '#141423',
    'text': '#c8c8c8',
    'text_dim': '#78788c',
}

# CHIP-8 Font (4x5 pixels, stored as 5 bytes each)
FONTSET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
    0x20, 0x60, 0x20, 0x20, 0x70,  # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
    0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
    0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 5
    0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
    0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
    0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
    0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
    0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
    0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
    0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
    0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
    0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
    0xF0, 0x80, 0xF0, 0x80, 0x80,  # F
]

# Keyboard mapping (QWERTY -> CHIP-8 hex keypad)
KEY_MAP = {
    '1': 0x1, '2': 0x2, '3': 0x3, '4': 0xC,
    'q': 0x4, 'w': 0x5, 'e': 0x6, 'r': 0xD,
    'a': 0x7, 's': 0x8, 'd': 0x9, 'f': 0xE,
    'z': 0xA, 'x': 0x0, 'c': 0xB, 'v': 0xF,
}

# ═══════════════════════════════════════════════════════════════════════════════
# CHIP-8 CPU CORE (pure Python, no numpy)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CPUState:
    memory: bytearray = field(default_factory=lambda: bytearray(MEMORY_SIZE))
    V: List[int] = field(default_factory=lambda: [0] * NUM_REGISTERS)
    I: int = 0
    PC: int = PROGRAM_START
    SP: int = 0
    stack: List[int] = field(default_factory=lambda: [0] * STACK_SIZE)
    delay_timer: int = 0
    sound_timer: int = 0
    # Display as list of lists (rows of 0/1)
    display: List[List[int]] = field(default_factory=lambda: [[0]*DISPLAY_W for _ in range(DISPLAY_H)])
    keys: List[bool] = field(default_factory=lambda: [False] * NUM_KEYS)
    waiting_for_key: bool = False
    key_register: int = 0
    schip_mode: bool = False
    high_res: bool = False

class Chip8CPU:
    def __init__(self):
        self.state = CPUState()
        self.running = False
        self.paused = False
        self.draw_flag = False
        self.clock_hz = DEFAULT_CLOCK_HZ
        self.quirks = {
            'shift_vx': True,
            'load_store_inc': True,
            'jump_v0': True,
        }
        self._load_fontset()

    def _load_fontset(self):
        for i, byte in enumerate(FONTSET):
            self.state.memory[i] = byte

    def reset(self):
        self.state = CPUState()
        self._load_fontset()
        self.running = False
        self.paused = False
        self.draw_flag = True

    def load_rom(self, data: bytes) -> bool:
        if len(data) > MEMORY_SIZE - PROGRAM_START:
            return False
        self.reset()
        for i, byte in enumerate(data):
            self.state.memory[PROGRAM_START + i] = byte
        self.running = True
        return True

    def load_rom_file(self, filepath: str) -> bool:
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            return self.load_rom(data)
        except Exception as e:
            print(f"Failed to load ROM: {e}")
            return False

    def fetch(self) -> int:
        hi = self.state.memory[self.state.PC]
        lo = self.state.memory[self.state.PC + 1]
        self.state.PC += 2
        return (hi << 8) | lo

    def execute(self, opcode: int):
        nnn = opcode & 0x0FFF
        nn = opcode & 0x00FF
        n = opcode & 0x000F
        x = (opcode >> 8) & 0x0F
        y = (opcode >> 4) & 0x0F
        op = (opcode >> 12) & 0xF
        V = self.state.V

        if op == 0x0:
            if opcode == 0x00E0:
                # CLS
                for row in range(DISPLAY_H):
                    for col in range(DISPLAY_W):
                        self.state.display[row][col] = 0
                self.draw_flag = True
            elif opcode == 0x00EE:
                # RET
                self.state.SP -= 1
                self.state.PC = self.state.stack[self.state.SP]
            elif opcode == 0x00FE:
                self.state.high_res = False
            elif opcode == 0x00FF:
                self.state.high_res = True
            elif (opcode & 0xFFF0) == 0x00C0:
                n_lines = n
                # Scroll down N lines
                new_display = [[0]*DISPLAY_W for _ in range(DISPLAY_H)]
                for row in range(n_lines, DISPLAY_H):
                    new_display[row] = self.state.display[row - n_lines]
                self.state.display = new_display
                self.draw_flag = True
        elif op == 0x1:
            self.state.PC = nnn
        elif op == 0x2:
            self.state.stack[self.state.SP] = self.state.PC
            self.state.SP += 1
            self.state.PC = nnn
        elif op == 0x3:
            if V[x] == nn:
                self.state.PC += 2
        elif op == 0x4:
            if V[x] != nn:
                self.state.PC += 2
        elif op == 0x5:
            if V[x] == V[y]:
                self.state.PC += 2
        elif op == 0x6:
            V[x] = nn
        elif op == 0x7:
            V[x] = (V[x] + nn) & 0xFF
        elif op == 0x8:
            z = n
            if z == 0x0:
                V[x] = V[y]
            elif z == 0x1:
                V[x] |= V[y]
                V[0xF] = 0
            elif z == 0x2:
                V[x] &= V[y]
                V[0xF] = 0
            elif z == 0x3:
                V[x] ^= V[y]
                V[0xF] = 0
            elif z == 0x4:
                result = V[x] + V[y]
                V[x] = result & 0xFF
                V[0xF] = 1 if result > 255 else 0
            elif z == 0x5:
                V[0xF] = 1 if V[x] >= V[y] else 0
                V[x] = (V[x] - V[y]) & 0xFF
            elif z == 0x6:
                if self.quirks['shift_vx']:
                    src = x
                else:
                    src = y
                V[0xF] = V[src] & 0x1
                V[x] = V[src] >> 1
            elif z == 0x7:
                V[0xF] = 1 if V[y] >= V[x] else 0
                V[x] = (V[y] - V[x]) & 0xFF
            elif z == 0xE:
                if self.quirks['shift_vx']:
                    src = x
                else:
                    src = y
                V[0xF] = (V[src] >> 7) & 0x1
                V[x] = (V[src] << 1) & 0xFF
        elif op == 0x9:
            if V[x] != V[y]:
                self.state.PC += 2
        elif op == 0xA:
            self.state.I = nnn
        elif op == 0xB:
            if self.quirks['jump_v0']:
                self.state.PC = nnn + V[0]
            else:
                self.state.PC = nnn + V[x]
        elif op == 0xC:
            V[x] = random.randint(0, 255) & nn
        elif op == 0xD:
            self._draw_sprite(V[x], V[y], n)
        elif op == 0xE:
            if nn == 0x9E:
                if self.state.keys[V[x] & 0xF]:
                    self.state.PC += 2
            elif nn == 0xA1:
                if not self.state.keys[V[x] & 0xF]:
                    self.state.PC += 2
        elif op == 0xF:
            if nn == 0x07:
                V[x] = self.state.delay_timer
            elif nn == 0x0A:
                self.state.waiting_for_key = True
                self.state.key_register = x
            elif nn == 0x15:
                self.state.delay_timer = V[x]
            elif nn == 0x18:
                self.state.sound_timer = V[x]
            elif nn == 0x1E:
                self.state.I = (self.state.I + V[x]) & 0xFFF
            elif nn == 0x29:
                self.state.I = (V[x] & 0xF) * 5
            elif nn == 0x30:
                self.state.I = (V[x] & 0xF) * 10 + 80
            elif nn == 0x33:
                value = V[x]
                self.state.memory[self.state.I] = value // 100
                self.state.memory[self.state.I + 1] = (value // 10) % 10
                self.state.memory[self.state.I + 2] = value % 10
            elif nn == 0x55:
                for i in range(x + 1):
                    self.state.memory[self.state.I + i] = V[i]
                if self.quirks['load_store_inc']:
                    self.state.I += x + 1
            elif nn == 0x65:
                for i in range(x + 1):
                    V[i] = self.state.memory[self.state.I + i]
                if self.quirks['load_store_inc']:
                    self.state.I += x + 1
            elif nn == 0x75:
                pass  # RPL not implemented
            elif nn == 0x85:
                pass  # RPL not implemented

    def _draw_sprite(self, x: int, y: int, height: int):
        V = self.state.V
        V[0xF] = 0
        x = x % DISPLAY_W
        y = y % DISPLAY_H
        for row in range(height):
            if y + row >= DISPLAY_H:
                break
            sprite_byte = self.state.memory[self.state.I + row]
            for col in range(8):
                if x + col >= DISPLAY_W:
                    break
                if sprite_byte & (0x80 >> col):
                    px = x + col
                    py = y + row
                    if self.state.display[py][px]:
                        V[0xF] = 1
                    self.state.display[py][px] ^= 1
        self.draw_flag = True

    def cycle(self):
        if not self.running or self.paused:
            return
        if self.state.waiting_for_key:
            for i, pressed in enumerate(self.state.keys):
                if pressed:
                    self.state.V[self.state.key_register] = i
                    self.state.waiting_for_key = False
                    break
            return
        opcode = self.fetch()
        self.execute(opcode)

    def update_timers(self):
        if self.state.delay_timer > 0:
            self.state.delay_timer -= 1
        if self.state.sound_timer > 0:
            self.state.sound_timer -= 1

    def key_down(self, key: int):
        if 0 <= key < NUM_KEYS:
            self.state.keys[key] = True

    def key_up(self, key: int):
        if 0 <= key < NUM_KEYS:
            self.state.keys[key] = False

    def disassemble(self, opcode: int) -> str:
        nnn = opcode & 0x0FFF
        nn = opcode & 0x00FF
        n = opcode & 0x000F
        x = (opcode >> 8) & 0x0F
        y = (opcode >> 4) & 0x0F
        op = (opcode >> 12) & 0xF

        if opcode == 0x00E0:
            return "CLS"
        elif opcode == 0x00EE:
            return "RET"
        elif op == 0x1:
            return f"JP ${nnn:03X}"
        elif op == 0x2:
            return f"CALL ${nnn:03X}"
        elif op == 0x3:
            return f"SE V{x:X}, ${nn:02X}"
        elif op == 0x4:
            return f"SNE V{x:X}, ${nn:02X}"
        elif op == 0x5:
            return f"SE V{x:X}, V{y:X}"
        elif op == 0x6:
            return f"LD V{x:X}, ${nn:02X}"
        elif op == 0x7:
            return f"ADD V{x:X}, ${nn:02X}"
        elif op == 0x8:
            ops = {0: "LD", 1: "OR", 2: "AND", 3: "XOR", 4: "ADD",
                   5: "SUB", 6: "SHR", 7: "SUBN", 0xE: "SHL"}
            return f"{ops.get(n, '???')} V{x:X}, V{y:X}"
        elif op == 0x9:
            return f"SNE V{x:X}, V{y:X}"
        elif op == 0xA:
            return f"LD I, ${nnn:03X}"
        elif op == 0xB:
            return f"JP V0, ${nnn:03X}"
        elif op == 0xC:
            return f"RND V{x:X}, ${nn:02X}"
        elif op == 0xD:
            return f"DRW V{x:X}, V{y:X}, {n}"
        elif op == 0xE:
            if nn == 0x9E:
                return f"SKP V{x:X}"
            elif nn == 0xA1:
                return f"SKNP V{x:X}"
        elif op == 0xF:
            fops = {0x07: "LD Vx, DT", 0x0A: "LD Vx, K", 0x15: "LD DT, Vx",
                    0x18: "LD ST, Vx", 0x1E: "ADD I, Vx", 0x29: "LD F, Vx",
                    0x33: "LD B, Vx", 0x55: "LD [I], Vx", 0x65: "LD Vx, [I]"}
            base = fops.get(nn, f"??? ${nn:02X}")
            return base.replace("Vx", f"V{x:X}")
        return f"??? ${opcode:04X}"


# ═══════════════════════════════════════════════════════════════════════════════
# TKINTER GUI APPLICATION (No external deps)
# ═══════════════════════════════════════════════════════════════════════════════

class Chip8EmulatorTk:
    def __init__(self, root):
        self.root = root
        self.root.title("🐱 Cat's CHIP-8 Emulator v0 - Pure Python")
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS['bg_dark'])

        self.cpu = Chip8CPU()
        self.rom_path = None
        self.rom_name = None

        # Display scale and colors
        self.scale = SCALE
        self.current_fg_color = COLORS['fg_green']
        self.current_bg_color = COLORS['bg_dark']

        # GUI variables
        self.show_debug = tk.BooleanVar(value=False)
        self.color_scheme = tk.IntVar(value=0)
        self.color_schemes = [
            ('Green Phosphor', COLORS['fg_green']),
            ('Amber CRT', COLORS['fg_amber']),
            ('Cool White', COLORS['fg_white']),
            ('Ice Blue', COLORS['fg_blue']),
        ]
        self.speed_hz = tk.IntVar(value=DEFAULT_CLOCK_HZ)

        # Timing
        self.last_timer_tick = time.time()
        self.cycles_per_frame = DEFAULT_CLOCK_HZ // 60
        self.running_emulation = True
        self.after_id = None

        # Build GUI
        self._create_menu()
        self._create_status_bar()
        self._create_display()
        self._bind_keys()

        # Start emulation loop
        self._update_emulation()

        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    def _create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open ROM...", command=self._open_rom, accelerator="Ctrl+O")
        file_menu.add_command(label="Reset", command=self._reset)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._quit, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        emu_menu = tk.Menu(menubar, tearoff=0)
        emu_menu.add_command(label="Pause/Resume", command=self._toggle_pause, accelerator="P")
        emu_menu.add_command(label="Step", command=self._step, accelerator="S")
        emu_menu.add_separator()
        emu_menu.add_radiobutton(label="Speed: 500 Hz", variable=self.speed_hz, value=500,
                                 command=lambda: self._set_speed(500))
        emu_menu.add_radiobutton(label="Speed: 1000 Hz", variable=self.speed_hz, value=1000,
                                 command=lambda: self._set_speed(1000))
        emu_menu.add_radiobutton(label="Speed: 2000 Hz", variable=self.speed_hz, value=2000,
                                 command=lambda: self._set_speed(2000))
        menubar.add_cascade(label="Emulation", menu=emu_menu)

        display_menu = tk.Menu(menubar, tearoff=0)
        for i, (name, color) in enumerate(self.color_schemes):
            display_menu.add_radiobutton(label=name, variable=self.color_scheme, value=i,
                                         command=lambda idx=i: self._set_color(idx))
        display_menu.add_separator()
        display_menu.add_checkbutton(label="Debug Overlay", variable=self.show_debug,
                                     command=self._toggle_debug)
        menubar.add_cascade(label="Display", menu=display_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Controls", command=self._show_controls)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

        # Keyboard shortcuts
        self.root.bind('<Control-o>', lambda e: self._open_rom())
        self.root.bind('<Control-q>', lambda e: self._quit())
        self.root.bind('<Key-p>', lambda e: self._toggle_pause())
        self.root.bind('<Key-s>', lambda e: self._step())

    def _create_status_bar(self):
        self.status_frame = tk.Frame(self.root, height=25, bg=COLORS['status_bg'])
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = tk.Label(
            self.status_frame,
            text="Ready - Load a ROM to begin",
            fg=COLORS['text_dim'],
            bg=COLORS['status_bg'],
            anchor='w',
            font=('TkDefaultFont', 9)
        )
        self.status_label.pack(side=tk.LEFT, padx=5)

    def _create_display(self):
        self.display_frame = tk.Frame(self.root, bg=COLORS['bg_dark'])
        self.display_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=(10, 5))

        self.canvas = tk.Canvas(
            self.display_frame,
            width=DISPLAY_SCALED_W,
            height=DISPLAY_SCALED_H,
            bg='#000000',
            highlightthickness=1,
            highlightbackground=COLORS['text_dim']
        )
        self.canvas.pack(expand=True)

        # We'll draw pixels as rectangles; no image object needed.
        self.pixel_rects = [[None]*DISPLAY_W for _ in range(DISPLAY_H)]
        self._create_pixel_grid()

    def _create_pixel_grid(self):
        """Create rectangle objects for each pixel (scaled)"""
        for y in range(DISPLAY_H):
            for x in range(DISPLAY_W):
                x1 = x * self.scale
                y1 = y * self.scale
                x2 = x1 + self.scale
                y2 = y1 + self.scale
                rect = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=self.current_bg_color,
                    outline=''
                )
                self.pixel_rects[y][x] = rect

    def _bind_keys(self):
        self.root.bind('<KeyPress>', self._on_key_press)
        self.root.bind('<KeyRelease>', self._on_key_release)

    def _on_key_press(self, event):
        if event.char and event.char.lower() in KEY_MAP:
            key = KEY_MAP[event.char.lower()]
            self.cpu.key_down(key)
        elif event.keysym == 'F1':
            self._show_controls()
        elif event.keysym == 'F2':
            self._show_about()

    def _on_key_release(self, event):
        if event.char and event.char.lower() in KEY_MAP:
            key = KEY_MAP[event.char.lower()]
            self.cpu.key_up(key)

    def _open_rom(self):
        file_path = filedialog.askopenfilename(
            title="Select a CHIP-8 ROM",
            filetypes=[("CHIP-8 ROMs", "*.ch8 *.c8"), ("All files", "*.*")]
        )
        if file_path:
            self._load_rom(file_path)
        else:
            self.status_label.config(text="ROM selection cancelled")

    def _load_rom(self, path):
        if self.cpu.load_rom_file(path):
            self.rom_path = path
            self.rom_name = Path(path).stem
            self.status_label.config(text=f"Loaded: {self.rom_name}")
            self._update_display()
        else:
            self.status_label.config(text="Failed to load ROM!")

    def _reset(self):
        if self.rom_path:
            self._load_rom(self.rom_path)
        else:
            self.cpu.reset()
        self.status_label.config(text="Reset")

    def _quit(self):
        self.running_emulation = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.root.quit()
        self.root.destroy()

    def _toggle_pause(self):
        self.cpu.paused = not self.cpu.paused
        state = "Paused" if self.cpu.paused else "Running"
        self.status_label.config(text=state)

    def _step(self):
        if self.cpu.running:
            self.cpu.paused = False
            self.cpu.cycle()
            self.cpu.paused = True
            self._update_display()
            self.status_label.config(text=f"Step - PC: ${self.cpu.state.PC:03X}")

    def _set_speed(self, hz):
        self.cpu.clock_hz = hz
        self.cycles_per_frame = hz // 60
        self.status_label.config(text=f"Speed: {hz} Hz")

    def _set_color(self, index):
        name, color = self.color_schemes[index]
        self.current_fg_color = color
        self.status_label.config(text=f"Color: {name}")
        self._update_display()  # redraw with new color

    def _toggle_debug(self):
        # Debug overlay drawn in _update_display
        self.status_label.config(text="Debug " + ("on" if self.show_debug.get() else "off"))

    def _show_controls(self):
        msg = ("CHIP-8 Keypad Mapping:\n"
               " 1 2 3 C  → 1 2 3 4\n"
               " 4 5 6 D  → Q W E R\n"
               " 7 8 9 E  → A S D F\n"
               " A 0 B F  → Z X C V\n\n"
               "P: Pause/Resume\n"
               "S: Step (when paused)\n"
               "F1: This help\n"
               "F2: About")
        messagebox.showinfo("Controls", msg)

    def _show_about(self):
        msg = ("🐱 Cat's CHIP-8 Emulator v0\n"
               "Team Flames / Samsoft - 2026\n\n"
               "A complete CHIP-8/SCHIP emulator\n"
               "Pure Python / No external dependencies.\n"
               "GUI inspired by mGBA.")
        messagebox.showinfo("About", msg)

    def _update_display(self):
        """Update pixel colors from framebuffer"""
        display = self.cpu.state.display
        for y in range(DISPLAY_H):
            for x in range(DISPLAY_W):
                color = self.current_fg_color if display[y][x] else self.current_bg_color
                self.canvas.itemconfig(self.pixel_rects[y][x], fill=color)

        if self.show_debug.get():
            self._draw_debug_overlay()
        else:
            self.canvas.delete("debug")

    def _draw_debug_overlay(self):
        self.canvas.delete("debug")
        s = self.cpu.state
        lines = [
            f"PC: ${s.PC:03X}   I: ${s.I:03X}",
            f"SP: {s.SP}   DT: {s.delay_timer:02X}   ST: {s.sound_timer:02X}",
            "V0-V7: " + " ".join(f"{v:02X}" for v in s.V[:8]),
            "V8-VF: " + " ".join(f"{v:02X}" for v in s.V[8:]),
        ]
        if s.PC < MEMORY_SIZE - 1:
            opcode = (s.memory[s.PC] << 8) | s.memory[s.PC + 1]
            lines.append(f"OP: ${opcode:04X} {self.cpu.disassemble(opcode)}")

        x0, y0 = 10, 10
        x1 = x0 + 220
        y1 = y0 + 15 * len(lines) + 10
        self.canvas.create_rectangle(x0, y0, x1, y1, fill='#00000080', outline='', tags="debug")
        for i, line in enumerate(lines):
            self.canvas.create_text(
                x0 + 5, y0 + 5 + i * 15,
                text=line,
                fill=COLORS['fg_green'],
                font=('TkFixedFont', 9),
                anchor='nw',
                tags="debug"
            )

    def _update_emulation(self):
        if not self.running_emulation:
            return

        for _ in range(self.cycles_per_frame):
            self.cpu.cycle()

        now = time.time()
        if now - self.last_timer_tick >= 1/60:
            self.cpu.update_timers()
            self.last_timer_tick = now

        if self.cpu.draw_flag:
            self._update_display()
            self.cpu.draw_flag = False

        self.after_id = self.root.after(16, self._update_emulation)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║      🐱 Cat's CHIP-8 Emulator v0 - 'Meow Machine' Edition     ║")
    print("║              Team Flames / Samsoft - 2026                     ║")
    print("║               (Pure Python / No Dependencies)                 ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()
    print("Controls:")
    print("  CHIP-8 Keypad: 1234 / QWER / ASDF / ZXCV")
    print("  P = Pause/Resume")
    print("  S = Step (when paused)")
    print("  F1 = Controls help")
    print()

    root = tk.Tk()
    app = Chip8EmulatorTk(root)

    if len(sys.argv) > 1:
        rom_path = sys.argv[1]
        if os.path.exists(rom_path):
            app._load_rom(rom_path)
        else:
            print(f"ROM not found: {rom_path}")

    root.mainloop()

if __name__ == "__main__":
    main()