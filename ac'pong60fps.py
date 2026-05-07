import array
import math
import os
import random
import sys

import pygame

# Tear-free presents: hint double-buffering; must be set before pygame initializes SDL.
os.environ.setdefault("SDL_VIDEO_DOUBLE_BUFFER", "1")

# Atari-ish audio: low sample rate; slightly larger buffer reduces pops when the frame paces tightly
AUDIO_SR = 22050
pygame.mixer.pre_init(AUDIO_SR, size=-16, channels=1, buffer=512)
pygame.init()

WIDTH = 800
HEIGHT = 480
TARGET_FPS = 60

# Fixed logical resolution (no pygame.SCALED: that scales the window to arbitrary aspect and stretches sprites).
# DOUBLEBUF + vsync still requests a tear-free swap where the driver supports it.
_flags = pygame.DOUBLEBUF
try:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), _flags, vsync=1)
except TypeError:
    screen = pygame.display.set_mode((WIDTH, HEIGHT), _flags)

pygame.display.set_caption("AC's Pong")

try:
    pygame.mixer.init()
except pygame.error:
    pass

FONT = pygame.font.Font(None, 80)
TITLE_FONT = pygame.font.Font(None, 96)
SMALL_FONT = pygame.font.Font(None, 32)
MENU_FONT = pygame.font.Font(None, 40)
WIN_SCORE = 5

# Movement tuned so one frame at 60 Hz feels close to classic Pong pace (not “modern fast pong”)
BALL_BASE_SPEED = 4.75
BALL_MAX_SPEED = 9.0
PADDLE_MOVE_SPEED = 5.25
AI_MAX_SPEED = 5.0
AI_DEAD_ZONE = 4


def _square_wave(freq_hz: float, duration_ms: float, volume: float = 0.22) -> pygame.mixer.Sound | None:
    if not pygame.mixer.get_init():
        return None
    n = max(1, int(AUDIO_SR * (duration_ms / 1000.0)))
    period = int(AUDIO_SR / max(30.0, freq_hz))
    if period < 2:
        period = 2
    amp = int(32767 * min(1.0, max(0.0, volume)))
    buf = array.array("h")
    for i in range(n):
        high = ((i % period) / period) < 0.5
        buf.append(amp if high else -amp)
    try:
        return pygame.mixer.Sound(buffer=buf.tobytes())
    except pygame.error:
        return None


# Atari-style tones: short square bursts
snd_wall = _square_wave(320, 45, 0.18)
snd_paddle = _square_wave(220, 70, 0.24)
snd_score = _square_wave(140, 160, 0.28)


def play(s: pygame.mixer.Sound | None) -> None:
    if s is not None:
        s.play()


class Ball:
    def __init__(self):
        self.radius = 9
        self.base_speed = BALL_BASE_SPEED
        self.reset()

    def reset(self) -> None:
        self.x = WIDTH // 2
        self.y = HEIGHT // 2
        angle = random.uniform(-math.pi / 4, math.pi / 4)
        if random.choice((True, False)):
            angle += math.pi
        speed = self.base_speed
        self.vx = speed * math.cos(angle)
        self.vy = speed * math.sin(angle)


class Paddle:
    def __init__(self, x: int):
        self.x = x
        self.width = 12
        self.height = 86
        self.speed = PADDLE_MOVE_SPEED
        self.y = HEIGHT // 2 - self.height // 2

    def rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.width, self.height)


class Score:
    def __init__(self) -> None:
        self.player = 0
        self.cpu = 0


ball = Ball()
paddle_left = Paddle(36)
paddle_right = Paddle(WIDTH - 48)
score = Score()


def reset_ball() -> None:
    ball.reset()


def clamp_paddle(p: Paddle) -> None:
    p.y = max(0, min(HEIGHT - p.height, p.y))


