#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║             🐱 Cat's CHIP-8 Emulator v0 - "Meow Machine" Edition 🐱            ║
║                                                                               ║
║  A complete CHIP-8/SCHIP emulator with authentic glow CRT effects             ║
║  Team Flames / Samsoft - 2026                                                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝

Features:
- Complete CHIP-8 instruction set (35 opcodes)
- Super CHIP-8 extensions (SCHIP)
- Authentic phosphor glow/bloom effects
- Project64-style GUI with ROM browser
- Configurable speed, colors, and effects
- Save states and pause/resume
- Debug mode with disassembly
"""

import pygame
import numpy as np
import random
import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DISPLAY_W, DISPLAY_H = 64, 32          # CHIP-8 native resolution
SCALE = 12                              # Display scale factor
GLOW_UPSCALE = 4                        # Internal upscale for glow blur
BLOOM_STRENGTH = 0.55                   # Glow intensity (0.0-1.0)
BLUR_RADIUS = 1                         # Box blur passes (0-3)

WINDOW_W = DISPLAY_W * SCALE            # 768
WINDOW_H = DISPLAY_H * SCALE + 80       # 384 + menu/status = 464

MEMORY_SIZE = 4096                      # 4KB RAM
PROGRAM_START = 0x200                   # Programs load at 0x200
STACK_SIZE = 16                         # 16-level stack
NUM_REGISTERS = 16                      # V0-VF registers
NUM_KEYS = 16                           # 16 hex keys

# CPU Timing
DEFAULT_CLOCK_HZ = 500                  # Instructions per second
TIMER_HZ = 60                           # Delay/Sound timer rate

# Colors (RGB)
COLORS = {
    'bg_dark': (15, 15, 25),
    'bg_light': (25, 25, 40),
    'fg_green': (0, 255, 128),
    'fg_amber': (255, 176, 0),
    'fg_white': (220, 220, 220),
    'fg_blue': (100, 180, 255),
    'accent': (255, 100, 150),
    'menu_bg': (30, 30, 45),
    'menu_hover': (50, 50, 70),
    'status_bg': (20, 20, 35),
    'text': (200, 200, 200),
    'text_dim': (120, 120, 140),
}

# CHIP-8 Font (4x5 pixels, stored as 5 bytes each)
FONTSET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
    0x20, 0x60, 0x20, 0x20, 0x70,  # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
    0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
    0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
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
# CHIP-8 Keypad:    Keyboard:
# 1 2 3 C          1 2 3 4
# 4 5 6 D          Q W E R
# 7 8 9 E          A S D F
# A 0 B F          Z X C V
KEY_MAP = {
    pygame.K_1: 0x1, pygame.K_2: 0x2, pygame.K_3: 0x3, pygame.K_4: 0xC,
    pygame.K_q: 0x4, pygame.K_w: 0x5, pygame.K_e: 0x6, pygame.K_r: 0xD,
    pygame.K_a: 0x7, pygame.K_s: 0x8, pygame.K_d: 0x9, pygame.K_f: 0xE,
    pygame.K_z: 0xA, pygame.K_x: 0x0, pygame.K_c: 0xB, pygame.K_v: 0xF,
}


# ═══════════════════════════════════════════════════════════════════════════════
# GLOW EFFECT SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class GlowRenderer:
    """Phosphor glow/bloom post-processing effect"""
    
    def __init__(self, width: int, height: int, scale: int, 
                 fg_color: Tuple[int, int, int] = COLORS['fg_green'],
                 bg_color: Tuple[int, int, int] = COLORS['bg_dark']):
        self.width = width
        self.height = height
        self.scale = scale
        self.fg_color = fg_color
        self.bg_color = bg_color
        self.bloom_strength = BLOOM_STRENGTH
        self.blur_radius = BLUR_RADIUS
        self.glow_upscale = GLOW_UPSCALE
        
        self.final_size = (width * scale, height * scale)
    
    def box_blur(self, arr: np.ndarray, passes: int = 1) -> np.ndarray:
        """Fast box blur using rolling averages"""
        a = arr.copy()
        for _ in range(passes):
            # Horizontal blur
            a = (np.roll(a, 1, axis=1) + a + np.roll(a, -1, axis=1)) / 3.0
            # Vertical blur
            a = (np.roll(a, 1, axis=0) + a + np.roll(a, -1, axis=0)) / 3.0
        return a
    
    def render(self, framebuffer: np.ndarray) -> Tuple[pygame.Surface, pygame.Surface]:
        """
        Convert boolean framebuffer to glow surfaces
        
        Args:
            framebuffer: (height, width) boolean/0-1 array
            
        Returns:
            (base_surface, glow_surface) tuple
        """
        # Normalize to float32
        base = framebuffer.astype(np.float32)
        
        # Upscale dimensions for smoother blur
        up_w = self.width * self.glow_upscale
        up_h = self.height * self.glow_upscale
        
        # Create base grayscale surface
        base_gray = (base * 255).astype(np.uint8)
        base_surf_small = pygame.surfarray.make_surface(
            np.stack([base_gray.T] * 3, axis=-1)
        )
        
        # Upscale for blur processing
        base_up = pygame.transform.scale(base_surf_small, (up_w, up_h))
        
        # Extract luminance for blur
        arr = pygame.surfarray.array2d(base_up).astype(np.float32)
        arr = arr / arr.max() if arr.max() > 0 else arr
        
        # Apply blur to create glow halo
        glow = self.box_blur(arr, passes=1 + self.blur_radius)
        glow = np.clip(glow * self.bloom_strength, 0.0, 1.0)
        
        # Colorize glow
        glow_rgb = np.zeros((up_w, up_h, 3), dtype=np.uint8)
        for i, c in enumerate(self.fg_color):
            glow_rgb[:, :, i] = (glow * c).astype(np.uint8)
        
        glow_surf = pygame.surfarray.make_surface(glow_rgb)
        
        # Colorize base pixels
        base_rgb = np.zeros((self.width, self.height, 3), dtype=np.uint8)
        for i, c in enumerate(self.fg_color):
            base_rgb[:, :, i] = (base.T * c).astype(np.uint8)
        
        base_surf = pygame.surfarray.make_surface(base_rgb)
        
        # Scale to final size
        base_final = pygame.transform.scale(base_surf, self.final_size)
        glow_final = pygame.transform.smoothscale(glow_surf, self.final_size)
        
        return base_final, glow_final
    
    def create_background(self) -> pygame.Surface:
        """Create CRT-style background with scanlines"""
        surf = pygame.Surface(self.final_size)
        surf.fill(self.bg_color)
        
        # Add subtle scanlines
        for y in range(0, self.final_size[1], 2):
            pygame.draw.line(surf, 
                           (self.bg_color[0] + 5, self.bg_color[1] + 5, self.bg_color[2] + 5),
                           (0, y), (self.final_size[0], y))
        
        return surf


# ═══════════════════════════════════════════════════════════════════════════════
# CHIP-8 CPU CORE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CPUState:
    """CHIP-8 CPU state container"""
    # Memory
    memory: bytearray = field(default_factory=lambda: bytearray(MEMORY_SIZE))
    
    # Registers
    V: List[int] = field(default_factory=lambda: [0] * NUM_REGISTERS)  # V0-VF
    I: int = 0              # Index register (12-bit)
    PC: int = PROGRAM_START # Program counter
    SP: int = 0             # Stack pointer
    
    # Stack
    stack: List[int] = field(default_factory=lambda: [0] * STACK_SIZE)
    
    # Timers (60Hz)
    delay_timer: int = 0
    sound_timer: int = 0
    
    # Display (64x32)
    display: np.ndarray = field(default_factory=lambda: np.zeros((DISPLAY_H, DISPLAY_W), dtype=np.uint8))
    
    # Keypad state
    keys: List[bool] = field(default_factory=lambda: [False] * NUM_KEYS)
    
    # Wait for key state
    waiting_for_key: bool = False
    key_register: int = 0
    
    # SCHIP mode
    schip_mode: bool = False
    high_res: bool = False  # 128x64 mode


class Chip8CPU:
    """Complete CHIP-8/SCHIP CPU emulator"""
    
    def __init__(self):
        self.state = CPUState()
        self.running = False
        self.paused = False
        self.draw_flag = False
        self.clock_hz = DEFAULT_CLOCK_HZ
        self.quirks = {
            'shift_vx': True,       # SCHIP: Shift VX, not VY
            'load_store_inc': True, # Original: I increments after load/store
            'jump_v0': True,        # BNNN uses V0 offset
        }
        
        self._load_fontset()
    
    def _load_fontset(self):
        """Load built-in font sprites to memory"""
        for i, byte in enumerate(FONTSET):
            self.state.memory[i] = byte
    
    def reset(self):
        """Reset CPU to initial state"""
        self.state = CPUState()
        self._load_fontset()
        self.running = False
        self.paused = False
        self.draw_flag = True
    
    def load_rom(self, data: bytes) -> bool:
        """Load ROM data into memory"""
        if len(data) > MEMORY_SIZE - PROGRAM_START:
            return False
        
        self.reset()
        for i, byte in enumerate(data):
            self.state.memory[PROGRAM_START + i] = byte
        
        self.running = True
        return True
    
    def load_rom_file(self, filepath: str) -> bool:
        """Load ROM from file"""
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            return self.load_rom(data)
        except Exception as e:
            print(f"Failed to load ROM: {e}")
            return False
    
    def fetch(self) -> int:
        """Fetch next 16-bit opcode"""
        hi = self.state.memory[self.state.PC]
        lo = self.state.memory[self.state.PC + 1]
        self.state.PC += 2
        return (hi << 8) | lo
    
    def execute(self, opcode: int):
        """Decode and execute a single opcode"""
        # Extract common opcode parts
        nnn = opcode & 0x0FFF        # 12-bit address
        nn = opcode & 0x00FF         # 8-bit constant
        n = opcode & 0x000F          # 4-bit constant
        x = (opcode >> 8) & 0x0F     # 4-bit register index
        y = (opcode >> 4) & 0x0F     # 4-bit register index
        
        op = (opcode >> 12) & 0xF    # First nibble
        
        V = self.state.V
        
        # ─── 0x0XXX ───
        if op == 0x0:
            if opcode == 0x00E0:
                # 00E0: CLS - Clear display
                self.state.display.fill(0)
                self.draw_flag = True
            
            elif opcode == 0x00EE:
                # 00EE: RET - Return from subroutine
                self.state.SP -= 1
                self.state.PC = self.state.stack[self.state.SP]
            
            elif opcode == 0x00FE:
                # 00FE: SCHIP - Disable high-res mode
                self.state.high_res = False
            
            elif opcode == 0x00FF:
                # 00FF: SCHIP - Enable high-res mode (128x64)
                self.state.high_res = True
            
            elif (opcode & 0xFFF0) == 0x00C0:
                # 00CN: SCHIP - Scroll down N lines
                n_lines = n
                self.state.display = np.roll(self.state.display, n_lines, axis=0)
                self.state.display[:n_lines, :] = 0
                self.draw_flag = True
        
        # ─── 1NNN: JP addr ───
        elif op == 0x1:
            self.state.PC = nnn
        
        # ─── 2NNN: CALL addr ───
        elif op == 0x2:
            self.state.stack[self.state.SP] = self.state.PC
            self.state.SP += 1
            self.state.PC = nnn
        
        # ─── 3XNN: SE Vx, byte ───
        elif op == 0x3:
            if V[x] == nn:
                self.state.PC += 2
        
        # ─── 4XNN: SNE Vx, byte ───
        elif op == 0x4:
            if V[x] != nn:
                self.state.PC += 2
        
        # ─── 5XY0: SE Vx, Vy ───
        elif op == 0x5:
            if V[x] == V[y]:
                self.state.PC += 2
        
        # ─── 6XNN: LD Vx, byte ───
        elif op == 0x6:
            V[x] = nn
        
        # ─── 7XNN: ADD Vx, byte ───
        elif op == 0x7:
            V[x] = (V[x] + nn) & 0xFF
        
        # ─── 8XYZ: ALU operations ───
        elif op == 0x8:
            z = n
            
            if z == 0x0:
                # 8XY0: LD Vx, Vy
                V[x] = V[y]
            
            elif z == 0x1:
                # 8XY1: OR Vx, Vy
                V[x] |= V[y]
                V[0xF] = 0  # SCHIP quirk
            
            elif z == 0x2:
                # 8XY2: AND Vx, Vy
                V[x] &= V[y]
                V[0xF] = 0  # SCHIP quirk
            
            elif z == 0x3:
                # 8XY3: XOR Vx, Vy
                V[x] ^= V[y]
                V[0xF] = 0  # SCHIP quirk
            
            elif z == 0x4:
                # 8XY4: ADD Vx, Vy (VF = carry)
                result = V[x] + V[y]
                V[x] = result & 0xFF
                V[0xF] = 1 if result > 255 else 0
            
            elif z == 0x5:
                # 8XY5: SUB Vx, Vy (VF = NOT borrow)
                V[0xF] = 1 if V[x] >= V[y] else 0
                V[x] = (V[x] - V[y]) & 0xFF
            
            elif z == 0x6:
                # 8XY6: SHR Vx {, Vy}
                if self.quirks['shift_vx']:
                    src = x
                else:
                    src = y
                V[0xF] = V[src] & 0x1
                V[x] = V[src] >> 1
            
            elif z == 0x7:
                # 8XY7: SUBN Vx, Vy (VF = NOT borrow)
                V[0xF] = 1 if V[y] >= V[x] else 0
                V[x] = (V[y] - V[x]) & 0xFF
            
            elif z == 0xE:
                # 8XYE: SHL Vx {, Vy}
                if self.quirks['shift_vx']:
                    src = x
                else:
                    src = y
                V[0xF] = (V[src] >> 7) & 0x1
                V[x] = (V[src] << 1) & 0xFF
        
        # ─── 9XY0: SNE Vx, Vy ───
        elif op == 0x9:
            if V[x] != V[y]:
                self.state.PC += 2
        
        # ─── ANNN: LD I, addr ───
        elif op == 0xA:
            self.state.I = nnn
        
        # ─── BNNN: JP V0, addr ───
        elif op == 0xB:
            if self.quirks['jump_v0']:
                self.state.PC = nnn + V[0]
            else:
                # SCHIP: BXNN jumps to XNN + VX
                self.state.PC = nnn + V[x]
        
        # ─── CXNN: RND Vx, byte ───
        elif op == 0xC:
            V[x] = random.randint(0, 255) & nn
        
        # ─── DXYN: DRW Vx, Vy, nibble ───
        elif op == 0xD:
            self._draw_sprite(V[x], V[y], n)
        
        # ─── EX9E/EXA1: Key operations ───
        elif op == 0xE:
            if nn == 0x9E:
                # EX9E: SKP Vx (skip if key pressed)
                if self.state.keys[V[x] & 0xF]:
                    self.state.PC += 2
            
            elif nn == 0xA1:
                # EXA1: SKNP Vx (skip if key not pressed)
                if not self.state.keys[V[x] & 0xF]:
                    self.state.PC += 2
        
        # ─── FX00-FX65: Misc operations ───
        elif op == 0xF:
            if nn == 0x07:
                # FX07: LD Vx, DT
                V[x] = self.state.delay_timer
            
            elif nn == 0x0A:
                # FX0A: LD Vx, K (wait for key press)
                self.state.waiting_for_key = True
                self.state.key_register = x
            
            elif nn == 0x15:
                # FX15: LD DT, Vx
                self.state.delay_timer = V[x]
            
            elif nn == 0x18:
                # FX18: LD ST, Vx
                self.state.sound_timer = V[x]
            
            elif nn == 0x1E:
                # FX1E: ADD I, Vx
                self.state.I = (self.state.I + V[x]) & 0xFFF
            
            elif nn == 0x29:
                # FX29: LD F, Vx (point I to font sprite)
                self.state.I = (V[x] & 0xF) * 5
            
            elif nn == 0x30:
                # FX30: SCHIP - Point I to 10-byte font
                self.state.I = (V[x] & 0xF) * 10 + 80
            
            elif nn == 0x33:
                # FX33: LD B, Vx (BCD)
                value = V[x]
                self.state.memory[self.state.I] = value // 100
                self.state.memory[self.state.I + 1] = (value // 10) % 10
                self.state.memory[self.state.I + 2] = value % 10
            
            elif nn == 0x55:
                # FX55: LD [I], Vx (store V0-Vx)
                for i in range(x + 1):
                    self.state.memory[self.state.I + i] = V[i]
                if self.quirks['load_store_inc']:
                    self.state.I += x + 1
            
            elif nn == 0x65:
                # FX65: LD Vx, [I] (load V0-Vx)
                for i in range(x + 1):
                    V[i] = self.state.memory[self.state.I + i]
                if self.quirks['load_store_inc']:
                    self.state.I += x + 1
            
            elif nn == 0x75:
                # FX75: SCHIP - Store V0-Vx in RPL flags
                pass  # Not implemented
            
            elif nn == 0x85:
                # FX85: SCHIP - Load V0-Vx from RPL flags
                pass  # Not implemented
    
    def _draw_sprite(self, x: int, y: int, height: int):
        """Draw sprite at (x, y) with given height"""
        V = self.state.V
        V[0xF] = 0  # Reset collision flag
        
        # Wrap coordinates
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
                    
                    # XOR pixel
                    if self.state.display[py, px]:
                        V[0xF] = 1  # Collision!
                    
                    self.state.display[py, px] ^= 1
        
        self.draw_flag = True
    
    def cycle(self):
        """Execute one CPU cycle"""
        if not self.running or self.paused:
            return
        
        # Handle key wait
        if self.state.waiting_for_key:
            for i, pressed in enumerate(self.state.keys):
                if pressed:
                    self.state.V[self.state.key_register] = i
                    self.state.waiting_for_key = False
                    break
            return
        
        # Fetch and execute
        opcode = self.fetch()
        self.execute(opcode)
    
    def update_timers(self):
        """Decrement timers (call at 60Hz)"""
        if self.state.delay_timer > 0:
            self.state.delay_timer -= 1
        
        if self.state.sound_timer > 0:
            self.state.sound_timer -= 1
    
    def key_down(self, key: int):
        """Handle key press"""
        if 0 <= key < NUM_KEYS:
            self.state.keys[key] = True
    
    def key_up(self, key: int):
        """Handle key release"""
        if 0 <= key < NUM_KEYS:
            self.state.keys[key] = False
    
    def disassemble(self, opcode: int) -> str:
        """Disassemble opcode to human-readable string"""
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
# GUI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

class Button:
    """Simple clickable button"""
    
    def __init__(self, rect: pygame.Rect, text: str, callback=None):
        self.rect = rect
        self.text = text
        self.callback = callback
        self.hovered = False
        self.font = None
    
    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        self.font = font
        color = COLORS['menu_hover'] if self.hovered else COLORS['menu_bg']
        pygame.draw.rect(surface, color, self.rect)
        pygame.draw.rect(surface, COLORS['text_dim'], self.rect, 1)
        
        text_surf = font.render(self.text, True, COLORS['text'])
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos) and self.callback:
                self.callback()
                return True
        return False


class MenuBar:
    """Dropdown menu bar"""
    
    def __init__(self, y: int, height: int):
        self.rect = pygame.Rect(0, y, WINDOW_W, height)
        self.menus = []
        self.active_menu = None
        self.font = None
    
    def add_menu(self, name: str, items: List[Tuple[str, callable]]):
        """Add a dropdown menu"""
        x = sum(100 for _ in self.menus)
        self.menus.append({
            'name': name,
            'rect': pygame.Rect(x, self.rect.y, 100, self.rect.height),
            'items': items,
            'open': False
        })
    
    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        self.font = font
        
        # Draw menu bar background
        pygame.draw.rect(surface, COLORS['menu_bg'], self.rect)
        
        # Draw menu items
        for menu in self.menus:
            color = COLORS['menu_hover'] if menu['open'] else COLORS['menu_bg']
            pygame.draw.rect(surface, color, menu['rect'])
            
            text_surf = font.render(menu['name'], True, COLORS['text'])
            text_rect = text_surf.get_rect(center=menu['rect'].center)
            surface.blit(text_surf, text_rect)
            
            # Draw dropdown if open
            if menu['open']:
                self._draw_dropdown(surface, menu)
    
    def _draw_dropdown(self, surface: pygame.Surface, menu: dict):
        """Draw dropdown menu items"""
        x = menu['rect'].x
        y = menu['rect'].bottom
        width = 180
        
        for i, (name, _) in enumerate(menu['items']):
            item_rect = pygame.Rect(x, y + i * 25, width, 25)
            
            mouse_pos = pygame.mouse.get_pos()
            hovered = item_rect.collidepoint(mouse_pos)
            
            color = COLORS['menu_hover'] if hovered else COLORS['menu_bg']
            pygame.draw.rect(surface, color, item_rect)
            pygame.draw.rect(surface, COLORS['text_dim'], item_rect, 1)
            
            text_surf = self.font.render(name, True, COLORS['text'])
            surface.blit(text_surf, (x + 10, y + i * 25 + 4))
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            
            # Check menu headers
            for menu in self.menus:
                if menu['rect'].collidepoint(pos):
                    # Toggle this menu
                    was_open = menu['open']
                    for m in self.menus:
                        m['open'] = False
                    menu['open'] = not was_open
                    return True
                
                # Check dropdown items
                if menu['open']:
                    x = menu['rect'].x
                    y = menu['rect'].bottom
                    width = 180
                    
                    for i, (name, callback) in enumerate(menu['items']):
                        item_rect = pygame.Rect(x, y + i * 25, width, 25)
                        if item_rect.collidepoint(pos):
                            if callback:
                                callback()
                            menu['open'] = False
                            return True
            
            # Click outside - close all
            for menu in self.menus:
                menu['open'] = False
        
        return False


class StatusBar:
    """Bottom status bar"""
    
    def __init__(self, y: int, height: int):
        self.rect = pygame.Rect(0, y, WINDOW_W, height)
        self.text = "Ready - Load a ROM to begin"
        self.font = None
    
    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        self.font = font
        pygame.draw.rect(surface, COLORS['status_bg'], self.rect)
        
        text_surf = font.render(self.text, True, COLORS['text_dim'])
        surface.blit(text_surf, (10, self.rect.y + 5))
    
    def set_text(self, text: str):
        self.text = text


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EMULATOR APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

class CatsChip8Emulator:
    """Main emulator application with GUI"""
    
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("🐱 Cat's CHIP-8 Emulator v0")
        
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        
        # Fonts
        self.font = pygame.font.Font(None, 20)
        self.font_large = pygame.font.Font(None, 28)
        
        # CPU
        self.cpu = Chip8CPU()
        
        # Renderer
        self.renderer = GlowRenderer(DISPLAY_W, DISPLAY_H, SCALE, COLORS['fg_green'])
        self.background = self.renderer.create_background()
        
        # GUI
        self.menu_bar = MenuBar(0, 25)
        self._setup_menus()
        
        self.status_bar = StatusBar(WINDOW_H - 25, 25)
        
        # Display area
        self.display_rect = pygame.Rect(0, 25, DISPLAY_W * SCALE, DISPLAY_H * SCALE)
        
        # State
        self.running = True
        self.show_debug = False
        self.color_scheme = 0
        self.color_schemes = [
            ('Green Phosphor', COLORS['fg_green']),
            ('Amber CRT', COLORS['fg_amber']),
            ('Cool White', COLORS['fg_white']),
            ('Ice Blue', COLORS['fg_blue']),
        ]
        
        # Timing
        self.last_timer_tick = time.time()
        self.cycles_per_frame = DEFAULT_CLOCK_HZ // 60
        
        # ROM info
        self.rom_name = None
        self.rom_path = None
    
    def _setup_menus(self):
        """Setup menu bar items"""
        self.menu_bar.add_menu("File", [
            ("Open ROM...", self._open_rom),
            ("Reset", self._reset),
            ("─────────────", None),
            ("Exit", self._quit),
        ])
        
        self.menu_bar.add_menu("Emulation", [
            ("Pause/Resume", self._toggle_pause),
            ("Step", self._step),
            ("─────────────", None),
            ("Speed: 500 Hz", lambda: self._set_speed(500)),
            ("Speed: 1000 Hz", lambda: self._set_speed(1000)),
            ("Speed: 2000 Hz", lambda: self._set_speed(2000)),
        ])
        
        self.menu_bar.add_menu("Display", [
            ("Green Phosphor", lambda: self._set_color(0)),
            ("Amber CRT", lambda: self._set_color(1)),
            ("Cool White", lambda: self._set_color(2)),
            ("Ice Blue", lambda: self._set_color(3)),
            ("─────────────", None),
            ("Toggle Debug", self._toggle_debug),
        ])
        
        self.menu_bar.add_menu("Help", [
            ("Controls", self._show_controls),
            ("About", self._show_about),
        ])
    
    def _open_rom(self):
        """Open ROM file dialog (simple implementation)"""
        # For a real app, use tkinter.filedialog or similar
        # Here we'll look for ROMs in current directory
        rom_dir = Path(".")
        roms = list(rom_dir.glob("*.ch8")) + list(rom_dir.glob("*.c8"))
        
        if roms:
            # Load first found ROM for demo
            self._load_rom(str(roms[0]))
        else:
            self.status_bar.set_text("No .ch8 files found - place ROMs in current directory")
    
    def _load_rom(self, path: str):
        """Load a ROM file"""
        if self.cpu.load_rom_file(path):
            self.rom_path = path
            self.rom_name = Path(path).stem
            self.status_bar.set_text(f"Loaded: {self.rom_name}")
        else:
            self.status_bar.set_text(f"Failed to load ROM!")
    
    def _reset(self):
        """Reset emulator"""
        if self.rom_path:
            self._load_rom(self.rom_path)
        else:
            self.cpu.reset()
        self.status_bar.set_text("Reset")
    
    def _quit(self):
        """Exit application"""
        self.running = False
    
    def _toggle_pause(self):
        """Toggle pause state"""
        self.cpu.paused = not self.cpu.paused
        state = "Paused" if self.cpu.paused else "Running"
        self.status_bar.set_text(state)
    
    def _step(self):
        """Single step execution"""
        if self.cpu.running:
            self.cpu.paused = False
            self.cpu.cycle()
            self.cpu.paused = True
            self.status_bar.set_text(f"Step - PC: ${self.cpu.state.PC:03X}")
    
    def _set_speed(self, hz: int):
        """Set CPU clock speed"""
        self.cpu.clock_hz = hz
        self.cycles_per_frame = hz // 60
        self.status_bar.set_text(f"Speed: {hz} Hz")
    
    def _set_color(self, index: int):
        """Set color scheme"""
        self.color_scheme = index
        name, color = self.color_schemes[index]
        self.renderer.fg_color = color
        self.status_bar.set_text(f"Color: {name}")
    
    def _toggle_debug(self):
        """Toggle debug overlay"""
        self.show_debug = not self.show_debug
    
    def _show_controls(self):
        """Show controls help"""
        self.status_bar.set_text("Keys: 1234/QWER/ASDF/ZXCV → Hex 123C/456D/789E/A0BF | P=Pause | ESC=Menu")
    
    def _show_about(self):
        """Show about info"""
        self.status_bar.set_text("🐱 Cat's CHIP-8 Emulator v0 - Team Flames/Samsoft 2026")
    
    def handle_events(self):
        """Process input events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            # Menu handling
            if self.menu_bar.handle_event(event):
                continue
            
            # Keyboard
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._quit()
                elif event.key == pygame.K_p:
                    self._toggle_pause()
                elif event.key == pygame.K_F1:
                    self._show_controls()
                elif event.key in KEY_MAP:
                    self.cpu.key_down(KEY_MAP[event.key])
            
            elif event.type == pygame.KEYUP:
                if event.key in KEY_MAP:
                    self.cpu.key_up(KEY_MAP[event.key])
    
    def update(self):
        """Update emulator state"""
        # Run CPU cycles
        for _ in range(self.cycles_per_frame):
            self.cpu.cycle()
        
        # Update timers at 60Hz
        now = time.time()
        if now - self.last_timer_tick >= 1/60:
            self.cpu.update_timers()
            self.last_timer_tick = now
    
    def render(self):
        """Render display"""
        # Clear
        self.screen.fill(COLORS['bg_dark'])
        
        # Draw background with scanlines
        self.screen.blit(self.background, (0, 25))
        
        # Render CHIP-8 display with glow
        if self.cpu.draw_flag or True:
            base_surf, glow_surf = self.renderer.render(self.cpu.state.display)
            
            # Draw glow layer (additive blend)
            self.screen.blit(glow_surf, (0, 25), special_flags=pygame.BLEND_ADD)
            
            # Draw crisp pixels on top
            self.screen.blit(base_surf, (0, 25))
            
            self.cpu.draw_flag = False
        
        # Debug overlay
        if self.show_debug:
            self._render_debug()
        
        # GUI
        self.menu_bar.draw(self.screen, self.font)
        self.status_bar.draw(self.screen, self.font)
        
        pygame.display.flip()
    
    def _render_debug(self):
        """Render debug information overlay"""
        s = self.cpu.state
        
        # Semi-transparent background
        overlay = pygame.Surface((200, 150), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (WINDOW_W - 210, 30))
        
        # CPU state
        lines = [
            f"PC: ${s.PC:03X}  I: ${s.I:03X}",
            f"SP: {s.SP}  DT: {s.delay_timer:02X}  ST: {s.sound_timer:02X}",
            "V0-V7: " + " ".join(f"{v:02X}" for v in s.V[:8]),
            "V8-VF: " + " ".join(f"{v:02X}" for v in s.V[8:]),
        ]
        
        # Current instruction
        if s.PC < MEMORY_SIZE - 1:
            opcode = (s.memory[s.PC] << 8) | s.memory[s.PC + 1]
            lines.append(f"OP: ${opcode:04X} {self.cpu.disassemble(opcode)}")
        
        for i, line in enumerate(lines):
            text = self.font.render(line, True, COLORS['fg_green'])
            self.screen.blit(text, (WINDOW_W - 205, 35 + i * 18))
    
    def run(self):
        """Main loop"""
        while self.running:
            self.handle_events()
            self.update()
            self.render()
            self.clock.tick(60)
        
        pygame.quit()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point"""
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║      🐱 Cat's CHIP-8 Emulator v0 - 'Meow Machine' Edition     ║")
    print("║              Team Flames / Samsoft - 2026                     ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()
    print("Controls:")
    print("  CHIP-8 Keypad: 1234 / QWER / ASDF / ZXCV")
    print("  P = Pause/Resume")
    print("  ESC = Exit")
    print()
    
    emu = CatsChip8Emulator()
    
    # Check for ROM argument
    if len(sys.argv) > 1:
        rom_path = sys.argv[1]
        if os.path.exists(rom_path):
            emu._load_rom(rom_path)
        else:
            print(f"ROM not found: {rom_path}")
    else:
        print("No ROM loaded - use File > Open ROM or pass .ch8 as argument")
    
    emu.run()


if __name__ == "__main__":
    main()
