"""LAN Games host for the Tank Circuit arena."""
import argparse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from random import uniform
import socket
from threading import Event, Lock, Thread
from time import monotonic
from uuid import uuid4
import webbrowser

WIDTH, HEIGHT = 1440, 900
RADIUS, TICK = 19, 0.025
UPGRADES = ('speed', 'damage', 'health', 'fireRate')
COLORS = ('#69e9b3', '#ff9d72', '#8bbaff', '#e9a2ff', '#f6d365', '#ff8ca8')


@dataclass
class Player:
    id: int
    name: str
    color: str
    seen: float
    x: float = 0
    y: float = 0
    angle: float = 0
    dx: float = 0
    dy: float = 0
    firing: bool = False
    hp: int = 100
    points: int = 0
    kills: int = 0
    levels: dict = field(default_factory=lambda: dict.fromkeys(UPGRADES, 0))
    dead_until: float = 0
    shield_until: float = 0
    next_shot: float = 0
    notice: str = ''
    notice_until: float = 0

    @property
    def max_hp(self):
        return 100 + self.levels['health'] * 25


@dataclass
class Shot:
    owner: Player
    x: float
    y: float
    vx: float
    vy: float
    damage: int
    expires: float


def point():
    return uniform(45, WIDTH - 45), uniform(45, HEIGHT - 45)


def clamp(value, low, high):
    return min(high, max(low, value))


def number(value, fallback=0):
    if type(value) in (int, float) and -1e9 <= value <= 1e9:
        return value
    return fallback


