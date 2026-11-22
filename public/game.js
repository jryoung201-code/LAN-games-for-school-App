const byId = id => document.getElementById(id);
const canvas = byId('arena');
const ctx = canvas.getContext('2d');
const keys = new Set();
const catalog = [['speed', 'Speed'], ['damage', 'Damage'], ['health', 'Max HP'], ['fireRate', 'Fire rate']];
const buttons = new Map();
let token;
let state;
let aim;
let firing = false;
let pendingUpgrade;
let lastScore = '';

for (const [index, [key, name]] of catalog.entries()) {
  const button = document.createElement('button');
  const label = document.createElement('span');
  const price = document.createElement('span');
  label.textContent = (index + 1) + ' · ' + name;
  button.append(label, price);
  button.addEventListener('click', () => queueUpgrade(key));
  byId('upgrades').append(button);
  buttons.set(key, { button, price });
}

function queueUpgrade(key) {
  if (!buttons.get(key).button.disabled) pendingUpgrade = key;
}

async function post(path, data) {
  const response = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    signal: AbortSignal.timeout(3000),
  });
  const result = await response.json();
  if (!response.ok) throw Object.assign(new Error(result.error), { status: response.status });
  return result;
}

const movementKeys = ['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowLeft', 'ArrowDown', 'ArrowRight', 'Space'];
window.addEventListener('keydown', event => {
  if (!token) return;
  if (movementKeys.includes(event.code)) {
    if (event.code === 'Space' && document.activeElement?.tagName === 'BUTTON') return;
    event.preventDefault();
    keys.add(event.code);
  }
  if (!event.repeat && /^Digit[1-4]$/.test(event.code)) queueUpgrade(catalog[Number(event.code.at(-1)) - 1][0]);
});
window.addEventListener('keyup', event => keys.delete(event.code));
window.addEventListener('blur', () => { keys.clear(); firing = false; });
function aimAt(event) {
  const rect = canvas.getBoundingClientRect();
  aim = { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height };
}
canvas.addEventListener('pointermove', aimAt);
canvas.addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  document.activeElement?.blur();
  aimAt(event);
  firing = true;
  canvas.setPointerCapture(event.pointerId);
});
window.addEventListener('pointerup', () => { firing = false; });
window.addEventListener('pointercancel', () => { firing = false; });

byId('join-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  byId('error').textContent = '';
  try {
    const joined = await post('/join', { name: byId('name').value });
    token = joined.token;
    canvas.width = joined.width;
    canvas.height = joined.height;
    byId('entrance').hidden = true;
    byId('game').hidden = false;
    update(joined.state);
    poll();
  } catch (error) {
    byId('error').textContent = error.status ? error.message : 'Could not reach the host.';
  } finally {
    button.disabled = false;
  }
});

const pressed = (first, second) => Number(keys.has(first) || keys.has(second));

async function poll() {
  const player = state.players.find(entry => entry.id === state.self);
  const upgrade = pendingUpgrade;
  pendingUpgrade = undefined;
  try {
    update(await post('/state', {
      token, upgrade,
      dx: pressed('KeyD', 'ArrowRight') - pressed('KeyA', 'ArrowLeft'),
      dy: pressed('KeyS', 'ArrowDown') - pressed('KeyW', 'ArrowUp'),
      firing: firing || keys.has('Space'),
      angle: aim ? Math.atan2(aim.y - player.y, aim.x - player.x) : player.angle,
    }));
    byId('connection').textContent = state.players.length + ' / 16 pilots online';
  } catch (error) {
    if (error.status === 401) {
      token = undefined;
      aim = undefined;
      keys.clear();
      firing = false;
      byId('game').hidden = true;
      byId('entrance').hidden = false;
      byId('connection').textContent = 'Disconnected';
      byId('error').textContent = error.message;
      return;
    }
    byId('connection').textContent = 'Reconnecting…';
  }
  setTimeout(poll, 42);
}

function update(next) {
  state = next;
  byId('points').textContent = state.points;
  for (const [key, { button, price }] of buttons) {
    const level = state.levels[key];
    const cost = 5 + 5 * level;
    button.disabled = Boolean(state.respawn) || level === 5 || state.points < cost;
    price.textContent = level === 5 ? 'MAX' : 'Lv ' + level + ' / ' + cost + ' pts';
  }
  const notice = state.respawn ? state.notice + ' · Respawn in ' + Math.ceil(state.respawn / 1000) + 's' : state.notice;
  if (notice !== byId('notice').textContent) byId('notice').textContent = notice;
  byId('notice').hidden = !notice;
  const scores = [...state.players].sort((a, b) => b.kills - a.kills || b.points - a.points);
  const score = JSON.stringify(scores.map(p => [p.id, p.name, p.kills, p.points]));
  if (score !== lastScore) {
    byId('scores').replaceChildren(...scores.map(player => {
      const li = document.createElement('li');
      li.textContent = player.name + (player.id === state.self ? ' (you)' : '') + ' · ' + player.kills + ' K · ' + player.points + ' pts';
      return li;
    }));
    lastScore = score;
  }
  draw();
}

function circle(x, y, r, fill) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
}

function draw() {
  ctx.fillStyle = '#101d29';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = '#1b2d3b';
  ctx.beginPath();
  for (let x = 0; x < canvas.width; x += 40) { ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); }
  for (let y = 0; y < canvas.height; y += 40) { ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); }
  ctx.stroke();
  for (const coin of state.coins) {
    circle(coin.x, coin.y, coin.gold ? 10 : 7, coin.gold ? '#f6d365' : '#aec0cd');
    circle(coin.x, coin.y, coin.gold ? 5 : 3, coin.gold ? '#ac7228' : '#617788');
  }
  for (const shot of state.shots) circle(shot.x, shot.y, 5, shot.color);
  for (const player of state.players) {
    if (player.hp <= 0) continue;
    const own = player.id === state.self;
    const angle = own && aim ? Math.atan2(aim.y - player.y, aim.x - player.x) : player.angle;
    ctx.save();
    ctx.translate(player.x, player.y);
    ctx.rotate(angle);
    ctx.fillStyle = '#091117';
    ctx.fillRect(-18, -18, 36, 9);
    ctx.fillRect(-18, 9, 36, 9);
    ctx.fillStyle = player.color;
    ctx.fillRect(-17, -13, 32, 26);
    ctx.fillRect(0, -4, 26, 8);
    circle(0, 0, 8, '#284148');
    ctx.restore();
    if (own || player.shield) {
      ctx.beginPath();
      ctx.arc(player.x, player.y, 24, 0, Math.PI * 2);
      ctx.strokeStyle = player.shield ? '#8bbaff' : '#ffffffb0';
      ctx.stroke();
    }
    ctx.fillStyle = '#081219';
    ctx.fillRect(player.x - 20, player.y + 28, 40, 5);
    ctx.fillStyle = player.color;
    ctx.fillRect(player.x - 20, player.y + 28, 40 * player.hp / player.maxHp, 5);
    ctx.textAlign = 'center';
    ctx.font = '600 15px system-ui';
    ctx.fillStyle = '#eff8fc';
    ctx.fillText(player.name, player.x, player.y - 30);
  }
}