def set_paddle_from_mouse_y(mouse_y: int, p: Paddle) -> None:
    center = max(p.height // 2, min(HEIGHT - p.height // 2, mouse_y))
    p.y = int(center - p.height // 2)
    clamp_paddle(p)


def update_ai() -> None:
    """Right paddle: react when the ball is moving toward it; otherwise drift to center."""
    target_y = HEIGHT // 2 - paddle_right.height // 2
    if ball.vx > 0:
        predict = ball.y + (ball.vy * ((paddle_right.x - ball.x) / max(8.0, abs(ball.vx))))
        predict = max(ball.radius, min(HEIGHT - ball.radius, predict))
        target_y = int(predict - paddle_right.height // 2)

    diff = (target_y + paddle_right.height // 2) - (paddle_right.y + paddle_right.height // 2)
    if abs(diff) < AI_DEAD_ZONE:
        return
    step = AI_MAX_SPEED if diff > 0 else -AI_MAX_SPEED
    if abs(diff) < AI_MAX_SPEED:
        step = int(math.copysign(abs(diff), diff))
    paddle_right.y += step
    clamp_paddle(paddle_right)


def paddle_hit_velocity(paddle: Paddle, going_right: bool) -> None:
    rel = (ball.y - (paddle.y + paddle.height / 2)) / (paddle.height / 2)
    rel = max(-1.0, min(1.0, rel))
    angle = rel * (math.pi / 3)
    spd = math.hypot(ball.vx, ball.vy)
    spd = min(spd * 1.04, BALL_MAX_SPEED)
    if going_right:
        ball.vx = abs(spd * math.cos(angle))
    else:
        ball.vx = -abs(spd * math.cos(angle))
    ball.vy = spd * math.sin(angle)


def update() -> None:
    prev_vy_sign = 1 if ball.vy >= 0 else -1

    ball.x += ball.vx
    ball.y += ball.vy

    if ball.y - ball.radius <= 0:
        ball.y = ball.radius
        ball.vy = abs(ball.vy)
        if prev_vy_sign < 0:
            play(snd_wall)
    elif ball.y + ball.radius >= HEIGHT:
        ball.y = HEIGHT - ball.radius
        ball.vy = -abs(ball.vy)
        if prev_vy_sign > 0:
            play(snd_wall)

    pl = paddle_left.rect()
    pr = paddle_right.rect()

    ball_rect = pygame.Rect(
        ball.x - ball.radius,
        ball.y - ball.radius,
        ball.radius * 2,
        ball.radius * 2,
    )

    if ball_rect.colliderect(pl) and ball.vx < 0:
        ball.x = pl.right + ball.radius
        paddle_hit_velocity(paddle_left, going_right=True)
        play(snd_paddle)

    if ball_rect.colliderect(pr) and ball.vx > 0:
        ball.x = pr.left - ball.radius
        paddle_hit_velocity(paddle_right, going_right=False)
        play(snd_paddle)

    if ball.x < -ball.radius:
        score.cpu += 1
        play(snd_score)
        reset_ball()
    elif ball.x > WIDTH + ball.radius:
        score.player += 1
        play(snd_score)
        reset_ball()


def draw_playfield() -> None:
    # Clear the back buffer every frame; DOUBLEBUF alternates buffers so without this you see
    # the previous frame underneath the new one (looks like ghosting/stretching on motion).
    screen.fill((12, 12, 18))

    for y in range(0, HEIGHT, 22):
        pygame.draw.rect(screen, (55, 55, 65), (WIDTH // 2 - 3, y, 6, 11))

    pygame.draw.circle(screen, (235, 235, 240), (int(ball.x), int(ball.y)), ball.radius)
    pygame.draw.rect(screen, (220, 245, 255), paddle_left.rect())
    pygame.draw.rect(screen, (255, 215, 215), paddle_right.rect())

    you = FONT.render(str(score.player), True, (200, 230, 255))
    cpu_s = FONT.render(str(score.cpu), True, (255, 200, 200))
    screen.blit(you, (WIDTH // 4 - you.get_width() // 2, 28))
    screen.blit(cpu_s, (3 * WIDTH // 4 - cpu_s.get_width() // 2, 28))

    hint = SMALL_FONT.render("Mouse: your paddle   |   First to 5   |   ESC: menu", True, (115, 115, 125))
    screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 38))


def draw_game_over_overlay() -> None:
    headline = None
    if score.player >= WIN_SCORE:
        headline = "PLAYER WON"
    elif score.cpu >= WIN_SCORE:
        headline = "AI WINS"
    overlay = pygame.Surface((WIDTH, HEIGHT))
    overlay.set_alpha(205)
    overlay.fill((0, 0, 0))
    screen.blit(overlay, (0, 0))
    if headline:
        ws = FONT.render(headline, True, (255, 255, 255))
        screen.blit(ws, (WIDTH // 2 - ws.get_width() // 2, HEIGHT // 2 - 56))
    yn = MENU_FONT.render("Y / N ?", True, (190, 255, 190))
    screen.blit(yn, (WIDTH // 2 - yn.get_width() // 2, HEIGHT // 2 + 4))
    rs = SMALL_FONT.render("Y = RESTART     N = QUIT", True, (200, 200, 200))
    screen.blit(rs, (WIDTH // 2 - rs.get_width() // 2, HEIGHT // 2 + 56))


def draw_main_menu() -> None:
    screen.fill((12, 12, 18))
    title = TITLE_FONT.render("AC's Pong", True, (245, 245, 250))
    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 3))

    blip = MENU_FONT.render("Click or SPACE — Play", True, (180, 220, 180))
    screen.blit(blip, (WIDTH // 2 - blip.get_width() // 2, HEIGHT // 2 + 10))

    sub = SMALL_FONT.render(
        "You: mouse (left)   ·   CPU: right   ·   First to 5 wins", True, (130, 130, 140)
    )
    screen.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 70))

    fps_note = SMALL_FONT.render(f"{TARGET_FPS} FPS — Atari pacing", True, (95, 95, 105))
    screen.blit(fps_note, (WIDTH // 2 - fps_note.get_width() // 2, HEIGHT - 48))


def reset_match() -> None:
    score.player = 0
    score.cpu = 0
    reset_ball()
    paddle_left.y = HEIGHT // 2 - paddle_left.height // 2
    paddle_right.y = HEIGHT // 2 - paddle_right.height // 2


# --- states: menu | playing | game_over
STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"

state = STATE_MENU
clock = pygame.time.Clock()


def go_menu() -> None:
    global state
    state = STATE_MENU
    pygame.mouse.set_visible(True)


def start_game() -> None:
    global state
    reset_match()
    state = STATE_PLAYING
    pygame.mouse.set_visible(False)
    pygame.mouse.set_pos(WIDTH // 2, HEIGHT // 2)


while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if state == STATE_MENU:
                    pygame.quit()
                    sys.exit()
                go_menu()

            if state == STATE_MENU and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                start_game()

            if state == STATE_GAME_OVER:
                if event.key == pygame.K_y:
                    start_game()
                if event.key == pygame.K_n:
                    pygame.quit()
                    sys.exit()

        if state == STATE_MENU and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            start_game()

    dt_ms = clock.tick(TARGET_FPS)

    if state == STATE_MENU:
        draw_main_menu()
    elif state == STATE_PLAYING:
        mx, my = pygame.mouse.get_pos()
        set_paddle_from_mouse_y(my, paddle_left)
        update_ai()
        update()
        draw_playfield()
        if score.player >= WIN_SCORE or score.cpu >= WIN_SCORE:
            state = STATE_GAME_OVER
            pygame.mouse.set_visible(True)
    elif state == STATE_GAME_OVER:
        draw_playfield()
        draw_game_over_overlay()

    pygame.display.set_caption(f"AC's Pong — {clock.get_fps():.0f} FPS")
    pygame.display.flip()
