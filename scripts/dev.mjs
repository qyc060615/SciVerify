import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const backend = path.join(root, 'backend')
const frontend = path.join(root, 'frontend')
const vite = path.join(frontend, 'node_modules', 'vite', 'bin', 'vite.js')
const windows = process.platform === 'win32'
const checkOnly = process.argv.includes('--check')
const children = new Set()
let stopping = false
let shutdownTimer

function fail(message) { console.error('\n[dev] ' + message); process.exitCode = 1 }
function findPython() {
  const executable = windows ? 'python.exe' : 'bin/python'
  const envDirs = (process.env.CONDA_ENVS_PATH ?? '').split(path.delimiter).filter(Boolean)
  const candidates = process.env.RESEARCHGUARD_PYTHON ? [process.env.RESEARCHGUARD_PYTHON] : [
    path.join(backend, '.venv', windows ? 'Scripts/python.exe' : 'bin/python'),
    path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python'),
    ...(process.env.CONDA_PREFIX ? [path.join(process.env.CONDA_PREFIX, executable)] : []),
    ...envDirs.map(dir => path.join(dir, 'researchguard', executable)),
    ...(process.env.CONDA_EXE ? [path.join(path.dirname(path.dirname(process.env.CONDA_EXE)), 'envs', 'researchguard', executable)] : []),
    ...(windows ? ['D:/conda_envs/researchguard/python.exe'] : []),
    'python', ...(windows ? [] : ['python3']),
  ]
  for (const candidate of [...new Set(candidates)]) {
    if (path.isAbsolute(candidate) && !existsSync(candidate)) continue
    const probe = spawnSync(candidate, ['-c', 'import sys, uvicorn, fastapi, dotenv; assert sys.version_info >= (3, 11)'],
      { cwd: backend, encoding: 'utf8', timeout: 10000, windowsHide: true })
    if (probe.status === 0) return candidate
  }
  throw new Error('No Python 3.11+ environment with backend dependencies found. Set RESEARCHGUARD_PYTHON to your researchguard Python executable, or activate that Conda environment.')
}
function portFree(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', error => error.code === 'EADDRINUSE' ? resolve(false) : reject(error))
    server.listen({ host: '127.0.0.1', port, exclusive: true }, () => server.close(() => resolve(true)))
  })
}
function stop(signal = 'SIGTERM') {
  if (stopping) return
  stopping = true
  console.log('\n[dev] Stopping the services started by this command…')
  // Ctrl+C reaches children in this console too; let Uvicorn finish its shutdown.
  // Other exits terminate only children owned by this launcher, never existing services.
  if (signal !== 'SIGINT') for (const child of children) child.kill('SIGTERM')
  shutdownTimer = setTimeout(() => {
    for (const child of children) child.kill('SIGKILL')
  }, 35000)
  shutdownTimer.unref()
}
function start(name, executable, args, cwd, env = process.env) {
  const child = spawn(executable, args, { cwd, env, stdio: 'inherit', windowsHide: true })
  children.add(child)
  child.once('error', () => { fail('Could not start ' + name + '.'); stop() })
  child.once('exit', code => {
    children.delete(child)
    if (!stopping) {
      fail(name + ' exited' + (code === null ? '.' : ' with code ' + code + '.'))
      stop()
    }
    if (!children.size) clearTimeout(shutdownTimer)
  })
}

try {
  const [major, minor] = process.versions.node.split('.').map(Number)
  if (major < 22 || major === 22 && minor < 13) throw new Error('Use Node.js 24.x or Node.js 22.13+.')
  if (!existsSync(vite)) throw new Error('Frontend dependencies are missing. Run npm ci in frontend once.')
  if (!existsSync(path.join(backend, '.env'))) throw new Error('Create backend/.env from backend/.env.example and fill your model keys first. Existing configurations are never overwritten.')
  const python = findPython()
  const ports = await Promise.all([8000, 5173].map(async port => ({ port, free: await portFree(port) })))
  console.log('[dev] Python: ' + python)
  for (const { port, free } of ports) console.log('[dev] Port ' + port + ': ' + (free ? 'available' : 'already in use'))
  if (checkOnly) {
    console.log('[dev] Environment check passed. GROBID is managed separately.')
  } else if (ports.some(port => !port.free)) {
    throw new Error('Stop the existing backend/frontend before starting this combined launcher. No existing process was stopped.')
  } else {
    process.on('SIGINT', () => stop('SIGINT'))
    process.on('SIGTERM', () => stop('SIGTERM'))
    console.log('[dev] Local Demo: http://127.0.0.1:5173/app/manuscripts')
    console.log('[dev] Backend: http://127.0.0.1:8000/docs')
    console.log('[dev] Press Ctrl+C to stop. Start GROBID separately when needed. Backend does not auto-reload during jobs.')
    start('Backend', python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--workers', '1'], backend)
    if (!stopping) start('Frontend', process.execPath, [vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort'], frontend,
      { ...process.env, VITE_LOCAL_DEMO_MODE: 'true', VITE_API_BASE_URL: 'http://127.0.0.1:8000' })
  }
} catch (error) { fail(error.message); if (children.size) stop() }
