import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic
import unittest
from urllib.request import Request, urlopen

from server import Arena, TICK, UPGRADES


class ArenaTests(unittest.TestCase):
    def test_upgrade_kill_transfer_and_respawn(self):
        arena = Arena()
        _, attacker_session = arena.request('/join', {'name': 'Alpha'})
        _, victim_session = arena.request('/join', {'name': 'Beta'})
        a = arena.players[attacker_session['token']]
        b = arena.players[victim_session['token']]
        a.x, a.y, b.x, b.y = 200, 200, 320, 200
        now = monotonic()
        a.shield_until = b.shield_until = 0
        arena.coins = [(320, 200, True), (320, 200, True), (320, 200, False)]
        arena.step(now)
        self.assertEqual(b.points, 11)
        _, state = arena.request('/state', {'token': victim_session['token'], 'upgrade': 'health'})
        self.assertEqual(state['levels']['health'], 1)
        self.assertEqual(b.hp, 125)
        self.assertEqual(b.points, 6)
        a.firing = True
        a.angle = 0
        for i in range(200):
            now += TICK
            a.seen = b.seen = now
            arena.coins.clear()
            arena.step(now)
            if b.dead_until:
                break
        self.assertEqual(a.kills, 1)
        self.assertEqual(a.points, 6)
        self.assertEqual(b.points, 0)
        self.assertEqual(b.levels, dict.fromkeys(UPGRADES, 0))
        arena.step(b.dead_until + TICK)
        self.assertEqual(b.hp, 100)
        self.assertEqual(b.dead_until, 0)


class HostTests(unittest.TestCase):
    def test_host_serves_browser_and_accepts_two_players(self):
        exe = os.environ.get('TANK_CIRCUIT_EXE')
        command = [exe] if exe else [sys.executable, str(Path(__file__).with_name('server.py'))]
        with subprocess.Popen(command + ['--port', '0', '--no-browser'], stdout=subprocess.PIPE, text=True) as host:
            try:
                _, separator, url = host.stdout.readline().strip().partition('Host play link: ')
                self.assertTrue(separator)
                for path, marker in (('/', b'Tank Circuit'), ('/game.js', b'queueUpgrade'), ('/style.css', b'.battle')):
                    with urlopen(url + path, timeout=5) as response:
                        self.assertIn(marker, response.read())
                states = []
                for name in ('Alpha', 'Beta'):
                    request = Request(url + '/join', json.dumps({'name': name}).encode(),
                                      {'Content-Type': 'application/json'})
                    with urlopen(request, timeout=5) as response:
                        states.append(json.load(response))
                self.assertNotEqual(states[0]['token'], states[1]['token'])
                self.assertEqual(len(states[1]['state']['players']), 2)
            finally:
                host.terminate()
                host.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