class Arena:
    def __init__(self):
        self.players = {}
        self.shots = []
        self.coins = []
        self.next_id = 0
        self.lock = Lock()
        self.replenish()

    def replenish(self):
        for gold, target in ((False, 36), (True, 7)):
            missing = target - sum(coin[2] == gold for coin in self.coins)
            self.coins.extend((*point(), gold) for _ in range(missing))

    def spawn(self, player, now):
        for _ in range(30):
            x, y = point()
            if all(other is player or other.dead_until or math.hypot(other.x-x, other.y-y) > 180
                   for other in self.players.values()):
                break
        player.x, player.y = x, y
        player.hp = player.max_hp
        player.dead_until = 0
        player.shield_until = now + 1.6
        player.next_shot = 0

    @staticmethod
    def kill(victim, attacker, now):
        stolen = victim.points
        attacker.points += stolen
        attacker.kills += 1
        attacker.notice = f'Eliminated {victim.name} · +{stolen} points'
        attacker.notice_until = now + 3
        victim.points = 0
        victim.levels = dict.fromkeys(UPGRADES, 0)
        victim.dx = victim.dy = 0
        victim.firing = False
        victim.dead_until = now + 2.2
        victim.notice = f'{attacker.name} eliminated you and took {stolen} points'
        victim.notice_until = now + 3.9

    def step(self, now):
        for token, player in list(self.players.items()):
            if now - player.seen > 15:
                del self.players[token]
                self.shots = [shot for shot in self.shots if shot.owner is not player]
                continue
            if player.dead_until:
                if now >= player.dead_until:
                    self.spawn(player, now)
                continue
            if now - player.seen > 0.25:
                continue
            movement = (210 + player.levels['speed'] * 32) * TICK
            movement /= max(1, math.hypot(player.dx, player.dy))
            player.x = clamp(player.x + player.dx * movement, RADIUS, WIDTH - RADIUS)
            player.y = clamp(player.y + player.dy * movement, RADIUS, HEIGHT - RADIUS)
            remaining = []
            for x, y, gold in self.coins:
                if math.hypot(player.x-x, player.y-y) < RADIUS + 9:
                    player.points += 5 if gold else 1
                else:
                    remaining.append((x, y, gold))
            self.coins = remaining
            if player.firing and now >= max(player.next_shot, player.shield_until):
                player.next_shot = now + 0.510 - 0.065 * player.levels['fireRate']
                vx, vy = math.cos(player.angle), math.sin(player.angle)
                self.shots.append(Shot(player, player.x + vx*25, player.y + vy*25, vx, vy,
                                       20 + player.levels['damage'] * 7, now + 1.15))

        remaining_shots = []
        for shot in self.shots:
            if shot.owner.dead_until or now >= shot.expires:
                continue
            shot.x += shot.vx * 610 * TICK
            shot.y += shot.vy * 610 * TICK
            if not (0 <= shot.x <= WIDTH and 0 <= shot.y <= HEIGHT):
                continue
            for player in self.players.values():
                if player is shot.owner or player.dead_until or now < player.shield_until:
                    continue
                if math.hypot(player.x-shot.x, player.y-shot.y) >= RADIUS + 4:
                    continue
                player.hp = max(0, player.hp - shot.damage)
                if not player.hp:
                    self.kill(player, shot.owner, now)
                break
            else:
                remaining_shots.append(shot)
        self.shots = [shot for shot in remaining_shots if not shot.owner.dead_until]
        self.replenish()

    def snapshot(self, player, now):
        return {
            'self': player.id, 'points': player.points, 'levels': dict(player.levels),
            'respawn': max(0, (player.dead_until - now) * 1000),
            'notice': player.notice if now < player.notice_until else '',
            'players': [
                dict(id=p.id, name=p.name, color=p.color, x=p.x, y=p.y, angle=p.angle,
                     hp=p.hp, maxHp=p.max_hp, shield=now < p.shield_until, kills=p.kills, points=p.points)
                for p in self.players.values()
            ],
            'coins': [dict(x=x, y=y, gold=gold) for x, y, gold in self.coins],
            'shots': [dict(x=s.x, y=s.y, color=s.owner.color) for s in self.shots],
        }

    def request(self, route, data):
        with self.lock:
            now = monotonic()
            if route == '/join':
                name = data.get('name')
                name = name.strip()[:20] if isinstance(name, str) else ''
                if not name:
                    return 400, {'error': 'Enter a pilot name'}
                if len(self.players) >= 16:
                    return 409, {'error': 'Arena is full (16 players)'}
                token = uuid4().hex
                self.next_id += 1
                player = Player(self.next_id, name, COLORS[(self.next_id - 1) % len(COLORS)], now)
                self.spawn(player, now)
                self.players[token] = player
                return 200, dict(token=token, width=WIDTH, height=HEIGHT, state=self.snapshot(player, now))
            token = data.get('token')
            player = self.players.get(token) if isinstance(token, str) else None
            if player is None:
                return 401, {'error': 'Session ended. Join again to play.'}
            player.seen = now
            if not player.dead_until:
                player.dx = clamp(number(data.get('dx')), -1, 1)
                player.dy = clamp(number(data.get('dy')), -1, 1)
                player.angle = number(data.get('angle'), player.angle) % math.tau
                player.firing = data.get('firing') is True
                upgrade = data.get('upgrade')
                if upgrade in UPGRADES:
                    level = player.levels[upgrade]
                    cost = 5 + 5 * level
                    if level < 5 and player.points >= cost:
                        player.points -= cost
                        player.levels[upgrade] += 1
                        if upgrade == 'health':
                            player.hp += 25
            return 200, self.snapshot(player, now)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    timeout = 5
    assets = {'/': ('index.html', 'text/html'), '/game.js': ('game.js', 'text/javascript'),
              '/style.css': ('style.css', 'text/css')}

    def log_message(self, pattern, *args):
        pass

    def send(self, status, content_type, body):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def send_json(self, status, data):
        self.send(status, 'application/json', json.dumps(data, separators=(',', ':')).encode())

    def do_GET(self):
        asset = self.assets.get(self.path.partition('?')[0])
        if asset is None:
            return self.send_json(404, {'error': 'Page not found'})
        filename, content_type = asset
        body = (Path(__file__).resolve().parent / 'public' / filename).read_bytes()
        self.send(200, content_type + '; charset=utf-8', body)

    def do_POST(self):
        route = self.path.partition('?')[0]
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            size = -1
        if route not in ('/join', '/state') or self.headers.get_content_type() != 'application/json' or not 0 < size <= 2048:
            self.close_connection = True
            return self.send_json(400, {'error': 'Invalid request'})
        try:
            data = json.loads(self.rfile.read(size))
        except (ValueError, TimeoutError):
            self.close_connection = True
            return self.send_json(400, {'error': 'Invalid JSON'})
        if not isinstance(data, dict):
            return self.send_json(400, {'error': 'Invalid request'})
        self.send_json(*self.server.arena.request(route, data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    arena = Arena()
    stop = Event()

    def run_ticks():
        while not stop.wait(TICK):
            with arena.lock:
                arena.step(monotonic())

    with ThreadingHTTPServer(('0.0.0.0', args.port), Handler) as server:
        server.arena = arena
        Thread(target=run_ticks, daemon=True).start()
        port = server.server_port
        local_url = f'http://localhost:{port}'
        print(f'Host play link: {local_url}', flush=True)
        try:
            addresses = socket.gethostbyname_ex(socket.gethostname())[2]
        except OSError:
            addresses = []
        for address in sorted(set(addresses)):
            if not address.startswith('127.'):
                print(f'LAN join link: http://{address}:{port}', flush=True)
        print('Keep this window open while playing. Press Ctrl+C to end the game.', flush=True)
        if not args.no_browser:
            Thread(target=webbrowser.open, args=(local_url,), daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()


if __name__ == '__main__':
    main()
