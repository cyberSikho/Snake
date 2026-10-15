# pyrefly: ignore [missing-import]
import pygame
import sys
import os
import math
import random
import json
import time
import colorsys
import struct
import wave
import io

# ---------------- Initialization ----------------
pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
    AUDIO_AVAILABLE = True
except Exception as e:
    print(f"Audio init failed: {e}")
    AUDIO_AVAILABLE = False

# ---------------- Constants ----------------
CELL_SIZE = 28
GRID_W = 32
GRID_H = 22
WIDTH = GRID_W * CELL_SIZE
HEIGHT = GRID_H * CELL_SIZE
UI_H = 70
TOTAL_W = WIDTH
TOTAL_H = HEIGHT + UI_H

BG_COLOR = (15, 18, 25)
GRID_COLOR = (25, 30, 40)
TEXT_COLOR = (240, 240, 255)

STATE_MENU = 0
STATE_PLAY = 1
STATE_PAUSE = 2
STATE_GAMEOVER = 3
STATE_SETTINGS = 4

# ---------------- Utilities ----------------
def get_font(size, bold=False):
    return pygame.font.SysFont("Trebuchet MS, Tahoma, Arial", size, bold=bold)

def hsv2rgb(h, s, v):
    return tuple(round(i * 255) for i in colorsys.hsv_to_rgb(h % 1.0, s, v))

def draw_rounded_rect(surface, color, rect, radius):
    pygame.draw.rect(surface, color, rect, border_radius=radius)

def generate_wav(duration, func, volume=0.5):
    if not AUDIO_AVAILABLE: return None
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    buf = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        val = func(t)
        env = 1.0
        if i < 441: env = i / 441
        elif i > n_samples - 441: env = (n_samples - i) / 441
        sample = int(val * volume * env * 32767)
        sample = max(-32768, min(32767, sample))
        buf.extend(struct.pack('<h', sample))
        
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(buf)
    
    wav_io.seek(0)
    try:
        return pygame.mixer.Sound(wav_io)
    except:
        return None

# ---------------- Sound Functions ----------------
def pop_func(t):
    freq = 600 * math.exp(-25 * t)
    return math.sin(2 * math.pi * freq * t) * math.exp(-15 * t)

def crunch_func(t):
    return (random.random() * 2 - 1) * math.exp(-10 * t)

def buzzer_func(t):
    freq = 150 - (t * 50)
    return 1.0 if math.sin(2 * math.pi * freq * t) > 0 else -1.0

def powerup_func(t):
    freq = 400 + int(t * 15) * 50
    return math.sin(2 * math.pi * freq * t) * math.exp(-3 * t)

class AudioEngine:
    def __init__(self):
        self.muted = False
        self.pop = generate_wav(0.15, pop_func, 0.4)
        self.crunch = generate_wav(0.3, crunch_func, 0.5)
        self.buzzer = generate_wav(1.0, buzzer_func, 0.4)
        self.powerup = generate_wav(0.6, powerup_func, 0.4)
        
    def play(self, sound):
        if not self.muted and sound and AUDIO_AVAILABLE:
            sound.play()

audio = AudioEngine()

# ---------------- Save Data ----------------
class SaveData:
    def __init__(self):
        self.file_path = os.path.join(os.path.dirname(__file__), "snake_save.json")
        self.high_score = 0
        self.difficulty = 1 # 0: Easy, 1: Med, 2: Hard
        self.wrap_mode = False
        self.load()

    def load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    data = json.load(f)
                    self.high_score = data.get("high_score", 0)
                    self.difficulty = data.get("difficulty", 1)
                    self.wrap_mode = data.get("wrap_mode", False)
            except:
                pass

    def save(self):
        try:
            with open(self.file_path, "w") as f:
                json.dump({
                    "high_score": self.high_score,
                    "difficulty": self.difficulty,
                    "wrap_mode": self.wrap_mode
                }, f)
        except:
            pass

save_data = SaveData()

# ---------------- Game Entities ----------------
class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(20, 100)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 1.0
        self.decay = random.uniform(1.0, 2.0)
        
    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= self.decay * dt
        
    def draw(self, surface):
        if self.life > 0:
            alpha = int(255 * self.life)
            c = (*self.color[:3], alpha)
            s = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(s, c, (3, 3), 3)
            surface.blit(s, (int(self.x - 3), int(self.y - 3) + UI_H))

class FloatingText:
    def __init__(self, x, y, text, color, size=24):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = 1.0
        self.vy = -30
        self.font = get_font(size, True)
        
    def update(self, dt):
        self.y += self.vy * dt
        self.life -= 1.0 * dt
        
    def draw(self, surface):
        if self.life > 0:
            alpha = int(255 * self.life)
            txt_surface = self.font.render(self.text, True, self.color)
            txt_surface.set_alpha(alpha)
            surface.blit(txt_surface, (int(self.x - txt_surface.get_width()/2), int(self.y) + UI_H))

class Food:
    def __init__(self, snake_body):
        self.type = 0 # 0: Normal, 1: Golden, 2: Powerup
        self.x = 0
        self.y = 0
        self.time = 0
        self.respawn(snake_body, 0)
        
    def respawn(self, snake_body, foods_eaten):
        while True:
            self.x = random.randint(0, GRID_W - 1)
            self.y = random.randint(0, GRID_H - 1)
            if (self.x, self.y) not in snake_body:
                break
        
        # Determine type
        if foods_eaten > 0 and foods_eaten % 6 == 0:
            self.type = 1 # Golden
        elif foods_eaten > 0 and random.random() < 0.1:
            self.type = 2 # Powerup
        else:
            self.type = 0
            
    def update(self, dt):
        self.time += dt
        
    def draw(self, surface):
        px = self.x * CELL_SIZE + CELL_SIZE/2
        py = self.y * CELL_SIZE + CELL_SIZE/2 + UI_H
        
        pulse = (math.sin(self.time * 5) + 1) / 2
        
        if self.type == 0:
            base_col = (255, 50, 50)
            glow_col = (255, 50, 50, 100 + int(100 * pulse))
            rad = CELL_SIZE/2.5
        elif self.type == 1:
            base_col = (255, 215, 0)
            glow_col = (255, 215, 0, 100 + int(100 * pulse))
            rad = CELL_SIZE/2.2
            # Rainbow shimmer overlay
            base_col = hsv2rgb(self.time * 2, 0.8, 1.0)
        else:
            base_col = (50, 200, 255)
            glow_col = (50, 200, 255, 100 + int(100 * pulse))
            rad = CELL_SIZE/2.2

        # Draw glow
        glow_surf = pygame.Surface((CELL_SIZE*2, CELL_SIZE*2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, glow_col, (CELL_SIZE, CELL_SIZE), rad * 1.5)
        surface.blit(glow_surf, (px - CELL_SIZE, py - CELL_SIZE))
        
        # Draw core
        if self.type == 2:
            # Lightning bolt for powerup
            points = [(px, py - rad), (px - rad*0.6, py + rad*0.2), (px, py), (px - rad*0.2, py + rad), (px + rad*0.6, py - rad*0.2), (px, py), (px + rad*0.2, py - rad)]
            pygame.draw.polygon(surface, (255, 255, 255), points)
        else:
            pygame.draw.circle(surface, base_col, (int(px), int(py)), rad)

class Snake:
    def __init__(self):
        self.body = [(GRID_W//2, GRID_H//2), (GRID_W//2 - 1, GRID_H//2), (GRID_W//2 - 2, GRID_H//2)]
        self.direction = (1, 0)
        self.next_dir = (1, 0)
        self.hue_offset = 0.0
        self.invincible_time = 0.0
        
    def move(self, wrap_mode):
        self.direction = self.next_dir
        head_x, head_y = self.body[0]
        dx, dy = self.direction
        new_x, new_y = head_x + dx, head_y + dy
        
        hit_wall = False
        if new_x < 0 or new_x >= GRID_W or new_y < 0 or new_y >= GRID_H:
            if wrap_mode or self.invincible_time > 0:
                new_x = new_x % GRID_W
                new_y = new_y % GRID_H
            else:
                hit_wall = True
                
        self.body.insert(0, (new_x, new_y))
        return hit_wall
        
    def shrink(self):
        self.body.pop()
        
    def check_self_collision(self):
        if self.body[0] in self.body[1:]:
            return True
        return False
        
    def draw(self, surface, time_acc):
        self.hue_offset = (time_acc * 0.1) % 1.0
        is_inv = self.invincible_time > 0
        
        for i, (x, y) in enumerate(self.body):
            px = x * CELL_SIZE
            py = y * CELL_SIZE + UI_H
            rect = pygame.Rect(px + 1, py + 1, CELL_SIZE - 2, CELL_SIZE - 2)
            
            if is_inv:
                pulse = (math.sin(time_acc * 10) + 1)/2
                c = (200 + 55*pulse, 200 + 55*pulse, 255)
            else:
                hue = (self.hue_offset + i * 0.02) % 1.0
                c = hsv2rgb(hue, 0.8, 1.0)
                
            draw_rounded_rect(surface, c, rect, CELL_SIZE//4)
            
            # Eyes for head
            if i == 0:
                dx, dy = self.direction
                eye_off_x = CELL_SIZE * 0.25
                eye_off_y = CELL_SIZE * 0.25
                
                # Positions based on direction
                if dx == 1:   e1, e2 = (px + CELL_SIZE*0.7, py + eye_off_y), (px + CELL_SIZE*0.7, py + CELL_SIZE - eye_off_y)
                elif dx == -1:e1, e2 = (px + CELL_SIZE*0.3, py + eye_off_y), (px + CELL_SIZE*0.3, py + CELL_SIZE - eye_off_y)
                elif dy == 1: e1, e2 = (px + eye_off_x, py + CELL_SIZE*0.7), (px + CELL_SIZE - eye_off_x, py + CELL_SIZE*0.7)
                else:         e1, e2 = (px + eye_off_x, py + CELL_SIZE*0.3), (px + CELL_SIZE - eye_off_x, py + CELL_SIZE*0.3)
                
                pygame.draw.circle(surface, (255, 255, 255), (int(e1[0]), int(e1[1])), 4)
                pygame.draw.circle(surface, (255, 255, 255), (int(e2[0]), int(e2[1])), 4)
                pygame.draw.circle(surface, (0, 0, 0), (int(e1[0] + dx*2), int(e1[1] + dy*2)), 2)
                pygame.draw.circle(surface, (0, 0, 0), (int(e2[0] + dx*2), int(e2[1] + dy*2)), 2)

class GameEngine:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.state = STATE_MENU
        self.time_acc = 0.0
        
        self.snake = Snake()
        self.food = Food(self.snake.body)
        self.particles = []
        self.texts = []
        
        self.score = 0
        self.foods_eaten = 0
        self.multiplier = 1.0
        self.time_since_last_eat = 0.0
        
        self.move_timer = 0.0
        self.base_speed = 0.15
        
        self.countdown = 3.0
        self.fade_alpha = 0.0
        
        # Menu Demo
        self.demo_timer = 0.0
        
    def reset_game(self):
        self.snake = Snake()
        self.score = 0
        self.foods_eaten = 0
        self.multiplier = 1.0
        self.time_since_last_eat = 0.0
        self.particles = []
        self.texts = []
        self.food.respawn(self.snake.body, 0)
        self.countdown = 3.99
        self.fade_alpha = 0.0
        
        if save_data.difficulty == 0: self.base_speed = 0.18
        elif save_data.difficulty == 1: self.base_speed = 0.12
        else: self.base_speed = 0.08
        
    def spawn_particles(self, x, y, color, count=15):
        px = x * CELL_SIZE + CELL_SIZE/2
        py = y * CELL_SIZE + CELL_SIZE/2
        for _ in range(count):
            self.particles.append(Particle(px, py, color))
            
    def update_play(self, dt):
        if self.countdown > 0:
            self.countdown -= dt
            return
            
        self.time_since_last_eat += dt
        if self.time_since_last_eat > 5.0:
            self.multiplier = max(1.0, self.multiplier - dt * 0.5)
            
        if self.snake.invincible_time > 0:
            self.snake.invincible_time -= dt
            
        # Speed scaling based on length
        current_speed = max(0.04, self.base_speed * (0.98 ** self.foods_eaten))
        
        self.move_timer += dt
        if self.move_timer >= current_speed:
            self.move_timer -= current_speed
            
            hit_wall = self.snake.move(save_data.wrap_mode)
            if hit_wall or (self.snake.check_self_collision() and self.snake.invincible_time <= 0):
                audio.play(audio.buzzer)
                self.state = STATE_GAMEOVER
                if self.score > save_data.high_score:
                    save_data.high_score = self.score
                    save_data.save()
                return
                
            head = self.snake.body[0]
            if head[0] == self.food.x and head[1] == self.food.y:
                self.foods_eaten += 1
                
                if self.food.type == 0:
                    pts = int(10 * self.multiplier)
                    c = (255, 50, 50)
                    audio.play(audio.pop)
                elif self.food.type == 1:
                    pts = int(50 * self.multiplier)
                    c = (255, 215, 0)
                    audio.play(audio.crunch)
                else:
                    pts = int(20 * self.multiplier)
                    c = (50, 200, 255)
                    self.snake.invincible_time = 5.0
                    audio.play(audio.powerup)
                    
                self.score += pts
                self.multiplier += 0.5
                self.time_since_last_eat = 0.0
                
                self.spawn_particles(self.food.x, self.food.y, c)
                px = self.food.x * CELL_SIZE + CELL_SIZE/2
                py = self.food.y * CELL_SIZE + CELL_SIZE/2
                self.texts.append(FloatingText(px, py, f"+{pts}", c))
                
                self.food.respawn(self.snake.body, self.foods_eaten)
            else:
                self.snake.shrink()
                
        # Update VFX
        for p in self.particles[:]:
            p.update(dt)
            if p.life <= 0: self.particles.remove(p)
        for t in self.texts[:]:
            t.update(dt)
            if t.life <= 0: self.texts.remove(t)
            
        self.food.update(dt)

    def draw_hud(self):
        pygame.draw.rect(self.screen, (20, 24, 34), (0, 0, TOTAL_W, UI_H))
        pygame.draw.line(self.screen, (40, 50, 70), (0, UI_H-1), (TOTAL_W, UI_H-1), 2)
        
        font_large = get_font(32, True)
        font_small = get_font(18)
        
        score_t = font_large.render(f"{self.score}", True, (255, 255, 255))
        self.screen.blit(score_t, (20, 15))
        
        mult_t = font_small.render(f"x{self.multiplier:.1f}", True, (255, 200, 50))
        self.screen.blit(mult_t, (25 + score_t.get_width(), 25))
        
        hs_t = font_small.render(f"HIGH SCORE: {save_data.high_score}", True, (150, 160, 180))
        self.screen.blit(hs_t, (20, 5))
        
        info = f"Length: {len(self.snake.body)}   Foods: {self.foods_eaten}"
        info_t = font_small.render(info, True, (200, 200, 200))
        self.screen.blit(info_t, (TOTAL_W - info_t.get_width() - 20, 25))
        
        # Audio icon
        icon = "VOL: ON" if not audio.muted else "VOL: OFF"
        mute_t = font_small.render(icon, True, (255, 255, 255))
        self.screen.blit(mute_t, (TOTAL_W - 80, 5))
        
    def draw_grid(self):
        for x in range(0, WIDTH, CELL_SIZE):
            pygame.draw.line(self.screen, GRID_COLOR, (x, UI_H), (x, TOTAL_H))
        for y in range(0, HEIGHT, CELL_SIZE):
            pygame.draw.line(self.screen, GRID_COLOR, (0, y + UI_H), (WIDTH, y + UI_H))
            
    def draw_border_glow(self):
        hue = (self.time_acc * 0.1) % 1.0
        c = hsv2rgb(hue, 1.0, 1.0)
        
        for i in range(3, 0, -1):
            width = i * 4
            alpha = 100 // i
            surf = pygame.Surface((TOTAL_W, HEIGHT), pygame.SRCALPHA)
            pygame.draw.rect(surf, (*c, alpha), (0, 0, TOTAL_W, HEIGHT), width)
            self.screen.blit(surf, (0, UI_H))

    def render(self):
        self.screen.fill(BG_COLOR)
        
        if self.state == STATE_MENU or self.state == STATE_SETTINGS:
            # Draw background demo
            self.draw_grid()
            # Faux snake demo
            self.demo_timer += 0.05
            h = (self.demo_timer * 0.1) % 1.0
            c = hsv2rgb(h, 0.8, 1.0)
            for i in range(15):
                px = (TOTAL_W//2) + math.sin(self.demo_timer + i*0.2) * 200
                py = (TOTAL_H//2) + math.cos(self.demo_timer + i*0.2) * 150
                r = pygame.Rect(px, py, CELL_SIZE, CELL_SIZE)
                draw_rounded_rect(self.screen, c, r, CELL_SIZE//4)
                
            # Overlay
            surf = pygame.Surface((TOTAL_W, TOTAL_H), pygame.SRCALPHA)
            surf.fill((10, 12, 18, 200))
            self.screen.blit(surf, (0,0))
            
            if self.state == STATE_MENU:
                title_font = get_font(72, True)
                title_c = hsv2rgb(h, 0.5, 1.0)
                t = title_font.render("NEON SNAKE", True, title_c)
                self.screen.blit(t, (TOTAL_W//2 - t.get_width()//2, 150))
                
                if int(self.demo_timer * 2) % 2 == 0:
                    start_t = get_font(28).render("Press SPACE to Start", True, (255, 255, 255))
                    self.screen.blit(start_t, (TOTAL_W//2 - start_t.get_width()//2, 350))
                    
                hint_t = get_font(18).render("Press 'S' for Settings", True, (150, 150, 150))
                self.screen.blit(hint_t, (TOTAL_W//2 - hint_t.get_width()//2, 450))
                
            elif self.state == STATE_SETTINGS:
                t = get_font(48, True).render("SETTINGS", True, (255, 255, 255))
                self.screen.blit(t, (TOTAL_W//2 - t.get_width()//2, 100))
                
                diffs = ["Easy", "Medium", "Hard"]
                d_str = diffs[save_data.difficulty]
                w_str = "ON" if save_data.wrap_mode else "OFF"
                
                items = [
                    f"1. Difficulty: {d_str}",
                    f"2. Wall-Wrap Mode: {w_str}",
                    "Press ESC to Return"
                ]
                
                for i, item in enumerate(items):
                    color = (200, 200, 200) if i < 2 else (100, 150, 255)
                    t_item = get_font(28).render(item, True, color)
                    self.screen.blit(t_item, (TOTAL_W//2 - t_item.get_width()//2, 250 + i*50))
            return

        self.draw_hud()
        self.draw_grid()
        self.food.draw(self.screen)
        self.snake.draw(self.screen, self.time_acc)
        
        for p in self.particles: p.draw(self.screen)
        for t in self.texts: t.draw(self.screen)
        
        self.draw_border_glow()
        
        if self.state == STATE_PLAY and self.countdown > 0:
            count_val = int(self.countdown)
            txt = str(count_val) if count_val > 0 else "GO!"
            alpha = int((self.countdown % 1.0) * 255) if count_val > 0 else int(min(1.0, self.countdown)*255)
            font = get_font(100, True)
            t = font.render(txt, True, (255, 255, 255))
            t.set_alpha(alpha)
            self.screen.blit(t, (TOTAL_W//2 - t.get_width()//2, TOTAL_H//2 - t.get_height()//2))

        if self.state == STATE_PAUSE:
            surf = pygame.Surface((TOTAL_W, TOTAL_H), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 150))
            self.screen.blit(surf, (0,0))
            t = get_font(64, True).render("PAUSED", True, (255, 255, 255))
            self.screen.blit(t, (TOTAL_W//2 - t.get_width()//2, TOTAL_H//2 - t.get_height()//2))

        if self.state == STATE_GAMEOVER:
            self.fade_alpha = min(200, self.fade_alpha + 2)
            surf = pygame.Surface((TOTAL_W, TOTAL_H), pygame.SRCALPHA)
            surf.fill((10, 0, 0, int(self.fade_alpha)))
            self.screen.blit(surf, (0,0))
            
            if self.fade_alpha > 150:
                t = get_font(64, True).render("GAME OVER", True, (255, 50, 50))
                self.screen.blit(t, (TOTAL_W//2 - t.get_width()//2, TOTAL_H//2 - 100))
                
                s = get_font(32).render(f"Final Score: {self.score}", True, (255, 255, 255))
                self.screen.blit(s, (TOTAL_W//2 - s.get_width()//2, TOTAL_H//2))
                
                h = get_font(24).render(f"High Score: {save_data.high_score}", True, (200, 200, 200))
                self.screen.blit(h, (TOTAL_W//2 - h.get_width()//2, TOTAL_H//2 + 50))
                
                p = get_font(28).render("Press SPACE to Play Again", True, (150, 255, 150))
                if int(self.time_acc * 2) % 2 == 0:
                    self.screen.blit(p, (TOTAL_W//2 - p.get_width()//2, TOTAL_H//2 + 120))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            self.time_acc += dt
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_m:
                        audio.muted = not audio.muted
                        
                    if self.state == STATE_MENU:
                        if event.key == pygame.K_SPACE:
                            self.reset_game()
                            self.state = STATE_PLAY
                        elif event.key == pygame.K_s:
                            self.state = STATE_SETTINGS
                            
                    elif self.state == STATE_SETTINGS:
                        if event.key == pygame.K_1:
                            save_data.difficulty = (save_data.difficulty + 1) % 3
                            save_data.save()
                        elif event.key == pygame.K_2:
                            save_data.wrap_mode = not save_data.wrap_mode
                            save_data.save()
                        elif event.key == pygame.K_ESCAPE:
                            self.state = STATE_MENU
                            
                    elif self.state == STATE_PLAY:
                        if event.key in (pygame.K_w, pygame.K_UP) and self.snake.direction != (0, 1):
                            self.snake.next_dir = (0, -1)
                        elif event.key in (pygame.K_s, pygame.K_DOWN) and self.snake.direction != (0, -1):
                            self.snake.next_dir = (0, 1)
                        elif event.key in (pygame.K_a, pygame.K_LEFT) and self.snake.direction != (1, 0):
                            self.snake.next_dir = (-1, 0)
                        elif event.key in (pygame.K_d, pygame.K_RIGHT) and self.snake.direction != (-1, 0):
                            self.snake.next_dir = (1, 0)
                        elif event.key == pygame.K_p or event.key == pygame.K_ESCAPE:
                            self.state = STATE_PAUSE
                            
                    elif self.state == STATE_PAUSE:
                        if event.key == pygame.K_p or event.key == pygame.K_ESCAPE:
                            self.state = STATE_PLAY
                            
                    elif self.state == STATE_GAMEOVER:
                        if event.key == pygame.K_SPACE:
                            self.reset_game()
                            self.state = STATE_PLAY

            if self.state == STATE_PLAY:
                self.update_play(dt)
                
            self.render()
            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    screen = pygame.display.set_mode((TOTAL_W, TOTAL_H))
    pygame.display.set_caption("Neon Snake - The Ultimate Experience")
    engine = GameEngine(screen)
    engine.run()
